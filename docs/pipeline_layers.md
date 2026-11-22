# 层级产线编排（流月/流年/流时对齐流日满配管线）

> **必读纪律**：补跑流日/流月前，判据=capture-guide；编排=本文。禁凭记忆自由发挥。

>组件层（liupan/dispatch/check_outputs/assemble/fill_brief/check_brief/extract_predictions）已全部层参数化或层无关，本文补**编排层**。流日/流月/流年/流时编排均以本文为准（定时调度由宿主环境自行承担）。

## 通用七步（以流月 2026-11 为例）

0. **底座闸（链式）**：`bin/check_base.py --level liunian --key 2026 --person <命主名>`——FAIL 则先按本文跑流年产线再回来（流日→流月→流年→大限→原局逐层闸）。
1. **排盘出批次**：`<RUNTIME_PYTHON> core/liupan.py --pan pans/<命主名>.json --level liuyue --month 2026-11 --person <命主名> --outdir`（成功判据=首行「批次目录：」；批次落 `Liuyue/temp/2026-11/`，含 12 宫 input_*.md）。流年用 `--level liunian --year 2026`（落 `Liunian/temp/2026/`）。
2. **12 宫派发**：会话侧 workflow 工具跑 `bin/dispatch_liupan.workflow.js`（吃批次 input，层无关）。**必须 `run_in_background: true` 后台作业化**——前台调用撞宿主 600s 执行墙会被中断。
3. **后验**：`<RUNTIME_PYTHON> bin/check_outputs.py --dir <批次> --no-shengong`；FAIL 项补发后重跑至 PASS。
4. **整体分析头**：读 12 宫结论 → 写 head.md（结构对标流日：主要矛盾定调 + 三轴线式整体分析 + 宜/忌行），存批次目录。
5. **组装**：`<RUNTIME_PYTHON> bin/assemble_report.py --batch <批次> --out Liuyue/报告-2026-11.md --head <head.md>`；若批次产出 fusion_materials.json → 按 docs/palace-prompts.md 融合模板微派发写 fusion_<宫名>.md（L1/L2/L3 叙述分级）→ `--fusion-dir` 重组装嵌入。
**断语溯源纪律**：宫产线全链生效——星曜断语（「某星（在某宫）＝某具体事项」形态）必须落在引擎注入的判据切片内（三层并标/行运匹配判语/语料引文节）；切片内无支撑的断语禁写或降调为「与某象相合」式软描绘——防固有知识混入与自证循环污染统计底座。
6. **简报**：`<RUNTIME_PYTHON> bin/fill_brief_prompt.py --type liuyue --person <命主名> --report <报告路径> --out <简报路径>` 生成派单 → 派发写简报 → `<RUNTIME_PYTHON> bin/check_brief.py <简报> --type liuyue`（六节模板：义理综述/往事为鉴/月度宜忌/逐宫推演/月度经典/月度典故）。
7. **预判提取**：`<RUNTIME_PYTHON> verify/bin/extract_predictions.py --brief <简报> --person <命主名> --date 2026-11-30 --layer liuyue`——**date 传当月最后一日=验证截止日语义**（check_pending 7 天过期窗口从截止日起算，整月自然覆盖，零代码兼容）。

## 流年

同七步：`--level liunian --year YYYY`；check_brief `--type liunian`（年度宜忌等节）；extract `--date YYYY-12-31 --layer liunian`；报告落 `Liunian/报告-YYYY.md`（新管线重产出直接覆盖旧文件，git 留历史）。

## 流时（按需手动，不建定时）

七步同款（简报**可选**：需要时按流日模板近似出轻简报——fill_brief --type liuri 近似；**流时预判行不 extract 入队**（验证价值低）；**规格实测禁走生产 extract**

## 触发时机

- 流月：每月首日由流日任务**步骤 0 底座闸**触发（check_base FAIL→按本文跑流月再跑流日）；
- 流年：每年首日同闸链（流日闸→流月闸→流年产线）；
- 重产出：手动按本文（如老报告升级新管线）。

## RUNTIME_PYTHON

python（建议带 PYTHONUTF8=1）。


## 队列日清（定时任务步骤 1 编排细节·）

- 步骤 1 从「列出」升级为「**销账到零**」：check_pending 列出的当日待验证条目逐条处理——收益数据到达→当日判方向句（按判定标准对照）；当日 events 无对应操作/事件记录→条件句 resolve untriggered（**与收益数据解绑**：不依赖 read_returns 有无数据，无操作记录即可判，禁 no_data 连坐跳过）；数据未到→留队并报一行「待数据 N 条」。
- 设立根因：条件句确认错绑收益环+队列无日清载体，判定全被动。

## 收益环内部数据链（定时任务步骤 7/7b 编排细节）

- **判卷正路=人工判卷**：交易日方向句由定时任务人工判定——读 read_returns 数据→分端对照（主端=期货/投机优先定胜负，次端平稳类不可证伪跳过）→**写完整 theory 四段（引事前象禁新造）→append 落账（theory 随判定必然同时产生，禁机器简版占位+事后补写的两段式）**→calibration 先累档→resolve→更新台账。`auto_judge_returns.py` 降级为可选预检参考（跑它看判定建议可以，落账必走人工 append 完整 theory）；断档补录逐日 `--date` 照旧；回放/测试用 --returns-json 且量纲为小数。
- **台账日更**：步骤 7 判定完成后跑 `verify/bin/update_trading_ledger.py`——交易预判台账（_verify/trading_predictions_ledger.xlsx）自动追加/更新当日行（判定值归档/events 直读；周末休市与已出账条目整条跳过；待判定占位行落判更新禁新增）+汇总页刷新；**预判依据列留空标黄由 agent 补写一句**（当日该端事前盘面象，禁沿用旧名）；**事后归因列 agent 补写，规程=引事前象禁新造**（只解释事前分析已摆出的象组哪个兑现/反向，禁事后配象；判不准且方向反转案例须点明择向错误——喂矫正经验）——内容直接取自当日人工判卷的 theory④（判定时已写，台账列为其浓缩句，无需二次归因）。；**台账十列标准格式（案）**：①日期 YYYY-MM-DD；②类型=方向句/条件句（封闭）；③预判端=总账（固定）；④预判原文=预判句全句含命中标准；⑤置信档=高/中/低/未标（封闭）；⑥预判依据=定性句式「主星结构+关键煞忌+判语定性」≤40字；⑦实际结果=「投资收益（总账）±X.XX%」纯格式；⑧事后归因=双线归因浓缩≤80字；⑨验证判定=预判准确/预判不准/—（无预判）（封闭禁发明）；⑩队列判定=准确/不准/—（无预判）（封闭）；⑪方向句累计准确率=截至该日方向句累计命中/判定（每次日更整列重算；与 calibration 各档 resolved 之和对账，差异行注明手补路径；n<10 仅参考）。休市不记行；交易日必出题；历史空缺按统一标准补造回溯题——正常运行零"—（无预判）"实例。
**台账手补行格式对照**：手工补台账行前必读上一行实际结果列格式并逐字对照（现行标准=「投资收益（总账）±X.XX%」纯格式无尾巴），禁凭旧印象写格式；**交易日 no_data 异常闸**：交易日（周一至周五非节假日）read_returns 报 no_data/待更新≠正常——必须当轮开 xlsx 亲验 C/D 余额列（openpyxl 三行探针）确认真无数据才许跳过；有余额被工具漏读=读取端缺陷当场修（按余额门槛判定，已根修）；**待数据行闭环**：日更脚本对队列判定=待数据的行逐日查收益表，数据到达即自动补判（calibration 先累档→resolve→events 回写→台账落判）——待数据是有出口的状态，禁永久挂账

- **数据读取**：read_returns.py 自动取最新年份账本文件，输出最新可录入条目（日期+总/股票/期货收益率+金额+操作列）
- **去重闸**：_verify/returns_marker.json 的 last_recorded_date——条目日期 ≤ marker 跳过；> marker 才录；**录毕推进**：当日条目完整入库+回写后将 last_recorded_date 更新为该日期（断档全部补录后推进至最新已录日）
- **收益率无值/文件不存在**：打印"投资收益数据待更新"并继续（禁中断后续步骤）
- **断档补录**：marker 落后多条交易日→逐天补录（休市日无条目属正常，勿误判断档；判定标准=交易历）
- **操作环幂等**：当日 events 已有 text 以「今日操作：」开头的条目→跳过防重录（定时任务重跑/补录场景）
- **空态回写**：操作列空+当日 pending 有交易类条件句→当日全部此类条目 resolve --result untriggered --no-capture（次日自动确认不等 7 天）；无此类条目→无动作
- **theory 素材**：该日批次 input_03_财帛.md 切片（批次不存在→干支推简版，append 带 --batch 指向批次路径）

## 校准账（calibration.json）结构与累档口径

- **结构**：{\"高\": {\"resolved\": N, \"accurate\": N}, \"中\": {...}, \"低\": {...}, \"未标\": {...}}——按预判入队时的置信档分桶累计
- **日常累档**（每晨步骤 7 通用）：对当日将 resolve 为 accurate/inaccurate 的每条预判，先读其 confidence 档→该档 resolved+1（accurate 则 accurate+1）→再执行 resolve；文件不存在则按上述结构创建空账（全 0 起步）
- **untriggered 不入账**（未触发不属置信统计口径）；月环月度汇总判定同法累档
- **回审读法**：高置信档 accurate/resolved 连续 3 期 <60% → 简报尾附「置信标签体系回审」提示行

## 月环年环编排（定时任务步骤 8/9 编排细节；触发分支骨架在调度壳）

- **月环（每月 1 日）**：read_returns --month-aggregate {上月}→取上月流月方向句（pending 中 layer=liuyue 且 date 双形态兼容）→对照月聚合判定→**先 append 后 resolve**（回写注记依赖事件先在）→更新校准账
- **统计时序铁律（全文）**：必须在 resolve 之前从队列条目读 confidence 并累入 calibration.json——resolve 会移出条目、档随条目消失；流程=读条目（含档）→统计累入→append→再 resolve。**漏此步=置信档数据永久丢失（不可逆）——调度壳留守硬指令一行即防此**
- **月环事件**：append 月度收益事件（--level liuyue --soft-gate --no-extract 月级首账周期用；theory 素材=该月流月批次 input_03 切片+级联流年财帛结论+月聚合归因对照段）
- **年环（仅 1 月 1 日，月环后）**：年聚合→上年流年方向句对照→append（--level liunian 同构）→resolve→年度校准账累计；**人生断言到窗对照**：pending 中 layer=yuanju/daxian 到窗断言逐条——收益类对年度聚合与逐年序列判定；事件类双通道（查验证库该年同类事件+问命主）——库有或命主确认=按实际判；双通道均无=「未确认」留档**不算不准**；未到窗断言不动
- **跳过**：方向句未标/缺失→跳过判定；月聚合 no_data→跳过
- **月中背离预警（每月 15 日，仅提示不判定）**：月聚合（月中至今累计）对照当月流月方向句→背离→简报草稿区附提示行；无背离或无方向句→静默

## 哨兵与对话触发·内部（定时任务步骤 1.5 编排细节）

- **触发**：sentry_scan.py --date {昨日}（PYTHONUTF8=1；python 解释器需已装 zstandard 依赖）→输出候选/歧义/草稿三段
- **判定**：候选逐条按 capture-guide「事件采集与复核」节判据复核（真事件三要素/误抽四型）——工程语气与自动化系统消息是最常见误抽源（如评论定时任务工作内容的语句撞情绪句式）
- **入库**：真事件按 capture-guide 判卷纪律配口径；零真事件=零入册静默；pending_draft 合并式重建（旧挂起天数+1，≥3 天清除）仅供内部对账
- **渲染**：入册条目由简报派单自动注入「近期事件」节（新格式：日期·宫·类｜事件｜判定+事后归因行）
