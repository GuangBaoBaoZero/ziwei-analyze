# -*- coding: utf-8 -*-
"""紫微斗数知识库切片检索器（规则匹配，ziwei-analyze 原味）

功能对应 formatPalaceContext / getForcedSlicesForPalace / getPalaceSingleStarSlices
         / getPalaceComboSlices / buildPalaceKbContext
不调用任何 AI、不联网——只负责"检索"。

用法：
  python retrieve.py --pan pan.json --out ctx.json
  python retrieve.py --pan pan.json            # 输出到 stdout（前 2000 字预览）
"""

import json
import re
import sys
import os
import hashlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy import (MAIN_STARS, JI_GROUPS, SHA_GROUPS, ZA_GROUPS, ZA_STARS,
                      ZHI_ORDER, PALACES, DESIRED_ORDER, get_parent_topic_rank)

_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 知识库选择：--kb 取库标识；命令行 > 环境变量 ZIWEI_KB > 默认 open
KB_OPTIONS = {
    'open': os.path.join(_SKILL_ROOT, 'data', 'zeropro_open_kb.json'),
}
DEFAULT_KB = 'open'
ENV_KB_VAR = 'ZIWEI_KB'

MAX_CONTEXT_CHARS = 80000  # 每宫上下文上限（同 PHP buildPalaceKbContext）


def resolve_default_path():
    """按解析链（env ZIWEI_KB > 默认 open）解析库路径"""
    kb_name = os.environ.get(ENV_KB_VAR) or DEFAULT_KB
    if kb_name not in KB_OPTIONS:
        raise SystemExit(f'错误：未知知识库标识 "{kb_name}"（可选：{" / ".join(KB_OPTIONS)}）')
    return KB_OPTIONS[kb_name]


def load_kb_data(path=None):
    """照抄 PHP loadKbData：兼容 {"slices": [...]} 包装；path 缺省按 env/默认库自解析"""
    if path is None:
        path = resolve_default_path()
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get('slices'), list):
        return data['slices']
    return data if isinstance(data, list) else []


def clean_star_name(star_with_brightness):
    """照抄 PHP cleanStarName：去亮度括号，如 紫微(庙) -> 紫微"""
    return re.sub(r'\(.*\)', '', star_with_brightness)


def build_indexes(kb_data):
    """预建索引（构建一次全类匹配共用，切片保持 kb 原序——命中顺序与旧线性扫一致）"""
    by_topic = {}
    by_parent = {}
    for s in kb_data:
        by_topic.setdefault(s.get('topic', ''), []).append(s)
        by_parent.setdefault(s.get('parent_topic', ''), []).append(s)
    return {'by_topic': by_topic, 'by_parent': by_parent}


# ═══════════════════════════════════════
#  命盘上下文格式化（照抄 formatPalaceContext）
# ═══════════════════════════════════════

def format_palace_context(pan_data, palace_zhi):
    pan = pan_data.get('pan', {})
    zhi_to_gong = pan.get('twelvePalaces', {}) or {}
    all_star_map = pan.get('allStarMap', {}) or {}
    brightness = pan.get('starBrightness', {}) or {}
    aux_brightness = pan.get('auxStarBrightness', {}) or {}
    sihua = pan.get('siHua', {}) or {}
    ming_shen = pan.get('mingShen', {}) or {}

    palace_name = zhi_to_gong.get(palace_zhi, palace_zhi)

    ji_members = {m for members in JI_GROUPS.values() for m in members}
    sha_members = {m for members in SHA_GROUPS.values() for m in members}

    stars = {'main': [], 'ji': [], 'sha': [], 'za': [], 'sihua': []}
    for star, zhi in all_star_map.items():
        if zhi != palace_zhi:
            continue
        if star in MAIN_STARS:
            b = brightness.get(star, '')
            stars['main'].append(f"{star}({b})" if b else star)
        else:
            if star in ji_members:
                b = aux_brightness.get(star, '')
                stars['ji'].append(f"{star}({b})" if b else star)
            elif star in sha_members:
                b = aux_brightness.get(star, '')
                stars['sha'].append(f"{star}({b})" if b else star)
            else:
                # 不在任何已知分组中的星，仍归入杂曜显示，避免遗漏
                stars['za'].append(star)

    for hua_name, info in sihua.items():
        if (info or {}).get('gong', '') == palace_zhi:
            stars['sihua'].append(f"{(info or {}).get('star', '')}化{hua_name}")

    # 空宫借对宫
    stars['borrowed_main'] = []
    stars['borrowed_sihua'] = []
    opp_zhi = ''
    if not stars['main']:
        try:
            zhi_idx = ZHI_ORDER.index(palace_zhi)
            opp_zhi = ZHI_ORDER[(zhi_idx + 6) % 12]
        except ValueError:
            opp_zhi = ''
        if opp_zhi:
            for star, zhi in all_star_map.items():
                if zhi != opp_zhi:
                    continue
                if star in MAIN_STARS:
                    b = brightness.get(star, '')
                    stars['borrowed_main'].append(f"{star}({b})" if b else star)
            for hua_name, info in sihua.items():
                if (info or {}).get('gong', '') == opp_zhi:
                    stars['borrowed_sihua'].append(f"{(info or {}).get('star', '')}化{hua_name}")

    context = f"【{palace_name}宫·{palace_zhi}】\n"
    if stars['main']:
        context += "主星：" + "、".join(stars['main']) + "\n"
    if stars['borrowed_main']:
        opp_palace_name = zhi_to_gong.get(opp_zhi, opp_zhi)
        context += f"空宫：借对宫（{opp_palace_name}·{opp_zhi}）主星：" + "、".join(stars['borrowed_main']) + "\n"
    if stars['ji']:
        context += "辅曜：" + "、".join(stars['ji']) + "\n"
    if stars['sha']:
        context += "煞曜：" + "、".join(stars['sha']) + "\n"
    if stars['za']:
        context += "杂曜：" + "、".join(stars['za']) + "\n"
    if stars['sihua']:
        context += "四化：" + "、".join(stars['sihua']) + "\n"
    if stars['borrowed_sihua']:
        opp_palace_name = zhi_to_gong.get(opp_zhi, opp_zhi)
        context += f"借对宫（{opp_palace_name}·{opp_zhi}）四化：" + "、".join(stars['borrowed_sihua']) + "\n"

    if ming_shen.get('ming', '') == palace_zhi:
        context += "（命宫）\n"
    if ming_shen.get('shen', '') == palace_zhi:
        context += "（身宫）\n"

    return {'name': palace_name, 'zhi': palace_zhi, 'context': context, 'raw_stars': stars}


# ═══════════════════════════════════════
#  三类匹配（对拍原版行为；v2.10 改查预建索引，命中与切片顺序同旧线性扫）
# ═══════════════════════════════════════

def get_forced_slices(indexes, palace_info):
    """照抄 getForcedSlicesForPalace：强制匹配（v2.10 索引版）"""
    by_topic = indexes['by_topic']
    by_parent = indexes['by_parent']
    forced = []
    raw_stars = palace_info.get('raw_stars', {})
    palace_name = palace_info.get('name', '')

    # 宫位性质
    if palace_name:
        for s in by_topic.get(palace_name, ()):
            if s.get('parent_topic', '') == palace_name + ' 性质':
                forced.append(s)

    star_set = set()
    for cat in ('main', 'ji', 'sha', 'za'):
        for s in raw_stars.get(cat, []):
            star_set.add(clean_star_name(s))

    # 正曜性质（含空宫借对宫主星）
    main_stars = raw_stars.get('main', []) + raw_stars.get('borrowed_main', [])
    for star_with_b in main_stars:
        star = clean_star_name(star_with_b)
        for s in by_topic.get(star, ()):
            if s.get('parent_topic', '') == star + '性质':
                forced.append(s)

    # 正曜格局（含空宫借对宫主星）
    for star_with_b in main_stars:
        star = clean_star_name(star_with_b)
        for s in by_topic.get(star, ()):
            if s.get('parent_topic', '') == star + '格局':
                forced.append(s)

    # 辅曜组合性质/格局（同 topic 单扫保 kb 原序，与旧单遍线性扫一致）
    for group, members in JI_GROUPS.items():
        matched = any(m in star_set for m in members)
        if matched:
            for s in by_topic.get(group, ()):
                pt = s.get('parent_topic', '')
                if pt == group + '性质' or pt == group + '格局':
                    forced.append(s)

    # 煞曜组合性质/格局
    for group, members in SHA_GROUPS.items():
        matched = any(m in star_set for m in members)
        if matched:
            for s in by_topic.get(group, ()):
                pt = s.get('parent_topic', '')
                if pt == group + '性质' or pt == group + '格局':
                    forced.append(s)

    # 杂曜（知识库中 parent_topic 直接等于 topic，如 天姚 -> 天姚）
    for star_with_b in raw_stars.get('za', []):
        star = clean_star_name(star_with_b)
        for s in by_topic.get(star, ()):
            if s.get('parent_topic', '') == star:
                forced.append(s)

    # 杂曜组合（对星）：如 天伤 天使、天刑 天姚 等
    for group, members in ZA_GROUPS.items():
        matched = any(m in star_set for m in members)
        if matched:
            for s in by_topic.get(group, ()):
                if s.get('parent_topic', '') == group:
                    forced.append(s)

    # 四化（含借对宫四化）
    # 辅曜组合成员 -> 组合名 映射（如 文昌 -> 文昌 文曲）
    star_to_group = {}
    for group, members in JI_GROUPS.items():
        for m in members:
            star_to_group[m] = group

    all_sihua = raw_stars.get('sihua', []) + raw_stars.get('borrowed_sihua', [])
    for sihua_str in all_sihua:
        m = re.match(r'^(.*)化(禄|权|科|忌)$', sihua_str)
        if not m:
            continue
        star = m.group(1)
        target_pt = star + '化' + m.group(2)
        for s in by_parent.get(target_pt, ()):
            topic = s.get('topic', '')
            # 正曜四化：topic 为单星
            if topic == star:
                forced.append(s)
            # 辅曜组合四化：topic 为组合名（如 文昌 文曲），parent_topic 为单星四化
            elif star in star_to_group and topic == star_to_group[star]:
                forced.append(s)

    return forced


def get_palace_single_star_slices(indexes, palace_info):
    """照抄 getPalaceSingleStarSlices：宫位单星（不带地支限定，如 仆役 天机）"""
    by_topic = indexes['by_topic']
    palace_name = palace_info.get('name', '')
    if palace_name == '':
        return []

    raw_stars = palace_info.get('raw_stars', {})
    all_stars = (raw_stars.get('main', []) + raw_stars.get('ji', []) +
                 raw_stars.get('sha', []) + raw_stars.get('za', []) +
                 raw_stars.get('borrowed_main', []))
    star_names = {clean_star_name(s) for s in all_stars}
    if not star_names:
        return []

    matched = []
    pattern = '^' + re.escape(palace_name) + r'\s+([^\s]+)$'
    for s in by_topic.get(palace_name, ()):
        pt = s.get('parent_topic', '').strip()
        m = re.match(pattern, pt)
        if m and m.group(1) in star_names:
            matched.append(s)
    return matched


def get_palace_combo_slices(indexes, palace_info):
    """照抄 getPalaceComboSlices：宫位主星组合 + 地支限定"""
    by_topic = indexes['by_topic']
    palace_name = palace_info.get('name', '')
    zhi = palace_info.get('zhi', '')
    if palace_name == '' or zhi == '':
        return []

    raw_stars = palace_info.get('raw_stars', {})
    src = raw_stars.get('main', []) + raw_stars.get('borrowed_main', [])
    main_stars = sorted(clean_star_name(s) for s in src)
    if not main_stars:
        return []

    matched = []
    pattern = '^' + re.escape(palace_name) + r'\s+(.+?)(?:（([子丑寅卯辰巳午未申酉戌亥、]+)）)?$'
    for s in by_topic.get(palace_name, ()):
        pt = s.get('parent_topic', '').strip()
        m = re.match(pattern, pt)
        if not m:
            continue
        # 只处理带地支限定的切片
        if not m.group(2):
            continue
        stars = sorted(m.group(1).split())
        if stars != main_stars:
            continue
        # 地支 OR 匹配：本宫地支须在限定列表中
        if zhi not in m.group(2):
            continue
        matched.append(s)
    return matched


# ═════════════════════════════════════
#  第四类匹配：六十星系（v2.10 新增）
# ═════════════════════════════════════

def _xingxi_key_star_set(key):
    """六十星系 parent_topic 键（如 '武曲 贪狼（丑、未）'）的地支括号前星集合"""
    return frozenset(key.split('（', 1)[0].split())


def get_star_system_slices(indexes, palace_info):
    """六十星系切片：L2 专论（星集合+地支对键，星系组合唯一确定地支对故地支不精确匹配）
    → L1 总论（每颗主星裸键，含借星）。空宫用借宫主星，同法。"""
    by_parent = indexes['by_parent']
    raw_stars = palace_info.get('raw_stars', {})
    mains = [clean_star_name(s) for s in raw_stars.get('main', []) + raw_stars.get('borrowed_main', [])]
    out = []
    if not mains:
        return out

    star_set = frozenset(mains)
    # L2 专论：by_parent 键中找"星集合相同且含（"的键（星名排序集合匹配，地支不限）
    for key, slices in by_parent.items():
        if '（' not in key or _xingxi_key_star_set(key) != star_set:
            continue
        out.extend(s for s in slices if s.get('topic', '') == '六十星系')

    # L1 总论：每颗主星裸键（无地支括号）
    for star in mains:
        out.extend(s for s in by_parent.get(star, ())
                   if s.get('topic', '') == '六十星系')

    return out


# ═══════════════════════════════════════
#  组装（照抄 buildPalaceKbContext）
# ═══════════════════════════════════════

def _slice_fp(s):
    return f"{s.get('topic', '')}|{s.get('parent_topic', '')}|{hashlib.md5((s.get('content', '') or '').encode('utf-8')).hexdigest()}"


def build_palace_kb_context(indexes, palace_info):
    """四路合并（v2.10：星系切片在前）→ 去重 → rank 排序 → 80000 字符截断"""
    forced = (get_star_system_slices(indexes, palace_info) +
              get_forced_slices(indexes, palace_info) +
              get_palace_single_star_slices(indexes, palace_info) +
              get_palace_combo_slices(indexes, palace_info))

    # 去重
    seen = set()
    unique = []
    for s in forced:
        key = _slice_fp(s)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # 排序：性质 > 四化 > 格局 > 辅曜 > 煞曜 > ...
    unique.sort(key=lambda s: (get_parent_topic_rank(s.get('parent_topic', '')), s.get('id', '')))

    # 构建上下文，限制 80000 字符
    context = f"【知识库·{palace_info['name']}宫参考资料】\n\n"
    total = len(context)
    blocks = []
    for s in unique:
        content = s.get('content', '') or ''
        # 不再单片截断，保留完整切片原文
        block = f"◆ {s.get('topic', '')} · {s.get('parent_topic', '')}\n"
        block += content + "\n"
        if s.get('source'):
            block += f"（出处：{s['source']}）\n"
        block += "\n"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        total += len(block)

    return context + ''.join(blocks), unique


# ═══════════════════════════════════════
#  CLI
# ═══════════════════════════════════════

def resolve_kb(args):
    """库标识解析：命令行 > 环境变量 ZIWEI_KB > 默认 open；返回 (标识, 路径)"""
    kb_name = args.kb or os.environ.get(ENV_KB_VAR) or DEFAULT_KB
    if kb_name not in KB_OPTIONS:
        raise SystemExit(f'错误：未知知识库标识 "{kb_name}"（可选：{" / ".join(KB_OPTIONS)}）')
    return kb_name, KB_OPTIONS[kb_name]


def main():
    ap = argparse.ArgumentParser(description='紫微知识库规则检索（ziwei-analyze 原味）')
    ap.add_argument('--pan', required=True, help='命盘 JSON 路径（paipan.js 输出格式）')
    ap.add_argument('--kb', choices=sorted(KB_OPTIONS), default=None,
                    help=f'知识库标识（默认 {DEFAULT_KB}；环境变量 {ENV_KB_VAR} 同义备选，命令行优先）')
    ap.add_argument('--out', default=None, help='输出 ctx.json 路径（缺省打印预览）')
    args = ap.parse_args()

    kb_name, kb_path = resolve_kb(args)
    with open(args.pan, 'r', encoding='utf-8') as f:
        pan_data = json.load(f)
    kb = load_kb_data(kb_path)
    indexes = build_indexes(kb)
    print(f'知识库 [{kb_name}] {len(kb)} 片（{os.path.basename(kb_path)}）', file=sys.stderr)

    # 按 DESIRED_ORDER 输出十二宫
    palace_to_zhi = {}
    for zhi, name in (pan_data.get('pan', {}).get('twelvePalaces', {}) or {}).items():
        palace_to_zhi[name] = zhi

    result = {}
    for palace_name in DESIRED_ORDER:
        zhi = palace_to_zhi.get(palace_name) or palace_to_zhi.get(palace_name.rstrip('宫'))
        if not zhi:
            continue
        info = format_palace_context(pan_data, zhi)
        ctx, unique = build_palace_kb_context(indexes, info)
        result[palace_name] = {
            'name': info['name'],
            'zhi': info['zhi'],
            'kb': kb_name,
            'context_text': info['context'],
            'raw_stars': info['raw_stars'],
            'slice_count': len(unique),
            'slice_ids': [s.get('id', '') for s in unique],
            'context_chars': len(ctx),
            'kb_context': ctx,
        }
        print(f"{palace_name}({zhi}): {len(unique)} 片 / {len(ctx)} 字符", file=sys.stderr)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'已写入 {args.out}', file=sys.stderr)
    else:
        first = next(iter(result.values()))
        print(first['kb_context'][:2000])


if __name__ == '__main__':
    main()
