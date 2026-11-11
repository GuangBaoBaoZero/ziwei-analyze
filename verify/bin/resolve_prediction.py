# -*- coding: utf-8 -*-
"""接收结构化验证结果 → 更新 pending 状态 → accurate/inaccurate 输出录入指引。

用法：resolve_prediction.py --pred-id <ID> --result accurate|inaccurate|untriggered
                          [--detail "用户原话"] [--data-dir 目录]

accurate/inaccurate → 输出提示走完整录入管线（palace_extract→theory 四段格式（v2，见
theory 四段：①宫位判定依据 ②结构原文+语料判据 ③八要素含行运判语与级联 ④事件对照）→append.py）；
untriggered → 输出「已关闭，不入库」。--detail 非空时同步按 pred_id 直写 events 对应条目 verify_note 字段。
零第三方依赖。
"""
import argparse
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import resolve_data_dir

PENDING_FILE = "pending_predictions.jsonl"
CAPTURE_FILE = "pending_capture.jsonl"
RESULTS = {"accurate": "准确", "inaccurate": "不准", "untriggered": "未触发"}
# 捕获行 result 取值（与 append 侧 RESULTS 白名单「预测准确/预测不准」对齐）
CAPTURE_RESULTS = {"accurate": "预测准确", "inaccurate": "预测不准"}


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

    reread = []
    with open(tmp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                reread.append(json.loads(line))
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


def write_events_verify_note(data_dir, pred_id, detail):
    """--detail 落痕：全库 events_*.jsonl 按 pred_id 匹配 → 直写 verify_note 字段。
    匹配多条=错误退出码 2（拒写）；零匹配=stderr 警告不阻断（人工路径 resolve 先/append 后时序）。"""
    hits = []
    for path in sorted(glob.glob(os.path.join(data_dir, "events_*.jsonl"))):
        with open(path, "r", encoding="utf-8", newline="") as f:
            raw = f.readlines()
        for idx, line in enumerate(raw):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("pred_id") == pred_id:
                hits.append((path, idx, raw, rec))
    if not hits:
        print("⚠ events 全库无 pred_id=%s——verify_note 未写（append 尚未落账时属正常时序）" % pred_id,
              file=sys.stderr)
        return
    if len(hits) > 1:
        print("错误：pred_id=%s 在 events 匹配多条（%d），拒绝写 verify_note" % (pred_id, len(hits)))
        sys.exit(2)
    path, idx, raw, rec = hits[0]
    rec["verify_note"] = detail
    raw[idx] = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(path + ".bak", "w", encoding="utf-8", newline="") as f:
        with open(path, "r", encoding="utf-8", newline="") as src:
            f.write(src.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(raw)
    os.replace(tmp, path)
    print("verify_note 已写：%s（event_id=%s）" % (pred_id, rec.get("event_id", "?")))


def main():
    ap = argparse.ArgumentParser(description="预测验证结果落账")
    ap.add_argument("--pred-id", required=True, help="预测 ID（pred-YYYYMMDD-NNN）")
    ap.add_argument("--result", required=True, choices=["accurate", "inaccurate", "untriggered"], help="验证结果")
    ap.add_argument("--detail", default="", help="用户反馈原话")
    ap.add_argument("--data-dir", default=None, help="印证库目录（默认 _verify）")
    ap.add_argument("--no-capture", action="store_true", help="命中时跳过 pending_capture 待办写入（机器判定路径：事件已由 append 先录，仅关队列）")
    args = ap.parse_args()

    path = os.path.join(resolve_data_dir(args.data_dir), PENDING_FILE)
    if not os.path.isfile(path):
        print("错误：队列不存在：%s" % path)
        sys.exit(2)

    recs, hit, prior_status = [], None, ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("pred_id") == args.pred_id and not hit:
                hit = rec
                prior_status = rec.get("status", "")
                rec["status"] = RESULTS[args.result]
                rec["verify_detail"] = args.detail
                rec["verified_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            recs.append(rec)
    if not hit:
        print("错误：未找到 pred_id=%s" % args.pred_id)
        sys.exit(2)

    if prior_status in RESULTS.values():
        # 已验证滞留条重复 resolve = 幂等 no-op（不重写文件、不重复捕获）
        print("已处理过（%s → %s），本次无变更" % (args.pred_id, prior_status))
        return

    # 已验证条目移出 pending（队列回归纯待办语义；untriggered 同样移出）
    kept = [rec for rec in recs if rec is not hit]
    atomic_save(path, kept, {args.pred_id})
    print("已更新 %s → %s" % (args.pred_id, hit["status"]))
    if args.detail:
        write_events_verify_note(os.path.dirname(path), args.pred_id, args.detail)

    if args.result in CAPTURE_RESULTS and not args.no_capture:
        capture = {
            "pred_id": args.pred_id,
            "person": hit.get("person", ""),
            "date": hit.get("date", ""),
            "layer": hit.get("layer", ""),
            "palace": hit.get("palace", ""),
            "prediction": hit.get("prediction", ""),
            "result": CAPTURE_RESULTS[args.result],
            "detail": args.detail,
            "resolved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "capture_status": "未录入",
        }
        with open(os.path.join(os.path.dirname(path), CAPTURE_FILE), "a",
                  encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(capture, ensure_ascii=False) + "\n")
        print("已捕获至 pending_capture.jsonl（录入待办，勿忘）——完整录入："
              "append.py --from-capture %s --person <人> --date <事件日> "
              "--category <类目> --text <事件> --theory <四段>（prediction/result 自动填充）"
              % args.pred_id)
        if args.result == "inaccurate":
            print("注意：theory 第④段须写预测对照与偏差分析（%s）" % hit["status"])
    elif args.no_capture:
        print("已跳过待办捕获（--no-capture，机器判定路径）")
    else:
        print("已关闭，不入库")


if __name__ == "__main__":
    main()
