# Quickstart

> **本文是什么**：入门路径（假定读者=会用命令行的新用户；按先修排序渐进）。**不是什么**：完整规格（→SKILL.md）与判据（→capture-guide）。

从安装到看到第一张命盘与第一条检索结果，约 5 分钟。主线四步（与 README「快速开始」一致）。

## 前置条件

- Python ≥3.10（产线）；检索工具 3.8+ 可用
- Node.js ≥16

Windows 用户：`python` 命令找不到时改用 `py`；控制台中文乱码时先设 `PYTHONUTF8=1`（或 `chcp 65001`）。

## ① 排一张盘

```bash
node engine/paipan.js --birth "1995-06-15 14:00" --gender male
```

终端输出完整的十二宫星曜排布 JSON。将日期替换为自己的生日即可。输出字段（十二宫/主星/四化/大限等）的可视化对照见 `engine/ziwei-pure.html`（浏览器打开即得排盘界面）。

## ② 检索配置（自动装依赖+自检）

```bash
python bin/setup_vector.py
```

一条命令完成依赖检测→安装→索引/模型在位检测→真查询自检，末段显示「全部就绪」（其前 [6/6] 交易日历段亦应 OK）即成。

## ③ 古籍检索（语义+字面混合）

```bash
python bin/classics_search.py --keywords "欲速则不达"
```

## ④ 引文验证（防 AI 编造）

```bash
python bin/classics_verify.py --quote "学而时习之，不亦说乎" --book 论语
```

## 验证安装（可选）

```bash
python bin/selfcheck.py
```

前四行显示 PASS 即环境就绪。第五行（向量引擎）为可选项，未配置不影响核心功能。

## 查看知识库判据

```bash
python -c "
import sys; sys.path.insert(0, 'core')
import retrieve
kb = retrieve.load_kb_data('data/zeropro_open_kb.json')
idx = retrieve.build_indexes(kb)
slices = retrieve.get_star_system_slices(idx, {'raw_stars': {'main': ['武曲', '贪狼']}})
for s in slices[:3]:
    print(f'[{s[\"topic\"]}] {s[\"content\"][:80]}...')
"
```

## 生成完整分析（需 AI 代理宿主）

本技能的核心十二宫分析需要 AI 代理执行。将本技能目录添加到宿主的技能路径，然后在对话中发起分析请求即可。

若无 AI 代理宿主，可使用引擎 CLI 排盘和浏览器面板体验核心功能。

## 浏览器排盘面板

用浏览器打开 `engine/ziwei-pure.html`，输入生辰即可获得可视化排盘界面。

## 语义检索（可选）

安装向量三件套后可启用语义检索（`vector/` 子模块）：

```bash
pip install -r requirements-vec.txt
python vector/vector_search.py --query "武曲贪狼坐命事业" --top_k 3
```

详见 [vector/README.md](../vector/README.md)。

## 验证库（可选）

验证库提供预判、验证、历史参考的流程。详见 [verify/README.md](../verify/README.md)。

## 后续阅读

- [SKILL.md](../SKILL.md) -- 完整分析工作流
- [liupan-guide.md](liupan-guide.md) -- 流盘分析指南



## 收益对照验证（进阶）

```bash
python verify/bin/returns_import.py --make-sample returns.csv
python verify/bin/auto_judge_returns.py --csv returns.csv --person demo
python verify/bin/update_trading_ledger.py --person demo --ledger demo_ledger.xlsx
```

样例数据全虚构；接入你的真实收益后即得累计预判准确率台账。详见 README「核心特色·预判-验证闭环」节。

## 古籍库（classics/）

73 部古籍原文（经史子集精选，公有领域）随包附带：

```bash
# 首次配置（自动装依赖+自检，agent 可自动执行）
python bin/setup_vector.py

# 可选：自建全文检索索引（faiss）
python bin/classics_build_index.py
```
---

*本工具仅供传统文化学习研究参考。*
