# -*- coding: utf-8 -*-
"""构建检索索引（vectors.index + metadata.db + bm25.cache）。

输入默认取技能包上级 data/zeropro_open_kb.json，本地真源重跑须显式 --input。
仅入库八列白名单字段；attribution/origin/spec_id 等过程字段不入索引。
用法示例（仓库根相对）：见 SKILL.md quickstart。
"""
import argparse
import json
import pickle
import sqlite3
import sys
import time
from pathlib import Path

import faiss
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

FIELDS = ["id", "topic", "parent_topic", "content", "source", "tags", "char_count", "related_stars"]
BATCH = 100


def main():
    parser = argparse.ArgumentParser(description="Build kb index")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "kb_index")
    args = parser.parse_args()

    default_input = Path(__file__).resolve().parent.parent / "data" / "zeropro_open_kb.json"
    in_path = args.input or default_input
    if not in_path.exists():
        print(f"[ERR] 输入不存在: {in_path}（用 --input 指定 master json 路径）", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    slices = data if isinstance(data, list) else data.get("slices", [])
    print(f"[1/6] 载入 {len(slices)} 片（来源 {in_path}）")

    def to_row(s):
        vals = []
        for k in FIELDS:
            v = s.get(k)
            if k in ("tags", "related_stars"):
                v = json.dumps(v or [], ensure_ascii=False)
            vals.append(v)
        return tuple(vals)

    rows = [to_row(s) for s in slices]

    print("[2/6] 加载嵌入模型 BAAI/bge-small-zh-v1.5")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    print(f"[3/6] 嵌入 content（{len(rows)} 片，{BATCH}/批）")
    contents = [s.get("content", "") for s in slices]
    all_vecs = []
    for i in range(0, len(contents), BATCH):
        vecs = model.encode(contents[i:i + BATCH], normalize_embeddings=True)
        all_vecs.append(vecs)
        print(f"      {min(i + BATCH, len(contents))}/{len(contents)}")
    vecs = np.vstack(all_vecs).astype("float32")

    print("[4/6] 构建 FAISS IndexHNSWFlat (dim=512, M=32, efConstruction=200)")
    index = faiss.IndexHNSWFlat(vecs.shape[1], 32)
    index.hnsw.efConstruction = 200
    index.add(vecs)

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out_dir / "vectors.index"))

    print("[5/6] 写 metadata.db（SQLite 八列）")
    db_path = out_dir / "metadata.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute(f"CREATE TABLE slices (id TEXT PRIMARY KEY, topic TEXT, parent_topic TEXT, content TEXT, source TEXT, tags TEXT, char_count INTEGER, related_stars TEXT)")
    conn.executemany(
        f"INSERT INTO slices ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})", rows
    )
    conn.commit()
    conn.close()

    print("[6/6] 写 bm25.cache（jieba + BM25Okapi）")
    tokenized = [list(jieba.cut_for_search(c)) for c in contents]
    bm25 = BM25Okapi(tokenized)
    with open(out_dir / "bm25.cache", "wb") as f:
        pickle.dump(bm25, f)

    dt = time.time() - t0
    print("=== 构建完成 ===")
    print(f"切片数: {len(rows)}")
    print(f"向量维度: {vecs.shape[1]}")
    print(f"索引类型: {type(index).__name__} (M=32, efC=200) ntotal={index.ntotal}")
    print(f"输出目录: {out_dir}")
    print(f"耗时: {dt:.1f}s")


if __name__ == "__main__":
    main()
