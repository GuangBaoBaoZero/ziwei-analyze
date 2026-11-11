// dsh-ziwei-panel — host half.
//
// 期3 转正：apply() 自动拉起本地桥（bin/bridge.mjs，端口见 bin/bridge.config.json）。
// 桌面端兼容：经官方 webServer 公开面注册 prefix 反代路由
// /plugins/dsh-ziwei-panel → 本地桥——面板不再直连回环端口（Electron 桌面端
// 拦应用层直连本地端口），Web/桌面端统一同源走宿主路由。路由风格与官方
// dsh-client-modules 的 /plugins bundle 路由一致（最长前缀优先，不冲突）。
// 桥子进程管理不变——唯一副作用 = 桥子进程 + 一条反代路由，
// 全部逻辑围绕它的生灭：
//   - 复用判据：apply 先探 /api/version（2s 超时），
//     应答 JSON name === 'dsh-ziwei-panel-bridge' = 已有实例在跑，不 spawn；
//     误判漏网由桥自身 EADDRINUSE 退出兜底，不会真双起。
//   - stdin-EOF 自杀：stdio[0] = 'pipe' 且全程不写不 end——DSH
//     进程死 = 管道断 = 桥 stdin 'end' 自退；清理函数（DSH 正常卸载路径）
//     主动 stdin.end() + kill 双保险。
//   - 非预期退出（spawn error 或 exit code !== 0；stdin-EOF 路径桥经
//     gracefulShutdown 自退 code=0，不算）：3s 后重试 spawn 一次，再败
//     console.warn 放弃——warn 附 stdout/stderr 环形缓冲尾部 4KB 助诊。
//   - env 白名单（PATH/SYSTEMROOT/USERPROFILE/SYSTEMDRIVE/TEMP/APPDATA，
//     大小写不敏感匹配）：不继承 DSH 全量环境。

import { spawn } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 端口唯一真源 = bin/bridge.config.json（桥 bin/bridge.mjs 的 loadConfig 读同
// 一文件，同值兜底 9871）——代理目标与探活 URL 均从此派生，改端口只动一处。
const CONFIG_PATH = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"../bin/bridge.config.json"
);
const DEFAULT_PORT = 9871;

function bridgePort() {
	try {
		const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
		if (Number.isInteger(cfg.port) && cfg.port > 0) return cfg.port;
	} catch { /* 缺文件/坏 JSON 走默认，与桥的兜底同值 */ }
	return DEFAULT_PORT;
}

const PORT = bridgePort();
const BRIDGE_HOST = "127.0.0.1";
const BRIDGE_NAME = "dsh-ziwei-panel-bridge";
const PROXY_PATH = "/plugins/dsh-ziwei-panel";
const PROBE_TIMEOUT_MS = 2000;
const RETRY_DELAY_MS = 3000;
const RING_LIMIT = 4096;

const BRIDGE_PATH = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"../bin/bridge.mjs"
);

const ENV_KEEP = new Set(["PATH", "SYSTEMROOT", "USERPROFILE", "SYSTEMDRIVE", "TEMP", "APPDATA"]);

function minimalEnv() {
	const env = {};
	for (const key of Object.keys(process.env)) {
		if (ENV_KEEP.has(key.toUpperCase())) env[key] = process.env[key];
	}
	return env;
}

function isBridgeRunning() {
	const ctrl = new AbortController();
	const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
	return fetch(`http://${BRIDGE_HOST}:${PORT}/api/version`, { signal: ctrl.signal })
		.then((res) => (res.ok ? res.json() : null))
		.then((body) => body !== null && body.name === BRIDGE_NAME)
		.catch(() => false)
		.finally(() => clearTimeout(timer));
}

// 反向代理：宿主半经官方 webServer prefix 路由收请求（req.url = 含
// PROXY_PATH 前缀的原始全路径），剥前缀后转发本地桥；method/headers/body
// 流透传，响应状态码/headers/body 流原样回传（支持流式）。桥不可达 = 502
// JSON（面板探活以 502 判"桥未起"）。host 头改写为桥地址，其余原样。
// 导出供离线单测直调（宿主只消费 apply/inject）。
export function createProxyHandler(prefix, port, host = "127.0.0.1") {
	return function proxy(req, res) {
		let target;
		try {
			target = new URL(req.url ?? "/", `http://${host}:${port}`);
		} catch {
			res.writeHead(400).end();
			return;
		}
		const suffix = target.pathname.slice(prefix.length) || "/";
		const headers = { ...req.headers, host: `${host}:${port}` };
		const upstream = http.request(
			{ hostname: host, port, method: req.method, path: suffix + target.search, headers },
			(up) => {
				res.writeHead(up.statusCode ?? 502, up.headers);
				up.pipe(res);
			}
		);
		upstream.on("error", () => {
			if (res.headersSent) {
				res.destroy();
				return;
			}
			res.writeHead(502, { "content-type": "application/json; charset=utf-8" });
			res.end(JSON.stringify({ error: "bridge unreachable" }));
		});
		req.pipe(upstream);
	};
}

export function apply(ctx) {
	let child = null;
	let disposed = false;
	let retried = false;
	let retryTimer = null;
	const ring = { buf: "" };

	function onChunk(chunk) {
		ring.buf += String(chunk);
		if (ring.buf.length > RING_LIMIT) {
			ring.buf = ring.buf.slice(ring.buf.length - RING_LIMIT);
		}
	}

	function onUnexpected(reason) {
		if (disposed) return;
		if (retried) {
			const tail = ring.buf.length > 0 ? `\n--- 桥输出尾部 ---\n${ring.buf}` : "";
			console.warn(`[dsh-ziwei-panel] 桥启动失败（${reason}），本会话不再自动重试；可手动双击 start-ziwei-panel.bat。${tail}`);
			return;
		}
		retried = true;
		retryTimer = setTimeout(() => {
			retryTimer = null;
			startBridge();
		}, RETRY_DELAY_MS);
	}

	function startBridge() {
		if (disposed) return;
		child = spawn("node", [BRIDGE_PATH], {
			stdio: ["pipe", "pipe", "pipe"],
			env: minimalEnv(),
			detached: false,
			windowsHide: true
		});
		child.stdout.on("data", onChunk);
		child.stderr.on("data", onChunk);
		child.on("error", (e) => onUnexpected(`error: ${e.message}`));
		child.on("exit", (code) => {
			if (code !== 0) onUnexpected(`exit ${code}`);
		});
	}

	isBridgeRunning().then((running) => {
		if (!running) startBridge();
	});

	// 反代路由：随插件生命周期注册/注销（register 返回注销函数）。
	ctx.effect(() => ctx.webServer.register({
		kind: "prefix",
		path: PROXY_PATH,
		handler: createProxyHandler(PROXY_PATH, PORT, BRIDGE_HOST)
	}), "dsh-ziwei-panel: bridge proxy route");

	return function cleanup() {
		disposed = true;
		if (retryTimer !== null) {
			clearTimeout(retryTimer);
			retryTimer = null;
		}
		if (child !== null) {
			const c = child;
			child = null;
			try { c.stdin.end(); } catch { /* 管道已断 */ }
			c.kill();
		}
	};
}

export const inject = ["webServer"];
