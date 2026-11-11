#!/usr/bin/env node
/**
 * dsh-ziwei-panel 本地桥服务（由宿主自动拉起，也可手动启动）
 *
 * 职责（路由表）：
 *   GET /                  → 插件 web\ziwei-panel.html（自检失败时顶部注入横幅）
 *   GET /lunar-data.js     → engineDir 同名文件（原版 html 相对引用，勿改 src）
 *   GET /ziwei-engine.js   → engineDir 同名文件
 *   GET /engine/<name>     → engineDir/<name>（basename 防穿越）
 *   /api/*                 → 盘 REST 桥（模拟原后端 API 契约）
 *
 * 桥硬规则：仅监听 127.0.0.1；CORS 全锁同源；三键过滤（birth/pan/saved_at）；
 *   原子写（tmp+rename）；覆盖前备份一代；DELETE 集合一律拒绝；saved_at 桥统一打点。
 * 分组（真分组状态层）：pans\.groups.json 桥私有（技能不读）；"默认分组"为隐式组
 *   （不进 groups 数组、禁删禁建，改名=成员整体迁移）；盘文件本体零触碰。
 * 盘主键：文件名=命主名（personName，唯一实体主键）；同名=同人=覆盖
 *   （覆盖前备份一代）；改名=原子重命名文件（id 同步变）；旧规约名 pan_*.json 只读兼容
 *   （列表照常，不再新生成）；保留名黑名单 README 禁 API 写删改名。
 *
 * stdin-EOF 自杀：宿主 spawn（pipe）父进程死亡 → stdin 'end' → 优雅退出；
 *   bat 手动模式（控制台 stdin）不会触发误退。
 *
 * 面板自检上送（v0.2.0）：POST /api/selfcheck 收页面固定
 *   schema 小 payload（≤4KB、checks ≤16 项，字段类型不符/解析失败一律 400）；
 *   origin 键服务端 sanitize（仅 [a-z0-9.-] 替 '-' 截 ≤40，非法/空 'unknown'，
 *   payload 不含任何路径成分），盖戳 plugin + version 后覆盖写
 *   healthcheck/<origin键>-dsh-ziwei-panel.json
 *   （UTF-8 无 BOM；目录经锚点推导）。版本口径：/api/version 的 version 字段
 *   与自检盖戳同源 = PLUGIN_VERSION（读插件 package.json，单一真源）。
 *
 * 前置：Node >= 18，零第三方依赖。技能包 engine/pans 目录只读引用，不复制不修改。
 */

'use strict';

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import http from 'node:http';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = path.resolve(__dirname, '..');
// 版本单一真源：/api/version 响应与自检盖戳同用此值
const PLUGIN_VERSION = JSON.parse(fs.readFileSync(path.join(PLUGIN_ROOT, 'package.json'), 'utf8')).version;

// 路径锚点加载器（realpath 上溯；不走静态相对 import 是因为经 junction 装载时相对基准落在别的盘，realpath 起点才稳）
function loadAnchors() {
    let dir = path.dirname(fs.realpathSync(fileURLToPath(import.meta.url)));
    for (let i = 0; i < 8; i++) {
        const c = path.join(dir, 'anchors.json');
        if (fs.existsSync(c)) return applyEnv(JSON.parse(fs.readFileSync(c, 'utf8')));
        const extDir = path.join(dir, 'extensions');
        const f = path.join(extDir, 'anchors.json');
        if (fs.existsSync(extDir) && fs.existsSync(f)) return applyEnv(JSON.parse(fs.readFileSync(f, 'utf8')));
        const parent = path.dirname(dir);
        if (parent === dir) break;
        dir = parent;
    }
    return null; // fail-soft：裸环境无 anchors.json 时回退包内相对路径
}
function applyEnv(raw) {
    for (const k of Object.keys(raw)) if (process.env[k] !== undefined) raw[k] = process.env[k];
    return raw;
}
const _A = loadAnchors() || {};

// ── 配置 ──
// engineDir/pansDir 缺省回退：优先 anchors（ZERO_ROOT 派生），裸环境用包内相对路径
// （../ziwei-analyze 与本插件同为 extensions 下资产，相对布局天然成立）
const ZIWEI_DIR = _A.ZERO_ROOT
    ? path.join(_A.ZERO_ROOT, 'extensions', 'skills', 'mystic-only', 'ziwei-analyze')
    : path.resolve(PLUGIN_ROOT, '..', 'ziwei-analyze');
const DEFAULTS = {
    port: 9871,
    engineDir: path.join(ZIWEI_DIR, 'engine'),
    pansDir: path.join(ZIWEI_DIR, 'pans'),
};
// 备份目录：裸环境（无 anchors）时禁用（null=不落备份），避免写仓外位置
const BACKUP_DIR = _A.ZERO_ROOT
    ? path.join(_A.ZERO_ROOT, '.dsh-tmp', 'ziwei-panel-backup')
    : null;
const BODY_LIMIT = 1024 * 1024;
// 自检上送安全面：小 payload 上限 + 检查项上限；报告目录锚点推导
// 裸环境无锚点时禁用自检落盘（null=收到即 503，不写仓外）
const SELFCHECK_DIR = _A.ZERO_ROOT
    ? path.join(_A.ZERO_ROOT, 'healthcheck', 'selfcheck')
    : null;
const SELFCHECK_BODY_LIMIT = 4096;
const SELFCHECK_MAX_CHECKS = 16;

function loadConfig() {
    const cfgPath = path.join(__dirname, 'bridge.config.json');
    const cfg = { ...DEFAULTS };
    try {
        const raw = JSON.parse(fs.readFileSync(cfgPath, 'utf-8'));
        for (const k of ['port', 'engineDir', 'pansDir']) {
            if (raw[k] !== undefined) cfg[k] = raw[k];
        }
    } catch (e) {
        console.warn(`[bridge] 配置读取失败（${cfgPath}），使用默认值: ${e.message}`);
    }
    if (!path.isAbsolute(cfg.engineDir)) cfg.engineDir = path.resolve(__dirname, cfg.engineDir);
    if (!path.isAbsolute(cfg.pansDir)) cfg.pansDir = path.resolve(__dirname, cfg.pansDir);
    return cfg;
}
const config = loadConfig();
const ENGINE_FILES = {
    'lunar-data.js': path.join(config.engineDir, 'lunar-data.js'),
    'ziwei-engine.js': path.join(config.engineDir, 'ziwei-engine.js'),
};
const WEB_INDEX = path.join(PLUGIN_ROOT, 'web', 'ziwei-panel.html');
const SELF_ORIGIN = `http://127.0.0.1:${config.port}`;

// ── 盘命名与校验（导出供单测） ──
// 主键=命主名（文件名 stem）；旧规约名 pan_*.json 为遗留格式，只读兼容不新生成
const NAME_ILLEGAL_RE = /[\\/:*?"<>|]/;
const NAME_MAX_LEN = 50;
const PROTECTED_STEMS = ['README']; // README.md=pans 目录说明文件，禁 API 写删

/** 命主名校验（保存/改名共用）：返回错误消息，合法返回 null */
function personNameError(raw) {
    if (typeof raw !== 'string' || raw === '') return '名字缺失（personName 必填）';
    if (raw !== raw.trim()) return '名字首尾不得含空格';
    if (raw.length > NAME_MAX_LEN) return `名字长度超过 ${NAME_MAX_LEN}`;
    if (NAME_ILLEGAL_RE.test(raw)) return '名字含 Windows 非法字符（\\/:*?"<>|）';
    const low = raw.toLowerCase();
    if (PROTECTED_STEMS.some((s) => s.toLowerCase() === low)) return '保留名禁止写入（README）';
    return null;
}

function isProtectedStem(stem) {
    const low = String(stem).toLowerCase();
    return PROTECTED_STEMS.some((s) => s.toLowerCase() === low);
}

/** 生辰九字段合法性校验（仅验字段，不再派生文件名）；非法返回 null */
function validateBirthFields(birth) {
    const g = normalizeGender(birth && birth.gender);
    if (!g) return null;
    const { year, month, day, hour, minute } = birth || {};
    const parts = { year, month, day, hour, minute };
    for (const [k, v] of Object.entries(parts)) {
        if (!Number.isInteger(v) || v < 0) return null;
    }
    if (year > 9999 || month < 1 || month > 12 || day < 1 || day > 31 ||
        hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
    return true;
}

/** gender 归一化：male/female 直通，男/女映射，其余 null */
function normalizeGender(v) {
    if (v === 'male' || v === 'female') return v;
    if (v === '男') return 'male';
    if (v === '女') return 'female';
    return null;
}

/** panType 校验：tian/di/ren（缺省 tian），其余 null */
function normalizePanType(v) {
    if (v === undefined || v === null || v === '') return 'tian';
    if (v === 'tian' || v === 'di' || v === 'ren') return v;
    return null;
}

/** 三键白名单过滤：只保留 birth/pan/saved_at，其余字段一律丢弃 */
function pickPanFileContent(obj) {
    if (!obj || typeof obj !== 'object') return null;
    const out = {};
    for (const k of ['birth', 'pan', 'saved_at']) {
        if (obj[k] !== undefined) out[k] = obj[k];
    }
    return out;
}

/** 盘文件数据 → 列表行（生辰取 birth，label=文件名 stem，createdAt=saved_at） */
function deriveListRow(stem, fileData, groupName) {
    const birth = (fileData && fileData.birth) || {};
    return {
        id: stem,
        chartName: stem,
        createdAt: fileData && fileData.saved_at !== undefined ? fileData.saved_at : '',
        panType: birth.panType !== undefined ? birth.panType : 'tian',
        personName: stem,
        gender: birth.gender !== undefined ? birth.gender : '',
        birthYear: birth.year,
        birthMonth: birth.month,
        birthDay: birth.day,
        birthHour: birth.hour,
        birthMinute: birth.minute,
        groupName: groupName || DEFAULT_GROUP,
    };
}

// ── 分组状态层（pans\.groups.json 桥私有；默认分组为隐式组，不进 groups 数组） ──
const DEFAULT_GROUP = '默认分组';
let groupsCache = null; // null=未加载；加载后为 { groups: [..], membership: { stem: groupName } }

function groupsFilePath() {
    return path.join(config.pansDir, '.groups.json');
}

function loadGroups() {
    if (groupsCache) return groupsCache;
    try {
        const raw = JSON.parse(fs.readFileSync(groupsFilePath(), 'utf-8'));
        groupsCache = {
            groups: Array.isArray(raw.groups) ? raw.groups.filter((g) => typeof g === 'string' && g !== DEFAULT_GROUP) : [],
            membership: (raw.membership && typeof raw.membership === 'object') ? raw.membership : {},
        };
    } catch {
        groupsCache = { groups: [], membership: {} }; // 文件缺失/损坏=空状态
    }
    return groupsCache;
}

function persistGroups() {
    atomicWrite(groupsFilePath(), JSON.stringify(loadGroups(), null, 2));
}

/** 分组名校验：复用盘名校验规则；默认分组为保留名（隐式组，禁建禁作新名） */
function groupNameError(raw) {
    if (typeof raw !== 'string' || raw === '') return '分组名缺失（groupName 必填）';
    if (raw !== raw.trim()) return '分组名首尾不得含空格';
    if (raw.length > NAME_MAX_LEN) return `分组名长度超过 ${NAME_MAX_LEN}`;
    if (NAME_ILLEGAL_RE.test(raw)) return '分组名含 Windows 非法字符（\\/:*?"<>|）';
    if (raw === DEFAULT_GROUP) return `"${DEFAULT_GROUP}" 为系统保留分组名`;
    return null;
}

// ── vm 排盘引擎（同 paipan.js 沙箱用法，懒加载缓存） ──
let engineSandbox = null;

function getEngine() {
    if (engineSandbox) return engineSandbox;
    for (const f of Object.values(ENGINE_FILES)) {
        if (!fs.existsSync(f)) throw new Error(`engine 缺失: ${f}`);
    }
    const sandbox = {
        console: { log: () => {}, error: console.error, warn: console.warn },
        // 现役引擎在 1900-2099 内嵌表范围内不会发起任何网络请求；
        // fetch 兜底 reject，防止超范围时静默失败（同 paipan.js）
        fetch: () => Promise.reject(new Error('离线模式：生日超出 1900-2099 内嵌农历数据范围，无法排盘。')),
        setTimeout, clearTimeout, setInterval, clearInterval,
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(ENGINE_FILES['lunar-data.js'], 'utf-8'), sandbox, { filename: 'lunar-data.js' });
    vm.runInContext(fs.readFileSync(ENGINE_FILES['ziwei-engine.js'], 'utf-8'), sandbox, { filename: 'ziwei-engine.js' });
    if (typeof sandbox.getZiweiPaipan !== 'function') throw new Error('引擎加载后未找到 getZiweiPaipan 入口');
    engineSandbox = sandbox;
    return sandbox;
}

async function paipanViaVm(birth) {
    const { getZiweiPaipan } = getEngine();
    const result = await getZiweiPaipan(
        birth.year, birth.month, birth.day, birth.hour, birth.minute, birth.gender, birth.panType);
    if (!result || !result.twelvePalaces) {
        throw new Error('排盘失败：引擎返回空结果（请检查生辰是否在 1900-2099 范围内）');
    }
    return result;
}

// ── 自检（engineDir 两文件 + pansDir） ──
function checkEnv() {
    const missing = [];
    for (const [name, f] of Object.entries(ENGINE_FILES)) {
        if (!fs.existsSync(f)) missing.push(`${name}（${f}）`);
    }
    if (!fs.existsSync(config.pansDir)) missing.push(`pansDir（${config.pansDir}）`);
    return { ok: missing.length === 0, missing };
}

// ── 文件工具 ──
function atomicWrite(target, content) {
    const tmp = path.join(path.dirname(target), `.${path.basename(target)}.tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
    fs.writeFileSync(tmp, content, 'utf-8');
    fs.renameSync(tmp, target);
}

function backupOnce(filename) {
    if (!BACKUP_DIR) return; // 裸环境（无 anchors）禁用备份
    fs.mkdirSync(BACKUP_DIR, { recursive: true });
    fs.copyFileSync(path.join(config.pansDir, filename), path.join(BACKUP_DIR, filename));
}

/** 保存盘（upsert by name）：文件名=personName；同名=同人=覆盖（覆盖前备份一代） */
function savePanFile(personName, birth, pan) {
    const filename = `${personName}.json`;
    const target = path.join(config.pansDir, filename);
    if (fs.existsSync(target)) backupOnce(filename);
    const record = { birth, pan, saved_at: new Date().toLocaleString('zh-CN', { hour12: false }) };
    atomicWrite(target, JSON.stringify(record, null, 2));
    return { stem: personName, record };
}

/** 列举盘 stem：任何 *.json（README.md 与隐藏文件除外；旧规约名 pan_*.json 照常列出） */
function listPanStems() {
    const out = [];
    for (const name of fs.readdirSync(config.pansDir)) {
        if (name.endsWith('.json') && !name.startsWith('.')) out.push(name.slice(0, -5));
    }
    out.sort();
    return out;
}

// ── HTTP 工具 ──
function sendJson(res, status, obj, extraHeaders) {
    const body = JSON.stringify(obj);
    res.writeHead(status, {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
        ...extraHeaders,
    });
    res.end(body);
}

// DELETE 集合（无 id = 清空全部盘）一律拒绝
const CLEAR_ALL_REJECT = Object.freeze({ status: 403, body: { success: false, message: '本地模式禁用清空' } });

const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
};

function sendFile(res, filePath) {
    const ext = path.extname(filePath).toLowerCase();
    const data = fs.readFileSync(filePath);
    res.writeHead(200, {
        'Content-Type': MIME[ext] || 'application/octet-stream',
        'Cache-Control': 'no-cache',
    });
    res.end(data);
}

function readBody(req, limit = BODY_LIMIT, hardAbort = true) {
    return new Promise((resolve, reject) => {
        let size = 0;
        let over = false; // 已超限：大上限(1MB档)硬断保护；小上限端点排干后由调用方回 400
        const chunks = [];
        req.on('data', (c) => {
            if (over) return;
            size += c.length;
            if (size > limit) {
                over = true;
                if (hardAbort) {
                    reject(new Error('请求体过大'));
                    req.destroy();
                } else {
                    req.resume(); // 排干剩余分块，待 end 判拒——未排干就应答会被 Node 重置连接
                }
                return;
            }
            chunks.push(c);
        });
        req.on('end', () => {
            if (over) return reject(new Error('请求体过大'));
            const raw = Buffer.concat(chunks).toString('utf-8');
            if (!raw) return resolve({});
            try { resolve(JSON.parse(raw)); }
            catch { reject(new Error('请求体不是合法 JSON')); }
        });
        req.on('error', reject);
    });
}

/** 写操作 CSRF 防护：Origin/Referer 为空（非浏览器/curl）放行；非空时须为本机回环家族
 *  （http://127.0.0.1:任意端口）——宿主代理转发浏览器写请求时透传 Origin（:3080 等），
 *  本机回环任意端口同属可信圈；非本机 origin（如 https://evil.com）仍拒绝。 */
function isWriteAllowed(req) {
    const LOOPBACK_ORIGIN_RE = /^http:\/\/127\.0\.0\.1:\d+$/;
    const origin = req.headers.origin;
    if (origin !== undefined && origin !== '') return LOOPBACK_ORIGIN_RE.test(origin);
    const referer = req.headers.referer;
    if (referer !== undefined && referer !== '') {
        try { return LOOPBACK_ORIGIN_RE.test(new URL(referer).origin); }
        catch { return false; }
    }
    return true;
}

// ── 面板自检上送（v0.2.0）──
// origin 键 sanitize：仅 [a-z0-9.-]（其余替 '-'），截断 ≤40，非法/空用
// 'unknown'——文件名成分不信任客户端输入，路径全服务端派生。
function sanitizeOriginKey(origin) {
    if (typeof origin !== 'string') return 'unknown';
    const key = origin.toLowerCase().replace(/[^a-z0-9.-]/g, '-').slice(0, 40);
    return key.length > 0 ? key : 'unknown';
}

function selfcheckBad(message) {
    return { status: 400, body: { success: false, message } };
}

/** POST /api/selfcheck：固定 schema 校验（不符一律 400）→ 盖戳 → 覆盖写报告 */
async function handleSelfcheckPost(req) {
    let body;
    try {
        body = await readBody(req, SELFCHECK_BODY_LIMIT, false);
    } catch (e) {
        return selfcheckBad(`payload 拒收（须为 ≤4KB 的合法 JSON）: ${e.message}`);
    }
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
        return selfcheckBad('payload 必须为对象 {origin, ts, checks}');
    }
    if (typeof body.origin !== 'string') return selfcheckBad('origin 必须为字符串');
    if (typeof body.ts !== 'number' || !Number.isFinite(body.ts)) return selfcheckBad('ts 必须为有限数字');
    if (!Array.isArray(body.checks)) return selfcheckBad('checks 必须为数组');
    if (body.checks.length > SELFCHECK_MAX_CHECKS) return selfcheckBad(`checks 超过 ${SELFCHECK_MAX_CHECKS} 项上限`);
    for (const c of body.checks) {
        if (c === null || typeof c !== 'object' || Array.isArray(c)) return selfcheckBad('check 条目必须为对象 {name, ok, detail}');
        if (typeof c.name !== 'string' || c.name === '') return selfcheckBad('check.name 必须为非空字符串');
        if (typeof c.ok !== 'boolean') return selfcheckBad('check.ok 必须为布尔');
        if (typeof c.detail !== 'string') return selfcheckBad('check.detail 必须为字符串');
    }
    if (!SELFCHECK_DIR) return { status: 503, body: { success: false, message: 'selfcheck 落盘未启用（无锚点环境）' } };
    const report = {
        plugin: 'dsh-ziwei-panel',
        version: PLUGIN_VERSION,
        origin: body.origin,
        ts: body.ts,
        checks: body.checks,
    };
    fs.mkdirSync(SELFCHECK_DIR, { recursive: true });
    atomicWrite(
        path.join(SELFCHECK_DIR, `${sanitizeOriginKey(body.origin)}-dsh-ziwei-panel.json`),
        JSON.stringify(report, null, 2)
    );
    return { status: 200, body: { success: true } };
}

// ── /api 处理器 ──
function handleVersion() {
    const engine = {};
    for (const [name, f] of Object.entries(ENGINE_FILES)) {
        try {
            const st = fs.statSync(f);
            const sha8 = crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex').slice(0, 8);
            engine[name] = { mtime: st.mtime.toISOString(), sha256_8: sha8 };
        } catch {
            engine[name] = null;
        }
    }
    return { name: 'dsh-ziwei-panel-bridge', version: PLUGIN_VERSION, engine, pansDir: config.pansDir };
}

function handleListCharts() {
    const g = loadGroups();
    const rows = [];
    for (const stem of listPanStems()) {
        const filePath = path.join(config.pansDir, `${stem}.json`);
        let data;
        try {
            data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        } catch {
            continue; // 坏文件跳过，列表不炸
        }
        rows.push(deriveListRow(stem, data, g.membership[stem]));
    }
    return { success: true, data: rows };
}

async function handleCreateChart(body) {
    const nameErr = personNameError(body && body.personName);
    if (nameErr) return { status: 400, body: { success: false, message: nameErr } };
    const birth = extractBirth(body);
    if (!birth) return { status: 400, body: { success: false, message: '生辰九字段（gender+birthYear..birthMinute）缺失或非法' } };
    let pan;
    try {
        pan = await paipanViaVm(birth);
    } catch (e) {
        return { status: 400, body: { success: false, message: e.message || String(e) } };
    }
    const { stem } = savePanFile(body.personName, birth, pan);
    // 存盘带 groupName：组存在则登记 membership；不存在（含默认分组）忽略归默认，不卡存盘
    if (typeof body.groupName === 'string' && body.groupName !== DEFAULT_GROUP) {
        const g = loadGroups();
        if (g.groups.includes(body.groupName)) {
            g.membership[stem] = body.groupName;
            persistGroups();
        }
    }
    return { status: 200, body: { success: true, data: { id: stem } } };
}

async function handleUpdateChart(id, body) {
    if (typeof id !== 'string' || id === '' || NAME_ILLEGAL_RE.test(id) || id.includes('..')) {
        return { status: 400, body: { success: false, message: '非法盘 id' } };
    }
    if (isProtectedStem(id)) return { status: 403, body: { success: false, message: '保留名禁止 API 修改（README）' } };
    const oldFile = path.join(config.pansDir, `${id}.json`);
    if (!fs.existsSync(oldFile)) return { status: 404, body: { success: false, message: '盘不存在' } };

    // 仅带 groupName（拖组移动）：纯状态层更新，盘文件不动
    if (body && typeof body.personName !== 'string' && typeof body.groupName === 'string') {
        const g = loadGroups();
        if (body.groupName === DEFAULT_GROUP) {
            delete g.membership[id]; // 移回默认=清除登记
        } else if (!g.groups.includes(body.groupName)) {
            return { status: 400, body: { success: false, message: `分组 "${body.groupName}" 不存在` } };
        } else {
            g.membership[id] = body.groupName;
        }
        persistGroups();
        return { status: 200, body: { success: true, data: { id } } };
    }

    const nameErr = personNameError(body && body.personName);
    if (nameErr) return { status: 400, body: { success: false, message: nameErr } };
    const newStem = body.personName;

    if (extractBirth(body)) {
        // 带生辰 = 重新排盘 upsert（新名落盘，id 与旧名不同时删除旧文件）；分组登记跟人走
        const result = await handleCreateChart(body);
        if (!result.body.success) return result;
        if (newStem !== id) {
            // create 已按 groupName 登记新键时只清旧键，否则登记随人迁移
            const g = loadGroups();
            if (g.membership[newStem] !== undefined && g.membership[newStem] !== g.membership[id]) {
                delete g.membership[id];
                persistGroups();
            } else {
                moveMembership(id, newStem);
            }
        }
        return result;
    }

    // 只带姓名 = 改名：原子重命名文件（id 同步变）；目标同名=同人=覆盖（备份一代）
    if (newStem === id) return { status: 200, body: { success: true, data: { id: newStem } } };
    const newFile = path.join(config.pansDir, `${newStem}.json`);
    if (fs.existsSync(newFile)) {
        backupOnce(`${newStem}.json`);
        fs.copyFileSync(oldFile, newFile);
        fs.unlinkSync(oldFile);
    } else {
        fs.renameSync(oldFile, newFile);
    }
    moveMembership(id, newStem);
    return { status: 200, body: { success: true, data: { id: newStem } } };
}

/** 盘改名时分组登记键跟随（无登记则无操作） */
function moveMembership(oldStem, newStem) {
    const g = loadGroups();
    if (g.membership[oldStem] === undefined) return;
    g.membership[newStem] = g.membership[oldStem];
    delete g.membership[oldStem];
    persistGroups();
}

function handleDeleteChart(id) {
    if (typeof id !== 'string' || id === '' || NAME_ILLEGAL_RE.test(id) || id.includes('..')) {
        return { status: 400, body: { success: false, message: '非法盘 id' } };
    }
    if (isProtectedStem(id)) return { status: 403, body: { success: false, message: '保留名禁止 API 删除（README）' } };
    const target = path.join(config.pansDir, `${id}.json`);
    if (!fs.existsSync(target)) return { status: 404, body: { success: false, message: '盘不存在' } };
    fs.unlinkSync(target);
    const g = loadGroups();
    if (g.membership[id] !== undefined) {
        delete g.membership[id];
        persistGroups();
    }
    return { status: 200, body: { success: true } };
}

/** POST/PUT body 生辰九字段 → 规范 birth 对象（panType 用请求值，gender 映射 male/female）；非法返回 null */
function extractBirth(body) {
    if (!body || typeof body !== 'object') return null;
    const gender = normalizeGender(body.gender);
    const panType = normalizePanType(body.panType);
    if (!gender || !panType) return null;
    const birth = {
        year: body.birthYear, month: body.birthMonth, day: body.birthDay,
        hour: body.birthHour, minute: body.birthMinute,
        gender, panType,
    };
    return validateBirthFields(birth) ? birth : null;
}

async function handleApi(req, res, pathname) {
    // 探活端点 CORS：客户端 bundle 从 DSH 页面源(127.0.0.1:3080)跨源 fetch 探活，仅此端点放行精确源
    if (pathname === '/api/version') {
        const origin = req.headers.origin;
        if (origin === 'http://127.0.0.1:3080') {
            if (req.method === 'OPTIONS') {
                res.writeHead(204, {
                    'Access-Control-Allow-Origin': 'http://127.0.0.1:3080',
                    'Access-Control-Allow-Methods': 'GET',
                });
                return res.end();
            }
            if (req.method === 'GET') {
                return sendJson(res, 200, handleVersion(), {
                    'Access-Control-Allow-Origin': 'http://127.0.0.1:3080',
                    'Access-Control-Allow-Methods': 'GET',
                });
            }
        }
    }
    // POST /api/selfcheck（面板自检上送）：置于写源校验与懒自检 503 之前——
    // 桥环境损坏时报告更要能落地；安全面=固定 schema 小 payload + 服务端
    // sanitize + 路径全服务端派生，文件只落 selfcheck 报告目录。
    if (pathname === '/api/selfcheck') {
        if (req.method !== 'POST') return sendJson(res, 405, { success: false, message: 'method not allowed' });
        const r = await handleSelfcheckPost(req);
        return sendJson(res, r.status, r.body);
    }
    if (['POST', 'PUT', 'DELETE'].includes(req.method) && !isWriteAllowed(req)) {
        return sendJson(res, 403, { success: false, message: '跨源写请求已拒绝（仅同源 127.0.0.1）' });
    }

    // 懒自检：engine 两文件 + pansDir 缺失 → /api/* 一律 503
    const env = checkEnv();
    if (!env.ok) {
        return sendJson(res, 503, { success: false, message: `桥自检失败，缺少: ${env.missing.join('；')}` });
    }

    const parts = pathname.split('/').filter(Boolean); // ['api', ...]
    const rest = parts.slice(1);
    let id = null;
    if (rest[0] === 'ziwei-charts' && rest.length > 1) {
        try { id = decodeURIComponent(rest[1]); } catch { id = rest[1]; }
    }

    try {
        // GET /api/version（跨源放行已在函数首处理；此处兜同源 GET）
        if (req.method === 'GET' && pathname === '/api/version') {
            return sendJson(res, 200, handleVersion());
        }
        // /api/ziwei-charts（集合）
        if (rest[0] === 'ziwei-charts' && rest.length === 1) {
            if (req.method === 'GET') return sendJson(res, 200, handleListCharts());
            if (req.method === 'POST') {
                const r = await handleCreateChart(await readBody(req));
                return sendJson(res, r.status, r.body);
            }
            if (req.method === 'DELETE') {
                return sendJson(res, CLEAR_ALL_REJECT.status, CLEAR_ALL_REJECT.body);
            }
            return sendJson(res, 405, { success: false, message: 'method not allowed' });
        }
        // PUT /api/ziwei-charts/order（排序映射：空操作）
        if (rest[0] === 'ziwei-charts' && rest[1] === 'order' && req.method === 'PUT') {
            await readBody(req);
            return sendJson(res, 200, { success: true });
        }
        // /api/ziwei-charts/{id}
        if (rest[0] === 'ziwei-charts' && id !== null) {
            if (req.method === 'PUT') {
                const r = await handleUpdateChart(id, await readBody(req));
                return sendJson(res, r.status, r.body);
            }
            if (req.method === 'DELETE') {
                const r = handleDeleteChart(id);
                return sendJson(res, r.status, r.body);
            }
            return sendJson(res, 405, { success: false, message: 'method not allowed' });
        }
        // /api/user（登录墙旁路：恒已登录本地用户）
        if (rest[0] === 'user' && rest.length === 1) {
            if (req.method === 'GET') return sendJson(res, 200, { success: true });
            if (req.method === 'PUT') { await readBody(req); return sendJson(res, 200, { success: true }); }
            return sendJson(res, 405, { success: false, message: 'method not allowed' });
        }
        // /api/ziwei-chart-groups（真分组 CRUD，状态层=.groups.json；默认分组为隐式组）
        if (rest[0] === 'ziwei-chart-groups') {
            let gName = null;
            if (rest.length > 1) {
                try { gName = decodeURIComponent(rest[1]); } catch { gName = rest[1]; }
            }
            if (req.method === 'GET' && rest.length === 1) {
                return sendJson(res, 200, { success: true, data: loadGroups().groups.slice() });
            }
            if (req.method === 'POST' && rest.length === 1) {
                const body = await readBody(req);
                if (body.groupName === DEFAULT_GROUP) {
                    // 前端重命名默认分组前 POST 确保存在：隐式组恒存在，幂等成功
                    return sendJson(res, 200, { success: true });
                }
                const err = groupNameError(body.groupName);
                if (err) return sendJson(res, 400, { success: false, message: err });
                const g = loadGroups();
                if (g.groups.includes(body.groupName)) {
                    return sendJson(res, 400, { success: false, message: `分组 "${body.groupName}" 已存在` });
                }
                g.groups.push(body.groupName);
                persistGroups();
                return sendJson(res, 200, { success: true });
            }
            if (req.method === 'PUT' && gName !== null) {
                const body = await readBody(req);
                const err = groupNameError(body.newName);
                if (err) return sendJson(res, 400, { success: false, message: err });
                const g = loadGroups();
                if (gName !== DEFAULT_GROUP && !g.groups.includes(gName)) {
                    return sendJson(res, 404, { success: false, message: `分组 "${gName}" 不存在` });
                }
                if (g.groups.includes(body.newName)) {
                    return sendJson(res, 400, { success: false, message: `分组 "${body.newName}" 已存在` });
                }
                if (gName === DEFAULT_GROUP) {
                    // 默认分组改名：所有未登记/登记为默认的盘整体迁入新组，新组顶替注册
                    for (const stem of listPanStems()) {
                        if (g.membership[stem] === undefined || g.membership[stem] === DEFAULT_GROUP) {
                            g.membership[stem] = body.newName;
                        }
                    }
                    g.groups.push(body.newName);
                } else {
                    g.groups[g.groups.indexOf(gName)] = body.newName;
                    for (const stem of Object.keys(g.membership)) {
                        if (g.membership[stem] === gName) g.membership[stem] = body.newName;
                    }
                }
                persistGroups();
                return sendJson(res, 200, { success: true });
            }
            if (req.method === 'DELETE' && gName !== null) {
                await readBody(req);
                if (gName === DEFAULT_GROUP) {
                    return sendJson(res, 403, { success: false, message: `"${DEFAULT_GROUP}" 不允许删除` });
                }
                const g = loadGroups();
                const idx = g.groups.indexOf(gName);
                if (idx === -1) return sendJson(res, 404, { success: false, message: `分组 "${gName}" 不存在` });
                g.groups.splice(idx, 1);
                for (const stem of Object.keys(g.membership)) {
                    if (g.membership[stem] === gName) delete g.membership[stem]; // 成员归默认
                }
                persistGroups();
                return sendJson(res, 200, { success: true });
            }
            return sendJson(res, 405, { success: false, message: 'method not allowed' });
        }
        return sendJson(res, 404, { success: false, message: 'unknown endpoint' });
    } catch (e) {
        return sendJson(res, 400, { success: false, message: e.message || String(e) });
    }
}

// ── 静态路由 ──
function serveIndex(res) {
    let html;
    try {
        html = fs.readFileSync(WEB_INDEX, 'utf-8');
    } catch {
        res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end(`前端文件缺失: ${WEB_INDEX}`);
    }
    const env = checkEnv();
    if (!env.ok) {
        const banner = `<div style="background:#c0392b;color:#fff;padding:10px 14px;font-size:14px;">` +
            `dsh-ziwei-panel 桥自检失败，缺少：${env.missing.join('；')}（排盘与盘列表不可用，请检查技能包 mystic-only\\ziwei-analyze 是否就位）</div>`;
        html = /<body[^>]*>/i.test(html)
            ? html.replace(/<body[^>]*>/i, (m) => m + banner)
            : banner + html;
    }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
    res.end(html);
}

function serveStatic(res, pathname) {
    let filePath = null;
    if (pathname === '/') return serveIndex(res);
    if (pathname === '/lunar-data.js' || pathname === '/ziwei-engine.js') {
        filePath = ENGINE_FILES[pathname.slice(1)];
    } else if (pathname.startsWith('/engine/')) {
        const name = path.basename(pathname); // 防目录穿越
        filePath = path.join(config.engineDir, name);
    }
    if (filePath && fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        return sendFile(res, filePath);
    }
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('not found');
}

// ── 主流程 ──
let server = null;

function main() {
    server = http.createServer((req, res) => {
        let pathname;
        try {
            pathname = new URL(req.url, SELF_ORIGIN).pathname;
        } catch {
            res.writeHead(400); return res.end('bad request');
        }
        if (pathname === '/api' || pathname.startsWith('/api/')) {
            handleApi(req, res, pathname).catch((e) => {
                try { sendJson(res, 500, { success: false, message: e.message || String(e) }); }
                catch { /* 已应答 */ }
            });
            return;
        }
        serveStatic(res, pathname);
    });

    server.on('error', (e) => {
        if (e.code === 'EADDRINUSE') {
            console.error(`[bridge] 端口 ${config.port} 已被占用（可能已有桥实例在跑）。退出；如需复用请先探活 http://127.0.0.1:${config.port}/api/version`);
            process.exit(1);
        }
        console.error(`[bridge] 后端错误:`, e);
    });

    server.listen(config.port, '127.0.0.1', () => {
        const env = checkEnv();
        console.log(`[bridge] dsh-ziwei-panel-bridge ${PLUGIN_VERSION} 监听 http://127.0.0.1:${config.port}`);
        console.log(`[bridge] engineDir=${config.engineDir}`);
        console.log(`[bridge] pansDir=${config.pansDir}`);
        console.log(`[bridge] 自检: ${env.ok ? 'OK' : `缺失 ${env.missing.join('；')}（/api 返回 503，首页显示横幅）`}`);
        console.log(`[bridge] 手动停止: Ctrl+C 或关窗；宿主 spawn 模式下父进程退出即自动退出（stdin-EOF）`);
    });

    // stdin-EOF 自杀（宿主拉起模式；手动控制台模式不触发）
    process.stdin.on('end', () => gracefulShutdown('stdin EOF（父进程已关闭）'));
    process.stdin.on('close', () => gracefulShutdown('stdin closed'));
    process.stdin.resume();
    process.on('SIGINT', () => gracefulShutdown('SIGINT'));
    process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
}

let shuttingDown = false;
function gracefulShutdown(reason) {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`[bridge] 退出（${reason}）`);
    if (server) server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 1500).unref();
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) main();

// 纯函数导出（单测用，不触发服务）
export {
    NAME_ILLEGAL_RE, NAME_MAX_LEN, PROTECTED_STEMS,
    personNameError, isProtectedStem,
    validateBirthFields, normalizeGender, normalizePanType,
    pickPanFileContent, deriveListRow, extractBirth,
    CLEAR_ALL_REJECT, handleDeleteChart,
};
