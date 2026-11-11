#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""流盘排布引擎（方法论工程转译，统一架构）

五层参数化：daxian / liunian / liuyue / liuri / liushi。
输出：流盘 JSON（stdout 或 --out）+ 叠盘事实表 Markdown（--facttable）。

口径来源（全量回归引擎验证）：排盘一律用引擎，禁自写排布——
- 层命宫/层干支/四化/流层十二神/流昌流曲/大限归属：全部子进程调
  node engine/paipan.js --liupan（引擎正稿函数：斗君法流月/流日顺数农历日/
  流时顺数时辰/流年博士含顺逆/getSiHua/getTaiSuiTwelve/getJiangQian/getLiuChangQu/
  getYunNumByLiuNianDate/getDaXian/getDaXianStartTime）；
- 层十二宫重贴：机械贴标签（宫名映射），命宫支来自引擎；
- 长生十二神随原局五行局，流层不重排（口径注明）。

用法：
  python liupan.py --pan pans/<命主名>.json --level liuri --date 2026-10-21 [--out o.json] [--facttable t.md]
  python liupan.py --pan pans/<命主名>.json --level daxian --seq 3
  python liupan.py --pan pans/<命主名>.json --level liunian --year 2026
  python liupan.py --pan pans/<命主名>.json --level liuyue --month 2026-10
  python liupan.py --pan pans/<命主名>.json --level liushi --date 2026-10-21 --hour 午
批次模式（--outdir 开关，十二宫派发链；批次目录按行运日期命名）：
  python liupan.py --pan pans/<命主名>.json --level liuri --date 2026-10-21 --outdir [--person <命主名>]
  落 <ZERO_ROOT>\output\<person>\<Topic>\temp\<行运日期>\（liuri=YYYY-MM-DD /
  liushi=YYYY-MM-DD-时辰 / liuyue=YYYY-MM / liunian=YYYY / daxian=第N限<起>-<讫>；同标的重做=覆盖；
  anchors 缺=技能 output\），
  产出 pan_<层>_<参数>.json + facttable.md + 12 份 input_<01-12>_<宫名>.md + dispatch_liupan.workflow.js。
"""
import argparse
import copy
import itertools
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
PAIPAN = os.path.join(SKILL_ROOT, 'engine', 'paipan.js')

sys.path.insert(0, HERE)
from taxonomy import MAIN_STARS

ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
GAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
JIAZI = [GAN[i % 10] + ZHI[i % 12] for i in range(60)]

LEVEL_ORDER = ['origin', 'daxian', 'liunian', 'liuyue', 'liuri', 'liushi']
LEVEL_CN = {'origin': '原局', 'daxian': '大限', 'liunian': '流年', 'liuyue': '流月',
            'liuri': '流日', 'liushi': '流时'}
LEVEL_TOPIC = {'daxian': 'Daxian', 'liunian': 'Liunian', 'liuyue': 'Liuyue',
               'liuri': 'Liuri', 'liushi': 'Liushi'}
DISPATCH_LIUPAN_TPL = os.path.join(SKILL_ROOT, 'bin', 'dispatch_liupan.workflow.js')


def engine_liupan(pan_path, level, date, hour=None, minute=None, seq=None):
    """子进程调 paipan.js --liupan：层命宫/干支/四化/流层十二神/流昌流曲/大限，全引擎算。"""
    cmd = ['node', PAIPAN, '--liupan', '--pan', pan_path, '--level', level, '--date', date]
    if hour is not None:
        cmd += ['--hour', str(hour)]
    if minute is not None:
        cmd += ['--minute', str(minute)]
    if seq is not None:
        cmd += ['--seq', str(seq)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                       cwd=SKILL_ROOT, encoding='utf-8')
    if r.returncode != 0:
        raise RuntimeError('paipan.js --liupan 失败: %s' % r.stderr.strip())
    return json.loads(r.stdout)


def stars_by_gong(pan):
    """allStarMap（星→支）反转为 支→[星]，保持 allStarMap 原序。"""
    by = {z: [] for z in ZHI}
    for star, zhi in pan.get('allStarMap', {}).items():
        if zhi in by:
            by[zhi].append(star)
    return by


def palace_direction(pan):
    """从原盘反推宫名排列方向：兄弟宫支相对命宫支的步进（±1 mod 12）。"""
    tp = pan['twelvePalaces']
    ming = pan['mingShen']['ming']
    xiong = next(z for z, name in tp.items() if name == '兄弟')
    step = (ZHI.index(xiong) - ZHI.index(ming)) % 12
    return 1 if step == 1 else -1, ming


def palace_name_order(pan):
    """命宫起、按排列方向的十二宫名序（命→兄弟→夫妻→…）。"""
    tp = pan['twelvePalaces']
    step, ming = palace_direction(pan)
    return [tp[ZHI[(ZHI.index(ming) + i * step) % 12]] for i in range(12)]


def relayout_palaces(pan, ming_zhi):
    """层十二宫重布：宫支不动，以层命宫支贴"命宫"，按原盘方向套宫名序。"""
    step, _ = palace_direction(pan)
    names = palace_name_order(pan)
    return {ZHI[(ZHI.index(ming_zhi) + i * step) % 12]: names[i] for i in range(12)}


def si_hua_from_engine(engine_sihua):
    """引擎 getSiHua 输出直采（{hua:{star,gong}}）。"""
    return engine_sihua or {}


def flow_twelve_gods_from_engine(pan, flow_gods):
    """流层十二神：岁建/将前/博士全引擎流年支/流年干版；长生随原局五行局不重排。"""
    return {
        'taiSuiTwelve': flow_gods['taiSuiTwelve'],
        'jiangQian': flow_gods['jiangQian'],
        'boShi': flow_gods['boShi'],
        'changShengTwelve': pan['changShengTwelve'],  # 随原局五行局，流层不重排
    }


LIUYAO_STARS = ['文昌', '文曲', '擎羊', '陀罗', '禄存', '天马', '天魁', '天钺']


def hui_zhao(z1, z2):
    """会照判定（三方四正）：三合（地支差 4 或 8）+ 对宫（差 6）。"""
    d = abs(ZHI.index(z1) - ZHI.index(z2)) % 12
    return d in (4, 6, 8)


def liuyao_scope_chain(chain):
    """流曜三层化：流曜只看 本层+紧邻上层+原局 三层（大限两层=原局+大限）。
    口径：当前层+紧邻上层+原局——永远三层，禁扩展为全部层。"""
    seen = set()
    out = []
    for l in [chain[0]] + chain[-2:]:
        if l['level'] not in seen:
            seen.add(l['level'])
            out.append(l)
    return out


def origin_liuyao(pan):
    """原局层流曜八曜：直接取盘面 allStarMap。"""
    asm = pan.get('allStarMap', {})
    return {s: asm.get(s) for s in LIUYAO_STARS if asm.get(s)}


def build_layer(level, pan, ming_zhi, level_gan, label, engine=None,
                flow_year=None, with_gods=False):
    liuyao = origin_liuyao(pan) if level == 'origin' else (engine or {}).get('liuYao', {}).get(level)
    return {
        'level': level,
        'label': label,
        'level_gan': level_gan,
        'ming_zhi': ming_zhi,
        'palaces': relayout_palaces(pan, ming_zhi),
        'sihua': si_hua_from_engine((engine or {}).get('sihua', {}).get(level)),
        'twelve_gods': flow_twelve_gods_from_engine(pan, engine['flowGods'])
        if (with_gods and engine) else None,
        'liuyao': liuyao,
    }


def origin_layer(pan):
    return build_layer('origin', pan, pan['mingShen']['ming'], pan['siZhu']['year'][0],
                       '%s年生原局' % pan['siZhu']['year'],
                       engine={'sihua': {'origin': pan.get('siHua') or {}}, 'flowGods': None})


def _check_daxian(eng, ctx):
    dx = eng.get('daxian') or {}
    if 'zhi' not in dx:
        raise RuntimeError('%s：引擎判未入限（%s），无大限层' % (ctx, dx.get('note') or dx.get('yunNum')))
    return dx


def compute_chain(level, pan, pan_file, args):
    """按层组链：排布数据全部来自引擎 --liupan 查询结果。返回 [origin, ..., 本层]。"""
    chain = [origin_layer(pan)]

    # 各层查询用的代表日：流年取年中（6-15，农历年内安全）；流月取当月 15 日；
    # 流日/流时用当日；流时另传时支序（午=12，引擎按 (hour+1)/2 归时辰）
    def hour_num(zhi):
        return ZHI.index(zhi) * 2

    if level == 'daxian':
        eng = engine_liupan(args.pan, 'daxian', '%04d-06-15' % pan_file['birth']['year'],
                            seq=args.seq)
        dx = eng['daxian']
        chain.append(build_layer('daxian', pan, dx['zhi'], dx['gan'],
                                 '第%d限（%s宫，%s岁）' % (dx['seq'], dx['zhi'], dx['range']),
                                 engine=eng))
        chain[-1]['dx_range'] = dx['range']
        return chain, None

    if level == 'liunian':
        eng = engine_liupan(args.pan, 'liunian', '%04d-06-15' % args.year)
        dx = _check_daxian(eng, '%d流年' % args.year)
        gz = eng['lunar']['liuNianGZ']
        chain.append(build_layer('daxian', pan, dx['zhi'], dx['gan'],
                                 '第%d限（%s宫）' % (dx['seq'], dx['zhi']),
                                 engine=eng))
        chain.append(build_layer('liunian', pan, gz[1], gz[0], '%s流年' % gz, engine=eng))
        return chain, args.year

    if level == 'liuyue':
        y, m = parse_ym(args.month)
        eng = engine_liupan(args.pan, 'liuyue', '%04d-%02d-15' % (y, m))
        chain += _liuyue_chain(pan, eng)
        return chain, y

    if level == 'liuri':
        eng = engine_liupan(args.pan, 'liuri', args.date)
        chain += _liuyue_chain(pan, eng)
        chain += _liuri_layer(pan, eng, with_gods=True)
        return chain, int(args.date[:4])

    if level == 'liushi':
        eng = engine_liupan(args.pan, 'liushi', args.date, hour=hour_num(args.hour))
        chain += _liuyue_chain(pan, eng)
        chain += _liuri_layer(pan, eng, with_gods=True)
        hgz = eng['ganZhi']['liuShi']
        chain.append(build_layer('liushi', pan, eng['mingZhi']['liushi'], hgz[0],
                                 '%s时流时' % hgz, engine=eng, with_gods=True))
        chain[-1]['hour_ganzhi'] = hgz
        return chain, int(args.date[:4])

    raise ValueError('未知 level: %s' % level)


def _liuyue_chain(pan, eng):
    """原局之上：大限 → 流年 → 流月（引擎 yunNum/流年干支/斗君流月命宫/五虎遁月干）。"""
    dx = _check_daxian(eng, '流月链')
    gz = eng['lunar']['liuNianGZ']
    ygz = eng['ganZhi']['liuYue']
    layers = [
        build_layer('daxian', pan, dx['zhi'], dx['gan'],
                    '第%d限（%s宫）' % (dx['seq'], dx['zhi']),
                    engine=eng),
        build_layer('liunian', pan, gz[1], gz[0], '%s流年' % gz, engine=eng),
        build_layer('liuyue', pan, eng['mingZhi']['liuyue'], ygz[0],
                    '%s年农历%s月流月' % (gz, eng['lunar']['effectiveLunarMonth']),
                    engine=eng),
    ]
    return layers


def _liuri_layer(pan, eng, with_gods):
    lay = build_layer('liuri', pan, eng['mingZhi']['liuri'],
                      eng['ganZhi']['liuRi'][0], '%s流日' % eng['ganZhi']['liuRi'],
                      engine=eng, with_gods=with_gods)
    lay['day_ganzhi'] = eng['ganZhi']['liuRi']
    return [lay]


def gz_short(year):
    return JIAZI[(year - 4) % 60]


def parse_ym(s):
    y, m = s.split('-')
    return int(y), int(m)


# ═════════════════════════════════════
#  叠盘事实表
# ═════════════════════════════════════

HUA_ORDER = ['禄', '权', '科', '忌']


def double_tag(up_h, cur_h):
    """同星双化命名（叠/转分离）：同象=叠X（两层力量增强）；变象=X转Y（上层=过程，本层=结果）。"""
    if up_h == cur_h:
        return '「叠%s」（同象两层力量增强）' % cur_h
    return '「%s转%s」（上层=过程，本层=结果）' % (up_h, cur_h)


def palace_zhi_of(layer, name):
    zhi_of = {n: z for z, n in layer['palaces'].items()}
    return zhi_of.get(name) or zhi_of.get(name.rstrip('宫'))


def gong_cell(sbg, z):
    stars = '、'.join(sbg[z]) if sbg[z] else '（空宫）'
    return '%s·%s' % (z, stars)


def fact_table(pan, chain):
    sbg = stars_by_gong(pan)
    cur, up = chain[-1], chain[-2]
    lines = []
    lines.append('# 叠盘事实表 — %s' % cur['label'])
    tishi = '、'.join('%s以%s为体' % (LEVEL_CN[chain[i]['level']], LEVEL_CN[chain[i - 1]['level']])
                      for i in range(2, len(chain)))
    lines.append('')
    lines.append('- 体用上下文：原局为体，' + (tishi if tishi else '大限以原局为体'))
    lines.append('- 层天干：%s（四化：%s）' % (
        cur['level_gan'],
        '、'.join('%s%s化%s' % (cur['sihua'][h]['star'], cur['sihua'][h]['gong'], h)
                  for h in HUA_ORDER if h in cur['sihua'])))
    lines.append('- 上层（%s）天干：%s（四化：%s）' % (
        up['label'], up['level_gan'],
        '、'.join('%s%s化%s' % (up['sihua'][h]['star'], up['sihua'][h]['gong'], h)
                  for h in HUA_ORDER if h in up['sihua'])))
    lines.append('- 本层命宫：%s宫（%s）；上层命宫：%s宫' % (
        cur['ming_zhi'], cur['palaces'][cur['ming_zhi']], up['ming_zhi']))

    # 上层四化对本层盘的直接作用（落宫一律抄引擎 chain sihua 原值，禁流曜反查）
    lines.append('')
    lines.append('## 上层四化落本层宫（直接作用）')
    for h in HUA_ORDER:
        if h in up['sihua']:
            e = up['sihua'][h]
            g = e['gong']
            lines.append('- %s%s化%s → 落本层【%s】（%s宫）' % (
                e['star'], e['gong'], h, cur['palaces'].get(g, g), g))

    # 双化标注（同星上下两层皆化；同象=双化X / 变象=X转Y）
    up_hua = {e['star']: h for h, e in up['sihua'].items()}
    cur_hua = {e['star']: h for h, e in cur['sihua'].items()}
    doubles = [s for s in cur_hua if s in up_hua]
    lines.append('')
    lines.append('## 同星双化（紧邻上层→本层）')
    if doubles:
        for s in doubles:
            lines.append('- %s：上层(%s)化%s + 本层(%s)化%s = %s' % (
                s, up['level_gan'], up_hua[s], cur['level_gan'], cur_hua[s],
                double_tag(up_hua[s], cur_hua[s])))
    else:
        lines.append('-（无同星双化）')
    # 十二宫三层并标（宫名纵叠：同名宫，各层盘各自的支与星系）
    from taxonomy import DESIRED_ORDER
    upup = chain[-3] if len(chain) >= 3 else None
    lines.append('')
    if upup:
        lines.append('## 十二宫三层并标（宫名纵叠：同一宫名，三层各层盘各自的支与星系）')
        lines.append('| 宫名 | 事象层(%s) | 基调层(%s) | 背景层(%s) |' % (
            cur['label'], up['label'], upup['label']))
        lines.append('|---|---|---|---|')
        for name in DESIRED_ORDER:
            lines.append('| %s | %s | %s | %s |' % (
                name, gong_cell(sbg, palace_zhi_of(cur, name)),
                gong_cell(sbg, palace_zhi_of(up, name)),
                gong_cell(sbg, palace_zhi_of(upup, name))))
    else:
        lines.append('## 十二宫两层并标（宫名纵叠：同一宫名，原局与大限各自的支与星系）')
        lines.append('| 宫名 | 本限层(%s) | 原局层(%s) |' % (cur['label'], up['label']))
        lines.append('|---|---|---|')
        for name in DESIRED_ORDER:
            lines.append('| %s | %s | %s |' % (
                name, gong_cell(sbg, palace_zhi_of(cur, name)),
                gong_cell(sbg, palace_zhi_of(up, name))))

    if cur.get('twelve_gods'):
        tg = cur['twelve_gods']
        lines.append('')
        lines.append('## 流层十二神定位（引擎 getTaiSuiTwelve/getJiangQian 起流年支、getLiuNianBoShi 起流年禄存含顺逆；长生随原局五行局）')
        for key in ('taiSuiTwelve', 'jiangQian', 'boShi'):
            items = '、'.join('%s%s' % (z, tg[key][z]) for z in ZHI)
            lines.append('- %s：%s' % (key, items))
        lines.append('- changShengTwelve（原局，随五行局不重排）：%s' % (
            '、'.join('%s%s' % (z, tg['changShengTwelve'][z]) for z in ZHI)))

    return '\n'.join(lines) + '\n'


# ═════════════════════════════════════
#  检索接入（复用既有索引，import 不改）
# ═════════════════════════════════════

def retrieve_for_layer(pan_file, pan, layer):
    """层命宫+三方四正各支按六十星系两级查语料；流日/流时另查十二神（按星名）。
    返回 {支: {palace: 本层宫名, slice_ids: [...]}} + twelve_god_hits。"""
    sys.path.insert(0, HERE)
    import retrieve
    kb = retrieve.load_kb_data()
    indexes = retrieve.build_indexes(kb)
    ming = ZHI.index(layer['ming_zhi'])
    # 三方四正：对宫、三合（命宫起 ±4、±6 支序——与原局对宫/三合同构，宫支固定）
    targets = [layer['ming_zhi'],
               ZHI[(ming + 4) % 12], ZHI[(ming + 8) % 12], ZHI[(ming + 6) % 12]]
    out = {}
    for z in targets:
        pinfo = retrieve.format_palace_context(pan_file, z)
        slices = retrieve.get_star_system_slices(indexes, pinfo)
        out[z] = {'palace': layer['palaces'][z],
                  'slice_ids': sorted({retrieve._slice_fp(s) for s in slices})}
    god_hits = {}
    if layer.get('twelve_gods'):
        for key in ('taiSuiTwelve', 'jiangQian', 'boShi'):
            for z, name in layer['twelve_gods'][key].items():
                for s in indexes['by_parent'].get(name, ()):
                    god_hits.setdefault(name, set()).add(retrieve._slice_fp(s))
    return {'star_system': out,
            'twelve_gods': {k: sorted(v) for k, v in god_hits.items()}}


# ═════════════════════════════════════
#  批次模式（--outdir，十二宫派发链）
# ═════════════════════════════════════

def level_param(level, args):
    """批次文件名里的行运参数段"""
    if level == 'daxian':
        return 'seq%d' % args.seq
    if level == 'liunian':
        return str(args.year)
    if level == 'liuyue':
        return args.month
    if level == 'liuri':
        return args.date
    return '%s-%s时' % (args.date, args.hour)


def tiyong_line(chain):
    return '、'.join('%s以%s为体' % (LEVEL_CN[chain[i]['level']], LEVEL_CN[chain[i - 1]['level']])
                     for i in range(1, len(chain)))


def layer_sihua_line(layer):
    parts = []
    for h in HUA_ORDER:
        if h in layer['sihua']:
            e = layer['sihua'][h]
            gong = e['gong']
            parts.append('化%s%s@%s（%s）' % (h, e['star'], gong, layer['palaces'].get(gong, gong)))
    return '、'.join(parts)


# fail-fast：渲染文本四化标注 vs 引擎 chain siHua 原值（星名+宫支+象），错位即拒出批次
_ANNO_AT = re.compile(r'化([禄权科忌])[：]?([\u4e00-\u9fff]{1,4})@([子丑寅卯辰巳午未申酉戌亥])')
_ANNO_ADHOC = re.compile(r'([\u4e00-\u9fff]{1,4})([子丑寅卯辰巳午未申酉戌亥])化([禄权科忌])')


def extract_sihua_annotations(text):
    """从渲染文本提取四化标注集 {(星, 宫支, 象)}——覆盖两类生成格式：
    「化X星@支」（sihuaLine/会照行）与「星+支化X」（facttable/input 天干行/落本层行）。
    两类均只扫本模块生成的行形（含"四化/层化/天干：/落本层"标记的行），防语料正文误报。"""
    got = set()
    for ln in text.split('\n'):
        if '四化' in ln or '层化' in ln:
            for m in _ANNO_AT.finditer(ln):
                got.add((m.group(2), m.group(3), m.group(1)))
        if '天干：' in ln or ' → 落本层' in ln:
            for m in _ANNO_ADHOC.finditer(ln):
                got.add((m.group(1), m.group(2), m.group(3)))
    return got


def verify_sihua_render(chain, texts, where='batch'):
    """fail-fast 自检：渲染标注逐星比对 chain siHua 引擎原值。
    任一标注三元组不在任何层的引擎原值集合中=错位，print 明细并 sys.exit(2) 拒绝出批次。"""
    expected = {(l['sihua'][h]['star'], l['sihua'][h]['gong'], h)
                for l in chain for h in HUA_ORDER if h in l['sihua']}
    for text in texts:
        bad = extract_sihua_annotations(text) - expected
        if bad:
            print('✗ 四化标注与引擎 chain siHua 原值不一致（%s）——拒绝出批次：' % where)
            for star, gong, hua in sorted(bad):
                print('  渲染=%s化%s@%s；引擎原值无此组合' % (star, hua, gong))
            sys.exit(2)


def xingxi_mains(sbg, zhi):
    """该支主星（空宫借对宫主星，行运判语检索用）。"""
    mains = [s for s in sbg[zhi] if s in MAIN_STARS]
    if not mains:
        opp = ZHI[(ZHI.index(zhi) + 6) % 12]
        mains = [s for s in sbg[opp] if s in MAIN_STARS]
    return mains


def xingxi_names(mains):
    """星系名候选（全排列紧排/空排，如 太阳巨门/巨门太阳）。"""
    names = set()
    for p in itertools.permutations(mains):
        names.add(''.join(p))
        names.add(' '.join(p))
    return names


# 本质二分对：出发星系 → (A 版本质词, B 版本质词)；判语按含词标注两路，不预判选版
ESSENCE_PAIRS = [
    ({'武曲', '贪狼'}, '欲望', '野心'),
    ({'紫微', '七杀'}, '开创力', '权力欲'),
    ({'廉贞', '破军'}, '兴利除弊', '私利'),
    ({'天机', '天梁'}, '明断', '尖刻'),
    ({'太阳', '巨门'}, '偏利', '偏名'),
    ({'太阴', '天同'}, '积极', '消极'),
    ({'天府'}, '守成', '空露'),
    ({'天相'}, '财荫', '刑忌'),
]


def essence_pair(star_set):
    for stars, a, b in ESSENCE_PAIRS:
        if star_set == stars:
            return a, b
    return None


def essence_material(indexes, sbg, pan_file, up, cur, name, has_uprefs=False):
    """【版本判定素材】：紧邻上层该宫完整配置 + 紧邻两层四化对此星系
    + 六十星系"判版本"整段判据。只取紧邻上层+本层四化（不取流年/原局四化行）。
    返回（行列表, 二分对）；无主星返回 (None, None)。"""
    dep_z = palace_zhi_of(up, name)
    dep_m = xingxi_mains(sbg, dep_z)
    if not dep_m:
        return None, None
    sys.path.insert(0, HERE)
    import retrieve
    import geju
    pair = essence_pair(frozenset(dep_m))

    up_pan_file = copy.deepcopy(pan_file)
    up_pan_file['pan']['twelvePalaces'] = up['palaces']
    up_pan_file['pan']['mingShen']['ming'] = up['ming_zhi']
    up_pan_file['pan']['siHua'] = up['sihua']
    info = retrieve.format_palace_context(up_pan_file, dep_z)
    # 流盘层上层配置同样剔除身宫标注
    info['context'] = re.sub(r'（身宫）\n?', '', info['context'])

    L = ['【版本判定素材】（子代理据此判定当前宫内星系的版本——读配置+判据→判定，判定过程须在 output 中体现）']
    L.append('⚠ 版本判定依据：紧邻上层四化+本层四化——不直接引用更远层四化')
    if has_uprefs:
        L.append('⚠ 上级已判定版本结论（见【上级分析结论参考】），直接引用优先于自行判定')
    L.append('- 上层星系：%s@%s（%s盘·%s）' % ('、'.join(dep_m), dep_z, LEVEL_CN[up['level']], name))
    L.append('- 宫内配置（主星/辅曜/煞曜/杂曜/四化+借宫，上层盘视角）：')
    L.append('  ' + info['context'].rstrip('\n').replace('\n', '\n  '))

    def hua_of(layer):
        hits = ['%s（%s干化%s）' % (h, layer['level_gan'], h)
                for h in HUA_ORDER if h in layer['sihua']
                and layer['sihua'][h]['star'] in dep_m]
        return '、'.join(hits) if hits else '无（%s干不化%s）' % (layer['level_gan'], '/'.join(dep_m))
    L.append('- 紧邻上层（%s）对此星系的四化：%s' % (up['label'], hua_of(up)))
    L.append('- 本层（%s）对此星系的四化：%s' % (cur['label'], hua_of(cur)))
    trine = geju.trine_zhi(dep_z)
    hui = ['%s化%s@%s（%s）会照本宫三方四正' % (up['sihua'][h]['star'], h, up['sihua'][h]['gong'],
                                            up['palaces'].get(up['sihua'][h]['gong'], ''))
           for h in HUA_ORDER if h in up['sihua'] and up['sihua'][h]['gong'] in trine]
    L.append('- 上层四化会照：%s' % ('、'.join(hui) if hui else '（无上层四化会照本宫）'))
    if pair:
        L.append('- 版本二分：%s 星系须先判「%s版」抑或「%s版」（判据见下），两版行运判语截然不同' % (
            '、'.join(dep_m), pair[0], pair[1]))

    # 语料判据：六十星系专论中含"本质"的完整切片（整段注入，非关键词碎片）
    dep_set = frozenset(dep_m)
    verdicts = []
    for key, ss in indexes['by_parent'].items():
        if '（' in key and frozenset(key.split('（', 1)[0].split()) == dep_set:
            verdicts += [s for s in ss if s.get('topic', '') == '六十星系'
                         and '本质' in (s.get('content', '') or '')]
    if verdicts:
        L.append('- 语料判据（六十星系专论·判版本整段——表述须与语料原文一致，禁加强/弱化措辞）：')
        for s in verdicts:
            body = (s.get('content', '') or '').strip()
            L.append('  ◆ %s · %s' % (s.get('topic', ''), s.get('parent_topic', '')))
            L.append('  ' + body.replace('\n', '\n  '))
    else:
        L.append('- 语料判据：六十星系专论无"判版本"专段命中，按 L1/L2 专论+上方配置自行判定')
    return L, pair


def xingyun_duanyu(indexes, sbg, dep_layer, tgt_layer, name, pair=None):
    """行运匹配第三路（§二·D 链式两步的单步）：在出发星系（dep 层 name 宫主星）的
    六十星系专论片中，扫含目标层（tgt 层）name 宫星系名的行运判语段落（含上下文）。
    pair=(A,B) 本质二分对时按判语含词标注「A版/B版」两路同时注入（不预判选版）。
    返回 (出发主星列表, 判语文本或未命中说明)。"""
    dep_z = palace_zhi_of(dep_layer, name)
    tgt_z = palace_zhi_of(tgt_layer, name)
    dep_m = xingxi_mains(sbg, dep_z)
    tgt_m = xingxi_mains(sbg, tgt_z)
    if not dep_m:
        return dep_m, '  该宫行运判语未命中（出发宫无主星含借宫），按 L1/L2 专论推演'
    tgt_names = xingxi_names(tgt_m) if tgt_m else set()
    dep_set = frozenset(dep_m)
    slices = []
    for key, ss in indexes['by_parent'].items():
        if '（' in key and frozenset(key.split('（', 1)[0].split()) == dep_set:
            slices += [s for s in ss if s.get('topic', '') == '六十星系']
    if not slices:
        return dep_m, '  该星系行运判语未命中（六十星系语料无专论），按 L1/L2 专论推演'
    hits = []
    for s in slices:
        clines = (s.get('content', '') or '').split('\n')
        idxs = [i for i, ln in enumerate(clines) if any(n in ln for n in tgt_names)]
        if not idxs:
            continue
        flavor = [i for i in idxs if any(k in clines[i] for k in ('喜', '忌', '行', '垣'))]
        for i in (flavor or idxs):
            seg = [x.strip() for x in clines[max(0, i - 1):i + 2] if x.strip()]
            tag = ''
            if pair:
                seg_text = ' '.join(seg)
                if pair[0] in seg_text and pair[1] not in seg_text:
                    tag = '「%s版」' % pair[0]
                elif pair[1] in seg_text and pair[0] not in seg_text:
                    tag = '「%s版」' % pair[1]
            hits.append('（%s）%s%s' % (s.get('parent_topic', ''), tag, ' ⟧ '.join(seg)))
    if not hits:
        return dep_m, ('  该星系行运判语未命中（专论无涉 %s 段落），按 L1/L2 专论推演'
                       % ('、'.join(tgt_m) if tgt_m else '目标宫'))
    cap = hits[:12]
    text = '\n'.join('  ' + h for h in cap)
    if len(hits) > 12:
        text += '\n  …（共 %d 段命中，取前 12）' % len(hits)
    return dep_m, text


def liuyao_lines(chain, zhi):
    """【流曜叠化】节（三层化）：流曜只看 本层+紧邻上层+原局 三层
    （大限两层=原局+大限）——禁扩展为全部层；八曜宫位按宫归组+力量层级+共振+传染标注；
    传染规则：本层干化八曜→本层流曜带性（无条件）→紧邻上层同名流曜随（无条件）→
    原局同名星须会照（三方四正：三合差4/8+对宫差6）才随；大限层原局星直接随。"""
    cur = chain[-1]
    scope = liuyao_scope_chain(chain)
    scope_cn = '+'.join(LEVEL_CN[l['level']] for l in scope)
    L = ['【流曜叠化】（各层流曜八曜宫位——文昌/文曲/擎羊/陀罗/禄存/天马/天魁/天钺；'
         '只看三层：%s——当前层+紧邻上层+原局（稿，禁扩展为全部层）；'
         '力量层级：越上层体越强（如流月>流日>原局））' % scope_cn]
    in_gong = []
    for lay in scope:
        for star, pos in (lay.get('liuyao') or {}).items():
            if pos == zhi:
                in_gong.append((star, lay, pos))
    if in_gong:
        in_gong.sort(key=lambda t: LEVEL_ORDER.index(t[1]['level']))
        by_star = {}
        for star, lay, pos in in_gong:
            by_star.setdefault(star, []).append(lay)
        parts = []
        for star, lays in by_star.items():
            layers_txt = '+'.join(LEVEL_CN[l['level']] for l in lays)
            if len(lays) >= 2:
                parts.append('%s：%s同宫=共振加强（%s）' % (star, layers_txt, star))
            else:
                parts.append('%s（%s）' % (star, layers_txt))
        L.append('- 本宫（%s）流曜：%s' % (zhi, '、'.join(parts)))
    else:
        L.append('- 本宫（%s）无三层内流曜落入' % zhi)
    # 同宫共振（三层范围内，全盘视角）：同类流曜≥2 层同宫逐处列出
    res = []
    for z in ZHI:
        for star in LIUYAO_STARS:
            lays = [lay for lay in scope if (lay.get('liuyao') or {}).get(star) == z]
            if len(lays) >= 2:
                res.append('%s@%s（%s）' % (star, z, '+'.join(LEVEL_CN[l['level']] for l in lays)))
    L.append('- 同宫共振（三层内）：%s' % ('、'.join(res) if res else '（三层内无多层同类流曜同宫）'))
    # 四化传染（化性传染规则）
    up = chain[-2]
    origin = chain[0]
    chuan = []
    for h in HUA_ORDER:
        if h not in cur['sihua']:
            continue
        star = cur['sihua'][h]['star']
        if star not in LIUYAO_STARS:
            continue
        cur_pos = (cur.get('liuyao') or {}).get(star)
        up_pos = (up.get('liuyao') or {}).get(star) if up is not cur else None
        if cur_pos:
            chuan.append('本层%s化%s → 本层流曜%s@%s 带化%s性质（无条件）' % (
                star, h, star, cur_pos, h))
        if up_pos:
            chuan.append('本层%s化%s → %s%s@%s 随之具备化%s性质（紧邻上层，无条件）' % (
                star, h, LEVEL_CN[up['level']], star, up_pos, h))
        if origin is not cur:
            o_pos = (origin.get('liuyao') or {}).get(star)
            if o_pos:
                if cur['level'] == 'daxian':
                    chuan.append('本层%s化%s → 原局%s@%s 随之具备化%s性质（大限紧邻原局，直接随）' % (
                        star, h, star, o_pos, h))
                else:
                    ref = cur_pos or up_pos
                    if ref and hui_zhao(o_pos, ref):
                        chuan.append('本层%s化%s → 原局%s@%s 会照%s@%s（三方四正）→ 随之具备化%s性质' % (
                            star, h, star, o_pos, star, ref, h))
    L.append('- 四化传染：%s' % ('；'.join(chuan) if chuan else '（本层四化星不涉八曜或三层内无同名流曜）'))
    L.append('- 本层天干四化之星，本层自身排的流曜也带该化性——如己日文曲化忌→流日文曲（无论落何宫）也带忌性，分析时须按化性断。')
    return L


def build_layer_inputs(pan_file, pan, chain, outdir, uprefs=None):
    """12 份分宫 input（原局超集）：
    层命盘信息+层盘星曜信息+三层并标（宫名纵叠）+四化相邻配对（叠X/X转Y）+
    （流日/流时）十二神定位+本层格局核验+三方四正会照（四化会照）+流曜叠化+
    上级分析结论参考（级联）+版本判定素材+行运匹配判语（版本两路标注）+
    检索语料正文+硬约束。语料宫位三类按本层宫名匹配（宫支不动、星系同源）。
    流盘层（非原局）过滤身宫数据——数据不出现=子代理不可能引用。"""
    sys.path.insert(0, HERE)
    import retrieve
    import geju
    from taxonomy import DESIRED_ORDER
    cur, up = chain[-1], chain[-2]
    upup = chain[-3] if len(chain) >= 3 else None
    sbg = stars_by_gong(pan)

    layer_pan_file = copy.deepcopy(pan_file)
    layer_pan_file['pan']['twelvePalaces'] = cur['palaces']
    layer_pan_file['pan']['mingShen']['ming'] = cur['ming_zhi']
    layer_pan_file['pan']['siHua'] = cur['sihua']
    layer_pan = layer_pan_file['pan']
    kb = retrieve.load_kb_data()
    indexes = retrieve.build_indexes(kb)

    up_hua = {e['star']: h for h, e in up['sihua'].items()}
    cur_hua = {e['star']: h for h, e in cur['sihua'].items()}
    doubles = [s for s in cur_hua if s in up_hua]

    def bingbiao_line(name):
        """三层并标行（宫名纵叠）：同名宫，三层各层盘各自的支与星系。"""
        if upup:
            return ('事象层：%s盘·%s=%s｜基调层：%s盘·%s=%s｜背景层：%s盘·%s=%s' % (
                LEVEL_CN[cur['level']], name, gong_cell(sbg, palace_zhi_of(cur, name)),
                LEVEL_CN[up['level']], name, gong_cell(sbg, palace_zhi_of(up, name)),
                LEVEL_CN[upup['level']], name, gong_cell(sbg, palace_zhi_of(upup, name))))
        return ('事象层：%s盘·%s=%s｜背景层：%s盘·%s=%s（大限两重：原局+大限）' % (
            LEVEL_CN[cur['level']], name, gong_cell(sbg, palace_zhi_of(cur, name)),
            LEVEL_CN[up['level']], name, gong_cell(sbg, palace_zhi_of(up, name))))

    # 行运匹配步组：[主]=紧邻上层→本层，[辅]=再上层→紧邻上层；大限两重单步无主辅
    if upup:
        xy_steps = [('[主]', up, cur), ('[辅]', upup, up)]
    else:
        xy_steps = [('', up, cur)]

    tishi = tiyong_line(chain)
    files = []
    rendered = []
    for idx, name in enumerate(DESIRED_ORDER, 1):
        zhi = palace_zhi_of(cur, name)
        if not zhi:
            raise RuntimeError('本层盘缺少 %s 宫' % name)
        stars = sbg[zhi]
        L = []
        L.append('【本层命盘信息】（排盘程序核毕，直接采信勿再自推宫位关系）')
        L.append('- 层：%s' % cur['label'])
        L.append('- 体用上下文：%s' % tishi)
        L.append('- 本层天干：%s（四化：%s）' % (cur['level_gan'], layer_sihua_line(cur)))
        L.append('- 上层（%s）天干：%s（四化：%s）' % (up['label'], up['level_gan'], layer_sihua_line(up)))
        L.append('- 本层命宫：%s宫' % cur['ming_zhi'])
        L.append('')
        info = retrieve.format_palace_context(layer_pan_file, zhi)
        if cur['level'] != 'origin':
            # 流盘层剔除身宫标注（源头断绝数据层泄露）
            info['context'] = re.sub(r'（身宫）\n?', '', info['context'])
        L.append('【本层盘·%s宫星曜信息】（星曜庙旺/四化/借宫标注，层盘版）' % name)
        L.append(info['context'].rstrip('\n'))
        L.append('')
        L.append('【该宫三层并标】（宫名纵叠：同一宫名，各层盘重布后各自的支与星系）')
        L.append('- %s' % bingbiao_line(name))
        L.append('')
        L.append('【该宫四化相邻配对】（只看紧邻上层与本层两层）')
        hit = [h for h in HUA_ORDER if h in up['sihua'] and up['sihua'][h]['gong'] == zhi]
        if hit:
            for h in hit:
                e = up['sihua'][h]
                L.append('- 上层化%s：%s@%s化%s，直落本宫' % (h, e['star'], zhi, h))
        else:
            L.append('-（上层四化无落本宫）')
        if doubles:
            for s in doubles:
                if s in stars:
                    L.append('- 同星双化：%s 上层(%s)化%s + 本层(%s)化%s = %s' % (
                        s, up['level_gan'], up_hua[s], cur['level_gan'], cur_hua[s],
                        double_tag(up_hua[s], cur_hua[s])))
        if cur.get('twelve_gods'):
            tg = cur['twelve_gods']
            L.append('')
            L.append('【该宫十二神定位】（引擎流层十二神：岁建/将星起流年支、博士起流年禄存含顺逆；长生随原局五行局）')
            L.append('- 本宫%s：岁建十二神=%s、将星=%s、博士=%s、长生（原局）=%s' % (
                zhi, tg['taiSuiTwelve'][zhi], tg['jiangQian'][zhi],
                tg['boShi'][zhi], tg['changShengTwelve'][zhi]))
        L.append('')
        L.append('【本层格局核验】（A 级 22 项+B 级 14 项，对本层盘逐宫判；共享模块 geju.py 与原局链同源）')
        L += geju.geju_lines(layer_pan, name, zhi)
        L.append('')
        L.append('【该宫三方四正会照】（本层盘视角）')
        L += geju.trine_block(layer_pan, name, zhi)
        L.append(geju.six_lucky_line(layer_pan, geju.trine_zhi(zhi)))
        q = geju.trine_zhi(zhi)
        for h in HUA_ORDER:
            if h in cur['sihua']:
                e = cur['sihua'][h]
                g = e['gong']
                L.append('  - 本层化%s：%s@%s（%s）%s' % (
                    h, e['star'], g, layer_pan['twelvePalaces'].get(g, g),
                    '会入本宫三方四正' if g in q else '未会入'))
            if h in up['sihua']:
                e = up['sihua'][h]
                g = e['gong']
                L.append('  - 上层化%s：%s@%s（%s）%s' % (
                    h, e['star'], g, layer_pan['twelvePalaces'].get(g, g),
                    '会入本宫三方四正' if g in q else '未会入'))
        L.append('')
        L += liuyao_lines(chain, zhi)
        if uprefs and name in uprefs:
            L.append('')
            L += uprefs[name]
        em_lines, em_pair = essence_material(indexes, sbg, pan_file, up, cur, name,
                                             has_uprefs=bool(uprefs and name in uprefs))
        if em_lines:
            L.append('')
            L += em_lines
        L.append('')
        L.append('【行运匹配判语】（检索第三路·链式两步：[主]=紧邻上层星系×本层宫垣，'
                 '[辅]=再上层星系×紧邻上层宫垣；大限两重单步无主辅；'
                 '版本二分星系两版判语同时列出——先按【版本判定素材】判版本再选版展开）')
        for tag, dep, tgt in xy_steps:
            dep_z = palace_zhi_of(dep, name)
            step_pair = em_pair if dep is up else None
            dep_m, body = xingyun_duanyu(indexes, sbg, dep, tgt, name, pair=step_pair)
            L.append('- %s %s盘·%s宫星系（%s@%s）× %s盘·%s宫垣（%s宫支）' % (
                tag, LEVEL_CN[dep['level']], name,
                '、'.join(dep_m) if dep_m else '（无主星）', dep_z,
                LEVEL_CN[tgt['level']], name, palace_zhi_of(tgt, name)))
            L.append(body)
            L.append('  提示：判语内嵌条件须回本层盘面核验（如太阳化忌否/魁钺会否）')
        L.append('')
        kbctx, _ = retrieve.build_palace_kb_context(indexes, info)
        L.append(kbctx)
        L.append('【硬约束】')
        L.append('- 只基于知识库切片与命盘结构，不编造；资料论述少的组合明确说明')
        L.append('- 空宫只能借对宫（上文已标注），禁止从其他宫借星')
        L.append('- 不确定判断用"可能/倾向/需注意"，禁绝对化表述')
        L.append('- 四化只认上文列明的（层四化+相邻配对），不得给未列明星曜添加四化')
        L.append('- 行运判语为主判材料，内嵌条件未回盘核验不得直接下断')
        content = '\n'.join(L) + '\n'
        fname = 'input_%02d_%s.md' % (idx, name)
        rendered.append((fname, content))
    # fail-fast：落盘前逐星校验渲染四化标注 vs 引擎 chain siHua 原值，错位拒绝出批次
    verify_sihua_render(chain, [c for _, c in rendered], where='input_*.md')
    for fname, content in rendered:
        with open(os.path.join(outdir, fname), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        files.append(fname)
    return files


def generate_dispatch_liupan(outdir, chain, pan, pattern_stats_text=''):
    # 批次尾件：读流盘 dispatch 模板替换占位后落 <批次>/dispatch_liupan.workflow.js
    """占位替换同 make.generate_dispatch 模式；pattern_stats_text=预测流程 v2.1
    历史战绩注入文本（JSON 字面量替换，内部引号/换行安全转义；空串=CONFIG 留空不注入）。"""
    cur = chain[-1]
    with open(DISPATCH_LIUPAN_TPL, 'r', encoding='utf-8') as f:
        tpl = f.read()
    js_dir = outdir.replace('\\', '\\\\')
    gender_cn = {'male': '男', 'female': '女'}.get(pan.get('gender', ''), '男')
    content = (tpl.replace('{{INPUTS_DIR}}', js_dir)
                  .replace('{{OUTPUTS_DIR}}', js_dir)
                  .replace('{{TIYONG_LINE}}', tiyong_line(chain))
                  .replace('{{SIHUA_LINE}}', layer_sihua_line(cur))
                  .replace('{{GENDER}}', gender_cn)
                  .replace('{{SHENGONG_NOTE}}',
                           '流盘分析禁引用任何身宫信息——原局身宫与本层分析无关，'
                           '输入中如出现身宫标注请忽略，输出中不得提及身宫二字')
                  .replace("'{{PATTERN_STATS}}'",
                           json.dumps(pattern_stats_text, ensure_ascii=False)))
    dest = os.path.join(outdir, 'dispatch_liupan.workflow.js')
    with open(dest, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    return dest


def layer_dirname(level, args, chain):
    """批次目录名=被分析的行运日期标识（同标的重做=新批次覆盖旧批次）。"""
    if level == 'daxian':
        nums = re.findall(r'\d+', chain[-1].get('dx_range') or '')
        seg = '%s-%s' % (nums[0], nums[1]) if len(nums) >= 2 else (chain[-1].get('dx_range') or '')
        return '第%d限%s' % (args.seq, seg)
    if level == 'liunian':
        return str(args.year)
    if level == 'liuyue':
        return args.month
    if level == 'liuri':
        return args.date
    return '%s-%s' % (args.date, args.hour)


def batch_outdir(person, topic, leaf):
    r"""批次目录：<输出库|技能output>\<person>\<topic>\temp\<行运日期>\（覆盖式）。"""
    import make
    zero_root = make._zero_root()
    if zero_root:
        base = os.path.join(zero_root, 'output', person, topic, 'temp')
    else:
        make._ensure_output_gitignore(os.path.join(SKILL_ROOT, 'output'))
        base = os.path.join(SKILL_ROOT, 'output', person, topic, 'temp')
    outdir = os.path.join(base, leaf)
    os.makedirs(outdir, exist_ok=True)
    return outdir


def cascade_uprefs(level, args, chain, person_root):
    """级联分析链：检查上级分析报告，存在→按宫提取结论注入
    【上级分析结论参考】；不存在→stdout 提示建议先生成（不自动生成）。
    返回 {宫名: 行列表}（仅含有命中结论的宫）。"""
    from taxonomy import DESIRED_ORDER
    dx_seq = None
    for l in chain:
        if l['level'] == 'daxian':
            m = re.findall(r'第(\d+)限', l['label'])
            dx_seq = m[0] if m else None
    ym = None
    y = str(args.year) if args.year else (args.month[:4] if args.month else None)
    if args.date:
        # 上级报告按流月/流年层的公历键命名（流月=当月15日所在农历月，流年=年中所在农历年），
        # 公历日期跨农历月/年时须按本盘链上的农历月与流年干支反查
        ly = next(l for l in chain if l['level'] == 'liuyue')
        ln = next(l for l in chain if l['level'] == 'liunian')
        gy = int(args.date[:4])
        y = str(next(c for c in (gy, gy - 1) if ln['label'].startswith(GAN[(c - 4) % 10] + ZHI[(c - 4) % 12])))
        gm = int(args.date[5:7])
        for dy, dm in ((gy, gm), (gy - (gm == 1), (gm - 2) % 12 + 1), (gy + (gm == 12), gm % 12 + 1)):
            e = engine_liupan(args.pan, 'liuyue', '%04d-%02d-15' % (dy, dm))
            if '农历%s月' % e['lunar']['effectiveLunarMonth'] in ly['label']:
                ym = '%04d-%02d' % (dy, dm)
                break
    tbl = {
        'liuri': [('流月', 'Liuyue', '报告-%s.md' % ym), ('流年', 'Liunian', '报告-%s.md' % y)],
        'liushi': [('流月', 'Liuyue', '报告-%s.md' % ym), ('流年', 'Liunian', '报告-%s.md' % y)],
        'liuyue': [('流年', 'Liunian', '报告-%s.md' % y),
                   ('大限', 'Daxian', '报告-第%s限.md' % dx_seq if dx_seq else '报告.md')],
        'liunian': [('大限', 'Daxian', '报告-第%s限.md' % dx_seq if dx_seq else '报告.md'),
                    ('原局', 'Yuanju', '报告.md')],
        'daxian': [('原局', 'Yuanju', '报告.md')],
    }
    reports = []
    for cn, topic, fn in tbl[level]:
        path = os.path.join(person_root, topic, fn)
        if os.path.exists(path):
            reports.append((cn, path))
        else:
            print('⚠ 上级分析未生成：建议先生成 %s' % path)
    refs = {}
    if not reports:
        return refs
    for name in DESIRED_ORDER:
        L = ['【上级分析结论参考】（上级已判定的版本结论优先于本层自行推演——直接引用校准本层判断）']
        got = False
        for cn, path in reports:
            with open(path, encoding='utf-8') as f:
                paras = re.split(r'\n\s*\n', f.read())
            hits = [p.strip().replace('\n', ' ') for p in paras if name in p]
            if not hits:
                continue
            got = True
            text = ' ▍ '.join(hits[:6])
            if len(text) > 2000:
                text = text[:2000] + '…'
            L.append('- %s分析·%s宫相关结论：%s' % (cn, name, text))
        if got:
            refs[name] = L
    return refs


def batch_mode(args, pan_file, pan, chain, result):
    """全链批次模式：落批次目录（技能 output 兜底）自包含批次 + dispatch 生成物。"""
    import make
    person = args.person or os.path.splitext(os.path.basename(args.pan))[0]
    if not make.PERSON_RE.match(person):
        raise RuntimeError('--person 含非法字符（只允中文/字母/数字/下划线/连字符）：%s' % person)
    topic = LEVEL_TOPIC[args.level]
    outdir = batch_outdir(person, topic, layer_dirname(args.level, args, chain))
    print('批次目录：%s' % outdir)
    # outdir = <person>\<Topic>\temp\<行运日期> → person_root = <person>（上级报告在 <person>\<上级Topic>\）
    person_root = os.path.dirname(os.path.dirname(os.path.dirname(outdir)))
    uprefs = cascade_uprefs(args.level, args, chain, person_root)

    pan_name = 'pan_%s_%s.json' % (args.level, level_param(args.level, args))
    # fail-fast：批次产物落盘前，facttable 与 dispatch sihuaLine 同过四化标注自检
    ft_text = fact_table(pan, chain)
    verify_sihua_render(chain, [ft_text, layer_sihua_line(chain[-1])], where='facttable/sihuaLine')
    with open(os.path.join(outdir, pan_name), 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2))
    print(pan_name)
    with open(os.path.join(outdir, 'facttable.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(ft_text)
    print('facttable.md')
    for fname in build_layer_inputs(pan_file, pan, chain, outdir, uprefs=uprefs):
        print(fname)

    # 历史印证一查多注：全盘 combo → FAISS top-K → 类别路由宫位注入
    pattern_injection = ''
    try:
        sys.path.insert(0, os.path.join(SKILL_ROOT, 'verify', 'bin'))
        sys.path.insert(0, os.path.join(SKILL_ROOT, 'bin'))
        import extractor
        import verify_refs
        combo = extractor.build_combo(pan, result, ft_text)
        snap = extractor.build_structure_snapshot(pan, result, ft_text)
        exclude = {'liuri': args.date, 'liushi': args.date,
                   'liuyue': args.month, 'liunian': str(args.year or '')}.get(args.level) or None
        # 脱敏比对用账本权威名（盘文件名）：报告对象名与账本权威名字符串不等会把自己的历史错脱敏
        ledger_person = os.path.splitext(os.path.basename(args.pan))[0]
        verify_refs.inject_verify_refs(outdir, combo, ledger_person, exclude_date=exclude,
                                       layer=args.level, structure_snapshot=snap,
                                       liuyue_label=snap.get('liuyue_label', ''))
        # 预测流程 v2.1：盘面模式级战绩统计 → 注入 dispatch 子代理 prompt
        # （核心特征=忌/禄落宫+命宫星系；查询键必须用 combo_features 展平后的原键名
        #   layer_ming_xingxi——自造中文键会因键不存在永不命中，gate=len(q) 随之永不满足）
        q = {h: v for h, v in (combo.get('sihua') or {}).items() if h in ('忌', '禄') and v}
        if combo.get('layer_ming_xingxi'):
            q['layer_ming_xingxi'] = combo['layer_ming_xingxi']
        if q:
            try:
                cmd = [sys.executable, os.path.join(SKILL_ROOT, 'verify', 'bin', 'pattern_stats.py'),
                       '--person', ledger_person, '--combo', json.dumps(q, ensure_ascii=False),
                       '--gate', '2', '--exclude-date', exclude or '']  # gate=2（3 AND 太慢）
                if args.level in ('liuri', 'liuyue', 'liunian', 'liushi'):
                    cmd += ['--level', args.level]  # 按本层统计（层内禁跨层合并）
                r = subprocess.run(cmd,
                    capture_output=True, timeout=60, cwd=SKILL_ROOT,
                    env=dict(os.environ, PYTHONUTF8='1'))
                pattern_injection = json.loads(
                    r.stdout.decode('utf-8', 'replace')).get('injection_text', '')
            except Exception as e:  # 容错：统计失败只跳过注入，不误标印证链、不阻断批次
                print('⚠ 盘面模式统计失败（%s）——dispatch 不注入历史战绩' % e)
    except Exception as e:  # 容错：印证链失败不阻断批次
        print('⚠ 历史印证注入失败（%s）——批次照常生成' % e)

    dest = generate_dispatch_liupan(outdir, chain, pan, pattern_injection)
    print('workflow 脚本已生成：%s，直接以其内容执行' % os.path.abspath(dest))
    print('批次完成：%s（%s 份 input + %s + facttable.md + dispatch_liupan.workflow.js）'
          % (os.path.abspath(outdir), 12, pan_name))


# ═════════════════════════════════════
#  main
# ═════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description='流盘排布引擎（五层参数化）')
    ap.add_argument('--pan', required=True)
    ap.add_argument('--level', required=True,
                    choices=['daxian', 'liunian', 'liuyue', 'liuri', 'liushi'])
    ap.add_argument('--seq', type=int, help='大限序号（1-based，daxian 层必填）')
    ap.add_argument('--year', type=int, help='liunian 层')
    ap.add_argument('--month', help='liuyue 层，YYYY-MM')
    ap.add_argument('--date', help='liuri/liushi 层，YYYY-MM-DD')
    ap.add_argument('--hour', help='liushi 层时支')
    ap.add_argument('--out', help='流盘 JSON 输出文件（缺省 stdout）')
    ap.add_argument('--facttable', help='叠盘事实表 Markdown 输出文件')
    ap.add_argument('--outdir', action='store_true',
                    help='全链批次模式：落批次目录 <person><Topic>\\temp\\<行运日期>\\ 自包含批次并生成 dispatch（同标的重做=覆盖）')
    ap.add_argument('--person', help='批次对象名（缺省=盘文件名；批次对象词=<命主名>/Guest<n>/人名）')
    args = ap.parse_args()

    with open(args.pan, encoding='utf-8') as f:
        pan_file = json.load(f)
    pan = pan_file['pan']

    chain, flow_year = compute_chain(args.level, pan, pan_file, args)
    cur = chain[-1]

    result = {
        'level': cur['level'],
        'label': cur['label'],
        'level_gan': cur['level_gan'],
        'ming_zhi': cur['ming_zhi'],
        'palaces': cur['palaces'],
        'sihua': cur['sihua'],
        'twelve_gods': cur['twelve_gods'],
        'chain': [{'level': l['level'], 'label': l['label'], 'level_gan': l['level_gan'],
                   'ming_zhi': l['ming_zhi'],
                   'palace_of_ming': l['palaces'][l['ming_zhi']],
                   'sihua': {h: l['sihua'][h] for h in HUA_ORDER if h in l['sihua']}}
                  for l in chain],
    }
    for k in ('day_ganzhi', 'hour_ganzhi'):
        if k in cur:
            result[k] = cur[k]
    result['retrieval'] = retrieve_for_layer(pan_file, pan, cur)

    if args.outdir:
        batch_mode(args, pan_file, pan, chain, result)
        return

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    else:
        print(text)

    ft = fact_table(pan, chain)
    if args.facttable:
        with open(args.facttable, 'w', encoding='utf-8') as f:
            f.write(ft)
    else:
        print('\n' + ft)


if __name__ == '__main__':
    main()
