"use strict";

// 收集範例頁：先選標註，再拍照存進範例庫

const collectState = {
  labels: [],
  selected: null,
  filter: "",
  busy: false,
};

// ============================================================
// 標註選擇與拍照
// ============================================================

function buildLabelButtons() {
  $("label-buttons").innerHTML = collectState.labels.map((label) =>
    `<button type="button" class="label-option label-${label}" data-label="${label}" aria-pressed="false">
       ${labelName(label)}
     </button>`).join("");
  $("label-buttons").addEventListener("click", (event) => {
    const button = event.target.closest(".label-option");
    if (button) selectLabel(button.dataset.label);
  });
}

function selectLabel(label) {
  collectState.selected = label;
  document.querySelectorAll(".label-option").forEach((button) => {
    const active = button.dataset.label === label;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
  updateCaptureButton();
}

function updateCaptureButton() {
  const button = $("btn-capture");
  const hint = $("capture-hint");
  const label = collectState.selected;
  button.disabled = !label || !state.sourceRunning || collectState.busy;
  button.className = `capture-button${label ? ` label-${label}` : ""}`;
  button.textContent = label ? `拍照 → 存為「${labelName(label)}」` : "拍照";
  if (!state.sourceRunning) hint.textContent = "請先開啟影像來源";
  else if (!label) hint.textContent = "請先選擇要標註的類別";
  else hint.textContent = "快捷鍵：空白鍵";
}

function renderCaptureMethod() {
  const box = $("capture-method");
  if (!state.sourceName) { box.textContent = ""; return; }
  const source = state.sources.find((s) => s.name === state.sourceName);
  box.innerHTML = source && source.snapshot_url
    ? `拍照方式：呼叫 <b>${source.name}</b> 的拍照 API（<code>${source.snapshot_url}</code>）`
    : `拍照方式：<b>${state.sourceName}</b> 沒有設定拍照 API，存目前串流畫面`;
}

function flashVideo() {
  const flash = $("capture-flash");
  flash.classList.remove("on");
  void flash.offsetWidth;  // 重新觸發動畫
  flash.classList.add("on");
}

async function capture() {
  const label = collectState.selected;
  if (!label || collectState.busy || !state.sourceRunning) return;
  collectState.busy = true;
  updateCaptureButton();
  const created = await run(() => api("/api/exemplar/capture_exemplar", { label }), `已存為「${labelName(label)}」範例`);
  collectState.busy = false;
  updateCaptureButton();
  if (created) {
    flashVideo();
    loadExemplars();
  }
}

// ============================================================
// 範例庫
// ============================================================

function renderCounts(counts, min) {
  $("exemplar-counts").innerHTML = collectState.labels.map((label) => {
    const n = counts[label] || 0;
    return `<div class="count-box label-${label}">
              <div class="count-name">${labelName(label)}</div>
              <div class="count-value">${n}</div>
              <div class="count-note ${n < min ? "warn" : "muted"}">${n < min ? `至少 ${min} 個才會開始評分` : "可評分"}</div>
            </div>`;
  }).join("");
}

function buildFilter() {
  const options = [["", "全部"], ...collectState.labels.map((label) => [label, labelName(label)])];
  $("exemplar-filter").innerHTML = options.map(([value, name]) =>
    `<button type="button" data-filter="${value}" class="${value === collectState.filter ? "selected" : ""}">${name}</button>`).join("");
  $("exemplar-filter").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    collectState.filter = button.dataset.filter;
    document.querySelectorAll("#exemplar-filter button").forEach((b) => b.classList.toggle("selected", b === button));
    loadExemplars();
  });
}

async function loadExemplars() {
  const query = collectState.filter ? `?label=${encodeURIComponent(collectState.filter)}` : "";
  const data = await run(() => api(`/api/exemplar/get_exemplars${query}`));
  if (!data) return;
  renderCounts(data.counts, state.config.min_per_label);
  $("exemplar-grid").innerHTML = data.items.map((item) => `
    <div class="exemplar ${item.label}" title="${item.id}">
      <img src="/api/exemplar/get_thumbnail/${encodeURIComponent(item.id)}" loading="lazy" alt="">
      <span class="tag">${labelName(item.label)}</span>
      <button class="del" data-id="${item.id}" title="刪除">✕</button>
    </div>`).join("") || `<div class="muted">還沒有範例。開啟影像、選好標註後按「拍照」。</div>`;
}

async function deleteExemplar(id) {
  if (!confirm(`刪除範例 ${id}？`)) return;
  const done = await run(() => api("/api/exemplar/delete_exemplar", { exemplar_id: id }), "已刪除");
  if (done) loadExemplars();
}

// ============================================================
// Init
// ============================================================

async function init() {
  await initCommon();
  const exemplars = await api("/api/exemplar/get_exemplars");
  collectState.labels = exemplars.labels;
  buildLabelButtons();
  buildFilter();
  updateCaptureButton();

  onStatus = () => {
    updateCaptureButton();
    renderCaptureMethod();
  };
  $("btn-capture").addEventListener("click", capture);
  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
    if (event.code === "Space" && !typing) {
      event.preventDefault();
      capture();
    }
  });
  $("exemplar-grid").addEventListener("click", (event) => {
    if (event.target.classList.contains("del")) deleteExemplar(event.target.dataset.id);
  });

  await loadExemplars();
  refreshCommonStatus();
  setInterval(refreshCommonStatus, state.config.ui.status_poll_ms);
}

init().catch((error) => toast(`初始化失敗：${error.message}`, true));
