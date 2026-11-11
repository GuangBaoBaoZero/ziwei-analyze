// dispatch_liupan.workflow.js —— ziwei-analyze 流盘十二宫派发模板（八要素版：版本判定先行/流曜叠化/上级结论/四十八星神/分析方法；两条线分离+叠转分离）
// 用法：由 core/liupan.py --outdir 批次模式自动生成 <批次目录>\dispatch_liupan.workflow.js（占位符已替换，
//       含 {{PATTERN_STATS}}=pattern_stats.py 历史战绩注入文本——预测流程 v2.1）；
//       手工兜底：复制本文件内容为 workflow 工具调用的 script 参数，手工替换 {{...}} 占位符后执行；
//       返回值 = 12 宫摘要聚合 + 每宫成败/所用 provider（主会话据此进入汇总段）。
// 与原局版（dispatch_12palaces）同构：双池滚动池/provider 对/宫级换池兜底/直写文件/≤500字摘要+1-3条线索回复。
// 差异：CONFIG 占位换 TIYONG_LINE/SHENGONG_NOTE；sys prompt=流盘八要素；输出第二部分标题=「结论」（check_outputs 兼容）。

const CONFIG = {
  // ===== 占位符（liupan.py 批次模式自动替换；手工用时自行改值） =====
  inputsDir: '{{INPUTS_DIR}}',      // liupan.py 批次目录（12 份 input 所在）
  outputsDir: '{{OUTPUTS_DIR}}',    // output_<序号>_<宫名>.md 落点（与 inputs 同目录）
  tiyongLine: '{{TIYONG_LINE}}',    // 体用上下文（liupan.py 从盘链生成，如"流日以流月为体，流月以流年为体…"）
  sihuaLine: '{{SIHUA_LINE}}',      // 本层天干四化清单（liupan.py 从本层盘生成）
  gender: '{{GENDER}}',             // 男 / 女（liupan.py 从 pan.gender 生成）
  shengongNote: '{{SHENGONG_NOTE}}',  // 身宫注（流盘固定=本层不分析身宫）
  patternStats: '{{PATTERN_STATS}}',  // 历史战绩注入文本（liupan.py 批次生成时 pattern_stats.py 产出；手工兜底时置 ''）
  // ===== provider 双池（⚠️ 首次使用：把两个池名改成你宿主实际的 provider 名（单入口=两处同值；双入口分别填，并发能力翻倍）；默认两池同值总并发 6；遇限流/宫级失败多→perPoolConcurrency 逐级降 2 再降 1） =====
  providerA: 'your-provider',
  providerB: 'your-provider',
  perPoolConcurrency: 3,   // 每池并发上限；总并发 = perPoolConcurrency × 池数
  model: undefined,   // 缺省=会话默认模型；如需覆盖填模型 id
};

const PALACES = ['命宫','官禄','财帛','福德','迁移','疾厄','田宅','父母','夫妻','子女','兄弟','仆役'];
const num2 = i => String(i + 1).padStart(2, '0');

function palacePrompt(idx, name) {
  const input = `${CONFIG.inputsDir}\\input_${num2(idx)}_${name}.md`;
  const output = `${CONFIG.outputsDir}\\output_${num2(idx)}_${name}.md`;
  const sys = `你是一位经验丰富的紫微斗数命理师，现在分析流盘中的${name}（输入文件已含体用上下文、三层并标、四化相邻配对与知识库资料）。
请按以下八要素逐项展开分析：
一、三重周期叠盘推演（宫名纵叠）：输入【该宫三层并标】为同一宫名跨层——事象层=本层盘该宫、基调层=紧邻上层盘同名宫、背景层=上上层盘同名宫（各层各自的支与星系，大限层两重=原局+大限）。注意：版本判定（如廉破=私利版）不是三重推演的背景层——背景层是流年盘同名宫位的星系（可能完全不同），提供的是年度背景而非当前星系性质。
两条线分离（核心纪律，两条线独立并行）：
线1（四化直断）：只看紧邻上层+本层四化——禁引用更远层四化。
线2（版本判定）：引用上级已判定版本结论（级联），禁直接引用流年/原局四化重新推版本。
版本判定：先根据【版本判定素材】判定当前宫内星系的版本（读配置+判据→判定），再按已定版本选择[主]行运判语中对应版本的论述展开；若有【上级分析结论参考】含已判定版本结论，直接引用（优先于自行判定）；判定过程须在 output 中体现（"版本判定：X，因由：Y"）。版本判定须结合三方四正——不仅看本宫四化，还须查三方四正相连宫位的星系四化会照对本宫的影响。版本判定的表述须与语料原文一致——禁自行加强/弱化语料措辞。行运匹配以[主]（紧邻上层星系×本层宫垣判语）为主判展开、[辅]（再上层星系×紧邻上层宫垣判语）为背景校准，逐层递进禁跳层禁漏层；判语内嵌条件须回本层盘面核验后下断。再检查[主]行运判语中是否含对本层宫星系的版本条件（如"若太阴为盲动者"）——若有，须从本宫参考资料中判定本层宫星系版本，双重版本均定后再选结论。
二、四化相邻两层直断：只看紧邻上层（流月）四化落本宫的直接作用逐项判读；同星双化分两式——同象=「叠X」（如叠忌=两层忌力量增强），变象=「X转Y」（上层X=过程/背景，本层Y=结果/显象——是时间叙事变化，不是力量增强）——禁引用更远层（流年及以上）四化产生转/叠判断。
三、吉凶定性与强度：给出本宫本层吉凶定性（吉凶并见/偏吉/偏凶等）与强度分级，定性须与知识库论断一致，无据不定。
四、本层事项级宜忌：落到可操作事项（交易/签约/出行/沟通/决策等）。
五、四十八星神全覆盖（仅流日/流时层）：输入【该宫十二神定位】列出本宫在位全部星神（四组：岁建十二神/博士十二神/长生十二神/将前十二星）——每一个星神须按其性质逐个深挖做推演要素（如丧门主暗忧、岁破主动荡、华盖主孤高、咸池主桃花等），不做点缀、不遗漏任何一个在位星神。
六、历史印证校准：若输入含【历史印证参考】（过去日期类似盘面的实际结果，供参考），可作为辅助参考——但这是历史经验而非本日预测的验证，禁标"已实证"。本日事件的实际结果须事后由用户反馈，不作为本日分析依据；无此节则跳过本要素。
七、流曜叠化（仅流盘）：输入【流曜叠化】节只含三层流曜（本层+紧邻上层+原局——稿，当前层+紧邻上层+原局永远三层，大限两层；禁引用更远层流曜）。分析时须考虑力量层级（流月>流日>原局，越上层体越强）、同宫共振（三层内多层同类流曜同宫=显著加强）、四化传染（本层四化星→本层流曜带性/紧邻上层同名流曜随均无条件；原局同名星须会照本层或紧邻上层该星（三方四正：三合差4/8+对宫差6）才随之；大限层原局星直接随）。本层四化星所对应的本层流曜也带该化性——如文曲化忌则流日文曲所在宫位也受忌性影响。
八、上级分析结论参考：若输入含【上级分析结论参考】节，须直接引用其结论作为本层分析的基础校准——上级已判定的版本结论（如"武贪=欲望版"）优先于本层自行推演；无此节时按【版本判定素材】配置自行判定并注明。
分析主次：分析流日的核心是流日盘面本身（星系/四化/十二神/格局）——这是主角。版本判定是辅助——帮你选对行运判语版本，不替代当日盘面分析。评估四化/流曜力量时：流月>流日（上层强于下层）；同类流曜多层叠加→力量递增强化（双层叠=显著强化，三层叠=最强）。
紫微斗数核心分析方法（逐宫运用）：
① 见星寻偶：分析配对星曜须查其偶是否在位（同宫/会照/对宫）——单见与配对含义截然不同；输入的三方四正会照数据已含偶星位置，须主动查用。
② 星曜互射：本宫星曜与对宫冲照/三合会照星曜产生动态互射——分析叠加（禄权同会威力倍增）、对冲（忌冲禄=破）、化解（科解忌）等效果。
输出格式要求：请输出两个部分，用以下格式：
## ${name} 详细分析
### 三重推演
- 版本判定：X，因由：Y；事象层显象 ← 基调层校准 ← 背景层校准，以[主]行运判语按已定版本选版展开、[辅]为背景校准，逐层推进
### 四化直断
- 上层四化对本宫的直接作用；同星双化：同象「叠X」/变象「X转Y」（上层=过程，本层=结果；输入未列明的四化不得提及）
### 吉凶定性
- 定性+强度+主要因由（与知识库一致，无据不定）
### 本层宜忌
- 事项级宜忌（交易/签约/出行/沟通等）
## ${name} 结论
- 以 1000-1200 字给出本宫核心结论与关键提示，供整体汇总直接引用
要求：以本宫为分析主体；须运用三方四正会照数据分析见星寻偶与星曜互射（他宫星曜照入本宫是本宫分析的一部分）；不要在本宫输出中完整展开其他宫位的独立分析（跨宫互动点到即可）；空宫只能借对宫（输入文件已标注）禁止从其他宫借星；必须基于知识库资料不编造，论述少的组合明确说明；不确定判断用"可能/倾向/需注意"禁绝对化；禁在 output 中标注方法论版本号/修正纪要/内部工程标记（如 v2026-xx、化性修正、批次 等）——报告是给命主看的命理分析，不是工程文档；语言自然像面对客人；请充分分析不要刻意压缩字数；结合命主性别：知识库『男命/女命』论断采用与命主性别相符的解读。
层级禁令（越层泄露防护）：行运判语层级须匹配——[主]=紧邻上层×本层、[辅]=上上层×紧邻上层（合法），禁引用非[主][辅]组合的更远层行运判语（如流日分析禁用大限级'十年主X'判语）。时间框架须与本层匹配（流日用'今日'、流月用'本月'——禁跨层时间表述如'大限十年''流年全年'）。上级结论引用（级联注入）合法。${CONFIG.shengongNote}`;
  let usr = `先用 read 工具读取输入文件：${input}
其内容含【本层命盘信息】【本层盘·${name}宫星曜信息】【该宫三层并标】【该宫四化相邻配对】【流曜叠化】（流日/流时另含【该宫十二神定位】）【本层格局核验】【该宫三方四正会照】【版本判定素材】【行运匹配判语】（排盘程序核毕，直接采信勿再自推宫位关系）（如含）【上级分析结论参考】（上级已判定版本结论，优先引用）（如含）【历史印证参考】（过去日期类似盘面的实际结果，供参考——非本日预测验证）与【知识库·${name}宫参考资料】。
体用上下文：${CONFIG.tiyongLine}。命主性别：${CONFIG.gender}；本层四化：${CONFIG.sihuaLine}。
按上述 system 六要素要求分析${name}，用 write 工具将完整分析写入：${output}
（UTF-8，Markdown；文件内容=「## ${name} 详细分析」与「## ${name} 结论」两部分全文）
然后只回复：第一行 ${name}-DONE；随后 ≤500 字精简摘要；最后列出本宫 1-3 条全盘线索（给整体汇总用）。不要在回复里贴分析全文。`;
  if (CONFIG.patternStats && !CONFIG.patternStats.includes('{{')) {
    usr += `\n\n【历史战绩参考】（来自印证库——历史统计校准，与输入文件【历史印证参考】（叙事级素材）互补；教科书判据始终是基础，不替代语料）\n${CONFIG.patternStats}\n使用方式：每条预测行末尾统一标注 [高置信]/[中置信]/[低置信]——替代模糊的"大概率/可能"；高置信（历史 rate≥80% 或教科书强判据）→重点写+确定性措辞；中置信（历史 50-80% 或教科书+样本不足）→正常写；低置信（历史 rate<50%）→轻写或跳过；样本不足→正常写+教科书置信度标签。`;
  }
  return { sys, usr, output };
}

async function runPalace(idx, name, primary) {
  const secondary = primary === CONFIG.providerA ? CONFIG.providerB : CONFIG.providerA;
  const { sys, usr, output } = palacePrompt(idx, name);
  let prompt = `${sys}\n\n${usr}`;
  if (primary === CONFIG.providerB && CONFIG.providerB !== CONFIG.providerA) {
    prompt += '\n特别提醒：结论/摘要部分务必充分展开至 1000-1200 中文字符，宁长勿短——这是硬性要求。';
  }
  let used = primary;
  let r = await agent(prompt, { provider: primary, label: `${num2(idx)}_${name}@${primary}`, ...(CONFIG.model ? { model: CONFIG.model } : {}) });
  if (r == null) {
    log(`${name}@${primary} 失败，换 ${secondary} 重发`);
    used = secondary;
    r = await agent(prompt, { provider: secondary, label: `${num2(idx)}_${name}@${secondary}-retry`, ...(CONFIG.model ? { model: CONFIG.model } : {}) });
  }
  return { palace: name, ok: r != null, provider: r != null ? used : 'FAIL', output, reply: r == null ? '（失败：两池均未成，主会话串行补跑本宫）' : String(r).slice(0, 800) };
}

// 池内滚动：每池最多 perPoolConcurrency 个 worker，任一任务完成立刻补位取下一任务
async function runPool(provider, tasks) {
  const results = new Array(tasks.length);
  let next = 0;
  async function worker() {
    while (next < tasks.length) {
      const i = next++;
      results[i] = await runPalace(tasks[i].idx, tasks[i].name, provider);
    }
  }
  const n = Math.min(CONFIG.perPoolConcurrency, tasks.length);
  await parallel(Array.from({ length: n }, () => worker));
  return results;
}

phase('dispatch-liupan-12-palaces');
log(`双池滚动：1-6 宫@${CONFIG.providerA}，7-12 宫@${CONFIG.providerB}，每池并发 ${CONFIG.perPoolConcurrency}`);
const half = PALACES.map((name, idx) => ({ idx, name }));
const [ra, rb] = await parallel([
  () => runPool(CONFIG.providerA, half.slice(0, 6)),
  () => runPool(CONFIG.providerB, half.slice(6, 12)),
]);
const results = [...ra, ...rb];
const okN = results.filter(x => x.ok).length;
log(`完成 ${okN}/12`);

// ── 内嵌 check+auto-refill──
log('12 宫完成，启动 checker 子代理');
const checkPrompt = `读取目录 ${CONFIG.outputsDir} 下全部 12 份 output_XX_*.md 文件（用 read 工具逐份读取），对每份检查三条规则：
①含"## <宫名> 详细分析"标题 ②"## <宫名> 摘要"或"## <宫名> 结论"节的正文中文字符数在 800-1400 之间（中文字符计数：去空白后逐字计）③文件大小>1KB。
宫序：命宫/官禄/财帛/福德/迁移/疾厄/田宅/父母/夫妻/子女/兄弟/仆役。
只回复一个 JSON 对象（不要其他文字）：{"pass":["命宫",...],"fail":[{"palace":"父母","reason":"摘要 675 字"}]}`;
let checkResult = null;
try {
  const cr = await agent(checkPrompt, { label: 'checker' });
  checkResult = JSON.parse(String(cr).trim());
} catch(e) { log('checker 解析失败：'+e); }
let refilled = [];
if (checkResult && checkResult.fail && checkResult.fail.length > 0) {
  log(`FAIL 宫 ${checkResult.fail.length} 个：${checkResult.fail.map(f=>f.palace).join('、')}——自动换另一池重发`);
  const refillTasks = checkResult.fail
    .map(f => PALACES.findIndex(p => p === f.palace))
    .filter(i => i >= 0)
    .map(i => ({idx: i, name: PALACES[i]}));
  await parallel(refillTasks.map(t => () => runPalace(t.idx, t.name, CONFIG.providerA)));
  refilled = refillTasks.map(t => t.name);
  log(`补发完成：${refilled.join('、')}`);
} else { log('checker：12/12 全 PASS，无需补发'); }
return { okCount: okN, refilled, results };
