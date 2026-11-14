"use strict";

const LABEL_NAMES = { normal: "正常", collision: "碰撞" };
const TIMELINE_WINDOW_S = 120;

const state = {
  config: null,
  history: [],
  sources: [],
  monitorRunning: true,
  nearestId: null,
};

const $ = (id) => document.getElementById(id);
const labelName = (label) => LABEL_NAMES[label] || label;

// ============================================================
// API
// ============================================================

async function api(path, body) {
  const options = body === undefined
    ? {}
    : body instanceof FormData
      ? { method: "POST", body }
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
  toast.timer = setTimeout(() => { box.hidden = true; }, 3500);
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

// ============================================================
// Score card
// ============================================================

function buildScale() {
  const levels = state.config.levels;
  const track = $("score-track");
  const scale = $("score-scale");
  track.innerHTML = "";
  scale.innerHTML = "";
  levels.forEach((level, i) => {
    const end = i + 1 < levels.length ? levels[i + 1].min : 100;
    const part = document.createElement("span");
    part.style.width = `${end - level.min}%`;
    part.style.background = level.color;
    track.appendChild(part);
    if (level.min > 0) {
      const tick = document.createElement("span");
      tick.style.left = `${level.min}%`;
      tick.textContent = level.min;
      scale.appendChild(tick);
    }
  });
}

function renderScore(item) {
  const value = $("score-value");
  const level = $("score-level");
  const marker = $("score-marker");
  if (!item || item.score === null || item.score === undefined) {
    value.textContent = "--";
    value.style.color = "var(--muted)";
    level.textContent = item ? item.level : "NOT READY";
    level.style.color = "var(--muted)";
    marker.style.display = "none";
  } else {
    value.textContent = Math.round(item.score);
    value.style.color = item.color;
    level.textContent = item.level;
    level.style.color = item.color;
    marker.style.display = "block";
    marker.style.left = `${Math.max(0, Math.min(100, item.score))}%`;
  }
  $("score-reason").textContent = item && item.reason ? item.reason : "";

  const nearest = item && item.nearest;
  const thumb = $("nearest-thumb");
  if (nearest) {
    if (state.nearestId !== nearest.exemplar_id) {
      thumb.src = `/api/exemplar/get_thumbnail/${encodeURIComponent(nearest.exemplar_id)}`;
      state.nearestId = nearest.exemplar_id;
    }
    thumb.hidden = false;
    $("nearest-info").innerHTML =
      `<div><b>${labelName(nearest.label)}</b></div>` +
      `<div class="muted">距離 ${nearest.distance.toFixed(3)}</div>`;
  } else {
    thumb.hidden = true;
    state.nearestId = null;
    $("nearest-info").textContent = "—";
  }
  document.querySelectorAll(".exemplar").forEach((el) => {
    el.classList.toggle("highlight", nearest && el.dataset.id === nearest.exemplar_id);
  });

  const parts = [];
  if (item && item.raw_score !== null && item.raw_score !== undefined) parts.push(`原始分數 ${item.raw_score.toFixed(1)}`);
  if (item && item.latency_ms) parts.push(`分析延遲 ${Math.round(item.latency_ms)} ms`);
  $("score-meta").textContent = parts.join(" · ");
}

// ============================================================
// Timeline
// ============================================================

function drawTimeline() {
  const canvas = $("timeline");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== width * ratio || canvas.height !== height * ratio) {
    canvas.width = width * ratio;
    canvas.height = height * ratio;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = { left: 36, right: 12, top: 10, bottom: 24 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const points = state.history;
  const tMax = points.length ? Math.max(points[points.length - 1].t, 10) : 10;
  const tMin = Math.max(0, tMax - TIMELINE_WINDOW_S);
  const x = (t) => pad.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
  const y = (s) => pad.top + (1 - s / 100) * plotH;

  // 等級背景帶
  const levels = state.config ? state.config.levels : [];
  levels.forEach((level, i) => {
    const end = i + 1 < levels.length ? levels[i + 1].min : 100;
    ctx.fillStyle = level.color + "14";
    ctx.fillRect(pad.left, y(end), plotW, y(level.min) - y(end));
  });

  // 格線與座標
  ctx.strokeStyle = "#2a3039";
  ctx.fillStyle = "#8a93a0";
  ctx.font = "11px sans-serif";
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  [0, 20, 40, 60, 80, 100].forEach((s) => {
    ctx.beginPath(); ctx.moveTo(pad.left, y(s)); ctx.lineTo(pad.left + plotW, y(s)); ctx.stroke();
    ctx.fillText(s, pad.left - 6, y(s));
  });
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const step = (tMax - tMin) > 60 ? 20 : (tMax - tMin) > 20 ? 5 : 2;
  for (let t = Math.ceil(tMin / step) * step; t <= tMax; t += step) {
    ctx.fillText(`${t}s`, x(t), pad.top + plotH + 6);
  }

  // 門檻線
  ctx.setLineDash([6, 4]);
  levels.filter((level) => level.min > 0).forEach((level) => {
    ctx.strokeStyle = level.color;
    ctx.beginPath(); ctx.moveTo(pad.left, y(level.min)); ctx.lineTo(pad.left + plotW, y(level.min)); ctx.stroke();
    ctx.fillStyle = level.color;
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText(`${level.name} (${level.min})`, pad.left + plotW - 4, y(level.min) - 2);
  });
  ctx.setLineDash([]);

  // 分數曲線（分數為 null 時斷開）
  const visible = points.filter((p) => p.t >= tMin);
  ctx.strokeStyle = "#e6e9ee";
  ctx.lineWidth = 2;
  ctx.beginPath();
  let drawing = false;
  visible.forEach((p) => {
    if (p.score === null || p.score === undefined) { drawing = false; return; }
    if (drawing) ctx.lineTo(x(p.t), y(p.score)); else ctx.moveTo(x(p.t), y(p.score));
    drawing = true;
  });
  ctx.stroke();
  visible.forEach((p) => {
    if (p.score === null || p.score === undefined) return;
    ctx.fillStyle = p.color;
    ctx.beginPath(); ctx.arc(x(p.t), y(p.score), 2.5, 0, Math.PI * 2); ctx.fill();
  });
}

// ============================================================
// Source
// ============================================================

function renderSourceOptions() {
  const select = $("source-select");
  const current = select.value;
  select.innerHTML = state.sources.map((s) => `<option value="${s.name}">${s.name}（${s.driver}）</option>`).join("");
  if (current) select.value = current;
  updateVideoSelect();
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
  refreshStatus();
}

async function stopSource() {
  await run(() => api("/api/source/stop_source", {}));
  refreshStatus();
}

function renderSourceStatus(status) {
  const running = status.state === "running";
  // 開啟網頁時，選單顯示目前正在使用的來源
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

// ============================================================
// Model
// ============================================================

function fillSelect(select, values, current) {
  if (select.options.length !== values.length) {
    select.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join("");
  }
  if (current && document.activeElement !== select) select.value = current;
}

function renderModelStatus(model) {
  const enc = model.encoder;
  const sc = model.scorer;
  fillSelect($("encoder-select"), model.available_encoders, enc.name);
  fillSelect($("scorer-select"), model.available_scorers, sc.name);

  const encChip = $("chip-encoder");
  encChip.textContent = `模型：${enc.name || "—"} ${enc.state === "ready" ? "READY" : enc.state.toUpperCase()}`;
  encChip.className = `chip ${enc.state === "ready" ? "ok" : enc.state === "error" ? "err" : "warn"}`;

  const scChip = $("chip-scorer");
  scChip.textContent = `評分：${sc.name || "—"} ${sc.ready ? "READY" : "未就緒"}`;
  scChip.className = `chip ${sc.ready ? "ok" : "warn"}`;

  const meta = [];
  if (enc.error) meta.push(`模型錯誤：${enc.error}`);
  if (enc.load_time_s) meta.push(`載入耗時 ${enc.load_time_s}s`);
  if (enc.last_latency_ms) meta.push(`encoder 延遲 ${Math.round(enc.last_latency_ms)} ms`);
  if (enc.info && enc.info.dim) meta.push(`特徵維度 ${enc.info.dim}`);
  if (sc.reason) meta.push(`評分：${sc.reason}`);
  $("model-meta").textContent = meta.join(" · ");

  renderExemplarSummary(sc.counts, sc.min_per_label);
}

// ============================================================
// Exemplars
// ============================================================

function renderExemplarSummary(counts, min) {
  $("exemplar-summary").innerHTML = Object.entries(counts).map(([label, n]) =>
    `<span class="count ${n < min ? "short" : ""}">${labelName(label)}：${n}${n < min ? `（至少 ${min}）` : ""}</span>`
  ).join("");
}

async function loadExemplars() {
  const data = await run(() => api("/api/exemplar/get_exemplars"));
  if (!data) return;
  $("exemplar-grid").innerHTML = data.items.map((item) => `
    <div class="exemplar ${item.label}" data-id="${item.id}" title="${item.id}">
      <img src="/api/exemplar/get_thumbnail/${encodeURIComponent(item.id)}" loading="lazy" alt="">
      <span class="tag">${labelName(item.label)}</span>
      <button class="del" data-id="${item.id}" title="刪除">✕</button>
    </div>`).join("") || `<div class="muted">尚未建立範例。開啟影像後，按上方按鈕把目前畫面存成範例。</div>`;
}

function buildExemplarControls(labels) {
  $("capture-buttons").innerHTML = labels.map((label) =>
    `<button class="label-${label}" data-label="${label}">存為${labelName(label)}範例</button>`
  ).join("");
  $("upload-label").innerHTML = labels.map((label) => `<option value="${label}">${labelName(label)}</option>`).join("");
}

async function captureExemplar(label) {
  const created = await run(() => api("/api/exemplar/capture_exemplar", { label }), `已存為${labelName(label)}範例`);
  if (created) { loadExemplars(); refreshStatus(); }
}

async function uploadExemplars() {
  const files = $("upload-files").files;
  if (!files.length) { toast("請先選擇圖片", true); return; }
  const form = new FormData();
  form.append("label", $("upload-label").value);
  [...files].forEach((file) => form.append("files", file));
  const created = await run(() => api("/api/exemplar/upload_exemplar", form), `已上傳 ${files.length} 張`);
  if (created) { $("upload-files").value = ""; loadExemplars(); refreshStatus(); }
}

async function deleteExemplar(id) {
  if (!confirm(`刪除範例 ${id}？`)) return;
  const done = await run(() => api("/api/exemplar/delete_exemplar", { exemplar_id: id }), "已刪除");
  if (done) { loadExemplars(); refreshStatus(); }
}

// ============================================================
// Monitor
// ============================================================

async function loadHistory() {
  const history = await run(() => api("/api/monitor/get_history"));
  if (!history) return;
  state.history = history;
  renderScore(history[history.length - 1]);
  drawTimeline();
}

function connectEvents() {
  const source = new EventSource("/api/monitor/get_events");
  source.addEventListener("risk", (event) => {
    const item = JSON.parse(event.data);
    state.history.push(item);
    if (state.history.length > state.config.pipeline.history_size) state.history.shift();
    renderScore(item);
    drawTimeline();
  });
  source.addEventListener("reset", () => { state.history = []; drawTimeline(); });
}

function renderMonitorStatus(status) {
  state.monitorRunning = status.running;
  $("btn-monitor-toggle").textContent = status.running ? "暫停分析" : "繼續分析";
}

async function toggleMonitor() {
  const path = state.monitorRunning ? "/api/monitor/stop_monitor" : "/api/monitor/start_monitor";
  const status = await run(() => api(path, {}));
  if (status) renderMonitorStatus(status);
}

// ============================================================
// Status polling
// ============================================================

async function refreshStatus() {
  try {
    const [source, model, monitor] = await Promise.all([
      api("/api/source/get_source_status"),
      api("/api/model/get_model_status"),
      api("/api/monitor/get_monitor_status"),
    ]);
    renderSourceStatus(source);
    renderModelStatus(model);
    renderMonitorStatus(monitor);
  } catch (error) {
    $("chip-source").textContent = "伺服器無回應";
    $("chip-source").className = "chip err";
  }
}

// ============================================================
// Init
// ============================================================

async function init() {
  state.config = await api("/api/monitor/get_monitor_config");
  buildScale();
  state.sources = await api("/api/source/get_sources");
  renderSourceOptions();
  const exemplars = await api("/api/exemplar/get_exemplars");
  buildExemplarControls(exemplars.labels);

  $("source-select").addEventListener("change", updateVideoSelect);
  $("btn-source-start").addEventListener("click", startSource);
  $("btn-source-stop").addEventListener("click", stopSource);
  $("btn-monitor-toggle").addEventListener("click", toggleMonitor);
  $("btn-reset").addEventListener("click", () => run(() => api("/api/monitor/reset_history", {})));
  $("btn-upload").addEventListener("click", uploadExemplars);
  $("capture-buttons").addEventListener("click", (e) => {
    const label = e.target.dataset && e.target.dataset.label;
    if (label) captureExemplar(label);
  });
  $("exemplar-grid").addEventListener("click", (e) => {
    if (e.target.classList.contains("del")) deleteExemplar(e.target.dataset.id);
  });
  $("encoder-select").addEventListener("change", async (e) => {
    await run(() => api("/api/model/select_encoder", { encoder_name: e.target.value }), "切換模型中…");
    refreshStatus();
  });
  $("scorer-select").addEventListener("change", async (e) => {
    await run(() => api("/api/model/select_scorer", { scorer_name: e.target.value }), "已切換評分方法");
    refreshStatus();
  });
  window.addEventListener("resize", drawTimeline);

  await loadHistory();
  await loadExemplars();
  connectEvents();
  refreshStatus();
  setInterval(refreshStatus, 2000);
}

init().catch((error) => toast(`初始化失敗：${error.message}`, true));
