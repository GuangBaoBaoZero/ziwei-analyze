#!/usr/bin/env node
/**
 * 紫微斗数排盘命令行工具（本地技能版）
 *
 * 包装同目录 ziwei-engine.js + lunar-data.js（排盘引擎原文件），
 * vm 沙箱加载，全本地离线排盘（1900-2099）。
 *
 * 输出格式为命盘文件标准结构：
 *   { "birth": {...}, "pan": <getZiweiPaipan 返回值>, "saved_at": "..." }
 * 可直接喂给 core/retrieve.py 做知识库检索。
 *
 * 用法：
 *   node paipan.js --year 1995 --month 6 --day 15 --hour 12 --minute 30 --gender male
 *   node paipan.js --birth "1995-06-15 12:30" --gender male
 *   node paipan.js --birth "1995-06-15 12:30" --gender male --out pan_xxx.json
 *   echo '{"year":1995,...}' | node paipan.js     (stdin JSON)
 *
 * 流盘查询（引擎唯一出口：命宫/干支/十二神/四化全部引擎函数直算）：
 *   node paipan.js --liupan --pan pans/名.json --level liuyue|liuri|liushi|liuke --date YYYY-MM-DD [--hour H] [--minute M]
 *   node paipan.js --liupan --pan pans/名.json --level liunian --date YYYY-MM-DD
 *   node paipan.js --liupan --pan pans/名.json --level daxian --seq N
 *
 * 前置：Node.js >= 14；同目录存在 lunar-data.js 与 ziwei-engine.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ENGINE_DIR = __dirname;
const ENGINE_FILE = path.join(ENGINE_DIR, 'ziwei-engine.js');
const LUNAR_FILE = path.join(ENGINE_DIR, 'lunar-data.js');

for (const f of [ENGINE_FILE, LUNAR_FILE]) {
    if (!fs.existsSync(f)) {
        console.error(`错误：找不到 ${path.basename(f)}（应与 paipan.js 同目录）`);
        process.exit(2);
    }
}

// ── 沙箱加载引擎 ──
const sandbox = {
    console: { log: () => {}, error: console.error, warn: console.warn },
    // 现役引擎在 1900-2099 内嵌表范围内不会发起任何网络请求；
    // fetch 兜底 reject，防止超范围时静默失败
    fetch: () => Promise.reject(new Error('离线模式：生日超出 1900-2099 内嵌农历数据范围，无法排盘。')),
    setTimeout, clearTimeout, setInterval, clearInterval,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(LUNAR_FILE, 'utf-8'), sandbox, { filename: 'lunar-data.js' });
vm.runInContext(fs.readFileSync(ENGINE_FILE, 'utf-8'), sandbox, { filename: 'ziwei-engine.js' });

const getZiweiPaipan = sandbox.getZiweiPaipan;
if (typeof getZiweiPaipan !== 'function') {
    console.error('错误：引擎加载后未找到 getZiweiPaipan 入口');
    process.exit(2);
}

// ── 参数解析 ──
function parseArgs(argv) {
    const a = { gender: 'male', panType: 'tian', out: null };
    for (let i = 0; i < argv.length; i++) {
        const k = argv[i];
        const v = argv[i + 1];
        switch (k) {
            case '--year': a.year = parseInt(v, 10); i++; break;
            case '--month': a.month = parseInt(v, 10); i++; break;
            case '--day': a.day = parseInt(v, 10); i++; break;
            case '--hour': a.hour = parseInt(v, 10); i++; break;
            case '--minute': a.minute = parseInt(v, 10); i++; break;
            case '--gender': a.gender = v; i++; break;
            case '--pantype': a.panType = v; i++; break;
            case '--birth': {
                // "1995-06-15 12:30" 或 "1995-6-15 12:30"
                const m = String(v).trim().match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{1,2}))?$/);
                if (!m) { console.error(`错误：--birth 格式应为 "YYYY-MM-DD HH:mm"，收到 "${v}"`); process.exit(2); }
                a.year = +m[1]; a.month = +m[2]; a.day = +m[3];
                a.hour = m[4] ? +m[4] : 12;   // 缺省正午
                a.minute = m[5] ? +m[5] : 0;
                i++; break;
            }
            case '--out': a.out = v; i++; break;
            case '--help': case '-h':
                console.log('用法: node paipan.js --birth "1995-06-15 12:30" --gender male [--out pan.json]\n' +
                    '     node paipan.js --year 1995 --month 6 --day 15 --hour 12 --minute 30 --gender male');
                process.exit(0);
            default:
                console.error(`未知参数: ${k}（--help 查看）`); process.exit(2);
        }
    }
    return a;
}

// ── 流盘查询（引擎唯一出口；派生口径与 ziwei-pure.html renderLiuYue/renderLiuRi/renderLiuShi/renderLiuKe 一致）──
async function liupanQuery(argv) {
    const a = {};
    for (let i = 0; i < argv.length; i++) {
        const k = argv[i], v = argv[i + 1];
        if (['--pan', '--level', '--date', '--hour', '--minute', '--seq'].includes(k)) { a[k.slice(2)] = v; i++; }
        else if (k === '--liupan') { /* 模式开关 */ }
        else { console.error(`--liupan 未知参数: ${k}`); process.exit(2); }
    }
    for (const k of ['pan', 'level', 'date']) {
        if (!a[k]) { console.error(`--liupan 缺少 --${k}`); process.exit(2); }
    }
    const levels = ['daxian', 'liunian', 'liuyue', 'liuri', 'liushi', 'liuke'];
    if (!levels.includes(a.level)) { console.error(`--liupan level 须为 ${levels.join('|')}`); process.exit(2); }

    const panFile = JSON.parse(fs.readFileSync(a.pan, 'utf-8'));
    const pan = panFile.pan;
    const birth = panFile.birth;
    const gender = pan.gender || birth.gender;
    const nianGan = pan.siZhu.year.charAt(0);

    // 目标日公历 → 农历派生（全部引擎侧）
    const m = a.date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) { console.error(`--liupan --date 应为 YYYY-MM-DD，收到 ${a.date}`); process.exit(2); }
    const y = +m[1], mo = +m[2], d = +m[3];
    const dataMap = await sandbox.fetchZiweiYearData(y);
    if (!dataMap) { console.error('--liupan: 无该年农历数据'); process.exit(3); }
    const dayData = dataMap[mo + '-' + d];
    if (!dayData) { console.error(`--liupan: 无 ${a.date} 农历数据`); process.exit(3); }

    const lunarYear = await sandbox.getLunarYearOfDate(y, mo, d);
    const liuNianGZ = sandbox.getYearGanZhi(lunarYear);
    const liuNianGan = liuNianGZ.charAt(0);
    const liuNianZhi = liuNianGZ.charAt(1);
    const effectiveLunarMonth = sandbox.getEffectiveLunarMonth(dayData, 0);
    const lunarDay = parseInt(dayData.lunarDay, 10);
    const liuYueGZ = sandbox.getMonthGanZhi(liuNianGan, effectiveLunarMonth);
    const liuRiGZ = dayData.dayGZ;

    // 流月命宫（斗君法）→ 流日 → 流时 → 流刻
    const birthHourZhi = pan.siZhu.hour.charAt(1); // 出生时支（四柱时柱已有，与 hourZhiIndex 同源）
    const liuYueMingZhi = sandbox.getLiuYueMingZhi(liuNianZhi, pan.effectiveLunarMonth, birthHourZhi, effectiveLunarMonth);
    const liuRiMingZhi = liuYueMingZhi ? sandbox.getLiuRiMingZhi(liuYueMingZhi, lunarDay) : null;
    let hour = a.hour !== undefined ? parseInt(a.hour, 10) : null;
    let minute = a.minute !== undefined ? parseInt(a.minute, 10) : null;
    const liuShiMingZhi = (liuRiMingZhi !== null && hour !== null) ? sandbox.getLiuShiMingZhi(liuRiMingZhi, hour) : null;
    const liuKeMingZhi = (liuShiMingZhi !== null && hour !== null && minute !== null) ? sandbox.getLiuKeMingZhi(liuShiMingZhi, hour, minute) : null;

    // 流时/流刻干支
    let liuShiGZ = null, liuKeGZ = null;
    if (hour !== null && liuRiGZ) {
        const scIdx = Math.floor((hour + 1) / 2) % 12;
        liuShiGZ = sandbox.getHourGan(liuRiGZ.charAt(0), scIdx) + sandbox.stepZhi('子', scIdx);
        if (minute !== null) liuKeGZ = sandbox.getKeGanZhi(liuShiGZ.charAt(0), hour, minute);
    }

    // 层四化（引擎 getSiHua，星宫落原盘 allStarMap）
    const sihua = {};
    const layerGans = {
        daxian: null, // 大限干由限宫定（下方填）
        liunian: liuNianGan,
        liuyue: liuYueGZ ? liuYueGZ.charAt(0) : null,
        liuri: liuRiGZ ? liuRiGZ.charAt(0) : null,
        liushi: liuShiGZ ? liuShiGZ.charAt(0) : null,
        liuke: liuKeGZ ? liuKeGZ.charAt(0) : null,
    };
    for (const [lv, gan] of Object.entries(layerGans)) {
        if (gan) sihua[lv] = sandbox.getSiHua(gan, pan.allStarMap);
    }

    // 大限层：yunNum 由引擎按流年日期反推；限宫/起讫/起始时间引擎算
    const daXianMap = sandbox.getDaXian(pan.mingShen.ming, pan.wuXingJu, nianGan, gender);
    const sortedXian = Object.entries(daXianMap)
        .map(([zhi, rng]) => ({ zhi, start: parseInt(rng.split('-')[0], 10), range: rng }))
        .sort((p, q) => p.start - q.start);
    let daxian = null;
    if (a.level === 'daxian') {
        const seq = parseInt(a.seq, 10);
        if (!(seq >= 1 && seq <= sortedXian.length)) { console.error(`--liupan --seq 须为 1-${sortedXian.length}`); process.exit(2); }
        const x = sortedXian[seq - 1];
        daxian = { seq, zhi: x.zhi, gan: pan.gongGan[x.zhi], range: x.range,
                   startTime: await sandbox.getDaXianStartTime('yun_' + seq, birth, pan.wuXingJu) };
        sihua.daxian = sandbox.getSiHua(daxian.gan, pan.allStarMap);
    } else {
        const yunNum = await sandbox.getYunNumByLiuNianDate(birth, { year: y, month: mo, day: d }, pan.wuXingJu);
        if (yunNum && yunNum.startsWith('yun_')) {
            const x = sortedXian[parseInt(yunNum.slice(4), 10) - 1];
            daxian = { seq: parseInt(yunNum.slice(4), 10), zhi: x.zhi, gan: pan.gongGan[x.zhi], range: x.range, yunNum,
                       startTime: await sandbox.getDaXianStartTime(yunNum, birth, pan.wuXingJu) };
        } else if (yunNum) {
            daxian = { yunNum, note: '未入限（起限前虚岁）' };
        }
        if (daxian && daxian.gan) sihua.daxian = sandbox.getSiHua(daxian.gan, pan.allStarMap);
    }

    // 流层十二神（引擎流年支/流年干版）+ 流昌流曲
    const flowGods = {
        taiSuiTwelve: sandbox.getTaiSuiTwelve(liuNianZhi),
        jiangQian: sandbox.getJiangQian(liuNianZhi),
        boShi: sandbox.getLiuNianBoShi(liuNianGan, nianGan, gender),
    };
    const liuChangQu = {};
    for (const [lv, gan] of Object.entries(layerGans)) {
        if (gan) liuChangQu[lv] = sandbox.getLiuChangQu(gan);
    }

    // 流曜八曜：各层按层干支引擎排——禄存/擎羊/陀罗/天魁/天钺/文昌/文曲随层干，天马随层支三合
    const liuYaoLayers = {
        liunian: liuNianGZ ? { gan: liuNianGZ.charAt(0), zhi: liuNianGZ.charAt(1) } : null,
        liuyue: liuYueGZ ? { gan: liuYueGZ.charAt(0), zhi: liuYueGZ.charAt(1) } : null,
        liuri: liuRiGZ ? { gan: liuRiGZ.charAt(0), zhi: liuRiGZ.charAt(1) } : null,
        liushi: liuShiGZ ? { gan: liuShiGZ.charAt(0), zhi: liuShiGZ.charAt(1) } : null,
        daxian: (daxian && daxian.gan) ? { gan: daxian.gan, zhi: daxian.zhi } : null,
    };
    const liuYao = {};
    for (const [lv, gz] of Object.entries(liuYaoLayers)) {
        if (!gz) continue;
        const cq = sandbox.getLiuChangQu(gz.gan) || {};
        liuYao[lv] = {
            '禄存': sandbox.getLuCun(gz.gan),
            '擎羊': sandbox.getQingYang(gz.gan),
            '陀罗': sandbox.getTuoLuo(gz.gan),
            '天魁': sandbox.getTianKui(gz.gan),
            '天钺': sandbox.getTianYue(gz.gan),
            '文昌': cq.chang || null,
            '文曲': cq.qu || null,
            '天马': sandbox.getTianMa(gz.zhi),
        };
    }

    const out = {
        level: a.level,
        date: a.date, hour, minute,
        lunar: { lunarYear, liuNianGZ, effectiveLunarMonth, lunarDay, isLeap: !!dayData.isLeap },
        ganZhi: { liuYue: liuYueGZ, liuRi: liuRiGZ, liuShi: liuShiGZ, liuKe: liuKeGZ },
        mingZhi: { liuyue: liuYueMingZhi, liuri: liuRiMingZhi, liushi: liuShiMingZhi, liuke: liuKeMingZhi, liunian: liuNianZhi },
        daxian, sihua, flowGods, liuChangQu, liuYao,
    };
    console.log(JSON.stringify(out, null, 2));
}

async function main() {
    if (process.argv.includes('--liupan')) {
        return liupanQuery(process.argv.slice(2));
    }
    let args;
    if (process.argv.length > 2) {
        args = parseArgs(process.argv.slice(2));
    } else {
        // stdin JSON
        const raw = fs.readFileSync(0, 'utf-8');
        try { args = JSON.parse(raw); } catch (e) { console.error('stdin 不是合法 JSON'); process.exit(2); }
    }

    const { year, month, day, hour, minute, gender, panType, out } = args;
    for (const [k, v] of Object.entries({ year, month, day, hour, minute })) {
        if (!Number.isInteger(v)) { console.error(`错误：缺少或非法参数 ${k}`); process.exit(2); }
    }

    const result = await getZiweiPaipan(year, month, day, hour, minute, gender, panType || 'tian');
    if (!result || !result.twelvePalaces) {
        console.error('排盘失败：引擎返回空结果（请检查生辰是否在 1900-2099 范围内）');
        process.exit(3);
    }

    // 命盘文件标准结构输出
    const output = {
        birth: { year, month, day, hour, minute, gender, panType: panType || 'tian' },
        pan: result,
        saved_at: new Date().toLocaleString('zh-CN', { hour12: false }),
    };

    const json = JSON.stringify(output, null, 2);
    if (out) {
        fs.writeFileSync(out, json, 'utf-8');
        console.error(`已写入 ${out}`);
        // 摘要到 stderr，stdout 保持干净
        const p = result;
        console.error(`排盘OK: 命宫=${p.twelvePalaces?.[p.mingShen?.ming] || p.mingShen?.ming} 五行局=${p.wuXingJu} 农历=${p.lunarText || ''}`);
    } else {
        console.log(json);
    }
}

main().catch(e => { console.error('排盘异常:', e.message || e); process.exit(3); });
