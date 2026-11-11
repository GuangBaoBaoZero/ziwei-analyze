# -*- coding: utf-8 -*-
"""知识库向量语义搜索（/search 检索 + 查询增强）

用法：
  python vector_search.py --query "廉贞贪狼在巳亥坐命事业如何" --top_k 10
  python vector_search.py --query "事业如何" --pan pan.json          # 星名增强
  python vector_search.py --query "..." --top_k 15                   # /search 端点默认值
  python vector_search.py --query "火贪格"                           # FAISS+BM25 双通道 RRF 融合
  python vector_search.py --browse                                   # parent_topic 分组概览
  python vector_search.py --browse "天同格局"                        # 主题组切片清单
  python vector_search.py --filter star=廉贞                          # 结构化筛选（star/palace/pattern/topic）
  python vector_search.py --query "事业" --filter star=廉破           # 筛选+双通道检索组合

依赖（环境另行安装）：
  pip install faiss-cpu sentence-transformers jieba rank-bm25
  模型：BAAI/bge-small-zh-v1.5（首次运行自动下载）
"""

import json
import os
import pickle
import re
import sys
import argparse
import sqlite3

_SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(_SKILL_ROOT, 'kb_index', 'vectors.index')
DB_PATH = os.path.join(_SKILL_ROOT, 'kb_index', 'metadata.db')
MODEL_NAME = 'BAAI/bge-small-zh-v1.5'  # 与建库模型一致，不可更换

# 本地降级用的 HF 环境（须在任何 hf/huggingface_hub import 之前生效——缓存路径常量在 import 时冻结）：
# 模型缓存在 anchors.json HF_HOME_DIR 指定的本地目录；在线 HEAD 检查在网络受限环境重试拖死子进程
_anchors = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_ROOT))), 'anchors.json')
try:
    with open(_anchors, 'r', encoding='utf-8') as _f:
        _hf_home = json.load(_f).get('HF_HOME_DIR')
except (OSError, ValueError):
    _hf_home = None
if _hf_home:
    os.environ.setdefault('HF_HOME', _hf_home)
# 仅当模型已在本地缓存（anchors HF_HOME_DIR 或默认 HF 缓存）时才离线；
# 缓存缺失时不设 OFFLINE，允许首次在线下载
_bge_in_hf_home = _hf_home and os.path.isdir(os.path.join(
    _hf_home, 'hub', 'models--BAAI--bge-small-zh-v1.5'))
_bge_in_default = os.path.isdir(os.path.join(
    os.path.expanduser('~'), '.cache', 'huggingface', 'hub',
    'models--BAAI--bge-small-zh-v1.5'))
if _bge_in_hf_home or _bge_in_default:
    os.environ.setdefault('HF_HUB_OFFLINE', '1')

# extractStarNames 星曜全集（MAIN + 辅 + 煞 + 杂）
STAR_VOCAB = [
    '紫微', '天机', '太阳', '武曲', '天同', '廉贞', '天府', '太阴', '贪狼', '巨门',
    '天相', '天梁', '七杀', '破军',
    '左辅', '右弼', '文昌', '文曲', '天魁', '天钺', '禄存', '天马',
    '擎羊', '陀罗', '火星', '铃星', '地空', '地劫',
    '截空', '蜚廉', '台辅', '天姚', '天官', '大耗', '龙德', '天才', '天月', '天虚',
    '天哭', '天厨', '劫杀', '破碎', '月德', '华盖', '龙池', '封诰', '天刑', '三台',
    '红鸾', '孤辰', '月解', '天使', '天空', '阴煞', '天伤', '恩光', '天寿', '天巫',
    '旬空', '寡宿', '年解', '凤阁', '八座', '天贵', '天福', '天喜', '咸池', '天德',
]


def check_env():
    """依赖自检：缺失时给出准确安装指引"""
    missing = []
    try:
        import faiss  # noqa: F401
    except ImportError:
        missing.append('faiss-cpu')
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        missing.append('sentence-transformers')
    try:
        from jieba import lcut  # noqa: F401
    except ImportError:
        missing.append('jieba')
    try:
        from rank_bm25 import BM25Okapi  # noqa: F401
    except ImportError:
        missing.append('rank-bm25')
    if missing:
        print('错误：向量检索依赖未安装。', file=sys.stderr)
        print(f'请先执行: pip install {" ".join(missing)}', file=sys.stderr)
        print(f'模型 {MODEL_NAME} 首次运行自动下载（约 100M）。', file=sys.stderr)
        sys.exit(2)


def build_enhanced_query(query, pan_path):
    """查询增强（extractStarNames 同源逻辑）：
    query + 命盘前 30 颗星名（有命盘时）+ 问题中星曜名重复两遍加权"""
    if not pan_path:
        return query

    with open(pan_path, 'r', encoding='utf-8') as f:
        pan_data = json.load(f)

    parts = [query]
    star_map = (pan_data.get('pan', {}) or {}).get('allStarMap', {}) or {}
    if star_map:
        stars = list(star_map.keys())[:30]
        parts.append(' '.join(stars))

    # 提取用户问题中的星曜名，追加两遍增强权重
    query_stars = [s for s in STAR_VOCAB if s in query]
    if query_stars:
        doubled = ' '.join(query_stars + query_stars)
        parts.append(doubled)

    return ' '.join(parts)


LOOPBACK_PORT_DEFAULT = 21730
LOOPBACK_BATCH = 64  # 服务端单请求上限


def loopback_embed(texts):
    """回环通道（本地回环服务 embed 入口）：成功返回 float32 向量，失败返回 None。"""
    import socket
    port = int(os.environ.get('MEM_EMBED_PORT') or LOOPBACK_PORT_DEFAULT)
    out = []
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2) as sock:
            sock.settimeout(60)
            for i in range(0, len(texts), LOOPBACK_BATCH):
                chunk = texts[i:i + LOOPBACK_BATCH]
                req = json.dumps({'id': 1, 'method': 'embed',
                                  'params': {'texts': chunk, 'is_query': False}},
                                 ensure_ascii=False).encode('utf-8') + b'\n'
                sock.sendall(req)
                buf = b''
                while b'\n' not in buf:
                    data = sock.recv(65536)
                    if not data:
                        return None
                    buf += data
                resp = json.loads(buf.split(b'\n', 1)[0].decode('utf-8'))
                result = resp.get('result') or {}
                vectors = result.get('vectors')
                if (resp.get('error') or result.get('model') != MODEL_NAME
                        or result.get('dim') != 512 or not vectors
                        or len(vectors) != len(chunk)):
                    return None
                out.extend(vectors)
    except Exception:
        return None
    import faiss
    import numpy as np
    vecs = np.array(out, dtype='float32')
    faiss.normalize_L2(vecs)  # 幂等：与本地 encode(normalize=True) 同口径
    return vecs


def embed_texts_smart(texts):
    """嵌入来源统一入口：回环优先（重试 1 次），失败降级本地 SentenceTransformer。
    stdout 是 JSON 通道，日志走 stderr。"""
    for _ in range(2):
        vecs = loopback_embed(texts)
        if vecs is not None:
            print('[embed] loopback (port %s)' % os.environ.get('MEM_EMBED_PORT', LOOPBACK_PORT_DEFAULT),
                  file=sys.stderr)
            return vecs
    print('[embed] local fallback (loopback unavailable)', file=sys.stderr)
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    vecs = np.array(model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
                    dtype='float32')
    faiss.normalize_L2(vecs)
    return vecs


# ───────────────────────── BM25 通道（Y1）─────────────────────────
BM25_CACHE_PATH = os.path.join(_SKILL_ROOT, 'kb_index', 'bm25.cache')
RRF_K = 60            # RRF 融合常数：score = Σ 1/(k + rank)
FAISS_CANDIDATES = 64  # 无筛选时向量通道取的候选数（融合池）


def load_metadata():
    """全部切片元数据，列表下标 = FAISS 索引行号（同一 SELECT 顺序）。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM slices').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_bm25(metadata):
    """BM25 索引：jieba 分词结果缓存 bm25.cache（pickle）；metadata.db mtime 或条数变更自动重建。"""
    from jieba import lcut
    from rank_bm25 import BM25Okapi
    db_mtime = os.path.getmtime(DB_PATH)
    tokens = None
    if os.path.exists(BM25_CACHE_PATH):
        try:
            with open(BM25_CACHE_PATH, 'rb') as f:
                cache = pickle.load(f)
            if cache.get('db_mtime') == db_mtime and len(cache.get('tokens', [])) == len(metadata):
                tokens = cache['tokens']
        except Exception:
            tokens = None
    if tokens is None:
        tokens = [lcut(r['content']) for r in metadata]
        with open(BM25_CACHE_PATH, 'wb') as f:
            pickle.dump({'db_mtime': db_mtime, 'tokens': tokens}, f)
    return BM25Okapi(tokens)


def bm25_rank(bm25, query, n):
    """BM25 通道：返回前 n 名 (行号, 分数)，行号与 metadata 列表下标一致。"""
    from jieba import lcut
    scores = bm25.get_scores(lcut(query))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
    return [(i, scores[i]) for i in order if scores[i] > 0]


def rrf_fuse(vector_hits, bm25_hits, top_k):
    """RRF 融合：score = Σ 1/(RRF_K+rank)；两通道都命中标 fused。"""
    fused = {}  # 行号 -> {'score': 累计分, 'channels': 命中通道集合}
    for channel, hits in (('vector', vector_hits), ('bm25', bm25_hits)):
        for rank, (i, _s) in enumerate(hits, start=1):
            e = fused.setdefault(i, {'score': 0.0, 'channels': set()})
            e['score'] += 1.0 / (RRF_K + rank)
            e['channels'].add(channel)
    ranked = sorted(fused.items(), key=lambda kv: kv[1]['score'], reverse=True)[:top_k]
    out = []
    for i, e in ranked:
        channel = 'fused' if len(e['channels']) == 2 else next(iter(e['channels']))
        out.append((i, round(e['score'], 6), channel))
    return out


# ───────────────────────── 结构化筛选（Y3）─────────────────────────

def parse_filters(filter_args):
    """解析 --filter key=val（可重复）→ dict；非法键/格式当场报错。"""
    filters = {}
    for item in filter_args or []:
        if '=' not in item:
            sys.exit(f"错误：--filter 格式应为 key=value，收到 {item!r}")
        k, v = item.split('=', 1)
        k = k.strip().lower()
        if k not in ('star', 'palace', 'pattern', 'topic'):
            sys.exit(f"错误：--filter 不支持的键 {k!r}（可选 star/palace/pattern/topic）")
        filters[k] = v.strip()
    return filters


def _has(haystacks, needle):
    return any(needle in (h or '') for h in haystacks)


def match_filter(row, filters):
    """单切片是否通过全部筛选条件。"""
    tags = row.get('tags') or ''
    related = row.get('related_stars') or ''
    topic = row.get('topic') or ''
    ptopic = row.get('parent_topic') or ''
    for key, value in filters.items():
        if key == 'star':
            # 值可含多星缩写（廉破=廉贞+破军）：拆出已知星名，逐星要求命中 related_stars/tags
            stars = [s for s in STAR_VOCAB if s in value]
            if stars:
                if not all((s in related or s in tags) for s in stars):
                    return False
            elif not _has((related, tags), value):
                return False
        elif key == 'palace':
            if not _has((topic, ptopic, tags), value):
                return False
        elif key == 'pattern':
            # 火贪格 → tags 含"火贪格"或 parent_topic 含"火贪"（去尾"格"近似）
            core = value[:-1] if value.endswith('格') else value
            if not (_has((tags,), value) or _has((tags, ptopic, topic), core)):
                return False
        elif key == 'topic':
            if not _has((topic, ptopic), value):
                return False
    return True


def filter_indices(metadata, filters):
    """全部筛选条件命中切片的行号集合。"""
    return {i for i, r in enumerate(metadata) if match_filter(r, filters)}


# ───────────────────────── 目录浏览（Y2）─────────────────────────

BROWSE_TOP_N = 30  # parent_topic 概览首屏截断数


def browse(metadata, args_list):
    if not args_list:
        groups = {}
        for r in metadata:
            groups[r['parent_topic']] = groups.get(r['parent_topic'], 0) + 1
        ranked = sorted(groups.items(), key=lambda kv: -kv[1])
        print(f'共 {len(groups)} 个主题组，{len(metadata)} 个切片：')
        for t, n in ranked[:BROWSE_TOP_N]:
            print(f'  {t}  [{n} 片]')
        if len(ranked) > BROWSE_TOP_N:
            print(f'  …… 共 {len(ranked)} 组，仅显示前 {BROWSE_TOP_N}，--filter topic= 过滤')
        return
    ptopic = args_list[0]
    rows = [r for r in metadata if r['parent_topic'] == ptopic]
    if not rows:
        sys.exit(f'错误：主题组不存在：{ptopic!r}（--browse 查看全部主题组）')
    print(f'{ptopic} 共 {len(rows)} 个切片：')
    for r in rows:
        print(f"  {r['id']}  {r['topic'][:30]}")


def main():
    ap = argparse.ArgumentParser(description='知识库多通道检索（FAISS+BM25 RRF 融合 / 目录浏览 / 结构化筛选）')
    ap.add_argument('--query', default=None, help='查询文本（FAISS 向量 + BM25 关键词双通道 RRF 融合）')
    ap.add_argument('--pan', default=None, help='可选：命盘 JSON，启用星名增强（仅向量通道）')
    ap.add_argument('--top_k', type=int, default=10, help='返回条数（默认 10）')
    ap.add_argument('--browse', nargs='*', metavar='PARENT_TOPIC', default=None,
                    help='目录浏览：无参数=parent_topic 分组概览（前 30）；<parent_topic>=切片清单')
    ap.add_argument('--filter', action='append', dest='filter_args', metavar='KEY=VALUE',
                    help='结构化筛选：star=/palace=/pattern=/topic=（可重复，可与 --query 组合）')
    args = ap.parse_args()

    if not args.query and args.browse is None and not args.filter_args:
        ap.error('须指定 --query / --browse / --filter 至少一项')

    if not os.path.exists(DB_PATH):
        print(f'错误：元数据库缺失（{DB_PATH}）', file=sys.stderr)
        sys.exit(2)

    metadata = load_metadata()

    if args.browse is not None:
        if len(args.browse) > 1:
            ap.error('--browse 至多一个参数：<parent_topic>')
        browse(metadata, args.browse)
        return

    filters = parse_filters(args.filter_args)

    if not args.query:
        # 纯 --filter：列出命中切片清单（全文阅读配合 --browse 定位后走 sqlite/后续 --read）
        hit = sorted(filter_indices(metadata, filters)) if filters else list(range(len(metadata)))
        desc = '、'.join(f'{k}={v}' for k, v in filters.items())
        print(f'筛选 {desc}：命中 {len(hit)} 个切片')
        for i in hit:
            r = metadata[i]
            print(f"  {r['id']}  {r['topic'][:30]}  [{r['source']}]")
        return

    # ── 双通道检索（--query，可叠加 --filter）──
    check_env()
    import faiss

    if not os.path.exists(INDEX_PATH):
        print(f'错误：向量索引缺失（{INDEX_PATH}）', file=sys.stderr)
        sys.exit(2)

    allowed = filter_indices(metadata, filters) if filters else None

    # FAISS 向量通道：星名增强仅用于此通道（BM25 用原始查询词，避免星名串扰关键词权重）
    search_query = build_enhanced_query(args.query, args.pan)
    if search_query != args.query:
        print(f'增强查询(向量通道): {search_query[:120]}...', file=sys.stderr)
    vec = embed_texts_smart([search_query])

    # 有筛选时搜全库保证过滤后仍有足够候选；无筛选只取融合池
    index = faiss.read_index(INDEX_PATH)
    n_search = index.ntotal if allowed is not None else min(max(args.top_k, FAISS_CANDIDATES), index.ntotal)
    scores, indices = index.search(vec.astype('float32'), n_search)
    vector_hits = [(int(idx), float(score)) for score, idx in zip(scores[0], indices[0])
                   if 0 <= idx < len(metadata) and (allowed is None or idx in allowed)]

    # BM25 关键词通道
    bm25 = get_bm25(metadata)
    bm25_hits = [(i, s) for i, s in bm25_rank(bm25, args.query, n_search)
                 if allowed is None or i in allowed]

    results = []
    for i, rrf_score, channel in rrf_fuse(vector_hits, bm25_hits, args.top_k):
        item = dict(metadata[i])
        item['score'] = rrf_score
        item['channel'] = channel  # vector / bm25 / fused
        results.append(item)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
