# -*- coding: utf-8 -*-
"""完整宫位深挖九维度自动提取。

用法：
  palace_extract.py --pan pans/<命主名>.json --level liuri --date 2026-10-22 --palace 财帛
  [--person <命主名>]（生成批次时的对象名，缺省=盘文件名；批次已存在则直接解析不生成）

流程：批次目录不存在→子进程调 core/liupan.py --outdir 生成（约30秒）；
     存在→定位 input_<序号>_<宫名>.md →解析九维度→stdout 结构化摘要（约5秒）。
零第三方依赖（纯标准库）。
"""
import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.dirname(HERE)            # verify\
SKILL_ROOT = os.path.dirname(BIN)      # ziwei-analyze\
LIUPAN = os.path.join(SKILL_ROOT, 'core', 'liupan.py')

LEVEL_TOPIC = {'daxian': 'Daxian', 'liunian': 'Liunian', 'liuyue': 'Liuyue',
               'liuri': 'Liuri', 'liushi': 'Liushi'}
MAIN_STARS = set('紫微天机太阳武曲天同廉贞天府太阴贪狼巨门天相天梁七杀破军')
AUX_LUCK = ['左辅', '右弼', '文昌', '文曲', '天魁', '天钺']
SHA = ['擎羊', '陀罗', '火星', '铃星', '地空', '地劫']
ZHI = '子丑寅卯辰巳午未申酉戌亥'


def zero_root():
    """读 anchors.json 的 ZERO_ROOT（与 core/make.py 同源口径）。"""
    cur = SKILL_ROOT
    while True:
        path = os.path.join(cur, 'anchors.json')
        if os.path.isfile(path):
            try:
                import json
                with open(path, encoding='utf-8') as f:
                    val = json.load(f).get('ZERO_ROOT')
                if val:
                    return val
            except (OSError, ValueError):
                return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def find_existing_batch(level, date, palace):
    """扫已有批次目录（anchors 可用时）：已有含该宫 input 的同层同日期批次→返回其 input 路径。"""
    root = zero_root()
    if not root:
        return None
    pat = os.path.join(root, 'output', '*',
                       LEVEL_TOPIC[level], 'temp', date, 'input_*_%s.md' % palace)
    hits = glob.glob(pat)
    return sorted(hits)[0] if hits else None


def generate_batch(pan, level, date, person):
    """批次不存在→调 liupan.py --outdir 生成，返回本脚本视角的 input 路径。"""
    cmd = [sys.executable, LIUPAN, '--pan', pan, '--level', level,
           '--date', date, '--outdir', '--person', person]
    env = dict(os.environ, PYTHONUTF8='1')
    r = subprocess.run(cmd, capture_output=True, env=env, cwd=SKILL_ROOT)
    print(r.stdout.decode('utf-8', 'replace').strip())
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
        sys.exit('错误：liupan.py 批次生成失败')


def split_sections(text):
    """按【XX】节标题切块（input 文件节标题行以【开头）。"""
    sections = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r'^【([^】]+)】', line.strip())
        if m:
            cur = m.group(1)
            sections.setdefault(cur, [])
        if cur is not None:
            sections[cur].append(line)
    return {k: '\n'.join(v) for k, v in sections.items()}


def first_line(sections, key, prefix):
    for line in sections.get(key, '').splitlines():
        if line.strip().startswith(prefix):
            return line.strip()
    return ''


def parse_stars(seg):
    """'紫微(旺)、七杀(平)' → [('紫微','旺'), ('七杀','平')]；纯名不带亮度→亮度''。"""
    out = []
    for part in re.split(r'[、，,]', seg):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'(.+?)[（(](.+?)[）)]$', part)
        out.append((m.group(1), m.group(2)) if m else (part, ''))
    return out


def extract(input_path, level, date, palace):
    with open(input_path, encoding='utf-8') as f:
        text = f.read()
    sec = split_sections(text)

    # —— 宫内星系：本层盘·X宫星曜信息头 + 内层【X宫·支】 + 主星/辅曜/杂曜三行 ——
    # （内层【宫·支】行也是【开头，不能靠节切块——直接全文正则定位）
    star_m = re.search(r'【本层盘·%s宫星曜信息】[^\n]*\n【%s宫·(\w)】\n((?:[^\n]*\n)+?)(?=\n|\Z)'
                       % (palace, palace), text)
    if not star_m:
        sys.exit('错误：input 中未定位到【本层盘·%s宫星曜信息】块' % palace)
    zhi = star_m.group(1)
    rows = {}
    for ln in star_m.group(2).splitlines():
        m = re.match(r'(?:- )?(主星|辅曜|煞曜|杂曜|四化)：(.*)', ln.strip())
        if m:
            rows[m.group(1)] = m.group(2)
    mains = parse_stars(rows.get('主星', ''))
    auxs = parse_stars(rows.get('辅曜', ''))
    shas = parse_stars(rows.get('煞曜', ''))
    zas = parse_stars(rows.get('杂曜', ''))
    star_sihua = rows.get('四化', '')
    in_palace = [n for n, _ in mains + auxs + shas + zas]

    # —— 三方四正会照节：本宫/对宫/三合宫支与星系 + 六吉会照 + 四化会入 ——
    sanfang = sec.get('该宫三方四正会照', '')
    hdr = re.search(r'三方四正（对宫(\w)、三合([\w、与]+)）', sanfang)
    pal_rows = re.findall(r'^\s*-?\s*(\w{1,3})\[(\w)\]：(.+)$', sanfang, re.M)
    zhi_pal = {z: (p, s.strip()) for p, z, s in pal_rows}
    dgang = duigong = None
    sanhe = []
    if hdr:
        dgang = hdr.group(1)
        duigong = zhi_pal.get(dgang)
        sanhe = [z for z in re.findall(r'\w', hdr.group(2)) if z in ZHI]

    # —— ①主星（无主星→借对宫）——
    if mains:
        s1 = '、'.join('%s（%s）' % (n, b) if b else n for n, b in mains)
        s1 += ' 同宫' if len(mains) > 1 else ' 独坐' if len(mains) == 1 else ''
    else:
        s1 = '无主星，借对宫%s（%s）%s' % (dgang or '?', duigong[0] if duigong else '?',
                                        duigong[1] if duigong else '?')

    # —— ②四化（本层天干四化+是否落本宫/会照）——
    gan_line = first_line(sec, '本层命盘信息', '- 本层天干：')
    sihua = re.findall(r'化([禄权科忌])([\w]+)@(\w)（([\w]+)）', gan_line)
    parts = []
    for hua, star, z, pg in sihua:
        loc = '坐本宫' if z == zhi else (
            '会照本宫三方四正' if re.search(r'%s@%s.*会入' % (star, z), sanfang) else '@%s（%s）' % (z, pg))
        parts.append('%s化%s%s' % (star, hua, loc))
    s2 = '；'.join(parts) if parts else '本层四化不涉本宫星系'
    s2 = '（本层%s干）%s' % (re.search(r'天干：(\w)', gan_line).group(1) if re.search(r'天干：(\w)', gan_line) else '?', s2)
    if star_sihua:
        s2 += '；宫内标注：%s' % star_sihua

    # —— ③辅星/吉星：同宫 + 六吉会照 ——
    liuhui = first_line(sec, '该宫三方四正会照', '- 六吉会照：')
    same = [n for n in AUX_LUCK if n in in_palace]
    s3 = ('、'.join(same) + ' 同宫') if same else '无同宫辅吉'
    if liuhui:
        s3 += '；' + liuhui.lstrip('- ')

    # —— ④煞星：同宫煞（含流曜煞）+ 夹宫煞（格局核验）——
    geju = sec.get('本层格局核验', '')
    same_sha = [n for n in SHA if n in in_palace]
    liuyao = first_line(sec, '流曜叠化', '- 本宫（%s）流曜：' % zhi)
    liu_sha = [n for n in SHA if n in liuyao]
    jia = [m for m in re.findall(r'(羊陀夹|火铃夹|空劫夹)：成立', geju)]
    s4_parts = []
    if same_sha:
        s4_parts.append('、'.join(same_sha) + ' 同宫')
    if liu_sha:
        s4_parts.append('、'.join(liu_sha) + ' 落本宫（流曜）')
    if not same_sha and not liu_sha:
        s4_parts.append('无同宫煞')
    if jia:
        s4_parts.append('；'.join(jia) + ' 相夹')
    s4 = '；'.join(s4_parts)

    # —— ⑤杂曜 ——
    s5 = '、'.join(n for n, _ in zas) if zas else '无'

    # —— ⑥三方四正 ——
    rows = []
    if dgang and duigong:
        rows.append('对宫%s（%s）%s' % (dgang, duigong[0], duigong[1]))
    for z in sanhe:
        if z != dgang and z in zhi_pal and z != zhi:
            p, s = zhi_pal[z]
            rows.append('三合%s（%s）%s' % (z, p, s))
    s6 = '；'.join(rows) if rows else '未解析到'

    # —— ⑦流曜叠化 ——
    s7 = liuyao.split('：', 1)[-1].strip() if '：' in liuyao else '本宫无流曜落宫'
    if not liuyao:
        s7 = '（%s 层不适用/未排）' % level

    # —— ⑧十二神 ——
    shen = first_line(sec, '该宫十二神定位', '- 本宫%s' % zhi) or \
        first_line(sec, '该宫十二神定位', '- 本宫')
    s8 = shen.split('：', 1)[-1].strip() if '：' in shen else '未解析到'

    # —— ⑨化性传染 ——
    chuan = first_line(sec, '流曜叠化', '- 四化传染：')
    s9 = chuan.split('：', 1)[-1].strip() if '：' in chuan else '无四化传染（本层四化之星非流曜型或不落）'

    print('【九维度摘要】%s宫（%s）——%s %s  （源：%s）'
          % (palace, zhi, date, level, os.path.relpath(input_path, zero_root() or SKILL_ROOT)))
    print('①主星：%s' % s1)
    print('②四化：%s' % s2)
    print('③辅星：%s' % s3)
    print('④煞星：%s' % s4)
    print('⑤杂曜：%s' % s5)
    print('⑥三方四正：%s' % s6)
    print('⑦流曜：%s' % s7)
    print('⑧十二神：%s' % s8)
    print('⑨化性传染：%s' % s9)


def main():
    ap = argparse.ArgumentParser(description='九维度自动提取（完整宫位深挖）')
    ap.add_argument('--pan', required=True)
    ap.add_argument('--level', required=True, choices=list(LEVEL_TOPIC))
    ap.add_argument('--date', required=True)
    ap.add_argument('--palace', required=True)
    ap.add_argument('--person', default=None, help='批次对象名（生成批次时用，缺省=盘文件名）')
    args = ap.parse_args()

    path = find_existing_batch(args.level, args.date, args.palace)
    if not path:
        person = args.person or os.path.splitext(os.path.basename(args.pan))[0]
        generate_batch(args.pan, args.level, args.date, person)
        path = find_existing_batch(args.level, args.date, args.palace)
    if not path:
        sys.exit('错误：批次生成后仍未找到 input（宫名=%s 是否十二宫之一）' % args.palace)
    extract(path, args.level, args.date, args.palace)


if __name__ == '__main__':
    main()
