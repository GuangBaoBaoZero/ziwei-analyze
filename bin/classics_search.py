#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""典籍库检索（典籍三工具件之三，方案 v1.9.2 批；faiss 引擎 2026-11-21 增）。

功能：
  --engine fts（默认）：--keywords 关键词（空格分隔=AND）→ 按字插空格 →
      FTS5 MATCH → 输出 书名/para_id/原文片段。
  --engine faiss：语义（faiss IndexFlatIP + bge 本地模型）+ 字面子串精配
      书级 RRF 混合 → 同格式输出（对齐 zk_query 设计：字面臂不分词，
      查询串连续出现即命中；融合按书聚合，同书多块取最优 rank）。
降级链：faiss 模式缺依赖或缺索引、fts 模式 db 缺席/查询失败 → txt grep
（同输出格式）。

用法：
  python classics_search.py --keywords "欲速则不达"
  python classics_search.py --keywords "学而时习" --book 论语
  python classics_search.py --engine faiss --keywords "欲速则不达"
零第三方依赖（fts/grep 模式）；PYTHONUTF8=1 兼容。
"""
import argparse
import glob
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
CLASSICS_DIR = os.path.join(SKILL_ROOT, "data", "classics")
DB_PATH = os.path.join(SKILL_ROOT, "data", "classics_index.db")
FAISS_INDEX_PATH = os.path.join(SKILL_ROOT, "data", "classics_faiss.index")
META_DB_PATH = os.path.join(SKILL_ROOT, "data", "classics_meta.db")
PUNCT_CHARS = "，。；：？！、·「」『』“”‘’《》〈〉【】〔〕—…－-,.!?;:\"'`()<>[]{}~·　,，. "
PUNCT_TABLE = {ord(c): None for c in PUNCT_CHARS}
RRF_K = 60
LIT_WEIGHT = 2.0  # 字面精配臂权重（子串命中=强信号，压过语义臂默认权）


def normalize_plain(text):
    """去空白+去标点（中英标点），字面臂子串匹配用；命中位置在此口径上算。"""
    return "".join(text.split()).translate(PUNCT_TABLE)


def find_model_dir():
    d = os.path.join(SKILL_ROOT, "vector", "models", "bge-small-zh")
    return d if os.path.isdir(d) else None


def spaced(text):
    """按字插空格（ASCII 词不拆），与 build_index 同构。"""
    out = []
    prev_ascii = False
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            out.append(("" if prev_ascii else " ") + ch)
            prev_ascii = True
        else:
            out.append(ch + " ")
            prev_ascii = False
    return "".join(out).strip()


def search_fts(keywords, book, limit):
    conn = sqlite3.connect(DB_PATH)
    # 每个 keyword 作为短语查询（双引号包裹），多 keyword 空格连接=AND
    match = " ".join('"' + spaced(k).replace('"', '""') + '"' for k in keywords)
    sql = "SELECT book, para_id, text FROM classics WHERE classics MATCH ?"
    params = [match]
    if book:
        sql += " AND book = ?"
        params.append(book)
    sql += " LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        conn.close()
        raise e
    conn.close()
    results = []
    for b, pid, text in rows:
        plain = text.replace(" ", "")
        results.append((b, pid, plain))
    return results, match


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def search_grep(keywords, book, limit):
    """降级：txt 逐书 grep（段落为单位，空行分段），输出格式与 FTS 一致。"""
    files = sorted(glob.glob(os.path.join(CLASSICS_DIR, f"*{book}*.txt" if book else "*.txt")))
    results = []
    kw_all = [k.replace(" ", "") for k in keywords]
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        paras = []
        cur = []
        for line in read_text(path).splitlines():
            if line.strip() == "":
                if cur:
                    paras.append("".join(cur))
                    cur = []
            else:
                cur.append(line.strip())
        if cur:
            paras.append("".join(cur))
        for i, p in enumerate(paras):
            if all(k in p for k in kw_all):
                results.append((name, i, p))
                if len(results) >= limit:
                    return results, None
    return results, None


def search_faiss(query, book, limit):
    """faiss 模式：语义 + 字面子串精配，书级 RRF 融合。

    字面臂：查询串去空白+去标点后在 segs.text（同口径归一）上做子串匹配，
    连续出现即命中，命中越靠前 rank 越优——不做分词（短查询分词会被
    高频单字稀释，zk_query 实测定案）。融合单元=书：各臂同书多块取
    最优 rank 参与 RRF，输出按书排序、每书给最优块。
    返回 [(book, para_id, text)]。
    """
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model_dir = find_model_dir()
    model = (SentenceTransformer(model_dir) if model_dir
             else SentenceTransformer("BAAI/bge-small-zh-v1.5"))

    conn = sqlite3.connect(META_DB_PATH)
    rows = conn.execute("SELECT book, para_id, text FROM segs").fetchall()
    conn.close()

    # 字面臂：子串精配（原文与查询都去空白+去标点，规避换行/标点断开连续串）
    q_plain = normalize_plain(query)
    lit_hits = []
    for i, r in enumerate(rows):
        if book and r[0] != book:
            continue
        pos = normalize_plain(r[2]).find(q_plain)
        if pos >= 0:
            lit_hits.append((pos, i))
    lit_hits.sort()  # 命中位置越靠前越优

    # 语义臂：faiss top
    vec = np.array(model.encode([query], normalize_embeddings=True,
                                show_progress_bar=False), dtype="float32")
    faiss.normalize_L2(vec)
    index = faiss.read_index(FAISS_INDEX_PATH)
    n = min(max(limit * 4, 32), index.ntotal)
    scores, indices = index.search(vec, n)
    vec_hits = [int(i) for i in indices[0]
                if 0 <= i < len(rows) and (not book or rows[i][0] == book)]

    # 书级 RRF：每臂每书只取最优 rank（不累加多块），字面臂加权（精配信号
    # 强于语义）；best_blk 记每书最优块（两臂 rank 最小者）
    book_score = {}
    best_blk = {}  # book -> (min_rank, seg_idx)
    for weight, hits in ((LIT_WEIGHT, [i for _pos, i in lit_hits]),
                         (1.0, vec_hits)):
        seen = {}  # book -> best rank 本臂
        for rank, i in enumerate(hits, start=1):
            b = rows[i][0]
            if b not in seen or rank < seen[b]:
                seen[b] = rank
            if b not in best_blk or rank < best_blk[b][0]:
                best_blk[b] = (rank, i)
        for b, rank in seen.items():
            book_score[b] = book_score.get(b, 0.0) + weight / (RRF_K + rank)
    ranked_books = sorted(book_score.items(), key=lambda kv: kv[1],
                          reverse=True)[:limit]
    return [(b, rows[best_blk[b][1]][1], rows[best_blk[b][1]][2])
            for b, _s in ranked_books]


def main():
    ap = argparse.ArgumentParser(description="典籍库检索（fts 默认 / faiss 语义混合；缺件自动降级 grep）")
    ap.add_argument("--keywords", required=True, help="关键词/查询文本，空格分隔多词=AND（fts）")
    ap.add_argument("--engine", choices=["fts", "faiss"], default="faiss",
                    help="检索引擎（默认 fts；faiss=语义+BM25 混合）")
    ap.add_argument("--book", default=None, help="限定书名")
    ap.add_argument("--limit", type=int, default=20, help="最多输出条数（默认 20）")
    args = ap.parse_args()

    keywords = args.keywords.split()
    if not keywords:
        print("[FAIL] keywords 为空", file=sys.stderr)
        return 1

    mode = args.engine
    if args.engine == "faiss":
        need = (FAISS_INDEX_PATH, META_DB_PATH)
        if all(os.path.isfile(p) for p in need):
            try:
                results = search_faiss(args.keywords, args.book, args.limit)
            except ImportError as e:
                print(f"[warn] faiss 依赖缺失（{e}），降级 txt grep"
                      "（修复：python bin/setup_vector.py）", file=sys.stderr)
                results, _ = search_grep(keywords, args.book, args.limit)
                mode = "grep"
            except Exception as e:
                print(f"[warn] faiss 检索失败（{e}），降级 txt grep", file=sys.stderr)
                results, _ = search_grep(keywords, args.book, args.limit)
                mode = "grep"
        else:
            lack = [os.path.basename(p) for p in need if not os.path.isfile(p)]
            print(f"[warn] faiss 索引缺失（{', '.join(lack)}），降级 txt grep"
                  "（构建：python bin/classics_build_index.py --engine faiss）",
                  file=sys.stderr)
            results, _ = search_grep(keywords, args.book, args.limit)
            mode = "grep"
    elif os.path.isfile(DB_PATH):
        try:
            results, match = search_fts(keywords, args.book, args.limit)
        except sqlite3.OperationalError as e:
            print(f"[warn] FTS 查询失败（{e}），降级 grep", file=sys.stderr)
            results, _ = search_grep(keywords, args.book, args.limit)
            mode = "grep"
    else:
        print("[warn] classics_index.db 缺席，降级 txt grep（建议先跑 classics_build_index.py）",
              file=sys.stderr)
        results, _ = search_grep(keywords, args.book, args.limit)
        mode = "grep"

    if not results:
        print("[MISS] 无命中")
        return 1
    print(f"[mode={mode}] 命中 {len(results)} 条（混合检索·书级聚合排序）")
    for b, pid, plain in results:
        frag = plain[:60] + "…"
        k0 = keywords[0].replace(" ", "")
        pos = plain.find(k0)
        if pos >= 0:
            s = max(0, pos - 15)
            frag = ("…" if s > 0 else "") + plain[s:pos + 40] + "…"
        print(f"  {b} / 段{pid} / {frag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
