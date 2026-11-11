# -*- coding: utf-8 -*-
"""印证库向量索引（层别向量）：combo_features → bge-small-zh 嵌入 → FAISS IndexFlatIP。

须用装好 faiss、numpy、sentence_transformers 的 Python 环境运行：
  python embed.py [--data-dir 目录] [--event-id <id> ...]   # 增量嵌入（缺省全量补齐）
  python embed.py --rebuild [--data-dir 目录]              # 全量重建索引
  python embed.py --query "<序列化文本>" [--layer liuri|liuyue|liunian]
                       [--top-k 5] [--exclude-date YYYY-MM-DD] [--data-dir 目录]
  python embed.py --serialize '<combo_json>' [--layer liuri|liuyue|liunian]
                                                                       # 序列化唯一出口（纯文本，任意 Python 可跑）

层别相似度：每条事件存双份向量——全盘（vec=full，跨层参考用）+ 层别
（vec=liuri/liuyue/liunian，按事件 level；层内精确比对用）。
--query --layer L 用层别查询向量与同层别存储向量比对（同维度对比）。
--exclude-date 语义（未来函数修正）：排除 ≥ 该日期的所有事件（非仅同日）。
旧索引条目无 vec 字段按 full 计；启用层别查询须先 --rebuild 全量重建。

索引文件（<data-dir>\index\）：verify.index（FAISS）+ idmap.json（位置→元数据）+
model.lock（嵌入模型锁定戳——换模型=全量重建）。--query 输出 JSON 数组（stdout），
其余模式输出单行 JSON 摘要，供 append/liupan/make 子进程解析。--serialize 纯文本输出。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import list_shards, read_lines, resolve_data_dir

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
INDEX_DIR = "index"
INDEX_FILE = "verify.index"
IDMAP_FILE = "idmap.json"
LOCK_FILE = "model.lock"
HUA_ORDER = ["禄", "权", "科", "忌"]
MIN_SIM = 0.5  # 注入阈值：低于此相似度不作为历史印证
# 账本 level 字段 → 层别向量名（层内精确比对）
LEVEL_KEY = {"流日": "liuri", "流月": "liuyue", "流年": "liunian"}


def serialize_combo(combo_features):
    """序列化函数唯一出口：嵌入侧与查询侧统一格式，禁在调用方自行拼字符串。"""
    def sihua_part():
        items = []
        for h in HUA_ORDER:
            v = (combo_features.get("sihua") or {}).get(h)
            if v:
                items.append("%s@%s" % (h, v))
        return ",".join(items)

    def double_part():
        return ",".join(combo_features.get("double_hua") or [])

    return "命宫:%s | 四化:{%s} | 双化:{%s}" % (
        combo_features.get("layer_ming_xingxi", ""), sihua_part(), double_part())


def serialize_layer(combo_features, layer):
    """层别序列化：只含当前分析层自身的盘面特征（命宫星系+本层四化），
    不含 double_hua（跨两层）——同层内两天的相似度真实反映该层盘面差异。"""
    items = []
    for h in HUA_ORDER:
        v = (combo_features.get("sihua") or {}).get(h)
        if v:
            items.append("%s@%s" % (h, v))
    return "层:%s 命宫:%s | 四化:{%s}" % (
        layer, combo_features.get("layer_ming_xingxi", ""), ",".join(items))


def index_paths(data_dir):
    d = os.path.join(data_dir, INDEX_DIR)
    return d, os.path.join(d, INDEX_FILE), os.path.join(d, IDMAP_FILE), os.path.join(d, LOCK_FILE)


def find_anchor_key(key):
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        path = os.path.join(cur, "anchors.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = json.load(f).get(key)
                if val:
                    return val
            except (OSError, ValueError):
                return None
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def iter_events(data_dir):
    """yield 账本记录（非法行跳过）。"""
    for _, _, name in list_shards(data_dir):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                yield json.loads(line)
            except ValueError:
                continue


def load_model():
    os.environ.setdefault("HF_HOME", find_anchor_key("HF_HOME_DIR") or "")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model.lock 已锁本地缓存模型；在线 HEAD 检查在网络受限环境重试拖死子进程
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME, local_files_only=True)  # 同检索服务离线口径


def embed_texts(model, texts):
    import faiss
    import numpy as np
    vecs = np.array(model.encode(texts, normalize_embeddings=True), dtype="float32")
    faiss.normalize_L2(vecs)
    return vecs


LOOPBACK_PORT_DEFAULT = 21730
LOOPBACK_BATCH = 64  # 服务端单请求上限


def loopback_embed(texts):
    """回环通道（本地回环服务入口）：成功返回 float32 向量，失败返回 None。
    is_query 恒 False——ziwei 系查询/入库同一口径（与本地 SentenceTransformer 用法一致）。"""
    import socket
    port = int(os.environ.get("MEM_EMBED_PORT") or LOOPBACK_PORT_DEFAULT)
    out = []
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.settimeout(60)
            for i in range(0, len(texts), LOOPBACK_BATCH):
                chunk = texts[i:i + LOOPBACK_BATCH]
                req = json.dumps({"id": 1, "method": "embed",
                                  "params": {"texts": chunk, "is_query": False}},
                                 ensure_ascii=False).encode("utf-8") + b"\n"
                sock.sendall(req)
                buf = b""
                while b"\n" not in buf:
                    data = sock.recv(65536)
                    if not data:
                        return None
                    buf += data
                resp = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
                result = resp.get("result") or {}
                vectors = result.get("vectors")
                if (resp.get("error") or result.get("model") != MODEL_NAME
                        or result.get("dim") != 512 or not vectors
                        or len(vectors) != len(chunk)):
                    return None
                out.extend(vectors)
    except Exception:
        return None
    import faiss
    import numpy as np
    vecs = np.array(out, dtype="float32")
    faiss.normalize_L2(vecs)  # 幂等：与本地 embed_texts 同口径
    return vecs


def embed_texts_smart(texts, use_loopback=True):
    """嵌入来源统一入口：回环优先（重试 1 次），失败降级本地模型加载。stdout 是 JSON 通道，日志走 stderr。"""
    if use_loopback:
        for _ in range(2):
            vecs = loopback_embed(texts)
            if vecs is not None:
                print("[embed] loopback (port %s)" % os.environ.get("MEM_EMBED_PORT", LOOPBACK_PORT_DEFAULT),
                      file=sys.stderr)
                return vecs
        print("[embed] local fallback (loopback unavailable)", file=sys.stderr)
    return embed_texts(load_model(), texts)


def load_index(data_dir):
    import faiss
    idx_dir, idx_file, idmap_file, lock_file = index_paths(data_dir)
    if not (os.path.isfile(idx_file) and os.path.isfile(idmap_file)):
        return None, None
    with open(lock_file, "r", encoding="utf-8") as f:
        lock = json.load(f)
    if lock.get("model") != MODEL_NAME:
        raise RuntimeError("model.lock 模型不一致（%r ≠ %s）——须 --rebuild 全量重建"
                           % (lock.get("model"), MODEL_NAME))
    index = faiss.read_index(idx_file)
    with open(idmap_file, "r", encoding="utf-8") as f:
        idmap = json.load(f)
    if index.ntotal != len(idmap):
        raise RuntimeError("索引条数(%d) != idmap 条数(%d)——须 --rebuild" % (index.ntotal, len(idmap)))
    return index, idmap


def save_index(data_dir, index, idmap):
    import faiss
    idx_dir, idx_file, idmap_file, lock_file = index_paths(data_dir)
    os.makedirs(idx_dir, exist_ok=True)
    faiss.write_index(index, idx_file)
    with open(idmap_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(idmap, f, ensure_ascii=False)
    with open(lock_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"model": MODEL_NAME}, f, ensure_ascii=False)


def do_add(data_dir, event_ids, rebuild):
    want = set(event_ids) if event_ids else None
    old_ids = set()
    index, idmap = (None, []) if rebuild else load_index(data_dir) or (None, [])
    if not rebuild and index is not None:
        old_ids = {e.get("event_id") for e in idmap}
    import faiss
    pending = []
    seen = set()
    for rec in iter_events(data_dir):
        eid = rec.get("event_id", "")
        if eid in seen:
            continue
        seen.add(eid)
        if want is not None and eid not in want:
            continue
        combo = rec.get("combo_features") or {}
        if not combo:
            continue
        if not rebuild and eid in old_ids:
            continue
        base = {
            "event_id": eid, "person": rec.get("person", ""),
            "category": rec.get("category", ""), "date": rec.get("event_date", ""),
            "text": rec.get("text", ""), "verify_result": rec.get("verify_result", ""),
            "prediction": rec.get("prediction", ""),   # 经验链字段入索引元数据
            "outcome": rec.get("outcome", ""),
        }
        # 双份向量：全盘 + 层别（按事件 level；无 level 仅存全盘）
        pending.append(dict(base, vec="full", combo_text=serialize_combo(combo)))
        layer = LEVEL_KEY.get(rec.get("level", ""))
        if layer:
            pending.append(dict(base, vec=layer, combo_text=serialize_layer(combo, layer)))
    if index is None:
        index = faiss.IndexFlatIP(512)
        idmap = []
    if pending:
        # --rebuild 批量大，恒走本地加载；增量/补齐走回环优先
        index.add(embed_texts_smart([p["combo_text"] for p in pending], use_loopback=not rebuild))
        idmap.extend(pending)
    save_index(data_dir, index, idmap)
    return {"added": len(pending), "total": len(idmap),
            "mode": "rebuild" if rebuild else "incremental"}


def do_query(data_dir, text, top_k, exclude_date, layer=None):
    index, idmap = load_index(data_dir)
    if index is None or index.ntotal == 0:
        return []
    qv = embed_texts_smart([text])
    # 层别查询只与同层别存储向量比对——候选面放大防过滤后不足 top_k
    cand = max(top_k * 8, 32) if layer else max(top_k * 4, 16)
    scores, poss = index.search(qv, min(index.ntotal, cand))
    hits = []
    seen_eids = set()
    for score, pos in zip(scores[0], poss[0]):
        if pos < 0:
            continue
        meta = dict(idmap[pos])
        if layer and meta.get("vec", "full") != layer:
            continue
        # 未来函数修正：排除 ≥ 分析日期的所有事件（非仅同日）
        if exclude_date and meta.get("date", "") >= exclude_date:
            continue
        if score < MIN_SIM:
            continue
        if meta.get("event_id") in seen_eids:  # 同事件双份向量（全盘+层别）去重
            continue
        seen_eids.add(meta.get("event_id"))
        hits.append({"pos": int(pos), "similarity": round(float(score), 4), **meta})
        if len(hits) >= top_k:
            break
    hits.sort(key=lambda h: -h["similarity"])
    for h in hits:
        h.pop("pos", None)
        h.pop("combo_text", None)
    return hits


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="印证库向量索引（嵌入/检索/序列化）")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--event-id", dest="event_id", action="append", default=None)
    ap.add_argument("--rebuild", action="store_true", default=False, help="全量重建索引")
    ap.add_argument("--query", default=None, help="序列化文本，相似检索 top-K")
    ap.add_argument("--layer", default=None, choices=list(LEVEL_KEY.values()),
                    help="层别查询：层别序列化+只与同层别存储向量比对")
    ap.add_argument("--top-k", dest="top_k", type=int, default=5)
    ap.add_argument("--exclude-date", dest="exclude_date", default=None,
                    help="排除 ≥该日期的所有事件（未来函数修正：当天及以后不注入）")
    ap.add_argument("--serialize", default=None, help="combo_features JSON → 标准序列化文本（唯一出口）")
    args = ap.parse_args()

    if args.serialize is not None:
        combo = json.loads(args.serialize)
        print(serialize_layer(combo, args.layer) if args.layer
              else serialize_combo(combo))
        return
    data_dir = resolve_data_dir(args.data_dir)
    if args.query is not None:
        print(json.dumps(do_query(data_dir, args.query, args.top_k, args.exclude_date,
                                  layer=args.layer),
                         ensure_ascii=False))
        return
    print(json.dumps(do_add(data_dir, args.event_id or [], args.rebuild), ensure_ascii=False))


if __name__ == "__main__":
    main()
