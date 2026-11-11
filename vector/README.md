# vector/ · 向量检索子模块（ziwei-analyze）

多通道检索 CLI（FAISS 向量 + BM25 关键词 RRF 融合），预建索引随仓提供。
检索层本地运行；回答层由宿主 AI 承担。

## 触发条件

用户提出紫微斗数**知识性问题**（如"廉贞贪狼在巳亥坐命事业如何""天刑天姚同宫什么含义"）
或要求"查知识库/语义搜索"时使用本模块。
本模块为 ziwei-analyze 的向量检索层，也可独立用于**自由问答**，检索方式为多通道检索（向量语义 + BM25 关键词 RRF 融合），并支持目录浏览与结构化筛选。

## 环境依赖

- Python 3.x，依赖：faiss-cpu / numpy / sentence-transformers / jieba / rank-bm25
- 模型：BAAI/bge-small-zh-v1.5（与建库模型一致，不可更换；已在本地缓存时自动离线加载）
- 就绪自检：
  ```powershell
  pip install -r requirements-vec.txt
  python vector/vector_search.py --query 测试
  ```
  依赖缺失时脚本会友好报错并给出安装命令

## 目录

```
vector/
├── vector_search.py           # 多通道检索 CLI（FAISS+BM25 RRF 融合 / --browse / --filter）
├── build_index.py                  # 索引生成（维护用）
├── kb_index/vectors.index          # FAISS HNSWFlat 索引（9.7M，4253 条）
├── kb_index/metadata.db            # SQLite 元数据（与索引成对）
└── kb_index/bm25.cache             # BM25 分词缓存（db 变更自动重新生成，可删）
```

## 工作流

### Step 1 构造检索（AI 执行）

```powershell
python vector/vector_search.py --query "用户问题原文" --top_k 10
# 可选带命盘（星名增强，命中更聚焦当前盘）：
python vector/vector_search.py --query "事业如何" --pan pan.json --top_k 10
```

`--pan` 时自动执行查询增强：
`问题 + 命盘前 30 颗星名 + 问题中星曜名重复两遍加权`（仅向量通道；BM25 用原始查询词）。
pan.json 可来自 ziwei-analyze 技能的排盘产物（跨技能协作，AI 自行编排）。

**双通道融合**：--query 自动走 FAISS 向量 + BM25 关键词两通道，RRF 融合排序
（score = Σ 1/(60+rank)）——精确术语命中排前，语义相关补充。结果含 `channel` 标注（vector/bm25/fused）。
BM25 分词缓存于 `vector/kb_index/bm25.cache`（首次构建约 2 秒，之后毫秒级加载；metadata.db 变更自动重新生成）。

### 多通道检索补充用法

```powershell
# 目录浏览（两级）：parent_topic 分组概览（前 30）→ 主题组切片清单
python vector/vector_search.py --browse
python vector/vector_search.py --browse "天同格局"

# 结构化筛选（可重复组合）：
#   star=    related_stars/tags 含指定星（支持廉破=廉贞+破军 多星缩写拆解）
#   palace=  topic/parent_topic/tags 含指定宫位
#   pattern= tags 含指定格局（火贪格自动容错 tags 含"火贪格"或 parent_topic 含"火贪"）
#   topic=   topic/parent_topic 含指定主题词
python vector/vector_search.py --filter star=廉贞
python vector/vector_search.py --filter star=廉破 --filter topic=化忌

# 筛选+检索组合：先筛出子集，再在其中做 FAISS+BM25 双通道检索
python vector/vector_search.py --query "事业" --filter star=廉破 --top_k 10
```

注意：topic 词汇以语料实际用词为准（如"化禄/化忌"而非泛称"四化"，后者在 topic 字段零出现）；
星系组合 tag 语料已含缩写形（如"廉破"），star= 筛选可直击。

### Step 2 基于切片作答（AI 执行）

拿到 top_k 切片（含 id/topic/parent_topic/content/source/tags/score）后：

1. 优先采信 score 高、与问题主题直接相关的切片
2. **只基于返回切片作答，不编造、不外引**切片之外的命理论断
3. 引用出处（source 字段）
4. 资料未覆盖或论述冲突时如实说明，不用绝对化表述
5. 回答末尾注明参考切片数与命中主题，便于用户回查

### 回答格式

```
## 答
{基于切片的回答}

**依据**：{命宫 贪狼 · ts_4031 等切片 id+出处，列出主要参考切片}
```

- top_k 默认 10（需要更多结果时 --top_k 15）；返回顺序按 RRF 融合分数排序

## 验收（环境就绪后执行）

冒烟验收：`python vector/vector_search.py --query '武曲' --top_k 3` 返回非空结果即可。

## 维护

- 知识库更新：master 语料更新后重跑 `build_index.py` 重新生成 `vector/kb_index/`
（两文件 FAISS 行号↔SQLite 记录一一对应，单换会错位）
- 依赖环境变化：保证 faiss-cpu / sentence-transformers / jieba / rank-bm25 可 import，模型名不可改

## 冷启动说明

首次运行向量检索时 sentence-transformers 需联网下载 BAAI/bge-small-zh-v1.5 模型（约 100MB）；建议国内用户设置环境变量 `HF_ENDPOINT=https://hf-mirror.com` 加速下载。下载完成后全部推理均在本地完成。
