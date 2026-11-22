<div align="center">

# ziwei-analyze · 紫微斗数预判验证系统

[![CI](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml/badge.svg)](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](./LICENSE)
[![Dataset: CC BY-SA 4.0](https://img.shields.io/badge/dataset-CC%20BY--SA%204.0-green.svg)](./DATASET-LICENSE)

**中文** · [English](./README.en.md)

[快速开始](./docs/quickstart.md) · [知识库规格](./DATA_CARD.md)

</div>

---

一套以「预判 → 验证」闭环为核心的紫微斗数分析系统：盘面给出预判（方向断言），
现实给出事实（收益/事件），系统自动判卷并对账成战绩台账；配 73 部古籍混合检索
与五层引文验证，断语与引文均有出处可查。

```
闭环全景（十步一条链）：

  排盘 ──→ 简报 ──→ 预判 ──→ 验证 ──→ 台账 ──→ 统计回注
  paipan    assemble  断言句    判卷器    xlsx     分层准确率
  十二宫    报告+简报  入队      事实对照  逐条累计  反哺置信分层
     ↑                                              │
     └────────── 判据/断语全程可溯源（引文五层验证）←──┘
```

## 适合谁用

- **紫微学习者/研究者**：需要判据可查证的分析（4253 片白话知识库+73 部古籍可查证）与预判能力的量化验证
- **AI/Agent 实践者**：给 agent 配一套可验证的紫微分析工具链（检索有据/引文有源/判卷有账），断语溯源设计（判据可回查、引文可验证、判卷有台账）
- **数据爱好者**：预判-验证闭环天然是实证实验场（命中率/校准度/置信分层统计）

## 核心特色（以下对照 bin/ 与 verify/ 实际实现）

### 1. 预判-验证闭环（本项目的灵魂）
- **预判入队**：简报中的方向断言（"预判（高/中/低）：今日总收益大概率为盈"）自动提取入待验队列，带条件句与命中标准
- **自动判卷**：交易日后自动对照实际收益（总收益 ≥0＝预判准确），判定写回台账
- **战绩台账**：xlsx 台账逐条累计（方向/置信/结果/准确率），按置信分层统计准确率——验证越多，统计越可信（示例形态见 verify/README）
- **不止盈亏**：事件验证八类（交易盈亏/出行/健康/口舌是非/意外/情绪/决策/人际）

### 2. 典籍库：73 部古籍原文 + 混合检索（开箱即用）
- **语料**：73 部经史子集精选（含《资治通鉴》294 卷、《明史》153 卷、《元史》78 卷全本），一书一 txt，古籍原文，公有领域
- **检索**：FAISS 语义向量 + 字面精配（简繁归一+标点归一）RRF 融合，书级聚合排序
  - 语义档：白话"说话要谨慎"能找到"言不可不慎"
  - 字面档："欲速则不达"精准定位《论语》原文段
- **预建随包**：20969 块索引 + bge 模型全部随包，**装完依赖即用，零下载零联网**
- **一句话自动配置**：`python bin/setup_vector.py` 自动检测→安装依赖→自检（agent 可全自动执行）

### 3. 引文验证：五层容错逐字把关
`classics_verify.py --quote "学而时习之，不亦说乎" --book 论语`
逐字 → 空白归一 → 繁简等价 → 跨行拼接 → 虚词差异，五层逐级容错；命中报书名+行号，
全败报各层最近差异。**AI 引经据典不再有编造空间**。

### 4. 产线四编排器：日/周/月/年一键化
`ziwei_daily.py`（13 步）/ `ziwei_monthly.py` / `ziwei_yearly.py`（10 步）/ `weekly_check.py`（L1 十三项机器检+L2 待办）
幂等设计、断点续跑（--from-step）、JSON 运行日志。

### 5. 排盘引擎 + 白话知识库
- Node.js 排盘引擎（零依赖）：`node engine/paipan.js --birth "1995-06-15 12:30" --gender male`
- 白话知识库 4253 片（CC BY-SA 4.0）：主星/四化/辅煞/宫位判据切片，FAISS+BM25 混合检索（预建索引随包）
- 可选向量语义检索：装 faiss 后模型随包本地加载，零联网

## 快速开始

前置：Node.js ≥16（排盘用）；Python ≥3.10（产线用；3.12 自带 FTS5/sqlite）

> **Windows 用户注意**：①下述 `python` 命令若提示找不到，改用 `py`（或在安装 Python 时勾选 Add to PATH）；②控制台中文乱码时，先设 `PYTHONUTF8=1`（或执行 `chcp 65001`）再跑。

```bash
git clone https://github.com/GuangBaoBaoZero/ziwei-analyze.git
cd ziwei-analyze

# ① 排盘（零依赖，立即可用）
node engine/paipan.js --birth "1995-06-15 12:30" --gender male
# → 输出十二宫+主星+四化的完整命盘 JSON

# ② 检索配置（自动装依赖+自检，一条命令）
python bin/setup_vector.py
# → [1/5] 依赖… [5/5] 真查询自检 → 全部就绪

# ③ 古籍检索（语义+字面混合）
python bin/classics_search.py --keywords "欲速则不达"
# → 论语 / 段18 / …子曰："无欲速，无见小利。欲速则不达…"

# ④ 引文验证（防 AI 编造）
python bin/classics_verify.py --quote "山下有雷，颐" --book 周易
# → [HIT] 周易 ①逐字 第578行
```

详见 [docs/quickstart.md](docs/quickstart.md)。

## 目录结构

```
bin/        产线编排器+典籍三件套（verify/build_index/search）+setup 等 18 件
verify/     验证学习库：预判提取/自动判卷/台账/统计 18 件
core/       报告组装引擎（make.py 三级解析）
engine/     排盘引擎（Node.js 零依赖）
data/       知识库 4253 片 + 古籍 73 部 + 检索索引（预建）
vector/     紫微语义检索（预建索引+bge 模型随包）
docs/       使用指南五份
dsh-plugin/ 可选 DSH 面板插件
```

## 体量与数字

| 项 | 数 |
|---|---|
| 古籍 | 73 部（公有领域） |
| 知识库判据切片 | 4253 片 |
| 古籍检索索引 | 20969 块（768 字/块） |
| 引文验证 | 五层容错 |
| 构建断言 | 14/14（隐私/完整性/一致性机器检） |
| 包体 | 约 290MB（模型+索引全预建） |

## 局限性（如实声明）

- **向量语义检索需装依赖**：`pip install faiss-cpu` 等五件（`setup_vector.py` 自动装）；不装仍可用零依赖的 txt 字面检索（自动降级）
- **战绩不会从天降**：预判-验证闭环需要你自己的验证数据流（收益记录或事件记录）持续输入，台账从零积累
- **简报生成需 LLM 配合**：本仓库提供工具链与模板（docs/brief_prompt_template.md），产线全自动但写手环节由你的 agent 承担
- **交易日历自动更新需 akshare**：`pip install akshare`（setup/定时任务会自动尝试）；未装或断网时用包内预置日历（覆盖至 2027-11），过期按休市保守处理
- **古文语料为现代整理形态**：带标点/简体（检索层已做繁简与标点双向归一）

## 协议

- 代码：[MIT](LICENSE)
- 知识库数据集：[CC BY-SA 4.0](DATASET-LICENSE)
- 古籍库（data/classics/）：古籍原文，公有领域，可自由使用
- 检索模型 bge-small-zh-v1.5：BAAI，MIT License（随包分发）
