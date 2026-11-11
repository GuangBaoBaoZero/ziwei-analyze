#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""简报派单 prompt 生成器（ziwei 简报产线）。

功能：层类型+命主+报告路径+简报输出路径 → 读 brief_prompt_template.md 做变量替换 → 输出完整可派发 prompt。
单一真源：层类型参数（节名/区间/侧重点）不复制进脚本，运行时解析模板「层类型参数对照」markdown 表格——
模板升版脚本自动跟随，零双源漂移。模板本体只读不改。

用法：
  python fill_brief_prompt.py --type liuri --person <命主名> ^
    --report "...\Liuri\报告-2026-10-27.md" --out "...\简报-2026-10-27.md" [--save 派单.md]
参数：
  --type   yuanju|daxian|liunian|liuyue|liuri|liushi 必填
  --person 命主名 必填
  --report 报告路径 必填
  --out    简报输出路径 必填
  --label  标题括注（如 "第4限"/"2026年"/"2026-10"/"2026-10-27"）；缺省从 --report 文件名提取，提取失败报错
  --save   直写文件（UTF-8 无 BOM）；缺省 stdout
铁律：未识别变量 fail-fast 报错列出（禁静默漏填）；label 缺失禁空标题。
零第三方依赖；PYTHONUTF8=1 兼容。
"""
import argparse
import datetime
import json
import os
import re
import sys

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(BIN_DIR)
TEMPLATE = os.path.join(SKILL_ROOT, "docs", "brief_prompt_template.md")

sys.path.insert(0, os.path.join(BIN_DIR, "..", "verify", "bin"))
from common import list_shards, read_lines, resolve_data_dir, find_anchors_zero_root  # noqa: E402  # EXPIRE_DAYS 已不用（尾节渲染上一同层批次）

PENDING_FILE = "pending_predictions.jsonl"
TAIL_TITLE = "待验预测"  # 标题不带计数（check_brief 纯计数校验）；尾节渲染上一同层批次，空态常驻
TAIL_EMPTY = "上一批次无待验预测。"  # 尾节空态句（六层常驻）
EVENTS_EMPTY = "本日无新增入册。"  # 近期事件节空态句（六层统一措辞）
SCENARIO_TOP_K = 4  # 高频场景卡取 top 类目数（行为画像）
LEVEL_CN = {"liuri": "流日", "liuyue": "流月", "liunian": "流年", "liushi": "流时"}
# 判定标准前置：预测行要求段追加句——锚点=模板预测行要求段唯一标记，
# 缺锚点 fail-fast（模板升版改结构时禁静默丢失要求）。模板本体只读不改，插入在脚本侧完成。
CRITERIA_REQ = "每条预测句后紧随判定标准（怎样算命中/怎样算不中，可判零裁量）"
CRITERIA_ANCHOR = "纯标记"

# 表格列名 → 模板变量名（单一真源=模板「层类型参数对照」表）
COLUMN_VARS = {
    "层": "层名",
    "简报标题": "简报标题",
    "宜忌节名": "宜忌节名",
    "经典节名": "经典节名",
    "典故节名": "典故节名",
    "侧重点": "层侧重点",
    "综述": "层综述区间",
    "每宫": "层每宫区间",
    "总字数": "层总字数区间",
}
LABEL_TYPES = ("daxian", "liunian", "liuyue", "liuri", "liushi")
LABEL_PATTERNS = {
    "daxian": re.compile(r"^第.{1,3}限$"),
    "liunian": re.compile(r"^\d{4}$"),
    "liuyue": re.compile(r"^\d{4}-\d{2}$"),
    "liuri": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "liushi": re.compile(r"^\d{4}-\d{2}-\d{2}-(子|丑|寅|卯|辰|巳|午|未|申|酉|戌|亥)$"),
}


def load_template():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def strip_doc_title(text):
    """剥模板首行文档标题（含 '{{}}' 字样，属模板自述非 prompt 内容）。"""
    lines = text.split("\n")
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)


def parse_layer_table(text):
    """解析「层类型参数对照」markdown 表 → {type: {变量: 值}}。"""
    rows = {}
    in_table = False
    header = None
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not in_table:
                in_table = True
                header = cells
                continue
            if set(s.replace("|", "").strip()) <= set("-: "):
                continue  # 分隔行
            rec = dict(zip(header, cells))
            t = rec.get("--type")
            if t:
                rows[t] = rec
        else:
            in_table = False
    if not rows:
        sys.stderr.write("模板「层类型参数对照」表解析失败（零行）——模板可能已升版改结构。\n")
        sys.exit(2)
    return rows


def extract_label(layer_type, report_path):
    """从报告文件名提取 label（四层规则各不同）；yuanju 无 label。"""
    stem = os.path.splitext(os.path.basename(report_path))[0]
    if stem == "报告":
        return None
    if not stem.startswith("报告-"):
        return None
    suffix = stem[len("报告-"):]
    if layer_type == "daxian" and LABEL_PATTERNS["daxian"].match(suffix):
        return suffix
    if layer_type == "liunian" and LABEL_PATTERNS["liunian"].match(suffix):
        return suffix + "年"
    if layer_type == "liuyue" and LABEL_PATTERNS["liuyue"].match(suffix):
        return suffix
    if layer_type == "liuri" and LABEL_PATTERNS["liuri"].match(suffix):
        return suffix
    if layer_type == "liushi" and LABEL_PATTERNS["liushi"].match(suffix):
        return suffix + "时"  # 2026-11-04-午 → 2026-11-04-午时（对齐 liunian suffix+"年" 后缀惯例）
    return None


def build_title(layer_type, table_title, label):
    m = re.match(r"^(.*?)（.*?）$", table_title)
    base = m.group(1) if m else table_title
    if layer_type == "yuanju":
        return table_title  # 人生简报，无括注
    if not label:
        return None
    return "%s（%s）" % (base, label)


def expand_conditionals(text, layer_type):
    """{{#if <type>}}...{{/if}}：匹配保留、不匹配删除（支持同行内联块）。
    条件支持竖线多值（如 liuri|liushi=两层同生效）。"""
    def repl(m):
        return m.group(2) if layer_type in m.group(1).split("|") else ""
    return re.sub(r"\{\{#if\s+([\w|]+)\}\}(.*?)\{\{/if\}\}", repl, text, flags=re.S)


LIUSHI_BRANCHES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


def liushi_prev_label(now=None):
    """上一时支批次标签 YYYY-MM-DD-时支：取当前时刻减 2 小时，按其所在时辰定支
    （时辰界=奇数小时，23:00 起子时；-2h 落在上一时辰窗口内，跨日/跨子时自然正确）。"""
    t = now or datetime.datetime.now()
    prev = t - datetime.timedelta(hours=2)
    branch = LIUSHI_BRANCHES[((prev.hour + 1) // 2) % 12]
    return "%s-%s" % (prev.strftime("%Y-%m-%d"), branch)


def prev_batch_match(layer_type, rec_date, label):
    """六层「上一同层批次」判定：
    liuri=昨日；liushi=上一时支批次；liuyue=上月（date 取 YYYY-MM 或月末日全日期均认）；
    liunian=上一年（YYYY 或年内全日期均认）；daxian=第N-1限（date=「第M限」字符串精确匹配）；
    yuanju=原局无上期概念恒 False。"""
    if layer_type == "liuri":
        return rec_date == (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if layer_type == "liushi":
        return rec_date == liushi_prev_label()
    if layer_type == "liuyue":
        prev_month = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
        return rec_date == prev_month or rec_date.startswith(prev_month + "-")
    if layer_type == "liunian":
        prev_year = str(datetime.date.today().year - 1)
        return rec_date == prev_year or rec_date.startswith(prev_year + "-")
    if layer_type == "daxian":
        if not label:
            return False
        m = re.match(r"^第(\d{1,3})限$", label or "")
        if not m or int(m.group(1)) <= 1:
            return False  # 第1限无上一限
        return rec_date == "第%d限" % (int(m.group(1)) - 1)
    return False  # yuanju 恒无上期


def load_pending(layer_type, data_dir, label=None):
    """纯读 pending_predictions.jsonl（无副作用）：status=="待验证" 且 layer==当前层 且
    date==上一同层批次（六层口径见 prev_batch_match）。目标批次无待验证→尾节空态句（常驻，非跳节）。"""
    path = os.path.join(resolve_data_dir(data_dir), PENDING_FILE)
    recs = []
    if not os.path.isfile(path):
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("status") != "待验证":
                continue
            if rec.get("layer", "liuri") != layer_type:
                continue
            if not prev_batch_match(layer_type, rec.get("date", ""), label):
                continue
            recs.append(rec)
    recs.sort(key=lambda r: (r.get("date", ""), r.get("pred_id", "")))
    return recs


def render_pending(recs):
    """按模板尾节格式区示例渲染（唯一规范）：YYYY-MM-DD 完整日期锚＋「预测原文完整显示」禁截断＋三态问句，一条一段、条间空行（markdown 双换行）、无编号。"""
    lines = []
    for rec in recs:
        pred = rec.get("prediction", "")
        core = pred  # 完整显示预测原文，禁截断（30 字截断会看不全无法回答）
        lines.append("%s「%s」当天这类事发生了吗？（没发生/发生了→结果如何/记不清了）"
                     % (rec.get("date", ""), core))
    return "\n\n".join(lines)


BRIEF_NAME_RE = re.compile(r"^报告-(.*)-简报\.md$")


def label_key(layer_type, lbl):
    """label → 可比较键（六层「上期同层简报=label<本期的最新一份」判定用）；
    daxian=限序整数；liushi=(日期,时支序)；liunian 剥「年」后缀对齐文件名；其余=字符串；
    不可解析返回 None。"""
    if lbl is None:
        return None
    if layer_type == "daxian":
        m = re.match(r"^第(\d{1,3})限$", lbl)
        return int(m.group(1)) if m else None
    if layer_type == "liushi":
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-([子丑寅卯辰巳午未申酉戌亥])时?$", lbl)
        if not m:
            return None
        return (m.group(1), LIUSHI_BRANCHES.index(m.group(2)))
    if layer_type == "liunian":
        return lbl[:-1] if lbl.endswith("年") else lbl
    return lbl


def load_recent_events(layer_type, label, person, out_path, data_dir):
    """近期事件节数据注入（fill_brief 统一注入六层）。口径=自上期同层简报（out 同目录、文件名 label<本期的最新一份
    报告-*-简报.md；yuanju 取其余最新 mtime 份）以来 created_at 新入册的该命主账本条目。
    上期简报不存在（首期）→无时间界，返回 (None, 0)（空态句+stderr 注记）。"""
    d = os.path.dirname(os.path.abspath(out_path))
    cur_name = os.path.basename(out_path)
    cur_key = label_key(layer_type, label) if layer_type != "yuanju" else None
    best_key, best_mt = None, None
    if os.path.isdir(d):
        for name in os.listdir(d):
            if name == cur_name:
                continue
            m = BRIEF_NAME_RE.match(name)
            if not m:
                continue
            if layer_type == "yuanju":
                key = None
            else:
                key = label_key(layer_type, m.group(1))
                if key is None or cur_key is None or key >= cur_key:
                    continue
            try:
                mt = os.path.getmtime(os.path.join(d, name))
            except OSError:
                continue
            better = best_mt is None
            if key is None:  # yuanju：取其余最新 mtime 份
                better = better or mt > best_mt
            else:
                better = better or key > best_key or (key == best_key and mt > best_mt)
            if better:
                best_key, best_mt = key, mt
    if best_mt is None:
        sys.stderr.write("⚠ 近期事件：未找到上期同层简报（首期无时间界）——本节按空态渲染。\n")
        return None, 0
    cutoff = datetime.datetime.fromtimestamp(best_mt).strftime("%Y-%m-%dT%H:%M:%S")
    if best_mt is None:
        sys.stderr.write("⚠ 近期事件：未找到上期同层简报（首期无时间界）——本节按空态渲染。\n")
        return None, 0
    cutoff = datetime.datetime.fromtimestamp(best_mt).strftime("%Y-%m-%dT%H:%M:%S")
    data_dir = resolve_data_dir(data_dir)
    recs = []
    for _, _, name in list_shards(data_dir):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("person") != person:
                continue
            if rec.get("created_at", "") > cutoff:
                recs.append(rec)
    recs.sort(key=lambda r: (r.get("created_at", ""), r.get("工程标识", "")))
    return recs, cutoff


AMOUNT_PAREN_RE = re.compile(r"（[+\-−]?[0-9][0-9.,万千]*）")


def market_lookback(theory):
    """盘面回看浓缩：从 theory ④段抽「方向——」或「从盘推事」标记句（取首个命中）与
    「双线归因」句拼接（"；"连接）。
    无④段或两标记皆无→返回 None（旧条目兼容，整行省略）；>200 字符截断至最后一个句号。"""
    if not theory:
        return None
    seg = theory.split("④", 1)[1].split("⑤", 1)[0] if "④" in theory else ""
    i = min((j for j in (seg.find("方向——"), seg.find("从盘推事")) if j >= 0), default=-1)
    if i < 0:
        return None
    a = seg[i:next((j for j in (seg.find("；", i), seg.find("。", i)) if j > 0), len(seg))]
    b = ""
    j = seg.find("双线归因")
    if j >= 0:
        k = seg.find("。", j)
        b = seg[j:k if k > 0 else len(seg)]
    out = (a + ("；" + b if b else "")).strip()
    if len(out) > 200:
        cut = out.rfind("。", 0, 200)
        out = out[:cut + 1] if cut > 0 else out[:200]
    return out or None


def render_recent_events(recs):
    """近期事件节渲染（新格式）：行首加粗「MM-DD · 宫 · 类」，事件文本剥离金额括号段，
    判定尾随 prediction 对照括注（有则）；来源仅有留档时渲染；工程标识不出现；
    有④段方向句的条目紧跟「盘面回看」行；排序=事件日新→旧。"""
    ordered = sorted(recs, key=lambda r: (r.get("event_date", ""), r.get("created_at", "")), reverse=True)
    lines = []
    for r in ordered:
        d = r.get("event_date", "")
        md = d[5:] if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else d
        text = AMOUNT_PAREN_RE.sub("", r.get("text", ""))
        head = "**%s · %s · %s**" % (md, r.get("event_palace")
                                     or LEVEL_CN.get(r.get("level", ""), "") or "宫线未标注",
                                     r.get("category", ""))
        line = "%s｜%s｜判定：%s" % (head, text, r.get("verify_result", ""))
        pred = (r.get("prediction") or "").strip()
        if pred:
            line += "（%s→%s）" % (pred[:30] + ("…" if len(pred) > 30 else ""), r.get("verify_result", ""))
        src = (r.get("session_hint") or "").strip()[:60]
        if src:
            line += "｜来源：%s" % src
        lines.append(line)
        look = market_lookback(r.get("theory", ""))
        if look:
            lines.append("盘面回看：%s" % look)
    return "\n\n".join(lines)


def scenario_card(person, data_dir=None):
    """命主高频场景卡（行为画像，内联现算无缓存）：扫印证库 events_*.jsonl
    按 person 过滤、截至昨日（event_date < 今天），统计类目频次取 top SCENARIO_TOP_K。
    返回派单末尾追加段；无记录返回空串（跳段非报错）。"""
    try:
        data_dir = resolve_data_dir(data_dir)
        today = datetime.date.today().isoformat()
        counts = {}
        n = 0
        for _, _, name in list_shards(data_dir):
            for line in read_lines(os.path.join(data_dir, name)):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("person") != person:
                    continue
                if rec.get("event_date", "") >= today:
                    continue
                n += 1
                cat = rec.get("category", "") or "未分类"
                counts[cat] = counts.get(cat, 0) + 1
    except (OSError, ValueError) as e:
        sys.stderr.write("⚠ 高频场景统计失败（%s）——派单不含场景卡\n" % e)
        return ""
    if not n:
        return ""
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:SCENARIO_TOP_K]
    return "\n【命主高频场景】（截至昨日，印证库 n=%d）：%s\n" % (
        n, "｜".join("%s×%d" % (c, k) for c, k in top))


def main():
    ap = argparse.ArgumentParser(description="简报派单 prompt 生成器：读模板真源做变量替换（层参数表单一真源，未识别变量 fail-fast）")
    ap.add_argument("--type", required=True, choices=["yuanju", "daxian", "liunian", "liuyue", "liuri", "liushi"])
    ap.add_argument("--person", required=True, help="命主名")
    ap.add_argument("--report", required=True, help="报告路径")
    ap.add_argument("--out", required=True, help="简报输出路径")
    ap.add_argument("--label", help="标题括注；缺省从 --report 文件名提取（四层格式规则见 --help 顶部说明）")
    ap.add_argument("--save", help="直写文件路径（UTF-8 无 BOM）")
    ap.add_argument("--data-dir", default=None, help="印证库目录（默认 _verify；纯读 pending 用）")
    args = ap.parse_args()

    template = load_template()
    if template.count(CRITERIA_ANCHOR) != 1:
        sys.stderr.write("判定标准要求插入锚点「%s」在模板中出现 %d 次（须恰 1 次）——模板可能已升版。\n"
                         % (CRITERIA_ANCHOR, template.count(CRITERIA_ANCHOR)))
        sys.exit(2)
    template = template.replace(CRITERIA_ANCHOR, CRITERIA_ANCHOR + "；" + CRITERIA_REQ, 1)
    # 注：CRITERIA 锚点位于 {{#if liuri|liushi}} 块内（模板要求13），其余层展开条件块时该段整体剔除。
    table = parse_layer_table(template)
    if args.type not in table:
        sys.stderr.write("模板层参数表缺 --type=%s 行（模板可能已升版）。\n" % args.type)
        sys.exit(2)

    label = args.label or extract_label(args.type, args.report)
    if args.type in LABEL_TYPES and not label:
        sys.stderr.write(
            "label 提取失败：--type=%s 需要标题括注（daxian=第N限 / liunian=YYYY年 / liuyue=YYYY-MM / liuri=YYYY-MM-DD / liushi=YYYY-MM-DD-时支），"
            "且无法从报告文件名提取（%s）——请显式传 --label，禁空标题。\n" % (args.type, os.path.basename(args.report)))
        sys.exit(2)
    title = build_title(args.type, table[args.type].get("简报标题", ""), label)
    if not title:
        sys.stderr.write("简报标题构建失败（层=%s，label=%s）。\n" % (args.type, label))
        sys.exit(2)

    variables = {"命主名": args.person, "报告路径": args.report, "简报输出路径": args.out,
                 "层类型": args.type, "简报标题": title}
    for col, var in COLUMN_VARS.items():
        if col == "简报标题":
            continue
        val = table[args.type].get(col)
        if val is None:
            sys.stderr.write("模板层参数表缺列「%s」——模板可能已升版。\n" % col)
            sys.exit(2)
        variables[var] = val

    text = expand_conditionals(strip_doc_title(template), args.type)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # 模板自述注释不入派单

    # 休市日注入（交易日历版——trade_calendar.csv 路径经 anchors.json ZQDATA_ROOT 解析）
    def _is_trading_day(d):
        try:
            _root = find_anchors_zero_root(os.path.dirname(os.path.abspath(__file__)))
            _cal = os.path.join(json.load(open(os.path.join(_root, "extensions", "anchors.json"), encoding="utf-8"))["ZQDATA_ROOT"], "EDB", "Zero_EDB", "calendar", "trade_calendar.csv")
            with open(_cal, encoding="utf-8") as cf:
                for ln in cf:
                    if ln.startswith(d.isoformat()):
                        p = ln.strip().split(",")
                        return p[1] == "1" or p[2] == "1"  # a_stock 或 futures 任一开市（interbank 不用）
                        # 已知局限：a_stock 2027 段为占位 0（数据源未更新）——futures 列兜底多数交易日；2027 年前应更新，若届时误判休市先查此注
            return False  # 日历无此日（超范围）按休市
        except Exception:
            return d.weekday() < 5  # 日历不可读退周末规则
    if not _is_trading_day(datetime.date.today()):
        text = ("【休市日指令】今日为周末休市日——禁出任何交易类预测（方向句收盘符号无从判、交易行为条件句无从触发），"
                "题额全部让给生活线/其他宫线；交易类预测的验证闭环休市日自然空转属正常。\n\n" + text)

    # 尾节常驻：待验证项非空→渲染上一同层批次；空→空态句（标题+空态行照抄）
    pending = load_pending(args.type, args.data_dir, label)
    text = text.replace("{{PENDING_VERIFY_LIST}}",
                        render_pending(pending) if pending else TAIL_EMPTY)
    # 近期事件节常驻（六层）：fill_brief 数据注入
    recent, recent_cutoff = load_recent_events(args.type, label, args.person, args.out, args.data_dir)
    text = text.replace("{{RECENT_EVENTS_LIST}}",
                        render_recent_events(recent) if recent else EVENTS_EMPTY)

    for var, val in variables.items():
        text = text.replace("{{%s}}" % var, val)

    leftover = sorted(set(re.findall(r"\{\{[^{}\n]*\}\}", text)))
    if leftover:
        sys.stderr.write("未识别模板变量（fail-fast，禁静默漏填）：%s\n" % "、".join(leftover))
        sys.exit(2)

    # 高频场景卡（批3）：内联现算、按 person 隔离，追加在派单末尾（无记录=空串不追加）
    card = scenario_card(args.person, args.data_dir)
    if card:
        text = text.rstrip("\n") + "\n" + card

    if args.save:
        with open(args.save, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("已生成派单 prompt → %s（层=%s，标题=%s，label=%s；尾节=%d 条；近期事件=%d 条%s；场景卡=%s）"
              % (args.save, args.type, title, label or "无", len(pending), len(recent or []),
                 "" if recent_cutoff else "（首期空态）", "含" if card else "无"))
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
