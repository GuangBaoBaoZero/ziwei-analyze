#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""典籍库索引构建（典籍三工具件之二，方案 v1.9.2 批；faiss 引擎 2026-11-21 增）。

功能：
  --engine fts（默认，向后兼容）：读 data/classics/*.txt → 空行分段 →
      sqlite3 FTS5 表 → 按字插空格入库 → data/classics_index.db。
  --engine faiss：块级聚合切分（句号/问号/叹号边界聚合，目标 768 字/块、
      上限 1200，段间跨段聚合不跨书，段衔接换行）→ 本地 bge-small-zh
      embedding + faiss IndexFlatIP 归一化向量索引 →
      data/classics_faiss.index +
      classics_meta.db（book/para_id/text 三列，原文）。

幂等：直接重建（覆盖旧产物）。
FTS5 不可用（老 sqlite）→ 打印降级指引 exit 2。
faiss 依赖缺失 → 明确报错指引 exit 2。

用法：
  python classics_build_index.py                         # FTS 默认
  python classics_build_index.py --engine faiss          # 全量 25248 段
  python classics_build_index.py --engine faiss --books 论语,史记
零第三方依赖（fts 模式）；PYTHONUTF8=1 兼容。
"""
import glob
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
CLASSICS_DIR = os.path.join(SKILL_ROOT, "data", "classics")
DB_PATH = os.path.join(SKILL_ROOT, "data", "classics_index.db")
FAISS_INDEX_PATH = os.path.join(SKILL_ROOT, "data", "classics_faiss.index")
META_DB_PATH = os.path.join(SKILL_ROOT, "data", "classics_meta.db")

# 块级切块参数（对齐成熟方案实测：avg=768 max=1200）
CHUNK_TARGET = 768   # 聚合到 ≥768 字即出块
CHUNK_MAX = 1200     # 硬上限，超出在最近句边界切


def find_model_dir():
    """本地 bge-small-zh 模型目录（vector/ 子模块）。"""
    d = os.path.join(SKILL_ROOT, "vector", "models", "bge-small-zh")
    return d if os.path.isdir(d) else None


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def split_paras(text):
    """空行分段；段内换行替换为空（段落为检索单元）。"""
    paras = []
    cur = []
    for line in text.splitlines():
        if line.strip() == "":
            if cur:
                paras.append("".join(cur))
                cur = []
        else:
            cur.append(line.strip())
    if cur:
        paras.append("".join(cur))
    return paras


def spaced(text):
    """按字插空格（保留连续 ASCII 词不拆）。"""
    out = []
    prev_ascii = False
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            if prev_ascii:
                out.append(ch)
            else:
                out.append(" " + ch)
            prev_ascii = True
        else:
            out.append(ch + " ")
            prev_ascii = False
    return "".join(out).strip()


SENT_SPLIT = re.compile(r"(?<=[。？！])")


def chunk_book(paras):
    """块级聚合切块（书内，禁跨书）：
    ①段内句子流（。？！边界）聚合，到 ≥CHUNK_TARGET 出块；
    ②超 CHUNK_MAX 在最近句边界切；
    ③段尾不足目标的残块与后续段继续聚合（跨段但不跨书）；
    ④段落衔接用换行。
    """
    chunks = []
    cur = ""  # 当前未出块的聚合缓冲
    for para in paras:
        for sent in (s for s in SENT_SPLIT.split(para) if s.strip()):
            if len(cur) + len(sent) + 1 > CHUNK_MAX:
                if cur:
                    chunks.append(cur)
                    cur = ""
                # 单句自身超限：整句独占出块（不切句）
                if len(sent) >= CHUNK_MAX:
                    chunks.append(sent)
                    continue
            cur = sent if not cur else cur + "\n" + sent
            if len(cur) >= CHUNK_TARGET:
                chunks.append(cur)
                cur = ""
    if cur:
        chunks.append(cur)
    return chunks


def collect_books(books_filter):
    files = sorted(glob.glob(os.path.join(CLASSICS_DIR, "*.txt")))
    if books_filter:
        want = [b.strip() for b in books_filter.split(",") if b.strip()]
        files = [f for f in files
                 if os.path.splitext(os.path.basename(f))[0] in want]
        found = {os.path.splitext(os.path.basename(f))[0] for f in files}
        lack = [b for b in want if b not in found]
        if lack:
            print(f"[FAIL] 指定书名不存在：{','.join(lack)}", file=sys.stderr)
            return None
    return files


def build_faiss(files):
    """faiss 模式：句级切分 → 本地 bge embedding + IndexFlatIP 向量索引。"""
    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"[FAIL] faiss 模式依赖缺失：{e}", file=sys.stderr)
        print("指引：python bin/setup_vector.py（自动装齐）或 "
              "python -m pip install faiss-cpu numpy sentence-transformers",
              file=sys.stderr)
        return 2

    model_dir = find_model_dir()
    if model_dir:
        print(f"模型：{model_dir}")
        model = SentenceTransformer(model_dir)
    else:
        print("[warn] 本地 bge-small-zh 缺失，在线加载 BAAI/bge-small-zh-v1.5",
              file=sys.stderr)
        model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    # 块级聚合切块入元数据（书内聚块，para_id 为书内块序号）
    segs = []  # (book, para_id, text)
    for path in files:
        book = os.path.splitext(os.path.basename(path))[0]
        paras = split_paras(read_text(path))
        for i, chunk in enumerate(chunk_book(paras)):
            segs.append((book, i, chunk))
    if not segs:
        print("[FAIL] 无可索引内容", file=sys.stderr)
        return 1
    lens = [len(s[2]) for s in segs]
    print(f"切分：{len(files)} 部 / {len(segs)} 块，"
          f"avg={sum(lens) // len(lens)} max={max(lens)}，embedding ...")

    texts = [s[2] for s in segs]
    vecs = np.array(model.encode(texts, normalize_embeddings=True,
                                 show_progress_bar=True), dtype="float32")
    faiss.normalize_L2(vecs)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, FAISS_INDEX_PATH)

    if os.path.exists(META_DB_PATH):
        os.remove(META_DB_PATH)
    conn = sqlite3.connect(META_DB_PATH)
    conn.execute("CREATE TABLE segs(book TEXT, para_id INT, text TEXT)")
    conn.executemany("INSERT INTO segs VALUES (?,?,?)", segs)
    conn.commit()
    conn.close()

    print(f"[OK] {len(files)} 部 / {len(segs)} 句段 →")
    print(f"  {FAISS_INDEX_PATH}")
    print(f"  {META_DB_PATH}")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="典籍索引构建（fts 默认 / faiss 语义）")
    ap.add_argument("--engine", choices=["fts", "faiss"], default="fts")
    ap.add_argument("--books", default=None,
                    help="逗号分隔书名限量构建（测试用），如 论语,史记")
    args = ap.parse_args()

    files = collect_books(args.books)
    if not files:
        print(f"[FAIL] 无典籍文件：{CLASSICS_DIR}", file=sys.stderr)
        return 1

    if args.engine == "faiss":
        return build_faiss(files)

    # FTS5 可用性预检
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        probe.close()
    except sqlite3.OperationalError as e:
        print("[FAIL] 本机 sqlite 不支持 FTS5：" + str(e))
        print("降级指引：classics_search.py 在 db 缺席时自动走 txt grep 降级路径（输出格式一致）；")
        print("如需 FTS，请升级 Python 自带 sqlite（3.12 底座正常应含 FTS5）。")
        return 2

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE VIRTUAL TABLE classics USING fts5(book, para_id UNINDEXED, text)")
    total = 0
    for path in files:
        book = os.path.splitext(os.path.basename(path))[0]
        paras = split_paras(read_text(path))
        rows = [(book, i, spaced(p)) for i, p in enumerate(paras)]
        conn.executemany("INSERT INTO classics(book, para_id, text) VALUES (?,?,?)", rows)
        total += len(rows)
        print(f"  {book}: {len(rows)} 段")
    conn.commit()
    conn.close()
    print(f"[OK] {len(files)} 部 / {total} 段 → {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
