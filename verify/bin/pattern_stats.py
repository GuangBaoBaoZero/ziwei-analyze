#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pattern_stats — 历史同型盘面战绩统计（预测流程 v2.1 置信度标签源）。

按 combo 特征匹配 events 库历史事件的 combo_features（嵌套 sihua 键提升、
list 逐元素展开；key 必须存在且值子串命中），命中字段数 >= gate 判 matched，
统计已判定样本准确率，输出置信度五档标签与双层注入文本（JSON）。

用法：
  PYTHONUTF8=1 python pattern_stats.py --person <命主名> --combo '{"忌":"天机"}' --gate 1
"""
import argparse
import json
import os
import re
import sys

from common import list_shards, read_lines, resolve_data_dir

# verify_result 口径归一（common.RESULTS 全集）：新口径「预测准确/预测不准」
# + 库内存量旧口径「符合/不符」；「部分」未全中归失准侧；「待验」未判定不计战绩。
# 现行口径（符合计入准确侧）。
ACCURATE_RESULTS = ("预测准确", "符合")
INACCURATE_RESULTS = ("预测不准", "不符", "部分")
PENDING_RESULT = "待验"


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
    """失准条目偏差摘要：优先取④预测对照段（含偏差分析），缺④取开头，压平空白后截 100 字。"""
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
    stat = "历史同型盘面战绩%s：n=%d，预测准确 %d（%.0f%%）、预测不准 %d。" % (
        layer_tag, n, accurate, rate * 100, inaccurate)
    if notes:
        return stat + " 历史偏差注意：" + "；".join(notes)
    return stat + " 历史偏差注意：同类盘面暂无失准记录。"


def main():
    ap = argparse.ArgumentParser(description="历史同型盘面战绩统计（置信度标签+注入文本）")
    ap.add_argument("--person", required=True, help="命主名（events_<person>-NNN.jsonl 持有人）")
    ap.add_argument("--combo", required=True, help="待查特征组合 JSON 字符串，如 '{\"忌\":\"天机\"}'")
    ap.add_argument("--gate", type=int, default=3, help="命中字段数阈值，默认 3")
    ap.add_argument("--data-dir", default=None, help="events 数据目录（默认 anchors 三级解析）")
    ap.add_argument("--level", default=None, choices=["liuri", "liuyue", "liunian", "liushi"],
                    help="单层查询：只统计该 level 事件（层内统计，禁跨层合并）")
    ap.add_argument("--exclude-date", dest="exclude_date", default=None,
                    help="排除该日期事件（批次重做防自匹配）")
    args = ap.parse_args()

    try:
        combo = json.loads(args.combo)
    except ValueError as e:
        sys.exit("combo 不是合法 JSON：%s" % e)
    if not isinstance(combo, dict) or not combo:
        sys.exit("combo 必须是非空 JSON 对象")

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
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
