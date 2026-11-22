# -*- coding: utf-8 -*-
"""定时任务全链一键化编排器（方案 v1.5 件4）。

步骤序（幂等/断点续跑 --from-step N/每步 JSON 日志落 _verify/daily_log/<date>.jsonl/失败即停明示步骤）：
  s1  底座闸（check_base liuyue 当月）
  s2  四闸采集（check_pending/read_returns/sentry_scan --date 昨日）
  s3  日清机械判定（条件句无操作=untriggered；断言句零记录=inaccurate+累档；
      方向句有数据=auto_judge；无数据=挂待数据不动）
  s4  排盘（报告已存在跳过）
  s5  派发生成（只落批次 dispatch 脚本，不执行——待 agent 后台作业化）
  s6  质检（check_outputs；FAIL→refill 生成补发脚本后打印路径退出转人工，不自动跑 workflow）
  s7  组装（assemble_report）
  s8  简报派单生成（fill_brief_prompt；简报已存在跳过）
  s9  check_brief（期望尾节数=昨日待验证条数自动计算；简报未写则打印参数待 agent）
  s10 extract_predictions（幂等=extract 逐条内容指纹，无整跑闸）
  s11 判定链（read_returns 最新 + auto_judge 缺省最新，幂等）
  s12 台账日更（update_trading_ledger）
  s13 输出汇总（agent 人工点清单）

用法：
  python ziwei_daily.py [--person <person>] [--date YYYY-MM-DD] [--from-step N]
      [--root <workspace>] [--csv <returns.csv>]

开源形态：
  - 命主工作区缺省=SKILL_ROOT 同级 ziwei-workspace/（不存在则建目录+样例结构说明），--root 可覆盖；
  - anchors.json 缺失时运行时 Python 回退 sys.executable（本地 ZERO_ROOT 锚点解析保留）；
  - 哨兵件（sentry_scan）不在包内→s2 跳过不 FAIL；判定链 read_returns 不可用→提示 --csv
    路径参数（与 returns_import 对接，s11 透传 --csv）。
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
from fill_brief_prompt import _is_trading_day, _calendar_candidates  # noqa: E402  # 休市豁免同源：交易日历三级降级


def _ensure_calendar_fresh(log, today):
    """s9 前日历保鲜：包内 trade_calendar.csv 最大 date 距 --date 剩余覆盖 <30 天→
    静默调 update_trade_calendar.py 联网更新（失败 log 提示不阻断）。"""
    cal = next(_calendar_candidates(), None)
    try:
        with open(cal, encoding="utf-8") as f:
            dates = [ln[:10] for ln in f if ln[:4].isdigit()]
        max_d = max(dates)
    except (OSError, ValueError):
        return
    try:
        remain = (datetime.datetime.strptime(max_d, "%Y-%m-%d").date()
                  - datetime.datetime.strptime(today, "%Y-%m-%d").date()).days
    except ValueError:
        return
    if remain < 30:
        try:
            rc = subprocess.call([sys.executable, os.path.join(SKILL_ROOT, "bin", "update_trade_calendar.py")],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            rc = -1
        if rc == 0:
            log.log(0, "trade_calendar", "OK", "日历覆盖不足 30 天，已联网更新（原最大 %s）" % max_d)
        else:
            log.log(0, "trade_calendar", "OK",
                    "日历覆盖不足 30 天（最大 %s），联网更新失败 rc=%s 不阻断——可手动跑 bin/update_trade_calendar.py" % (max_d, rc))


def _anchors():
    """锚点解析：本地在位读 ZERO_ROOT/RUNTIME 等键；开源形态无 anchors.json 回退空表。"""
    try:
        with open(os.path.join(SKILL_ROOT, "..", "..", "..", "anchors.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


ANCHORS = _anchors()
RUNTIME_PY = ANCHORS.get("RUNTIME_PYTHON") or sys.executable
VEC_PY = ANCHORS.get("PYTHON_VEC") or sys.executable
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
                "  Liuri/报告-YYYY-MM-DD.md\n  Liuri/temp/<date>/（排盘批次）\n```\n\n"
                    "编排器（ziwei_daily/monthly/yearly）经 --root 指向本目录，缺省即本目录。\n")
    return root


class StepFail(Exception):
    """步骤失败即停。"""


class Logger:
    def __init__(self, date):
        d = os.path.join(DATA_DIR, "daily_log")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, "%s.jsonl" % date)
        self.date = date

    def log(self, step, name, status, detail=""):
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "date": self.date, "step": step, "name": name,
               "status": status, "detail": detail}
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("[%s] s%d %s：%s" % (status, step, name, detail))
        if status == "FAIL":
            raise StepFail("s%d %s 失败——断点续跑：--from-step %d" % (step, name, step))
        return rec


def run(cmd, py=None, env_extra=None):
    """跑子进程，返回 (rc, stdout+stderr 合流文本)。PYTHONUTF8=1。"""
    exe = py or sys.executable
    env = dict(os.environ, PYTHONUTF8="1")
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([exe] + cmd, capture_output=True, env=env, cwd=SKILL_ROOT)
    text = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return r.returncode, text


def load_pending(date):
    recs = []
    path = os.path.join(DATA_DIR, "pending_predictions.jsonl")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except ValueError:
                        pass
    return [r for r in recs if r.get("date") == date and r.get("status") == "待验证"]


def has_operation_record(person, date):
    """events 当日「今日操作：」前缀条目存在=有操作记录。"""
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "events_%s-*.jsonl" % person))):
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
            if rec.get("person") == person and rec.get("event_date") == date \
                    and str(rec.get("text", "")).startswith("今日操作："):
                return True
    return False


def sentry_candidate_count(text):
    """sentry_scan 输出的候选条数：优先 stdout JSON candidates 数组；
    无 JSON 时按 stderr 统计行「候选 N」（run() 合流后统解析）。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj.get("candidates"), list):
                return len(obj["candidates"])
    m = re.search(r"候选\s*[：:]?\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return -1  # 无法解析（s3 断言句对该日转人工复核）


def bump_calibration(confidence, result):
    """resolve 前累档（时序铁律）；untriggered 不入账由调用方保证。"""
    path = os.path.join(DATA_DIR, "calibration.json")
    cal = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cal = json.load(f)
    bucket = confidence if confidence in ("高", "中", "低") else "未标"
    slot = cal.setdefault(bucket, {"resolved": 0, "accurate": 0})
    slot["resolved"] += 1
    if result == "accurate":
        slot["accurate"] += 1
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(cal, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)
    return bucket


SIDE_KWS = ("期货", "投机", "股票", "长线", "总盘", "总收益", "总账")
BAD_WORDS = ("受损", "劳而少获", "亏损", "亏")
GOOD_WORDS = ("正收益", "受益", "偏吉", "平稳", "盈")


def classify(rec):
    """pending 条目三分类：conditional / direction / assertion（与 auto_judge 口径同源）。"""
    pred = rec.get("prediction", "")
    if "若" in pred:
        return "conditional"
    for cl in re.split(r"[，。；,;.]", pred):
        sides = [k for k in SIDE_KWS if k in cl]
        bad = [w for w in BAD_WORDS if w in cl]
        good = [w for w in GOOD_WORDS if w in cl]
        if sides and (bad or good) and not (bad and good):
            return "direction"
    return "assertion"


def s1(log, person, month):
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_base.py"),
                    "--level", "liuyue", "--key", month, "--person", person])
    if rc == 0 and "BASE-OK" in text:
        log.log(1, "底座闸", "OK", text.strip().splitlines()[0])
    else:
        log.log(1, "底座闸", "FAIL",
                "当月流月底座缺失——先按 docs/pipeline_layers.md 跑流月产线：%s"
                % text.strip().splitlines()[0] if text.strip() else "无输出")


def s2(log, yesterday, results):
    sentry_py = os.path.join(SKILL_ROOT, "verify", "bin", "sentry_scan.py")
    returns_py = os.path.join(SKILL_ROOT, "verify", "bin", "read_returns.py")
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "check_pending.py"),
                    "--date", yesterday])
    if rc != 0:
        log.log(2, "check_pending", "FAIL", text.strip()[:300])
    items = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                items = json.loads(line)
            except ValueError:
                pass
    results["yesterday_items"] = items
    if os.path.isfile(returns_py):
        rc, text = run([returns_py, "--date", yesterday])
    else:
        rc, text = 0, ""
    returns_y = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                returns_y = json.loads(line)
            except ValueError:
                pass
    if not os.path.isfile(returns_py):
        log.log(2, "read_returns", "OK",
                "依赖件不存在，跳过（开源形态）——收益数据可用 --csv <路径> 参数经 returns_import 导入")
    results["returns_yesterday"] = returns_y
    if not os.path.isfile(sentry_py):
        log.log(2, "sentry_scan", "OK", "依赖件不存在，跳过（开源形态）")
        results["sentry_candidates"] = -1
        n_cand = -1
        log.log(2, "四闸采集", "OK",
                "昨日待验证 %d 条；收益 %s；哨兵候选 %s（开源形态：哨兵件不在包，断言句转人工）"
                % (len(results.get("yesterday_items", [])), returns_y.get("status") or "跳过", "不可用"))
        return
    rc, text = run([sentry_py, "--date", yesterday], py=VEC_PY)
    if rc != 0:
        log.log(2, "sentry_scan", "FAIL", text.strip()[:300])
    results["sentry_text"] = text
    n_cand = sentry_candidate_count(text)
    results["sentry_candidates"] = n_cand
    log.log(2, "四闸采集", "OK",
            "昨日待验证 %d 条；收益 %s；哨兵候选 %s"
            % (len(items), returns_y.get("status") or returns_y.get("date", "无"), n_cand))


def s3(log, person, yesterday, results):
    """日清机械判定。已 resolve 的条目不在 pending——重放自然零条目=幂等。"""
    recs = load_pending(yesterday)
    if not recs:
        log.log(3, "日清机械判定", "OK", "昨日队列零待验证（已日清或无出题）")
        return
    has_op = has_operation_record(person, yesterday)
    returns_y = results.get("returns_yesterday", {})
    has_data = returns_y.get("date") == yesterday and returns_y.get("total") not in (None, "", "no_data")
    n_cand = results.get("sentry_candidates", -1)
    done, need_data, manual = [], [], []
    for rec in recs:
        kind = classify(rec)
        pid = rec["pred_id"]
        if kind == "conditional":
            if not has_op and not str(returns_y.get("operation", "")).strip():
                rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "resolve_prediction.py"),
                                "--pred-id", pid, "--result", "untriggered",
                                "--no-capture",
                                "--detail", "%s 无操作记录，条件未触发（机械日清）" % yesterday])
                if rc != 0:
                    log.log(3, "日清机械判定", "FAIL", "resolve %s 失败：%s" % (pid, text.strip()[:200]))
                done.append("%s→untriggered" % pid)
            else:
                manual.append("%s（有操作记录，条件句按结果人工判定）" % pid)
        elif kind == "direction":
            if has_data:
                done.append("%s→auto_judge" % pid)
            else:
                need_data.append(pid)
        else:  # assertion
            if n_cand == 0 and not has_op:
                bucket = bump_calibration(rec.get("confidence", ""), "inaccurate")
                rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "resolve_prediction.py"),
                                "--pred-id", pid, "--result", "inaccurate",
                                "--no-capture",
                                "--detail", "%s 哨兵零候选+无口述记录，断言未兑现→不准（机械日清）" % yesterday])
                if rc != 0:
                    log.log(3, "日清机械判定", "FAIL", "resolve %s 失败：%s" % (pid, text.strip()[:200]))
                done.append("%s→inaccurate（%s档累档）" % (pid, bucket))
            else:
                manual.append("%s（哨兵有候选或歧义，待 agent 复核断言句）" % pid)
    if has_data and any(classify(r) == "direction" for r in recs):
        rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "auto_judge_returns.py"),
                        "--date", yesterday])
        if rc != 0:
            # auto_judge=可选预检参考（pipeline_layers 收益环节）：失败降 WARN，
            # 方向句判定正路=agent 人工判卷（完整 theory 四段 append）
            log.log(3, "日清机械判定", "WARN",
                    "auto_judge 预检失败（%s）——方向句转 agent 人工判卷" % text.strip().splitlines()[-1][:120])
    log.log(3, "日清机械判定", "OK",
            "销账 %d；待数据 %d；待人工 %d" % (len(done), len(need_data), len(manual))
            + ("；待数据：" + "、".join(need_data) if need_data else "")
            + ("；待人工：" + "；".join(manual) if manual else ""))
    results["need_data"] = need_data
    results["s3_manual"] = manual


def s4(log, person, today, results):
    report = os.path.join(PERSON_ROOT, person, "Liuri", "报告-%s.md" % today)
    results["report"] = report
    if os.path.isfile(report):
        log.log(4, "排盘", "OK", "报告已存在，跳过生成：%s" % report)
        return
    rc, text = run([os.path.join(SKILL_ROOT, "core", "liupan.py"),
                    "--pan", os.path.join(SKILL_ROOT, "pans", "%s.json" % person),
                    "--level", "liuri", "--date", today,
                    "--person", person, "--outdir"])
    if rc != 0:
        log.log(4, "排盘", "FAIL", text.strip()[:300])
    m = re.search(r"批次目录：(.+)", text)
    if not m:
        log.log(4, "排盘", "FAIL", "未解析到批次目录行：%s" % text.strip()[:200])
    results["batch"] = m.group(1).strip()
    log.log(4, "排盘", "OK", "批次目录：%s" % results["batch"])


def batch_of(person, today):
    return os.path.join(PERSON_ROOT, person, "Liuri", "temp", today)


def s5(log, person, today, results):
    batch = results.get("batch") or batch_of(person, today)
    results["batch"] = batch
    if not os.path.isdir(batch):
        log.log(5, "派发生成", "FAIL", "批次目录不存在：%s" % batch)
    script = os.path.join(batch, "dispatch_liupan.workflow.js")
    if os.path.isfile(script):
        log.log(5, "派发生成", "OK",
                "dispatch 脚本在位（待 agent 后台作业化执行，禁前台）：%s" % script)
    else:
        log.log(5, "派发生成", "FAIL", "缺 dispatch_liupan.workflow.js：%s" % script)


def s6(log, person, today, results, auto_refill=False):
    batch = results.get("batch") or batch_of(person, today)
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_outputs.py"),
                    "--dir", batch, "--no-shengong"])
    if rc == 0:
        log.log(6, "质检", "OK", "check_outputs PASS")
        return
    # FAIL→refill 生成补发脚本；保守=打印路径转人工，不自动跑 workflow
    rc2, text2 = run([os.path.join(SKILL_ROOT, "bin", "refill.py"), "--dir", batch])
    refill_scripts = sorted(glob.glob(os.path.join(batch, "refill_*.workflow.js")))
    msg = "check_outputs FAIL；refill 输出见日志；补发脚本：%s" % (
        "、".join(refill_scripts) if refill_scripts else "(未生成——看 refill.py 输出：" + text2.strip()[-200:] + ")")
    if auto_refill and refill_scripts:
        msg += "（--auto-refill 模式由 agent 显式启用后才可后台执行）"
    log.log(6, "质检", "FAIL", msg + "——转人工：后台执行补发脚本后重跑本步骤")


def s7(log, person, today, results):
    batch = results.get("batch") or batch_of(person, today)
    report = results.get("report") or os.path.join(
        PERSON_ROOT, person, "Liuri", "报告-%s.md" % today)
    if os.path.isfile(report):
        log.log(7, "组装", "OK", "报告已存在，跳过组装（重做=先删旧报告）：%s" % report)
        return
    head = os.path.join(batch, "head.md")
    cmd = [os.path.join(SKILL_ROOT, "bin", "assemble_report.py"),
           "--batch", batch, "--out", report]
    if os.path.isfile(head):
        cmd += ["--head", head]
    rc, text = run(cmd)
    if rc != 0:
        log.log(7, "组装", "FAIL", text.strip()[:300])
    log.log(7, "组装", "OK",
            "报告落盘：%s%s" % (report, "" if os.path.isfile(head) else "（无 head.md——agent 补写分析头后可重组装）"))


def s8(log, person, today, results):
    report = results.get("report") or os.path.join(
        PERSON_ROOT, person, "Liuri", "报告-%s.md" % today)
    brief = os.path.join(os.path.dirname(report), "报告-%s-简报.md" % today)
    results["brief"] = brief
    if os.path.isfile(brief):
        results["brief_preexisting"] = True
        log.log(8, "简报派单生成", "OK", "简报已存在，跳过派单生成：%s" % brief)
        return
    batch = results.get("batch") or batch_of(person, today)
    prompt_path = os.path.join(batch, "brief_prompt.md")
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "fill_brief_prompt.py"),
                    "--type", "liuri", "--person", person,
                    "--report", report, "--out", brief, "--save", prompt_path])
    if rc != 0:
        log.log(8, "简报派单生成", "FAIL", text.strip()[:300])
    log.log(8, "简报派单生成", "OK",
            "派单 prompt 落盘（待 agent 派发写简报）：%s" % prompt_path)


def s9(log, person, today, results):
    brief = results.get("brief") or os.path.join(
        PERSON_ROOT, person, "Liuri", "报告-%s-简报.md" % today)
    n = len(results.get("yesterday_items", []))
    if results.get("brief_preexisting"):
        log.log(9, "check_brief", "OK", "幂等重放：简报为既有产物（已过当日闸），跳过")
        return
    if not os.path.isfile(brief):
        log.log(9, "check_brief", "OK",
                "简报未写——待 agent 写完后跑：check_brief.py %s --type liuri --expect-tail %d"
                % (brief, n))
        return
    cmd = [os.path.join(SKILL_ROOT, "bin", "check_brief.py"),
           brief, "--type", "liuri", "--expect-tail", str(n)]
    closed = not _is_trading_day(datetime.datetime.strptime(today, "%Y-%m-%d").date())
    if closed:
        cmd.append("--closed-market")
    rc, text = run(cmd)
    if rc != 0:
        log.log(9, "check_brief", "FAIL", "（--expect-tail %d%s）%s"
                % (n, " --closed-market" if closed else "", text.strip()[:400]))
    log.log(9, "check_brief", "OK", "简报过闸（expect-tail=%d%s）"
            % (n, "，休市豁免节15" if closed else ""))


def s10(log, person, today, results):
    brief = results.get("brief") or os.path.join(
        PERSON_ROOT, person, "Liuri", "报告-%s-简报.md" % today)
    if not os.path.isfile(brief):
        log.log(10, "extract_predictions", "OK",
                "简报未写——待 agent 写简报后跑：extract_predictions.py --brief %s --person %s --date %s --layer liuri"
                % (brief, person, today))
        return
    # 幂等归 extract 逐条内容指纹（pending+resolved 双库查重）——此处不做数量级整跑闸
    # （旧版「当日已有 N 条在队，跳过」会把首跑漏提的条目永久挡在补录外，2026-11-21 实案废除）
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "extract_predictions.py"),
                    "--brief", brief, "--person", person, "--date", today, "--layer", "liuri"])
    if rc != 0:
        if "拒绝入队" in text and "Traceback" not in text and "unrecognized" not in text:
            log.log(10, "extract_predictions", "OK", text.strip().splitlines()[0] + "（含正常拒绝告知——拒绝始 rc=1 属 extract 设计）")
            return
        log.log(10, "extract_predictions", "FAIL", text.strip()[:300])
        return
    log.log(10, "extract_predictions", "OK", text.strip().splitlines()[-1] if text.strip() else "完成")


def s11(log, person, today, results):
    returns_py = os.path.join(SKILL_ROOT, "verify", "bin", "read_returns.py")
    auto_py = os.path.join(SKILL_ROOT, "verify", "bin", "auto_judge_returns.py")
    csv_path = results.get("csv")
    if not csv_path and not os.path.isfile(returns_py):
        log.log(11, "判定链", "OK",
                "read_returns 依赖件不存在，跳过（开源形态）——收益数据可用 --csv <路径> 参数（returns_import 对接）后重跑 --from-step 11")
        return
    latest = {}
    if not csv_path:
        rc, text = run([returns_py])
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    latest = json.loads(line)
                except ValueError:
                    pass
        if latest.get("status"):
            log.log(11, "判定链", "OK", "最新收益 %s（%s）——无判卷" % (latest.get("status"), latest.get("message", "")))
            return
    csv_args = ["--csv", csv_path] if csv_path else []
    rc, text = run([auto_py] + csv_args)
    if rc != 0:
        # auto_judge=可选预检参考；最新条目 F 列公式缓存为 None 时其 event_text 崩（预存局限）
        log.log(11, "判定链", "WARN",
                "auto_judge 预检失败（%s）——待 agent 人工判卷（完整 theory 四段 append）"
                % text.strip().splitlines()[-1][:120])
        return
    log.log(11, "判定链", "OK", "auto_judge 最新交易日（%s）：%s"
            % (latest.get("date"), text.strip().splitlines()[-1] if text.strip() else "无方向句"))


def s12(log, person, today, results):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "update_trading_ledger.py"),
                    "--date", today])
    if rc != 0:
        log.log(12, "台账日更", "FAIL", text.strip()[:300])
    log.log(12, "台账日更", "OK", text.strip().splitlines()[-1] if text.strip() else "完成")


def s13(log, person, today, yesterday, results):
    lines = [
        "①哨兵复核：s2 哨兵候选 %s 条——按 capture-guide「事件采集与复核」逐条复核后入库（s3 断言句判定依赖此复核，若复核结论非零事件须回补 resolve）"
        % results.get("sentry_candidates", "?"),
        "②派发执行：s5 dispatch_liupan.workflow.js 后台作业化执行（run_in_background），完成后从 s6 续跑 --from-step 6",
        "③分析头：s7 若无 head.md——读 12 宫结论补写批次 head.md 后重组装",
        "④简报写手：s8 派单 prompt 派发写简报；写完从 s9 续跑 --from-step 9",
        "⑤theory ④段：s3/s11 人工判定路径的条目须按判卷纪律写完整 theory 四段后 append 落账（禁机器简版占位）",
        "⑥简报呈现：会话内呈现简报要点+present 报告简报（不送达=未完成）",
    ]
    if results.get("need_data"):
        lines.insert(0, "⓿待数据：" + "、".join(results["need_data"]) + "——数据到达后重跑 --from-step 3")
    log.log(13, "输出汇总", "OK", "agent 人工点清单：\n  " + "\n  ".join(lines))
    print("\n═ agent 人工点清单 ═")
    for ln in lines:
        print("  " + ln)


def main():
    ap = argparse.ArgumentParser(description="定时任务全链一键化编排器（方案 v1.5 件4）")
    ap.add_argument("--person", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="YYYY-MM-DD，缺省今天")
    ap.add_argument("--from-step", dest="from_step", type=int, default=1, help="断点续跑起始步骤（1-13）")
    ap.add_argument("--auto-refill", dest="auto_refill", action="store_true",
                    help="s6 质检 FAIL 时仍生成补发脚本（缺省保守：仅打印转人工，不自动执行）")
    ap.add_argument("--root", default=None,
                    help="命主工作区根（缺省=SKILL_ROOT 同级 ziwei-workspace/，不存在则建样例结构）")
    ap.add_argument("--csv", default=None,
                    help="收益数据 CSV 路径（returns_import 对接，s11 判定链透传给 read_returns/auto_judge）")
    args = ap.parse_args()
    global PERSON_ROOT
    PERSON_ROOT = resolve_person_root(args.root)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        print("错误：--date 须为 YYYY-MM-DD")
        sys.exit(2)
    today = args.date
    d = datetime.date.fromisoformat(today)
    yesterday = (d - datetime.timedelta(days=1)).isoformat()
    results = {"csv": args.csv} if args.csv else {}
    log = Logger(today)
    steps = [
        lambda: s1(log, args.person, today[:7]),
        lambda: s2(log, yesterday, results),
        lambda: s3(log, args.person, yesterday, results),
        lambda: s4(log, args.person, today, results),
        lambda: s5(log, args.person, today, results),
        lambda: s6(log, args.person, today, results, auto_refill=args.auto_refill),
        lambda: s7(log, args.person, today, results),
        lambda: s8(log, args.person, today, results),
        lambda: (_ensure_calendar_fresh(log, today), s9(log, args.person, today, results)),
        lambda: s10(log, args.person, today, results),
        lambda: s11(log, args.person, today, results),
        lambda: s12(log, args.person, today, results),
        lambda: s13(log, args.person, today, yesterday, results),
    ]
    print("═ ziwei_daily %s（%s；from-step=%d；日志=%s）═" % (today, args.person, args.from_step, log.path))
    try:
        for i, fn in enumerate(steps, 1):
            if i < args.from_step:
                continue
            fn()
    except StepFail as e:
        print("\nFAIL：%s" % e)
        sys.exit(1)
    print("\n全链完成（13 步）——日志：%s" % log.path)


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
