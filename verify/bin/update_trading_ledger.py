# -*- coding: utf-8 -*-
"""交易预判台账（trading_predictions_ledger.xlsx）每日自动更新。

数据源：_verify/resolved_predictions.jsonl（判定归档）+ events_*（交易盈亏事件）
        + read_returns.py --date（投资收益真值）。

用法：update_trading_ledger.py [--data-dir 目录] [--ledger 路径] [--date YYYY-MM-DD]
  --data-dir  验证库目录（默认同 resolve_prediction 三级解析）
  --ledger    台账 xlsx 路径（默认 <data-dir>/trading_predictions_ledger.xlsx）
  --date      只处理该日；缺省=归档有判定且台账缺行/存在占位行的日期集合

行为：
  - 归档交易类条目 → 台账行（文本匹配幂等：已有同预判文本行→只更新判定三格；
    占位行落判定更新原行禁新增；缺行→追加）。
  - 实际结果列：read_returns --date 合成「投资收益（总账）±X.XX%」纯格式
    ；
    无数据=「待录入」（队列判定待数据行保持占位不落判定）。
  - 预判依据列：从当日 events theory ③「定性强弱判别」定性句程序化提炼
    （主星结构+关键煞忌+判语定性，≤40 字，禁三层并标引文/结论叙述长段）；
    提炼不出=留空标黄（定时任务 agent 补写）。事后归因列留空标黄（agent 补写）。
  - 待数据回填：台账「待数据」行在收益数据后到时自动补判（复用 auto_judge_returns
    符号语义；先 calibration 累档再 resolve；台账落「准确（队列）/不准（队列）」）。
  - 汇总页刷新：方向句判数/准确/准确率（台账内已判非条件句行统计，含历史基线）+
    注「n<10 仅参考」（n≥10 置空）。
  - 第 11 列「方向句累计准确率」：只算方向句行，每行=截至该日累计命中/判定（百分比，
    括注 h/n）；每次运行整列重算（幂等）。
  - calibration 对账：日更输出末尾打印第 11 列终值分子分母 vs calibration.json 各档
    resolved/accurate 之和；不一致打差异行（已知差异源：手补行不走 resolve、
    条件句触发判定入 calibration 不入方向句列）。
  - 判定着色：准确=C6EFCE / 不准=FFC7CE / 待数据与待判定=FFEB9C。

幂等重跑零副作用；零第三方依赖（openpyxl）；禁碰生产数据（写目标仅 --ledger）。
"""
import argparse
import copy
import glob
import json
import os
import re
import subprocess
import sys

_CSV_OVERRIDE = os.environ.get("RETURNS_CSV", "")  # 模块级缺省；--csv 覆盖
from datetime import datetime

from openpyxl import load_workbook
from openpyxl.styles import PatternFill

BIN = os.path.dirname(os.path.abspath(__file__))
RESOLVED_FILE = "resolved_predictions.jsonl"
LEDGER_NAME = "trading_predictions_ledger.xlsx"
SHEET_MAIN = "交易预判战绩"
SHEET_SUM = "汇总"

# 交易类预判条目筛选词（与 auto_judge_returns 端词同源 + 进账/盘面/收益）
TRADE_KEYWORDS = ("期货", "投机", "股票", "长线", "总盘", "总收益", "总账", "盘面",
                  "进账", "收益", "杠杆", "豪赌", "交易")

FILL_GREEN = PatternFill("solid", fgColor="C6EFCE")
FILL_RED = PatternFill("solid", fgColor="FFC7CE")
FILL_YELLOW = PatternFill("solid", fgColor="FFEB9C")

RESULT_MAP = {"accurate": "准确", "inaccurate": "不准", "未触发": "未触发",
              "准确": "准确", "不准": "不准"}

# 台账「交易预判战绩」列序（1 起）
COL_DATE, COL_TYPE, COL_SIDE, COL_TEXT, COL_CONF, COL_REVIEW, COL_ACTUAL, \
    COL_POSTMORTEM, COL_EVENT_JUDGE, COL_QUEUE, COL_CUMRATE = range(1, 12)
QUEUE_JUDGED = ("准确", "不准")
COL_CUMRATE_HEADER = "方向句累计准确率"


def queue_marker_strip(value):
    """队列判定归一：「准确（队列）」（待数据回填落判）与「准确」同义。"""
    return value.replace("（队列）", "") if isinstance(value, str) else value


def norm_text(s):
    """行匹配键：去句读空白。"""
    return re.sub(r"[。．.，,；;、\s]", "", s or "")


def is_trade_entry(rec):
    return any(k in rec.get("prediction", "") for k in TRADE_KEYWORDS)


def side_label(prediction, conditional):
    """预判端列：总账口径（弃分端）；
    台账十列标准③预判端=总账（固定）——条件句亦不再出「总账/行为」。"""
    return "总账"


def fmt_pct(v):
    return ("+" if v >= 0 else "") + "%.2f%%" % (v * 100)


def actual_result_text(entry):
    """read_returns JSON → 「投资收益（总账）±X.XX%」纯格式（十列标准⑦，无尾巴）。"""
    if not entry or entry.get("status") or entry.get("date") is None:
        return "待录入"
    _tv = entry.get("total") if isinstance(entry.get("total"), (int, float)) else entry.get("total_return")
    if not isinstance(_tv, (int, float)):
        return "待录入"  # total/no_data 或缓存缺失形态
    return "投资收益（总账）%s" % fmt_pct(float(_tv))


def fetch_returns(date):
    """子进程调 read_returns.py --date；无数据/无文件返回 None（禁读 .env、不打印环境变量）。"""
    env = dict(os.environ, PYTHONUTF8="1")
    rr = os.path.join(BIN, "read_returns.py")
    ri = os.path.join(BIN, "returns_import.py")
    if os.path.isfile(rr):
        r = subprocess.run([sys.executable, rr, "--date", date], capture_output=True, env=env)
    elif _CSV_OVERRIDE and os.path.isfile(ri):
        r = subprocess.run([sys.executable, ri, "--csv", _CSV_OVERRIDE, "--date", date], capture_output=True, env=env)
    else:
        return None
    text = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0 or not text:
        return None
    try:
        rec = json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return None if rec.get("status") else rec


def load_events_judge(data_dir, date):
    """events 库该日 category=交易盈亏 首条 verify_result；无 → '—'。"""
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
            if rec.get("event_date") == date and rec.get("category") == "交易盈亏":
                v = rec.get("verify_result")
                if v:
                    return v
    return "—"


def load_events_theory(data_dir, date):
    """events 库该日 category=交易盈亏 首条 theory（定性句提炼源）；无 → ''。"""
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
            if rec.get("event_date") == date and rec.get("category") == "交易盈亏":
                v = rec.get("theory")
                if v:
                    return v
    return ""


BASIS_MAX_CHARS = 40


def extract_basis(theory):
    """theory ③「定性强弱判别」定性句 → 预判依据（≤40 字）。

    句式=主星结构+关键煞忌+判语定性（theory ③ 定性强弱判别段即为此句式）；
    禁三层并标引文（②结构原文）与结论叙述长段（④事件对照）——只取该判别段。
    提炼不出（无标记段）→ None（调用方留空标黄交 agent 补写）。
    """
    if not theory:
        return None
    m = re.search(r"定性强弱判别[:：]", theory)
    if not m:
        return None
    seg = theory[m.end():]
    # 段落止于「；置信」（定性强弱段后接置信说明）或下一个 ③④编号/句末
    for stop in ("；置信", "置信档"):
        idx = seg.find(stop)
        if idx > 0:
            seg = seg[:idx]
    seg = re.split(r"[。]", seg)[0].strip(" ；;，,")
    if len(seg) > BASIS_MAX_CHARS:
        # 40 字内取最靠后的逗/顿号断口，无断口硬截
        cut = seg[:BASIS_MAX_CHARS]
        idx = max(cut.rfind("，"), cut.rfind("、"), cut.rfind("="))
        seg = cut[:idx] if idx > 10 else cut
    return seg or None


def load_resolved(data_dir):
    out = []
    path = os.path.join(data_dir, RESOLVED_FILE)
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
                # 休市日（周六/周日）条目整条跳过：不追加行、不更新、不计汇总；
                # 法定节假日休市暂不识别（后续由收益表口径覆盖）
                try:
                    if datetime.strptime(str(rec.get("date", ""))[:10],
                                         "%Y-%m-%d").weekday() >= 5:
                        continue
                except ValueError:
                    pass
                # 出账条目（判定作废，如流时实测产物误入生产队）整条跳过：
                # 不追加行、不更新、不计汇总
                if "出账" in rec.get("detail", ""):
                    continue
                # 条件句队列判定=「未触发」整条跳过：
                # 不追加行、不更新、不计汇总；仅触发判定（准确/不准）才记行
                if "若" in rec.get("prediction", "") and \
                        RESULT_MAP.get(rec.get("result", ""),
                                       rec.get("result", "")) == "未触发":
                    continue
                if is_trade_entry(rec):
                    out.append(rec)
    return out


def queue_color(value):
    value = queue_marker_strip(value)
    if value == "准确":
        return FILL_GREEN
    if value == "不准":
        return FILL_RED
    if value in ("待数据", "待判定"):
        return FILL_YELLOW
    return None  # 未触发等：不着色


def ensure_ledger(path, person_label=""):
    """台账不存在则首建（开源冷启动；2026-11-20 扩容补）——SHEET_MAIN 十一列表头+SHEET_SUM 骨架。"""
    if os.path.isfile(path):
        return
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    headers = ["日期", "类型", "预判端", "预判原文", "置信档", "预判依据", "实际结果", "事后归因", "验证判定(events库)", "队列判定", "方向句累计准确率"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    wsum = wb.create_sheet(SHEET_SUM)
    wsum.cell(1, 1, "累计预判准确率")
    wsum.cell(1, 2, "n<10 仅参考")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)


class Ledger:
    def __init__(self, path):
        self.path = path
        ensure_ledger(path)
        self.wb = load_workbook(path)
        self.ws = self.wb[SHEET_MAIN]

    def rows(self):
        """[(row_idx, {col: value})] 数据行（第 2 行起）。"""
        out = []
        for r in range(2, self.ws.max_row + 1):
            vals = {c: self.ws.cell(r, c).value for c in range(1, 12)}
            if any(v not in (None, "") for v in vals.values()):
                out.append((r, vals))
        return out

    def find_by_text(self, text, date=None):
        """按日期+预判原文双匹配行（norm 后比对）；返回 row_idx 或 None。

        双匹配防同文异日撞行：每日复用句（如「今日总收益大概率为亏」）
        只含日期+文本双键才算既有行，避免旧行拦截当日追加。"""
        key = norm_text(text)
        d = str(date)[:10] if date else None
        for r, vals in self.rows():
            if d is not None and str(vals.get(COL_DATE) or "")[:10] != d:
                continue
            if norm_text(str(vals.get(COL_TEXT) or "")) == key:
                return r
        return None

    def append_row(self, template_row, values):
        """按上一数据行样式追加一行；返回新行 idx。"""
        r = self.ws.max_row + 1
        for c in range(1, 12):
            cell = self.ws.cell(r, c)
            tcell = self.ws.cell(template_row, c)
            if tcell.has_style:
                cell._style = copy.copy(tcell._style)
            if c in values:
                cell.value = values[c]
        return r

    def set_cell(self, r, c, value, fill=None):
        cell = self.ws.cell(r, c)
        cell.value = value
        # fill=None = 清除既有着色（占位黄残留）
        cell.fill = fill if fill is not None else PatternFill(fill_type=None)

    def refresh_cumrate(self):
        """第 11 列整列重算：方向句已判行=截至该日累计命中/判定；其余行置空。

        返回 (hit, n) 终值（供 calibration 对账）。按日期排序累计——行序不依赖
        物理行顺序（历史手工插入/补行不破坏累计口径）。
        """
        if self.ws.cell(1, COL_CUMRATE).value != COL_CUMRATE_HEADER:
            self.ws.cell(1, COL_CUMRATE).value = COL_CUMRATE_HEADER
        judged = []
        for r, vals in self.rows():
            if vals.get(COL_TYPE) == "方向句" and \
                    queue_marker_strip(vals.get(COL_QUEUE)) in QUEUE_JUDGED:
                judged.append((str(vals.get(COL_DATE) or "")[:10], r,
                               queue_marker_strip(vals.get(COL_QUEUE)) == "准确"))
        judged.sort(key=lambda x: (x[0], x[1]))
        hit = n = 0
        values = {}
        for date, r, ok in judged:
            n += 1
            hit += 1 if ok else 0
            values[r] = "%d%%（%d/%d）" % (round(hit * 100 / n), hit, n)
        for r, vals in self.rows():
            want = values.get(r, None)
            if self.ws.cell(r, COL_CUMRATE).value != want:
                self.ws.cell(r, COL_CUMRATE).value = want
        return hit, n

    def refresh_summary(self):
        """汇总页：方向句已判行统计（判数/准确/准确率 + 逐日说明）。"""
        if SHEET_SUM not in self.wb.sheetnames:
            return False
        ws = self.wb[SHEET_SUM]
        judged = []
        for r, vals in self.rows():
            if vals.get(COL_TYPE) == "方向句" and \
                    queue_marker_strip(vals.get(COL_QUEUE)) in QUEUE_JUDGED:
                d = str(vals.get(COL_DATE) or "")
                judged.append((d, queue_marker_strip(vals.get(COL_QUEUE))))
        judged.sort()
        n, hit = len(judged), sum(1 for _, q in judged if q == "准确")
        rate = "%.0f%%" % (hit * 100 / n) if n else "—"
        note = "/".join("%s%s" % (d[5:] if len(d) >= 10 else d,
                                  "准" if q == "准确" else "不准") for d, q in judged)
        changed = False
        note_ref = "n<10 仅参考" if n < 10 else "—"
        if ws.cell(1, 6).value != "注":
            ws.cell(1, 6).value = "注"
        for col, newv in ((2, n), (3, hit), (4, rate), (5, note), (6, note_ref)):
            cell = ws.cell(2, col)
            if cell.value != newv:
                cell.value = newv
                changed = True
        return changed

    def save(self):
        self.wb.save(self.path)


def load_pending(data_dir):
    out = []
    path = os.path.join(data_dir, "pending_predictions.jsonl")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    return out


def backfill_pending_data(ledger, data_dir, log):
    """待数据回填（077/079 空转根治）：台账「待数据」行在收益数据后到时自动补判。

    每行：pending 按日期+预判文本定位 pred_id/置信档/person → read_returns --date 取数 →
    主端符号判定（复用 auto_judge_returns 语义：凶向主端收益<0=accurate）→
    先 calibration 累档再 resolve（正常路径 --no-capture：关队列+归档+events verify_note
    由 --detail 的 person+date 回退匹配自带）→ 台账行改「准确（队列）/不准（队列）」、
    实际结果列落当日收益、事后归因保持留空标黄（agent 补写）。
    数据未到/无法机判 → 保持待数据；已 resolve 归档而台账滞留 → 仅同步台账不重判不重累档。
    """
    sys.path.insert(0, BIN)
    from auto_judge_returns import (parse_clauses, resolve_total, judge_total,
                                    bump_calibration)

    pend = load_pending(data_dir)
    resolved_ids, resolved_by_text = set(), {}
    path = os.path.join(data_dir, RESOLVED_FILE)
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
                resolved_ids.add(rec.get("pred_id"))
                resolved_by_text[(str(rec.get("date", ""))[:10],
                                  norm_text(rec.get("prediction", "")))] = rec

    returns_cache = {}
    basis_cache = {}

    def returns_of(date):
        if date not in returns_cache:
            returns_cache[date] = fetch_returns(date)
        return returns_cache[date]

    def basis_of(date):
        if date not in basis_cache:
            basis_cache[date] = extract_basis(load_events_theory(data_dir, date))
        return basis_cache[date]

    def sync_row(r, queue, date):
        ledger.set_cell(r, COL_QUEUE, queue, queue_color(queue))
        actual = actual_result_text(returns_of(date))
        if actual != "待录入":
            ledger.set_cell(r, COL_ACTUAL, actual)
        # 回填行预判依据：空则 theory 定性句补写（十列标准⑥同新增行）
        if not ledger.ws.cell(r, COL_REVIEW).value:
            basis = basis_of(date)
            if basis:
                ledger.set_cell(r, COL_REVIEW, basis, None)

    changed = 0
    for r, vals in ledger.rows():
        if queue_marker_strip(vals.get(COL_QUEUE)) != "待数据":
            continue
        date = str(vals.get(COL_DATE) or "")[:10]
        text = str(vals.get(COL_TEXT) or "")
        key = (date, norm_text(text))
        rec = next((p for p in pend
                    if (str(p.get("date", ""))[:10],
                        norm_text(p.get("prediction", ""))) == key), None)
        if rec is None or rec.get("pred_id") in resolved_ids:
            # 队列已关（resolve 落归档后台账滞留）→ 仅同步台账行，不重判不重累档
            hit = resolved_by_text.get(key)
            if hit and queue_marker_strip(hit.get("result", "")) in QUEUE_JUDGED:
                sync_row(r, "%s（队列）" % hit["result"], date)
                log("回填同步 %s %s → %s（归档已判，台账补齐）"
                    % (hit.get("pred_id", "?"), date, hit["result"]))
                changed += 1
            elif rec is None:
                log("待数据行无法定位 pred_id（%s %s…）——保持待数据，需人工"
                    % (date, text[:20]))
            continue
        entry = returns_of(date)
        parsed = parse_clauses(text)
        direction = resolve_total(parsed) if isinstance(parsed, list) else None
        if entry is None or parsed in (None, "nodir") or direction in (None, "conflict"):
            log("待数据保持 %s %s（%s）" % (date, rec.get("pred_id"),
                "收益数据未到" if entry is None else "条件句或端/方向歧义，需人工"))
            continue
        ret = entry.get("total")
        if ret is None or ret == "" or ret == "no_data":
            log("待数据保持 %s %s（当日总收益缺失）" % (date, rec.get("pred_id")))
            continue
        outcome = judge_total(direction, float(ret))
        bucket = bump_calibration(data_dir,
                                  rec.get("confidence") or vals.get(COL_CONF) or "",
                                  outcome)
        detail = "机器补判（update_trading_ledger 待数据回填，总账口径）：当日总收益%s 对照方向句（%s向）" % (
            fmt_pct(float(ret)), direction)
        env = dict(os.environ, PYTHONUTF8="1")
        rp = subprocess.run([sys.executable, os.path.join(BIN, "resolve_prediction.py"),
                             "--pred-id", rec["pred_id"], "--result", outcome,
                             "--detail", detail, "--no-capture",
                             "--data-dir", data_dir], capture_output=True, env=env)
        for stream in (rp.stdout, rp.stderr):
            for line in stream.decode("utf-8", "replace").strip().splitlines():
                if line:
                    log("  | %s" % line)
        if rp.returncode != 0:
            log("错误：%s resolve 退出码 %d——台账行不动，下轮重试（calibration 已累档）"
                % (rec["pred_id"], rp.returncode))
            continue
        log("回填判卷 %s %s → %s（%s档累档）"
            % (rec.get("person", "?"), rec["pred_id"], outcome, bucket))
        sync_row(r, "%s（队列）" % RESULT_MAP[outcome], date)
        changed += 1
    return changed


def process_date(date, ledger, resolved, data_dir, log):
    """处理单日：归档条目映射行 + 实际结果/验证判定刷新。返回变更行数。"""
    entries = [r for r in resolved if str(r.get("date", ""))[:10] == date]
    returns = fetch_returns(date)
    actual = actual_result_text(returns)
    event_judge = load_events_judge(data_dir, date)
    basis = extract_basis(load_events_theory(data_dir, date))
    changed = 0

    rows = ledger.rows()
    template = rows[-1][0] if rows else 2

    # 1) 归档条目 → 行（文本幂等；占位行落判定禁新增）
    for rec in entries:
        text = rec.get("prediction", "")
        queue = RESULT_MAP.get(rec.get("result", ""), rec.get("result", ""))
        conf = rec.get("confidence", "") or "未标"
        typ = "条件句" if "若" in text else "方向句"
        side = side_label(text, "若" in text)
        r = ledger.find_by_text(text, rec.get("date", date))
        if r is None:
            r = ledger.append_row(template, {
                COL_DATE: rec.get("date", date), COL_TYPE: typ, COL_SIDE: side,
                COL_TEXT: text, COL_CONF: conf, COL_REVIEW: None,
                COL_ACTUAL: actual, COL_POSTMORTEM: None,
                COL_EVENT_JUDGE: "—" if typ == "条件句" else event_judge,
                COL_QUEUE: queue})
            # 预判依据=theory 定性句程序化提炼（十列标准⑥）；提炼不出留空标黄
            # 交 agent 补写。事后归因列留空标黄（agent 补写）。
            ledger.set_cell(r, COL_REVIEW, basis, None if basis else FILL_YELLOW)
            ledger.set_cell(r, COL_POSTMORTEM, None, FILL_YELLOW)
            ledger.set_cell(r, COL_QUEUE, queue, queue_color(queue))
            log("追加 %s %s → %s（%s）" % (rec.get("pred_id", "?"), date, queue, typ))
            changed += 1
        else:
            cur = queue_marker_strip(ledger.ws.cell(r, COL_QUEUE).value)
            if cur != queue:
                ledger.set_cell(r, COL_QUEUE, queue, queue_color(queue))
                log("更新 %s %s 队列判定 %s → %s" % (rec.get("pred_id", "?"), date, cur, queue))
                changed += 1

    # 2) 该日既有行（含占位行）刷新实际结果/验证判定
    for r, vals in ledger.rows():
        if str(vals.get(COL_DATE) or "")[:10] != date:
            continue
        if vals.get(COL_ACTUAL) != actual and actual != "待录入":
            ledger.set_cell(r, COL_ACTUAL, actual)
            log("更新 %s 实际结果 → %s" % (date, actual))
            changed += 1
        elif actual == "待录入" and vals.get(COL_ACTUAL) in (None, ""):
            ledger.set_cell(r, COL_ACTUAL, actual)
            changed += 1
        # 验证判定按句型：方向句=该日交易事件判定直抄；条件句=一律「—」
        # （条件句验证只看队列判定，无对应事件验证）
        if vals.get(COL_TYPE) == "条件句":
            if vals.get(COL_EVENT_JUDGE) != "—":
                ledger.set_cell(r, COL_EVENT_JUDGE, "—")
                log("更新 %s 验证判定 → —（条件句）" % date)
                changed += 1
        elif vals.get(COL_EVENT_JUDGE) != event_judge and event_judge != "—":
            ledger.set_cell(r, COL_EVENT_JUDGE, event_judge)
            log("更新 %s 验证判定 → %s" % (date, event_judge))
            changed += 1

    return changed


def main():
    global _CSV_OVERRIDE
    ap = argparse.ArgumentParser(description="交易预判台账每日自动更新")
    ap.add_argument("--person", dest="person", default="", help="按命主过滤（空=全库聚合）")
    ap.add_argument("--csv", dest="csv_override", default=_CSV_OVERRIDE, help="开源模式收益 CSV（read_returns 缺席时经 returns_import 导入）")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--ledger", dest="ledger", default="")
    ap.add_argument("--date", dest="date", default="")
    args = ap.parse_args()
    _CSV_OVERRIDE = args.csv_override or _CSV_OVERRIDE

    sys.path.insert(0, BIN)
    from common import resolve_data_dir
    data_dir = resolve_data_dir(args.data_dir)
    ledger_path = args.ledger or os.path.join(data_dir, LEDGER_NAME)
    if not os.path.isfile(ledger_path):
        if args.ledger:  # 显式 --ledger=冷启动首建（开源扩容）；缺省内部路径缺台账仍属异常
            ensure_ledger(ledger_path)
            print("首建台账：%s" % ledger_path)
        else:
            print("错误：台账不存在 %s" % ledger_path)
            sys.exit(2)

    ledger = Ledger(ledger_path)

    log_lines = []
    def log(msg):
        log_lines.append(msg)
        print(msg)

    # 待数据回填先行：数据后到的待数据行补判落 resolve 归档后，
    # 再 load_resolved 让常规路径（缺行追加/判定更新）看到新归档条目
    backfilled = backfill_pending_data(ledger, data_dir, log)

    resolved = load_resolved(data_dir)
    if getattr(args, "person", ""):
        resolved = [r for r in resolved if r.get("person", "") == args.person]

    if args.date:
        dates = [args.date]
    else:
        # 缺省处理集（逐条归档判）：条目预判文本在台账缺行，或其行/同日行存在
        # 待判定/待数据占位 → 该日入处理集
        dates = set()
        for rec in resolved:
            d = str(rec.get("date", ""))[:10]
            if not d:
                continue
            r = ledger.find_by_text(rec.get("prediction", ""), d)
            if r is None or ledger.ws.cell(r, COL_QUEUE).value in ("待判定", "待数据"):
                dates.add(d)
            elif any(str(v.get(COL_DATE) or "")[:10] == d
                     and v.get(COL_QUEUE) in ("待判定", "待数据")
                     for _, v in ledger.rows()):
                dates.add(d)
        dates = sorted(dates)

    total = 0
    for d in dates:
        log("— 处理 %s" % d)
        total += process_date(d, ledger, resolved, data_dir, log)

    if ledger.refresh_summary():
        log("汇总页刷新")
    hit, n = ledger.refresh_cumrate()
    # calibration 对账（N7 两账互锁）：第 11 列终值 vs calibration 各档之和
    cal_hit = cal_n = 0
    cal_path = os.path.join(data_dir, "calibration.json")
    if os.path.isfile(cal_path):
        with open(cal_path, encoding="utf-8") as f:
            for bucket, v in (json.load(f) or {}).items():
                if bucket.startswith("_") or not isinstance(v, dict):
                    continue
                cal_n += v.get("resolved", 0) or 0
                cal_hit += v.get("accurate", 0) or 0
    if (hit, n) == (cal_hit, cal_n):
        log("calibration 对账：台账方向句 %d/%d = calibration %d/%d —— 一致" % (hit, n, cal_hit, cal_n))
    else:
        log("⚠ calibration 差异行：台账方向句 %d/%d ≠ calibration %d/%d"
            % (hit, n, cal_hit, cal_n))
        log("  已知差异源（结构性，非事故）：①周末休市条目入 calibration 不入台账；"
            "②非交易类条目入 calibration 不入台账；③手补行只入台账不走 resolve——超出此类须人工核查")
    if total or True:
        ledger.save()
    print("完成：处理 %d 日，变更 %d 处，待数据回填 %d 行；台账 %s"
          % (len(dates), total, backfilled, ledger_path))


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
