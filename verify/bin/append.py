# -*- coding: utf-8 -*-
"""追加一条命主现实事件到印证账本。用法：
append.py --person 名 --date YYYY-MM-DD|YYYY-MM --category 类 --text 原文
         [--level 层级] [--result 待验] [--session-hint 指针] [--palace 宫名] --theory 分析过程（必填，四段=①宫位判定 ②结构原文+语料判据 ③八要素推理链 ④事件对照）
         [--batch 批次目录] [--pred-id ID] [--data-dir 目录] [--no-extract] [--no-embed] [--soft-gate]
append.py --amend-theory <event_id> --theory 新四段 [--batch 批次目录] [--data-dir 目录] [--soft-gate]
theory 四段格式（v2）：
①宫位判定依据 ②结构原文+语料判据引用 ③八要素推理链（含行运判语：『』与上级级联）
④事件对照（方向+力度+要素落位）。
原子链三步：落账 → extractor.py 回填盘面特征（combo_features + structure_snapshot L2 切面）
→ embed.py 嵌入向量索引（落账优先，后两步失败仅警告）。
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CATEGORIES, CATEGORY_PALACE_MAP, RESULTS, SHARD_RE, PALACE_NAMES,
                    ensure_data_dir, extract_theory_palace,
                    list_shards, out, read_lines, resolve_data_dir,
                    resolve_event_palace, shard_size)
from suggest_palace import suggest as suggest_palace

PERSON_RE = re.compile(r"^[\w\u4e00-\u9fff-]+$")
CAPTURE_FILE = "pending_capture.jsonl"

# theory 深度下限（实测基准 900-2500 字）
THEORY_MIN_CHARS = 900
DATE_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
DATE_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
DATE_HOUR_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-([子丑寅卯辰巳午未申酉戌亥])$")
LEVEL_CHOICES = ["liuri", "liuyue", "liunian", "liushi"]
LEVEL_CN = {"liuri": "流日级", "liuyue": "流月级", "liunian": "流年级", "liushi": "流时级"}
# category→默认级映射表（缺省判级唯一依据；例外一律显式 --level）
CATEGORY_LEVEL_MAP = {
    "交易盈亏": "liuri", "健康": "liuri", "意外": "liuri",
    "口舌是非": "liuri", "情绪波动": "liuri", "出行": "liuri",
    "重要决策": "liuyue", "人际事件": "liuyue",
}


def parse_date(s):
    m = DATE_HOUR_RE.match(s)
    if m:
        datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return s, "hour"
    m = DATE_DAY_RE.match(s)
    if m:
        datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return s, "day"
    m = DATE_MONTH_RE.match(s)
    if m:
        int(m.group(1)); int(m.group(2))
        return s, "month"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return s, "year"
    return None, None


def judge_level(args, precision):
    """三级判级链：显式 --level 最高 > precision 形态（hour→liushi+告警） > 类目八类表。
    返回落账 level（可能为空串=未知类目无默认且未显式）。"""
    if args.level:
        default = CATEGORY_LEVEL_MAP.get(args.category, "")
        if default and default != args.level:
            out("提示：显式 --level %s 与类目「%s」默认级 %s 不一致——落显式值"
                % (args.level, args.category, default))
        return args.level
    if precision == "hour":
        out("告警：date 带时支后缀（hour 精度）缺省判级=liushi（流时级）——如非时辰级事件请显式 --level")
        return "liushi"
    level = CATEGORY_LEVEL_MAP.get(args.category, "")
    if not level:
        out("⚠ 类目「%s」不在 category→级映射表——无法缺省判级，level 落空（扩表前过渡：请显式 --level）"
            % args.category)
    return level


def run_extractor(event_id, data_dir=None):
    """落账后原子回填：子进程调 extractor.py --event-id；失败仅警告，落账优先。
    data_dir 给定=透传 --data-dir（副本环境隔离）。"""
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
               "extractor.py"), "--event-id", event_id]
    if data_dir:
        cmd += ["--data-dir", data_dir]
    env = dict(os.environ, PYTHONUTF8="1")
    try:
        r = subprocess.run(cmd, capture_output=True, env=env)
    except OSError as e:
        out("⚠ 盘面回填失败：%s——落账已成功，可后续手动跑 extractor" % e)
        return
    text = r.stdout.decode("utf-8", "replace")
    pat = re.escape(event_id)
    m = re.search(r"已回填：%s (\S+) 命宫\((\S+)\) 双化(\d+)条" % pat, text)
    if r.returncode == 0 and m:
        out("盘面已回填：%s命宫(%s) 双化%s条" % (m.group(1), m.group(2), m.group(3)))
        return
    m2 = re.search(r"跳过（([^）]+)）：%s" % pat, text)
    reason = m2.group(1) if m2 else (
        re.search(r"FAIL（([^）]+)）：%s" % pat, text).group(1)
        if re.search(r"FAIL（[^）]+）：%s" % pat, text) else "未知原因")
    out("⚠ 盘面回填失败：%s——落账已成功，可后续手动跑 extractor" % reason)


def vec_python():
    """嵌入步专用解释器：anchors PYTHON_VEC（faiss 在场）；缺席退 sys.executable。"""
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        path = os.path.join(cur, "anchors.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = json.load(f).get("PYTHON_VEC")
                if val:
                    return val
            except (OSError, ValueError):
                return sys.executable
            return sys.executable
        parent = os.path.dirname(cur)
        if parent == cur:
            return sys.executable
        cur = parent


def run_embed(event_id, data_dir):
    """原子链第三步：venv 子进程嵌入 FAISS；失败仅警告，落账不受影响。"""
    cmd = [vec_python(), os.path.join(os.path.dirname(os.path.abspath(__file__)),
             "embed.py"), "--event-id", event_id, "--data-dir", data_dir]
    env = dict(os.environ, PYTHONUTF8="1")
    try:
        r = subprocess.run(cmd, capture_output=True, env=env)
    except OSError as e:
        out("⚠ 嵌入失败：%s——落账已成功，可后续手动跑 embed.py" % e)
        return
    try:
        summary = json.loads(r.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        summary = None
    if r.returncode == 0 and summary:
        out("已嵌入索引（top-K 可检索）：索引现 %s 条" % summary.get("total", "?"))
        return
    reason = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1] \
        if r.stderr else "未知原因"
    out("⚠ 嵌入失败：%s——落账已成功，可后续手动跑 embed.py" % reason)


XYUN_RE = re.compile(r"行运判语：『([^』]+)』")
SUPERIOR_RE = re.compile(r"【上级分析结论参考】(.*?)(?=\n【|\Z)", re.S)

# ③段维度覆盖：九维度组词 + 八要素词（行运/版本判定/叠盘/级联任一命中计入维度）
DIM_KEYWORDS = [
    '主星', '四化',
    '辅星|辅曜|左辅|右弼|文昌|文曲|天魁|天钺',
    '煞星|煞曜|擎羊|陀罗|火星|铃星|地空|地劫',
    '三方四正|三合|对宫',
    '流曜|流昌|流曲|流魁|流钺',
    '十二神|博士|岁建|将星|长生',
    '化性|传染',
    '杂曜|天喜|红鸾|天官|天福',
    '行运|版本判定|叠盘|级联',
]

THEORY_FORMAT_HINT = ("theory 四段格式（v2）：①宫位判定依据"
                      " ②结构原文+语料判据「」引用（合计≥2、每处≥10字符）"
                      " ③八要素推理链（含「行运判语：『原文』」前缀标记格式+上级级联引用）"
                      " ④事件对照（方向+力度+要素落位）")


def load_batch_input(batch_dir, palace):
    """读批次目录对应宫 input 切片 -> (input文本 or None, 上级参考存在 bool, 说明)。
    返回 None=豁免（--batch 未传或目录不存在，凭机器证据）；'' 且说明非空=目录在但切片缺失（不豁免）。"""
    if not batch_dir or not os.path.isdir(batch_dir):
        return None, False, ""
    names = palace and [palace, palace.rstrip("宫"), palace + "宫"] or []
    matched = []
    for path in sorted(glob.glob(os.path.join(batch_dir, "input_*.md"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        for n in names:
            if n and stem.endswith("_" + n):
                matched.append(path)
                break
    if not matched:
        return "", False, "批次目录中未找到宫位 %s 的 input 切片（input_*_<宫名>.md）" % (palace or "?")
    with open(matched[0], encoding="utf-8") as f:
        text = f.read()
    m = SUPERIOR_RE.search(text)
    has_super = bool(m and m.group(1).strip())
    return text, has_super, ""


def check_theory_quality(theory, batch_input=None, has_super=False, soft_gate=False):
    """batch_input=None（未传 --batch 或目录不存在）→ 豁免素材三项校验；
    否则做行运判语/级联/结构原文字串校验（--soft-gate 时降为 warning）。"""
    errors = []
    warns = []

    # ① 字数（去空白中文字符）
    clean = re.sub(r'\s', '', theory)
    if len(clean) < 500:
        errors.append(f"字数 {len(clean)} < 500——须扩充③段八要素推理链")

    # ② 维度覆盖（九维度+八要素，至少5组命中）
    hits = sum(1 for kw in DIM_KEYWORDS if re.search(kw, theory))
    if hits < 5:
        errors.append(f"维度覆盖 {hits}/{len(DIM_KEYWORDS)} < 5——③段须至少覆盖5组维度（九维度+八要素词）")

    # ③ 语料原文引用（含中文引号）
    if '「' not in theory and '『' not in theory:
        errors.append("缺语料原文引用（须含「」引号引用语料原文）")

    # ③b 深度·字数下限（防"每维度一句带过"式薄 theory）
    if len(clean) < THEORY_MIN_CHARS:
        errors.append(f"theory 深度不足：{len(clean)} 字 < {THEORY_MIN_CHARS}"
                      "（基准：四段俱全+每维度≥2句展开+语料≥2条引用）")

    # ③c 深度·语料引用块（「」引用≥2处且每处≥10字符，防空引号凑数）
    quotes = [q.strip() for q in re.findall(r'「([^」]+)」', theory)]
    valid_quotes = [q for q in quotes if len(q) >= 10]
    if len(valid_quotes) < 2:
        errors.append(f"语料引用不足：有效引用 {len(valid_quotes)} 处 < 2"
                      "（须「」引用块≥2处且每处≥10字符；②段=结构原文+语料判据各≥1）")

    # ④ 力度定性（文本匹配，禁用\b——中文word boundary不可靠）
    if not ('力度' in theory or '强' in theory or '弱' in theory):
        warns.append("缺力度定性（建议含'力度：强/中/弱'）")

    # ⑤ 素材三项校验（--batch 且批次目录在盘时；soft-gate 降级为 warning）
    if batch_input is not None:
        material = []
        xyun = XYUN_RE.findall(theory)
        if not xyun:
            material.append("③段缺行运判语引用（前缀标记格式「行运判语：『原文』」，原文为批次切片【行运匹配判语】逐字节选）")
        else:
            for q in xyun:
                if q not in batch_input:
                    material.append("行运判语非逐字原文（input 切片中不存在）：『%s…』" % q[:20])
        if has_super and '上级' not in theory:
            material.append("③段缺上级级联引用（input 切片含【上级分析结论参考】，theory 须含「上级」字样的引用句，如「按上级已判定结论——…」）")
        struct_quotes = [q.strip() for q in quotes if len(q.strip()) >= 10 and q.strip() in batch_input]
        if not struct_quotes:
            material.append("②段缺结构原文引用（须含「」≥1处且逐字存在于批次 input 切片）")
        if material:
            if soft_gate:
                warns.extend(material)
                out("⚠ --soft-gate：素材校验已降为警告")
            else:
                errors.extend(material)

    return errors, warns


def do_amend_theory(args, data_dir):
    """修订模式：全 person 扫描定位 event_id → 新 theory 重过全闸 → 原文归档 theory_superseded
    → 联动重跑宫位解析/盘面特征/embed。闸不过=拒绝修订（退出码 2，记录不动）。"""
    if not args.theory.strip():
        out("错误：--amend-theory 须配 --theory 新四段文本")
        sys.exit(2)
    found = None
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
            if rec.get("event_id") == args.amend_theory:
                found = (path, idx, raw, rec)
                break
        if found:
            break
    if not found:
        out("错误：全库未找到 event_id=%s" % args.amend_theory)
        sys.exit(2)
    path, idx, raw, rec = found

    palace_hint = args.palace or extract_theory_palace(args.theory)[0] \
        or CATEGORY_PALACE_MAP.get(rec.get("category", ""))
    batch_input, has_super, note = load_batch_input(args.batch, palace_hint)
    if batch_input == "":
        out("⚠ %s——素材校验仍执行（不豁免）" % note)

    errors, warns = check_theory_quality(args.theory, batch_input, has_super, args.soft_gate)
    for w in warns:
        out(f"⚠ {w}")
    if errors:
        for e in errors:
            out(f"错误：{e}")
        out("修订被拒：新 theory 未过质量闸，记录未改动")
        sys.exit(2)

    rec.setdefault("theory_superseded", []).append(rec.get("theory", ""))
    rec["theory"] = args.theory
    rec["theory_amended_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    palace, ambiguous, warn = resolve_event_palace(rec.get("category", ""), args.theory)
    palace_src = "auto"
    if args.palace:
        p = args.palace.rstrip("宫") if args.palace.rstrip("宫") in PALACE_NAMES else args.palace
        if p not in PALACE_NAMES:
            out("错误：--palace 须为十二宫名之一：" + "、".join(PALACE_NAMES))
            sys.exit(2)
        palace, palace_src = p, "--palace"
    if palace:
        rec["event_palace"] = palace
        rec["palace_source"] = palace_src
        rec.pop("palace_ambiguous", None)
        out("宫位联动更新：event_palace=%s（%s）" % (palace, palace_src))
    else:
        out("⚠ 修订后 theory 未判出宫位——event_palace 维持原值 %r" % rec.get("event_palace"))
    if warn:
        out("⚠ %s" % warn)

    # 清空特征以强制 extractor 重算（不清空会被"已非空"跳过）
    rec["combo_features"] = {}
    rec["structure_snapshot"] = {}
    raw[idx] = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(path + ".bak", "w", encoding="utf-8", newline="") as f:
        with open(path, "r", encoding="utf-8", newline="") as src:
            f.write(src.read())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(raw)
    os.replace(tmp, path)
    out("已修订 theory：%s（第 %d 代原文归档 theory_superseded）" % (rec["event_id"], len(rec["theory_superseded"])))

    if not args.no_extract:
        run_extractor(rec["event_id"], data_dir)
    if not args.no_embed:
        run_embed(rec["event_id"], data_dir)


def main():
    ap = argparse.ArgumentParser(description="追加印证事件")
    # 四项必填仅在追加路径强制（--amend-theory 修订路径不需要，见 main 内手动校验）
    ap.add_argument("--person")
    ap.add_argument("--date")
    ap.add_argument("--category")
    ap.add_argument("--text")
    ap.add_argument("--level", default="", choices=[""] + LEVEL_CHOICES,
                    help="周期量级（拼音值）：liuri/liuyue/liunian/liushi；缺省自动判（显式>precision 形态>类目八类表）")
    ap.add_argument("--result", default=None,
                    help="实际验证结果（缺省待验；--from-capture 时自动填捕获行值）")
    ap.add_argument("--session-hint", dest="session_hint", default="")
    ap.add_argument("--theory", default="",
                    help="分析过程（必填，theory v2）：四段=①宫位判定依据 ②结构原文+语料判据引用 ③八要素推理链（含行运判语：『』与级联） ④事件对照（方向+力度+要素落位）")
    ap.add_argument("--prediction", default="",
                    help="当时分析中的可证伪预测原文（先预测后验证）")
    ap.add_argument("--outcome", default="",
                    help="实际结果分类（如 亏损/盈利——与 prediction 对照后 --result 填 预测准确/预测不准）")
    ap.add_argument("--palace", default="",
                    help="事件归宫（推荐显式指定，如 财帛；缺省时依次 fallback：theory 提取 → suggest_palace 关键词建议）")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--batch", default="",
                    help="批次目录路径：闸读该目录对应宫 input_*.md 做素材逐字校验（行运判语/级联/结构原文）；目录不存在→豁免素材三项（凭机器证据）")
    ap.add_argument("--pred-id", dest="pred_id", default="",
                    help="预测 ID（pred-YYYYMMDD-NNN）：事件记录 pred_id 字段；--from-capture 时自动带入捕获行值")
    ap.add_argument("--amend-theory", dest="amend_theory", default="",
                    help="修订模式：按 event_id 更新 theory（原文归档 theory_superseded），联动宫位解析/盘面回填/embed；修订 theory 须重过全部质量闸")
    ap.add_argument("--soft-gate", dest="soft_gate", action="store_true", default=False,
                    help="素材三项校验（行运判语/级联/结构原文）降为警告不拒绝；默认硬拒")
    ap.add_argument("--no-extract", dest="no_extract", action="store_true", default=False,
                    help="跳过落账后的盘面特征自动回填")
    ap.add_argument("--no-embed", dest="no_embed", action="store_true", default=False,
                    help="跳过回填后的向量索引自动嵌入")
    ap.add_argument("--from-capture", dest="from_capture", default="",
                    help="从 pending_capture.jsonl 按 pred_id 取捕获行：自动填充 prediction/result，落账后移除该行")
    args = ap.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    if args.amend_theory:
        do_amend_theory(args, data_dir)
        return
    missing = [n for n, v in (("--person", args.person), ("--date", args.date),
                              ("--category", args.category), ("--text", args.text)) if not v]
    if missing:
        out("错误：追加路径缺必填参数：" + "、".join(missing))
        sys.exit(2)
    capture_rec = None
    if args.from_capture:
        capture_path = os.path.join(data_dir, CAPTURE_FILE)
        if not os.path.isfile(capture_path):
            out("错误：捕获文件不存在：%s（--from-capture 引用必须存在）" % capture_path)
            sys.exit(2)
        for line in read_lines(capture_path):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("pred_id") == args.from_capture:
                capture_rec = rec
                break
        if capture_rec is None:
            out("错误：捕获文件中无 pred_id=%s（引用必须存在，防拼写错致静默双录）"
                % args.from_capture)
            sys.exit(2)
        if args.prediction and args.prediction != capture_rec.get("prediction", ""):
            out("⚠ --prediction 与捕获行不一致，以捕获行为准（预测原文以入队时为准，禁改写）")
        if args.result and args.result != capture_rec.get("result", ""):
            out("⚠ --result 与捕获行不一致，以捕获行为准")
        args.prediction = capture_rec.get("prediction", args.prediction)
        args.result = capture_rec.get("result", args.result)
        if not args.pred_id:
            args.pred_id = capture_rec.get("pred_id", "")
    if args.result is None:
        args.result = "待验"

    if not PERSON_RE.match(args.person):
        out("错误：person 含非法字符（允许：中文/字母/数字/下划线/连字符）")
        sys.exit(2)
    event_date, precision = parse_date(args.date)
    if event_date is None:
        out("错误：date 须为 YYYY-MM-DD[-时支] / YYYY-MM / YYYY")
        sys.exit(2)
    if args.category not in CATEGORIES:
        out("⚠ 类目「%s」不在白名单八类（%s）——告警放行（扩表前过渡）"
            % (args.category, "、".join(CATEGORIES)))
    level = judge_level(args, precision)
    if level == "liunian" and precision == "day":
        out("提示：liunian 级配 day 精度日期——extractor 按 --year 截前 4 位取流年盘")
    if capture_rec is not None:
        cl = (capture_rec.get("layer") or "").strip()
        cdate = (capture_rec.get("date") or "").strip()
        if not cl:
            out("⚠ 捕获行缺 layer——层键闸放行（旧捕获行形态）")
        elif cl != level:
            out("错误：--from-capture 层键闸：捕获行 layer=%s 与落账 level=%s 不一致——拦截"
                % (cl, level))
            sys.exit(2)
        elif cl in ("liuri", "liushi"):
            if cdate != event_date:
                out("错误：--from-capture 层键闸：%s 级须日期等值——捕获行 %s vs 传参 %s——拦截"
                    % (cl, cdate, event_date))
                sys.exit(2)
        elif not (event_date.startswith(cdate) or cdate.startswith(event_date)):
            out("错误：--from-capture 层键闸：%s 级前缀不相容——捕获行 %s vs 传参 %s——拦截"
                % (cl, cdate, event_date))
            sys.exit(2)
    if not args.text.strip():
        out("错误：text 不能为空")
        sys.exit(2)
    if not args.theory.strip():
        out("错误：缺分析过程（--theory），禁录入。")
        out(THEORY_FORMAT_HINT)
        sys.exit(1)
    # 素材闸：--batch 在盘→读对应宫 input 切片做逐字校验；未传/目录不存在→豁免素材三项
    palace_hint = args.palace or extract_theory_palace(args.theory)[0] \
        or CATEGORY_PALACE_MAP.get(args.category)
    batch_input, has_super, batch_note = load_batch_input(args.batch, palace_hint)
    if batch_input == "":
        out("⚠ %s" % batch_note)
    errors, warns = check_theory_quality(args.theory, batch_input, has_super, args.soft_gate)
    for w in warns:
        out(f"⚠ {w}")
    if errors:
        for e in errors:
            out(f"错误：{e}")
        sys.exit(1)
    if args.result not in RESULTS:
        out("错误：result 必须是：" + "、".join(RESULTS))
        sys.exit(2)

    shards = [s for s in list_shards(data_dir, args.person)]

    # 同会话去重：同 person + 同 date + 同 text
    for _, _, name in shards:
        p = os.path.join(data_dir, name)
        for line in read_lines(p):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("person") == args.person and rec.get("event_date") == event_date \
                    and rec.get("text") == args.text:
                out("已记录（拒绝重复追加）：event_id=%s 同命主同日期同文本" % rec.get("event_id", "?"))
                sys.exit(2)

    # 分片决策：末片满则开新片
    size = shard_size()
    shard_num = 1
    if shards:
        last_name = shards[-1][2]
        count = sum(1 for _ in read_lines(os.path.join(data_dir, last_name)))
        if count >= size:
            shard_num = shards[-1][1] + 1
        else:
            shard_num = shards[-1][1]

    # event_id 时间基：当前时刻；seq 取同前缀全分片最大+1
    now = datetime.datetime.now()
    time_base = now.strftime("%Y%m%d-%H%M%S")
    prefix = "%s-%s-" % (args.person, time_base)
    max_seq = 0
    for _, _, name in shards:
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                eid = json.loads(line).get("event_id", "")
            except ValueError:
                continue
            if eid.startswith(prefix):
                try:
                    max_seq = max(max_seq, int(eid[len(prefix):]))
                except ValueError:
                    continue
    seq = max_seq + 1
    event_id = "%s%03d" % (prefix, seq)

    rec = {
        "event_id": event_id,
        "person": args.person,
        "event_date": event_date,
        "date_precision": precision,
        "level": level,
        "category": args.category,
        "text": args.text,
        "verify_result": args.result,
        "prediction": args.prediction,
        "outcome": args.outcome,
        "judged_by": "agent",
        "pred_id": args.pred_id,
        "session_hint": args.session_hint,
        "combo_features": {},
        "structure_snapshot": {},  # 结构切面（extractor 落账后自动回填，禁手填）
        "theory": args.theory,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    palace, ambiguous, warn = resolve_event_palace(args.category, args.theory)
    palace_src = "auto"  # theory 判定或类目映射
    if not palace and args.palace:
        palace = args.palace.rstrip("宫") if args.palace.rstrip("宫") in PALACE_NAMES else args.palace
        if palace not in PALACE_NAMES:
            out("错误：--palace 须为十二宫名之一（可带/不带宫后缀）：" + "、".join(PALACE_NAMES))
            sys.exit(2)
        palace_src = "--palace"
    if not palace:
        sug = suggest_palace(args.text)
        if sug:
            # 映射表值带"宫"后缀，落账统一为 PALACE_NAMES 无后缀形态（如 财帛宫→财帛）
            palace, hit_kws = sug[0][0].rstrip("宫"), sug[0][1]
            palace_src = "suggest"
            out("宫位自动建议: %s (匹配关键词: %s)" % (palace, "、".join(hit_kws)))
    if palace:
        rec["event_palace"] = palace
        rec["palace_source"] = palace_src
    if ambiguous and not palace:
        rec["palace_ambiguous"] = True
    if warn:
        out("⚠ %s" % warn)
    if not palace:
        out("⚠ 该事件未指定宫位——将无法参与三级匹配。"
            "建议用 --palace 参数显式指定或完善 theory 宫位判定段。")

    ensure_data_dir(data_dir)
    fname = "events_%s-%03d.jsonl" % (args.person, shard_num)
    with open(os.path.join(data_dir, fname), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if capture_rec is not None:
        capture_path = os.path.join(data_dir, CAPTURE_FILE)
        kept = [l for l in read_lines(capture_path)
                if json.loads(l).get("pred_id") != capture_rec["pred_id"]]
        with open(capture_path, "w", encoding="utf-8", newline="\n") as f:
            for l in kept:
                f.write(l + "\n")
        out("捕获待办已销：%s（pending_capture.jsonl 移除该行）" % capture_rec["pred_id"])

    label = LEVEL_CN.get(level) or {"day": "流日级", "month": "流月级", "year": "流年级",
                                    "hour": "流时级"}[precision]
    out("已记印证：%s %s · %s · %s · %s（event_id=%s）"
        % (label, event_date, args.category, args.text[:20], args.result, event_id))
    if not args.no_extract:
        run_extractor(event_id, data_dir)
    if not args.no_embed:
        run_embed(event_id, data_dir)


if __name__ == "__main__":
    main()
