"use strict";

// 兩個頁面共用：API、提示訊息、選單、影像來源控制、頂部狀態
// 顯示名稱、更新頻率等都來自 config.py（/api/monitor/get_monitor_config）

const state = {
  config: null,
  sources: [],
  sourceSynced: false,
  sourceRunning: false,
  sourceName: null,
};

const $ = (id) => document.getElementById(id);
const labelName = (label) => (state.config && state.config.display_names && state.config.display_names[label]) || label;

// ============================================================
// API
// ============================================================

async function api(path, body) {
  const options = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const reply = await fetch(path, options);
  let payload;
  try { payload = await reply.json(); } catch { throw new Error(`HTTP ${reply.status}`); }
  if (payload.status !== "success") throw new Error(payload.message || payload.status);
  return payload.data;
}

function toast(message, isError = false) {
  const box = $("toast");
  box.textContent = message;
  box.className = isError ? "toast err" : "toast";
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, state.config ? state.config.ui.toast_ms : 3500);
}

async function run(action, successMessage) {
  try {
    const result = await action();
    if (successMessage) toast(successMessage);
    return result;
  } catch (error) {
    toast(error.message, true);
    return undefined;
  }
}

async function loadConfig() {
  state.config = await api("/api/monitor/get_monitor_config");
  // 後端版本較舊、缺少欄位時使用預設值，避免整個頁面無法使用
  state.config.display_names = state.config.display_names || {};
  state.config.ui = { timeline_window_s: 120, status_poll_ms: 2000, toast_ms: 3500, ...(state.config.ui || {}) };
}

// ============================================================
// 漢堡選單
// ============================================================

function setupMenu() {
  const button = $("menu-button");
  const panel = $("menu-panel");
  const close = () => { panel.hidden = true; button.setAttribute("aria-expanded", "false"); };
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
  });
  document.addEventListener("click", (event) => { if (!panel.contains(event.target)) close(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  panel.querySelectorAll("a").forEach((link) => {
    if (link.getAttribute("href") === window.location.pathname) link.classList.add("active");
  });
}

// ============================================================
// 影像來源
// ============================================================

async function loadSources() {
  state.sources = await api("/api/source/get_sources");
  const select = $("source-select");
  select.innerHTML = state.sources.map((s) => `<option value="${s.name}">${s.name}</option>`).join("");
  // 優先順序：目前正在執行的來源（renderSourceStatus 設定）→ config.DEFAULT_SOURCE → 第一個
  const fallback = state.sources.find((s) => s.default);
  if (fallback) select.value = fallback.name;
  updateVideoSelect();
  select.addEventListener("change", updateVideoSelect);
  $("btn-source-start").addEventListener("click", startSource);
  $("btn-source-stop").addEventListener("click", stopSource);
}

function updateVideoSelect() {
  const source = state.sources.find((s) => s.name === $("source-select").value);
  const videos = (source && source.options && source.options.videos) || null;
  const select = $("video-select");
  select.hidden = !videos;
  if (videos) {
    select.innerHTML = videos.length
      ? videos.map((v) => `<option value="${v}">${v}</option>`).join("")
      : `<option value="">（data/videos 沒有影片）</option>`;
  }
}

async function startSource() {
  const name = $("source-select").value;
  const options = {};
  if (!$("video-select").hidden && $("video-select").value) options.video = $("video-select").value;
  await run(() => api("/api/source/start_source", { source_name: name, options }), `已開啟 ${name}`);
  refreshCommonStatus();
}

async function stopSource() {
  await run(() => api("/api/source/stop_source", {}));
  refreshCommonStatus();
}

function renderSourceStatus(status) {
  const running = status.state === "running";
  state.sourceRunning = running;
  state.sourceName = running ? status.source_name : null;
  if (running && !state.sourceSynced) {
    state.sourceSynced = true;
    $("source-select").value = status.source_name;
    updateVideoSelect();
    const video = status.options && status.options.video;
    if (video && !$("video-select").hidden) $("video-select").value = video;
  }
  const video = $("video");
  if (running && video.hidden) {
    video.src = `/api/source/get_stream?ts=${Date.now()}`;
    video.hidden = false;
  } else if (!running && !video.hidden) {
    video.removeAttribute("src");
    video.hidden = true;
  }
  $("video-placeholder").hidden = running;
  $("video-placeholder").textContent = status.state === "error" ? `來源錯誤：${status.error}` : "影像來源未啟動";

  const chip = $("chip-source");
  chip.textContent = `來源：${running ? status.source_name : status.state}`;
  chip.className = `chip ${running ? "ok" : status.state === "error" ? "err" : ""}`;

  const meta = [];
  if (running) {
    meta.push(`已擷取 ${status.frames} 張`);
    const d = status.driver || {};
    if (d.video) meta.push(`影片 ${d.video} @ ${d.position_s ?? 0}s${d.ended ? "（已結束）" : ""}`);
    if (d.mode) meta.push(`串流 ${d.mode}${d.reconnects ? `，重連 ${d.reconnects} 次` : ""}`);
    if (d.last_error) meta.push(`連線錯誤：${d.last_error}`);
  }
  $("source-meta").textContent = meta.join(" · ");
}

function renderModelChip(model) {
  const enc = model.encoder;
  const chip = $("chip-encoder");
  chip.textContent = `模型：${enc.name || "—"} ${enc.state === "ready" ? "READY" : enc.state.toUpperCase()}`;
  chip.className = `chip ${enc.state === "ready" ? "ok" : enc.state === "error" ? "err" : "warn"}`;
}

// 頁面可以覆寫 onStatus(source, model) 處理自己的狀態顯示
let onStatus = null;

async function refreshCommonStatus() {
  try {
    const [source, model] = await Promise.all([
      api("/api/source/get_source_status"),
      api("/api/model/get_model_status"),
    ]);
    renderSourceStatus(source);
    renderModelChip(model);
    if (onStatus) onStatus(source, model);
  } catch (error) {
    $("chip-source").textContent = "伺服器無回應";
    $("chip-source").className = "chip err";
  }
}

async function initCommon() {
  setupMenu();
  await loadConfig();
  await loadSources();
}
