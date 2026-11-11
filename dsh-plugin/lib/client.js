// dsh-ziwei-panel — client half. v0.1.1（主题跟随官方 ThemeRuntime 契约面）
//
// 右栏一个 Tab「紫微排盘」，面板 = iframe 指向宿主反代路径
// /plugins/dsh-ziwei-panel/（宿主半经官方 webServer 路由转发本地桥，
// 经宿主同源代理路径访问，Web/桌面双端通）。
// 客户端零宿主数据
// 依赖，唯一自持逻辑 = 桥探活错误态（禁白屏静默）。
//
// 公开面清单（全部为官方稳定面，无宿主内部契约）：
//   - ctx.sidebarRightTabs.register(SidebarRightTabDefinition)：两段式第一段，
//     注册 type（id/kind/priority 'extension'/title/guide），idiom 照抄
//     dsh-agent-bar 现役代码（已定案）。
//   - ctx.slots.inject("sidebar.right.pane.tab", ...) + ctx.slots.register：
//     两段式第二段，向 keyed 槽位以 definition id 为 key 注册 body 组件
//     （官方 dsh-client-ui-sidebar-files 同款 idiom）。
//   - ctx.theme.getTheme() + ctx.on("theme/change")（inject "theme"）：官方
//     ThemeRuntime 公开契约（主题真值与变化推送）。
//
// 设计约束：
//   - inject 最小集 = ["slots","sidebarRightTabs"]；body 组件纯函数零 hook
//     ——探活状态机全在模块级（engine + DOM 直刷 paint），React 只负责一次
//     性骨架（连接卡/错误卡/iframe 三块常驻，display 切换），无任何
//     useState/useEffect/useRef。
//   - 探活：组件挂载即探 + setInterval 30s（随插件生命周期）；fetch
//     反代路径 /api/version 3s 超时；任何非 502 HTTP 应答（含 503 自检
//     失败——桥在跑、页面自显横幅）= 桥在；502（代理报桥不可达）/网络错/
//     超时 = 未起 → 错误卡（红字 + 重试 + 手动启动指引）。
//
// 探活引擎与 DOM 刷新分离：createProbeEngine/fetchWithTimeout 只依赖注入
// 的 fetchFn 与回调（无 DOM），挂 exports.probeLogic 供单测三分支直测
//（agent-bar exports.cropMath 同款先例，宿主只消费 apply/inject）。

window.__ModuleLoader__.load({
	id: "dsh-ziwei-panel",
	factory: (require) => {
		var React = require("react");
		var module = { exports: {} };
		var exports = module.exports;
		var createElement = React.createElement;

		var PANEL_ID = "dsh-ziwei-panel";
		var KIND = "ziwei-panel"; // kind 契约：一个 kind 仅容一个 builtin + 一个 extension 共存
		var STYLE_ATTR = "data-plugin";

		// 宿主同源反代基址：Web 3080 / 桌面 19387 各自按当前 origin 解析（经宿主代理路径访问）。
		var PROXY_BASE = "/plugins/dsh-ziwei-panel";
		var FRAME_ORIGIN = window.location.origin; // iframe 同源后 postMessage 校验/投递目标
		var PROBE_URL = PROXY_BASE + "/api/version";
		var PROBE_TIMEOUT_MS = 3000;
		var PROBE_INTERVAL_MS = 30000;

		// ── 探活引擎（模块级，无 DOM）────────────────────────
		function fetchWithTimeout(fetchFn, url, ms) {
			if (typeof AbortController !== "function") return fetchFn(url);
			var ctrl = new AbortController();
			var timer = setTimeout(function () { ctrl.abort(); }, ms);
			return fetchFn(url, { signal: ctrl.signal }).then(function (res) {
				clearTimeout(timer);
				return res;
			}, function (error) {
				clearTimeout(timer);
				throw error;
			});
		}

		function createProbeEngine(fetchFn, onChange) {
			var pending = false;
			function run() {
				if (pending) return;
				pending = true;
				fetchWithTimeout(fetchFn, PROBE_URL, PROBE_TIMEOUT_MS).then(
					// 反代后语义：502 = 宿主路由可达但桥不可达（代理回
					// {error:'bridge unreachable'}）→ 未起；其余任何 HTTP 应答
					//（含桥自身 503 自检失败）= 桥在。网络错/超时同样未起。
					function (res) { pending = false; onChange(res.status !== 502); },
					function () { pending = false; onChange(false); }
				);
			}
			return { run: run };
		}

		// ── 模块级面板状态 + DOM 直刷 ────────────────────────
		// up: null = 未知（连接中）；true/false = 最近一次探活结果。paint 是
		// 零 hook 下状态→视图的唯一通道；ref 挂/卸（含 tab 反复切换）都经
		// paint 与模块状态对齐。
		var view = { up: null };
		var barVisible = true; // 保存栏显隐（真值在 iframe 内 localStorage，state 回执对齐）
		var dom = { connecting: null, error: null, frame: null, barToggle: null, barIcon: null };

		// paint 必须纯幂等（只切 display）——拖拽 sash 时右栏每帧 re-render，
		// 内联 ref 函数每渲染重挂都会触发 paint；若 paint 内含 src 重赋等副作用，
		// 会每帧强制 iframe 整页重载。
		// 副作用（重载清残留错误页）只允许发生在探活 false→true 翻转处，一次即止。
		function paint() {
			if (dom.connecting !== null) dom.connecting.style.display = view.up === null ? "" : "none";
			if (dom.error !== null) dom.error.style.display = view.up === false ? "" : "none";
			if (dom.frame !== null) dom.frame.style.display = view.up === true ? "" : "none";
			if (dom.barToggle !== null) {
				dom.barToggle.setAttribute("aria-pressed", barVisible ? "true" : "false");
			}
			// 方向即状态：显示中 ‹（scaleX(-1)）、已隐藏 ›（scaleX(1)）；翻转幂等。
			if (dom.barIcon !== null) {
				dom.barIcon.style.transform = barVisible ? "scaleX(-1)" : "scaleX(1)";
			}
			// 按钮整体色由 aria-pressed 选择器控（tertiary 淡化）。
		}

		// ── 保存栏显隐：postMessage 双向协议（iframe 经反代与宿主同源）────
		// 命令：{type:'dzp-sidebar', action:'toggle'|'query'}；回执：
		// {type:'dzp-sidebar-state', visible:<bool>}。origin 双向校验。
		function postToFrame(action) {
			if (dom.frame !== null && dom.frame.contentWindow !== null) {
				dom.frame.contentWindow.postMessage(
					{ type: "dzp-sidebar", action: action }, FRAME_ORIGIN);
			}
		}

		function onFrameLoad() {
			postToFrame("query"); // iframe 每次加载后同步一次真值（含恢复重载）
			postThemeToFrame(); // 主题同理：加载即推一次缓存值，免等下次事件翻转
		}

		// ── 主题跟随──
		// 真值源 = ctx.theme.getTheme().active.colorScheme（官方 ThemeRuntime
		// 解析终值：system 偏好已代解析、override 层已折入），变化经官方
		// 'theme/change' 事件推送——不再观察宿主 body 属性（那是 presenter
		// 内部实现细节，非契约）。lastDark = 模块级缓存，iframe 每次加载后
		//（onFrameLoad）补推当前值（apply 初始推送时 iframe 可能尚未加载）。
		var lastDark = false;

		function postThemeToFrame() {
			if (dom.frame !== null && dom.frame.contentWindow !== null) {
				dom.frame.contentWindow.postMessage(
					{ type: "dzp-theme", dark: lastDark }, FRAME_ORIGIN);
			}
		}

		function onMessage(e) {
			if (e.origin !== FRAME_ORIGIN) return;
			if (e.data === null || typeof e.data !== "object") return;
			if (e.data.type !== "dzp-sidebar-state") return;
			if (typeof e.data.visible !== "boolean") return;
			if (barVisible === e.data.visible) return;
			barVisible = e.data.visible;
			paint();
		}

		var engine = createProbeEngine(fetch, function (up) {
			var wasDown = view.up === false;
			if (view.up === up) return;
			view.up = up;
			paint();
			// 恢复转显时重载一次：清掉隐藏期可能残留的错误页（原设计意图，
			// 从 paint 移到状态翻转处，保证 ref 重挂风暴下零重载）。
			if (up === true && wasDown && dom.frame !== null) {
				dom.frame.src = dom.frame.src;
			}
		});

		// root ref 必须是模块级稳定函数：内联函数每次渲染重建会致 React 重调
		//（先 null 后 el），拖拽期每帧重探触发无谓 fetch。
		function onRootRef(el) {
			if (el !== null) engine.run(); // 首次挂载即探
		}

		function retryFromCard() {
			if (view.up !== null) { view.up = null; paint(); }
			engine.run();
		}

		var CSS = ""
			+ ".dzp-root{height:100%;width:100%;display:flex;flex-direction:column;overflow:hidden;box-sizing:border-box}"
			+ ".dzp-toolbar{flex-shrink:0;height:38px;box-sizing:border-box;border-bottom:.5px solid var(--dsw-alias-border-l3);display:flex;align-items:center;justify-content:flex-end;padding:0 6px}"
			// .dzp-bar-toggle 照抄官方 dsh-client-ui-sidebar-right .iconButton 参数
			//（lib/client.js 内 P3OORG_iconButton）：28×28、radius --dsw-radius-sm、
			// padding 6px、svg 15×15、hover --dsw-alias-interactive-bg-hover；官方无
			// transition/active 先例，不自行添加。
			// 自制 tooltip 对齐官方 dsh-client-ui-primitives Tooltip.module.css .bubble：
			// bg/字色/radius/字号/行高/padding 全取官方 token 与计算值；出现过渡照官方
			// 150ms cubic-bezier(.4,0,.2,1) 淡入；pointer-events:none 防浮标挡点击。
			+ ".dzp-bar-toggle:hover::after{content:\"命盘保存栏\";position:absolute;top:calc(100% + 6px);right:0;width:max-content;max-width:50vw;padding:3px 7px;border-radius:var(--dsw-radius-sm);background:var(--dsw-alias-tooltip-bg);color:var(--dsw-static-neutral-bluish-00);font-size:13px;line-height:20px;white-space:pre-line;pointer-events:none;animation:dzp-tooltip-in 150ms var(--ds-ease-in-out)}"
			+ "@keyframes dzp-tooltip-in{from{opacity:0}}"
			+ ".dzp-bar-toggle{position:relative;width:28px;height:28px;color:var(--dsw-alias-label-secondary);border-radius:var(--dsw-radius-sm);cursor:pointer;background:0 0;border:none;flex:none;justify-content:center;align-items:center;padding:6px;line-height:1;display:inline-flex}"
			+ ".dzp-bar-toggle svg{width:15px;height:15px;display:block}"
			+ ".dzp-bar-toggle:hover{background:var(--dsw-alias-interactive-bg-hover)}"
			+ ".dzp-bar-toggle[aria-pressed=\"false\"]{color:var(--dsw-alias-label-tertiary)}"
			+ ".dzp-frame{flex:1;width:100%;min-height:0;border:0;display:block;background:#fff}"
			+ ".dzp-connecting{flex:1;display:flex;align-items:center;justify-content:center;color:var(--dsw-alias-label-tertiary);font-size:var(--dsh-content-font-size-secondary,13px)}"
			+ ".dzp-error{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px;text-align:center}"
			+ ".dzp-error-title{color:var(--dsw-alias-state-error-primary);font-size:var(--dsh-content-font-size-secondary,13px);font-weight:600}"
			+ ".dzp-error-desc{color:var(--dsw-alias-label-primary);font-size:var(--dsh-content-font-size-secondary,13px)}"
			+ ".dzp-error-hint{color:var(--dsw-alias-label-tertiary);font-size:11px;line-height:1.6}"
			+ ".dzp-retry{border:1px solid var(--dsw-alias-border-l3);border-radius:6px;padding:4px 12px;cursor:pointer;background:transparent;color:var(--dsw-alias-label-primary);font-size:var(--dsh-content-font-size-secondary,13px)}"
			+ ".dzp-retry:hover{background:var(--dsw-alias-interactive-bg-hover)}";

		function ZiweiPanelBody() {
			return createElement("div", {
				className: "dzp-root",
				ref: onRootRef
			},
				createElement("div", { className: "dzp-toolbar" },
					createElement("button", {
						type: "button",
						className: "dzp-bar-toggle",
						ref: function (el) { dom.barToggle = el; paint(); },
						onClick: function () { postToFrame("toggle"); },
						"aria-pressed": "true"
					},
							// chevron 折线箭头：方向表状态（paint 幂等翻转 scaleX）——
							// 保存栏显示中 → ›（点击收起）；已隐藏 → ‹（点击展开）。
							// viewBox 16 / strokeWidth 1 / linecap round 对齐官方线宽口径。
						createElement("svg", {
							viewBox: "0 0 16 16",
							"aria-hidden": "true",
							fill: "none",
							xmlns: "http://www.w3.org/2000/svg",
							ref: function (el) { dom.barIcon = el; paint(); }
						},
							createElement("path", {
								d: "M6 3.5 L10.5 8 L6 12.5",
								stroke: "currentColor",
								"stroke-width": "1",
								"stroke-linecap": "round",
								"stroke-linejoin": "round"
							})
						)
					)
				),
				createElement("div", {
					className: "dzp-connecting",
					ref: function (el) { dom.connecting = el; paint(); }
				}, "正在连接本地桥服务…"),
				createElement("div", {
					className: "dzp-error",
					ref: function (el) { dom.error = el; paint(); },
					style: { display: "none" }
				},
					createElement("div", { className: "dzp-error-title" }, "桥服务未启动"),
					createElement("div", { className: "dzp-error-desc" },
						"面板依赖本地桥服务（经宿主代理路径 /plugins/dsh-ziwei-panel 转发），当前桥未起。"),
					createElement("div", { className: "dzp-error-hint" },
						"手动启动：双击 extensions\\plugins\\dsh-ziwei-panel\\start-ziwei-panel.bat"),
					createElement("button", { className: "dzp-retry", onClick: retryFromCard }, "重试")
				),
				createElement("iframe", {
					className: "dzp-frame",
					ref: function (el) { dom.frame = el; paint(); },
					style: { display: "none" },
					src: PROXY_BASE + "/",
					title: "紫微排盘",
					onLoad: onFrameLoad
				})
			);
		}

		// ── 注册 ────────────────────────────────────────────────

		var inject = [
			"slots",
			"sidebarRightTabs",
			"theme"
		];

		function apply(ctx) {
			// 两段式第一段：type 定义（guide 单入口，thunk 文案随读随取）。
			ctx.effect(function () {
				return ctx.sidebarRightTabs.register({
					id: PANEL_ID,
					kind: KIND,
					priority: "extension",
					title: function () { return "紫微排盘"; },
					guide: [{
						order: 910,
						title: function () { return "紫微排盘"; },
						description: function () { return "本地排盘面板（宿主代理转发本地桥）"; }
					}]
				});
			}, "dsh-ziwei-panel: tab type");

			// 样式标签：随插件生命周期注入/移除。
			ctx.effect(function () {
				var styleEl = document.createElement("style");
				styleEl.setAttribute(STYLE_ATTR, "dsh-ziwei-panel");
				styleEl.textContent = CSS;
				document.head.appendChild(styleEl);
				return function () { styleEl.remove(); };
			}, "dsh-ziwei-panel: style");

			// 定期探活：插件生命周期内常驻 30s 一探（组件挂载即探在
			// ZiweiPanelBody root ref）。
		ctx.effect(function () {
			var timer = setInterval(engine.run, PROBE_INTERVAL_MS);
			return function () { clearInterval(timer); };
		}, "dsh-ziwei-panel: probe timer");

		// 保存栏 state 回执监听（随插件生命周期注入/移除）。
		ctx.effect(function () {
			window.addEventListener("message", onMessage);
			return function () { window.removeEventListener("message", onMessage); };
		}, "dsh-ziwei-panel: sidebar message");

		// 主题跟随：官方 theme/change 事件（含 system 模式 OS 色系翻转）驱动；
		// 挂载时先推一次当前值。推送目标恒为 FRAME_ORIGIN（origin 校验风格
		// 沿用探活）。
		ctx.effect(function () {
			lastDark = ctx.theme.getTheme().active.colorScheme === "dark";
			postThemeToFrame();
			return ctx.on("theme/change", function (snapshot) {
				lastDark = snapshot.active.colorScheme === "dark";
				postThemeToFrame();
			});
		}, "dsh-ziwei-panel: theme");

			// 两段式第二段：body 注册到 keyed 槽位（key = definition id）。
			ctx.effect(function () {
				return ctx.slots.inject("sidebar.right.pane.tab", function () {
					return ctx.slots.register({
						name: "sidebar.right.pane.tab",
						key: PANEL_ID
					}, ZiweiPanelBody);
				});
			}, "dsh-ziwei-panel: tab body");
		}

		exports.apply = apply;
		exports.inject = inject;
		// 探活纯逻辑直测出口（宿主只消费 apply/inject，多挂导出无影响）。
		exports.probeLogic = {
			fetchWithTimeout: fetchWithTimeout,
			createProbeEngine: createProbeEngine
		};
		return module.exports;
	}
});
