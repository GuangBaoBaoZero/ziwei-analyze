# -*- coding: utf-8 -*-
"""theory 装配半固化脚本（方案 v1.5 件6）。

输入 --person --date --category --batch-dir（当日 temp）→ 程序化截取对应宫
input_XX_<宫>.md 的三层并标 / [主]行运判语块 / 语料引文（「」≥10字，逐字
截取禁改写），生成 theory ①②③段骨架 + ④段占位（人工填写标记），输出到
stdout 或 --out 文件。

串盘闸兼容：②段三层并标引文含「流日盘·X=」，X 须与 --category 类目映射宫
一致（CATEGORY_PALACE_MAP；不一致即报错退出，防错宫切片串盘）。

用法：
  python assemble_theory.py --person <person> --date <YYYY-MM-DD> --category 交易盈亏 --batch-dir <temp目录> [--out theory.txt]
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'verify', 'bin'))
from common import CATEGORIES, CATEGORY_PALACE_MAP  # noqa: E402

PLACEHOLDER_MARK = '【占位'          # 人工填写标记前缀
SECTION4_MARK = '【④段占位——人工填写'


def find_input(batch_dir, palace):
    """定位宫位切片 input_XX_<宫>.md（与 append.load_batch_input 同匹配规则）。"""
    names = [palace, palace.rstrip('宫'), palace + '宫']
    for path in sorted(glob.glob(os.path.join(batch_dir, 'input_*.md'))):
        stem = os.path.splitext(os.path.basename(path))[0]
        if any(stem.endswith('_' + n) for n in names):
            return path
    return None


def grab_section(text, header_re, end_re=r'^【'):
    """截取【头】节正文：header_re 命中行之后、到下一个 【 节头（或文尾）。"""
    m = re.search(header_re, text, re.M)
    if not m:
        return None
    tail = text[m.end():]
    nxt = re.search(end_re, tail, re.M)
    return tail[:nxt.start()] if nxt else tail


def extract_sandiao(section):
    """三层并标节 → 事象层行（去 '- ' 前缀，保留「流日盘·X=…」整行）。"""
    if not section:
        return None
    m = re.search(r'^\s*-\s*(事象层：.+)$', section, re.M)
    return m.group(1).strip() if m else None


def extract_main_xyun(text):
    """【行运匹配判语】节 → [主] 块判语正文（[主] 头行之后至 [辅]/提示/节尾）。"""
    sec = grab_section(text, r'^【行运匹配判语】')
    if not sec:
        return None
    m = re.search(r'^- \[主\].*$', sec, re.M)
    if not m:
        return None
    tail = sec[m.end():]
    nxt = re.search(r'^\s*(?:- \[辅\]|提示：)', tail, re.M)
    body = tail[:nxt.start()] if nxt else tail
    body = body.strip()
    return body or None


def pick_quote(block, min_len=10):
    """从文本块逐字取首个 ≥min_len 字符的完整句（按。；切分，带回句读）。"""
    if not block:
        return None
    clean = '\n'.join(ln for ln in block.splitlines() if not ln.strip().startswith(('◆', '⚠', '- ')))
    for sent in re.split(r'(?<=[。；])', clean.replace('\n', '')):
        s = sent.strip()
        if len(s) >= min_len:
            return s
    return None


def extract_yuke_quote(text):
    """语料引文：优先【版本判定素材】语料判据段，退【知识库·…参考资料】首句。"""
    sec = grab_section(text, r'^【版本判定素材】')
    if sec:
        m = re.search(r'语料判据[^\n]*\n', sec)
        if m:
            q = pick_quote(sec[m.end():])
            if q:
                return q
    kb = grab_section(text, r'^【知识库·')
    return pick_quote(kb) if kb else None


def extract_superior(text):
    """【上级分析结论参考】节 → 首个 ≥10 字句子（供③段级联引用占位）。"""
    sec = grab_section(text, r'^【上级分析结论参考】')
    if not sec:
        return None
    m = re.search(r'^- [^\n]+', sec, re.M)
    return pick_quote(m.group(0)[2:]) if m else None


def norm(s):
    return re.sub(r'\s+', '', s or '')


def main():
    ap = argparse.ArgumentParser(description='theory ①②③骨架+④占位 装配')
    ap.add_argument('--person', required=True)
    ap.add_argument('--date', required=True, help='YYYY-MM-DD')
    ap.add_argument('--category', required=True, choices=CATEGORIES)
    ap.add_argument('--batch-dir', required=True, help='当日批次 temp 目录（含 input_XX_<宫>.md）')
    ap.add_argument('--out', default=None, help='输出文件（缺省 stdout）')
    args = ap.parse_args()

    palace = CATEGORY_PALACE_MAP.get(args.category)
    if not palace:
        raise SystemExit('错误：类别 %s 无类目映射宫（天然宫位类之外须人工定宫后用 --category 对应宫切片手工装）' % args.category)
    batch_dir = os.path.abspath(args.batch_dir)
    path = find_input(batch_dir, palace)
    if not path:
        raise SystemExit('错误：批次目录未找到 %s 宫切片：%s' % (palace, batch_dir))
    text = open(path, encoding='utf-8').read()

    sandiao = extract_sandiao(grab_section(text, r'^【该宫三层并标】'))
    if not sandiao:
        raise SystemExit('错误：%s 切片缺【该宫三层并标】事象层行：%s' % (palace, path))
    # 串盘闸兼容：事象层「流日盘·X=」宫名须与类目映射宫一致
    m = re.search(r'流日盘·([^=「」/·\s]+?)=', sandiao)
    if not m or m.group(1).rstrip('宫') != palace.rstrip('宫'):
        got = m.group(1) if m else '（未匹配）'
        raise SystemExit('错误：串盘闸拦截——切片三层并标宫名「%s」与类目 %s 映射宫「%s」不符（找错切片？）' % (got, args.category, palace))

    xyun = extract_main_xyun(text)
    yuke = extract_yuke_quote(text)
    superior = extract_superior(text)

    # 逐字断言：所有引文（去空白）须存在于 input 原文
    for label, q in (('三层并标', sandiao), ('行运判语', xyun), ('语料引文', yuke), ('上级结论', superior)):
        if q and norm(q) not in norm(text):
            raise SystemExit('错误：%s 引文非逐字原文（内部断言失败）：%s…' % (label, q[:20]))

    sup_line = ''
    if superior:
        sup_line = ('\n上级级联引用：按上级已判定结论——「%s」……%s：结合上级结论校准本层判断方向。\n'
                    % (superior, PLACEHOLDER_MARK + '：展开上级结论与本宫盘面的衔接】'))

    theory = (
        '①宫位判定依据：命主 {person} 于 {date} 发生「{cat}」类事件，按类目映射（{cat}→{palace}宫）'
        '归{palace}宫，事象层锚点「{sandiao}」。{ph}：结合事件具体内容复核宫位归属，确认或改判并给依据】\n'
        '②结构原文+语料判据：三层并标「{sandiao}」；语料判据：「{yuke}」。{ph2}：可再补结构原文引用（四化配对/三方四正/流曜叠化节逐字截取）】\n'
        '③八要素推理链：行运判语：『{xyun}』——{phx}：按[主]判语展开——四化直断（紧邻上层+本层两层）、版本判定（结合三方四正）、'
        '吉凶定性与强度、本层事项级宜忌、十二神逐星推演、流曜叠化（三层共振/四化传染）、见星寻偶与星曜互射，每维度≥2句展开，'
        '判语内嵌条件回本层盘面核验后下断】\n'
        '{sup}'
        '④事件对照：{s4}：事件方向（应/不应/反）+力度（强/中/弱）+要素落位（事件对应盘面哪些星曜四化要素）】\n'
    ).format(person=args.person, date=args.date, cat=args.category, palace=palace,
             sandiao=sandiao, yuke=yuke or '（未取到——人工从知识库节逐字截取≥10字引用）',
             xyun=xyun or '（未取到——人工从【行运匹配判语】[主]块逐字截取）',
             sup=sup_line, ph=PLACEHOLDER_MARK, ph2=PLACEHOLDER_MARK, phx=PLACEHOLDER_MARK,
             s4=SECTION4_MARK)

    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(theory)
        print('已写入 %s（骨架：①②③已固化引文，④段与各占位待人工补全后走 append.py --theory 落账）' % args.out)
    else:
        sys.stdout.write(theory)
        sys.stdout.write('\n（骨架：①②③已固化引文，④段与各占位待人工补全后走 append.py --theory 落账）\n')


if __name__ == '__main__':
    main()
