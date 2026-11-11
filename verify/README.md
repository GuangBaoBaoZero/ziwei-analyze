# verify/ —— 命主印证学习库

## 定位

命主现实事件印证账本：命主报告已发生的现实事件 → 结构化落账 → 供紫微分析结果的事后印证与复盘。本目录只放**代码资产**（README + bin 脚本），**数据不入 git**（含命主行为数据，属隐私）。

## 隐私约定

- 事件数据（`events_*.jsonl`）一律不入 git；数据目录首建时自动写 `.gitignore`（`*` + `!.gitignore`）。
- 跨命主查询（`query.py --scope cross`）输出脱敏投影：命主名替换、原文不输出、日期截到月。

## 数据落点（三级解析，`--data-dir` 显式指定则最优先）

1. anchors 定位：逐级向上找 `anchors.json`（目录内直放或 `extensions/` 下），读 `ZERO_ROOT` 键拼数据目录；
2. anchors 缺席（开源用户等场景）：回退 `<技能根>\verify\data\`，首建自动写 .gitignore。

## 事件 schema（JSONL，每行一事件）

| 字段 | 说明 |
|---|---|
| event_id | 时间基 `<命主>-<YYYYMMDD-HHMMSS>-<seq3>`，同秒内递增 |
| person | 命主名（正则 `^[\w\u4e00-\u9fff-]+$`） |
| event_date | `YYYY-MM-DD` / `YYYY-MM` / `YYYY` |
| date_precision | day / month / year |
| level | 事件对应分析层级（流日/流月/…），无分析上下文留空字符串 |
| category | 白名单八类：交易盈亏/出行/健康/口舌是非/意外/情绪波动/重要决策/人际事件 |
| text | 事件原文 |
| verify_result | 符合/部分/不符/待验（默认待验） |
| judged_by | 初判 agent 或用户改判 |
| session_hint | 会话指针，可空 |
| combo_features | 预留对象，MVP 恒空 `{}` |
| created_at | 落账时刻 |
| theory | 分析过程四段（①宫位判定 ②结构原文+语料判据引用 ③九维度推理链（主星/四化/辅星/煞星/三方四正/流曜/十二神/化性/杂曜） ④事件对照），落账主体，≥900 字 |
| theory_amended_at | theory 改判时间戳 |
| event_palace | 应验宫（append 落账自动写入；无则不生成星系级/盘型级键） |
| palace_source | 宫位判定来源（theory ①段为主，天然宫位类映射兜底） |
| palace_ambiguous | 宫位判定存疑标记 |
| pred_id | 关联预测 id（预测验证流程用，可空） |
| prediction | 关联预测原文（可空） |
| result | 落账时验证结果自由文本（预测准确/预测不准/部分符合等；缺省待验） |
| outcome | 事件结果（可空） |
| structure_snapshot | 落账时盘面结构快照 |

## 分片与不变量

- 滚动分片：`events_<person>-%03d.jsonl`，末片条数 ≥ `VERIFY_SHARD_SIZE`（默认 5000）则开下一序号。
- 枚举用正则 `^events_(.+)-(\d{3})\.jsonl$` 分组精确匹配 owner（防"张"误配"张三"），片号按数字序排序。
- 不变量（validate.py 校验）：非末片恒满；event_id 全库唯一；owner 与文件名一致。

## 依赖

核心链三脚本（`append.py` / `query.py` / `validate.py` + 共享 `common.py`）**纯 Python 标准库，零第三方依赖**，任何 Python ≥ 3.8 可跑；`embed.py` 需向量检索环境（faiss 等，安装见 vector/README.md），清单中除 embed.py（需向量环境）外均零依赖；common.py 为共享模块非独立脚本。

## 脚本清单（verify/bin/）

append.py 落账 · query.py 查询 · validate.py 校验 · check_pending.py 过期关闭+追问清单 · extract_predictions.py 简报预测提取 · resolve_prediction.py 验证状态回写 · pattern_stats.py 历史战绩统计 · suggest_palace.py 事件归宫建议 · palace_extract.py 宫位提取 · extractor.py 全量抽取与回填（含 --backfill-palace） · embed.py 向量索引 · derive_insights.py 经验链派生 · common.py 共享工具。

各脚本参数面以 `--help` 输出为准。
