<div align="center">

# ziwei-analyze · 紫微斗数判卷验证系统

[![CI](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml/badge.svg)](https://github.com/GuangBaoBaoZero/ziwei-analyze/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](./LICENSE)
[![Dataset: CC BY-SA 4.0](https://img.shields.io/badge/dataset-CC%20BY--SA%204.0-green.svg)](./DATASET-LICENSE)

**中文** · [English](./README.en.md)

[在线体验](https://guangbaobaozero.github.io/ziwei-analyze/) · [快速开始](./docs/quickstart.md) · [知识库规格](./DATA_CARD.md)

</div>

---

## 这是什么

紫微斗数排盘与分析工具链，包含排盘引擎、知识库、判卷验证与统计报告四个模块。

- **排盘引擎** — Node.js 实现，零第三方依赖，六层全链
- **白话知识库** — 4253 片知识切片（CC BY-SA 4.0），覆盖十四主星系、十二宫位、格局、四化、行运全维度判据
- **检索与批产脚本** — Python 实现，零第三方依赖，支持关键词检索与向量语义检索（可选）
- **印证学习库** — 事件采集、判卷验证、置信校准、模式统计，把命理分析变成可量化的实证体系
- **DSH 面板插件** — 可选，DeepSeek Harness 用户可一键安装可视化面板

## 核心能力

- **六层全链排盘** — 本命/大限/流年/流月/流日/流时，Node.js 零依赖
- **AI 逐宫分析** — 知识库判据驱动，12 宫独立分析+整体汇总+融合分析
- **预测验证闭环** — 预测入队→事件采集→判定→置信校准，命理分析可量化
- **统计报告** — 准确率、分档统计、模式洞察、月度年度环
- **知识库检索** — 4253 片，覆盖星曜、宫位、格局、四化全维度
- **向量语义检索** — 可选 faiss 子模块，语义级命中

## 快速开始

```bash
git clone https://github.com/GuangBaoBaoZero/ziwei-analyze.git
cd ziwei-analyze

# 自检
python bin/selfcheck.py

# 排盘（需要 Node.js ≥14）
node engine/paipan.js --year 1990 --month 8 --day 15 --hour 14 --gender male

# 检索知识库
python core/retrieve.py --star 紫微 --palace 命宫
```

详细指引见 [quickstart.md](./docs/quickstart.md)。

## 目录结构

```
├── engine/          # 排盘引擎（Node.js，零依赖）
├── core/            # 分类/检索/输入准备/流盘引擎/格局核验
├── bin/             # 派发/校验/组装/简报生成
├── verify/bin/      # 印证学习库（采集/判卷/校准/统计）
├── data/            # 白话知识库 4253 片（CC BY-SA 4.0）
├── docs/            # 操作指南/宫位模板/简报规格/采集指南
├── vector/          # 向量语义检索子模块（可选 faiss）
├── dsh-plugin/      # DSH 可视化面板插件（可选）
└── engine/ziwei-pure.html  # 单机网页版（浏览器直接打开）
```

## 协议

- 代码：[MIT](./LICENSE)
- 知识库数据集：[CC BY-SA 4.0](./DATASET-LICENSE)

