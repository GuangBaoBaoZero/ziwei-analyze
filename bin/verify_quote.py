#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""古籍引文验证（ziwei 简报产线质检件）。

功能：引文片段 → 按书名定位外部古籍底本 → 直读原文 → 四层递进匹配 → 输出命中证据。
四层匹配：①原样 ②标点归一 ③简繁归一（内置高频对照小表，双向归一到简边）④全文拼接 fallback（跨行命中报行号区间）；
⑤兜底「疑似异文命中」：四层全败后滑窗找最小字符差并列差异对照（如 斯↔是），标"疑似"由人裁决——异文是古籍零命中的最常见真实原因。

为什么需要②③：source 层 txt 为 GB18030 编码+繁体正文，简报引文多为简体——裸 grep 零命中≠引文捏造。

用法：
  python verify_quote.py --quote "持而盈之，不如其已" --book "道德真经"
  python verify_quote.py --quote "天将降大任于斯人也" --book "孟子" --layer source
  python verify_quote.py --quote "持而盈之" --book "道德真经" --layer corpus --json
参数：
  --quote   必填。引文片段（≥4 字为宜）
  --book    必填。书名关键词（文件名 glob 匹配；支持 * 通配符）
  --layer   source|corpus，默认 source（source=GB18030 txt；corpus=UTF-8 md）
  --first N 输出前 N 个命中文件（默认 10），总数另报
  --json    机器可读输出（供子代理/验收脚本消费）
输出：命中文件路径+行号+原文行+判定；按底本优先级排序（本文类 > 玉诀类 > 其他）。
零第三方依赖；PYTHONUTF8=1 兼容。
"""
import argparse
import fnmatch
import json
import os
import re
import sys

# 古籍库根（素材目录）解析：--source 参数 > env ZERO_CLASSICS_HOME（用户自设外部 classics 库根）。
# 不探测任何固定路径；两者皆缺时按"可选依赖未配置"优雅降级（引文外部对照为可选能力，禁硬失败）。
def default_classics_root():
    """缺省素材目录解析：env ZERO_CLASSICS_HOME；未设返回 None（由调用方降级处理）。"""
    root = os.environ.get("ZERO_CLASSICS_HOME", "")
    return root or None

# 分层层名按用户自备库实际结构调整；source 层默认同目录下 "source"（若库无此层仅用 corpus 即可）
LAYER_DIRS = {"source": "source", "corpus": "corpus"}
LAYER_EXTS = {"source": ".txt", "corpus": ".md"}
LAYER_ENCODING = {"source": "gb18030", "corpus": "utf-8"}

# 中日标点（含全角空格），标点归一层剥除
PUNCT = "，。；：「」『』""''？！、·—…～《》〈〉【】[]()<>　 \t\r\n"

# 高频简繁对照小表（≥40 对；双向归一到简边；GB18030 繁体正文 vs 简体引文是常态，此层是主力）
SIMPLE_MAP = {
    "於": "于", "說": "说", "閒": "间", "爲": "为", "後": "后", "裏": "里",
    "無": "无", "經": "经", "滿": "满", "萬": "万", "課": "课", "誰": "谁",
    "難": "难", "麗": "丽", "廟": "庙", "齊": "齐", "龍": "龙", "鳳": "凤",
    "樂": "乐", "藥": "药", "醫": "医", "殺": "杀", "斷": "断", "變": "变",
    "書": "书", "畫": "画", "劍": "剑", "張": "张", "門": "门", "問": "问",
    "聞": "闻", "陽": "阳", "陰": "阴", "雲": "云", "風": "风", "龜": "龟",
    "馬": "马", "鳥": "鸟", "蟲": "虫", "聖": "圣", "賢": "贤", "學": "学",
    "覺": "觉", "師": "师", "處": "处", "眾": "众", "惡": "恶", "幾": "几",
    "與": "与", "淵": "渊", "動": "动", "長": "长", "寶": "宝", "貴": "贵",
    "驕": "骄", "遺": "遗", "銳": "锐", "髀": "髀",
}
_TO_SIMP = str.maketrans(SIMPLE_MAP)

PRIORITY_KEYWORDS = [("本文类", 0), ("玉诀类", 1)]


def to_simp(text):
    return text.translate(_TO_SIMP)


def strip_punct(text):
    return "".join(ch for ch in text if ch not in PUNCT)


def norm_punct(text):
    return strip_punct(text)


def norm_simp(text):
    return strip_punct(to_simp(text))


def file_priority(filename):
    for kw, pri in PRIORITY_KEYWORDS:
        if kw in filename:
            return pri
    return 2


def find_files(book, layer, root):
    layer_dir = os.path.join(root, LAYER_DIRS[layer])
    if not os.path.isdir(layer_dir):
        sys.stderr.write("素材目录不存在：%s\n" % layer_dir)
        sys.exit(2)
    root = layer_dir
    pattern = book if any(c in book for c in "*?[") else "*%s*" % book
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(LAYER_EXTS[layer]) and fnmatch.fnmatch(fn, pattern):
                hits.append(os.path.join(dirpath, fn))
    hits.sort()
    return hits


def read_lines(path, layer):
    with open(path, encoding=LAYER_ENCODING[layer], errors="replace") as f:
        return f.read().splitlines()


def match_lines(quote, lines):
    """逐层降级行级匹配；返回 (判定, 行号1based, 原文行)。"""
    q1 = quote
    q2 = norm_punct(quote)
    q3 = norm_simp(quote)
    n2 = [norm_punct(l) for l in lines]
    n3 = [norm_simp(l) for l in lines]
    for i, line in enumerate(lines):
        if q1 in line:
            return ("原样命中", i + 1, line)
    for i, nl in enumerate(n2):
        if q2 and q2 in nl:
            return ("标点归一命中", i + 1, lines[i])
    for i, nl in enumerate(n3):
        if q3 and q3 in nl:
            return ("简繁归一命中", i + 1, lines[i])
    return None


def match_variant(quote, lines):
    """疑似异文层：四层全败后，简繁+标点归一基础上滑窗找最小字符差窗口。
    命中报「疑似异文命中」并列出差异字符对照（如 斯↔是）——异文/节引是古籍引文零命中的
    最常见真实原因，标「疑似」不冒充逐字命中，人工看差异对照裁决。"""
    q = norm_simp(quote)
    if len(q) < 4:
        return None
    threshold = max(2, len(q) // 4)
    best = None  # (dist, line_idx, pairs)
    for i, line in enumerate(lines):
        nl = norm_simp(line)
        if len(nl) < len(q):
            continue
        for start in range(0, len(nl) - len(q) + 1):
            window = nl[start:start + len(q)]
            pairs = [(a, b) for a, b in zip(q, window) if a != b]
            if not pairs:
                continue  # 前层已处理，此处只要差异窗口
            if best is None or len(pairs) < len(best[2]):
                best = (len(pairs), i, pairs)
                if len(pairs) == 1:
                    break
        if best and best[0] == 1:
            break
    if best and best[0] <= threshold:
        dist, line_idx, pairs = best
        diff = "、".join("%s↔%s" % (a, b) for a, b in pairs)
        return ("疑似异文命中（差异：%s）" % diff, line_idx + 1, lines[line_idx])
    return None


def match_joined(quote, lines):
    """全文拼接 fallback：剥换行拼全文再匹配，命中报跨行行号区间。"""
    q = norm_simp(quote)
    if not q:
        return None
    joined = []
    line_of = []  # joined 每字符对应行号（1based）
    for i, line in enumerate(lines):
        for ch in norm_simp(line):
            joined.append(ch)
            line_of.append(i + 1)
    text = "".join(joined)
    pos = text.find(q)
    if pos < 0:
        return None
    lo = line_of[pos]
    hi = line_of[pos + len(q) - 1]
    return ("跨行命中（简繁归一）", lo, hi)


def main():
    ap = argparse.ArgumentParser(description="古籍引文验证：书名定位底本→四层递进匹配（原样/标点归一/简繁归一/全文拼接）")
    ap.add_argument("--quote", required=True, help="必填：引文片段（≥4 字为宜）")
    ap.add_argument("--book", required=True, help="必填：书名关键词（文件名 glob 匹配，支持 *）")
    ap.add_argument("--source", default="",
                    help="素材目录（含 source/corpus 子目录的古籍库根）；缺省读 env ZERO_CLASSICS_HOME")
    ap.add_argument("--layer", choices=["source", "corpus"], default="source",
                    help="source=GB18030 txt（默认）；corpus=UTF-8 md")
    ap.add_argument("--first", type=int, default=10, help="输出前 N 个命中文件（默认 10），总数另报")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    classics_root = args.source or default_classics_root()
    if not classics_root:
        sys.stderr.write("可选依赖未配置，跳过外部对照：--source 未给且 env ZERO_CLASSICS_HOME 未设"
                         "（如需引文外部对照，请将 env ZERO_CLASSICS_HOME 指向自备古籍库根）。\n")
        sys.exit(0)

    files = find_files(args.book, args.layer, classics_root)
    if not files:
        msg = "书名未匹配到任何文件（layer=%s，pattern=%s）——请核对书名关键词。" % (args.layer, args.book)
        if args.json:
            print(json.dumps({"quote": args.quote, "book": args.book, "layer": args.layer,
                              "total_hits": 0, "results": [], "message": msg}, ensure_ascii=False))
        else:
            print("未命中书名：%s" % msg)
        sys.exit(1)

    results = []
    for path in files:
        try:
            lines = read_lines(path, args.layer)
        except OSError as e:
            continue
        m = match_lines(args.quote, lines)
        if m:
            method, lineno, text = m
            results.append({"file": os.path.basename(path), "path": path, "line": lineno,
                            "text": text.strip(), "method": method,
                            "priority": file_priority(os.path.basename(path))})
            continue
        mj = match_joined(args.quote, lines)
        if mj:
            method, lo, hi = mj
            snippet = lines[lo - 1].strip() if lo - 1 < len(lines) else ""
            results.append({"file": os.path.basename(path), "path": path,
                            "line": lo, "line_end": hi, "text": snippet, "method": method,
                            "priority": file_priority(os.path.basename(path))})

        mv = match_variant(args.quote, lines)
        if mv:
            method, lineno, text = mv
            results.append({"file": os.path.basename(path), "path": path, "line": lineno,
                            "text": text.strip(), "method": method,
                            "priority": file_priority(os.path.basename(path))})

    results.sort(key=lambda r: (r["priority"], r["path"]))
    shown = results[: args.first]

    if args.json:
        print(json.dumps({"quote": args.quote, "book": args.book, "layer": args.layer,
                          "scanned_files": len(files), "total_hits": len(results),
                          "results": shown}, ensure_ascii=False, indent=2))
        sys.exit(0 if results else 1)

    if not results:
        print("未命中：引文在 %d 个候选底本（书名=%s，layer=%s）中零匹配。" % (len(files), args.book, args.layer))
        print("排查提示：①引文可能为异文/节引（古籍版本差异常见，试缩短为最核心 4-8 字再验）"
              "②书名关键词可能不准（换常用书名或用 * 通配）③跨书引文请换 --book 重试。")
        sys.exit(1)

    print("命中 %d / 扫描 %d 个候选底本（书名=%s，layer=%s），按底本优先级排序，展示前 %d："
          % (len(results), len(files), args.book, args.layer, len(shown)))
    for r in shown:
        span = "-L%d" % r["line_end"] if "line_end" in r else ""
        print("[%s] %s（L%d%s）" % (r["method"], r["path"], r["line"], span))
        print("    %s" % r["text"])


if __name__ == "__main__":
    main()
