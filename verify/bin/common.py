# -*- coding: utf-8 -*-
"""印证学习库共享工具：数据目录三级解析 + 分片枚举。零第三方依赖。"""
import json
import os
import re
import sys

SHARD_RE = re.compile(r"^events_(.+)-(\d{3})\.jsonl$")

# 待验证预测过期天数（单一真源：check_pending 过期关闭 / fill_brief_prompt 尾节过滤 共同 import）
EXPIRE_DAYS = 7

CATEGORIES = [
    "交易盈亏", "出行", "健康", "口舌是非",
    "意外", "情绪波动", "重要决策", "人际事件",
]
RESULTS = ["预测准确", "预测不准", "符合", "部分", "不符", "待验"]  # 万物类象原则：事件 vs 盘面严格二元（符合/不符），不设「无预测对照」

# 十二宫名（structure_snapshot.palaces 键同款，命宫带"宫"字）
PALACE_NAMES = ["命宫", "父母", "福德", "田宅", "官禄", "仆役",
                "迁移", "疾厄", "财帛", "子女", "夫妻", "兄弟"]
# 天然宫位类：category→默认宫位（theory 可覆盖）；事项域类不映射（theory 唯一源）
CATEGORY_PALACE_MAP = {"交易盈亏": "财帛", "健康": "疾厄",
                       "出行": "迁移", "情绪波动": "福德"}
# theory ①段宫位判定肯定式模式（归X宫/判定为X宫/→X宫/X宫
_PALACE_ALT = "|".join(PALACE_NAMES)
_POSITIVE_PATTERNS = [
    re.compile(r"归(%s)宫" % _PALACE_ALT),
    re.compile(r"判定为?(%s)宫" % _PALACE_ALT),
    re.compile(r"→(%s)宫" % _PALACE_ALT),
    re.compile(r"(%s)宫（规则判定" % _PALACE_ALT),
]
# 否定上下文：宫名前 4 字符内含否定词，或宫名后紧跟"虽"
_NEGATIVE_BEFORE = ("不归", "非", "不属", "不进", "不在")


def extract_theory_palace(theory):
    """theory ①段宫位判定提取 -> (首个判定宫名 or None, 多重肯定否)。
    肯定式模式优先；否定上下文（不归X宫/非X宫/X宫虽…）内宫名不取。"""
    m = re.search(r"①[^②③④]*", theory or "")
    if not m:
        return None, False
    seg = m.group(0)
    matches = []
    seen = set()
    for pat in _POSITIVE_PATTERNS:
        for pm in pat.finditer(seg):
            name = pm.group(1)
            start = pm.start(1)
            before = seg[max(0, start - 4):start]
            if any(before.endswith(n) or n in before for n in _NEGATIVE_BEFORE):
                continue
            if seg[pm.end(1):pm.end(1) + 1] == "虽":
                continue
            if name not in seen:
                seen.add(name)
                matches.append((start, name))
    if not matches:
        return None, False
    matches.sort()
    positives = [name for _, name in matches]
    return positives[0], len(positives) > 1


def resolve_event_palace(category, theory):
    """落账/回填共用的 event_palace 判定 -> (宫名 or None, palace_ambiguous, 警告 or None)。
    天然宫位类=映射默认+theory 覆盖；事项域类=theory 唯一源；
    theory 无判定或多重肯定取首个并标 ambiguous。"""
    t_palace, multi = extract_theory_palace(theory)
    default = CATEGORY_PALACE_MAP.get(category)
    ambiguous = False
    warn = None
    if multi:
        ambiguous = True
    if t_palace:
        palace = t_palace
        if default and default != t_palace:
            warn = "theory 宫位判定(%s)与类目映射(%s)不一致，以 theory 为准" % (t_palace, default)
    elif default:
        palace = default
    else:
        palace = None
        ambiguous = True
    return palace, ambiguous, warn


def find_anchors_zero_root(start_dir):
    """向上查找 anchors.json，返回 ZERO_ROOT 值；缺席返回 None。"""
    cur = os.path.abspath(start_dir)
    while True:
        path = os.path.join(cur, "anchors.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = json.load(f).get("ZERO_ROOT")
                if val:
                    return val
            except (OSError, ValueError):
                return None
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def resolve_data_dir(cli_data_dir):
    """三级解析：--data-dir > anchors 定位 > 技能根 verify\\data\\。"""
    if cli_data_dir:
        return os.path.abspath(cli_data_dir)
    zero_root = find_anchors_zero_root(os.path.dirname(os.path.abspath(__file__)))
    if zero_root:
        return os.path.join(zero_root, "output", "_verify")
    skill_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(skill_root, "verify", "data")


def ensure_data_dir(data_dir):
    """首建数据目录时写入 .gitignore（数据不入 git）。"""
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    gi = os.path.join(data_dir, ".gitignore")
    if not os.path.isfile(gi):
        with open(gi, "w", encoding="utf-8", newline="\n") as f:
            f.write("*\n!.gitignore\n")


def list_shards(data_dir, owner=None):
    """枚举分片。owner 给定时精确匹配（正则分组锚定，防前缀碰撞），
    返回 [(owner, 片号, 文件名)]，owner 内按片号数字序排序。"""
    out = []
    if not os.path.isdir(data_dir):
        return out
    for name in os.listdir(data_dir):
        m = SHARD_RE.match(name)
        if not m:
            continue
        o, num = m.group(1), int(m.group(2))
        if owner is not None and o != owner:
            continue
        out.append((o, num, name))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def shard_size(default=5000):
    try:
        return max(1, int(os.environ.get("VERIFY_SHARD_SIZE", default)))
    except ValueError:
        return default


def out(msg):
    print(msg)
