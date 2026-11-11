# -*- coding: utf-8 -*-
"""读 pending_predictions.jsonl → 输出昨日待验证项追问清单 + 分级过期自动关闭。

用法：check_pending.py [--date 指定日期，默认昨天] [--data-dir 目录]

stdout 输出 JSON 数组（agent 据此生成追问）：
[{"pred_id":"...","palace":"财帛","prediction":"投机大概率亏损","追问":"实际交易了吗？结果？"}]
副作用（分级过期）：status=="待验证" 条目按层过期——
liuri/liushi：date < (指定日期-EXPIRE_DAYS 天) 关闭（EXPIRE_DAYS 单一真源=common.py）；
liuyue：date（YYYY-MM 或月末日）月份 < 指定日期所在月即关闭；liunian：年份 < 指定年份即关闭；
daxian/yuanju：长期在验——不自动关闭不移出（统计单列"长期在验 N 条"，仅 resolve_prediction 关闭）。
关闭=置 status="未触发（未回应默认）"并从文件移出。
零第三方依赖。
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EXPIRE_DAYS, resolve_data_dir

PENDING_FILE = "pending_predictions.jsonl"


def parse_date(s):
    return datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def load(path):
    recs = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except ValueError:
                        pass
    return recs


def atomic_save(path, recs, expect_absent_ids):
    """原子重写：滚动备份→写临时文件→读回校验→os.replace。

    expect_absent_ids：本次应被移出的 pred_id 集合；其余条目必须全部在位，
    总条数必须等于内存预期——任一不符抛 RuntimeError（防并发丢写静默吞行）。
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        original = f.read()
    with open(path + ".bak", "w", encoding="utf-8", newline="") as f:
        f.write(original)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    reread = load(tmp)
    if len(reread) != len(recs):
        raise RuntimeError("写后读回校验失败：%s 条数 %d != 预期 %d" % (path, len(reread), len(recs)))
    reread_ids = {r.get("pred_id") for r in reread}
    expect_ids = {r.get("pred_id") for r in recs}
    leaked = reread_ids & expect_absent_ids
    if leaked:
        raise RuntimeError("写后读回校验失败：应移出仍在文件：%s" % sorted(leaked))
    missing = expect_ids - reread_ids
    if missing:
        raise RuntimeError("写后读回校验失败：应保留却丢失：%s（备份在 %s.bak）" % (sorted(missing), path))
    os.replace(tmp, path)


def followup(prediction):
    """按预测句生成一句简短追问（前 30 字截断保简洁）。"""
    core = prediction[:30] + ("…" if len(prediction) > 30 else "")
    return "「%s」——实际发生了吗？结果如何？" % core


def main():
    ap = argparse.ArgumentParser(description="昨日预测追问清单+过期关闭")
    ap.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD，默认昨天")
    ap.add_argument("--data-dir", default=None, help="印证库目录（默认 _verify）")
    args = ap.parse_args()

    if args.date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
            print("错误：--date 须为 YYYY-MM-DD")
            sys.exit(2)
        target = parse_date(args.date)
    else:
        target = datetime.date.today() - datetime.timedelta(days=1)

    path = os.path.join(resolve_data_dir(args.data_dir), PENDING_FILE)
    recs = load(path)
    expire_line = target - datetime.timedelta(days=EXPIRE_DAYS)
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    expired = 0
    long_pending = 0  # daxian/yuanju 长期在验（不自动关闭）

    expired_ids = set()
    items = []
    for rec in recs:
        if rec.get("status") != "待验证":
            continue
        layer = rec.get("layer", "liuri")
        date_s = rec.get("date", "")
        # 分级过期：liuri/liushi=日级（现行 EXPIRE_DAYS）；liuyue=次月即过期；
        # liunian=次年即过期；daxian/yuanju=长期在验跳过（date=第N限/终身非日期形态）
        if layer in ("daxian", "yuanju"):
            long_pending += 1
            continue
        if layer == "liuyue":
            if date_s[:7] < target.strftime("%Y-%m"):
                rec["status"] = "未触发（未回应默认）"
                rec["verified_at"] = now
                expired += 1
                expired_ids.add(rec.get("pred_id"))
            continue
        if layer == "liunian":
            if date_s[:4] < target.strftime("%Y"):
                rec["status"] = "未触发（未回应默认）"
                rec["verified_at"] = now
                expired += 1
                expired_ids.add(rec.get("pred_id"))
            continue
        try:
            d = parse_date(date_s)
        except (ValueError, IndexError):
            continue
        if d == target:
            items.append({
                "pred_id": rec["pred_id"],
                "palace": rec.get("palace", ""),
                "prediction": rec.get("prediction", ""),
                "追问": followup(rec.get("prediction", "")),
            })
        elif d < expire_line:
            rec["status"] = "未触发（未回应默认）"
            rec["verified_at"] = now
            expired += 1
            expired_ids.add(rec.get("pred_id"))

    if expired:
        # 过期条目关闭后即从文件移出（队列保持纯待办语义）
        atomic_save(path, [r for r in recs if r.get("pred_id") not in expired_ids], expired_ids)
    print(json.dumps(items, ensure_ascii=False))
    print("（%s 待验证 %d 条；过期关闭 %d 条；长期在验 %d 条）"
          % (target.isoformat(), len(items), expired, long_pending), file=sys.stderr)


if __name__ == "__main__":
    main()
