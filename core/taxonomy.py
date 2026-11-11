# -*- coding: utf-8 -*-
"""紫微斗数星曜分类与排序优先级

（含对星拆分后的杂曜口径）
口径原则：常量与 rank 函数逐行对应，不做任何"优化"
"""

MAIN_STARS = ['紫微', '天机', '太阳', '武曲', '天同', '廉贞', '天府', '太阴', '贪狼', '巨门', '天相', '天梁', '七杀', '破军']

JI_GROUPS = {
    '左辅 右弼': ['左辅', '右弼'],
    '文昌 文曲': ['文昌', '文曲'],
    '天魁 天钺': ['天魁', '天钺'],
    '禄存 天马': ['禄存', '天马'],
}

SHA_GROUPS = {
    '擎羊 陀罗': ['擎羊', '陀罗'],
    '火星 铃星': ['火星', '铃星'],
    '地空 地劫': ['地空', '地劫'],
}

# 杂曜组合（topic 为成对名称，如 天伤 天使）
ZA_GROUPS = {
    '天伤 天使': ['天伤', '天使'],
    '天刑 天姚': ['天刑', '天姚'],
    '天哭 天虚': ['天哭', '天虚'],
    '红鸾 天喜': ['红鸾', '天喜'],
    '三台 八座': ['三台', '八座'],
    '龙池 凤阁': ['龙池', '凤阁'],
    '孤辰 寡宿': ['孤辰', '寡宿'],
    '恩光 天贵': ['恩光', '天贵'],
    '台辅 封诰': ['台辅', '封诰'],
    '天官 天福': ['天官', '天福'],
    '年解 月解': ['年解', '月解'],
    '截空 旬空': ['截空', '旬空'],
    '天德 月德': ['天德', '月德'],
}

# 杂曜（与前端排盘页 zayaoOrder 保持一致，共 40 颗）
ZA_STARS = [
    '截空', '蜚廉', '台辅', '天姚', '天官', '大耗', '龙德', '天才', '天月', '天虚',
    '天哭', '天厨', '劫杀', '破碎', '月德', '华盖', '龙池', '封诰', '天刑', '三台',
    '红鸾', '孤辰', '月解', '天使', '天空', '阴煞', '天伤', '恩光', '天寿', '天巫',
    '旬空', '寡宿', '年解', '凤阁', '八座', '天贵', '天福', '天喜', '咸池', '天德',
]

ZHI_ORDER = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

PALACES = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '仆役', '官禄', '田宅', '福德', '父母']

# 呈现顺序（analyzeAllPalacesParallel 的 desiredOrder）
DESIRED_ORDER = ['命宫', '官禄', '财帛', '福德', '迁移', '疾厄', '田宅', '父母', '夫妻', '子女', '兄弟', '仆役']

import re

# 六十星系键（v2.10 第四类匹配）：主星空格连名 + 可选地支对括号，如 '武曲 贪狼（丑、未）'、'紫微（子、午）'、'紫微'
XINGXI_RE = re.compile(r'^(?:' + '|'.join(MAIN_STARS) + r')(?:\s(?:'
                       + '|'.join(MAIN_STARS) + r'))*(?:（[^）]*）)?$')


def get_parent_topic_rank(pt):
    """照抄 PHP getParentTopicRank：数字越小越靠前（v2.10 增六十星系 -10 最高档）"""
    # 六十星系切片排最前（正曜性质 0 之前）
    if XINGXI_RE.match(pt):
        return -10

    fu_stars = []
    for stars in JI_GROUPS.values():
        fu_stars.extend(stars)
    sha_stars = []
    for stars in SHA_GROUPS.values():
        sha_stars.extend(stars)

    # 宫位组合：例如 命宫 紫微 破军
    for palace in PALACES:
        if re.match('^' + re.escape(palace) + r'(\s+|$)', pt):
            return 31

    # 提取基础 topic 与后缀类型
    base = None
    suffix = None
    m = re.match(r'^(.*)性质$', pt)
    if m:
        base, suffix = m.group(1), '性质'
    else:
        m = re.match(r'^(.*)(化禄|化权|化科|化忌)$', pt)
        if m:
            base, suffix = m.group(1), '四化'
        else:
            m = re.match(r'^(.*)格局$', pt)
            if m:
                base, suffix = m.group(1), '格局'

    if base is None:
        return 99

    # 正曜
    if base in MAIN_STARS:
        if suffix == '性质':
            return 0
        if suffix == '四化':
            return 1
        if suffix == '格局':
            return 2

    # 辅曜（含组合名与单星）
    if base in fu_stars or base in JI_GROUPS:
        if suffix == '性质':
            return 10
        if suffix == '四化':
            return 11
        if suffix == '格局':
            return 12

    # 煞曜（含组合名与单星）
    if base in sha_stars or base in SHA_GROUPS:
        if suffix == '性质':
            return 20
        if suffix == '格局':
            return 22

    # 宫位性质
    if base in PALACES:
        if suffix == '性质':
            return 30
        return 99

    # 杂曜组合（对星）
    for group in ZA_GROUPS:
        if base == group:
            if suffix == '性质':
                return 40
            if suffix == '格局':
                return 42
            return 99  # 无后缀，如 天伤 天使

    # 杂曜（单个星）
    if base in ZA_STARS:
        if suffix == '性质':
            return 40
        if suffix == '格局':
            return 42

    return 99
