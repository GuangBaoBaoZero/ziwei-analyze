---
name: ziwei-analyze
description: 紫微斗数排盘与命盘分析（含本命/大限/流年/流月/流日/流时六层全链）。当用户要求排盘、分析命盘、看流日流年运势、分析某人的盘、或提及紫微相关术语时使用。
---

> **路径锚**：文中 `{ZERO_ROOT}` = ZeroPro 仓库根，取值读 `extensions\anchors.json` 的 `ZERO_ROOT` 键（env 同名覆盖）。

# 紫微斗数 · 十二宫命盘分析技能（ziwei-analyze）

> **本文是什么**：本技能总入口——触发条件/环境/目录/工作流/硬约束/产线衔接。**不是什么**：判据细则（→docs/capture-guide.md）、管线编排（→docs/pipeline_layers.md）、周检手册（→docs/maintenance.md）——细节归各 owner 文档。

本地化技能实现（排盘引擎、知识库、检索逻辑三层分工）。**prompt 层本地自主维护**，外部变更不跟进。

## 触发条件

用户要求"紫微排盘 / 命盘分析 / 十二宫分析 / 生成AI分析 / 分析这个盘"等任务时使用。**"做报告"=完整管线（报告+简报），简报非可选**。**用户本人命盘 = `pans\<命主名>.json`**（用户以「我/我的」提问默认加载，不再索取生辰）。**命名规约：盘文件名=命主名（唯一实体主键）**——按命主名找盘；排新盘=生辰+命主名（**未提供名字必须向用户索取**）；旧规约名 `pan_<YYYYMMDD-HHmm>_<gender>.json` 兼容可读。

## 环境依赖

- Node.js ≥ 14（排盘）；Python ≥ 3.8（检索，零第三方依赖），本机 `python`
- 全程离线；临时产物首选 `.dsh-tmp\`（沙箱被拦时兜底 `%TEMP%\ziwei_<任务名>\`，用完即清；**分析对象的过程批次目录持久保留**）
- **观测 core 脚本输出勿用截断管道**（`| Select-Object -Last N` 致退出码伪报非 0）——验成败看产物文件与无管道 `$LASTEXITCODE`

## 目录

```
ziwei-analyze/
├── engine/          # paipan.js（CLI）/ziwei-engine.js（排盘引擎）/lunar-data.js/ziwei-pure.html（单机网页版）
├── core/            # taxonomy.py 分类排序 · retrieve.py 检索 · prep_inputs.py 宫位输入
│                    # make.py 一条龙入口 · liupan.py 流盘引擎 · geju.py 格局核验
├── bin/             # dispatch_12palaces.workflow.js（原局）+ dispatch_liupan.workflow.js（流盘）
│                    # + check_outputs.py 后验 · check_brief.py 简报校验 · fill_brief_prompt.py 派单生成
│                    # + assemble_report.py 组装 · verify_refs.py 引文复核 · selfcheck.py 自检
├── docs/            # 外置规程：liupan-guide.md / palace-prompts.md / brief_prompt_template.md / quickstart.md / capture-guide.md
├── data/zeropro_open_kb.json   # 知识库（4253 片，默认）
├── data/zeropro_open_kb.json # 开源知识库 4253 片（open 版，--kb open）
├── verify/bin/      # 印证学习库脚本族（append/query/validate）
└── pans/            # 命盘存储（文件名=命主名，不入 git）
```

## 工作流（三步，严格按序执行）

### Step 1 一条命令生成（make.py）

```powershell
& "python" core/make.py --pan pans/<命主名>.json --person <命主名> --topic Yuanju   # 标准分析任务（盘文件须先存在，排新盘用 --birth 见下行）
& "python" core/make.py --pan pans/demo.json --person demo --topic Yuanju     # 他人盘
& "python" core/make.py --birth "1995-06-15 12:30" --gender male               # 生辰直入（存盘加 --save-pan pans\<命主名>.json）
```

outdir 三级解析：`--outdir` 显式 > **`--person <名> --topic <主题>` 标准模式**（内部环境落 `{ZERO_ROOT}\output\<名>\<主题>\temp\<时间戳>\`、开源环境落 `<技能>\output\`）> 缺省 `.dsh-tmp\`。**分析任务一律走 --person/--topic 标准模式，禁手拼库内路径**（8 主题词：Yuanju=原局/Daxian=大限/Liunian=流年/Liuyue=流月/Liuri=流日/Liushi=流时/Match=合盘/Research=研究）。**--person 模式自动生成 `<outdir>\dispatch.workflow.js`**（Step2 直接以其内容执行，禁手改模板拼 CONFIG）。outdir 自包含：pan.json + ctx.json + 12 份 `input_<序号>_<宫名>.md` + `input_13_身宫.md`（命盘信息含身宫标注 + 全盘事实表[三方四正/四化会照/格局核验——程序核毕直接采信] + 知识库切片全量 ≤80K，六十星系专论最优先）。用户给农历生日先换算公历（注意闰月口径）。过程批次持久保留；temp 平铺唯一源，重做=同名覆盖。

**身宫方法论**：身宫=**第13宫位，与其他宫完全同流程**（取星曜→检索语料→判吉凶→输出 input_13/output_13，dispatch 第13路）。身宫性质=判断一个人**后天如何做事**（做事风格/方式/执行力），并在一定程度上反映身体情况（与疾厄宫互参）；**非**"身宫在哪宫=人生重心在哪领域"（常见误说，非本库口径）。四象限判据（语料原文，注入 input_13）：命宫吉+身宫吉=一生多顺遂｜命宫吉+身宫不吉=如美玉，雕琢时可能出毛病，容易减色｜命宫不吉+身宫吉=如顽石，遇巧匠可雕成器｜命宫不吉+身宫不吉=如朽木不可雕，利用好大限流年+人事努力补救。义理综述：官禄宫（先天事业格局）×身宫（后天做事方式）=互补对。

### Step 2 逐宫分析（AI 执行）

**派发适配（agent 执行前自适应，无需用户配置）**：① 宿主有 workflow 派发能力：派发前先把生成物 CONFIG 的 providerA/B 改成本宿主实际 provider 名（单入口=两处同值；双入口分别填），默认总并发 6 路，遇限流/宫级失败多则 perPoolConcurrency 逐级降 2→1；② 宿主无派发工具/非 DSH 环境：跳过 dispatch 派发，直接按 docs/palace-prompts.md 的逐宫 prompt 串行分析十二宫+身宫（输出文件同构，仅速度不同）。

**执行前必读 `docs/palace-prompts.md`（Step 2/3 prompt 原文）+ `docs/liupan-guide.md`（流盘规程）**——硬指令，非可选。

概要：用 `<outdir>\dispatch.workflow.js` 生成物 workflow 派发（池A+池B 双池滚动池，A池1-7路+B池8-13路共13宫，宫级失败换池重发；**进度监控唯一凭据=落盘 output 文件数**）——dispatch 生成物已内嵌 check+auto-refill（checker 子代理+FAIL 宫换池重发），返回 `refilled` 字段=自动补发完成，无需手动后验。agent 直写 `output_<序号>_<宫名>.md`，**回复只含 ≤500 字摘要+该宫 1-3 条全盘线索**（防撑爆上下文）。空窗期先行组装报告程序性部分（头部/盘面总览/核查记录/拼接脚本）；拼接结论节每宫仅取「结论」区间并注入引用切片行（规则见 prompts 文件）。命理复杂度高的宫上下文可达 3 万字符属正常；引用 id 清单存批次 ctx.json（slice_ids）可回查。

### Step 3 综合汇总（第 13 步，主会话）

主会话读12宫结论→写整体分析（~800字含跨宫互动+主要矛盾+论证）→`bin/assemble_report.py --batch <dir> --out <报告.md> --head <头>` →报告=结论汇总+整体分析+核查（自动注入引用行、固定宫序），落 `output\<对象>\<主题>\报告.md`。prompt 原文见 `docs/palace-prompts.md`。

Step 3 综合分析方法（汇总层运用）：
**打破十二宫**：读 12 宫结论后打破宫位界限——看跨宫主题（如财帛忌+福德忌=财心两困）、四化飞化流向（禄入他宫=资源流向）、宫位交互（命宫与福德互映=性格与心态因果）。
**通盘主要矛盾**：从 12 宫结论中识别全盘的主要矛盾（如"三旺一险→主要矛盾在管住手"）——围绕主要矛盾组织整体解读，而非平铺 12 宫结论。

汇总操作顺序：先读 12 宫结论→识别主要矛盾→围绕矛盾组织定调/速览/宜忌（矛盾驱动叙事，非平铺罗列）。

**报告五节格式**：〇盘面总览（程序性）／一整体解读（首段格局定性+≤1200字+核心判断）／二逐宫精简（每宫100-200字）／三十二宫结论汇总（仅"结论"节+引用切片行，引用行放结论段之前）／四核查记录（含引用切片计数）。

## 流盘分析（五层统一链）

大限/流年/流月/流日/流时统一走本链（原局之外的第二条产线）：`core/liupan.py --level <层> <行运参数> --person <对象> --outdir` 排批次（--outdir 必带：仅 --person 只打印不落盘）（自包含：叠盘事实表+12份输入+dispatch 生成物）→ 派发 → `check_outputs.py` 后验 → 主会话出五节报告（定调/全览/四化主线/下层预筛/宜忌），落 `<对象>\<Topic>\报告-<行运参数>.md`。流盘不分析身宫。

**完整规程（层与参数/批次结构/五要素 sys/五节报告/文件名规约）必读 `docs/liupan-guide.md`**——硬指令。

**大批量产线模式**：批量生成多份报告（如全部大限/多年流年）时，每份派一个**单报告全管线子代理**（派单自包含：规程+参数+验收；子代理跑 workflow 工具→check_outputs→head→assemble→简报→check_brief 至 PASS），主会话只派单收摘要防上下文膨胀；过去日重做跳预测提取（check_brief 节 9 豁免，用补档占位行）；池B 池结论偏短宫换 池A 池重发为常态。**派单适配两则**：①check_outputs 实际参数是 `--dir` 非 --batch（写派单前先 --help 核参数面）；②subagent 有深度限制（maxDepth 1）不能再派孙代理——简报环节由子代理本会话按 brief_prompt_template v2 变量替换直写（22 条硬性要求照执行），勿假设可再派。**新链 v2 两则**：③liupan.py 落批次必须 `--person`+`--outdir` 并用（仅 --person 只出 stdout 不落盘——与 make.py 行为不同）；④dispatch 内嵌 checker 三规则不含越层检查，与 check_outputs 规则面不同——派单须预置"FAIL 补发 prompt 带层级禁令+字数硬约束专项提醒"条款，勿依赖 checker 兜全。

### Step 4 精简简报（完整报告落盘后执行，每层同构）

完整报告（原局/大限/流年/流月/流日）落盘后，同步产出一份精简简报 `报告-<标识>-简报.md`——**命理师短文体**（精炼但专业，写给命主的翻译层）。**格式正本=docs/brief_prompt_template.md（v2）——节名节序/22 条硬性要求/全层区间以模板为准，本节只载要点**：

- **节序金字塔（v2）**：义理综述（总·纯理论，末行主打诀全篇唯一，>300 字分 2-3 段）→ 往事为鉴（**常驻节**：有命中=报告「往事为鉴」块经验条目+节末历史参考行；无命中=固定一行「今日盘面，旧案无同款——首遇之局，以义理为准。」）→ 宜忌（**双层结构**：主题行+加粗动作行，矛盾驱动排序；流日含 1-3 条行首「- 预测（高/中/低）：」可证伪行）→ 逐宫推演（分·纯理论，按需查阅）→ 经典（义理）/典故（史事）双栏（有外部古籍检索环境（如可用）时经其检索验证，禁凭记忆引用；暂无该环境时标注语料已有出处，禁编造）。
- 前三节=决策摘要（3 分钟读完知道今天怎么办）；**零工程外露**：无置信词/无相似度数字/无流程声明行/无评审物料；术语首现括注白话；往事为鉴节禁"验证"字样（一等证据说"应验"，二等只说"曾发生过类似事件"）。
- 全层字数区间见模板层类型参数对照（check 全项同源）；FAIL 重写该节至全 PASS。
- **简报派单一律用 `bin/fill_brief_prompt.py` 生成**（--type/--person/--report/--out [--label] [--save]；脚本运行时解析 brief_prompt_template.md 层类型参数表=单一真源，条件块自动展开、未识别变量 fail-fast）——禁手写 prompt 亦禁手工变量替换（一律走模板生成）；模板本体为格式正本。**引文复核（需外部古籍检索环境与 verify_quote.py 工具，本仓未含；暂缺时标注语料已有出处，禁编造）**。

### 流时层（按需）

流时简报与五层同构但**无常驻任务**（按需触发：用户问某日某时辰时才跑）。全链用法（以 2026-11-04 午时为例）：

```
core/liupan.py --level liushi --date 2026-11-04 --hour 午 --person <命主名> --outdir <对象>\Liushi\temp\2026-11-04-午
→ 12宫派发（dispatch 生成物）→ check_outputs.py --dir <批次目录> → assemble_report.py --batch <批次> --out <命主名>\Liushi\报告-2026-11-04-午.md
→ bin/fill_brief_prompt.py --type liushi --person <命主名> --report <命主名>\Liushi\报告-2026-11-04-午.md --out <命主名>\Liushi\报告-2026-11-04-午-简报.md
→ 派发写简报 → check_brief.py <简报> --type liushi 至全 PASS
```

- 产物落位：`<命主名>\Liushi\报告-YYYY-MM-DD-时支.md` + 同名 `-简报.md`；批次目录 `Liushi\temp\YYYY-MM-DD-时支\`（命名即 label 规范）。
- 层参数（节名=时辰宜忌/时辰经典/时辰典故；区间 80-180/150-300/1200-2500）以 brief_prompt_template 层类型参数对照表为单一真源；label 从文件名提取为 `YYYY-MM-DD-时支时`（如 2026-11-04-午时）。
- **流时与流日全对齐产预测三件**：宜忌节含预测行（check_brief 节9）与方向句（节15，标签=时辰方向句）；尾节「待验预测」渲染上一时支批次的待验证项（date 形态 `YYYY-MM-DD-时支`）；简报最末「近期事件」节（在尾节之后，六层统一由 fill_brief 注入，零条=空态常驻）。
- **流时预测入队**：`verify/bin/extract_predictions.py --brief <时辰简报> --person <名> --date YYYY-MM-DD-时支 --layer liushi`——date 原样入队（pred_id 序号取日期部分）；check_pending/resolve_prediction 对时支 date 兼容（过期判定按日期部分）。

### 预测流程六层贯通口径（全链单一表）

尾节「待验预测」与「近期事件」节六层全常驻（空态句照抄，禁跳节）——机制统一：fill_brief_prompt 注入（`{{PENDING_VERIFY_LIST}}`/`{{RECENT_EVENTS_LIST}}`），流日定时任务原 4f 追加步骤已取消。extract_predictions 的 layer 按 date 形态联动（显式 `--layer` 优先）；check_pending 按层分级过期。

| 层 | date 形态（入队/尾节锚） | 尾节上一批次定义 | 过期行为（check_pending） |
|---|---|---|---|
| 原局 yuanju | `终身` | 恒无（空态句） | 长期在验，不自动关闭 |
| 大限 daxian | `第N限` | 第N-1限（第1限无=空态句） | 长期在验，不自动关闭 |
| 流年 liunian | `YYYY`（年内全日期亦认） | 上一年 | 次年即关闭（年份<判定年） |
| 流月 liuyue | `YYYY-MM`（月末日全日期亦认） | 上月 | 次月即关闭（月份<判定月） |
| 流日 liuri | `YYYY-MM-DD` | 昨日批次 | 日级 EXPIRE_DAYS（common.py 单一真源） |
| 流时 liushi | `YYYY-MM-DD-时支` | 上一时支批次 | 日级 EXPIRE_DAYS（按日期部分） |

「近期事件」节口径（六层同构）：自上期**同层**简报（out 同目录 label<本期的最新一份 `报告-*-简报.md`；yuanju 取其余最新 mtime 份）以来 created_at 新入册印证库的该命主条目；首期无上期简报=空态。空态句：尾节「上一批次无待验预测。」／近期事件「本日无新增入册。」。resolve_prediction 零分层（pred_id 驱动，全层通用）。

## 硬约束（分析时必须遵守）


1. 只基于知识库切片与命盘结构，**不编造**命理论断；资料论述少的组合明确说明
2. 空宫只能借对宫（context_text 已标注），禁止从其他宫借星
3. 不确定判断用"可能/倾向/需注意"，禁止绝对化表述
4. 四化只认命盘 siHua 列明的，不得给未列明星曜添加四化
5. 输出的命理内容仅供传统文化学习研究参考，附加免责声明
6. 三层权威来源：盘面数据唯一来源=排盘引擎（禁推断/计算/脑补）；分析判据唯一来源=**当前生效语料库（--kb 所指：open=zeropro_open_kb 开源知识库）**（禁通识/记忆/编造论断）；分析方法唯一来源=方法论规则体系（禁自创方法/偏离规则）。agent只做"读引擎数据+检索语料+按方法论框架组装分析→输出"——三层都不是agent的创作来源。
7. 既定方法论口径按字面执行，禁推广/扩展/一般化——用户没说的层不加，没提的规则不编（历史批次运行教训）。
8. 排盘引擎禁改：ziwei-engine（ziwei-pure.html 内嵌 JS）是唯一权威且已校验——任何方法论修正禁止直接修改引擎代码。修 liupan.py 的解读层（怎么用引擎数据），不修引擎的输出层（数据本身）。

## 预测准确率流程

**pattern_stats.py**：给定当日盘面特征→从印证库检索相似历史事件→聚合准确率→生成 injection_text（双层：统计+注意事项）。调用示例：`python verify/bin/pattern_stats.py --person <名> --combo '{"忌": "天机", "宫": "财帛"}'`。

**注入时机**：dispatch_liupan 派发前——读当日盘面 JSON（output/<命主名>/Liuri/temp/{日期}/pan_liuri_{日期}.json）提取核心特征（日忌星+宫位/命宫地支），跑 pattern_stats.py 获取 injection_text，**在每个宫的子代理 prompt 末尾追加**：
【历史战绩参考】（来自印证库）{injection_text}
使用方式：高置信→重点写+确定性措辞+[高置信]标签；低置信→轻写+[低置信]标签；样本不足→正常写；教科书判据始终是基础——历史战绩是叠加校准。

**置信度标签标准化**：每条预测行末尾统一标注 [高置信]/[中置信]/[低置信]——替代模糊的"大概率/可能"。

**置信度五档**：n<3=样本不足（不标注）/ 3-5=参考（轻写不标档）/ ≥6且rate≥80%=高置信 / ≥6且rate<40%=低置信 / ≥6其他=中置信（正常写）。

**教科书判据始终是基础——历史战绩是叠加校准，不替代语料。**

## 流日定时任务注册

**触发**：用户要求重建/注册/恢复流日定时任务（自然语义，如"重建每日流日定时任务""恢复流日 schedule"）。

**做什么**：用宿主 schedule 工具注册每日流日定时任务——一次注册后续全自动。

**宿主 schedule 工具参数**：
- rrule: 每日 05:00 → `DTSTART;TZID=Asia/Shanghai:<下一个05:00>`+`RRULE:FREQ=DAILY`（DTSTART 必须未来时刻）
- prompt: 流日管线完整指令（见下方模板）
- target: this_session（运行会话内投递；标签关闭=投递积压，会话归档=任务全灭）

**管线 prompt 模板**（宿主 schedule 工具的 prompt 参数原文）：
```
每日流日报告自动生成任务。执行：

1. 预测队列副作用归口：跑 verify/bin/check_pending.py（PYTHONUTF8=1——过期条目自动按"未触发（未回应默认）"关闭并移出）→**顺查 _verify\pending_capture.jsonl 有无未录入条目（已验证待录入的结构化待办）→有则当场补录（append.py --from-capture <pred_id>——prediction/result 自动填充，跑批次写 theory）后再继续**——追问不再由本会话生成，由简报尾节承载（步骤 4e 的 fill_brief_prompt 自动渲染近 7 日待验证追问节）
2. 检查 output\<命主名>\Liuri\报告-{今天日期}.md 是否存在
3. 已存在 → 跳过生成，但仍执行步骤6（预测提取）
4. 不存在 → 检查当月流月报告→不存在则先生成→再执行流日管线：
   a. liupan.py --pan pans/<命主名>.json --level liuri --date {今天日期} --person <命主名> --outdir
   b. dispatch_liupan workflow 12宫派发
   c. check_outputs --no-shengong + FAIL补发
   d. 读12宫结论→写整体分析头→assemble_report→报告
   d2. 若 assemble 产出 fusion_materials.json：读素材包按 docs/palace-prompts.md 微派发写 fusion_<宫名>.md →assemble_report --fusion-dir 重组装
   e. 基于报告写简报：派单一律用 bin/fill_brief_prompt.py --type liuri --person <命主名> --report <报告路径> --out <简报路径>（禁手工变量替换——输出行含「尾节=N 条」）→派发写简报→check_brief --expect-tail N（N=派单输出行尾节数；N>0 时尾节必须存在且条数一致）（全项，含待验预测尾节数据校验）PASS
5. 完成后确认报告+简报就绪
6. 预测提取：verify/bin/extract_predictions.py --brief <简报路径> --person <命主名> --date {今天日期}

注意：{今天日期}=YYYY-MM-DD，{当月}=YYYY-MM。月初跨月先跑流月。年初跨年先跑流年。
python 调用一律带 PYTHONUTF8=1。
```

**注册后验证**：schedule_list 确认流日任务在列。

**补充触发**（非 bootstrap、手动单跑）：用户说"跑流日"或"跑流日 {YYYY-MM-DD}"时，在当前会话直接按以下六步执行（不注册 schedule，只跑一次；与 05:00 定时任务完全同款）。已存在当日报告→跳过生成仅跑步骤 1+6：

1. **前置检查**：check_pending.py（副作用：过期条目自动按"未触发（未回应默认）"关闭并移出）——追问由简报尾节承载（fill_brief_prompt 自动渲染近 7 日待验证追问节，本会话不再单独呈现追问清单）；检查当日流月报告→不存在则先生成流月（月初跨月先跑流月，年初跨年先跑流年）
2. **排盘**：liupan.py --pan pans/<命主名>.json --level liuri --date {日期} --outdir
3. **12宫派发**：dispatch_liupan workflow（双池 池A/池B）→ check_outputs --no-shengong → FAIL 宫补发
4. **组装报告**：读12宫结论→写整体分析头→assemble_report→报告-{日期}.md；若有 fusion_materials.json：按 palace-prompts.md 模板微派发融合分析→--fusion-dir 重组装
5. **简报**：fill_brief_prompt.py --type liuri --person <命主名> --report {报告路径} --out {简报路径} →派发写简报→check_brief（同步骤 4e 口径：全项+条件尾节）→FAIL 项修正至 PASS
6. **预测提取**：extract_predictions.py --brief {简报路径} --person <命主名> --date {日期}

## 命主印证反馈（事件采集）

**触发**：命主报告已发生的现实事件（分析回答完成后执行，任意对话场景）。落账命令：`verify\bin\append.py --person {名} --date {日期} --category {类别} --text "事件描述" --level liuri --theory "分析过程" [--result 终态]`（参数面见 verify/bin/append.py --help；**--level 取拼音值 liuri/liuyue/liunian/liushi——判级三级链=显式最高>时支后缀形态〔hour→liushi〕>类目八类表，细则见 docs/capture-guide.md「事件判级三级链」节**），成功后回显一行供命主改判。

**当场对照判**：落账前完成「预测行/盘面 ↔ 事件」对照，对照清楚即传 --result 终态（自由文本，如：预测准确/预测不准/部分符合）——judged_by=agent，命主保留改判权；仅结果未明需观察窗口（如是否反复类）时省略 --result（默认待验）。禁「theory 写了判定结论却不传 --result」的断链。**自动扫描批语**：对话中回应「昨日事件草稿」待批条目（都对/N不对/补充昨日）→读 _verify\pending_draft.jsonl 逐条处置（对=事件采集规程落账当场判/错=弃/补充=并录）→合并式重建该文件→回显一行；与库内条目矛盾时以口诉为准、旧条目标「已被口述修正」留痕。**固有知识禁令**：模型固有命理知识（含八字框架如六害/神煞等体系外概念、星路连线、宫位拼接）**零发言权**——只允许用于读懂语料文字，**禁止作为任何分析依据写入 theory/简报/报告**；每颗星的落宫与连线（三合/对冲/象义）必须逐字引自当日批次盘面原文，原文没写的线=不存在，禁补。违反=返工+记事故。**原文矛盾仲裁**：逐句锚原文≠原文都对——原文自身表述打架时（如「四化无一落入」vs 同篇「化权照入/借入主星带权」），按产线机制规则（借星带化：借入之星其四化在借入宫生效）仲裁，采机制准的一侧并在 theory 中显式标注矛盾与取舍理由——禁无脑照搬矛盾句。**判定映射禁自造**：判定的每个「盘面语汇→实际事象」对应（如 名→股票/单→期货 类映射）必须有原文或规则出处——**映射也是一种连线**，无据映射=自造连线同罪。判定结论逐项可回溯：命中了什么（引原文语汇）、反了什么（引原文语汇）、映射依据各是什么。**人生断言审题制**：原局/大限层预测（人生断言）入队前**必须经命主审题**——agent 依报告定调出建议稿（每条附转译依据原文句）→呈命主批复→批准后方可 extract 入队；**禁未经审题直接入队**（断言=盘面语汇到可测指标的转译，映射无原文可锚，审题闸是唯一防线）。事件类断言到窗验证走双通道（查印证库+问命主，未确认不算不准）。

**⚠️ 验证录入两步强制清单（防跳步）**：凡涉及预测验证（resolve_prediction.py 改状态），**必须同时走 append.py 事件落账**——resolve_prediction 仅改 pending 状态字段（≠已录入）；append.py 才把事件实体写入 events 文件（含宫位关联+九维度+theory 四段 900+ 字+语料引用「」≥2 处）——**两步缺一=验证未完成，禁向用户报已录入**。theory 格式要求：字数≥900+九维度覆盖≥5/9（主星/四化/辅星/煞星/三方四正/流曜/十二神/化性/杂曜）+语料「」引用≥2 处每处≥10 字符。**机器路径同约束**：定时任务收益录入由判定环节（判定准确/不准）调 resolve 回写（先 append 后 resolve）——两步齐=全自动流程，禁只 resolve 不 append 或反之。

**执行紫微管线/涉及预测印证话题时，先查 _verify\pending_capture.jsonl 有无未录入条目（已验证待录入的结构化待办）→有则当场补录再继续**（append.py --from-capture）。

## 维护

**方法论当前版本：v2026-11-10**（**四化标注源铁律**——liupan 一切渲染（facttable/sihuaLine/input）一律直抄引擎 chain siHua 原值，禁任何星→宫反查；**fail-fast 自检**——批次落盘前逐星比对渲染 vs 引擎，不一致拒出；统计行比率 n<5 闸门与加持块同口径；extractor twelve_gods 判空）。

- **排盘一律引擎铁律（事故级）**：排盘排布一律 ziwei-engine.js 引擎本体（流盘走 `paipan.js --liupan` 出口），**禁任何自写排布/移植/口诀复述**；凡断言"引擎无 X 功能"必先穷尽审函数面再出口。
- **键单宫化（应验宫锚定；两级键=盘型级与星系级，闸门 1 条即注入）**：事件只为真实应验宫（event_palace）记键——星系级=应验宫星系×象别（不论宫名）、盘型级=干+命宫支；append 落账自动写 event_palace（theory ①段宫位判定为主，天然宫位类映射兜底），无 event_palace 记录不生成 L2/L3 键、禁 fallback 全盘；旧记录回填走 `extractor.py --backfill-palace`。
- **派单核对规程**：派单含字段/组件/步骤清单时与方案原文逐格对照；一字之差全变义的关键句逐字抄入并标注逐字实现；验收锚点先实测推算再写。
- **方法论修正 SOP（五步波及）**：升版号→代码修正→extractor 全量重跑→向量索引重建（见 vector/README.md）→旧报告加头部标注行。
- **污染修复类重做必查**：凡批次目的是修某口径污染（如四化错标），交付前必须对报告+简报+output **全文 grep 旧口径模式**（如"化科@申|叠科坐命"）——子代理结论段可能把详解节正确表述**压缩成与旧污染同形的字面**（详解对≠结论压缩不失真）；facttable 抽查与 check_outputs 只查结构不查内容口径，不能只信它们；发现残留=批次源文件与组装报告同步改+复跑 check。
- **详细维护规程见 `docs/maintenance.md`**。
- 命盘存储：`pans\<命主名>.json`（文件名=命主名=唯一实体主键；同生辰重排同名覆盖；不入 git）。
- 报告产出：`output\<对象>\<主题>\`（命主分层；**重做=覆盖唯一 `报告.md`，无版本号**；产出不入 git——约定与词表见 verify/README.md）。


