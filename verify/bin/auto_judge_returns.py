# -*- coding: utf-8 -*-
"""收益环自动判卷：一条命令完成「取数 → 方向句匹配 → 逐端符号判定 → 累档 → resolve → append」。

根治口径分裂：事件判符合（无方向句）与队列方向句 resolve 原本零交叉，本脚本把两条线接到
同一份收益真值上——append 与 resolve 在同一轮同一数据下闭环。

用法：auto_judge_returns.py [--data-dir 目录] [--returns-json 文件] [--csv 收益CSV]
                            [--date YYYY-MM-DD]
  --data-dir     验证库目录（默认同 resolve_prediction 三级解析）
  --returns-json 覆盖收益取数：直接读 read_returns 形态的 JSON 文件（测试/回放用）；
                 缺省子进程调 read_returns.py 取最新可录入交易日条目
  --csv          通用收益数据源：UTF-8 CSV（表头 date,total[,stock,futures]），
                 经 returns_import.py 转同构 entry（开源部署用，与 --returns-json 互斥）
  --date         判定该日方向句（断档补录逐日判卷）；缺省判最新交易日

判定口径（总账口径——弃期货/股票分端）：
  方向句一律按当日总收益±判定（read_returns 新增 total=股票+期货合并日变动%）。
  端关键词仅用于识别方向句：期货/投机→futures；股票/长线→stock；总盘/总收益/总账→total
  凶向=受损/劳而少获/亏损/亏；吉向=正收益/受益/偏吉/平稳/盈（震荡档作废）
  判定：二分，0 归盈侧——凶向：总收益<0=accurate，>=0=inaccurate；吉向：总收益>=0=accurate，<0=inaccurate。
  同句凶吉并见=方向冲突需人工；总收益缺失（no_data）→ 整条待数据；
  条件句（含「若」）、方向词全缺失 → 需人工，不动。

时序铁律：先按 confidence 档累档 calibration（resolved+1 / accurate+1），再 resolve，
再 append。幂等：events 当日已有同 pred_id（或同文本）→ 整条跳过不重复累档。
零第三方依赖；写操作原子写（tmp + os.replace）。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

BIN = os.path.dirname(os.path.abspath(__file__))
PENDING_FILE = "pending_predictions.jsonl"
CALIBRATION_FILE = "calibration.json"

# 端关键词 → 收益端字段（期货/投机→futures；股票/长线→stock；总盘/总收益/总账→total）
SIDE_KEYWORDS = [
    ("期货", "futures"),
    ("投机", "futures"),
    ("股票", "stock"),
    ("长线", "stock"),
    ("总盘", "total"),
    ("总收益", "total"),
    ("总账", "total"),
]
BAD_WORDS = ("受损", "劳而少获", "亏损", "亏")
GOOD_WORDS = ("正收益", "受益", "偏吉", "平稳", "盈")
# 平稳类：日级不可证伪（对小幅波动无法证伪）
CALM_WORDS = ("平稳", "偏吉")
# 主端优先级（遗留分端兼容用）：total 优先——总账口径下不再分端定胜负
SIDE_PRIORITY = ("total", "futures", "stock")

RETURN_FIELDS = {"futures": "futures_return", "stock": "stock_return", "total": "total_return"}
SIDE_CN = {"futures": "期货端", "stock": "股票端", "total": "总盘端"}


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def fetch_returns(returns_json, csv_path, date_arg):
    """取可录入交易日条目。--returns-json 直读文件；--csv 经 returns_import.py 导入；
    缺省子进程调 read_returns.py（--date 给定则取该日条目，缺省取最新——断档补录逐日判卷用）。"""
    if returns_json:
        with open(returns_json, encoding="utf-8") as f:
            return json.load(f)
    if csv_path:
        cmd = [sys.executable, os.path.join(BIN, "returns_import.py"),
               "--csv", csv_path]
        if date_arg:
            cmd += ["--date", date_arg]
        r = subprocess.run(cmd, capture_output=True, env=dict(os.environ, PYTHONUTF8="1"))
        text = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not text:
            print("错误：returns_import.py 导入失败：%s"
                  % (r.stderr.decode("utf-8", "replace").strip() or "无输出"))
            sys.exit(2)
        rec = json.loads(text.splitlines()[-1])
        if rec.get("status"):
            print("无收益数据（%s：%s），本轮无判卷" % (rec.get("status"), rec.get("message", "")))
            sys.exit(0)
        return rec
    env = dict(os.environ, PYTHONUTF8="1")
    cmd = [sys.executable, os.path.join(BIN, "read_returns.py")]
    if date_arg:
        cmd += ["--date", date_arg]
    r = subprocess.run(cmd, capture_output=True, env=env)
    text = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0 or not text:
        print("错误：read_returns.py 取数失败：%s"
              % (r.stderr.decode("utf-8", "replace").strip() or "无输出"))
        print("提示：开源部署无本地收益表——请用 --csv 提供收益数据"
              "（表头 date,total[,stock,futures]，格式见 returns_import.py --make-sample）")
        sys.exit(2)
    try:
        rec = json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        print("错误：read_returns.py 输出不可解析：%r" % text[:200])
        sys.exit(2)
    if rec.get("status"):
        print("无收益数据（%s：%s），本轮无判卷" % (rec.get("status"), rec.get("message", "")))
        sys.exit(0)
    return rec


def parse_clauses(prediction):
    """prediction → [(side_field, 凶/吉, 命中词)] 子句列表。
    返回 None=条件句/子句内歧义（多端词或凶吉并见）需人工；
    'nodir'=无端或无方向词（非方向句）。"""
    if "若" in prediction and "命中标准" not in prediction:
        return None
    body = prediction.split("命中标准")[0]  # 二分句式：命中标准段为判定说明非预判子句
    clauses = re.split(r"[，。；,;.]", body)
    parsed = []
    for cl in clauses:
        sides = [f for kw, f in SIDE_KEYWORDS if kw in cl]
        bad = [w for w in BAD_WORDS if w in cl]
        good = [w for w in GOOD_WORDS if w in cl]
        if not sides and not bad and not good:
            continue
        if len(sides) > 1 or (bad and good):
            return None
        if not sides or (not bad and not good):
            return None
        if bad:
            parsed.append((sides[0], "凶", bad[0]))
        else:
            parsed.append((sides[0], "吉", good[0]))
    if not parsed:
        return "nodir"
    return parsed


def pick_main(parsed):
    """分端独立判定主端选择（遗留分端兼容）：优先级 total > futures > stock；
    同端出现多条断言=同端冲突 → None（需人工）。"""
    by_side = {}
    for side, direction, word in parsed:
        if side in by_side and by_side[side][0] != direction:
            return None
        by_side[side] = (direction, word)
    for side in SIDE_PRIORITY:
        if side in by_side:
            return side
    return None


TOTAL_FIELD = "total"
TOTAL_CN = "总账"


def resolve_total(parsed):
    """总账口径：方向句一律按当日总收益±判定，不再主端分端。
    返回方向（凶/吉）；凶吉并见='conflict'（需人工）；无方向词=None。"""
    directions = {d for _, d, _ in parsed}
    if "凶" in directions and "吉" in directions:
        return "conflict"
    for d in ("凶", "吉"):
        if d in directions:
            return d
    return None


def judge_total(direction, ret):
    """总收益符号 vs 预判方向 → accurate/inaccurate（二分，0 归盈侧：>=0=吉侧命中）。"""
    ret = float(ret)
    negative = ret < 0
    return "accurate" if negative == (direction == "凶") else "inaccurate"


def judge(side, direction, ret):
    """端收益率符号 vs 预判方向 → accurate/inaccurate（>=0=吉侧命中）。"""
    negative = float(ret) < 0
    hit_bad = direction == "凶"
    return "accurate" if negative == hit_bad else "inaccurate"


def already_recorded(data_dir, person, date, pred_id, text):
    """幂等闸：events 该命主当日已有同 pred_id → ('pred', event_id)（纯幂等，整条跳过）；
    仅同文本不同 pred_id（同日多预判共用一条事件）→ ('text', event_id)（仍关队列，跳过 append）。"""
    text_hit = None
    for path in sorted(glob.glob(os.path.join(data_dir, "events_*.jsonl"))):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("person") != person or rec.get("event_date") != date:
                continue
            if rec.get("pred_id") == pred_id:
                return "pred", rec.get("event_id", "?")
            if text_hit is None and rec.get("text") == text:
                text_hit = rec.get("event_id", "?")
    return ("text", text_hit) if text_hit else None


def bump_calibration(data_dir, confidence, result):
    path = os.path.join(data_dir, CALIBRATION_FILE)
    cal = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cal = json.load(f)
    bucket = confidence if confidence in ("高", "中", "低") else "未标"
    slot = cal.setdefault(bucket, {"resolved": 0, "accurate": 0})
    slot["resolved"] += 1
    if result == "accurate":
        slot["accurate"] += 1
    atomic_write_json(path, cal)
    return bucket


def fmt_pct(v):
    return ("+" if v >= 0 else "") + "%.2f%%" % (v * 100)


def fmt_wan(v):
    return ("+" if v >= 0 else "") + "%.1f万" % (v / 10000)


def event_text(entry):
    """事件 text 照 read_returns 数据格式：投资收益X%——股票x%（±N万）/期货x%（±N万）。"""
    parts = []
    for side, rkey, pkey in (("stock", "stock_return", "stock_pnl"),
                             ("futures", "futures_return", "futures_pnl")):
        r, p = entry.get(rkey), entry.get(pkey)
        if r is not None:
            seg = {"stock": "股票", "futures": "期货"}[side] + fmt_pct(r)
            if p is not None:
                seg += "（%s）" % fmt_wan(p)
            parts.append(seg)
    _tv = entry["total_return"] if isinstance(entry.get("total_return"), (int, float)) else (entry.get("total") if isinstance(entry.get("total"), (int, float)) else None)
    if _tv is None:
        return None  # no_data/缓存缺形态——上层按数据未就绪处理
    return "投资收益%s——%s" % (fmt_pct(float(_tv)), "/".join(parts))


def run_sub(script, args):
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, os.path.join(BIN, script)] + args,
                       capture_output=True, env=env)
    for stream in (r.stdout, r.stderr):
        for line in stream.decode("utf-8", "replace").strip().splitlines():
            if line:
                print("  | %s" % line)
    if r.returncode != 0:
        print("错误：%s 退出码 %d" % (script, r.returncode))
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="收益环自动判卷")
    ap.add_argument("--person", dest="person", default="", help="按命主过滤（空=全库）")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--returns-json", dest="returns_json", default="",
                    help="覆盖取数：read_returns 形态 JSON 文件（测试/回放）")
    ap.add_argument("--csv", dest="csv", default="",
                    help="通用收益数据源：UTF-8 CSV（date,total[,stock,futures]），经 returns_import 导入")
    ap.add_argument("--date", dest="date", default="",
                    help="判定该日方向句（断档补录逐日判卷）；缺省判最新交易日")
    args = ap.parse_args()

    sys.path.insert(0, BIN)
    from common import resolve_data_dir
    data_dir = resolve_data_dir(args.data_dir)

    if args.returns_json and args.csv:
        ap.error("--returns-json 与 --csv 互斥")
    entry = fetch_returns(args.returns_json, args.csv, args.date)
    date = entry.get("date")
    if args.date and date != args.date:
        print("错误：--date %s 无对应收益条目（read_returns 返回 %r）" % (args.date, date))
        sys.exit(2)
    if not date:
        print("错误：收益条目缺 date：%r" % entry)
        sys.exit(2)
    _et = event_text(entry)
    if _et is None:
        print("数据未就绪（total=no_data 形态）——挂待数据，明晚数据齐后重判：%s" % date)
        sys.exit(0)
    print("收益取数：%s %s" % (date, _et))

    pending_path = os.path.join(data_dir, PENDING_FILE)
    records = []
    if os.path.isfile(pending_path):
        with open(pending_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue

    matched = [r for r in records
               if r.get("date") == date and r.get("status") == "待验证"
               and (not getattr(args, "person", "") or r.get("person", "") == args.person)]
    if not matched:
        print("无方向句，走符合口径（%s 无待验证方向句，定时任务 agent 按原流程 append）" % date)
        sys.exit(0)

    manual, pending_data, done = [], [], []
    for rec in matched:
        pred = rec.get("prediction", "")
        parsed = parse_clauses(pred)
        if parsed is None:
            manual.append((rec["pred_id"], "条件句或端/方向歧义"))
            continue
        if parsed == "nodir":
            manual.append((rec["pred_id"], "无端/方向关键词"))
            continue
        direction = resolve_total(parsed)
        if direction == "conflict":
            manual.append((rec["pred_id"], "凶吉多断言方向冲突"))
            continue
        if direction is None:
            manual.append((rec["pred_id"], "无方向关键词"))
            continue
        ret = entry.get(TOTAL_FIELD)
        if ret is None or ret == "" or ret == "no_data":
            pending_data.append(rec["pred_id"])
            continue
        outcome = judge_total(direction, float(ret))
        rec["_judge"] = (direction, float(ret), outcome)
        done.append(rec)

    for rec in done:
        direction, ret, outcome = rec["_judge"]
        pred_id, person = rec["pred_id"], rec.get("person", "")
        text = event_text(entry)
        dup = already_recorded(data_dir, person, date, pred_id, text)
        if dup and dup[0] == "pred":
            print("跳过（幂等）：%s events 当日已有记录（event_id=%s）" % (pred_id, dup[1]))
            continue
        detail = "机器判定（总账口径）：%s当日总收益%s 对照方向句（%s向）" % (
            TOTAL_CN, fmt_pct(ret), direction)
        bucket = bump_calibration(data_dir, rec.get("confidence", ""), outcome)
        print("[%s] %s → %s（%s档累档）" % (person, pred_id, outcome, bucket))
        if dup and dup[0] == "text":
            # 同日多预判共用一条事件：关队列+累档，跳过 append（防事件重复，
            # 亦防 --detail 回退匹配改写他条已固化 pred_id）
            print("  | %s" % detail)
            print("  | 当日事件已录（event_id=%s，text 判重）——跳过 append，仅关队列" % dup[1])
            run_sub("resolve_prediction.py",
                    ["--pred-id", pred_id, "--result", outcome,
                     "--no-capture", "--data-dir", data_dir])
            continue
        run_sub("resolve_prediction.py",
                ["--pred-id", pred_id, "--result", outcome, "--detail", detail,
                 "--no-capture", "--data-dir", data_dir])
        theory = "机器判定路径（auto_judge_returns）：收益真值对照流日方向句自动判卷。" \
                 "①归财帛宫（类目映射）②结构原文由当日流日簡报方向句承载：「%s」" \
                 "③机器推理链：收益端符号判定（%s）。④事件对照：%s。" \
                 % (rec.get("prediction", pred_id), detail,
                    "预判准确" if outcome == "accurate" else "预判不准")
        run_sub("append.py",
                ["--person", person, "--date", date, "--category", "交易盈亏",
                 "--text", text, "--level", "liuri",
                 "--result", "预判准确" if outcome == "accurate" else "预判不准",
                 "--pred-id", pred_id, "--theory", theory,
                 "--machine-judge", "--data-dir", data_dir])

    for pid in pending_data:
        print("待数据：%s（当日总收益缺失）" % pid)
    for pid, why in manual:
        print("需人工：%s（%s）" % (pid, why))


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
