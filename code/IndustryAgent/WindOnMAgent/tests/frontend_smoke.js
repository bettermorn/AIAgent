// 前端冒烟测试：在 Node 中以最小 DOM 桩运行 app.js，真实请求后端 API，逐个渲染所有视图，捕获运行时异常。
// 用法: node tests/frontend_smoke.js [http://localhost:8000]
const fs = require("fs");
const BASE = process.argv[2] || "http://localhost:8000";
const code = fs.readFileSync(__dirname + "/../web/static/app.js", "utf8");

function makeEl(tag = "div") {
  const el = {
    tagName: tag, children: [], dataset: {}, style: {}, _html: "", _text: "", value: "", className: "", id: "",
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, f) { f ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } },
    set innerHTML(v) { this._html = v; el._scan && el._scan(v); }, get innerHTML() { return this._html; },
    set textContent(v) { this._text = v; }, get textContent() { return this._text; },
    appendChild(c) { this.children.push(c); return c; }, remove() { }, insertAdjacentHTML(_, h) { this._html += h; },
    addEventListener() { }, querySelector(sel) { return find(sel); }, querySelectorAll(sel) { return []; },
    getContext() { return {}; }, focus() { }, onclick: null, onsubmit: null, onchange: null, onkeydown: null,
  };
  return el;
}
const registry = {};
function find(sel) { const k = sel; return registry[k] || (registry[k] = makeEl()); }
const errors = [];
global.document = { querySelector: find, querySelectorAll: () => [], createElement: makeEl, body: makeEl("body"), addEventListener() { } };
global.window = global; global.addEventListener = () => { };
global.location = { protocol: "http:", host: BASE.replace("http://", ""), reload() { } };
const store = {}; global.localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => store[k] = v, removeItem: k => delete store[k] };
global.echarts = { init: () => ({ setOption() { }, dispose() { }, resize() { }, on() { } }) };
global.L = { map: () => ({ setView() { return this; }, remove() { } }), tileLayer: () => ({ addTo() { } }), circleMarker: () => ({ addTo() { return this; }, bindTooltip() { return this; }, on() { return this; } }), marker: () => ({ addTo() { return this; }, bindTooltip() { return this; } }), polyline: () => ({ addTo() { return this; }, bindTooltip() { return this; } }), divIcon: () => ({}) };
global.WebSocket = function () { this.close = () => { }; };
const realFetch = fetch;
global.fetch = (u, o) => realFetch(u.startsWith("http") ? u : BASE + u, o);
global.setInterval = () => 0; global.clearInterval = () => { };
process.on("unhandledRejection", e => errors.push("unhandledRejection: " + (e && e.stack || e)));

(async () => {
  const login = await (await realFetch(BASE + "/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: process.env.U || "approver1", password: "windom123" }) })).json();
  store["wom_token"] = login.token;
  // 暴露内部符号：将 const/let 顶层声明导出到 globalThis
  const patched = code + "\n;globalThis.__app = { S, VIEWS, go, boot, NAV, api, woDetail, assetModal, traceModal, candModal, ingestModal, stepHtml };";
  (0, eval)(patched);
  const A = globalThis.__app;
  await new Promise(r => setTimeout(r, 1500));   // 等 boot()
  console.log("boot ok, user =", A.S.user && A.S.user.username, "farm =", A.S.farm);
  const origErr = console.error;
  for (const [key, , name, vis] of A.NAV) {
    if (!vis(A.S.user)) { console.log("skip (no perm):", name); continue; }
    try { A.go(key); await new Promise(r => setTimeout(r, 2500)); const html = find("#view")._html; console.log("✓ view", key.padEnd(10), name, "html=" + html.length); if (html.length < 20 && key !== "chat" && key !== "gis" && key !== "kg") errors.push("empty view " + key); }
    catch (e) { errors.push(`view ${key}: ${e.stack}`); }
  }
  // 弹窗类渲染
  try { await A.woDetail((await A.api("/workorders?limit=1"))[0].id); console.log("✓ woDetail"); } catch (e) { errors.push("woDetail: " + e.stack); }
  try { await A.assetModal("WT-023"); console.log("✓ assetModal"); } catch (e) { errors.push("assetModal: " + e.stack); }
  try { const t = await A.api("/agent/tasks?limit=1"); if (t[0]) { await A.traceModal(t[0].id); console.log("✓ traceModal"); } } catch (e) { errors.push("traceModal: " + e.stack); }
  try { const c = await A.api("/knowledge/candidates?status=all"); if (c[0]) { A.candModal(c[0], () => { }); console.log("✓ candModal"); } } catch (e) { errors.push("candModal: " + e.message); }
  if (errors.length) { console.log("\n❌ 前端错误:"); errors.forEach(e => console.log(" -", e.split("\n").slice(0, 4).join("\n   "))); process.exit(1); }
  console.log("\n✅ 前端冒烟通过");
  process.exit(0);
})();
