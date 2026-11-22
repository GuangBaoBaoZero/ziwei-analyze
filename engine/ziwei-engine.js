// 紫微斗数排盘 · 纯净版
// Copyright (c) 2026 GuangBaoBaoZero
// MIT License（详见 LICENSE 文件）

// ========== 紫微斗数核心引擎 V1.0 ==========
// 负责：历法数据获取、农历转换、紫微排盘计算
const ZIWEI_ENGINE_VERSION = 'V1.0';

const ziweiYearCache = {};

const tianGan = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸'];
const diZhi = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
const shichenNames = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];

function numToChineseYear(num) {
    const digits = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
    return num.toString().split('').map(c => digits[parseInt(c)]).join('') + '年';
}

function numToChinese(num) {
    const digits = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
    const n = parseInt(num, 10);
    if (n <= 10) return digits[n];
    if (n < 20) return '十' + digits[n - 10];
    if (n < 30) return '二十' + digits[n - 20];
    return '三十';
}

function getYearGanZhi(year) {
    let ganIdx = (year - 4) % 10; if (ganIdx < 0) ganIdx += 10;
    let zhiIdx = (year - 4) % 12; if (zhiIdx < 0) zhiIdx += 12;
    return tianGan[ganIdx] + diZhi[zhiIdx];
}

function getHourGan(dayGan, hourZhiIndex) {
    const startMap = { '甲': 0, '己': 0, '乙': 2, '庚': 2, '丙': 4, '辛': 4, '丁': 6, '壬': 6, '戊': 8, '癸': 8 };
    const start = startMap[dayGan];
    if (start === undefined) return '-';
    return tianGan[(start + hourZhiIndex) % 10];
}

async function fetchZiweiYearData(year) {
    if (ziweiYearCache[year]) return ziweiYearCache[year];
    // 内嵌离线历法表（1900-2099），零网络请求
    if (typeof getLunarYearMap === 'function') {
        const embedded = getLunarYearMap(year);
        if (embedded) {
            ziweiYearCache[year] = embedded;
            return embedded;
        }
    }
    return null;
}

function getEffectiveDate(year, month, day, hour) {
    // 00:00 才算新的一天，23:00-23:59 仍按当日推算
    return { year, month, day };
}

// 根据闰月规则确定实际用于排盘的农历月份
// 闰月前半月（初一至十五）按前月推算，后半月（十六及以后）按后月推算，00:00 才切换
function getEffectiveLunarMonth(dayData, hour) {
    if (!dayData) return null;
    const lunarMonth = parseInt(dayData.lunarMonth, 10);
    const lunarDay = parseInt(dayData.lunarDay, 10);
    if (!dayData.isLeap) return lunarMonth;
    if (lunarDay <= 15) return lunarMonth;
    return lunarMonth + 1;
}

// 根据公历日期和农历月份推断实际农历年
function getLunarYear(solarYear, solarMonth, lunarMonth) {
    // 年初公历1-2月，但农历已是冬月/腊月，说明还属于上一年农历
    if (solarMonth <= 2 && lunarMonth >= 11) return solarYear - 1;
    // 年末公历11-12月，但农历已是正月/二月，说明已进入下一年农历
    if (solarMonth >= 11 && lunarMonth <= 2) return solarYear + 1;
    return solarYear;
}

// 地支按 circle 步进，n 可为负（兼容任意大步数）
function stepZhi(zhi, n) {
    const idx = diZhi.indexOf(zhi);
    if (idx === -1) return null;
    const len = diZhi.length;
    return diZhi[((idx + n) % len + len) % len];
}

// 根据流年命宫地支、命主出生农历月、出生时辰，计算目标流月命宫地支
function getLiuYueMingZhi(liuNianZhi, birthLunarMonth, birthHourZhi, targetEffectiveLunarMonth) {
    if (!liuNianZhi || !birthLunarMonth || !birthHourZhi || !targetEffectiveLunarMonth) return null;
    // 1. 从流年命宫地支起一月，逆行到命主出生月
    const birthMonthPalaceZhi = stepZhi(liuNianZhi, -(birthLunarMonth - 1));
    // 2. 从出生月宫起子时，顺行到命主出生时辰，得到流月正月命宫
    const hourIdx = diZhi.indexOf(birthHourZhi);
    const zhengYueMingZhi = stepZhi(birthMonthPalaceZhi, hourIdx);
    // 3. 从正月命宫顺行到目标月
    return stepZhi(zhengYueMingZhi, targetEffectiveLunarMonth - 1);
}

// 以流月命宫为初一，顺行到目标农历日，得到流日命宫地支
function getLiuRiMingZhi(liuYueMingZhi, targetLunarDay) {
    if (!liuYueMingZhi || !targetLunarDay) return null;
    return stepZhi(liuYueMingZhi, targetLunarDay - 1);
}

// 以流日命宫起子时，顺行到目标时辰，得到流时命宫地支（00:00-00:59 为早子时，23:00-23:59 为晚子时，均按子时起算）
function getLiuShiMingZhi(liuRiMingZhi, hour) {
    if (!liuRiMingZhi || hour === null || hour === undefined) return null;
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    return stepZhi(liuRiMingZhi, scIdx);
}

// 以流时命宫起子时，顺行到当前刻，得到流刻命宫地支
function getLiuKeMingZhi(liuShiMingZhi, hour, minute) {
    if (!liuShiMingZhi || hour === null || hour === undefined || minute === null || minute === undefined) return null;
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const shichenStartHour = (scIdx * 2 - 1 + 24) % 24;
    const offsetHours = (hour - shichenStartHour + 24) % 24;
    const offsetInShichen = offsetHours * 60 + minute;
    const keIndex = Math.floor(offsetInShichen / 10) % 12;
    return stepZhi(liuShiMingZhi, keIndex);
}

async function getLunarText(year, month, day, hour) {
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    if (!dayData) return '-';
    const lunarMonthNum = parseInt(dayData.lunarMonth, 10);
    const lunarDayNum = parseInt(dayData.lunarDay, 10);
    const lunarYear = getLunarYear(eff.year, eff.month, lunarMonthNum);
    const leapStr = dayData.isLeap ? '闰' : '';
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const shiChen = shichenNames[scIdx];
    let shiLabel = shiChen + '时';
    if (shiChen === '子') {
        shiLabel = hour >= 23 ? '晚子时' : '早子时';
    }
    return `农历 ${numToChineseYear(lunarYear)} ${leapStr}${numToChinese(lunarMonthNum)}月${numToChinese(lunarDayNum)}日 ${shiLabel}`;
}

// 五鼠遁时起刻法：一个时辰分12刻，每刻10分钟
function getKeGanZhi(hourGan, hour, minute) {
    const startMap = { '甲': 0, '己': 0, '乙': 2, '庚': 2, '丙': 4, '辛': 4, '丁': 6, '壬': 6, '戊': 8, '癸': 8 };
    const start = startMap[hourGan];
    if (start === undefined) return '-';
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const shichenStartHour = (scIdx * 2 - 1 + 24) % 24;
    const offsetHours = (hour - shichenStartHour + 24) % 24;
    const offsetInShichen = offsetHours * 60 + minute;
    const keIndex = Math.floor(offsetInShichen / 10) % 12;
    const gan = tianGan[(start + keIndex) % 10];
    const zhi = diZhi[keIndex];
    return gan + zhi;
}

async function getLunarTextWithKe(year, month, day, hour, minute) {
    // 流刻：遵循早子时/晚子时规则，00:00 才算下一天
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    if (!dayData) return '-';
    const lunarMonthNum = parseInt(dayData.lunarMonth, 10);
    const lunarDayNum = parseInt(dayData.lunarDay, 10);
    const lunarYear = getLunarYear(eff.year, eff.month, lunarMonthNum);
    const leapStr = dayData.isLeap ? '闰' : '';
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const shiChen = shichenNames[scIdx];
    let shiLabel = shiChen + '时';
    if (shiChen === '子') {
        shiLabel = hour >= 23 ? '晚子时' : '早子时';
    }
    const dayGan = (dayData.dayGZ || '-').charAt(0);
    const hourGan = getHourGan(dayGan, scIdx);
    const keGZ = getKeGanZhi(hourGan, hour, minute);
    return `流盘农历 ${numToChineseYear(lunarYear)} ${leapStr}${numToChinese(lunarMonthNum)}月${numToChinese(lunarDayNum)}日 ${shiLabel} ${keGZ.charAt(1)}刻`;
}

async function getWuZhuWithKe(year, month, day, hour, minute) {
    // 流刻：遵循早子时/晚子时规则，00:00 才算下一天
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;
    if (!dayData) return null;

    const lunarMonthNum = parseInt(dayData.lunarMonth, 10);
    const effectiveLunarMonth = getEffectiveLunarMonth(dayData, hour);
    const lunarYear = getLunarYear(eff.year, eff.month, lunarMonthNum);
    const nianGan = getYearGanZhi(lunarYear).charAt(0);
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const dayGan = (dayData.dayGZ || '-').charAt(0);
    const hourGan = getHourGan(dayGan, scIdx);
    const keGZ = getKeGanZhi(hourGan, hour, minute);

    return {
        year: getYearGanZhi(lunarYear),
        month: getMonthGanZhi(nianGan, effectiveLunarMonth),
        day: dayData.dayGZ || '-',
        hour: hourGan + shichenNames[scIdx],
        ke: keGZ
    };
}

async function getSiZhu(year, month, day, hour) {
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    if (!dayData) {
        return { year: '-', month: '-', day: '-', hour: '-' };
    }

    const lunarMonthNum = parseInt(dayData.lunarMonth, 10);
    const effectiveLunarMonth = getEffectiveLunarMonth(dayData, hour);
    const lunarYear = getLunarYear(eff.year, eff.month, lunarMonthNum);
    const nianGan = getYearGanZhi(lunarYear).charAt(0);
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    const dayGan = dayData.dayGZ.charAt(0);
    const hourGan = getHourGan(dayGan, scIdx);
    const hourGZ = hourGan + shichenNames[scIdx];

    return {
        year: getYearGanZhi(lunarYear),
        month: getMonthGanZhi(nianGan, effectiveLunarMonth),
        day: dayData.dayGZ || '-',
        hour: hourGZ
    };
}

// 安命宫、身宫
// 寅宫起正月，顺数至本生月；再从该宫起子时，逆数至本生时为命宫，顺数至本生时为身宫
function getMingShenGong(lunarMonth, hour) {
    const scIdx = Math.floor((hour + 1) / 2) % 12;
    // 正月寅(index 2)，顺数 lunarMonth-1 步
    const monthStartIdx = (2 + (lunarMonth - 1)) % 12;
    const mingIdx = (monthStartIdx - scIdx + 12) % 12;
    const shenIdx = (monthStartIdx + scIdx) % 12;
    return {
        ming: diZhi[mingIdx],
        shen: diZhi[shenIdx]
    };
}

// 十二宫名称，由命宫逆数排列
const ziweiPalaces = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '仆役', '官禄', '田宅', '福德', '父母'];

// 根据命宫地支，排出十二宫名称（每个地支宫对应一个宫位）
function getTwelvePalaces(mingZhi) {
    const mingIdx = diZhi.indexOf(mingZhi);
    const map = {};
    diZhi.forEach((zhi, idx) => {
        const offset = (mingIdx - idx + 12) % 12;
        map[zhi] = ziweiPalaces[offset];
    });
    return map;
}

// 十四主星庙旺利陷表（横向：子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥）
const mainStarBrightness = {
    '紫微': ['平','庙','庙','旺','陷','旺','庙','庙','旺','平','闲','旺'],
    '天机': ['庙','陷','旺','旺','庙','平','庙','陷','平','旺','庙','平'],
    '太阳': ['陷','陷','旺','庙','旺','旺','庙','平','闲','闲','陷','陷'],
    '武曲': ['旺','庙','闲','陷','庙','平','旺','庙','平','旺','庙','平'],
    '天同': ['旺','陷','闲','庙','平','庙','陷','陷','旺','平','平','庙'],
    '廉贞': ['平','旺','庙','闲','旺','陷','平','庙','庙','平','旺','陷'],
    '天府': ['庙','庙','庙','平','庙','平','旺','庙','平','陷','庙','旺'],
    '太阴': ['庙','庙','闲','陷','闲','陷','陷','平','平','旺','旺','庙'],
    '贪狼': ['旺','庙','平','地','庙','陷','旺','庙','平','平','庙','陷'],
    '巨门': ['旺','旺','庙','庙','平','平','旺','陷','庙','庙','旺','旺'],
    '天相': ['庙','庙','庙','陷','旺','平','旺','闲','庙','陷','闲','平'],
    '天梁': ['庙','旺','庙','庙','旺','陷','庙','旺','陷','地','旺','陷'],
    '七杀': ['旺','庙','庙','陷','旺','平','旺','旺','庙','闲','庙','平'],
    '破军': ['庙','旺','陷','旺','旺','闲','庙','庙','陷','陷','旺','平']
};

// 查主星庙旺利陷
function getStarBrightness(star, zhi) {
    const row = mainStarBrightness[star];
    if (!row) return null;
    const idx = diZhi.indexOf(zhi);
    if (idx === -1) return null;
    return row[idx];
}

// 六吉星 / 辅曜 / 六煞星庙旺利陷表（横向：子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥）
const auxStarBrightnessMap = {
    '天马': ['/', '/', '旺', '/', '/', '平', '/', '/', '旺', '/', '/', '平'],
    '禄存': ['旺', '/', '庙', '旺', '/', '庙', '旺', '/', '庙', '旺', '/', '庙'],
    '文曲': ['庙', '庙', '平', '旺', '庙', '庙', '陷', '旺', '平', '庙', '陷', '旺'],
    '文昌': ['旺', '庙', '陷', '平', '旺', '庙', '陷', '平', '旺', '庙', '陷', '旺'],
    '右弼': ['庙', '庙', '旺', '陷', '庙', '平', '旺', '庙', '闲', '陷', '庙', '平'],
    '左辅': ['旺', '庙', '庙', '陷', '庙', '平', '旺', '庙', '平', '陷', '庙', '闲'],
    '天钺': ['/', '/', '旺', '/', '/', '旺', '/', '旺', '庙', '庙', '/', '/'],
    '天魁': ['旺', '旺', '/', '庙', '/', '/', '庙', '/', '/', '/', '/', '旺'],
    '地劫': ['陷', '陷', '平', '平', '陷', '闲', '庙', '平', '庙', '平', '平', '旺'],
    '地空': ['平', '陷', '陷', '平', '陷', '庙', '庙', '平', '庙', '陷', '陷', '陷'],
    '铃星': ['陷', '陷', '庙', '庙', '旺', '旺', '庙', '旺', '旺', '陷', '庙', '庙'],
    '火星': ['平', '旺', '庙', '平', '闲', '旺', '庙', '闲', '陷', '陷', '庙', '平'],
    '陀罗': ['/', '庙', '陷', '/', '庙', '陷', '/', '庙', '陷', '/', '庙', '陷'],
    '擎羊': ['陷', '庙', '/', '陷', '庙', '/', '平', '庙', '/', '陷', '庙', '/']
};

// 查辅星庙旺利陷
function getAuxStarBrightness(star, zhi) {
    const row = auxStarBrightnessMap[star];
    if (!row) return null;
    const idx = diZhi.indexOf(zhi);
    if (idx === -1) return null;
    return row[idx];
}

// 五虎遁：寅宫起正月，按年干定寅宫天干，顺排十二宫
function getGongGan(nianGan) {
    const startMap = { '甲': 2, '己': 2, '乙': 4, '庚': 4, '丙': 6, '辛': 6, '丁': 8, '壬': 8, '戊': 0, '癸': 0 };
    const start = startMap[nianGan];
    if (start === undefined) return {};
    const map = {};
    // 寅宫为地支 index 2，顺排十二宫
    for (let i = 0; i < 12; i++) {
        const zhiIdx = (2 + i) % 12;
        const gan = tianGan[(start + i) % 10];
        map[diZhi[zhiIdx]] = gan;
    }
    return map;
}

// 紫微掌诀：五行局掌上宫位分布（用于起紫微星）
// 酉宫（火1），午宫（火2，土1），亥宫（火3，土2，金1），
// 辰宫（火4，土3，金2，木1），丑宫（火5，土4，金3，木2，水1），
// 寅宫（水0，木0，金0，土0，火0）
const ziweiZhangJue = {
    '酉': [{ wuXing: '火', step: 1 }],
    '午': [{ wuXing: '火', step: 2 }, { wuXing: '土', step: 1 }],
    '亥': [{ wuXing: '火', step: 3 }, { wuXing: '土', step: 2 }, { wuXing: '金', step: 1 }],
    '辰': [{ wuXing: '火', step: 4 }, { wuXing: '土', step: 3 }, { wuXing: '金', step: 2 }, { wuXing: '木', step: 1 }],
    '丑': [{ wuXing: '火', step: 5 }, { wuXing: '土', step: 4 }, { wuXing: '金', step: 3 }, { wuXing: '木', step: 2 }, { wuXing: '水', step: 1 }],
    '寅': [{ wuXing: '水', step: 0 }, { wuXing: '木', step: 0 }, { wuXing: '金', step: 0 }, { wuXing: '土', step: 0 }, { wuXing: '火', step: 0 }]
};

// 根据五行和 step 查找紫微掌诀宫位
function getZhangJueGong(wuXing, step) {
    for (const [gong, items] of Object.entries(ziweiZhangJue)) {
        for (const item of items) {
            if (item.wuXing === wuXing && item.step === step) {
                return gong;
            }
        }
    }
    return null;
}

// 安左辅星
// 正月起辰，顺行一月一宫
function getZuoFu(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const startIdx = diZhi.indexOf('辰');
    return diZhi[(startIdx + lunarMonth - 1) % 12];
}

// 安右弼星
// 正月起戌，逆行一月一宫
function getYouBi(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const startIdx = diZhi.indexOf('戌');
    return diZhi[(startIdx - lunarMonth + 1 + 12) % 12];
}

// 安文曲星
// 子时起辰，顺行一时辰一宫
function getWenQu(hourZhiIndex) {
    if (hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf('辰');
    return diZhi[(startIdx + hourZhiIndex) % 12];
}

// 安文昌星
// 子时起戌，逆行一时辰一宫
function getWenChang(hourZhiIndex) {
    if (hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf('戌');
    return diZhi[(startIdx - hourZhiIndex + 12) % 12];
}

// 安地劫星
// 子时起亥，顺行一时辰一宫
function getDiJie(hourZhiIndex) {
    if (hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf('亥');
    return diZhi[(startIdx + hourZhiIndex) % 12];
}

// 安地空星
// 子时起亥，逆行一时辰一宫
function getDiKong(hourZhiIndex) {
    if (hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf('亥');
    return diZhi[(startIdx - hourZhiIndex + 12) % 12];
}

// 安火星、铃星
// 按出生年地支分组，从指定宫位起子时，顺/逆行到出生时辰
const huoXingMap = {
    '寅': { start: '丑', dir: 1 }, '午': { start: '丑', dir: 1 }, '戌': { start: '丑', dir: 1 },
    '申': { start: '寅', dir: 1 }, '子': { start: '寅', dir: 1 }, '辰': { start: '寅', dir: 1 },
    '巳': { start: '卯', dir: 1 }, '酉': { start: '卯', dir: 1 }, '丑': { start: '卯', dir: 1 },
    '亥': { start: '酉', dir: 1 }, '卯': { start: '酉', dir: 1 }, '未': { start: '酉', dir: 1 }
};

const lingXingMap = {
    '寅': { start: '卯', dir: 1 }, '午': { start: '卯', dir: 1 }, '戌': { start: '卯', dir: 1 },
    '申': { start: '戌', dir: 1 }, '子': { start: '戌', dir: 1 }, '辰': { start: '戌', dir: 1 },
    '巳': { start: '戌', dir: 1 }, '酉': { start: '戌', dir: 1 }, '丑': { start: '戌', dir: 1 },
    '亥': { start: '戌', dir: 1 }, '卯': { start: '戌', dir: 1 }, '未': { start: '戌', dir: 1 }
};

function getHuoXing(nianZhi, hourZhiIndex) {
    const cfg = huoXingMap[nianZhi];
    if (!cfg || hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf(cfg.start);
    return diZhi[(startIdx + cfg.dir * hourZhiIndex + 12) % 12];
}

function getLingXing(nianZhi, hourZhiIndex) {
    const cfg = lingXingMap[nianZhi];
    if (!cfg || hourZhiIndex === undefined || hourZhiIndex < 0 || hourZhiIndex > 11) return null;
    const startIdx = diZhi.indexOf(cfg.start);
    return diZhi[(startIdx + cfg.dir * hourZhiIndex + 12) % 12];
}

// 安天官、天福星
// 按出生年天干定位（甲羊鸡、乙龙猴、丙蛇鼠、丁虎猪、戊卯卯、己鸡寅、庚猪马、辛鸡蛇、壬犬马、癸马蛇）
const tianGuanMap = {
    '甲': '未', '乙': '辰', '丙': '巳', '丁': '寅',
    '戊': '卯', '己': '酉', '庚': '亥', '辛': '酉',
    '壬': '戌', '癸': '午'
};

const tianFuMap = {
    '甲': '酉', '乙': '申', '丙': '子', '丁': '亥',
    '戊': '卯', '己': '寅', '庚': '午', '辛': '巳',
    '壬': '午', '癸': '巳'
};

function getTianGuan(nianGan) {
    return tianGuanMap[nianGan] || null;
}

function getTianFu(nianGan) {
    return tianFuMap[nianGan] || null;
}

// 安天厨星
// 按出生年天干定位
const tianChuMap = {
    '甲': '巳', '丁': '巳',
    '乙': '午', '戊': '午', '辛': '午',
    '丙': '子',
    '己': '申',
    '庚': '寅',
    '壬': '酉',
    '癸': '亥'
};

function getTianChu(nianGan) {
    return tianChuMap[nianGan] || null;
}

// 安截空星
// 按出生年天干定位截空两宫，再根据年干阴阳取正空
const jieKongMap = {
    '甲': ['申', '酉'], '己': ['申', '酉'],
    '乙': ['午', '未'], '庚': ['午', '未'],
    '丙': ['辰', '巳'], '辛': ['辰', '巳'],
    '丁': ['寅', '卯'], '壬': ['寅', '卯'],
    '戊': ['子', '丑'], '癸': ['子', '丑']
};

const yangZhi = ['子', '寅', '辰', '午', '申', '戌'];
const yinZhi = ['丑', '卯', '巳', '未', '酉', '亥'];
const yangGan = ['甲', '丙', '戊', '庚', '壬'];

function getJieKong(nianGan) {
    const pair = jieKongMap[nianGan];
    if (!pair) return null;
    const isYangGan = yangGan.includes(nianGan);
    for (const zhi of pair) {
        const isYangZhi = yangZhi.includes(zhi);
        if (isYangGan && isYangZhi) return zhi;
        if (!isYangGan && !isYangZhi) return zhi;
    }
    return null;
}

// 安旬空星
// 从年支起年干，顺时针顺数至癸，再后二位，按年干阴阳取正空
function getXunKong(nianGan, nianZhi) {
    const ganIdx = tianGan.indexOf(nianGan);
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (ganIdx === -1 || zhiIdx === -1) return null;
    const guiIdx = tianGan.indexOf('癸');
    const stepsToGui = (guiIdx - ganIdx + 10) % 10;
    const guiZhiIdx = (zhiIdx + stepsToGui) % 12;
    const kong1 = diZhi[(guiZhiIdx + 1) % 12];
    const kong2 = diZhi[(guiZhiIdx + 2) % 12];
    const isYangGan = yangGan.includes(nianGan);
    const isKong1Yang = yangZhi.includes(kong1);
    if (isYangGan && isKong1Yang) return kong1;
    if (!isYangGan && !isKong1Yang) return kong1;
    return kong2;
}

// 安天空、天马星
// 天空在年支顺时针前一宫；天马在三合局长生宫的对冲宫
function getTianKongXing(nianZhi) {
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (zhiIdx === -1) return null;
    return diZhi[(zhiIdx + 1) % 12];
}

const tianMaMap = {
    '申': '寅', '子': '寅', '辰': '寅',
    '寅': '申', '午': '申', '戌': '申',
    '巳': '亥', '酉': '亥', '丑': '亥',
    '亥': '巳', '卯': '巳', '未': '巳'
};

function getTianMa(nianZhi) {
    return tianMaMap[nianZhi] || null;
}

// 安天哭、天虚星
// 从午宫起子年，天哭逆行数到生年，天虚顺行数到生年
function getTianKu(nianZhi) {
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (zhiIdx === -1) return null;
    const wuIdx = diZhi.indexOf('午');
    return diZhi[(wuIdx - zhiIdx + 12) % 12];
}

function getTianXu(nianZhi) {
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (zhiIdx === -1) return null;
    const wuIdx = diZhi.indexOf('午');
    return diZhi[(wuIdx + zhiIdx) % 12];
}

// 安孤辰、寡宿星
// 按出生年支所在方定位：寅卯辰巳丑，巳午未申辰，申酉戌亥未，亥子丑寅戌
const guChenGuaSuMap = {
    '寅': { guChen: '巳', guaSu: '丑' },
    '卯': { guChen: '巳', guaSu: '丑' },
    '辰': { guChen: '巳', guaSu: '丑' },
    '巳': { guChen: '申', guaSu: '辰' },
    '午': { guChen: '申', guaSu: '辰' },
    '未': { guChen: '申', guaSu: '辰' },
    '申': { guChen: '亥', guaSu: '未' },
    '酉': { guChen: '亥', guaSu: '未' },
    '戌': { guChen: '亥', guaSu: '未' },
    '亥': { guChen: '寅', guaSu: '戌' },
    '子': { guChen: '寅', guaSu: '戌' },
    '丑': { guChen: '寅', guaSu: '戌' }
};

function getGuChen(nianZhi) {
    return guChenGuaSuMap[nianZhi] ? guChenGuaSuMap[nianZhi].guChen : null;
}

function getGuaSu(nianZhi) {
    return guChenGuaSuMap[nianZhi] ? guChenGuaSuMap[nianZhi].guaSu : null;
}

// 安劫杀星
// 按出生年支所属三合局之绝位定位：申子辰绝巳，亥卯未绝申，寅午戌绝亥，巳酉丑绝寅
const jieShaMap = {
    '申': '巳', '子': '巳', '辰': '巳',
    '亥': '申', '卯': '申', '未': '申',
    '寅': '亥', '午': '亥', '戌': '亥',
    '巳': '寅', '酉': '寅', '丑': '寅'
};

function getJieSha(nianZhi) {
    return jieShaMap[nianZhi] || null;
}

// 安恩光、天贵星
// 恩光从文昌起初一顺行至生日再退后一步；天贵从文曲起初一顺行至生日再退后一步
function getEnGuang(wenChangZhi, lunarDay) {
    const idx = diZhi.indexOf(wenChangZhi);
    if (idx === -1) return null;
    return diZhi[(idx + lunarDay - 2 + 12) % 12];
}

function getTianGui(wenQuZhi, lunarDay) {
    const idx = diZhi.indexOf(wenQuZhi);
    if (idx === -1) return null;
    return diZhi[(idx + lunarDay - 2 + 12) % 12];
}

// 安三台、八座星
// 三台从左辅起初一顺行至生日；八座从右弼起初一逆行至生日
function getSanTai(zuoFuZhi, lunarDay) {
    const idx = diZhi.indexOf(zuoFuZhi);
    if (idx === -1) return null;
    return diZhi[(idx + lunarDay - 1) % 12];
}

function getBaZuo(youBiZhi, lunarDay) {
    const idx = diZhi.indexOf(youBiZhi);
    if (idx === -1) return null;
    return diZhi[(idx - lunarDay + 1 + 12) % 12];
}

// 安天伤、天使星
// 阳男阴女：天伤在仆役、天使在疾厄；阴男阳女：天伤在疾厄、天使在仆役
function getTianShang(mingZhi, gender, nianGan) {
    const mingIdx = diZhi.indexOf(mingZhi);
    if (mingIdx === -1) return null;
    const nuPuIdx = (mingIdx + 5) % 12;
    const jiEIdx = (mingIdx + 7) % 12;
    const isYangGan = yangGan.includes(nianGan);
    const isMale = gender === 'male';
    const shangInNuPu = (isYangGan && isMale) || (!isYangGan && !isMale);
    return diZhi[shangInNuPu ? nuPuIdx : jiEIdx];
}

function getTianShi(mingZhi, gender, nianGan) {
    const mingIdx = diZhi.indexOf(mingZhi);
    if (mingIdx === -1) return null;
    const nuPuIdx = (mingIdx + 5) % 12;
    const jiEIdx = (mingIdx + 7) % 12;
    const isYangGan = yangGan.includes(nianGan);
    const isMale = gender === 'male';
    const shangInNuPu = (isYangGan && isMale) || (!isYangGan && !isMale);
    return diZhi[shangInNuPu ? jiEIdx : nuPuIdx];
}

// 安阴煞星
// 正月寅起，隔一宫逆行轮排十二月
function getYinSha(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const yinIdx = diZhi.indexOf('寅');
    return diZhi[(yinIdx - (lunarMonth - 1) * 2 + 24) % 12];
}

// 安天月星
// 按农历月份直接定位：一犬二蛇三在龙，四虎五羊六兔宫，七猪八羊九在虎，十马冬犬腊寅中
const tianYueMap = {
    1: '戌', 2: '巳', 3: '辰', 4: '寅', 5: '未', 6: '卯',
    7: '亥', 8: '未', 9: '寅', 10: '午', 11: '戌', 12: '寅'
};

function getTianYueXing(lunarMonth) {
    return tianYueMap[lunarMonth] || null;
}

// 安月解、天巫星
// 月解按单月建取对宫，双月依前单月；天巫在巳申寅亥四轮
function getYueJie(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const monthZhiOrder = ['寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子', '丑'];
    const oddMonthIdx = Math.floor((lunarMonth - 1) / 2) * 2;
    const zhi = monthZhiOrder[oddMonthIdx];
    const zhiIdx = diZhi.indexOf(zhi);
    return diZhi[(zhiIdx + 6) % 12];
}

function getTianWu(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const map = ['巳', '申', '寅', '亥'];
    return map[(lunarMonth - 1) % 4];
}

// 安天刑、天姚星
// 天刑从酉宫起正月顺行；天姚从丑宫起正月顺行
function getTianXing(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const youIdx = diZhi.indexOf('酉');
    return diZhi[(youIdx + lunarMonth - 1) % 12];
}

function getTianYao(lunarMonth) {
    if (!lunarMonth || lunarMonth < 1 || lunarMonth > 12) return null;
    const chouIdx = diZhi.indexOf('丑');
    return diZhi[(chouIdx + lunarMonth - 1) % 12];
}

// 安台辅、封诰星
// 台辅在文曲前二位（顺行）；封诰在文曲后二位（逆行）
function getTaiFu(wenQuZhi) {
    const idx = diZhi.indexOf(wenQuZhi);
    if (idx === -1) return null;
    return diZhi[(idx + 2) % 12];
}

function getFengGao(wenQuZhi) {
    const idx = diZhi.indexOf(wenQuZhi);
    if (idx === -1) return null;
    return diZhi[(idx - 2 + 12) % 12];
}

// 安龙池、凤阁星
// 龙池从辰宫起子顺行至生年；凤阁从戌宫起子逆行至生年
function getLongChi(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const chenIdx = diZhi.indexOf('辰');
    return diZhi[(chenIdx + idx) % 12];
}

function getFengGe(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const xuIdx = diZhi.indexOf('戌');
    return diZhi[(xuIdx - idx + 12) % 12];
}

// 安天才、天寿星
// 天才从命宫起子顺行至生年；天寿从身宫起子顺行至生年
function getTianCai(mingZhi, nianZhi) {
    const mingIdx = diZhi.indexOf(mingZhi);
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (mingIdx === -1 || zhiIdx === -1) return null;
    return diZhi[(mingIdx + zhiIdx) % 12];
}

function getTianShou(shenZhi, nianZhi) {
    const shenIdx = diZhi.indexOf(shenZhi);
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (shenIdx === -1 || zhiIdx === -1) return null;
    return diZhi[(shenIdx + zhiIdx) % 12];
}

// 安天德、年解星
// 天德从酉宫起顺行至生年；年解从戌宫起逆行至生年
function getTianDe(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const youIdx = diZhi.indexOf('酉');
    return diZhi[(youIdx + idx) % 12];
}

function getNianJie(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const xuIdx = diZhi.indexOf('戌');
    return diZhi[(xuIdx - idx + 12) % 12];
}

// 安年支六曜：蜚廉、破碎、华盖、咸池、龙德、月德
// 均按出生年支定位
const feiLianMap = {
    '子': '申', '丑': '酉', '寅': '戌', '卯': '巳', '辰': '午', '巳': '未',
    '午': '寅', '未': '卯', '申': '辰', '酉': '亥', '戌': '子', '亥': '丑'
};

function getFeiLian(nianZhi) {
    return feiLianMap[nianZhi] || null;
}

function getPoSui(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const map = ['巳', '丑', '酉'];
    return map[idx % 3];
}

function getHuaGai(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const map = ['辰', '丑', '戌', '未'];
    return map[idx % 4];
}

function getXianChi(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const map = ['酉', '午', '卯', '子'];
    return map[idx % 4];
}

function getLongDe(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const weiIdx = diZhi.indexOf('未');
    return diZhi[(weiIdx + idx) % 12];
}

function getYueDe(nianZhi) {
    const idx = diZhi.indexOf(nianZhi);
    if (idx === -1) return null;
    const siIdx = diZhi.indexOf('巳');
    return diZhi[(siIdx + idx) % 12];
}

// 安大耗星
// 年支对宫，阳支顺行前一位，阴支逆行后一位
function getDaHao(nianZhi) {
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (zhiIdx === -1) return null;
    const duiGongIdx = (zhiIdx + 6) % 12;
    if (yangZhi.includes(nianZhi)) {
        return diZhi[(duiGongIdx + 1) % 12];
    }
    if (yinZhi.includes(nianZhi)) {
        return diZhi[(duiGongIdx - 1 + 12) % 12];
    }
    return null;
}

// 安红鸾、天喜星
// 红鸾从卯宫起子年逆行数到生年；天喜在红鸾对宫
function getHongLuan(nianZhi) {
    const zhiIdx = diZhi.indexOf(nianZhi);
    if (zhiIdx === -1) return null;
    const maoIdx = diZhi.indexOf('卯');
    return diZhi[(maoIdx - zhiIdx + 12) % 12];
}

function getTianXi(nianZhi) {
    const hongLuan = getHongLuan(nianZhi);
    if (!hongLuan) return null;
    const idx = diZhi.indexOf(hongLuan);
    return diZhi[(idx + 6) % 12];
}

// 安禄存、擎羊、陀罗星
// 按出生年天干定位禄存，擎羊在禄存前一宫（顺时针），陀罗在禄存后一宫（逆时针）
const luCunMap = {
    '甲': '寅', '乙': '卯', '丙': '巳', '丁': '午',
    '戊': '巳', '己': '午', '庚': '申', '辛': '酉',
    '壬': '亥', '癸': '子'
};

function getLuCun(nianGan) {
    return luCunMap[nianGan] || null;
}

function getQingYang(nianGan) {
    const luCun = getLuCun(nianGan);
    if (!luCun) return null;
    const idx = diZhi.indexOf(luCun);
    return diZhi[(idx + 1) % 12];
}

function getTuoLuo(nianGan) {
    const luCun = getLuCun(nianGan);
    if (!luCun) return null;
    const idx = diZhi.indexOf(luCun);
    return diZhi[(idx - 1 + 12) % 12];
}

// 安天魁、天钺星
// 按出生年天干定位
const kuiYueMap = {
    '甲': { tianKui: '丑', tianYue: '未' },
    '戊': { tianKui: '丑', tianYue: '未' },
    '庚': { tianKui: '丑', tianYue: '未' },
    '乙': { tianKui: '子', tianYue: '申' },
    '己': { tianKui: '子', tianYue: '申' },
    '丙': { tianKui: '亥', tianYue: '酉' },
    '丁': { tianKui: '亥', tianYue: '酉' },
    '壬': { tianKui: '卯', tianYue: '巳' },
    '癸': { tianKui: '卯', tianYue: '巳' },
    '辛': { tianKui: '午', tianYue: '寅' }
};

function getTianKui(nianGan) {
    return kuiYueMap[nianGan] ? kuiYueMap[nianGan].tianKui : null;
}

function getTianYue(nianGan) {
    return kuiYueMap[nianGan] ? kuiYueMap[nianGan].tianYue : null;
}

// 安命主（按出生年支）
// 子贪狼、丑巨门、寅禄存、卯文曲、辰廉贞、巳武曲、午破军、未武曲、申廉贞、酉文曲、戌禄存、亥巨门
const mingZhuMap = {
    '子': '贪狼', '丑': '巨门', '寅': '禄存', '卯': '文曲',
    '辰': '廉贞', '巳': '武曲', '午': '破军', '未': '武曲',
    '申': '廉贞', '酉': '文曲', '戌': '禄存', '亥': '巨门'
};

function getMingZhu(nianZhi) {
    return mingZhuMap[nianZhi] || null;
}

// 安身主（按出生年支）
// 子午火星、丑未天相、寅申天梁、卯酉天同、辰戌文昌、巳亥天机
const shenZhuMap = {
    '子': '火星', '午': '火星',
    '丑': '天相', '未': '天相',
    '寅': '天梁', '申': '天梁',
    '卯': '天同', '酉': '天同',
    '辰': '文昌', '戌': '文昌',
    '巳': '天机', '亥': '天机'
};

function getShenZhu(nianZhi) {
    return shenZhuMap[nianZhi] || null;
}

// 安四化星
// 根据出生年天干，给主星标注禄、权、科、忌
const siHuaMap = {
    '甲': { '禄': '廉贞', '权': '破军', '科': '武曲', '忌': '太阳' },
    '乙': { '禄': '天机', '权': '天梁', '科': '紫微', '忌': '太阴' },
    '丙': { '禄': '天同', '权': '天机', '科': '文昌', '忌': '廉贞' },
    '丁': { '禄': '太阴', '权': '天同', '科': '天机', '忌': '巨门' },
    '戊': { '禄': '贪狼', '权': '太阴', '科': '太阳', '忌': '天机' },
    '己': { '禄': '武曲', '权': '贪狼', '科': '天梁', '忌': '文曲' },
    '庚': { '禄': '太阳', '权': '武曲', '科': '天府', '忌': '天同' },
    '辛': { '禄': '巨门', '权': '太阳', '科': '文曲', '忌': '文昌' },
    '壬': { '禄': '天梁', '权': '紫微', '科': '天府', '忌': '武曲' },
    '癸': { '禄': '破军', '权': '巨门', '科': '太阴', '忌': '贪狼' }
};

function getSiHua(nianGan, starMap) {
    const map = siHuaMap[nianGan];
    if (!map || !starMap) return null;
    const result = {};
    for (const [type, star] of Object.entries(map)) {
        const gong = starMap[star] || null;
        if (gong) {
            result[type] = { star, gong };
        }
    }
    return result;
}

// 流昌流曲（大运/流年/流月/流日/流时昌曲）
// 流昌起巳顺行，流曲起酉逆行，丙丁戊己同宫
const liuChangMap = {
    '甲': '巳', '乙': '午', '丙': '申', '丁': '酉',
    '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
    '壬': '寅', '癸': '卯'
};

const liuQuMap = {
    '甲': '酉', '乙': '申', '丙': '午', '丁': '巳',
    '戊': '午', '己': '巳', '庚': '卯', '辛': '寅',
    '壬': '子', '癸': '亥'
};

function getLiuChangQu(gan) {
    if (!gan) return null;
    return {
        chang: liuChangMap[gan] || null,
        qu: liuQuMap[gan] || null
    };
}

// 安天府星系主星
// 天府定位后，按固定步数逆时针排布：太阴、贪狼、巨门、天相、天梁、七杀、破军
const tianFuStarOffsets = {
    '天府': 0,
    '太阴': 1,
    '贪狼': 2,
    '巨门': 3,
    '天相': 4,
    '天梁': 5,
    '七杀': 6,
    '破军': 10
};

function getTianFuStarSystem(tianFuXing) {
    if (!tianFuXing) return {};
    const startIdx = diZhi.indexOf(tianFuXing);
    if (startIdx === -1) return {};
    const result = {};
    for (const [star, offset] of Object.entries(tianFuStarOffsets)) {
        const idx = (startIdx + offset) % 12;
        result[star] = diZhi[idx];
    }
    return result;
}

// 紫微天府对应关系
// 寅申同宫；卯丑、辰子、巳亥、午戌、未酉相对
function getTianFuXing(ziweiXing) {
    if (!ziweiXing) return null;
    const map = {
        '寅': '寅', '申': '申',
        '卯': '丑', '丑': '卯',
        '辰': '子', '子': '辰',
        '巳': '亥', '亥': '巳',
        '午': '戌', '戌': '午',
        '未': '酉', '酉': '未'
    };
    return map[ziweiXing] || null;
}

// 安紫微星系主星
// 紫微定位后，按固定步数逆时针排布：天机、太阳、武曲、天同、廉贞
const ziweiStarOffsets = {
    '紫微': 0,
    '天机': 1,
    '太阳': 3,
    '武曲': 4,
    '天同': 5,
    '廉贞': 8
};

function getZiweiStarSystem(ziweiXing) {
    if (!ziweiXing) return {};
    const startIdx = diZhi.indexOf(ziweiXing);
    if (startIdx === -1) return {};
    const result = {};
    for (const [star, offset] of Object.entries(ziweiStarOffsets)) {
        const idx = (startIdx - offset + 12) % 12;
        result[star] = diZhi[idx];
    }
    return result;
}

// 起紫微星
// 生日 / 局数 = 商数 ... 余数
// 余数为0：从寅宫起顺行商数步
// 余数>0且商数为0：紫微在掌诀宫
// 余数>0且商数>0：从掌诀宫顺行商数步
function getZiweiXing(birthDay, wuXingJu) {
    if (!wuXingJu || wuXingJu === '-') return null;
    const wuXing = wuXingJu.charAt(0);
    const juMap = { '二': 2, '三': 3, '四': 4, '五': 5, '六': 6 };
    const ju = juMap[wuXingJu.charAt(1)];
    if (!ju) return null;

    const shang = Math.floor(birthDay / ju);
    const yu = birthDay % ju;

    if (yu === 0) {
        return stepZhi('寅', shang - 1);
    }

    const zhangJueGong = getZhangJueGong(wuXing, yu);
    if (!zhangJueGong) return null;

    if (shang === 0) {
        return zhangJueGong;
    }

    return stepZhi(zhangJueGong, shang);
}

// 农历月份对应月支（正月寅，二月卯...）
const monthZhiOrder = ['寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子', '丑'];

// 按农历月份计算月柱干支（五虎遁）
function getMonthGanZhi(nianGan, lunarMonth) {
    const startMap = { '甲': 2, '己': 2, '乙': 4, '庚': 4, '丙': 6, '辛': 6, '丁': 8, '壬': 8, '戊': 0, '癸': 0 };
    const start = startMap[nianGan];
    if (start === undefined) return '-';
    const zhiIdx = lunarMonth - 1;
    const zhi = monthZhiOrder[zhiIdx];
    const gan = tianGan[(start + zhiIdx) % 10];
    return gan + zhi;
}

// 六十甲子纳音（按六十甲子顺序）
const nayin60 = [
    '海中金','海中金','炉中火','炉中火','大林木','大林木',
    '路旁土','路旁土','剑锋金','剑锋金','山头火','山头火',
    '涧下水','涧下水','城头土','城头土','白蜡金','白蜡金',
    '杨柳木','杨柳木','泉中水','泉中水','屋上土','屋上土',
    '霹雳火','霹雳火','松柏木','松柏木','长流水','长流水',
    '沙中金','沙中金','山下火','山下火','平地木','平地木',
    '壁上土','壁上土','金箔金','金箔金','覆灯火','覆灯火',
    '天河水','天河水','大驿土','大驿土','钗钏金','钗钏金',
    '桑柘木','桑柘木','大溪水','大溪水','沙中土','沙中土',
    '天上火','天上火','石榴木','石榴木','大海水','大海水'
];

const wuxingJuMap = { '金': '金四局', '木': '木三局', '水': '水二局', '火': '火六局', '土': '土五局' };

// 五行长生位
const changShengStart = {
    '金': '巳', '木': '亥', '火': '寅', '水': '申', '土': '申'
};

// 长生十二神顺序
const changShengOrder = ['长生', '沐浴', '冠带', '临官', '帝旺', '衰', '病', '死', '墓', '绝', '胎', '养'];

// 太岁十二神顺序（太岁改称岁建）
const taiSuiOrder = ['岁建', '晦气', '丧门', '贯索', '官符', '小耗', '岁破', '龙德', '白虎', '天德', '吊客', '病符'];

// 安太岁十二神（按年支顺行）
function getTaiSuiTwelve(nianZhi) {
    if (!nianZhi) return {};
    const startIdx = diZhi.indexOf(nianZhi);
    if (startIdx === -1) return {};
    const result = {};
    taiSuiOrder.forEach((name, i) => {
        const idx = (startIdx + i) % 12;
        result[diZhi[idx]] = name;
    });
    return result;
}

// 三合局旺地
const sanHeWang = {
    '申': '子', '子': '子', '辰': '子',
    '亥': '卯', '卯': '卯', '未': '卯',
    '寅': '午', '午': '午', '戌': '午',
    '巳': '酉', '酉': '酉', '丑': '酉'
};

// 将前诸星顺序
const jiangQianOrder = ['将星', '攀鞍', '岁驿', '息神', '华盖', '劫煞', '灾煞', '天煞', '指背', '咸池', '月煞', '亡神'];

// 安将前诸星（按年支三合局旺地起，顺行）
function getJiangQian(nianZhi) {
    if (!nianZhi) return {};
    const startZhi = sanHeWang[nianZhi];
    if (!startZhi) return {};
    const startIdx = diZhi.indexOf(startZhi);
    if (startIdx === -1) return {};
    const result = {};
    jiangQianOrder.forEach((name, i) => {
        const idx = (startIdx + i) % 12;
        result[diZhi[idx]] = name;
    });
    return result;
}

// 生年博士十二神顺序
const boShiOrder = ['博士', '力士', '青龙', '小耗', '将军', '奏书', '飞廉', '喜神', '病符', '大耗', '伏兵', '官府'];

// 安生年博士十二神（以年干禄存起，阳男阴女顺行，阴男阳女逆行）
function getBoShi(nianGan, gender) {
    if (!nianGan) return {};
    const startZhi = luCunMap[nianGan];
    if (!startZhi) return {};
    const startIdx = diZhi.indexOf(startZhi);
    if (startIdx === -1) return {};
    const isYangGan = ['甲', '丙', '戊', '庚', '壬'].includes(nianGan);
    const isMale = gender === 'male';
    const isForward = (isYangGan && isMale) || (!isYangGan && !isMale);
    const result = {};
    boShiOrder.forEach((name, i) => {
        const idx = isForward
            ? (startIdx + i) % 12
            : (startIdx - i + 12) % 12;
        result[diZhi[idx]] = name;
    });
    return result;
}

// 安流年博士十二神：起点用流年天干禄存，顺逆仍按原局命主出生年干阴阳 + 性别
function getLiuNianBoShi(liuNianGan, nianGan, gender) {
    if (!liuNianGan || !nianGan) return {};
    const startZhi = luCunMap[liuNianGan];
    if (!startZhi) return {};
    const startIdx = diZhi.indexOf(startZhi);
    if (startIdx === -1) return {};
    const isYangGan = ['甲', '丙', '戊', '庚', '壬'].includes(nianGan);
    const isMale = gender === 'male';
    const isForward = (isYangGan && isMale) || (!isYangGan && !isMale);
    const result = {};
    boShiOrder.forEach((name, i) => {
        const idx = isForward
            ? (startIdx + i) % 12
            : (startIdx - i + 12) % 12;
        result[diZhi[idx]] = name;
    });
    return result;
}

// 起大限
// 由命宫起，阳男阴女顺地支，阴男阳女逆地支，每十年过一宫
// 起限年龄依五行局数：水二局2岁、木三局3岁、金四局4岁、土五局5岁、火六局6岁
function getDaXian(mingZhi, wuXingJu, nianGan, gender) {
    if (!mingZhi || !wuXingJu || wuXingJu === '-') return {};
    const juMap = { '水二局': 2, '木三局': 3, '金四局': 4, '土五局': 5, '火六局': 6 };
    const startAge = juMap[wuXingJu];
    if (!startAge) return {};

    const mingIdx = diZhi.indexOf(mingZhi);
    if (mingIdx === -1) return {};

    const isYangGan = ['甲', '丙', '戊', '庚', '壬'].includes(nianGan);
    const isMale = gender === 'male';
    // 阳男阴女顺地支，阴男阳女逆地支
    const isForward = (isYangGan && isMale) || (!isYangGan && !isMale);

    const result = {};
    for (let i = 0; i < 12; i++) {
        const zhiIdx = isForward
            ? (mingIdx + i) % 12
            : (mingIdx - i + 12) % 12;
        const zhi = diZhi[zhiIdx];
        const start = startAge + i * 10;
        const end = start + 9;
        result[zhi] = `${start}-${end}`;
    }
    return result;
}

// 查找某公历年内（含相邻年）的农历正月初一
async function getZhengYueChuYi(solarYear) {
    for (const year of [solarYear, solarYear - 1, solarYear + 1]) {
        if (year < LUNAR_BASE_YEAR || year >= LUNAR_BASE_YEAR + LUNAR_DATA.length) continue;
        const dataMap = await fetchZiweiYearData(year);
        if (!dataMap) continue;
        for (let m = 1; m <= 12; m++) {
            for (let d = 1; d <= 31; d++) {
                const dayData = dataMap[m + '-' + d];
                if (dayData && parseInt(dayData.lunarMonth, 10) === 1 && parseInt(dayData.lunarDay, 10) === 1 && !dayData.isLeap) {
                    return { year, month: m, day: d };
                }
            }
        }
    }
    return null;
}

// 根据公历日期获取农历年
async function getLunarYearOfDate(solarYear, solarMonth, solarDay) {
    const dataMap = await fetchZiweiYearData(solarYear);
    if (!dataMap) return null;
    const dayData = dataMap[solarMonth + '-' + solarDay];
    if (!dayData) return null;
    const lunarMonth = parseInt(dayData.lunarMonth, 10);
    return getLunarYear(solarYear, solarMonth, lunarMonth);
}

// 根据所选大限/岁数，计算该运起始时间
// birth: { year, month, day, hour, minute }
async function getDaXianStartTime(yunNumValue, birth, wuXingJu) {
    const juMap = { '水二局': 2, '木三局': 3, '金四局': 4, '土五局': 5, '火六局': 6 };

    if (yunNumValue.startsWith('age_')) {
        const age = parseInt(yunNumValue.replace('age_', ''), 10);
        if (age === 1) {
            return { ...birth };
        } else {
            const date = await getZhengYueChuYi(birth.year + age - 1);
            if (!date) return null;
            return { year: date.year, month: date.month, day: date.day, hour: 0, minute: 0 };
        }
    } else if (yunNumValue.startsWith('yun_')) {
        const yunIndex = parseInt(yunNumValue.replace('yun_', ''), 10);
        const startAge = juMap[wuXingJu];
        if (!startAge) return null;
        const age = startAge + (yunIndex - 1) * 10;
        const date = await getZhengYueChuYi(birth.year + age - 1);
        if (!date) return null;
        return { year: date.year, month: date.month, day: date.day, hour: 0, minute: 0 };
    }
    return null;
}

// 根据流年日期，反推该流年对应的大运选框值（age_N 或 yun_N）
// birth: { year, month, day, hour, minute }
// enteredDate: { year, month, day }
async function getYunNumByLiuNianDate(birth, enteredDate, wuXingJu) {
    const [enteredLunarYear, birthLunarYear] = await Promise.all([
        getLunarYearOfDate(enteredDate.year, enteredDate.month, enteredDate.day),
        getLunarYearOfDate(birth.year, birth.month, birth.day)
    ]);
    if (!enteredLunarYear || !birthLunarYear) return null;

    const age = enteredLunarYear - birthLunarYear + 1;
    const juMap = { '水二局': 2, '木三局': 3, '金四局': 4, '土五局': 5, '火六局': 6 };
    const startAge = juMap[wuXingJu];
    if (!startAge) return null;

    if (age < 1) return null;
    if (age < startAge) {
        return 'age_' + age;
    } else {
        const yunIndex = Math.floor((age - startAge) / 10) + 1;
        return 'yun_' + Math.min(12, Math.max(1, yunIndex));
    }
}

// 计算十二运的结束时间（十三运起点）：出生年 + 起运年龄 + 119 的农历正月初一 00:00
async function getTwelfthYunEnd(result) {
    const juMap = { '水二局': 2, '木三局': 3, '金四局': 4, '土五局': 5, '火六局': 6 };
    const startAge = juMap[result.wuXingJu];
    if (!startAge) return null;
    const endYear = result.solar.year + startAge + 119;
    const date = await getZhengYueChuYi(endYear);
    if (!date) return null;
    return new Date(date.year, date.month - 1, date.day, 0, 0, 0, 0);
}

// 安长生十二神
// 阳男阴女顺行，阴男阳女逆行
function getChangShengTwelve(wuXingJu, gender, nianGan) {
    if (!wuXingJu || wuXingJu === '-') return {};
    const wuXing = wuXingJu.charAt(0);
    const startZhi = changShengStart[wuXing];
    if (!startZhi) return {};
    const startIdx = diZhi.indexOf(startZhi);
    if (startIdx === -1) return {};
    const isYangGan = ['甲', '丙', '戊', '庚', '壬'].includes(nianGan);
    const isMale = gender === 'male';
    const isForward = (isYangGan && isMale) || (!isYangGan && !isMale);
    const result = {};
    changShengOrder.forEach((name, i) => {
        const idx = isForward
            ? (startIdx + i) % 12
            : (startIdx - i + 12) % 12;
        result[diZhi[idx]] = name;
    });
    return result;
}

function getGanZhiIndex(gan, zhi) {
    const ganIdx = tianGan.indexOf(gan);
    const zhiIdx = diZhi.indexOf(zhi);
    if (ganIdx === -1 || zhiIdx === -1) return -1;
    // 六十甲子序号：甲子=0, 乙丑=1, ...
    for (let i = 0; i < 60; i++) {
        if (i % 10 === ganIdx && i % 12 === zhiIdx) return i;
    }
    return -1;
}

function getNayin(gan, zhi) {
    const idx = getGanZhiIndex(gan, zhi);
    if (idx === -1) return '-';
    return nayin60[idx];
}

function getWuXingJu(mingGan, mingZhi) {
    const nayin = getNayin(mingGan, mingZhi);
    if (nayin === '-') return '-';
    const wx = nayin.charAt(nayin.length - 1); // 纳音最后一个字为五行
    return wuxingJuMap[wx] || '-';
}

// ========== 地盘排盘（以天盘身宫为命宫，身宫干支纳音定五行局）==========
async function getZiweiDiPan(year, month, day, hour, minute, gender) {
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    const lunarText = await getLunarText(year, month, day, hour);
    const siZhu = await getSiZhu(year, month, day, hour);

    // 先算天盘命宫、身宫（只为取地支）
    let tianMingShen = { ming: '-', shen: '-' };
    let effectiveLunarMonth = null;
    const hourZhiIndex = Math.floor((hour + 1) / 2) % 12;
    if (dayData) {
        effectiveLunarMonth = getEffectiveLunarMonth(dayData, hour);
        tianMingShen = getMingShenGong(effectiveLunarMonth, hour);
    }

    // 地盘规则：天盘身宫 → 地盘命宫
    const diMingZhi = tianMingShen.shen;
    const diTwelvePalaces = (diMingZhi !== '-') ? getTwelvePalaces(diMingZhi) : {};

    // 地盘身宫：保持与天盘身宫相同的"宫位名称"
    // 例：天盘身宫在夫妻宫 → 地盘身宫也在地盘的夫妻宫（原地支可能不同）
    let diShenZhi = '-';
    if (tianMingShen.shen !== '-' && tianMingShen.ming !== '-') {
        const tianTwelvePalaces = getTwelvePalaces(tianMingShen.ming);
        const shenPalaceName = tianTwelvePalaces[tianMingShen.shen];
        let found = false;
        for (const [zhi, name] of Object.entries(diTwelvePalaces)) {
            if (name === shenPalaceName) {
                diShenZhi = zhi;
                found = true;
                break;
            }
        }
        if (!found) {
            console.warn('[地盘身宫] 未找到匹配！shenPalaceName=', shenPalaceName, ' diTwelvePalaces=', JSON.stringify(diTwelvePalaces));
        }
    }
    const diMingShen = { ming: diMingZhi, shen: diShenZhi };

    let gongGan = {};
    let diWuXingJu = '-';
    let ziweiXing = null;
    let tianFuXing = null;
    let ziweiStarSystem = {};
    let tianFuStarSystem = {};
    let zuoFu = null, youBi = null, wenQu = null, wenChang = null, diJie = null, diKong = null;
    let tianKui = null, tianYue = null, luCun = null, qingYang = null, tuoLuo = null;
    let huoXing = null, lingXing = null, tianGuan = null, tianFuStar = null, tianChu = null;
    let jieKong = null, xunKong = null, tianKongXing = null, tianMa = null, tianKu = null, tianXu = null;
    let hongLuan = null, tianXi = null, guChen = null, guaSu = null, jieSha = null, daHao = null;
    let feiLian = null, poSui = null, huaGai = null, xianChi = null, longDe = null, yueDe = null;
    let tianDe = null, nianJie = null, tianCai = null, tianShou = null;
    let longChi = null, fengGe = null, taiFu = null, fengGao = null, tianXing = null, tianYao = null;
    let yueJie = null, tianWu = null, tianYueXing = null, yinSha = null;
    let tianShang = null, tianShi = null, sanTai = null, baZuo = null, enGuang = null, tianGui = null;
    let siHua = null, allStarMap = null, mingZhu = null, shenZhu = null;
    let changShengTwelve = {}, taiSuiTwelve = {}, jiangQian = {}, boShi = {};
    let starBrightness = {}, auxStarBrightness = {}, daXian = {};

    if (siZhu.year && siZhu.year !== '-') {
        const nianGan = siZhu.year.charAt(0);
        const nianZhi = siZhu.year.charAt(1);
        gongGan = getGongGan(nianGan);

        // 地盘五行局：以天盘身宫的天干+地支取纳音五行
        const diMingGan = gongGan[diMingZhi];
        if (diMingGan && diMingZhi !== '-') {
            diWuXingJu = getWuXingJu(diMingGan, diMingZhi);
        }

        // 不依赖命宫/五行局的通用星（与天盘一致）
        zuoFu = getZuoFu(effectiveLunarMonth);
        youBi = getYouBi(effectiveLunarMonth);
        wenQu = getWenQu(hourZhiIndex);
        wenChang = getWenChang(hourZhiIndex);
        diJie = getDiJie(hourZhiIndex);
        diKong = getDiKong(hourZhiIndex);
        tianKui = getTianKui(nianGan);
        tianYue = getTianYue(nianGan);
        luCun = getLuCun(nianGan);
        qingYang = getQingYang(nianGan);
        tuoLuo = getTuoLuo(nianGan);
        huoXing = getHuoXing(nianZhi, hourZhiIndex);
        lingXing = getLingXing(nianZhi, hourZhiIndex);
        tianGuan = getTianGuan(nianGan);
        tianFuStar = getTianFu(nianGan);
        tianChu = getTianChu(nianGan);
        jieKong = getJieKong(nianGan);
        xunKong = getXunKong(nianGan, nianZhi);
        tianKongXing = getTianKongXing(nianZhi);
        tianMa = getTianMa(nianZhi);
        tianKu = getTianKu(nianZhi);
        tianXu = getTianXu(nianZhi);
        hongLuan = getHongLuan(nianZhi);
        tianXi = getTianXi(nianZhi);
        guChen = getGuChen(nianZhi);
        guaSu = getGuaSu(nianZhi);
        jieSha = getJieSha(nianZhi);
        daHao = getDaHao(nianZhi);
        feiLian = getFeiLian(nianZhi);
        poSui = getPoSui(nianZhi);
        huaGai = getHuaGai(nianZhi);
        xianChi = getXianChi(nianZhi);
        longDe = getLongDe(nianZhi);
        yueDe = getYueDe(nianZhi);
        tianDe = getTianDe(nianZhi);
        nianJie = getNianJie(nianZhi);
        longChi = getLongChi(nianZhi);
        fengGe = getFengGe(nianZhi);
        mingZhu = getMingZhu(nianZhi);
        shenZhu = getShenZhu(nianZhi);
        taiSuiTwelve = getTaiSuiTwelve(nianZhi);
        jiangQian = getJiangQian(nianZhi);

        // 依赖月份/日期的通用星
        tianXing = getTianXing(effectiveLunarMonth);
        tianYao = getTianYao(effectiveLunarMonth);
        yueJie = getYueJie(effectiveLunarMonth);
        tianWu = getTianWu(effectiveLunarMonth);
        tianYueXing = getTianYueXing(effectiveLunarMonth);
        yinSha = getYinSha(effectiveLunarMonth);

        if (dayData && diWuXingJu !== '-') {
            const lunarDayNum = parseInt(dayData.lunarDay, 10);

            // === 依赖新五行局的星 ===
            ziweiXing = getZiweiXing(lunarDayNum, diWuXingJu);
            tianFuXing = getTianFuXing(ziweiXing);
            ziweiStarSystem = getZiweiStarSystem(ziweiXing);
            tianFuStarSystem = getTianFuStarSystem(tianFuXing);
            changShengTwelve = getChangShengTwelve(diWuXingJu, gender, nianGan);
            boShi = getBoShi(nianGan, gender);
            daXian = getDaXian(diMingZhi, diWuXingJu, nianGan, gender);

            // === 依赖新命宫/身宫的星 ===
            tianCai = getTianCai(diMingZhi, nianZhi);      // 天才从地盘命宫起
            tianShou = getTianShou(diShenZhi, nianZhi);    // 天寿从地盘身宫（=天盘命宫）起
            tianShang = getTianShang(diMingZhi, gender, nianGan);
            tianShi = getTianShi(diMingZhi, gender, nianGan);

            // 依赖文曲/文昌/左辅/右弼 + 农历日
            taiFu = getTaiFu(wenQu);
            fengGao = getFengGao(wenQu);
            sanTai = getSanTai(zuoFu, lunarDayNum);
            baZuo = getBaZuo(youBi, lunarDayNum);
            enGuang = getEnGuang(wenChang, lunarDayNum);
            tianGui = getTianGui(wenQu, lunarDayNum);

            // 组装星图
            allStarMap = { ...ziweiStarSystem, ...tianFuStarSystem };
            if (zuoFu) allStarMap['左辅'] = zuoFu;
            if (youBi) allStarMap['右弼'] = youBi;
            if (wenQu) allStarMap['文曲'] = wenQu;
            if (wenChang) allStarMap['文昌'] = wenChang;
            if (diJie) allStarMap['地劫'] = diJie;
            if (diKong) allStarMap['地空'] = diKong;
            if (tianKui) allStarMap['天魁'] = tianKui;
            if (tianYue) allStarMap['天钺'] = tianYue;
            if (luCun) allStarMap['禄存'] = luCun;
            if (qingYang) allStarMap['擎羊'] = qingYang;
            if (tuoLuo) allStarMap['陀罗'] = tuoLuo;
            if (huoXing) allStarMap['火星'] = huoXing;
            if (lingXing) allStarMap['铃星'] = lingXing;
            if (tianGuan) allStarMap['天官'] = tianGuan;
            if (tianFuStar) allStarMap['天福'] = tianFuStar;
            if (tianChu) allStarMap['天厨'] = tianChu;
            if (jieKong) allStarMap['截空'] = jieKong;
            if (xunKong) allStarMap['旬空'] = xunKong;
            if (tianKongXing) allStarMap['天空'] = tianKongXing;
            if (tianMa) allStarMap['天马'] = tianMa;
            if (tianKu) allStarMap['天哭'] = tianKu;
            if (tianXu) allStarMap['天虚'] = tianXu;
            if (hongLuan) allStarMap['红鸾'] = hongLuan;
            if (tianXi) allStarMap['天喜'] = tianXi;
            if (guChen) allStarMap['孤辰'] = guChen;
            if (guaSu) allStarMap['寡宿'] = guaSu;
            if (jieSha) allStarMap['劫杀'] = jieSha;
            if (daHao) allStarMap['大耗'] = daHao;
            if (feiLian) allStarMap['蜚廉'] = feiLian;
            if (poSui) allStarMap['破碎'] = poSui;
            if (huaGai) allStarMap['华盖'] = huaGai;
            if (xianChi) allStarMap['咸池'] = xianChi;
            if (longDe) allStarMap['龙德'] = longDe;
            if (yueDe) allStarMap['月德'] = yueDe;
            if (tianDe) allStarMap['天德'] = tianDe;
            if (nianJie) allStarMap['年解'] = nianJie;
            if (tianCai) allStarMap['天才'] = tianCai;
            if (tianShou) allStarMap['天寿'] = tianShou;
            if (longChi) allStarMap['龙池'] = longChi;
            if (fengGe) allStarMap['凤阁'] = fengGe;
            if (taiFu) allStarMap['台辅'] = taiFu;
            if (fengGao) allStarMap['封诰'] = fengGao;
            if (tianXing) allStarMap['天刑'] = tianXing;
            if (tianYao) allStarMap['天姚'] = tianYao;
            if (yueJie) allStarMap['月解'] = yueJie;
            if (tianWu) allStarMap['天巫'] = tianWu;
            if (tianYueXing) allStarMap['天月'] = tianYueXing;
            if (yinSha) allStarMap['阴煞'] = yinSha;
            if (tianShang) allStarMap['天伤'] = tianShang;
            if (tianShi) allStarMap['天使'] = tianShi;
            if (sanTai) allStarMap['三台'] = sanTai;
            if (baZuo) allStarMap['八座'] = baZuo;
            if (enGuang) allStarMap['恩光'] = enGuang;
            if (tianGui) allStarMap['天贵'] = tianGui;

            for (const [star, zhi] of Object.entries(allStarMap)) {
                if (mainStarBrightness[star]) {
                    starBrightness[star] = getStarBrightness(star, zhi);
                }
                if (auxStarBrightnessMap[star]) {
                    auxStarBrightness[star] = getAuxStarBrightness(star, zhi);
                }
            }
            siHua = getSiHua(nianGan, allStarMap);
        }
    }

    return {
        lunarText,
        siZhu,
        mingShen: diMingShen,
        twelvePalaces: diTwelvePalaces,
        gongGan,
        wuXingJu: diWuXingJu,
        ziweiXing,
        tianFuXing,
        ziweiStarSystem,
        tianFuStarSystem,
        zuoFu, youBi, wenQu, wenChang, diJie, diKong,
        tianKui, tianYue, luCun, qingYang, tuoLuo,
        huoXing, lingXing, tianGuan, tianFuStar, tianChu,
        jieKong, xunKong, tianKongXing, tianMa, tianKu, tianXu,
        hongLuan, tianXi, guChen, guaSu, jieSha, daHao,
        feiLian, poSui, huaGai, xianChi, longDe, yueDe,
        tianDe, nianJie, tianCai, tianShou,
        longChi, fengGe, taiFu, fengGao, tianXing, tianYao,
        yueJie, tianWu, tianYueXing, yinSha,
        tianShang, tianShi, sanTai, baZuo, enGuang, tianGui,
        siHua, allStarMap, mingZhu, shenZhu,
        changShengTwelve, taiSuiTwelve, jiangQian, boShi,
        starBrightness, auxStarBrightness, daXian,
        panType: 'di',
        solar: { year, month, day, hour, minute },
        effectiveLunarMonth,
        hourZhiIndex,
        gender
    };
}

// ===== 人盘排盘 =====
// 人盘规则：以天盘福德宫为命宫，福德宫干支纳音定五行局安星
// 身宫：与天盘身宫保持相同宫位名称（天盘身宫在夫妻宫 → 人盘身宫也在夫妻宫）
async function getZiweiRenPan(year, month, day, hour, minute, gender) {
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    const lunarText = await getLunarText(year, month, day, hour);
    const siZhu = await getSiZhu(year, month, day, hour);

    // 先算天盘命宫、身宫、十二宫（为取福德宫地支）
    let tianMingShen = { ming: '-', shen: '-' };
    let tianTwelvePalaces = {};
    let effectiveLunarMonth = null;
    const hourZhiIndex = Math.floor((hour + 1) / 2) % 12;
    if (dayData) {
        effectiveLunarMonth = getEffectiveLunarMonth(dayData, hour);
        tianMingShen = getMingShenGong(effectiveLunarMonth, hour);
        tianTwelvePalaces = (tianMingShen.ming !== '-') ? getTwelvePalaces(tianMingShen.ming) : {};
    }

    // 人盘规则：天盘福德宫 → 人盘命宫
    // 找到天盘十二宫中"福德"宫对应的地支
    let fuDeZhi = '-';
    if (tianMingShen.ming !== '-') {
        for (const [zhi, name] of Object.entries(tianTwelvePalaces)) {
            if (name === '福德') {
                fuDeZhi = zhi;
                break;
            }
        }
    }
    const renMingZhi = fuDeZhi;
    const renTwelvePalaces = (renMingZhi !== '-') ? getTwelvePalaces(renMingZhi) : {};

    // 人盘身宫：保持与天盘身宫相同的"宫位名称"
    // 例：天盘身宫在夫妻宫 → 人盘身宫也在人盘的夫妻宫（地支可能不同）
    let renShenZhi = '-';
    if (tianMingShen.shen !== '-' && tianMingShen.ming !== '-') {
        const shenPalaceName = tianTwelvePalaces[tianMingShen.shen];
        for (const [zhi, name] of Object.entries(renTwelvePalaces)) {
            if (name === shenPalaceName) {
                renShenZhi = zhi;
                break;
            }
        }
    }
    const renMingShen = { ming: renMingZhi, shen: renShenZhi };

    let gongGan = {};
    let renWuXingJu = '-';
    let ziweiXing = null;
    let tianFuXing = null;
    let ziweiStarSystem = {};
    let tianFuStarSystem = {};
    let zuoFu = null, youBi = null, wenQu = null, wenChang = null, diJie = null, diKong = null;
    let tianKui = null, tianYue = null, luCun = null, qingYang = null, tuoLuo = null;
    let huoXing = null, lingXing = null, tianGuan = null, tianFuStar = null, tianChu = null;
    let jieKong = null, xunKong = null, tianKongXing = null, tianMa = null, tianKu = null, tianXu = null;
    let hongLuan = null, tianXi = null, guChen = null, guaSu = null, jieSha = null, daHao = null;
    let feiLian = null, poSui = null, huaGai = null, xianChi = null, longDe = null, yueDe = null;
    let tianDe = null, nianJie = null, tianCai = null, tianShou = null;
    let longChi = null, fengGe = null, taiFu = null, fengGao = null, tianXing = null, tianYao = null;
    let yueJie = null, tianWu = null, tianYueXing = null, yinSha = null;
    let tianShang = null, tianShi = null, sanTai = null, baZuo = null, enGuang = null, tianGui = null;
    let siHua = null, allStarMap = null, mingZhu = null, shenZhu = null;
    let changShengTwelve = {}, taiSuiTwelve = {}, jiangQian = {}, boShi = {};
    let starBrightness = {}, auxStarBrightness = {}, daXian = {};

    if (siZhu.year && siZhu.year !== '-') {
        const nianGan = siZhu.year.charAt(0);
        const nianZhi = siZhu.year.charAt(1);
        gongGan = getGongGan(nianGan);

        // 人盘五行局：以天盘福德宫的天干+地支取纳音五行
        const renMingGan = gongGan[renMingZhi];
        if (renMingGan && renMingZhi !== '-') {
            renWuXingJu = getWuXingJu(renMingGan, renMingZhi);
        }

        // 不依赖命宫/五行局的通用星（与天盘一致）
        zuoFu = getZuoFu(effectiveLunarMonth);
        youBi = getYouBi(effectiveLunarMonth);
        wenQu = getWenQu(hourZhiIndex);
        wenChang = getWenChang(hourZhiIndex);
        diJie = getDiJie(hourZhiIndex);
        diKong = getDiKong(hourZhiIndex);
        tianKui = getTianKui(nianGan);
        tianYue = getTianYue(nianGan);
        luCun = getLuCun(nianGan);
        qingYang = getQingYang(nianGan);
        tuoLuo = getTuoLuo(nianGan);
        huoXing = getHuoXing(nianZhi, hourZhiIndex);
        lingXing = getLingXing(nianZhi, hourZhiIndex);
        tianGuan = getTianGuan(nianGan);
        tianFuStar = getTianFu(nianGan);
        tianChu = getTianChu(nianGan);
        jieKong = getJieKong(nianGan);
        xunKong = getXunKong(nianGan, nianZhi);
        tianKongXing = getTianKongXing(nianZhi);
        tianMa = getTianMa(nianZhi);
        tianKu = getTianKu(nianZhi);
        tianXu = getTianXu(nianZhi);
        hongLuan = getHongLuan(nianZhi);
        tianXi = getTianXi(nianZhi);
        guChen = getGuChen(nianZhi);
        guaSu = getGuaSu(nianZhi);
        jieSha = getJieSha(nianZhi);
        daHao = getDaHao(nianZhi);
        feiLian = getFeiLian(nianZhi);
        poSui = getPoSui(nianZhi);
        huaGai = getHuaGai(nianZhi);
        xianChi = getXianChi(nianZhi);
        longDe = getLongDe(nianZhi);
        yueDe = getYueDe(nianZhi);
        tianDe = getTianDe(nianZhi);
        nianJie = getNianJie(nianZhi);
        longChi = getLongChi(nianZhi);
        fengGe = getFengGe(nianZhi);
        mingZhu = getMingZhu(nianZhi);
        shenZhu = getShenZhu(nianZhi);
        taiSuiTwelve = getTaiSuiTwelve(nianZhi);
        jiangQian = getJiangQian(nianZhi);

        // 依赖月份/日期的通用星
        tianXing = getTianXing(effectiveLunarMonth);
        tianYao = getTianYao(effectiveLunarMonth);
        yueJie = getYueJie(effectiveLunarMonth);
        tianWu = getTianWu(effectiveLunarMonth);
        tianYueXing = getTianYueXing(effectiveLunarMonth);
        yinSha = getYinSha(effectiveLunarMonth);

        if (dayData && renWuXingJu !== '-') {
            const lunarDayNum = parseInt(dayData.lunarDay, 10);

            // === 依赖人盘五行局的星 ===
            ziweiXing = getZiweiXing(lunarDayNum, renWuXingJu);
            tianFuXing = getTianFuXing(ziweiXing);
            ziweiStarSystem = getZiweiStarSystem(ziweiXing);
            tianFuStarSystem = getTianFuStarSystem(tianFuXing);
            changShengTwelve = getChangShengTwelve(renWuXingJu, gender, nianGan);
            boShi = getBoShi(nianGan, gender);
            daXian = getDaXian(renMingZhi, renWuXingJu, nianGan, gender);

            // === 依赖人盘命宫/身宫的星 ===
            tianCai = getTianCai(renMingZhi, nianZhi);      // 天才从人盘命宫起
            tianShou = getTianShou(renShenZhi, nianZhi);    // 天寿从人盘身宫起
            tianShang = getTianShang(renMingZhi, gender, nianGan);
            tianShi = getTianShi(renMingZhi, gender, nianGan);

            // 依赖文曲/文昌/左辅/右弼 + 农历日
            taiFu = getTaiFu(wenQu);
            fengGao = getFengGao(wenQu);
            sanTai = getSanTai(zuoFu, lunarDayNum);
            baZuo = getBaZuo(youBi, lunarDayNum);
            enGuang = getEnGuang(wenChang, lunarDayNum);
            tianGui = getTianGui(wenQu, lunarDayNum);

            // 组装星图
            allStarMap = { ...ziweiStarSystem, ...tianFuStarSystem };
            if (zuoFu) allStarMap['左辅'] = zuoFu;
            if (youBi) allStarMap['右弼'] = youBi;
            if (wenQu) allStarMap['文曲'] = wenQu;
            if (wenChang) allStarMap['文昌'] = wenChang;
            if (diJie) allStarMap['地劫'] = diJie;
            if (diKong) allStarMap['地空'] = diKong;
            if (tianKui) allStarMap['天魁'] = tianKui;
            if (tianYue) allStarMap['天钺'] = tianYue;
            if (luCun) allStarMap['禄存'] = luCun;
            if (qingYang) allStarMap['擎羊'] = qingYang;
            if (tuoLuo) allStarMap['陀罗'] = tuoLuo;
            if (huoXing) allStarMap['火星'] = huoXing;
            if (lingXing) allStarMap['铃星'] = lingXing;
            if (tianGuan) allStarMap['天官'] = tianGuan;
            if (tianFuStar) allStarMap['天福'] = tianFuStar;
            if (tianChu) allStarMap['天厨'] = tianChu;
            if (jieKong) allStarMap['截空'] = jieKong;
            if (xunKong) allStarMap['旬空'] = xunKong;
            if (tianKongXing) allStarMap['天空'] = tianKongXing;
            if (tianMa) allStarMap['天马'] = tianMa;
            if (tianKu) allStarMap['天哭'] = tianKu;
            if (tianXu) allStarMap['天虚'] = tianXu;
            if (hongLuan) allStarMap['红鸾'] = hongLuan;
            if (tianXi) allStarMap['天喜'] = tianXi;
            if (guChen) allStarMap['孤辰'] = guChen;
            if (guaSu) allStarMap['寡宿'] = guaSu;
            if (jieSha) allStarMap['劫杀'] = jieSha;
            if (daHao) allStarMap['大耗'] = daHao;
            if (feiLian) allStarMap['蜚廉'] = feiLian;
            if (poSui) allStarMap['破碎'] = poSui;
            if (huaGai) allStarMap['华盖'] = huaGai;
            if (xianChi) allStarMap['咸池'] = xianChi;
            if (longDe) allStarMap['龙德'] = longDe;
            if (yueDe) allStarMap['月德'] = yueDe;
            if (tianDe) allStarMap['天德'] = tianDe;
            if (nianJie) allStarMap['年解'] = nianJie;
            if (tianCai) allStarMap['天才'] = tianCai;
            if (tianShou) allStarMap['天寿'] = tianShou;
            if (longChi) allStarMap['龙池'] = longChi;
            if (fengGe) allStarMap['凤阁'] = fengGe;
            if (taiFu) allStarMap['台辅'] = taiFu;
            if (fengGao) allStarMap['封诰'] = fengGao;
            if (tianXing) allStarMap['天刑'] = tianXing;
            if (tianYao) allStarMap['天姚'] = tianYao;
            if (yueJie) allStarMap['月解'] = yueJie;
            if (tianWu) allStarMap['天巫'] = tianWu;
            if (tianYueXing) allStarMap['天月'] = tianYueXing;
            if (yinSha) allStarMap['阴煞'] = yinSha;
            if (tianShang) allStarMap['天伤'] = tianShang;
            if (tianShi) allStarMap['天使'] = tianShi;
            if (sanTai) allStarMap['三台'] = sanTai;
            if (baZuo) allStarMap['八座'] = baZuo;
            if (enGuang) allStarMap['恩光'] = enGuang;
            if (tianGui) allStarMap['天贵'] = tianGui;

            for (const [star, zhi] of Object.entries(allStarMap)) {
                if (mainStarBrightness[star]) {
                    starBrightness[star] = getStarBrightness(star, zhi);
                }
                if (auxStarBrightnessMap[star]) {
                    auxStarBrightness[star] = getAuxStarBrightness(star, zhi);
                }
            }
            siHua = getSiHua(nianGan, allStarMap);
        }
    }

    return {
        lunarText,
        siZhu,
        mingShen: renMingShen,
        twelvePalaces: renTwelvePalaces,
        gongGan,
        wuXingJu: renWuXingJu,
        ziweiXing,
        tianFuXing,
        ziweiStarSystem,
        tianFuStarSystem,
        zuoFu, youBi, wenQu, wenChang, diJie, diKong,
        tianKui, tianYue, luCun, qingYang, tuoLuo,
        huoXing, lingXing, tianGuan, tianFuStar, tianChu,
        jieKong, xunKong, tianKongXing, tianMa, tianKu, tianXu,
        hongLuan, tianXi, guChen, guaSu, jieSha, daHao,
        feiLian, poSui, huaGai, xianChi, longDe, yueDe,
        tianDe, nianJie, tianCai, tianShou,
        longChi, fengGe, taiFu, fengGao, tianXing, tianYao,
        yueJie, tianWu, tianYueXing, yinSha,
        tianShang, tianShi, sanTai, baZuo, enGuang, tianGui,
        siHua, allStarMap, mingZhu, shenZhu,
        changShengTwelve, taiSuiTwelve, jiangQian, boShi,
        starBrightness, auxStarBrightness, daXian,
        panType: 'ren',
        solar: { year, month, day, hour, minute },
        effectiveLunarMonth,
        hourZhiIndex,
        gender
    };
}

async function getZiweiPaipan(year, month, day, hour, minute, gender, panType = 'tian') {
    if (panType === 'di') {
        return getZiweiDiPan(year, month, day, hour, minute, gender);
    }
    if (panType === 'ren') {
        return getZiweiRenPan(year, month, day, hour, minute, gender);
    }
    const eff = getEffectiveDate(year, month, day, hour);
    const dataMap = await fetchZiweiYearData(eff.year);
    const dayData = dataMap ? dataMap[eff.month + '-' + eff.day] : null;

    const lunarText = await getLunarText(year, month, day, hour);
    const siZhu = await getSiZhu(year, month, day, hour);

    let mingShen = { ming: '-', shen: '-' };
    let effectiveLunarMonth = null;
    const hourZhiIndex = Math.floor((hour + 1) / 2) % 12;
    if (dayData) {
        effectiveLunarMonth = getEffectiveLunarMonth(dayData, hour);
        mingShen = getMingShenGong(effectiveLunarMonth, hour);
    }

    const twelvePalaces = (mingShen.ming !== '-') ? getTwelvePalaces(mingShen.ming) : {};
    let gongGan = {};
    let wuXingJu = '-';
    let ziweiXing = null;
    let tianFuXing = null;
    let ziweiStarSystem = {};
    let tianFuStarSystem = {};
    let zuoFu = null;
    let youBi = null;
    let wenQu = null;
    let wenChang = null;
    let diJie = null;
    let diKong = null;
    let tianKui = null;
    let tianYue = null;
    let luCun = null;
    let qingYang = null;
    let tuoLuo = null;
    let huoXing = null;
    let lingXing = null;
    let tianGuan = null;
    let tianFuStar = null;
    let tianChu = null;
    let jieKong = null;
    let xunKong = null;
    let tianKongXing = null;
    let tianMa = null;
    let tianKu = null;
    let tianXu = null;
    let hongLuan = null;
    let tianXi = null;
    let guChen = null;
    let guaSu = null;
    let jieSha = null;
    let daHao = null;
    let feiLian = null;
    let poSui = null;
    let huaGai = null;
    let xianChi = null;
    let longDe = null;
    let yueDe = null;
    let tianDe = null;
    let nianJie = null;
    let tianCai = null;
    let tianShou = null;
    let longChi = null;
    let fengGe = null;
    let taiFu = null;
    let fengGao = null;
    let tianXing = null;
    let tianYao = null;
    let yueJie = null;
    let tianWu = null;
    let tianYueXing = null;
    let yinSha = null;
    let tianShang = null;
    let tianShi = null;
    let sanTai = null;
    let baZuo = null;
    let enGuang = null;
    let tianGui = null;
    let siHua = null;
    let allStarMap = null;
    let mingZhu = null;
    let shenZhu = null;
    let changShengTwelve = {};
    let taiSuiTwelve = {};
    let jiangQian = {};
    let boShi = {};
    let starBrightness = {};
    let auxStarBrightness = {};
    let daXian = {};
    if (siZhu.year && siZhu.year !== '-') {
        gongGan = getGongGan(siZhu.year.charAt(0));
        const mingGan = gongGan[mingShen.ming];
        if (mingGan && mingShen.ming !== '-') {
            wuXingJu = getWuXingJu(mingGan, mingShen.ming);
        }
        if (dayData && wuXingJu !== '-') {
            const lunarDayNum = parseInt(dayData.lunarDay, 10);
            const nianGan = siZhu.year.charAt(0);
            const nianZhi = siZhu.year.charAt(1);
            mingZhu = getMingZhu(nianZhi);
            shenZhu = getShenZhu(nianZhi);
            changShengTwelve = getChangShengTwelve(wuXingJu, gender, nianGan);
            taiSuiTwelve = getTaiSuiTwelve(nianZhi);
            jiangQian = getJiangQian(nianZhi);
            boShi = getBoShi(nianGan, gender);
            daXian = getDaXian(mingShen.ming, wuXingJu, nianGan, gender);
            ziweiXing = getZiweiXing(lunarDayNum, wuXingJu);
            tianFuXing = getTianFuXing(ziweiXing);
            ziweiStarSystem = getZiweiStarSystem(ziweiXing);
            tianFuStarSystem = getTianFuStarSystem(tianFuXing);
            zuoFu = getZuoFu(effectiveLunarMonth);
            youBi = getYouBi(effectiveLunarMonth);
            wenQu = getWenQu(hourZhiIndex);
            wenChang = getWenChang(hourZhiIndex);
            diJie = getDiJie(hourZhiIndex);
            diKong = getDiKong(hourZhiIndex);
            tianKui = getTianKui(nianGan);
            tianYue = getTianYue(nianGan);
            luCun = getLuCun(nianGan);
            qingYang = getQingYang(nianGan);
            tuoLuo = getTuoLuo(nianGan);
            huoXing = getHuoXing(nianZhi, hourZhiIndex);
            lingXing = getLingXing(nianZhi, hourZhiIndex);
            tianGuan = getTianGuan(nianGan);
            tianFuStar = getTianFu(nianGan);
            tianChu = getTianChu(nianGan);
            jieKong = getJieKong(nianGan);
            xunKong = getXunKong(nianGan, nianZhi);
            tianKongXing = getTianKongXing(nianZhi);
            tianMa = getTianMa(nianZhi);
            tianKu = getTianKu(nianZhi);
            tianXu = getTianXu(nianZhi);
            hongLuan = getHongLuan(nianZhi);
            tianXi = getTianXi(nianZhi);
            guChen = getGuChen(nianZhi);
            guaSu = getGuaSu(nianZhi);
            jieSha = getJieSha(nianZhi);
            daHao = getDaHao(nianZhi);
            feiLian = getFeiLian(nianZhi);
            poSui = getPoSui(nianZhi);
            huaGai = getHuaGai(nianZhi);
            xianChi = getXianChi(nianZhi);
            longDe = getLongDe(nianZhi);
            yueDe = getYueDe(nianZhi);
            tianDe = getTianDe(nianZhi);
            nianJie = getNianJie(nianZhi);
            tianCai = getTianCai(mingShen.ming, nianZhi);
            tianShou = getTianShou(mingShen.shen, nianZhi);
            longChi = getLongChi(nianZhi);
            fengGe = getFengGe(nianZhi);
            taiFu = getTaiFu(wenQu);
            fengGao = getFengGao(wenQu);
            tianXing = getTianXing(effectiveLunarMonth);
            tianYao = getTianYao(effectiveLunarMonth);
            yueJie = getYueJie(effectiveLunarMonth);
            tianWu = getTianWu(effectiveLunarMonth);
            tianYueXing = getTianYueXing(effectiveLunarMonth);
            yinSha = getYinSha(effectiveLunarMonth);
            tianShang = getTianShang(mingShen.ming, gender, nianGan);
            tianShi = getTianShi(mingShen.ming, gender, nianGan);
            sanTai = getSanTai(zuoFu, lunarDayNum);
            baZuo = getBaZuo(youBi, lunarDayNum);
            enGuang = getEnGuang(wenChang, lunarDayNum);
            tianGui = getTianGui(wenQu, lunarDayNum);
            allStarMap = { ...ziweiStarSystem, ...tianFuStarSystem };
            if (zuoFu) allStarMap['左辅'] = zuoFu;
            if (youBi) allStarMap['右弼'] = youBi;
            if (wenQu) allStarMap['文曲'] = wenQu;
            if (wenChang) allStarMap['文昌'] = wenChang;
            if (diJie) allStarMap['地劫'] = diJie;
            if (diKong) allStarMap['地空'] = diKong;
            if (tianKui) allStarMap['天魁'] = tianKui;
            if (tianYue) allStarMap['天钺'] = tianYue;
            if (luCun) allStarMap['禄存'] = luCun;
            if (qingYang) allStarMap['擎羊'] = qingYang;
            if (tuoLuo) allStarMap['陀罗'] = tuoLuo;
            if (huoXing) allStarMap['火星'] = huoXing;
            if (lingXing) allStarMap['铃星'] = lingXing;
            if (tianGuan) allStarMap['天官'] = tianGuan;
            if (tianFuStar) allStarMap['天福'] = tianFuStar;
            if (tianChu) allStarMap['天厨'] = tianChu;
            if (jieKong) allStarMap['截空'] = jieKong;
            if (xunKong) allStarMap['旬空'] = xunKong;
            if (tianKongXing) allStarMap['天空'] = tianKongXing;
            if (tianMa) allStarMap['天马'] = tianMa;
            if (tianKu) allStarMap['天哭'] = tianKu;
            if (tianXu) allStarMap['天虚'] = tianXu;
            if (hongLuan) allStarMap['红鸾'] = hongLuan;
            if (tianXi) allStarMap['天喜'] = tianXi;
            if (guChen) allStarMap['孤辰'] = guChen;
            if (guaSu) allStarMap['寡宿'] = guaSu;
            if (jieSha) allStarMap['劫杀'] = jieSha;
            if (daHao) allStarMap['大耗'] = daHao;
            if (feiLian) allStarMap['蜚廉'] = feiLian;
            if (poSui) allStarMap['破碎'] = poSui;
            if (huaGai) allStarMap['华盖'] = huaGai;
            if (xianChi) allStarMap['咸池'] = xianChi;
            if (longDe) allStarMap['龙德'] = longDe;
            if (yueDe) allStarMap['月德'] = yueDe;
            if (tianDe) allStarMap['天德'] = tianDe;
            if (nianJie) allStarMap['年解'] = nianJie;
            if (tianCai) allStarMap['天才'] = tianCai;
            if (tianShou) allStarMap['天寿'] = tianShou;
            if (longChi) allStarMap['龙池'] = longChi;
            if (fengGe) allStarMap['凤阁'] = fengGe;
            if (taiFu) allStarMap['台辅'] = taiFu;
            if (fengGao) allStarMap['封诰'] = fengGao;
            if (tianXing) allStarMap['天刑'] = tianXing;
            if (tianYao) allStarMap['天姚'] = tianYao;
            if (yueJie) allStarMap['月解'] = yueJie;
            if (tianWu) allStarMap['天巫'] = tianWu;
            if (tianYueXing) allStarMap['天月'] = tianYueXing;
            if (yinSha) allStarMap['阴煞'] = yinSha;
            if (tianShang) allStarMap['天伤'] = tianShang;
            if (tianShi) allStarMap['天使'] = tianShi;
            if (sanTai) allStarMap['三台'] = sanTai;
            if (baZuo) allStarMap['八座'] = baZuo;
            if (enGuang) allStarMap['恩光'] = enGuang;
            if (tianGui) allStarMap['天贵'] = tianGui;
            for (const [star, zhi] of Object.entries(allStarMap)) {
                if (mainStarBrightness[star]) {
                    starBrightness[star] = getStarBrightness(star, zhi);
                }
                if (auxStarBrightnessMap[star]) {
                    auxStarBrightness[star] = getAuxStarBrightness(star, zhi);
                }
            }
            siHua = getSiHua(nianGan, allStarMap);
        }
    }

    return {
        lunarText,
        siZhu,
        mingShen,
        twelvePalaces,
        gongGan,
        wuXingJu,
        ziweiXing,
        tianFuXing,
        ziweiStarSystem,
        tianFuStarSystem,
        zuoFu,
        youBi,
        wenQu,
        wenChang,
        diJie,
        diKong,
        tianKui,
        tianYue,
        luCun,
        qingYang,
        tuoLuo,
        huoXing,
        lingXing,
        tianGuan,
        tianFuStar,
        tianChu,
        jieKong,
        xunKong,
        tianKongXing,
        tianMa,
        tianKu,
        tianXu,
        hongLuan,
        tianXi,
        guChen,
        guaSu,
        jieSha,
        daHao,
        feiLian,
        poSui,
        huaGai,
        xianChi,
        longDe,
        yueDe,
        tianDe,
        nianJie,
        tianCai,
        tianShou,
        longChi,
        fengGe,
        taiFu,
        fengGao,
        tianXing,
        tianYao,
        yueJie,
        tianWu,
        tianYueXing,
        yinSha,
        tianShang,
        tianShi,
        sanTai,
        baZuo,
        enGuang,
        tianGui,
        siHua,
        allStarMap,
        mingZhu,
        shenZhu,
        changShengTwelve,
        taiSuiTwelve,
        jiangQian,
        boShi,
        starBrightness,
        auxStarBrightness,
        daXian,
        panType,
        solar: { year, month, day, hour, minute },
        effectiveLunarMonth,
        hourZhiIndex,
        gender
    };
}
