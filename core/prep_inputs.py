# -*- coding: utf-8 -*-
"""紫微斗数分宫分析输入生成器（全盘事实表 + 知识库全量注入）

读命盘 JSON（paipan.js 输出同构）与检索结果 ctx.json（retrieve.py 产出），
按 taxonomy.DESIRED_ORDER 为十二宫各生成一个 input_<序号两位>_<宫名>.md：
  【命盘信息】        该宫 context_text 原文
  【全盘事实表】      四化 / 本命格局核验 / 本宫三方四正星曜 / 六吉会照
  【知识库·…宫参考资料】  该宫 kb_context 全量（自带此头，超 80000 字符按整片边界截断）

格局核验函数已抽共享模块 geju.py（流盘链同源调用，单一真源）。

用法：
  python prep_inputs.py --pan pan.json --ctx ctx.json --outdir <dir>
"""

import json
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy import DESIRED_ORDER
from geju import (sihua_line, sha_stats_line, trine_block, six_lucky_line,
                  trine_zhi, at_tag, geju_lines)

MAX_KB_CHARS = 80000  # kb_context 超此线按整片边界截断
PIECE_MARK = '◆ '     # 知识库切片片头标记（同 retrieve.py build_palace_kb_context）

# 身宫性质判据（语料原文四象限框架，硬编码于模板）
SHENGONG_VERDICT = (
    "至于身宫，一般的说法是用来推断其人的后天发展。如果命宫吉，身宫亦吉，当然一生多顺遂；"
    "如果命宫吉，身宫不吉，则有如一块美玉，可能在雕琢时出毛病，因此也就容易减色；"
    "如果命宫不吉，身宫吉，则虽有如顽石，但碰到一位巧匠，亦可以雕成器；"
    "如果命宫不吉，身宫亦不吉，则有如朽木不可雕，人生自然减色，"
    "只能利用好的大限与流年，加以人事上的努力来补救。"
)


def build_shengong_input(pan, ctx):
    """第 13 份 input_13_身宫.md（身宫=第13宫位，与其他宫同流程）。
    身宫支取 pan.mingShen.shen；星曜/四化/煞曜取该支所在宫的引擎数据（同一方法），
    附身宫性质语料判据（四象限）+ 疾厄宫星系摘要（供身体互参）+ 语料切片。
    返回文件内容；盘缺身宫数据返回 None。"""
    shen_zhi = (pan.get('mingShen', {}) or {}).get('shen', '')
    if not shen_zhi:
        return None
    palace_to_zhi = {n: z for z, n in (pan.get('twelvePalaces', {}) or {}).items()}
    host = next((n for n, z in palace_to_zhi.items() if z == shen_zhi), None)
    if host is None or host.rstrip('宫') not in ctx:
        return None
    host_name = host.rstrip('宫')
    entry = ctx[host_name]
    ji_e = ctx.get('疾厄', {})
    L = [
        "【命盘信息·身宫（第13宫）】（身宫附于%s宫，本盘身宫支=%s；排盘程序核毕，直接采信勿再自推宫位关系）" % (host_name, shen_zhi),
        "身宫性质：判断一个人后天如何做事（做事风格/方式/执行力），并在一定程度上反映身体情况。",
        "",
        "【身宫星曜信息】（星曜/四化/煞曜——与十二宫同一方法从引擎数据取）",
        entry['context_text'].rstrip('\n'),
        "",
        "【全盘事实表】（身宫=%s宫支位，事实表按该宫位取）" % host_name,
        build_fact_sheet(pan, host_name, shen_zhi),
        "",
        "【疾厄宫星系摘要】（供身体互参）",
        ji_e.get('context_text', '（疾厄宫数据缺失）').rstrip('\n'),
        "",
        "【身宫性质判据】（语料原文——四象限框架，判身宫吉凶后与命宫吉凶对照套用）",
        SHENGONG_VERDICT,
        "四象限：命宫吉+身宫吉=一生多顺遂｜命宫吉+身宫不吉=如美玉，雕琢时可能出毛病，容易减色｜"
        "命宫不吉+身宫吉=如顽石，遇巧匠可雕成器｜命宫不吉+身宫不吉=如朽木不可雕，利用好大限流年+人事努力补救。",
        "",
        "【身宫分析方法】（与其他宫同流程：取星曜→检索语料→判吉凶→输出）",
        "- 主断：后天如何做事（做事风格/方式/执行力）——与官禄宫（先天事业格局）互补：官禄=先天格局，身宫=后天做事方式",
        "- 辅断：身体方面情况（与上方疾厄宫星系互参）",
        "- 套四象限框架须先判命宫与身宫各自吉凶（按星系配置，与其他宫判吉凶同一方法）",
        "",
        "【知识库·%s宫参考资料】（身宫附于该宫，星系语料同源）" % host_name,
        clamp_kb(entry['kb_context']),
    ]
    return "\n".join(L) + "\n"


# ═════════════════════════════════════
#  全盘事实表
# ═════════════════════════════════════

def build_fact_sheet(pan, name, zhi):
    ming_zhi = next(z for z, n in (pan.get('twelvePalaces', {}) or {}).items() if n == '命宫')
    mq = trine_zhi(ming_zhi)
    lines = [
        "【全盘事实表】（排盘程序核毕，分析时直接采信，勿再自行推断宫位关系）",
        sihua_line(pan),
    ]
    lines += geju_lines(pan, name, zhi)
    lines += [
        f"  - 禄存@{at_tag(pan, (pan.get('allStarMap', {}) or {}).get('禄存', '?'))}（供对拱判断）",
        sha_stats_line(pan, mq),
    ]
    lines += trine_block(pan, name, zhi)
    lines.append(six_lucky_line(pan, trine_zhi(zhi)))
    return "\n".join(lines) + "\n"


# ═════════════════════════════════════
#  kb_context 整片截断
# ═════════════════════════════════════

def clamp_kb(kb):
    """超 MAX_KB_CHARS 时按整片边界截断（片以 '◆ ' 行起始，不切半片），尾部注明保留片数"""
    if len(kb) <= MAX_KB_CHARS:
        return kb
    lines = kb.split('\n')
    starts = [i for i, ln in enumerate(lines) if ln.startswith(PIECE_MARK)]
    if not starts:
        return kb
    pieces = []
    for k, a in enumerate(starts):
        b = starts[k + 1] if k + 1 < len(starts) else len(lines)
        pieces.append('\n'.join(lines[a:b]) + '\n')
    head = '\n'.join(lines[:starts[0]]) + '\n'
    total, kept = len(head), 0
    for p in pieces:
        if total + len(p) > MAX_KB_CHARS:
            break
        total += len(p)
        kept += 1
    return head + ''.join(pieces[:kept]) + f"\n已截断：保留前 {kept} 片\n"


# ═════════════════════════════════════
#  CLI
# ═════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description='紫微分宫分析输入生成器（事实表+全量知识库）')
    ap.add_argument('--pan', required=True, help='命盘 JSON 路径（paipan.js 输出格式）')
    ap.add_argument('--ctx', required=True, help='检索结果 ctx.json 路径（retrieve.py 产出）')
    ap.add_argument('--outdir', required=True, help='输出目录')
    args = ap.parse_args()

    with open(args.pan, 'r', encoding='utf-8') as f:
        pan = json.load(f).get('pan', {})
    with open(args.ctx, 'r', encoding='utf-8') as f:
        ctx = json.load(f)

    palace_to_zhi = {n: z for z, n in (pan.get('twelvePalaces', {}) or {}).items()}
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    for idx, name in enumerate(DESIRED_ORDER, 1):
        zhi = palace_to_zhi.get(name) or palace_to_zhi.get(name.rstrip('宫'))
        if not zhi:
            raise SystemExit(f"命盘缺少 {name} 宫")
        entry = ctx[name]
        content = (
            "【命盘信息】\n"
            + entry['context_text']
            + "\n"
            + build_fact_sheet(pan, name, zhi)
            + "\n"
            + clamp_kb(entry['kb_context'])
        )
        fname = f"input_{idx:02d}_{name}.md"
        with open(os.path.join(outdir, fname), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        print(f"{fname}\t{len(content)} 字符")

    # 第 13 份：身宫（原局批次专有）
    sg = build_shengong_input(pan, ctx)
    if sg is None:
        print("警告：盘缺身宫数据（mingShen.shen），跳过 input_13_身宫.md")
    else:
        sg_fname = "input_13_身宫.md"
        with open(os.path.join(outdir, sg_fname), 'w', encoding='utf-8', newline='\n') as f:
            f.write(sg)
        print(f"{sg_fname}\t{len(sg)} 字符")
    print(f"共 {len(DESIRED_ORDER) + (sg is not None)} 个文件 -> {args.outdir}")


if __name__ == '__main__':
    main()
