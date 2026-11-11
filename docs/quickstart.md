# Quickstart

> **本文是什么**：入门路径（假定读者=会用命令行的新用户；按先修排序渐进）。**不是什么**：完整规格（→SKILL.md）与判据（→capture-guide）。

从安装到看到第一张命盘分析，约 5 分钟。

## 前置条件

- Python >= 3.8
- Node.js >= 14

## 安装自检

```bash
python bin/selfcheck.py
```

前四行显示 PASS 即环境就绪。第五行（向量引擎）为可选项，未配置不影响核心功能。

## 排一张盘

```bash
node engine/paipan.js --birth "1995-06-15 14:00" --gender male
```

终端输出完整的十二宫星曜排布 JSON。将日期替换为自己的生日即可。

## 查看知识库判据

```bash
python -c "
import sys; sys.path.insert(0, 'core')
import retrieve
kb = retrieve.load_kb_data('data/zeropro_open_kb.json')
idx = retrieve.build_indexes(kb)
slices = retrieve.get_star_system_slices(idx, {'raw_stars': {'main': ['武曲', '贪狼']}})
for s in slices[:3]:
    print(f'[{s["topic"]}] {s["content"][:80]}...')
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

## 印证库（可选）

印证库提供预测、验证、历史参考的流程。详见 [verify/README.md](../verify/README.md)。

## 后续阅读

- [SKILL.md](../SKILL.md) -- 完整分析工作流
- [liupan-guide.md](liupan-guide.md) -- 流盘分析指南

---

*本工具仅供传统文化学习研究参考。*
