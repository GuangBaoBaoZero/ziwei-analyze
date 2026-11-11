# -*- coding: utf-8 -*-
"""从簡报宜忌节提取预测行 → 写入 pending_predictions.jsonl（双识别：
行含「预测：」（新格式）或「待验证」（旧格式）均提取）。

用法：
extract_predictions.py --brief <簡报路径> --person <命主> --date YYYY-MM-DD
                      [--layer liuri] [--data-dir 目录]

提取逻辑：定位宜忌节（## 今日宜忌 / ## 人生大宜忌 / ## 阶段宜忌 / ## 年度宜忌 /
## 月度宜忌 / ## 今日大宜忌 等含「宜忌」标题）→ 逐行找含「待验证」的行 →
提取宫位（行内「（XX宫…）」括号）与预测文本（去掉行首序号/标记与「待验证」标注）。
pred_id = pred-<YYYYMMDD>-<三位序号>，全队列内唯一递增。零第三方依赖。
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ensure_data_dir, resolve_data_dir

PENDING_FILE = "pending_predictions.jsonl"
# 预测行锚点：「预测（高/中/低）：」带档（v1.5）或「预测：」无档（旧格式→confidence=未标）
PRED_ANCHOR_RE = re.compile(r"预测（([高中低])）[：:]|预测[：:]")
SECTION_RE = re.compile(r"^##\s*.*宜忌.*$", re.M)
PALACE_RE = re.compile(r"[（(]([^（()）]*宫[^（()）]*)[）)]")
PRED_ID_RE = re.compile(r"^pred-(\d{8})-(\d{3})$")

# 判定标准生成规则表（判定标准前置，对标 pre-registration resolution criteria）：
# 方向词→符号标准（按句中方向词映射语义）；口舌/人际关键词→事件发生判定；
# 条件句（「若X则/大概Y」）→触发判定。三类均不命中=拒绝入队（汇总输出逐条告知，退出码 1）。
DIRECTION_CRITERIA = {
    "受损": "该端当日收益率<0=受损成立；≥0=不成立",
    "受益": "该端当日收益率>0=受益成立；≤0=不成立",
    "平稳": "该端当日无明显负向异常（收益与事务均在正常区间）=平稳成立；出现明显异常/受损=不成立",
    "劳而少获": "该端当日投入产出不成正比（无实质正收益）=成立；有明显正收益=不成立",
}
EVENT_KEYWORDS = ("口舌", "是非", "争执", "纠纷", "冲突", "小人", "人际", "误会")
EVENT_CRITERIA = "当日出现同类事件（口舌/误会/是非类）=验证机会；无=未触发"


def build_resolution_criteria(pred):
    """按句式生成判定标准：条件句→触发判定；方向句→按方向词符号标准（逐分句）；
    口舌/人际句→事件发生判定。均不命中返回 None（调用方拒绝入队）。"""
    m = re.search(r"若([^，。；,]{1,30})[，,]", pred)
    if m:
        return "触发判定：「%s」当日发生=按句后半判定；未发生=未触发" % m.group(1)
    crits = []
    for part in re.split(r"[，,；;]", pred):
        for word, crit in DIRECTION_CRITERIA.items():
            if word in part:
                crits.append(crit)
                break
    if crits:
        return "；".join(crits)
    if any(k in pred for k in EVENT_KEYWORDS):
        return EVENT_CRITERIA
    return None


def clean_prediction(line):
    """取核心预测句：去行首序号/「宜忌X：」/「预测：」前缀、去宫位括号、去待验证标注与尾破折号。"""
    text = re.sub(r"^[\s>*\-—①-⑳\d\.、）)]+", "", line.strip())
    text = re.sub(r"^[宜忌][\u4e00-\u9fff]{0,4}[：:]\s*", "", text)
    text = re.sub(r"^预测（[高中低]）[：:]\s*", "", text)
    text = re.sub(r"^预测[：:]\s*", "", text)
    text = PALACE_RE.sub("", text)
    text = re.sub(r"[（(]?待验证[）)]?[。！!？?\s]*$", "", text)
    text = text.strip("*——-— \t")
    return text


def extract_confidence(line):
    """取预测行置信档：带档「预测（高）：」→高/中/低；旧「预测：」→未标。"""
    m = re.search(r"预测（([高中低])）[：:]", line)
    return m.group(1) if m else "未标"


def extract_palace(line):
    """从「（XX宫…）」括号内容取宫位名（去掉「宫」字，与库内宫名一致）；未命中返回空串。"""
    m = PALACE_RE.search(line)
    if not m:
        return ""
    pm = re.search(r"([\u4e00-\u9fff]{1,3})宫", m.group(1))
    return pm.group(1) if pm else ""


def next_seq(data_dir, date_compact):
    """扫描现有 pred_id，返回（当日最大序号, 全局最大序号, 已入队键集合）——
    序号保证唯一递增；键集合 (person,date,layer,prediction) 供幂等去重。"""
    path = os.path.join(data_dir, PENDING_FILE)
    day_max, global_max, existing = 0, 0, set()
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                m = PRED_ID_RE.match(rec.get("pred_id", ""))
                if not m:
                    continue
                seq = int(m.group(2))
                global_max = max(global_max, seq)
                if m.group(1) == date_compact:
                    day_max = max(day_max, seq)
                existing.add((rec.get("person", ""), rec.get("date", ""),
                              rec.get("layer", ""), rec.get("prediction", "")))
    return day_max, global_max, existing


def main():
    ap = argparse.ArgumentParser(description="簡报预测提取入 pending 队列")
    ap.add_argument("--brief", required=True, help="簡报 Markdown 路径")
    ap.add_argument("--person", required=True, help="命主名")
    ap.add_argument("--date", required=True,
                    help="批次标识：liuri=YYYY-MM-DD／liushi=YYYY-MM-DD-时支／liuyue=YYYY-MM／"
                         "liunian=YYYY／daxian=第N限／yuanju=终身")
    ap.add_argument("--layer", default=None,
                    help="分析层（缺省按 date 形态联动：时支→liushi、纯日期→liuri、YYYY-MM→liuyue、"
                         "YYYY→liunian、第N限→daxian、终身→yuanju；再不中按簡报标题含「第N限」/人生简报判；显式传参优先）")
    ap.add_argument("--data-dir", default=None, help="印证库目录（默认 _verify）")
    args = ap.parse_args()

    # 六层 date 形态：daxian/yuanju 无自然日期，date 字段存「第N限」/「终身」，
    # pred_id 序号段取当天日期（与日级共用当日序号空间保证全局唯一递增）
    DAXIAN_DATE_RE = re.compile(r"^第\d{1,3}限$")
    if not re.match(r"^\d{4}-\d{2}-\d{2}(-[子丑寅卯辰巳午未申酉戌亥])?$|^\d{4}-\d{2}$|^\d{4}$", args.date) \
            and not DAXIAN_DATE_RE.match(args.date) and args.date != "终身":
        print("错误：--date 形态须为 YYYY-MM-DD / YYYY-MM-DD-时支 / YYYY-MM / YYYY / 第N限 / 终身")
        sys.exit(2)
    if not os.path.isfile(args.brief):
        print("错误：簡报不存在：%s" % args.brief)
        sys.exit(2)

    with open(args.brief, "r", encoding="utf-8") as f:
        brief_text = f.read()

    # layer 缺省联动（显式传参优先）：date 形态 → 簡报标题（第N限→daxian、人生简报→yuanju）
    if args.layer is None:
        if re.search(r"-[子丑寅卯辰巳午未申酉戌亥]$", args.date):
            args.layer = "liushi"
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
            args.layer = "liuri"
        elif re.match(r"^\d{4}-\d{2}$", args.date):
            args.layer = "liuyue"
        elif re.match(r"^\d{4}$", args.date):
            args.layer = "liunian"
        elif DAXIAN_DATE_RE.match(args.date):
            args.layer = "daxian"
        elif args.date == "终身":
            args.layer = "yuanju"
        else:
            title_line = next((ln for ln in brief_text.splitlines() if ln.startswith("# ")), "")
            m = DAXIAN_DATE_RE.search(title_line)
            if m:
                args.layer, args.date = "daxian", m.group(0)
            elif "人生简报" in title_line:
                args.layer, args.date = "yuanju", "终身"
            else:
                print("错误：无法判定 layer——请显式传 --layer")
                sys.exit(2)

    # 定位宜忌节：首个含「宜忌」的 ## 标题起、至下一 ## 节前
    # 提取锚点识别：预测锚点正则（带档/无档）命中或行含「待验证」均提取（记行号供拒绝路径报告）
    section_lines = []
    in_section = False
    for lineno, line in enumerate(brief_text.splitlines(), 1):
        if line.startswith("## "):
            in_section = "宜忌" in line
            continue
        if in_section and (PRED_ANCHOR_RE.search(line) or "待验证" in line):
            section_lines.append((lineno, line))
    if not section_lines:
        print("未发现含「预测（档）：」/「预测：」/「待验证」的预测行，队列无新增")
        return

    data_dir = resolve_data_dir(args.data_dir)
    ensure_data_dir(data_dir)
    path = os.path.join(data_dir, PENDING_FILE)
    # pred_id 序号段：日期类批次取批次日期前 10 位；大限/原局（第N限/终身）取当天日期
    date_compact = args.date[:10].replace("-", "") if args.date[:2].isdigit() \
        else datetime.date.today().strftime("%Y%m%d")
    day_max, global_max, existing = next_seq(data_dir, date_compact)
    seq = max(day_max, global_max)
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    added, skipped_dup, rejected = [], 0, []
    for lineno, line in section_lines:
        pred = clean_prediction(line)
        if not pred:
            continue
        # 幂等去重：同人同日同层同文本已在队=跳过（存量记录不回填不动）
        if (args.person, args.date, args.layer, pred) in existing:
            skipped_dup += 1
            continue
        # 判定标准前置：无标准可生成=拒绝入队（禁无标准预测进队列）
        criteria = build_resolution_criteria(pred)
        if not criteria:
            rejected.append((lineno, pred))
            continue
        seq += 1
        rec = {
            "pred_id": "pred-%s-%03d" % (date_compact, seq),
            "person": args.person,
            "date": args.date,
            "layer": args.layer,
            "palace": extract_palace(line),
            "prediction": pred,
            "resolution_criteria": criteria,
            "confidence": extract_confidence(line),
            "status": "待验证",
            "created_at": now,
        }
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        existing.add((args.person, args.date, args.layer, pred))
        added.append(rec)
    print("提取 %d 条预测入队列 %s（跳过重复 %d 条）" % (len(added), path, skipped_dup))
    for rec in added:
        print("  %s [%s] %s" % (rec["pred_id"], rec["palace"] or "宫位未标注", rec["prediction"]))
        print("    判定标准：%s" % rec["resolution_criteria"])
    if rejected:
        print("拒绝入队 %d 条（无机器判定标准——非金融方向词/条件句/口舌事件三类）：" % len(rejected))
        for lineno, pred in rejected:
            print("  第 %d 行：%s" % (lineno, pred[:60]))
        sys.exit(1)


if __name__ == "__main__":
    main()
