#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pattern_stats — 历史同型盘面战绩统计（预判流程 v2.1 置信度标签源）。

按 combo 特征匹配 events 库历史事件的 combo_features（嵌套 sihua 键提升、
list 逐元素展开；key 必须存在且值子串命中），命中字段数 >= gate 判 matched，
统计已判定样本准确率，输出置信度五档标签与双层注入文本（JSON）。

用法：
  PYTHONUTF8=1 python pattern_stats.py --person <命主名> --combo '{"忌":"天机"}' --gate 1

按宫战绩扩展（预判学习体系方案 v1.5 件 3，仅财帛宫/方向句先行）：
  PYTHONUTF8=1 python pattern_stats.py --person <命主名> --combo '{}' --gate 99 \
      --with-pool-stats --palace 财帛 --palace-zhi 辰 --exclude-date 2026-11-20
  同型池匹配=同日干（流日天干同）+ 应验宫同支（structure_snapshot.palaces[宫].zhi
  与 --palace-zhi 相同）；条目方向（盈/亏）从 prediction 文本解析；统计口径=resolved
  已判定条目；n≥3 给分组数字，n<3 标「积累中」。注入文本首行带「影子期数据」标记。
"""
import argparse
import json
import os
import re
import sys

from common import list_shards, read_lines, resolve_data_dir

# verify_result 口径归一（common.RESULTS 全集）：新口径「预判准确/预判不准」
# + 库内存量旧口径「符合/不符」；「部分」未全中归失准侧；「待验」未判定不计战绩。
# 现行口径（符合计入准确侧）。
ACCURATE_RESULTS = ("预判准确", "预判准确", "符合")  # 旧值「预判准确」兼容（存量判读归一，出口一律新词）
INACCURATE_RESULTS = ("预判不准", "预判不准", "不符", "部分")
PENDING_RESULT = "待验"

# ── 按宫同型池（件 3；本节函数与 verify/bin/pool_query.py 共用，禁单侧改口径）──
_GAN = "甲乙丙丁戊己庚辛壬癸"
_ZHI = "子丑寅卯辰巳午未申酉戌亥"
POOL_MIN_N = 3  # n≥3 给数字；n<3 标「积累中」


def _jdn(y, m, d):
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def day_ganzhi(date_str):
    """公历日期 → 流日干支（公式经 41 份 pan_liuri_*.json day_ganzhi 逐条验证一致）。"""
    y, m, d = (int(x) for x in str(date_str)[:10].split("-"))
    j = _jdn(y, m, d)
    return _GAN[(j + 9) % 10] + _ZHI[(j + 1) % 12]


def parse_direction(prediction):
    """方向句文本 → '盈'/'亏'/None（'为盈/为亏'优先，退首个独立盈/亏字）。"""
    text = str(prediction or "")
    m = re.search(r"为(盈|亏)", text)
    if not m:
        m = re.search(r"(盈|亏)(?![盈亏])", text)
    return m.group(1) if m else None


def load_prediction_directions(data_dir):
    """{date[:10]: (direction, result_judged|None)} ← resolved+pending 交易方向句。

    resolved 条目带 result（准确/不准入统计）；pending 未判（列表可见不计战绩）。
    同日多条取首个可解析方向句（方向句每日一条为主态）。
    """
    out = {}
    for fname in (RESOLVED_FILE, "pending_predictions.jsonl"):
        path = os.path.join(data_dir, fname)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if "若" in rec.get("prediction", ""):
                    continue  # 条件句不入方向池
                d = parse_direction(rec.get("prediction", ""))
                if not d:
                    continue
                key = str(rec.get("date", ""))[:10]
                if key not in out:
                    result = RESULT_JUDGE.get(rec.get("result", ""))
                    out[key] = (d, result)
    return out


RESOLVED_FILE = "resolved_predictions.jsonl"
RESULT_JUDGE = {"准确": True, "不准": False}  # 其余（未触发等）= None 不计战绩


def collect_pool(data_dir, shards, palace, palace_zhi, query_date):
    """同型池：event_palace=宫 + 应验宫同支 + 同日干（query_date 的流日干）。

    排除 query_date 当日（批次防自匹配）；返回 entries 列表
    （date/direction/hit|xingxi/event_id；hit=None=未判定不计战绩）。
    """
    q_gan = day_ganzhi(query_date)[0]
    entries = []
    for _, _, name in shards:
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("event_palace") != palace:
                continue
            edate = str(event.get("event_date", ""))[:10]
            if edate == query_date:
                continue
            zhi = ((event.get("structure_snapshot") or {}).get("palaces")
                   or {}).get(palace, {}).get("zhi")
            if zhi != palace_zhi or day_ganzhi(edate)[0] != q_gan:
                continue
            entries.append(event)
    return entries


def build_pool_stats(data_dir, shards, palace, palace_zhi, query_date):
    """池条目+分组统计+注入文本。统计口径=resolved 已判定；n≥3 给数字。"""
    directions = load_prediction_directions(data_dir)
    events = collect_pool(data_dir, shards, palace, palace_zhi, query_date)
    entries, groups = [], {"盈": [0, 0], "亏": [0, 0]}  # [n, hit]
    xingxi_set = set()
    pending_n = 0
    for event in events:
        edate = str(event.get("event_date", ""))[:10]
        xingxi = (((event.get("structure_snapshot") or {}).get("palaces")
                   or {}).get(palace, {}) or {}).get("xingxi", "")
        xingxi_set.add(xingxi)
        direction, judged = directions.get(edate, (None, None))
        entries.append({
            "event_id": event.get("event_id", ""),
            "date": edate,
            "palace": palace,
            "palace_zhi": (event.get("structure_snapshot") or {}).get(
                "palaces", {}).get(palace, {}).get("zhi", ""),
            "day_ganzhi": day_ganzhi(edate),
            "xingxi": xingxi,
            "direction": direction,
            "judged": judged,
        })
        if direction is None or judged is None:
            pending_n += 1
            continue
        g = groups[direction]
        g[0] += 1
        g[1] += 1 if judged else 0

    def group_line(name):
        n, hit = groups[name]
        if n < POOL_MIN_N:
            return "%s向：积累中（n=%d）" % (name, n)
        return "%s向：n=%d，命中 %d（%.0f%%）" % (name, n, hit, hit * 100 / n)

    stats = {
        "palace": palace,
        "palace_zhi": palace_zhi,
        "day_ganzhi": day_ganzhi(query_date),
        "pool_total": len(events),
        "judged_盈": groups["盈"][0], "hit_盈": groups["盈"][1],
        "judged_亏": groups["亏"][0], "hit_亏": groups["亏"][1],
        "unresolved": pending_n,
        "xingxi_subsets": len(xingxi_set),
    }
    text = ("影子期数据（不作标档依据）\n按宫历史战绩（%s宫·同日干+应验宫%s支同型池）：%s；%s；"
            "盘型级子集 %d 种；未判定 %d 条不计战绩。"
            % (palace, palace_zhi, group_line("盈"), group_line("亏"),
               len(xingxi_set), pending_n))
    return {"stats": stats, "entries": entries, "injection_text": text}


def flatten_features(features):
    """combo_features 展平 -> {key: [str, ...]}：嵌套 dict（sihua）键值提升、list 逐元素展开。"""
    flat = {}

    def walk(node):
        for key, val in node.items():
            if isinstance(val, dict):
                walk(val)
                continue
            vals = val if isinstance(val, list) else [val]
            flat.setdefault(key, []).extend(str(v) for v in vals)

    walk(features)
    return flat


def count_hits(query_combo, flat):
    """query_combo 每键在 flat 中存在且值子串命中 -> 命中字段数。"""
    hits = 0
    for key, want in query_combo.items():
        values = flat.get(key)
        if values and any(str(want) in v for v in values):
            hits += 1
    return hits


def deviation_summary(theory):
    """失准条目偏差摘要：优先取④预判对照段（含偏差分析），缺④取开头，压平空白后截 100 字。"""
    text = re.sub(r"\s+", " ", str(theory or "")).strip()
    idx = text.find("④")
    if idx >= 0:
        text = text[idx:]
    return text[:100]


def classify_result(result):
    if result in ACCURATE_RESULTS:
        return "accurate"
    if result in INACCURATE_RESULTS:
        return "inaccurate"
    return None  # 待验/未知口径：不计战绩


def confidence_label(n, rate):
    if n < 5:
        return "insufficient"
    if n < 8:
        return "marginal"
    if rate >= 0.8:
        return "strong"
    if rate < 0.4:
        return "weak"
    return "sufficient"


def build_injection(n, accurate, inaccurate, rate, notes, level=None):
    """双层注入文本：统计层 + 注意事项层（失准条目偏差摘要）。层内标层。"""
    if n < 5:
        return "样本不足（n=%d），暂不参考历史战绩" % n
    layer_tag = "（%s 层内）" % level if level else ""
    stat = "历史同型盘面战绩%s：n=%d，预判准确 %d（%.0f%%）、预判不准 %d。" % (
        layer_tag, n, accurate, rate * 100, inaccurate)
    if notes:
        return stat + " 历史偏差注意：" + "；".join(notes)
    return stat + " 历史偏差注意：同类盘面暂无失准记录。"


def main():
    ap = argparse.ArgumentParser(description="历史同型盘面战绩统计（置信度标签+注入文本）")
    ap.add_argument("--person", required=True, help="命主名（events_<person>-NNN.jsonl 持有人）")
    ap.add_argument("--combo", default=None, help="待查特征组合 JSON 字符串，如 '{\"忌\":\"天机\"}'（按宫模式可省）")
    ap.add_argument("--gate", type=int, default=3, help="命中字段数阈值，默认 3")
    ap.add_argument("--data-dir", default=None, help="events 数据目录（默认 anchors 三级解析）")
    ap.add_argument("--level", default=None, choices=["liuri", "liuyue", "liunian", "liushi"],
                    help="单层查询：只统计该 level 事件（层内统计，禁跨层合并）")
    ap.add_argument("--exclude-date", dest="exclude_date", default=None,
                    help="排除该日期事件（批次重做防自匹配；按宫模式=当日基准日）")
    ap.add_argument("--with-pool-stats", dest="with_pool_stats", action="store_true",
                    help="按宫同型池战绩（件 3，缺省关；需 --palace/--palace-zhi/--exclude-date）")
    ap.add_argument("--palace", default=None, help="按宫模式的应验宫（现仅财帛）")
    ap.add_argument("--palace-zhi", dest="palace_zhi", default=None,
                    help="按宫模式：当日该宫地支（structure_snapshot.palaces[宫].zhi）")
    args = ap.parse_args()

    try:
        combo = json.loads(args.combo) if args.combo else {}
    except ValueError as e:
        sys.exit("combo 不是合法 JSON：%s" % e)
    if combo and not isinstance(combo, dict):
        sys.exit("combo 必须是非空 JSON 对象")
    if not combo and not args.with_pool_stats:
        sys.exit("combo 必须是非空 JSON 对象（或改用 --with-pool-stats 按宫模式）")
    if args.with_pool_stats and (not args.palace or not args.palace_zhi
                                 or not args.exclude_date):
        sys.exit("按宫模式需 --palace --palace-zhi --exclude-date 三参齐全")

    data_dir = resolve_data_dir(args.data_dir)
    shards = list_shards(data_dir, owner=args.person)
    if not shards:
        sys.exit("未找到命主 %s 的 events 分片（目录 %s）" % (args.person, data_dir))

    scanned = 0
    matched = 0          # 已判定（accurate/inaccurate）的命中数
    matched_pending = 0  # 命中但待验
    accurate = 0
    inaccurate = 0
    notes = []
    matched_events = []
    for _, _, name in shards:
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            scanned += 1
            if not combo:
                continue  # 纯按宫模式：不做 combo 匹配
            if args.level and event.get("level", "") != args.level:
                continue
            if args.exclude_date and (event.get("event_date") == args.exclude_date
                    or event.get("event_date", "").startswith(args.exclude_date + "-")):
                continue
            features = event.get("combo_features")
            if not isinstance(features, dict):
                continue
            if count_hits(combo, flatten_features(features)) < args.gate:
                continue
            result = event.get("verify_result")
            label = classify_result(result)
            if label is None:
                if result == PENDING_RESULT:
                    matched_pending += 1
                continue
            matched += 1
            matched_events.append({"event_id": event.get("event_id", ""),
                                   "verify_result": result})
            if label == "accurate":
                accurate += 1
            else:
                inaccurate += 1
                summary = deviation_summary(event.get("theory", ""))
                if summary:
                    notes.append(summary)

    rate = round(accurate / matched, 4) if matched else None
    confidence = confidence_label(matched, rate or 0)
    injection = build_injection(matched, accurate, inaccurate, rate or 0, notes,
                                level=args.level)
    result = {
        "person": args.person,
        "combo": combo,
        "gate": args.gate,
        "level": args.level,
        "scanned": scanned,
        "matched": matched,
        "matched_pending": matched_pending,
        "accurate": accurate,
        "inaccurate": inaccurate,
        "rate": rate,
        "confidence": confidence,
        "injection_text": injection,
        "matched_events": matched_events,
    }
    if args.with_pool_stats:
        pool = build_pool_stats(data_dir, shards, args.palace, args.palace_zhi,
                                args.exclude_date)
        result["pool_stats"] = pool["stats"]
        result["pool_entries"] = pool["entries"]
        result["pool_stats_text"] = pool["injection_text"]
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
