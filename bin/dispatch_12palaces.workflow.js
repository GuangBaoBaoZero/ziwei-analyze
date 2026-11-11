// dispatch_12palaces.workflow.js —— ziwei-analyze Step 2 十二宫派发模板（v2.10：双池滚动池）
// 用法：由 core/make.py --person 模式自动生成 <outdir>\dispatch.workflow.js（占位符已替换）；
//       手工用法兜底：复制本文件内容为 workflow 工具调用的 script 参数，手工替换 {{...}} 占位符后执行；
//       返回值 = 12 宫摘要聚合 + 每宫成败/所用 provider（主会话据此进入第二/三段）。
// 前置实证：workflow agent 具备 read/write 文件工具、支持 {provider, model} 覆盖。
// 落点说明（v2.10 命主分层）：<ZERO_ROOT>\output\<对象>\<主题>\temp\<时间戳>\
// 兜底：宫失败（null）→ 自动换另一池 provider 重发 → 仍败标记 FAIL（主会话串行补跑，等效降并发层）。

const CONFIG = {
  // ===== 占位符（make.py --person 模式自动替换；手工用时自行改值） =====
  inputsDir: '{{INPUTS_DIR}}',      // Step 1 make.py 的 outdir（12 份 input 所在）
  outputsDir: '{{OUTPUTS_DIR}}',    // output_<序号>_<宫名>.md 落点（与 inputs 同目录）
  sihuaLine: '{{SIHUA_LINE}}',      // 该盘四化清单（make.py 从 pan.siHua 生成）
  gender: '{{GENDER}}',             // 男 / 女（make.py 从 pan.gender 生成）
  shengongPalace: '{{SHENGONG_PALACE}}',  // 身宫所在宫名（make.py 从 pan.mingShen.shen 生成）
  // ===== provider 双池（⚠️ 首次使用：把两个池名改成你宿主实际的 provider 名（单入口=两处同值；双入口分别填，并发能力翻倍）；默认两池同值总并发 6；遇限流/宫级失败多→perPoolConcurrency 逐级降 2 再降 1，perPoolConcurrency 降 2） =====
  providerA: 'your-provider',
  providerB: 'your-provider',
  perPoolConcurrency: 3,   // 每池并发上限；总并发 = perPoolConcurrency × 池数
  model: undefined,   // 缺省=会话默认模型；如需覆盖填模型 id
};

const PALACES = ['命宫','官禄','财帛','福德','迁移','疾厄','田宅','父母','夫妻','子女','兄弟','仆役','身宫'];
const num2 = i => String(i + 1).padStart(2, '0');

// 身宫性质判据（语料原文四象限框架）
const SHENGONG_VERDICT = '至于身宫，一般的说法是用来推断其人的后天发展。如果命宫吉，身宫亦吉，当然一生多顺遂；如果命宫吉，身宫不吉，则有如一块美玉，可能在雕琢时出毛病，因此也就容易减色；如果命宫不吉，身宫吉，则虽有如顽石，但碰到一位巧匠，亦可以雕成器；如果命宫不吉，身宫亦不吉，则有如朽木不可雕，人生自然减色，只能利用好的大限与流年，加以人事上的努力来补救。';

function palacePrompt(idx, name) {
  const input = `${CONFIG.inputsDir}\\input_${num2(idx)}_${name}.md`;
  const output = `${CONFIG.outputsDir}\\output_${num2(idx)}_${name}.md`;
  const isShengong = name === '身宫';
  const sgNote = idx === 0
    ? `\n本盘身宫附于${CONFIG.shengongPalace}，参断时参考身宫分析段（第13宫）。`
    : '';
  const sgMethod = isShengong
    ? `\n身宫分析方法（与其他宫同流程）：
- 身宫性质：判断一个人后天如何做事（做事风格/方式/执行力），并在一定程度上反映身体情况；与官禄宫（先天事业格局）构成互补对：官禄=先天格局，身宫=后天做事方式。
- 语料判据（原文四象限框架，须先判命宫与身宫各自吉凶再对照套用）：${SHENGONG_VERDICT}
- 主断：后天如何做事；辅断：身体方面情况（与疾厄宫星系互参——输入已附疾厄宫星系摘要）。`
    : '';
  const sys = `你是一位经验丰富的紫微斗数命理师，现在只专注于分析命盘中的${name}。
你会收到：1. 该宫位所在的星曜组合 2. 与该宫位相关的知识库资料。
请基于这些信息，对${name}做出精炼、专业的分析。
输出格式要求：请输出两个部分，用以下格式：
## ${name} 详细分析
### 宫位特征
- 主星、辅曜、煞曜、四化的综合影响
### 核心判断
- 该宫位的主要倾向和特质
- 优势和挑战
- 各星曜组合的深层含义
- 须给出本宫星系组合的吉凶定性与强度（吉凶并见/偏吉/偏凶等）及主要因由；定性须与知识库论断一致，无据不定
### 与全盘的关联提示
- 该宫位哪些信息需要整体分析时特别注意
- 四化飞化去向（如果有）
## ${name} 摘要（供整体汇总用）
- 以 1000-1200 字给出本宫核心结论与关键提示，供整体汇总直接引用
紫微斗数核心分析方法（逐宫运用）：
① 见星寻偶：分析配对星曜须查其偶是否在位（同宫/会照/对宫）——单见与配对含义截然不同；输入的三方四正会照数据已含偶星位置，须主动查用。
② 星曜互射：本宫星曜与对宫冲照/三合会照星曜产生动态互射——分析叠加（禄权同会威力倍增）、对冲（忌冲禄=破）、化解（科解忌）等效果。
要求：以本宫为分析主体；须运用三方四正会照数据分析见星寻偶与星曜互射（他宫星曜照入本宫是本宫分析的一部分）；不要在本宫输出中完整展开其他宫位的独立分析（跨宫互动点到即可）；空宫只能借对宫（输入文件已标注）禁止从其他宫借星；必须基于知识库资料不编造，论述少的组合明确说明；不确定判断用"可能/倾向/需注意"禁绝对化；语言自然像面对客人；请充分分析不要刻意压缩字数；若输入含【历史印证参考】，须结合历史结果调整本宫判断权重（历史印证是实际发生的校准数据，优先级高于纯理论推演）；结合命主性别分析：知识库中『男命/女命』相关论断，采用与命主性别相符的解读，异性专属论断不套用；男女差异明显的组合（如桃花诸星、夫妻宫角色）须明示性别语境。
层级禁令（越层泄露防护）：原局分析禁引用大限/流年/流月/流日层信息——只分析本命盘的终身格局与本性。禁出现'流限经''流年逢''大限行至''四十岁后'等跨层表述。时间框架用'终身/一生/本性/格局'——禁'某岁后''某年'。${sgMethod}`;
  const usr = `先用 read 工具读取输入文件：${input}
其内容含【命盘信息】【全盘事实表】（排盘程序核毕，直接采信勿再自推宫位关系）（如含）【历史印证参考】（相似盘面实际发生的结果）与【知识库·${name}宫参考资料】。
命主性别：${CONFIG.gender}；本盘四化：${CONFIG.sihuaLine}。${sgNote}
按上述 system 要求分析${name}，用 write 工具将完整分析写入：${output}
（UTF-8，Markdown；文件内容=「## ${name} 详细分析」与「## ${name} 摘要」两部分全文）
然后只回复：第一行 ${name}-DONE；随后 ≤500 字精简摘要；最后列出本宫 1-3 条全盘线索（给整体汇总用）。不要在回复里贴分析全文。`;
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

phase('dispatch-12-palaces');
log(`双池滚动：1-7 宫@${CONFIG.providerA}，8-13 宫@${CONFIG.providerB}，每池并发 ${CONFIG.perPoolConcurrency}`);
const half = PALACES.map((name, idx) => ({ idx, name }));
const [ra, rb] = await parallel([
  () => runPool(CONFIG.providerA, half.slice(0, 7)),
  () => runPool(CONFIG.providerB, half.slice(7)),
]);
const results = [...ra, ...rb];
const okN = results.filter(x => x.ok).length;
log(`完成 ${okN}/13`);

// ── 内嵌 check+auto-refill──
log('13 宫完成，启动 checker 子代理');
const checkPrompt = `读取目录 ${CONFIG.outputsDir} 下全部 13 份 output_XX_*.md 文件（用 read 工具逐份读取），对每份检查三条规则：
①含"## <宫名> 详细分析"标题 ②"## <宫名> 摘要"或"## <宫名> 结论"节的正文中文字符数在 800-1400 之间（中文字符计数：去空白后逐字计）③文件大小>1KB。
宫序：命宫/官禄/财帛/福德/迁移/疾厄/田宅/父母/夫妻/子女/兄弟/仆役/身宫。
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
} else { log('checker：13/13 全 PASS，无需补发'); }
return { okCount: okN, refilled, results };
