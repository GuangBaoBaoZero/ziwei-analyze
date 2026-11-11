# -*- coding: utf-8 -*-
"""格局核验共享模块（A 级 22 项 + B 级 14 项，自 prep_inputs.py 抽出）

单一真源：原局链（prep_inputs.py）与流盘链（liupan.py）同源调用，禁复制两份。
接受的 pan 为"层盘版" dict：twelvePalaces/siHua/mingShen 按所验层盘覆写即可，
allStarMap/starBrightness 等星曜数据各层同源（宫支不动）。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy import MAIN_STARS, ZHI_ORDER

SIX_LUCKY = ['左辅', '右弼', '文昌', '文曲', '天魁', '天钺']
SHA_STATS = ['火星', '铃星', '擎羊', '陀罗', '地空', '地劫']

# ── 格局核验扩充一期（A 级 22 项）配置表 ──
SANDWICH_PATTERNS = [  # A1 夹型 (label, 星a, 星b)；双禄夹星b=None→siHua 化禄星动态解析
    ('空劫夹', '地空', '地劫'),
    ('昌曲夹', '文昌', '文曲'),
    ('左右夹', '左辅', '右弼'),
    ('日月夹', '太阳', '太阴'),
    ('魁钺夹', '天魁', '天钺'),
    ('双禄夹', '禄存', None),
    ('伤使夹', '天伤', '天使'),
]
PALACE_STAR_PATTERNS = [  # A2 落宫型 (label, 星, 触发支)：星@触发支成立，报该支所在宫
    ('极向离明', '紫微', '午'),
    ('七杀朝斗', '七杀', '申'),
    ('七杀仰斗', '七杀', '寅'),
    ('寿星入庙', '天梁', '午'),
    ('月照寒潭', '太阴', '戌'),
    ('月朗天门', '太阴', '亥'),
    ('日照雷门', '太阳', '卯'),
    ('日丽中天', '太阳', '午'),
    ('日月并明', '太阳', '辰'),
    ('日月反背', '太阳', '戌'),
]
COMBO_PATTERNS = [  # A3 同度灾格 (label, [(星, 支, 同度煞), ...])：多口径并列
    ('泛水桃花', [('贪狼', '子', '擎羊'), ('贪狼', '亥', '陀罗')]),
    ('风流彩杖', [('贪狼', '寅', '陀罗')]),
    ('马头带箭', [('天同', '午', '擎羊'), ('贪狼', '午', '擎羊')]),
]
# ── 格局核验扩充二期（B 级 14 项）：口径分歧项，行内嵌口径定义全文、并列报不拍板 ──
# 落位两制：星定宫制=宾语星所在宫（成立/不成立都报）；结构触发制=结构成立才触发行+落宫归位。
# 各项逻辑差异大不走配置表，函数化（见 b_geju_lines 以下 B 级函数区）。


# ═════════════════════════════════════
#  基础取数
# ═════════════════════════════════════

def trine_zhi(zhi):
    """三方四正四支：本宫、对宫、两三合"""
    i = ZHI_ORDER.index(zhi)
    return [zhi, ZHI_ORDER[(i + 6) % 12], ZHI_ORDER[(i + 4) % 12], ZHI_ORDER[(i + 8) % 12]]


def neigh_zhi(zhi):
    """前后两邻支（夹型判定基准，同 sandwich_line 口径）"""
    i = ZHI_ORDER.index(zhi)
    return (ZHI_ORDER[(i - 1) % 12], ZHI_ORDER[(i + 1) % 12])


def sihua_star(pan, hua):
    """本盘某四化（禄/权/科/忌）的化曜星名"""
    return ((pan.get('siHua', {}) or {}).get(hua) or {}).get('star')


def stars_at(pan, zhi):
    """该支星曜（allStarMap 原序，主星自然在前）"""
    return [s for s, z in pan.get('allStarMap', {}).items() if z == zhi]


def mains_at(pan, zhi):
    return [s for s in stars_at(pan, zhi) if s in MAIN_STARS]


def palace_name(pan, zhi):
    return (pan.get('twelvePalaces', {}) or {}).get(zhi, zhi)


def gong_tag(pan, zhi):
    """支旁注宫名：命宫不加重复的宫字，其余加宫"""
    name = palace_name(pan, zhi)
    return name if name.endswith('宫') else name + '宫'


def at_tag(pan, zhi):
    return f"{zhi}（{gong_tag(pan, zhi)}）"


def sihua_line(pan):
    parts = []
    for hua in ('禄', '权', '科', '忌'):
        info = (pan.get('siHua', {}) or {}).get(hua) or {}
        parts.append(f"化{hua}{info.get('star', '?')}@{at_tag(pan, info.get('gong', '?'))}")
    return "- 四化：" + "、".join(parts)


# ═════════════════════════════════════
#  A 级核验
# ═════════════════════════════════════

def pattern_basis(pan, quartet, wanted):
    """wanted 诸星在三方四正的落点（空宫借对宫主星计入）；返回 (落点串, 缺星串)"""
    seated = {s: z for s, z in pan.get('allStarMap', {}).items() if z in quartet and s in wanted}
    borrowed = {}
    for z in quartet:
        if mains_at(pan, z):
            continue
        opp = ZHI_ORDER[(ZHI_ORDER.index(z) + 6) % 12]
        for star in mains_at(pan, opp):
            if star in wanted and star not in seated:
                borrowed[star] = (z, opp)
    located, missing = [], []
    for s in wanted:
        if s in seated:
            located.append(f"{s}@{at_tag(pan, seated[s])}")
        elif s in borrowed:
            z, opp = borrowed[s]
            located.append(f"{s}@{at_tag(pan, opp)}（借入{palace_name(pan, z)}）")
        else:
            z = pan.get('allStarMap', {}).get(s)
            missing.append(f"{s}@{z}" if z else s)
    return located, missing


def pattern_line(pan, quartet, label, wanted):
    located, missing = pattern_basis(pan, quartet, wanted)
    if not missing:
        return f"  - {label}：成立——" + "、".join(located)
    miss = "、".join(missing)
    if located:
        return f"  - {label}：不成立——{miss}不在命宫三方四正；已会入：" + "、".join(located)
    return f"  - {label}：不成立——{miss}均不在命宫三方四正"


def sandwich_line(pan, zhi, label, star_a, star_b):
    """相邻两支是否分坐 star_a+star_b 夹本宫"""
    i = ZHI_ORDER.index(zhi)
    neigh = (ZHI_ORDER[(i - 1) % 12], ZHI_ORDER[(i + 1) % 12])
    am = pan.get('allStarMap', {}) or {}
    pa, pb = am.get(star_a), am.get(star_b)
    if pa in neigh and pb in neigh and pa != pb:
        return (f"  - {label}：成立——本宫[{palace_name(pan, zhi)}·{zhi}]"
                f"被{star_a}@{pa}、{star_b}@{pb}分列两邻支相夹")
    return f"  - {label}：不成立——邻支{neigh[0]}、{neigh[1]}无{star_a}+{star_b}分坐"


def guard_ming_line(ming_zhi, trigger_zhi):
    """守命条件行：命宫支==触发支为成立（落宫型格局原典多论坐命者）"""
    ok = ming_zhi == trigger_zhi
    return (f"  - 守命条件：{'成立' if ok else '不成立'}——命宫在{ming_zhi}"
            + ('' if ok else f'非{trigger_zhi}'))


def palace_star_line(pan, ming_zhi, zhi, label, star, palace_zhi):
    """A2 落宫型触发制：星@触发支才报且落宫归位（仅本宫支==触发支的文件出现）；
    触发行下附守命条件行，不触发返回 []"""
    am = pan.get('allStarMap', {}) or {}
    if palace_zhi != zhi or am.get(star) != palace_zhi:
        return []
    return [
        f"  - {label}：成立——{star}坐本宫[{palace_name(pan, palace_zhi)}·{palace_zhi}]",
        guard_ming_line(ming_zhi, palace_zhi),
    ]


def combo_line(pan, ming_zhi, zhi, label, combos):
    """A3 同度灾格触发制：星与同度煞俱@支才触发，多口径触发口径各一行，落宫归位同 A2"""
    am = pan.get('allStarMap', {}) or {}
    out = []
    for star, pz, co in combos:
        if pz != zhi or am.get(star) != pz or am.get(co) != pz:
            continue
        out.append(f"  - {label}：成立——{star}@{pz}坐本宫[{palace_name(pan, pz)}·{pz}]，与{co}同度")
        out.append(guard_ming_line(ming_zhi, pz))
    return out


def pattern_gong_line(pan, name, zhi, label, wanted):
    """A4 会齐型本宫变体：wanted 会齐本宫三方四正（空宫借对宫主星计入）才报，不齐无行"""
    located, missing = pattern_basis(pan, trine_zhi(zhi), wanted)
    if missing:
        return None
    return f"  - {label}：成立——{'、'.join(located)}会本宫[{name}·{zhi}]三方四正"


def baiguan_line(pan, name, zhi):
    """A4 百官朝拱中性计数行：本宫三方四正会入六吉 N 曜+禄注，只报数不判成格"""
    q = trine_zhi(zhi)
    am = pan.get('allStarMap', {}) or {}
    met = [f"{s}@{at_tag(pan, am[s])}" for s in SIX_LUCKY if am.get(s) in q]
    line = (f"  - 百官朝拱计数：本宫[{name}·{zhi}]三方四正会入 {len(met)} 曜"
            + (f"——{'、'.join(met)}" if met else '')
            + '（口径：左辅/右弼/文昌/文曲/天魁/天钺；成格门槛各家宽严不一，只计数不判定）')
    lu_star = ((pan.get('siHua', {}) or {}).get('禄') or {}).get('star')
    lu_notes = []
    if am.get('禄存'):
        lu_notes.append(f"禄存@{at_tag(pan, am['禄存'])}" + ('会入' if am['禄存'] in q else '未会入'))
    if lu_star and am.get(lu_star):
        lu_notes.append(f"化禄{lu_star}@{at_tag(pan, am[lu_star])}" + ('会入' if am[lu_star] in q else '未会入'))
    if lu_notes:
        line += '；禄注：' + '、'.join(lu_notes)
    return line


# ═════════════════════════════════════
#  格局核验扩充二期（B 级 14 项）：口径分歧项——行内嵌定义全文，并列报不拍板
# ═════════════════════════════════════

def xiongsu_lines(pan, ming_zhi, zhi):
    """B1 雄宿乾元格（触发制三口径）：①七杀@午+廉贞@申 ②廉杀@未同度（注明见吉无煞与否）
    ③廉贞@寅/申守命结构；①③附守命条件行"""
    am = pan.get('allStarMap', {}) or {}
    out = []
    if zhi == '午' and am.get('七杀') == '午' and am.get('廉贞') == '申':
        out.append(f"  - 雄宿乾元格：口径①（七杀@午且廉贞@申）成立——七杀坐本宫[{palace_name(pan, '午')}·午]，"
                   f"廉贞@{at_tag(pan, '申')}")
        out.append(guard_ming_line(ming_zhi, '午'))
    if zhi == '未' and am.get('廉贞') == '未' and am.get('七杀') == '未':
        q = trine_zhi('未')
        ji = sihua_star(pan, '忌')
        watchers = [f"{s}@{at_tag(pan, am[s])}" for s in SHA_STATS if am.get(s) in q]
        if ji and am.get(ji) in q:
            watchers.append(f"化忌{ji}@{at_tag(pan, am[ji])}")
        cond = ('满足——三方四正无煞忌会入' if not watchers
                else '不满足——煞忌会入：' + '、'.join(watchers))
        out.append(f"  - 雄宿乾元格：口径②（廉贞七杀@未同度且三方四正无煞忌，见吉无煞）触发——"
                   f"廉贞、七杀同度坐本宫[{palace_name(pan, '未')}·未]；见吉无煞条件：{cond}")
    if zhi in ('寅', '申') and am.get('廉贞') == zhi:
        opp = ZHI_ORDER[(ZHI_ORDER.index(zhi) + 6) % 12]
        oppm = '、'.join(mains_at(pan, opp)) or '无主星'
        out.append(f"  - 雄宿乾元格：口径③（廉贞@寅或申守命结构）触发——"
                   f"廉贞坐本宫[{palace_name(pan, zhi)}·{zhi}]，对宫{at_tag(pan, opp)}坐{oppm}")
        out.append(guard_ming_line(ming_zhi, zhi))
    return out


def tianxiang_jia_lines(pan, zhi):
    """B2 刑忌夹印（口径①巨门化忌+天梁夹/②擎羊+化忌夹）+B3 财荫夹印：星定宫=天相所在宫，各口径一行都报"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('天相') != zhi:
        return []
    n1, n2 = neigh_zhi(zhi)
    neigh = (n1, n2)
    ji = sihua_star(pan, '忌') or '?'
    lu = sihua_star(pan, '禄') or '?'
    liang, yang = am.get('天梁'), am.get('擎羊')
    jz, lz = am.get(ji), am.get(lu)
    head = f"天相@{at_tag(pan, zhi)}，邻支{n1}（{gong_tag(pan, n1)}）、{n2}（{gong_tag(pan, n2)}）"

    def note(star, z):
        """星落点+是否在邻支（星不在盘则注明）"""
        if not z:
            return f"{star}不在盘"
        return f"{star}@{at_tag(pan, z)}" + ('在邻支' if z in neigh else '不在邻支')

    out = []
    if ji == '巨门' and jz in neigh and liang in neigh and jz != liang:
        out.append(f"  - 刑忌夹印：口径①（巨门化忌+天梁夹天相）成立——{head}，"
                   f"化忌巨门@{at_tag(pan, jz)}与天梁@{at_tag(pan, liang)}分坐两邻支相夹")
    else:
        why = (f"本盘化忌星={note(ji, jz)}非巨门且不在邻支" if ji != '巨门'
               else f"化忌巨门@{at_tag(pan, jz) if jz else '不在盘'}不在邻支")
        out.append(f"  - 刑忌夹印：口径①（巨门化忌+天梁夹天相）不成立——{head}，"
                   f"{note('天梁', liang)}；{why}")
    if yang in neigh and jz in neigh and yang != jz:
        out.append(f"  - 刑忌夹印：口径②（擎羊+化忌夹天相）成立——{head}，"
                   f"擎羊@{at_tag(pan, yang)}与化忌{ji}@{at_tag(pan, jz)}分坐两邻支相夹")
    else:
        out.append(f"  - 刑忌夹印：口径②（擎羊+化忌夹天相）不成立——{head}，"
                   f"{note('擎羊', yang)}、化忌{note(ji, jz)}")
    if lz in neigh and liang in neigh and lz != liang:
        out.append(f"  - 财荫夹印：口径（化禄星+天梁夹天相）成立——{head}，"
                   f"化禄{lu}@{at_tag(pan, lz)}与天梁@{at_tag(pan, liang)}分坐两邻支相夹")
    else:
        out.append(f"  - 财荫夹印：口径（化禄星+天梁夹天相）不成立——{head}，"
                   f"化禄{note(lu, lz)}、{note('天梁', liang)}")
    return out


def yangtuo_jiaji_line(pan, zhi):
    """B4 羊陀夹忌：星定宫=被羊陀夹之宫（羊陀夹成立才报），判本宫坐化忌星"""
    am = pan.get('allStarMap', {}) or {}
    n1, n2 = neigh_zhi(zhi)
    yang, tuo = am.get('擎羊'), am.get('陀罗')
    if not (yang in (n1, n2) and tuo in (n1, n2) and yang != tuo):
        return []
    ji = sihua_star(pan, '忌')
    jz = am.get(ji)
    if jz == zhi:
        return [f"  - 羊陀夹忌：口径（羊陀夹+坐化忌星）成立——本宫[{palace_name(pan, zhi)}·{zhi}]"
                f"被擎羊@{at_tag(pan, yang)}、陀罗@{at_tag(pan, tuo)}相夹，且坐化忌{ji}"]
    jz_note = f"@{at_tag(pan, jz)}不坐本宫" if jz else '不在盘'
    return [f"  - 羊陀夹忌：口径（羊陀夹+坐化忌星）不成立——本宫[{palace_name(pan, zhi)}·{zhi}]"
            f"羊陀夹成立（擎羊@{at_tag(pan, yang)}、陀罗@{at_tag(pan, tuo)}相夹），但化忌{ji}{jz_note}"]


def mingzhu_lines(pan, ming_zhi, zhi):
    """B5 明珠出海：仅命宫文件报；未宫安命无正曜借丑宫同巨，丑借未为反向排除行"""
    if zhi != ming_zhi:
        return []
    if ming_zhi == '未':
        own = mains_at(pan, '未')
        if own:
            return [f"  - 明珠出海：口径（未宫安命无正曜借丑宫天同巨门）不成立——"
                    f"命宫@未有主星{'、'.join(own)}，不构成借宫"]
        borrow = mains_at(pan, '丑')
        names = '、'.join(borrow) if borrow else '无主星'
        if {'天同', '巨门'} <= set(borrow):
            return [f"  - 明珠出海：口径（未宫安命无正曜借丑宫天同巨门）成立——"
                    f"命宫@未无正曜，对宫丑（{gong_tag(pan, '丑')}）坐天同、巨门，借入成格"]
        return [f"  - 明珠出海：口径（未宫安命无正曜借丑宫天同巨门）不成立——"
                f"命宫@未无正曜，对宫丑（{gong_tag(pan, '丑')}）坐{names}非天同巨门"]
    if ming_zhi == '丑' and not mains_at(pan, '丑') and {'天同', '巨门'} <= set(mains_at(pan, '未')):
        return ["  - 明珠出海：口径（未宫安命无正曜借丑宫天同巨门）不成立——"
                "反向排除：命宫@丑无正曜借未宫天同巨门者不入此格"]
    return []


def luma_lines(pan, zhi):
    """B6 禄马交驰：星定宫=禄存与天马两宫（同内容各一行），同度/对照/三合三形态并列报"""
    am = pan.get('allStarMap', {}) or {}
    lc, tm = am.get('禄存'), am.get('天马')
    if not lc or not tm or zhi not in (lc, tm):
        return []
    mark = lambda b: '✓' if b else '✗'
    same = lc == tm
    dui = (ZHI_ORDER.index(lc) - ZHI_ORDER.index(tm)) % 12 == 6
    he = lc in trine_zhi(tm)
    return [f"  - 禄马交驰：禄存@{at_tag(pan, lc)}与天马@{at_tag(pan, tm)}——"
            f"同度（同宫）{mark(same)}/对照（相对两宫）{mark(dui)}/三合（共三方四正）{mark(he)}"
            f"（口径：禄存与天马交会三形态并列报，不拍板）"]


def tanlang_lines(pan, zhi):
    """B7 火贪格/铃贪格：星定宫=贪狼所在宫，正格（同度）/次格（会照）双口径各一行"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('贪狼') != zhi:
        return []
    q = trine_zhi(zhi)
    out = []
    for ge, sha in (('火贪格', '火星'), ('铃贪格', '铃星')):
        sz = am.get(sha)
        sz_pos = f"{sha}@{at_tag(pan, sz)}" if sz else f"{sha}不在盘"
        if sz == zhi:
            out.append(f"  - {ge}：口径①（贪狼与{sha}同度=正格）成立——{sz_pos}与贪狼同度")
        else:
            out.append(f"  - {ge}：口径①（贪狼与{sha}同度=正格）不成立——{sz_pos}非同度")
        if sz and sz in q[1:]:
            how = '对照会照' if sz == q[1] else '三合会照'
            out.append(f"  - {ge}：口径②（{sha}会照=次格）成立（次格）——{sz_pos}{how}贪狼@{at_tag(pan, zhi)}")
        else:
            out.append(f"  - {ge}：口径②（{sha}会照=次格）不成立——{sz_pos}不在贪狼三方四正")
    return out


def shizhong_lines(pan, ming_zhi, zhi):
    """B8 石中隐玉（触发制）：巨门@子/午触发；①会禄存或化禄（+守命行）②禄权科三化会（并列行）"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('巨门') != zhi or zhi not in ('子', '午'):
        return []
    q = trine_zhi(zhi)
    lu = sihua_star(pan, '禄')
    lc, hl = am.get('禄存'), am.get(lu) if lu else None
    n1 = f"禄存@{at_tag(pan, lc)}{'会入' if lc in q else '未会入'}" if lc else '禄存不在盘'
    n2 = f"化禄{lu}@{at_tag(pan, hl)}{'会入' if hl in q else '未会入'}" if lu and hl else f'化禄{lu or "?"}未会入'
    ok1 = (lc in q if lc else False) or (hl in q if hl else False)
    out = [f"  - 石中隐玉：口径①（巨门@子/午+会禄存或化禄）{'成立' if ok1 else '不成立'}——"
           f"巨门@{at_tag(pan, zhi)}，{n1}、{n2}",
           guard_ming_line(ming_zhi, zhi)]
    met2 = []
    for hua in ('禄', '权', '科'):
        s = sihua_star(pan, hua)
        z = am.get(s) if s else None
        met2.append((f"化{hua}{s}@{at_tag(pan, z)}会入" if z in q else
                     f"化{hua}{s}@{at_tag(pan, z) if z else '不在盘'}未会入") if s and z else
                    f"化{hua}{s or '?'}未会入")
    out.append(f"  - 石中隐玉：口径②（巨门@子/午+禄权科三化会，禄权科会版）"
               f"{'成立' if all('会入' in m for m in met2) else '不成立'}——巨门@{at_tag(pan, zhi)}，{'、'.join(met2)}")
    return out


def jiju_lines(pan, ming_zhi, zhi):
    """B9 机巨同临（触发制）：天机巨门@卯同度触发，附注会禄无煞与否，附守命条件行"""
    am = pan.get('allStarMap', {}) or {}
    if zhi != '卯' or am.get('天机') != '卯' or am.get('巨门') != '卯':
        return []
    q = trine_zhi('卯')
    lu = sihua_star(pan, '禄')
    lu_notes = []
    if am.get('禄存') in q:
        lu_notes.append(f"禄存@{at_tag(pan, am['禄存'])}会入")
    if lu and am.get(lu) in q:
        lu_notes.append(f"化禄{lu}@{at_tag(pan, am[lu])}会入")
    sha = [f"{s}@{at_tag(pan, am[s])}" for s in SHA_STATS if am.get(s) in q]
    return [f"  - 机巨同临：口径（天机巨门@卯同度）成立——天机、巨门同度坐本宫[{palace_name(pan, '卯')}·卯]",
            f"  - 附注（会禄无煞）：{'、'.join(lu_notes) if lu_notes else '禄存/化禄均未会入'}；"
            f"{'无煞曜会入' if not sha else '煞曜会入：' + '、'.join(sha)}",
            guard_ming_line(ming_zhi, '卯')]


def juri_lines(pan, ming_zhi, zhi):
    """B10 巨日同临（触发制）：太阳巨门@寅/申同度触发，附守命条件行"""
    am = pan.get('allStarMap', {}) or {}
    if zhi not in ('寅', '申') or am.get('太阳') != zhi or am.get('巨门') != zhi:
        return []
    return [f"  - 巨日同临：口径（太阳巨门@寅/申同度）成立——太阳、巨门同度坐本宫[{palace_name(pan, zhi)}·{zhi}]",
            guard_ming_line(ming_zhi, zhi)]


def lianzhen_lines(pan, zhi):
    """B11 廉贞清白（触发制三结构）：①廉杀@未+廉贞化禄 ②廉@寅/申+会禄存 ③廉@寅/申独坐对宫天府+见禄存"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('廉贞') != zhi:
        return []
    lu = sihua_star(pan, '禄')
    out = []
    if zhi == '未' and am.get('七杀') == '未':
        ok = lu == '廉贞'
        out.append(f"  - 廉贞清白：结构①（廉贞七杀@未同度且廉贞化禄）触发——"
                   f"廉贞、七杀同度坐本宫[{palace_name(pan, '未')}·未]；"
                   f"廉贞化禄：{'满足' if ok else f'不满足（本盘化禄星={lu or "?"}）'}")
    if zhi in ('寅', '申'):
        q = trine_zhi(zhi)
        lc = am.get('禄存')
        hui = lc in q if lc else False
        lc_note = f"禄存@{at_tag(pan, lc)}{'会入' if hui else '未会入'}" if lc else '禄存不在盘'
        out.append(f"  - 廉贞清白：结构②（廉贞@寅/申+会禄存）触发——廉贞坐本宫[{palace_name(pan, zhi)}·{zhi}]；"
                   f"会禄存：{'满足——' if hui else '不满足——'}{lc_note}")
        opp = ZHI_ORDER[(ZHI_ORDER.index(zhi) + 6) % 12]
        if am.get('天府') == opp and mains_at(pan, zhi) == ['廉贞']:
            out.append(f"  - 廉贞清白：结构③（廉贞@寅/申独坐对宫天府，见禄存）触发——"
                       f"廉贞独坐本宫[{palace_name(pan, zhi)}·{zhi}]，对宫{at_tag(pan, opp)}坐天府；"
                       f"见禄存：{'满足' if hui else '不满足'}——{lc_note}")
    return out


def lingchangtuowu_lines(pan, zhi):
    """B12 铃昌陀武：星定宫=武曲所在宫，结构条件+会照情况各报（原局/流曜冲起层级不判）"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('武曲') != zhi:
        return []
    q = trine_zhi(zhi)
    struct = zhi in ('辰', '戌')
    meets = []
    for s in ('铃星', '文昌', '陀罗'):
        z = am.get(s)
        meets.append(f"{s}@{at_tag(pan, z)}{'会入' if z in q else '未会入'}" if z else f"{s}不在盘")
    ok = struct and all('会入' in m for m in meets)
    return [f"  - 铃昌陀武：口径（武曲@辰/戌+铃昌陀会照）{'成立' if ok else '不成立'}——"
            f"武曲@{at_tag(pan, zhi)}{'居结构位' if struct else '非辰/戌'}；会照：{'、'.join(meets)}；"
            f"附注：原局/流曜冲起层级不判"]


def yincai_lines(pan, zhi):
    """B13 因财被劫/因财持刀：星定宫=武曲所在宫，各一行成立/不成立都报"""
    am = pan.get('allStarMap', {}) or {}
    if am.get('武曲') != zhi:
        return []
    q = trine_zhi(zhi)
    out = []
    huo, ling = am.get('火星'), am.get('铃星')
    duo = [n for n, z in (('火星', huo), ('铃星', ling)) if z == zhi]
    if duo:
        out.append(f"  - 因财被劫：口径（武曲与火星或铃星同度）成立——武曲@{at_tag(pan, zhi)}与{'、'.join(duo)}同度")
    else:
        det = '、'.join(f"{n}@{at_tag(pan, z)}非同度" for n, z in (('火星', huo), ('铃星', ling)) if z)
        out.append(f"  - 因财被劫：口径（武曲与火星或铃星同度）不成立——武曲@{at_tag(pan, zhi)}，{det or '火星/铃星均不在盘'}")
    sha_z = am.get('七杀')
    if sha_z == zhi:
        yang = am.get('擎羊')
        yang_note = f"擎羊@{at_tag(pan, yang)}{'会入' if yang in q else '未会入'}" if yang else '擎羊不在盘'
        ok = yang in q if yang else False
        note = '；卯/酉典型位：是' if zhi in ('卯', '酉') else ''
        out.append(f"  - 因财持刀：口径（武曲七杀同度+会擎羊，卯酉位典型）{'成立' if ok else '不成立'}——"
                   f"武曲、七杀同度@{at_tag(pan, zhi)}，{yang_note}{note}")
    else:
        out.append(f"  - 因财持刀：口径（武曲七杀同度+会擎羊，卯酉位典型）不成立——"
                   f"武曲@{at_tag(pan, zhi)}，七杀@{at_tag(pan, sha_z) if sha_z else '不在盘'}非同度")
    return out


def muya_lines(pan, zhi):
    """B14 木压雷惊（触发制）：武曲七杀@卯同度触发，注明煞忌会入情况"""
    am = pan.get('allStarMap', {}) or {}
    if zhi != '卯' or am.get('武曲') != '卯' or am.get('七杀') != '卯':
        return []
    q = trine_zhi('卯')
    ji = sihua_star(pan, '忌')
    watchers = [f"{s}@{at_tag(pan, am[s])}" for s in SHA_STATS if am.get(s) in q]
    if ji and am.get(ji) in q:
        watchers.append(f"化忌{ji}@{at_tag(pan, am[ji])}")
    return [f"  - 木压雷惊：口径（武曲七杀@卯同度+见煞忌）触发——"
            f"武曲、七杀同度坐本宫[{palace_name(pan, '卯')}·卯]；"
            f"煞忌会入：{'、'.join(watchers) if watchers else '无'}"]


def b_geju_lines(pan, ming_zhi, zhi):
    """B 级 14 项组装（按编号序）；星定宫制项内部自判宾语星是否在本宫"""
    out = []
    out += xiongsu_lines(pan, ming_zhi, zhi)        # B1 雄宿乾元格
    out += tianxiang_jia_lines(pan, zhi)            # B2 刑忌夹印 + B3 财荫夹印
    out += yangtuo_jiaji_line(pan, zhi)             # B4 羊陀夹忌
    out += mingzhu_lines(pan, ming_zhi, zhi)        # B5 明珠出海（仅命宫文件）
    out += luma_lines(pan, zhi)                     # B6 禄马交驰
    out += tanlang_lines(pan, zhi)                  # B7 火贪格/铃贪格
    out += shizhong_lines(pan, ming_zhi, zhi)       # B8 石中隐玉
    out += jiju_lines(pan, ming_zhi, zhi)           # B9 机巨同临
    out += juri_lines(pan, ming_zhi, zhi)           # B10 巨日同临
    out += lianzhen_lines(pan, zhi)                 # B11 廉贞清白
    out += lingchangtuowu_lines(pan, zhi)           # B12 铃昌陀武
    out += yincai_lines(pan, zhi)                   # B13 因财被劫/因财持刀
    out += muya_lines(pan, zhi)                     # B14 木压雷惊
    return out


# ═════════════════════════════════════
#  会照明细（原局全盘事实表与流盘 input 共用）
# ═════════════════════════════════════

def sha_stats_line(pan, quartet):
    met, unmet = [], []
    am = pan.get('allStarMap', {}) or {}
    for s in SHA_STATS:
        z = am.get(s)
        if z in quartet:
            met.append(f"{s}@{at_tag(pan, z)}")
        else:
            unmet.append(s)
    line = "- 命宫三方四正煞曜统计：" + ("、".join(met) if met else "无")
    if unmet:
        line += "；未会入：" + "、".join(unmet)
    return line


def trine_block(pan, name, zhi):
    q = trine_zhi(zhi)
    lines = [f"- 本宫[{name}·{zhi}]三方四正（对宫{q[1]}、三合{q[2]}{q[3]}）星曜："]
    for z in q:
        stars = stars_at(pan, z)
        item = f"  - {palace_name(pan, z)}[{z}]：" + ("、".join(stars) if stars else "无星曜")
        if z == zhi and not mains_at(pan, z):
            opp = ZHI_ORDER[(ZHI_ORDER.index(z) + 6) % 12]
            item += (f"（空宫，借对宫[{opp}·{palace_name(pan, opp)}]主星："
                     f"{'、'.join(mains_at(pan, opp))}）")
        lines.append(item)
    return lines


def six_lucky_line(pan, quartet):
    am = pan.get('allStarMap', {}) or {}
    met = [f"{s}@{at_tag(pan, am[s])}" for s in SIX_LUCKY if am.get(s) in quartet]
    return "- 六吉会照：" + ("、".join(met) if met else "无")


# ═════════════════════════════════════
#  组装入口（原局链 prep_inputs / 流盘链 liupan 同源调用）
# ═════════════════════════════════════

def geju_lines(pan, name, zhi):
    """格局核验节行组：A级 22 项（夹型/落宫/同度/会齐/朝拱）+ B级 14 项，逐宫判。"""
    ming_zhi = next(z for z, n in (pan.get('twelvePalaces', {}) or {}).items() if n == '命宫')
    mq = trine_zhi(ming_zhi)
    lines = [
        "- 本命格局核验：",
        pattern_line(pan, mq, "机月同梁", ["天机", "天同", "太阴", "天梁"]),
        pattern_line(pan, mq, "杀破狼", ["七杀", "破军", "贪狼"]),
        pattern_line(pan, mq, "府相朝垣", ["天府", "天相"]),
        sandwich_line(pan, zhi, "火铃夹", "火星", "铃星"),
        sandwich_line(pan, zhi, "羊陀夹", "擎羊", "陀罗"),
    ]
    lu_star = ((pan.get('siHua', {}) or {}).get('禄') or {}).get('star')
    for label, a, b in SANDWICH_PATTERNS:
        if b is None:
            b = lu_star or '化禄'
        lines.append(sandwich_line(pan, zhi, label, a, b))
    for label, star, pz in PALACE_STAR_PATTERNS:
        lines += palace_star_line(pan, ming_zhi, zhi, label, star, pz)
    for label, combos in COMBO_PATTERNS:
        lines += combo_line(pan, ming_zhi, zhi, label, combos)
    yang_variants = [("阳梁昌禄（禄存口径）", ["太阳", "天梁", "文昌", "禄存"])]
    if lu_star:
        yang_variants.append(("阳梁昌禄（化禄口径）", ["太阳", "天梁", "文昌", lu_star]))
    for label, wanted in yang_variants:
        hit = pattern_gong_line(pan, name, zhi, label, wanted)
        if hit:
            lines.append(hit)
    lines.append(baiguan_line(pan, name, zhi))
    lines += b_geju_lines(pan, ming_zhi, zhi)
    return lines
