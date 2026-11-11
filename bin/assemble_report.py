# -*- coding: utf-8 -*-
r"""报告组装（结论汇总架构）：从批次目录 12 份 output_*.md 切「结论」节+注入引用行
（引用行放结论段之前）+核查节骨架，可选 --head 拼接头部成完整报告。

用法：
assemble_report.py --batch <批次目录> --out <输出.md> [--head <头部.md>]

兼容两种批次结构：原局平铺（<对象>\Yuanju\temp\）与流盘嵌套（<对象>\<Topic>\temp\<日期>\）——
自动发现 output_*.md。引用行 slice_ids 双源：ctx.json（原局 make.py）与 pan_*.json
的 retrieval.star_system（流盘 liupan.py）。零第三方依赖。
"""
import argparse
import glob
import io
import json
import os
import re
import sys

PALACE_ORDER = ["命宫", "官禄", "财帛", "福德", "迁移", "疾厄", "田宅",
                "父母", "夫妻", "子女", "兄弟", "仆役"]
OUTPUT_RE = re.compile(r"^output_(\d+)_(.+)\.md$")
CONCLUSION_RE_TMPL = r"^##\s*%s[^\n]*(结论|摘要)"
NEXT_SECTION_RE = r"^##\s"


def find_outputs(batch_dir):
    """{宫名: 路径}；先平铺再一层子目录兜底。"""
    files = glob.glob(os.path.join(batch_dir, "output_*.md"))
    if not files:
        files = glob.glob(os.path.join(batch_dir, "*", "output_*.md"))
    found = {}
    for p in files:
        m = OUTPUT_RE.match(os.path.basename(p))
        if m:
            found[m.group(2)] = p
    return found


def load_slice_ids(batch_dir):
    """{宫名: slice_ids}；ctx.json（原局）与 pan_*.json retrieval.star_system（流盘）双源。"""
    ids = {}
    ctx = os.path.join(batch_dir, "ctx.json")
    if os.path.isfile(ctx):
        with io.open(ctx, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, info in data.items():
            if isinstance(info, dict) and info.get("slice_ids"):
                ids[name] = info["slice_ids"]
    for p in glob.glob(os.path.join(batch_dir, "pan_*.json")):
        with io.open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        for ent in (data.get("retrieval", {}).get("star_system", {}) or {}).values():
            if isinstance(ent, dict) and ent.get("palace") and ent.get("slice_ids"):
                ids.setdefault(ent["palace"], ent["slice_ids"])
    return ids


def load_verify_refs(batch_dir):
    """历史印证命中清单（liupan/make 一查多注所落 verify_refs.json）；缺档=无命中。"""
    for d in (batch_dir, os.path.dirname(batch_dir.rstrip("\\/"))):
        p = os.path.join(d, "verify_refs.json")
        if os.path.isfile(p):
            with io.open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    return []


def verify_refs_block(refs):
    """核查节"历史印证引用清单"渲染（F2 按 match 分流：structured 照表格；
    fuzzy 不进表格，末尾一行背景——撤印证依据地位）。"""
    structured = [r for r in refs if r.get("match") == "structured"]
    fuzzy = [r for r in refs if r.get("match") == "fuzzy"]
    lines = ["### 历史印证引用清单（批次 verify_refs.json）"]
    if not structured and not fuzzy:
        lines.append("（无历史印证命中）")
        return lines
    if structured:
        lines.append("| # | 事件 | 类别 | 日期 | 层 | 印证结果 | 引用宫位 |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, r in enumerate(structured, 1):
            lines.append("| %d | %s | %s | %s | %s | %s | %s |" % (
                i, r.get("text", ""), r.get("category", ""), r.get("date", ""),
                r.get("layer", ""), r.get("verify_result", ""),
                "/".join(r.get("routed_palaces", []))))
    if fuzzy:
        lines.append("模糊参考 %d 条（向量相似，不作印证依据）" % len(fuzzy))
    return lines


PRED_OK = "预测准确"
PRED_BAD = "预测不准"


def _first_evidence(r):
    """一等证据判据（F2 口径）：prediction 非空且 verify_result∈{预测准确,预测不准}。"""
    return bool(r.get("prediction")) and r.get("verify_result") in (PRED_OK, PRED_BAD)


def layer_stats_line(refs):
    """F2 分层统计行：按 layer 分组计数；一等证据 <5 条显示样本不足（口径同 blessing_blocks
    的 n<5 闸门），≥5 条才显示一等证据比率。"""
    names = {"盘型级": "盘型级印证", "星系级": "星系级参考", "宫位级": "宫位级参考"}
    parts = []
    for key in ("盘型级", "星系级", "宫位级"):
        rs = [r for r in refs
              if r.get("layer") == key and r.get("match") == "structured"]
        n = len(rs)
        if n == 0:
            parts.append("%s 0 条" % names[key])
            continue
        first = [r for r in rs if _first_evidence(r)]
        if not first:
            txt = "无预测数据"
        elif len(first) < 5:
            txt = "样本不足"
        else:
            n_acc = sum(1 for r in first if r["verify_result"] == PRED_OK)
            txt = "一等证据准确率 %d%%" % round(100.0 * n_acc / len(first))
        parts.append("%s %d 条（%s）" % (names[key], n, txt))
    return "- 分层统计：%s" % " / ".join(parts)


def blessing_blocks(refs):
    """{宫名: 往事为鉴块行}——全库分层：match=structured 且 layer='盘型级' 的记录全进素材池
    （不再按 prediction 非空排除）；一等判据（有预测且验证落定）标「应验级」，其余标「参考级」，
    一等优先排序；计分仅按应验级口径（预测准确 1.0 计分；预测不准计分母；部分属参考级不入计分）。
    块标题「**往事为鉴**」+块内事件明细行。无匹配=空 dict 不插块。"""
    stats = {}
    for r in refs:
        if r.get("match") != "structured" or r.get("layer") != "盘型级":
            continue
        first = _first_evidence(r)
        grade = "应验级" if first else "参考级"
        res = r.get("verify_result", "")
        for palace in r.get("routed_palaces", []):
            s = stats.setdefault(palace, {"n": 0, "n_first": 0, "score": 0.0, "items": [], "n_fit": 0, "n_part": 0, "n_badfit": 0})
            s["n"] += 1
            if first:
                s["n_first"] += 1
                if res == PRED_OK:
                    s["score"] += 1.0
            else:
                if res == "符合":
                    s["n_fit"] += 1
                elif res == "部分":
                    s["n_part"] += 1
                elif res == "不符":
                    s["n_badfit"] += 1
            if r.get("prediction"):
                chain = "预测%s→实际%s" % (r.get("prediction", ""), r.get("outcome", ""))
            else:
                chain = "实际%s" % (r.get("outcome", "") or r.get("text", "") or "事件参考")
            if first:
                rank = 0 if res == PRED_OK else 1  # 应验级：准确→不准
            else:
                rank = {"符合": 0, "部分": 1, "不符": 3}.get(res, 2)  # 参考级：符合→部分→其他2→不符3
            s["items"].append((0 if first else 1, rank, "［%s］%s %s：%s" % (
                grade, r.get("date", ""), r.get("category", ""), chain)))
    blocks = {}
    for palace, s in stats.items():
        if s["n"] == 0:
            continue
        n_ref = s["n"] - s["n_first"]
        dist = "符合 %d · 部分 %d · 不符 %d" % (s["n_fit"], s["n_part"], s["n_badfit"])
        n_other = n_ref - (s["n_fit"] + s["n_part"] + s["n_badfit"])
        if n_other > 0:
            dist += " · 其他 %d（待复判等）" % n_other
        if s["n_first"]:
            pct = s["score"] / s["n_first"]
            tier = "高置信" if pct >= 0.8 else ("中置信" if pct >= 0.5 else "低置信")
            head = ("此配置历史记录 %d 条（应验级 %d 条，应验级准确率 %d%%——%s；参考级 %d 条：%s）"
                    % (s["n"], s["n_first"], round(pct * 100), tier, n_ref, dist))
        else:
            head = "此配置历史记录 %d 条（应验级 0 条，参考级 %d 条：%s）" % (s["n"], n_ref, dist)
        lines = ["**往事为鉴**", head]
        lines += ["- %s" % it for _, _, it in sorted(s["items"], key=lambda t: (t[0], t[1]))]  # 三级：等级→验证值→时间（stable）
        blocks[palace] = lines
    return blocks


def l2_blocks(refs):
    """{宫名: 星系级/宫位级并列参考块行}——干支直查制：星系级（同干异支·应验宫
    同地支）/宫位级（同支异干·同宫名）structured 命中单条即触发，标注「同线参考级」
    （不作结论主轴）；无命中宫不插块。"""
    stats = {}
    for r in refs:
        if r.get("match") != "structured" or r.get("layer") not in ("星系级", "宫位级"):
            continue
        for palace in r.get("routed_palaces", []):
            stats.setdefault(palace, []).append(r)
    blocks = {}
    for palace, rs in stats.items():
        lines = ["**星系/宫位参考**（同线参考级）",
                 "此线过往同款 %d 次——历史参考，不作结论主轴：" % len(rs)]
        for r in rs:
            chain = "→".join(x for x in (
                "预测%s" % r.get("prediction", "") if r.get("prediction") else "",
                "实际%s" % r.get("outcome", "") if r.get("outcome") else "",
                r.get("verify_result") or "待验证") if x)
            lines.append("- %s %s：%s" % (r.get("date", ""), r.get("category", ""), chain))
        blocks[palace] = lines
    return blocks


FUSION_LAYERS = ("盘型级", "星系级", "宫位级")
FUSION_HEADER = "【融合分析】"
CITE_HEADER = "【引用清单】"


def _evidence_grade(r):
    """证据等级（F2 口径）：一等=有预测且验证落定；其余二等。"""
    return "一等证据" if _first_evidence(r) else "二等证据"


def fusion_materials(refs, slice_ids):
    """素材包结构 {宫名: {...}}——逐命中宫聚合盘型级/星系级/宫位级命中组+语料切片引用+证据等级，
    供主会话微派发 LLM 写融合段（素材聚合单派发）。"""
    mats = {}
    for r in refs:
        if r.get("match") != "structured" or r.get("layer") not in FUSION_LAYERS:
            continue
        for palace in r.get("routed_palaces", []):
            m = mats.setdefault(palace, {"palace": palace, "hits": [],
                                         "slice_ids": slice_ids.get(palace, [])})
            m["hits"].append({
                "layer": r.get("layer", ""),
                "evidence_grade": _evidence_grade(r),
                "event_id": r.get("event_id", ""),
                "person": r.get("person", ""),
                "date": r.get("date", ""),
                "category": r.get("category", ""),
                "text": r.get("text", ""),
                "verify_result": r.get("verify_result", ""),
                "prediction": r.get("prediction", ""),
                "outcome": r.get("outcome", ""),
            })
    for m in mats.values():
        m["layers"] = sorted({h["layer"] for h in m["hits"]})
    return mats


def fusion_citation_lines(palace, refs, slice_ids, sub):
    """融合段配套引用清单（零 LLM，纯程序可核查）：日期/宫线/事件/层级/events id/语料切片。"""
    lines = [CITE_HEADER + "（程序生成，核查流程）"]
    n = 0
    for r in refs:
        if r.get("match") != "structured" or r.get("layer") not in FUSION_LAYERS:
            continue
        if palace not in r.get("routed_palaces", []):
            continue
        n += 1
        label = {"盘型级": "盘型级印证", "星系级": "星系级参考",
                 "宫位级": "宫位级参考"}[r["layer"]]
        ev = "events %s" % r["event_id"] if r.get("event_id") else "events 无 id（留档记录）"
        lines.append("· %s %s·%s（%s）｜%s｜%s" % (
            r.get("date", ""), palace, r.get("text", "") or r.get("category", ""),
            r.get("verify_result", "") or "待验证", label, ev))
    ids = slice_ids.get(palace, [])
    if ids:
        shown = "、".join(ids[:3]) + (" 等 %d 片" % len(ids) if len(ids) > 3 else "")
        lines.append("· 语料：%s（本宫切片，见批次 ctx temp\\%s）" % (shown, sub))
    else:
        lines.append("· 语料：本宫无独立 slice_ids 记录（见批次 ctx temp\\%s）" % sub)
    return lines


def slice_conclusion(text, name):
    """取「## <宫名> 结论」起、至下一「## 」节前或文末（标题前缀匹配容后缀）。"""
    start_re = re.compile(CONCLUSION_RE_TMPL % re.escape(name), re.M)
    end_re = re.compile(NEXT_SECTION_RE, re.M)
    m = start_re.search(text)
    if not m:
        return None
    e = end_re.search(text, m.end())
    return text[m.start():e.start() if e else len(text)].rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="十二宫报告组装")
    ap.add_argument("--batch", required=True, help="批次目录（含 12 份 output_*.md）")
    ap.add_argument("--out", required=True, help="输出 Markdown 路径")
    ap.add_argument("--head", default=None, help="可选：主会话头部 Markdown，拼接在详解前")
    ap.add_argument("--fusion-dir", default=None,
                    help="融合段目录（含 fusion_<宫名>.md；缺省=批次目录；无文件宫不嵌入）")
    args = ap.parse_args()

    batch = os.path.abspath(args.batch)
    fusion_dir = os.path.abspath(args.fusion_dir) if args.fusion_dir else batch
    outputs = find_outputs(batch)
    missing = [n for n in PALACE_ORDER if n not in outputs]
    if missing:
        print("错误：批次缺宫 %s（发现：%s）" % ("、".join(missing), "、".join(outputs) or "无"))
        sys.exit(2)

    slice_ids = load_slice_ids(batch)
    refs = load_verify_refs(batch)
    blocks = blessing_blocks(refs)
    l2 = l2_blocks(refs)
    mats = fusion_materials(refs, slice_ids)
    if mats:
        with io.open(os.path.join(batch, "fusion_materials.json"), "w",
                     encoding="utf-8", newline="\n") as f:
            json.dump(mats, f, ensure_ascii=False, indent=1)
    sub = os.path.basename(batch.rstrip("\\/"))

    def fusion_section(name):
        """该宫融合段嵌入：fusion_<宫名>.md 存在→内容+程序生成引用清单；否则 None。"""
        p = os.path.join(fusion_dir, "fusion_%s.md" % name)
        if not os.path.isfile(p):
            return None
        with io.open(p, "r", encoding="utf-8") as f:
            body = f.read().strip()
        return body + "\n" + "\n".join(fusion_citation_lines(name, refs, slice_ids, sub))

    parts, total_slices, id_palaces, skipped, blessed, fused = [], 0, 0, [], [], []
    for name in PALACE_ORDER:
        with io.open(outputs[name], "r", encoding="utf-8") as f:
            text = f.read()
        concl = slice_conclusion(text, name)
        if concl is None:
            skipped.append(name)
            continue
        ids = slice_ids.get(name, [])
        if ids:
            total_slices += len(ids)
            id_palaces += 1
        cite = ("本宫引用切片（%d 片）：见批次 ctx（temp\\%s）" % (len(ids), sub)) if ids \
            else "本宫引用切片：见批次 ctx（temp\\%s；本宫无独立 slice_ids 记录）" % sub
        parts.append(cite + "\n" + concl + "\n")
        if name in blocks:
            parts.append("\n".join(blocks[name]) + "\n")
            blessed.append(name)
        if name in l2:
            parts.append("\n".join(l2[name]) + "\n")
        fus = fusion_section(name)
        if fus:
            parts.append(fus + "\n")
            fused.append(name)
    if skipped:
        print("错误：以下宫未找到「结论」节：%s" % "、".join(skipped))
        sys.exit(2)

    # 原局批次纳入第13段——提取「## 身宫 结论」节追加（仆役之后、核查节之前；缺文件则跳过）
    if "身宫" in outputs:
        with io.open(outputs["身宫"], "r", encoding="utf-8") as f:
            sg_text = f.read()
        sg_concl = slice_conclusion(sg_text, "身宫")
        if sg_concl:
            ids = slice_ids.get("身宫", [])
            cite = ("本宫引用切片（%d 片）：见批次 ctx（temp\\%s）" % (len(ids), sub)) if ids \
                else "本宫引用切片：见批次 ctx（temp\\%s；本宫无独立 slice_ids 记录）" % sub
            parts.append(cite + "\n" + sg_concl + "\n")
            if "身宫" in blocks:
                parts.append("\n".join(blocks["身宫"]) + "\n")
                blessed.append("身宫")
            if "身宫" in l2:
                parts.append("\n".join(l2["身宫"]) + "\n")
            fus = fusion_section("身宫")
            if fus:
                parts.append(fus + "\n")
                fused.append("身宫")
        else:
            print("警告：身宫 output 缺「结论」节，跳过第13段")

    check = ["", "## 核查记录（组装脚本骨架）",
             "- 引擎标识：ziwei-engine.js（本地排盘引擎，离线）",
             "- 派发统计：12/12 宫 output 落盘，结论汇总 12 宫齐全",
             "- 组装规则：assemble_report.py（结论汇总+引用行注入+核查节，宫序 %s）"
             % "命官财福迁疾田父夫子兄仆",
             "- 引用切片计数：%d/%d 宫有 slice_ids 记录、合计 %d 片（逐宫明细见各宫引用行）"
             % (id_palaces, len(PALACE_ORDER), total_slices)]
    check += verify_refs_block(refs)
    check.append(layer_stats_line(refs))
    check.append("")
    if blessed:
        check.append("- 往事为鉴：%s（verify_refs.json 盘型级一等证据，条件性插入）" % "、".join(blessed))
    if l2:
        check.append("- 星系/宫位参考（星系级·宫位级 同线参考级）：%s（条件性插入）" % "、".join(sorted(l2)))
    if mats:
        check.append("- 融合素材包：fusion_materials.json（%d 宫命中：%s）"
                     % (len(mats), "、".join(sorted(mats))))
    if fused:
        check.append("- 融合分析：%s（fusion_<宫名>.md+引用清单，成对嵌入）" % "、".join(fused))

    out_text = ""
    if args.head:
        with io.open(args.head, "r", encoding="utf-8") as f:
            out_text = f.read().rstrip() + "\n"
    out_text += "\n".join(parts) + "\n".join(check)

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(out_text)
    print("组装完成：%d 宫结论汇总 + 引用行 + 核查节（合计引用 %d 片；盘型级 %d 宫/星系·宫位 %d 宫/融合 %d 宫）-> %s（%d 字符）"
          % (len(parts), total_slices, len(blessed), len(l2), len(fused),
             args.out, len(out_text)))


if __name__ == "__main__":
    main()
