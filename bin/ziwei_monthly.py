# -*- coding: utf-8 -*-
"""月环编排器（月盘产线 + 上月方向句机械对照；与 ziwei_daily.py 同构）。

步骤序（幂等/断点续跑 --from-step N/每步 JSON 日志落 _verify/monthly_log/<YYYY-MM>.jsonl/失败即停明示步骤）：
  m1 底座闸链（check_base liunian 当年——MISSING 提示先跑年盘产线）
  m2 排月盘（core/liupan.py --level liuyue --month；报告在则跳）
  m3 派发生成（只生成不执行——dispatch 脚本在位校验）
  m4 质检（check_outputs；FAIL→refill 提示转人工）
  m5 组装（assemble_report）
  m6 月简报派单生成（fill_brief_prompt --type liuyue；简报在则跳）
  m7 check_brief（--type liuyue）
  m8 extract_predictions（--layer liuyue --date YYYY-MM；已入队/已 resolve 跳）
  m9 上月方向句机械对照（read_returns --month-aggregate 上月 × pending layer=liuyue；
     只算对照建议不落账——append/resolve 须 agent 四段 theory，见 m10 清单）
  m10 台账日更 + agent 人工点清单

用法：
  python ziwei_monthly.py --person <person> [--month YYYY-MM] [--from-step N] [--root <workspace>]

开源形态：
  - 命主工作区缺省=SKILL_ROOT 同级 ziwei-workspace/（不存在则建目录+样例结构说明），--root 可覆盖；
  - anchors.json 缺失可跑（本地 ZERO_ROOT 锚点解析保留回退）；
  - 判定链依赖 read_returns（含 anchors LEDGER_ROOT）不可用→m9 跳过月度对照不 FAIL，
    收益数据可经 returns_import --csv 导入后重跑。
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_ROOT, "verify", "bin"))
from common import resolve_data_dir  # noqa: E402

try:  # 开源形态守卫：read_returns 导入期依赖 anchors.json（缺则 SystemExit）
    import read_returns  # noqa: E402
    READ_RETURNS_OK = True
except (ImportError, SystemExit):
    read_returns = None
    READ_RETURNS_OK = False

try:
    with open(os.path.join(SKILL_ROOT, "..", "..", "..", "anchors.json"), encoding="utf-8") as f:
        ANCHORS = json.load(f)
except (OSError, ValueError):
    ANCHORS = {}
DATA_DIR = resolve_data_dir(None)

DEFAULT_PERSON_ROOT = os.path.join(os.path.dirname(SKILL_ROOT), "ziwei-workspace")
PERSON_ROOT = DEFAULT_PERSON_ROOT  # main() 按 --root 就近解析后覆写


def resolve_person_root(cli_root):
    """命主工作区三级就近解析：--root 显式 > SKILL_ROOT 同级 ziwei-workspace/（在位）
    > 本地 ZERO_ROOT 锚点 output/output（回退）；三级皆无则建
    ziwei-workspace/ 并落样例结构说明（开源开箱即跑）。"""
    if cli_root:
        return os.path.abspath(cli_root)
    if os.path.isdir(DEFAULT_PERSON_ROOT):
        return DEFAULT_PERSON_ROOT
    anchored = os.path.join(ANCHORS.get("ZERO_ROOT", ""), "output", "output")
    if ANCHORS.get("ZERO_ROOT") and os.path.isdir(anchored):
        return anchored
    root = DEFAULT_PERSON_ROOT
    os.makedirs(root, exist_ok=True)
    readme = os.path.join(root, "README.md")
    with open(readme, "w", encoding="utf-8", newline="\n") as f:
        f.write("# ziwei-workspace 命主工作区\n\n"
                "样例结构（命主名自定，禁硬编码入代码）：\n\n"
                "```\n<person>/\n  Yuanju/报告.md\n  Daxian/报告-第N限.md\n"
                "  Liunian/报告-YYYY.md\n  Liuyue/报告-YYYY-MM.md\n"
                "  Liuyue/temp/<YYYY-MM>/（排盘批次）\n```\n\n"
                "编排器（ziwei_daily/monthly/yearly）经 --root 指向本目录，缺省即本目录。\n")
    return root

SIDE_KWS = ("期货", "投机", "股票", "长线", "总盘", "总收益", "总账")
BAD_WORDS = ("受损", "劳而少获", "亏损", "亏")
GOOD_WORDS = ("正收益", "受益", "偏吉", "平稳", "盈")


class StepFail(Exception):
    """步骤失败即停。"""


class Logger:
    def __init__(self, month):
        d = os.path.join(DATA_DIR, "monthly_log")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, "%s.jsonl" % month)
        self.month = month

    def log(self, step, name, status, detail=""):
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "month": self.month, "step": step, "name": name,
               "status": status, "detail": detail}
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("[%s] m%d %s：%s" % (status, step, name, detail))
        if status == "FAIL":
            raise StepFail("m%d %s 失败——断点续跑：--from-step %d" % (step, name, step))
        return rec


def run(cmd):
    """跑子进程，返回 (rc, stdout+stderr 合流文本)。PYTHONUTF8=1。"""
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable] + cmd, capture_output=True, env=env, cwd=SKILL_ROOT)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def classify(pred):
    """预判句三分类（与 ziwei_daily/auto_judge 口径同源）。"""
    if "若" in pred:
        return "conditional"
    for cl in re.split(r"[，。；,;.]", pred):
        sides = [k for k in SIDE_KWS if k in cl]
        bad = [w for w in BAD_WORDS if w in cl]
        good = [w for w in GOOD_WORDS if w in cl]
        if sides and (bad or good) and not (bad and good):
            return "direction"
    return "assertion"


def expected_sign(pred):
    """方向句期望符号：正/负/None（无法判）。"""
    for cl in re.split(r"[，。；,;.]", pred):
        if any(k in cl for k in SIDE_KWS):
            if any(w in cl for w in GOOD_WORDS) and not any(w in cl for w in BAD_WORDS):
                return "+"
            if any(w in cl for w in BAD_WORDS) and not any(w in cl for w in GOOD_WORDS):
                return "-"
    return None


def load_pending_prefix(person, layer, prefix):
    """pending 中 person+layer 且 date 前缀匹配（月级双形态兼容：YYYY-MM / 月末日 YYYY-MM-DD）。"""
    out = []
    path = os.path.join(DATA_DIR, "pending_predictions.jsonl")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("person") == person and rec.get("layer") == layer \
                        and str(rec.get("date", "")).startswith(prefix) \
                        and rec.get("status") == "待验证":
                    out.append(rec)
    return out


def already_resolved(person, layer, prefix):
    path = os.path.join(DATA_DIR, "resolved_predictions.jsonl")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("person") == person and rec.get("layer") == layer \
                    and str(rec.get("date", "")).startswith(prefix):
                return True
    return False


def prev_month(month):
    y, m = int(month[:4]), int(month[5:7])
    return "%04d-%02d" % ((y, m - 1) if m > 1 else (y - 1, 12))


def _total_of(row):
    """总余额：E 列直读；公式无缓存值时回退 股票+期货 合并。"""
    t = read_returns.cell(row, read_returns.COL_TOTAL)
    if t not in (None, ""):
        return t
    s = read_returns.cell(row, read_returns.COL_STOCK)
    f = read_returns.cell(row, read_returns.COL_FUT)
    if isinstance(s, (int, float)) and isinstance(f, (int, float)):
        return s + f
    return None


def month_aggregate(month):
    """月度聚合：月度总收益=（该月最后有数据行总余额-上月最后有数据行总余额）/上月总余额。
    本地实现（跨年份 xlsx 全量并读 + E 列公式回退）——read_returns --month-aggregate
    只读最新一个文件且依赖 E 列缓存值，跨年/无缓存均 no_data。"""
    rows = []
    for path in sorted(glob.glob(os.path.join(read_returns.LEDGER_DIR, "daily_returns_*.xlsx"))):
        rows.extend(read_returns.read_rows(path)[read_returns.DATA_START_ROW - 1:])

    def last_row_with_total(prefix):
        last = None
        for row in rows:
            d = read_returns.fmt_date(read_returns.cell(row, read_returns.COL_DATE))
            if d and d.startswith(prefix) and _total_of(row) is not None:
                last = row
        return last

    y, m = int(month[:4]), int(month[5:7])
    prev = prev_month(month)
    cur_row, prev_row = last_row_with_total(month), last_row_with_total(prev)
    if cur_row is None or prev_row is None:
        missing = month if cur_row is None else prev
        return {"status": "no_data", "message": "%s 无数据，无法聚合月度收益" % missing}
    cur_total, prev_total = _total_of(cur_row), _total_of(prev_row)
    return {"month": month,
            "total_return": cur_total / prev_total - 1 if prev_total else "no_data",
            "month_end_total": cur_total, "prev_month_end_total": prev_total}


def m1(log, person, year):
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_base.py"),
                    "--level", "liunian", "--key", year, "--person", person])
    if rc == 0 and "BASE-OK" in text:
        log.log(1, "底座闸链", "OK", text.strip().splitlines()[0])
    else:
        log.log(1, "底座闸链", "FAIL",
                "当年流年底座缺失——先按 docs/pipeline_layers.md 跑年盘产线（ziwei_yearly.py --person %s --year %s）：%s"
                % (person, year, text.strip().splitlines()[0] if text.strip() else "无输出"))


def report_path(person, month):
    return os.path.join(PERSON_ROOT, person, "Liuyue", "报告-%s.md" % month)


def brief_path(person, month):
    return os.path.join(PERSON_ROOT, person, "Liuyue", "报告-%s-简报.md" % month)


def batch_of(person, month):
    return os.path.join(PERSON_ROOT, person, "Liuyue", "temp", month)


def m2(log, person, month, results):
    report = report_path(person, month)
    results["report"] = report
    if os.path.isfile(report):
        log.log(2, "排月盘", "OK", "报告已存在，跳过生成：%s" % report)
        return
    rc, text = run([os.path.join(SKILL_ROOT, "core", "liupan.py"),
                    "--pan", os.path.join(SKILL_ROOT, "pans", "%s.json" % person),
                    "--level", "liuyue", "--month", month,
                    "--person", person, "--outdir"])
    if rc != 0:
        log.log(2, "排月盘", "FAIL", text.strip()[:300])
    m = re.search(r"批次目录：(.+)", text)
    if not m:
        log.log(2, "排月盘", "FAIL", "未解析到批次目录行：%s" % text.strip()[:200])
    results["batch"] = m.group(1).strip()
    log.log(2, "排月盘", "OK", "批次目录：%s" % results["batch"])


def m3(log, person, month, results):
    batch = results.get("batch") or batch_of(person, month)
    results["batch"] = batch
    if not os.path.isdir(batch):
        log.log(3, "派发生成", "FAIL", "批次目录不存在：%s" % batch)
    script = os.path.join(batch, "dispatch_liupan.workflow.js")
    if os.path.isfile(script):
        log.log(3, "派发生成", "OK",
                "dispatch 脚本在位（待 agent 后台作业化执行，禁前台）：%s" % script)
    else:
        log.log(3, "派发生成", "FAIL", "缺 dispatch_liupan.workflow.js：%s" % script)


def m4(log, person, month, results):
    batch = results.get("batch") or batch_of(person, month)
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_outputs.py"),
                    "--dir", batch, "--no-shengong"])
    if rc == 0:
        log.log(4, "质检", "OK", "check_outputs PASS")
        return
    rc2, text2 = run([os.path.join(SKILL_ROOT, "bin", "refill.py"), "--dir", batch])
    msg = "check_outputs FAIL；refill 输出：%s——转人工：后台执行补发脚本后重跑本步骤（--from-step 4）" \
          % text2.strip()[-200:]
    log.log(4, "质检", "FAIL", msg)


def m5(log, person, month, results):
    batch = results.get("batch") or batch_of(person, month)
    report = results.get("report") or report_path(person, month)
    if os.path.isfile(report):
        log.log(5, "组装", "OK", "报告已存在，跳过组装（重做=先删旧报告）：%s" % report)
        return
    head = os.path.join(batch, "head.md")
    cmd = [os.path.join(SKILL_ROOT, "bin", "assemble_report.py"),
           "--batch", batch, "--out", report]
    if os.path.isfile(head):
        cmd += ["--head", head]
    rc, text = run(cmd)
    if rc != 0:
        log.log(5, "组装", "FAIL", text.strip()[:300])
    log.log(5, "组装", "OK",
            "报告落盘：%s%s" % (report, "" if os.path.isfile(head) else "（无 head.md——agent 补写分析头后可重组装）"))


def m6(log, person, month, results):
    brief = brief_path(person, month)
    results["brief"] = brief
    if os.path.isfile(brief):
        results = results or {}
        log.log(6, "简报派单生成", "OK", "简报已存在，跳过派单生成：%s" % brief)
        results["brief_preexisting"] = True
        return
    batch = results.get("batch") or batch_of(person, month)
    prompt_path = os.path.join(batch, "brief_prompt.md")
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "fill_brief_prompt.py"),
                    "--type", "liuyue", "--person", person,
                    "--report", results.get("report") or report_path(person, month),
                    "--out", brief, "--save", prompt_path])
    if rc != 0:
        log.log(6, "简报派单生成", "FAIL", text.strip()[:300])
    log.log(6, "简报派单生成", "OK", "派单 prompt 落盘（待 agent 派发写简报）：%s" % prompt_path)


def m7(log, person, month, results):
    if results.get("brief_preexisting"):
        log.log(7, "check_brief", "OK", "幂等重放：简报为既有产物（已过当日闸），跳过")
        return
    brief = results.get("brief") or brief_path(person, month)
    if not os.path.isfile(brief):
        log.log(7, "check_brief", "OK", "简报未写——待 agent 写完后重跑：--from-step 7")
        return
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_brief.py"),
                    brief, "--type", "liuyue"])
    if rc != 0:
        log.log(7, "check_brief", "FAIL", text.strip()[:400])
    log.log(7, "check_brief", "OK", "简报过闸（liuyue 模板）")


def m8(log, person, month, results):
    brief = results.get("brief") or brief_path(person, month)
    if not os.path.isfile(brief):
        log.log(8, "extract_predictions", "OK",
                "简报未写——待 agent 写简报后重跑：--from-step 8")
        return
    if load_pending_prefix(person, "liuyue", month):
        log.log(8, "extract_predictions", "OK", "该月已有 liuyue 条目在队，跳过（幂等防重复入队）")
        return
    if already_resolved(person, "liuyue", month):
        log.log(8, "extract_predictions", "OK", "该月条目已 resolve，跳过（幂等）")
        return
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "extract_predictions.py"),
                    "--brief", brief, "--person", person, "--date", month, "--layer", "liuyue"])
    if rc != 0:
        log.log(8, "extract_predictions", "FAIL", text.strip()[:300])
    log.log(8, "extract_predictions", "OK",
            text.strip().splitlines()[-1] if text.strip() else "完成")


def m9(log, person, month, results):
    """上月方向句机械对照：只算建议不落账（append/resolve 须 agent 四段 theory）。"""
    if not READ_RETURNS_OK:
        log.log(9, "月度收益对照", "OK",
                "read_returns 不可用（开源形态）——跳过月度对照；收益数据可经 returns_import --csv 导入后重跑 --from-step 9")
        results["m9_skip"] = True
        return
    prev = prev_month(month)
    agg = month_aggregate(prev)
    if agg.get("status"):
        log.log(9, "月度收益对照", "OK", "上月（%s）月聚合不可用（%s：%s）——跳过判定（no_data 口径）"
                % (prev, agg.get("status"), agg.get("message", "")))
        results["m9_skip"] = True
        return
    total_return = agg.get("total_return")
    if total_return in (None, "", "no_data"):
        log.log(9, "月度收益对照", "OK", "上月（%s）月聚合 total 缺数——跳过判定" % prev)
        results["m9_skip"] = True
        return
    recs = load_pending_prefix(person, "liuyue", prev)
    directions, others = [], []
    for rec in recs:
        (directions if classify(rec.get("prediction", "")) == "direction" else others).append(rec)
    if not directions:
        log.log(9, "月度收益对照", "OK",
                "上月（%s）无待验证 liuyue 方向句（条目 %d 条均非方向句）——跳过判定"
                % (prev, len(recs)))
        results["m9_skip"] = True
        return
    actual = "+" if float(total_return) >= 0 else "-"
    suggests = []
    for rec in directions:
        want = expected_sign(rec.get("prediction", ""))
        if want is None:
            suggests.append("%s：方向句未标——跳过（转 agent 判定）" % rec["pred_id"])
            continue
        verdict = "accurate" if want == actual else "inaccurate"
        suggests.append("%s：期望%s / 实际%s（月聚合 total=%.4f）→ 建议 %s"
                        % (rec["pred_id"], want, actual, float(total_return), verdict))
    results["m9_prev_month"] = prev
    results["m9_suggests"] = suggests
    results["m9_others"] = [r["pred_id"] for r in others]
    log.log(9, "月度收益对照", "OK",
            "上月 %s 月聚合 total=%.4f（%s）；方向句 %d 条对照建议：\n  %s"
            % (prev, float(total_return), actual, len(directions), "\n  ".join(suggests)))


def m10(log, person, month, results):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "update_trading_ledger.py"),
                    "--date", datetime.date.today().isoformat()])
    if rc != 0:
        log.log(10, "台账+汇总", "FAIL", text.strip()[:300])
    lines = [
        "①派发执行：m3 dispatch_liupan.workflow.js 后台作业化执行（run_in_background），完成后从 m4 续跑 --from-step 4",
        "②分析头：m5 若无 head.md——读 12 宫结论补写批次 head.md 后重组装",
        "③简报写手：m6 派单 prompt 派发写简报；写完从 m7 续跑 --from-step 7",
        "④月度判卷（m9 建议）：" + (
            "m9 已给对照建议——判卷纪律硬序：先读条目 confidence 累入 calibration.json（时序铁律：resolve 前累档）→ append 月度收益事件（--level liuyue --soft-gate，theory 四段完整，素材=该月流月批次 input_03 切片+级联流年财帛结论+月聚合归因对照段）→ 再 resolve（--no-capture）；禁机器简版占位"
            if results.get("m9_suggests") else "m9 本轮无可判方向句（no_data/未标/无条目），无判卷动作"),
        "⑤月中背离预警：每月 15 日月聚合（月中至今累计）对照当月流月方向句，背离→简报草稿区附提示行（仅提示不判定）",
        "⑥简报呈现：会话内呈现月报简报要点（不送达=未完成）",
    ]
    if results.get("m9_others"):
        lines.append("⑦非方向句（条件/断言）：" + "、".join(results["m9_others"])
                     + "——按到窗/触发口径由 agent 判定，未到窗不动")
    log.log(10, "台账+汇总", "OK", "agent 人工点清单：\n  " + "\n  ".join(lines))
    print("\n═ agent 人工点清单 ═")
    for ln in lines:
        print("  " + ln)


def main():
    ap = argparse.ArgumentParser(description="月环编排器（月盘产线+上月方向句对照）")
    ap.add_argument("--person", required=True)
    ap.add_argument("--month", default=datetime.date.today().strftime("%Y-%m"), help="YYYY-MM，缺省当月")
    ap.add_argument("--from-step", dest="from_step", type=int, default=1, help="断点续跑起始步骤（1-10）")
    ap.add_argument("--root", default=None,
                    help="命主工作区根（缺省=SKILL_ROOT 同级 ziwei-workspace/，不存在则建样例结构）")
    args = ap.parse_args()
    global PERSON_ROOT
    PERSON_ROOT = resolve_person_root(args.root)
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", args.month):
        print("错误：--month 须为 YYYY-MM")
        sys.exit(2)
    if not (1 <= args.from_step <= 10):
        print("错误：--from-step 须为 1-10")
        sys.exit(2)
    month = args.month
    results = {}
    log = Logger(month)
    steps = [
        lambda: m1(log, args.person, month[:4]),
        lambda: m2(log, args.person, month, results),
        lambda: m3(log, args.person, month, results),
        lambda: m4(log, args.person, month, results),
        lambda: m5(log, args.person, month, results),
        lambda: m6(log, args.person, month, results),
        lambda: m7(log, args.person, month, results),
        lambda: m8(log, args.person, month, results),
        lambda: m9(log, args.person, month, results),
        lambda: m10(log, args.person, month, results),
    ]
    print("═ ziwei_monthly %s（%s；from-step=%d；日志=%s）═" % (month, args.person, args.from_step, log.path))
    try:
        for i, fn in enumerate(steps, 1):
            if i < args.from_step:
                continue
            fn()
    except StepFail as e:
        print("\nFAIL：%s" % e)
        sys.exit(1)
    print("\n月环完成（10 步）——日志：%s" % log.path)


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
