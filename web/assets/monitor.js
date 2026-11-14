"use strict";

// 即時監控頁：分數、時間軸、模型資訊（唯讀）

const monitorState = {
  history: [],
  running: null,  // 尚未取得狀態
  nearestId: null,
};

// ============================================================
// 分數
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
    if (monitorState.nearestId !== nearest.exemplar_id) {
      thumb.src = `/api/exemplar/get_thumbnail/${encodeURIComponent(nearest.exemplar_id)}`;
      monitorState.nearestId = nearest.exemplar_id;
    }
    thumb.hidden = false;
    $("nearest-info").innerHTML =
      `<div><b>${labelName(nearest.label)}</b></div>` +
      `<div class="muted">距離 ${nearest.distance.toFixed(3)}</div>`;
  } else {
    thumb.hidden = true;
    monitorState.nearestId = null;
    $("nearest-info").textContent = "—";
  }

  const parts = [];
  if (item && item.raw_score !== null && item.raw_score !== undefined) parts.push(`原始分數 ${item.raw_score.toFixed(1)}`);
  if (item && item.latency_ms) parts.push(`分析延遲 ${Math.round(item.latency_ms)} ms`);
  $("score-meta").textContent = parts.join(" · ");
}

// ============================================================
// 模型資訊（唯讀）
// ============================================================

function renderModelInfo(model) {
  const enc = model.encoder;
  const sc = model.scorer;
  const scorerConfig = (state.config.scorers[sc.name] || {}).kwargs || {};
  const encState = enc.state === "ready" ? `<span class="ok">READY</span>`
    : enc.state === "error" ? `<span class="err">ERROR</span>` : `<span class="warn">${enc.state.toUpperCase()}</span>`;

  const counts = sc.counts || {};
  const countText = [state.config.negative_label, state.config.positive_label].map((label) => {
    const n = counts[label] || 0;
    return `<span class="${n < sc.min_per_label ? "warn" : ""}">${labelName(label)} ${n}</span>`;
  }).join(" / ");

  const scorerParams = Object.entries(scorerConfig).map(([key, value]) => `${key}=${value}`).join(", ");
  $("model-info").innerHTML = `
    <dt>特徵模型</dt><dd>${enc.name || "—"} ${encState}</dd>
    <dt>評分方式</dt><dd>${(sc.name || "—").toUpperCase()}${scorerParams ? ` <span class="muted">(${scorerParams})</span>` : ""}</dd>
    <dt>範例數</dt><dd>${countText || "—"}</dd>
    <dt>模型延遲</dt><dd>${enc.last_latency_ms ? `${Math.round(enc.last_latency_ms)} ms` : "—"}</dd>`;

  const notes = [];
  if (enc.error) notes.push(`模型錯誤：${enc.error}`);
  if (sc.reason) notes.push(sc.reason);
  $("model-note").innerHTML = notes.length
    ? `${notes.join(" · ")}${sc.reason && sc.reason.includes("範例不足") ? ' — <a href="/collect">前往收集範例</a>' : ""}`
    : "";
}

// ============================================================
// 時間軸
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
  const points = monitorState.history;
  const tMax = points.length ? Math.max(points[points.length - 1].t, 10) : 10;
  const tMin = Math.max(0, tMax - state.config.ui.timeline_window_s);
  const x = (t) => pad.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
  const y = (s) => pad.top + (1 - s / 100) * plotH;

  const levels = state.config.levels;
  levels.forEach((level, i) => {
    const end = i + 1 < levels.length ? levels[i + 1].min : 100;
    ctx.fillStyle = level.color + "14";
    ctx.fillRect(pad.left, y(end), plotW, y(level.min) - y(end));
  });

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
// 分析迴圈
// ============================================================

async function loadHistory() {
  const history = await run(() => api("/api/monitor/get_history"));
  if (!history) return;
  monitorState.history = history;
  renderScore(history[history.length - 1]);
  drawTimeline();
}

function connectEvents() {
  const events = new EventSource("/api/monitor/get_events");
  events.addEventListener("risk", (event) => {
    const item = JSON.parse(event.data);
    monitorState.history.push(item);
    if (monitorState.history.length > state.config.pipeline.history_size) monitorState.history.shift();
    renderScore(item);
    drawTimeline();
  });
  events.addEventListener("reset", () => { monitorState.history = []; drawTimeline(); });
  events.addEventListener("monitor", (event) => renderMonitorStatus(JSON.parse(event.data)));
}

const NOT_STARTED = { level: "NOT READY", score: null, reason: "分析未開始，請按「開始分析」" };

function renderMonitorStatus(status) {
  const wasRunning = monitorState.running;
  monitorState.running = status.running;
  const button = $("btn-monitor-toggle");
  button.textContent = status.running ? "停止分析" : "開始分析";
  button.classList.toggle("primary", !status.running);
  if (!status.running && wasRunning !== false) renderScore(NOT_STARTED);
}

async function toggleMonitor() {
  const path = monitorState.running ? "/api/monitor/stop_monitor" : "/api/monitor/start_monitor";
  const status = await run(() => api(path, {}));
  if (status) renderMonitorStatus(status);
}

async function refreshMonitorStatus() {
  await refreshCommonStatus();
  try { renderMonitorStatus(await api("/api/monitor/get_monitor_status")); } catch { /* 顯示在頂部狀態 */ }
}

// ============================================================
// Init
// ============================================================

async function init() {
  await initCommon();
  onStatus = (source, model) => renderModelInfo(model);
  buildScale();
  $("btn-monitor-toggle").addEventListener("click", toggleMonitor);
  $("btn-reset").addEventListener("click", () => run(() => api("/api/monitor/reset_history", {})));
  window.addEventListener("resize", drawTimeline);

  await loadHistory();
  connectEvents();
  refreshMonitorStatus();
  setInterval(refreshMonitorStatus, state.config.ui.status_poll_ms);
}

init().catch((error) => toast(`初始化失敗：${error.message}`, true));
