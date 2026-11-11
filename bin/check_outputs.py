# -*- coding: utf-8 -*-
"""十二宫产出点检器（v2.10 批次2）

对 make.py outdir 内 output_01..12_*.md 逐份点检：
  ① 「## {宫名} 详细分析」与「## {宫名} 摘要/结论」两标题在位（均前缀匹配，
     容"（供整体汇总用）"等后缀；结论=流盘版标题，原局批仍用摘要）；
  ② 摘要节（摘要标题起至文件尾或下一 ##）中文字符数 800-1400；
  ③ 文件 >1KB。
输出 12 行 PASS/FAIL，全过 exit 0 否则 exit 1。

用法：python check_outputs.py --dir <outdir>
"""

import argparse
import glob
import os
import re
import sys

PALACE_ORDER = ['命宫', '官禄', '财帛', '福德', '迁移', '疾厄', '田宅', '父母',
                '夫妻', '子女', '兄弟', '仆役']
FILE_RE = re.compile(r'^output_(\d{2})_(.+)\.md$')
HAN_RE = re.compile(r'[\u4e00-\u9fff]')
# 内部工程标记检测：方法论版本号/批号/化性修正——泄露到用户面即 FAIL
ENG_MARK_RE = re.compile(r'v\d{4}-|批[A-Z]|化性修正')
# 越层判语关键词（越层泄露防护）：按被分析目录层级自动选择；
# 检测的是越层判语，级联注入的上级结论引用（如"上级流年分析已判…"）不含关键词、不误杀
LAYER_KEYWORDS = {
    'Yuanju': re.compile(r'流限经|流年[天守逢]|大限行|十岁后|二十岁后|三十岁后|四十岁后|五十岁后'),
    'Daxian': re.compile(r'本月|本月内|当日|今日'),
    'Liunian': re.compile(r'当日|今日|本日'),
    'Liuyue': re.compile(r'当日|今日|本日'),
    'Liuri': re.compile(r'此时辰|大限十年|此十年|本限内|流年全年|今年全年'),
}


def crossover_reasons(text, layer):
    """越层判语检测：只检"详细分析"与"摘要/结论"节——
    从首个 ## 标题起至文件尾（此前内容为盘面信息引用行，input 数据行可能含层名，不检）。
    layer = 被分析层级（LAYER_KEYWORDS 键，由目录名判定）；只检该层关键词集。"""
    if layer not in LAYER_KEYWORDS:
        return []
    m = re.search(r'^## ', text, re.M)
    if not m:
        return []  # 无分析节，标题检测另行 FAIL，此处不重复报
    hits = LAYER_KEYWORDS[layer].findall(text[m.start():])
    if hits:
        return [f'越层判语泄露：{"、".join(sorted(set(hits)))}']
    return []


def check_one(path, palace, no_shengong=False, check_shengong=False, layer=None):
    """单宫点检，返回 (ok, 原因描述)"""
    reasons = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        return False, f'读取失败：{e}'

    if os.path.getsize(path) <= 1024:
        reasons.append(f'文件 {os.path.getsize(path)}B ≤1KB')

    if no_shengong and '身宫' in text:
        reasons.append('流盘输出含身宫引用')

    if ENG_MARK_RE.search(text):
        reasons.append('含内部工程标记（%s）' % '、'.join(sorted(set(ENG_MARK_RE.findall(text)))))

    reasons.extend(crossover_reasons(text, layer))

    if check_shengong and palace == '身宫':
        # 第13段检测移至 output_13_身宫.md（见 main 尾部独立检查），此处不重复
        pass

    if not re.search(rf'^## {re.escape(palace)} 详细分析\s*$', text, re.M):
        reasons.append('缺「## %s 详细分析」标题' % palace)

    m = re.search(rf'^## {re.escape(palace)} (?:摘要|结论).*$', text, re.M)
    if not m:
        reasons.append('缺「## %s 摘要/结论」标题' % palace)
    else:
        tail = text[m.end():]
        nxt = re.search(r'^## ', tail, re.M)
        summary = tail[:nxt.start()] if nxt else tail
        n = len(HAN_RE.findall(summary))
        if not 800 <= n <= 1400:
            reasons.append(f'摘要中文字数 {n} 不在 800-1400')

    return (not reasons), '；'.join(reasons)


def check_report_pairing(path):
    """报告层融合段成对断言（往事为鉴二次分析 v1.4）：报告中「【融合分析】」与
    「【引用清单】」出现次数必须相等（有融合段必有清单、反之亦然）。"""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    n_fus = text.count('【融合分析】')
    n_cit = text.count('【引用清单】')
    if n_fus == n_cit:
        print(f'PASS 报告融合段成对 ({n_fus} 对)')
        return True
    print(f'FAIL 报告融合段成对 融合分析×{n_fus} ≠ 引用清单×{n_cit}')
    return False


def main():
    ap = argparse.ArgumentParser(description='十二宫产出点检（标题/摘要字数/文件大小）')
    ap.add_argument('--dir', default=None, help='make.py 的 outdir（含 output_01..12_*.md）')
    ap.add_argument('--report', default=None,
                    help='报告层模式：检组装报告融合段⇔引用清单成对（与 --dir 二选一）')
    ap.add_argument('--no-shengong', action='store_true',
                    help='流盘链后验：检测 output 含"身宫"字样即 FAIL（流盘禁身宫引用）')
    ap.add_argument('--check-shengong', action='store_true',
                    help='原局链后验：output_13_身宫.md 须存在且含"身宫"分析段（≥800中文字）')
    args = ap.parse_args()
    if not args.dir and not args.report:
        ap.error('--dir 与 --report 必给其一')
    if args.report:
        sys.exit(0 if check_report_pairing(os.path.abspath(args.report)) else 1)
    # 原局链后验自动启用（目录含 Yuanju 且未显式 --no-shengong）
    absdir = os.path.abspath(args.dir)
    if not args.no_shengong and 'Yuanju' in absdir:
        args.check_shengong = True
    # 越层判语检测：按目录名判定被分析层级（无匹配层级目录则不检）
    layer = next((k for k in LAYER_KEYWORDS if k in absdir), None)

    files = {}
    inputs = {}
    for p in glob.glob(os.path.join(args.dir, '*.md')):
        mo = re.match(r'^input_(\d{2})_.+\.md$', os.path.basename(p))
        if mo:
            inputs[int(mo.group(1))] = p
    for p in glob.glob(os.path.join(args.dir, 'output_*.md')):
        m = FILE_RE.match(os.path.basename(p))
        if m:
            files[int(m.group(1))] = p

    all_ok = True
    for idx, palace in enumerate(PALACE_ORDER, 1):
        path = files.get(idx)
        if not path:
            print(f'FAIL {palace} 缺文件 output_{idx:02d}_{palace}.md')
            all_ok = False
            continue
        ok, why = check_one(path, palace, no_shengong=args.no_shengong,
                            check_shengong=args.check_shengong, layer=layer)
        # 级联引用检测（默认启用）：input 含上级结论参考 → output 须引用"上级"
        in_path = inputs.get(idx)
        if in_path:
            try:
                with open(in_path, 'r', encoding='utf-8') as f:
                    in_text = f.read()
                if '上级分析结论参考' in in_text:
                    with open(path, 'r', encoding='utf-8') as f:
                        out_text = f.read()
                    if out_text.count('上级') < 1:
                        ok = False
                        why += '；' if why else ''
                        why += 'input 含上级结论但 output 未引用上级结论'
            except OSError:
                pass
        print(('PASS' if ok else 'FAIL') + f' {palace}' + ('' if ok else f' {why}'))
        all_ok = all_ok and ok

    # --check-shengong（原局链）检测第13段——output_13_身宫.md 存在且含"身宫"分析段（≥800中文字）
    if args.check_shengong:
        sg_path = files.get(13)
        if not sg_path:
            print('FAIL 身宫 缺文件 output_13_身宫.md')
            all_ok = False
        else:
            with open(sg_path, 'r', encoding='utf-8') as f:
                sg_text = f.read()
            sg_reasons = []
            if '身宫' not in sg_text:
                sg_reasons.append('输出不含"身宫"论述')
            sg_reasons.extend(crossover_reasons(sg_text, layer))
            m = re.search(r'^## 身宫 (?:摘要|结论).*$', sg_text, re.M)
            if not m:
                sg_reasons.append('缺「## 身宫 摘要/结论」标题')
            else:
                tail = sg_text[m.end():]
                nxt = re.search(r'^## ', tail, re.M)
                summary = tail[:nxt.start()] if nxt else tail
                n = len(HAN_RE.findall(summary))
                if n < 800:
                    sg_reasons.append(f'摘要中文字数 {n} <800')
            ok = not sg_reasons
            print(('PASS' if ok else 'FAIL') + ' 身宫' + ('' if ok else ' ' + '；'.join(sg_reasons)))
            all_ok = all_ok and ok

    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
