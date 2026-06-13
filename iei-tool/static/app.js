/* =====================================================
   遺影写真作成ツール - Frontend Logic
   ===================================================== */

"use strict";

// ── State ─────────────────────────────────────────────
const state = {
  sessionId: null,
  currentStep: 1,
  bgColor: "#ffffff",
  selectedSizeId: null,
  bgFiles: [],           // uploaded background filenames (video)
  outputChoices: {},     // { yotsugiri: 1, cabinet: 1, askanet_mini: 3, video: true }
  comparing: false,
  personBoxes: [],
  videoDuration: 45,
  videoFade: 3,
};

// ── Helpers ───────────────────────────────────────────
function qs(sel, ctx = document) { return ctx.querySelector(sel); }
function qsa(sel, ctx = document) { return [...ctx.querySelectorAll(sel)]; }

function toast(msg, dur = 2800) {
  const el = qs("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), dur);
}

async function apiFetch(url, options = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return r.json();
}

function setPreview(url, withCompare = false) {
  const img = qs("#preview-img");
  const ph = qs("#preview-placeholder");
  const cw = qs("#compare-wrap");

  if (!url) {
    img.style.display = "none";
    ph.style.display = "flex";
    cw.classList.remove("visible");
    return;
  }
  ph.style.display = "none";
  if (withCompare) {
    qs("#compare-after").src = url + "&t=" + Date.now();
    cw.classList.add("visible");
    img.style.display = "none";
  } else {
    cw.classList.remove("visible");
    img.style.display = "block";
    img.src = url + "&t=" + Date.now();
  }
}

function previewUrl(name = "current.png") {
  return `/session/${state.sessionId}/preview?name=${name}`;
}

function refreshPreview(name) {
  setPreview(previewUrl(name));
}

// ── Job polling ───────────────────────────────────────
function pollJob(jobId, onDone, onError, progressBarSel, msgSel) {
  const bar = progressBarSel ? qs(progressBarSel) : null;
  const msg = msgSel ? qs(msgSel) : null;

  const interval = setInterval(async () => {
    const j = await apiFetch(`/job/${jobId}`);
    if (bar) bar.style.width = j.progress + "%";
    if (msg) msg.textContent = j.message || "";
    if (j.status === "done") {
      clearInterval(interval);
      onDone(j.result);
    } else if (j.status === "error") {
      clearInterval(interval);
      onError(j.error || "エラーが発生しました");
    }
  }, 1500);
}

// ── Step navigation ───────────────────────────────────
function goToStep(n) {
  if (!state.sessionId && n > 1) { toast("先に写真を読み込んでください"); return; }
  state.currentStep = n;
  qsa(".step-panel").forEach(p => p.classList.remove("active"));
  qsa(".step-tab").forEach((t, i) => {
    t.classList.toggle("active", i + 1 === n);
  });
  qs(`#step-${n}`).classList.add("active");
}

// ── STEP 1: Upload ────────────────────────────────────
function initUpload() {
  const zone = qs("#upload-zone");
  const input = qs("#file-input");

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) uploadFile(file);
  });
  input.addEventListener("change", e => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
  });
}

async function uploadFile(file) {
  const zone = qs("#upload-zone");
  zone.innerHTML = `<div class="spinner"></div><p style="margin-top:8px;color:var(--gray-mid)">読み込み中…</p>`;

  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/upload", { method: "POST", body: fd });
  const data = await r.json();

  if (data.error) { toast("❌ " + data.error); resetUploadZone(); return; }
  state.sessionId = data.session_id;

  refreshPreview();
  toast("✅ 写真を読み込みました");
  resetUploadZone();

  // Show detect persons button
  qs("#btn-detect-persons").style.display = "inline-flex";
  goToStep(2);
}

function resetUploadZone() {
  qs("#upload-zone").innerHTML = `
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
    <p class="upload-title">写真をここにドロップ</p>
    <p style="color:var(--gray-mid);font-size:12px;margin:8px 0">または</p>
    <button class="btn btn-primary" onclick="document.getElementById('file-input').click()">ファイルを選択</button>
    <p class="upload-hint">JPG・PNG・TIFF・BMP 対応</p>
    <input type="file" id="file-input" accept="image/*" hidden>`;
  initUpload();
}

// ── STEP 1: Person detection ──────────────────────────
async function detectPersons() {
  const btn = qs("#btn-detect-persons");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 人物を検出中…`;

  const { job_id } = await apiFetch(`/session/${state.sessionId}/detect_persons`, { method: "POST" });

  pollJob(job_id,
    result => {
      btn.disabled = false;
      btn.innerHTML = "👥 人物を検出";
      if (!result || !result.persons || result.persons.length === 0) {
        toast("人物が検出できませんでした。写真を確認してください。");
        return;
      }
      showPersonBoxes(result.persons);
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = "👥 人物を検出";
      toast("❌ " + err);
    }
  );
}

function showPersonBoxes(persons) {
  state.personBoxes = persons;
  const overlay = qs("#person-overlay");
  overlay.innerHTML = "";
  const img = qs("#preview-img");
  const rect = img.getBoundingClientRect();
  const prect = qs("#right-panel").getBoundingClientRect();

  persons.forEach(p => {
    const box = document.createElement("div");
    box.className = "person-box";
    box.style.left = ((p.x * rect.width) + (rect.left - prect.left)) + "px";
    box.style.top = ((p.y * rect.height) + (rect.top - prect.top)) + "px";
    box.style.width = (p.w * rect.width) + "px";
    box.style.height = (p.h * rect.height) + "px";
    box.innerHTML = `<span class="person-box-label">${p.label} ← クリックして選択</span>`;
    box.addEventListener("click", () => selectPerson(p));
    overlay.appendChild(box);
  });

  overlay.classList.add("visible");
  toast("遺影にする方をクリックしてください");
}

async function selectPerson(person) {
  qs("#person-overlay").classList.remove("visible");
  qs("#person-overlay").innerHTML = "";
  toast("人物を分離中…");

  // Snapshot before
  await apiFetch(`/session/${state.sessionId}/snapshot`, { method: "POST" });

  const { job_id } = await apiFetch(`/session/${state.sessionId}/isolate_person`, {
    method: "POST",
    body: JSON.stringify({ label: person.label }),
  });

  pollJob(job_id,
    () => { refreshPreview(); toast("✅ " + person.label + "を分離しました"); },
    err => toast("❌ " + err)
  );
}

// ── STEP 2: Enhance ───────────────────────────────────
function initEnhanceSliders() {
  ["brightness", "contrast", "sharpness"].forEach(name => {
    const slider = qs(`#slider-${name}`);
    const valEl = qs(`#val-${name}`);
    slider.addEventListener("input", () => {
      valEl.textContent = slider.value;
    });
  });
}

async function applyEnhance() {
  const btn = qs("#btn-enhance");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 補正中…`;

  const body = {
    brightness: parseFloat(qs("#slider-brightness").value),
    contrast: parseFloat(qs("#slider-contrast").value),
    sharpness: parseFloat(qs("#slider-sharpness").value),
  };

  await apiFetch(`/session/${state.sessionId}/enhance`, { method: "POST", body: JSON.stringify(body) });
  refreshPreview();
  btn.disabled = false;
  btn.innerHTML = "補正を適用";
  toast("✅ 補正しました");
}

async function geminiEnhance() {
  const btn = qs("#btn-gemini-enhance");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> AI処理中…`;
  qs("#enhance-progress").style.display = "block";

  // Save before snapshot
  await apiFetch(`/session/${state.sessionId}/snapshot`, { method: "POST" });

  const { job_id } = await apiFetch(`/session/${state.sessionId}/gemini_enhance`, { method: "POST" });
  pollJob(job_id,
    () => {
      refreshPreview();
      btn.disabled = false;
      btn.innerHTML = "✨ Gemini AI 高画質化";
      qs("#enhance-progress").style.display = "none";
      toast("✅ AI高画質化が完了しました");
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = "✨ Gemini AI 高画質化";
      qs("#enhance-progress").style.display = "none";
      toast("❌ " + err);
    },
    "#enhance-progress .progress-fill",
    "#enhance-progress .progress-msg"
  );
}

// ── STEP 3: Background removal & AI edits ────────────
async function removeBg() {
  const btn = qs("#btn-remove-bg");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 切り抜き中…`;
  qs("#bg-remove-progress").style.display = "block";

  const { job_id } = await apiFetch(`/session/${state.sessionId}/remove_bg`, { method: "POST" });
  pollJob(job_id,
    () => {
      refreshPreview();
      btn.disabled = false;
      btn.innerHTML = "✂️ 背景を除去する";
      qs("#bg-remove-progress").style.display = "none";
      toast("✅ 背景を除去しました");
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = "✂️ 背景を除去する";
      qs("#bg-remove-progress").style.display = "none";
      toast("❌ " + err);
    },
    "#bg-remove-progress .progress-fill",
    "#bg-remove-progress .progress-msg"
  );
}

async function runGeminiEdit(endpoint, btnSel, label) {
  const btn = qs(btnSel);
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> AI処理中…`;

  await apiFetch(`/session/${state.sessionId}/snapshot`, { method: "POST" });
  const { job_id } = await apiFetch(`/session/${state.sessionId}/${endpoint}`, { method: "POST" });

  pollJob(job_id,
    () => {
      refreshPreview();
      btn.disabled = false;
      btn.innerHTML = label;
      toast("✅ 処理が完了しました");
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = label;
      toast("❌ " + err);
    }
  );
}

async function applyClothingPreset(prompt) {
  const btn = qs("#btn-apply-preset");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`; }

  await apiFetch(`/session/${state.sessionId}/snapshot`, { method: "POST" });
  const { job_id } = await apiFetch(`/session/${state.sessionId}/clothing`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });

  pollJob(job_id,
    () => {
      refreshPreview();
      if (btn) { btn.disabled = false; btn.innerHTML = "適用"; }
      toast("✅ 衣装を変更しました");
    },
    err => {
      if (btn) { btn.disabled = false; btn.innerHTML = "適用"; }
      toast("❌ " + err);
    }
  );
}

async function applyCustomClothing() {
  const instruction = qs("#custom-clothing-input").value.trim();
  if (!instruction) { toast("指示を入力してください"); return; }

  const btn = qs("#btn-custom-clothing");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> AI処理中…`;

  await apiFetch(`/session/${state.sessionId}/snapshot`, { method: "POST" });
  const { job_id } = await apiFetch(`/session/${state.sessionId}/clothing`, {
    method: "POST",
    body: JSON.stringify({ prompt: instruction }),
  });

  pollJob(job_id,
    () => {
      refreshPreview();
      btn.disabled = false;
      btn.innerHTML = "適用する";
      toast("✅ 衣装を変更しました");
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = "適用する";
      toast("❌ " + err);
    }
  );
}

// ── STEP 4: Background color & swatch ────────────────
function initBgSwatches() {
  qsa(".bg-swatch[data-color]").forEach(sw => {
    sw.addEventListener("click", () => {
      qsa(".bg-swatch").forEach(s => s.classList.remove("selected"));
      sw.classList.add("selected");
      state.bgColor = sw.dataset.color;
    });
  });

  const customInput = qs("#swatch-custom-input");
  if (customInput) {
    customInput.addEventListener("input", () => {
      state.bgColor = customInput.value;
      qs(".bg-swatch-custom").style.background = customInput.value;
      qsa(".bg-swatch").forEach(s => s.classList.remove("selected"));
      qs(".bg-swatch-custom").classList.add("selected");
    });
  }
}

// ── STEP 5a: Photo output ─────────────────────────────
function initSizeOptions() {
  fetch("/sizes").then(r => r.json()).then(sizes => {
    const container = qs("#size-options");
    container.innerHTML = "";
    sizes.forEach((s, i) => {
      const div = document.createElement("div");
      div.className = "size-option" + (i === 0 ? " selected" : "");
      div.dataset.id = s.id;
      div.innerHTML = `
        <input type="radio" name="size" value="${s.id}" ${i === 0 ? "checked" : ""}>
        <div class="size-option-info">
          <div class="size-option-label">${s.label}</div>
          <div class="size-option-px">${s.px_w}×${s.px_h}px（${s.width_mm}×${s.height_mm}mm / ${s.dpi}dpi）</div>
        </div>`;
      div.addEventListener("click", () => {
        qsa(".size-option").forEach(o => o.classList.remove("selected"));
        div.classList.add("selected");
        div.querySelector("input").checked = true;
        state.selectedSizeId = s.id;
      });
      container.appendChild(div);
    });
    if (sizes.length > 0) state.selectedSizeId = sizes[0].id;
  });
}

async function downloadPhoto() {
  if (!state.selectedSizeId) { toast("サイズを選択してください"); return; }
  const btn = qs("#btn-download-photo");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 生成中…`;

  const body = {
    size_id: state.selectedSizeId,
    bg_color: state.bgColor,
    quality: 95,
  };

  const r = await fetch(`/session/${state.sessionId}/download_photo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!r.ok) {
    const e = await r.json();
    toast("❌ " + (e.error || "エラー"));
    btn.disabled = false;
    btn.innerHTML = "ダウンロード";
    return;
  }

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const cd = r.headers.get("Content-Disposition") || "";
  a.download = cd.match(/filename\*?=["']?([^"';]+)/)?.[1] || "photo.jpg";
  a.click();
  URL.revokeObjectURL(url);

  btn.disabled = false;
  btn.innerHTML = "ダウンロード";
  toast("✅ 保存しました");
}

async function printA3nobi() {
  const btn = qs("#btn-print-a3");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 生成中…`;

  const r = await fetch(`/session/${state.sessionId}/print_a3nobi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bg_color: state.bgColor }),
  });

  if (!r.ok) {
    const e = await r.json();
    toast("❌ " + (e.error || "エラー"));
    btn.disabled = false;
    btn.innerHTML = "A3ノビ印刷";
    return;
  }

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const w = window.open("", "_blank");
  w.document.write(`<html><head><title>印刷プレビュー</title>
    <style>@page{size:329mm 483mm;margin:0}body{margin:0}img{width:100%;display:block}</style></head>
    <body><img src="${url}" onload="setTimeout(()=>window.print(),400)"></body></html>`);

  btn.disabled = false;
  btn.innerHTML = "A3ノビ印刷";
}

async function printA5(mode) {
  const btn = mode === "cabinet" ? qs("#btn-print-a5-cab") : qs("#btn-print-a5-mini");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>`;

  const r = await fetch(`/session/${state.sessionId}/print_a5`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bg_color: state.bgColor, mode }),
  });

  if (!r.ok) {
    const e = await r.json();
    toast("❌ " + (e.error || "エラー"));
    btn.disabled = false;
    btn.innerHTML = mode === "cabinet" ? "A5キャビネ" : "A5 mini";
    return;
  }

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const w = window.open("", "_blank");
  w.document.write(`<html><head><title>印刷プレビュー</title>
    <style>@page{size:148mm 210mm;margin:0}body{margin:0}img{width:100%;display:block}</style></head>
    <body><img src="${url}" onload="setTimeout(()=>window.print(),400)"></body></html>`);

  btn.disabled = false;
  btn.innerHTML = mode === "cabinet" ? "A5キャビネ" : "A5 mini";
}

// ── STEP 5b: Video output ─────────────────────────────
function initVideoSettings() {
  const durInput = qs("#video-duration");
  const fadeInput = qs("#video-fade");
  if (durInput) {
    durInput.value = state.videoDuration;
    durInput.addEventListener("change", () => state.videoDuration = parseFloat(durInput.value));
  }
  if (fadeInput) {
    fadeInput.value = state.videoFade;
    fadeInput.addEventListener("change", () => state.videoFade = parseFloat(fadeInput.value));
  }
}

function initBgUpload() {
  const zone = qs("#bg-upload-zone");
  const input = qs("#bg-file-input");
  if (!zone || !input) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.style.background = "var(--orange-faint)"; });
  zone.addEventListener("dragleave", () => zone.style.background = "");
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.style.background = "";
    uploadBgFiles([...e.dataTransfer.files]);
  });
  input.addEventListener("change", e => uploadBgFiles([...e.target.files]));
}

async function uploadBgFiles(files) {
  if (files.length === 0) return;
  const fd = new FormData();
  files.forEach(f => fd.append("files", f));
  const r = await fetch(`/session/${state.sessionId}/upload_bg`, { method: "POST", body: fd });
  const data = await r.json();
  state.bgFiles = [...state.bgFiles, ...data.names];
  renderBgThumbs();
}

function renderBgThumbs() {
  const container = qs("#bg-thumbs");
  container.innerHTML = "";
  state.bgFiles.forEach((name, i) => {
    const img = document.createElement("img");
    img.className = "bg-thumb selected";
    img.src = `/session/${state.sessionId}/preview?name=${name}`;
    img.title = `背景 ${i + 1}`;
    img.addEventListener("click", () => img.classList.toggle("selected"));
    container.appendChild(img);
  });
}

async function generateVideo() {
  const selected = qsa("#bg-thumbs .bg-thumb.selected");
  if (selected.length === 0) { toast("背景素材を選択してください"); return; }

  const selectedNames = [...selected].map(img => {
    const src = img.src;
    const m = src.match(/name=([^&]+)/);
    return m ? m[1] : null;
  }).filter(Boolean);

  const btn = qs("#btn-gen-video");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> 動画を生成中…`;
  qs("#video-progress").style.display = "block";

  const { job_id } = await apiFetch(`/session/${state.sessionId}/compose_video`, {
    method: "POST",
    body: JSON.stringify({
      bg_names: selectedNames,
      duration_per_bg: state.videoDuration,
      fade_duration: state.videoFade,
      fps: 24,
    }),
  });

  pollJob(job_id,
    result => {
      btn.disabled = false;
      btn.innerHTML = "動画を生成する";
      qs("#video-progress").style.display = "none";
      if (result && result.filename) {
        qs("#btn-download-video").style.display = "inline-flex";
        qs("#btn-download-video").dataset.filename = result.filename;
        toast("✅ 動画が完成しました");
      }
    },
    err => {
      btn.disabled = false;
      btn.innerHTML = "動画を生成する";
      qs("#video-progress").style.display = "none";
      toast("❌ " + err);
    },
    "#video-progress .progress-fill",
    "#video-progress .progress-msg"
  );
}

function downloadVideo() {
  const btn = qs("#btn-download-video");
  const fname = btn.dataset.filename;
  if (!fname) return;
  window.location = `/session/${state.sessionId}/download_video?filename=${encodeURIComponent(fname)}`;
}

// ── Output tab switching ──────────────────────────────
function switchOutputTab(mode, el) {
  qsa(".output-tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");
  qsa(".output-tab-content").forEach(c => c.classList.remove("active"));
  qs(`#out-tab-${mode}`).classList.add("active");
}

// ── Before/After comparison slider ───────────────────
function initCompareSlider() {
  const wrap = qs("#compare-wrap");
  const handle = qs("#compare-handle");
  const before = qs("#compare-before");
  let dragging = false;

  handle.addEventListener("mousedown", () => dragging = true);
  document.addEventListener("mouseup", () => dragging = false);
  document.addEventListener("mousemove", e => {
    if (!dragging) return;
    const rect = wrap.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const pct = x / rect.width * 100;
    handle.style.left = pct + "%";
    before.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
  });
}

// ── Compare toggle ────────────────────────────────────
async function toggleCompare(btnSel) {
  const cw = qs("#compare-wrap");
  if (cw.classList.contains("visible")) {
    cw.classList.remove("visible");
    qs("#preview-img").style.display = "block";
    return;
  }
  // Load before/after
  qs("#compare-after").src = previewUrl("current.png") + "&t=" + Date.now();
  qs("#compare-before").src = previewUrl("before.png") + "&t=" + Date.now();
  qs("#preview-img").style.display = "none";
  cw.classList.add("visible");
}

// ── Start modal ───────────────────────────────────────
function initStartModal() {
  const modal = qs("#start-modal");
  qs("#btn-start-confirm").addEventListener("click", () => {
    state.outputChoices = {
      yotsugiri: qs("#cb-yotsugiri").checked ? parseInt(qs("#qty-yotsugiri").value) || 1 : 0,
      cabinet:   qs("#cb-cabinet").checked   ? parseInt(qs("#qty-cabinet").value)   || 1 : 0,
      mini:      qs("#cb-mini").checked      ? parseInt(qs("#qty-mini").value)       || 3 : 0,
      video:     qs("#cb-video").checked,
    };
    modal.classList.add("hidden");
    qs("#step-5-video-tab").style.display = state.outputChoices.video ? "" : "none";
  });
}

// ── Settings modal ────────────────────────────────────
function openSettings() {
  qs("#settings-modal").classList.remove("hidden");
  loadSettingsForm();
  loadSizesTable();
  loadPresetsTable();
}
function closeSettings() {
  qs("#settings-modal").classList.add("hidden");
}

async function loadSettingsForm() {
  const cfg = await apiFetch("/settings");
  qs("#cfg-gemini-key").value         = cfg.gemini_api_key || "";
  qs("#cfg-gemini-image-model").value = cfg.gemini_image_model || "gemini-2.0-flash-exp-image-generation";
  qs("#cfg-nas-out").value            = cfg.nas_output_path || "";
  qs("#cfg-nas-in").value             = cfg.nas_input_path || "";
  qs("#cfg-nas-bg").value             = cfg.nas_bg_assets_path || "";
  qs("#cfg-vid-dur").value            = cfg.video_duration_per_bg ?? 45;
  qs("#cfg-vid-fade").value           = cfg.video_fade_duration ?? 3;
}

async function saveSettings() {
  const cfg = {
    gemini_api_key:      qs("#cfg-gemini-key").value.trim(),
    gemini_image_model:  qs("#cfg-gemini-image-model").value.trim() || "gemini-2.0-flash-exp-image-generation",
    gemini_text_model:   "gemini-2.0-flash",
    nas_output_path:     qs("#cfg-nas-out").value.trim(),
    nas_input_path:      qs("#cfg-nas-in").value.trim(),
    nas_bg_assets_path:  qs("#cfg-nas-bg").value.trim(),
    video_duration_per_bg: parseFloat(qs("#cfg-vid-dur").value),
    video_fade_duration: parseFloat(qs("#cfg-vid-fade").value),
    video_fps: 24,
    default_bg_color: "#ffffff",
  };
  await apiFetch("/settings", { method: "POST", body: JSON.stringify(cfg) });
  state.videoDuration = cfg.video_duration_per_bg;
  state.videoFade     = cfg.video_fade_duration;
  initVideoSettings();
  toast("✅ 設定を保存しました");
}

async function loadSizesTable() {
  const sizes = await apiFetch("/sizes");
  const tbody = qs("#sizes-tbody");
  tbody.innerHTML = sizes.map(s => `
    <tr>
      <td>${s.label}</td>
      <td>${s.width_mm}×${s.height_mm}mm</td>
      <td>${s.dpi}</td>
      <td>${s.px_w}×${s.px_h}px</td>
      <td>${s.filename || s.id}</td>
      <td>
        <button class="btn btn-sm btn-secondary" onclick="editSize('${s.id}')">編集</button>
        <button class="btn btn-sm btn-danger" onclick="deleteSize('${s.id}')">削除</button>
      </td>
    </tr>`).join("");
}

async function deleteSize(id) {
  if (!confirm("このサイズを削除しますか？")) return;
  await apiFetch(`/sizes/${id}`, { method: "DELETE" });
  loadSizesTable();
  initSizeOptions();
  toast("削除しました");
}

function editSize(id) {
  // Reuse add modal pre-filled
  fetch("/sizes").then(r => r.json()).then(sizes => {
    const s = sizes.find(x => x.id === id);
    if (!s) return;
    qs("#size-form-label").value    = s.label;
    qs("#size-form-w").value        = s.width_mm;
    qs("#size-form-h").value        = s.height_mm;
    qs("#size-form-dpi").value      = s.dpi;
    qs("#size-form-filename").value = s.filename || "";
    qs("#size-form-modal").classList.remove("hidden");
    qs("#btn-save-size").onclick = async () => {
      const body = {
        label:     qs("#size-form-label").value,
        width_mm:  parseFloat(qs("#size-form-w").value),
        height_mm: parseFloat(qs("#size-form-h").value),
        dpi:       parseInt(qs("#size-form-dpi").value),
        filename:  qs("#size-form-filename").value,
      };
      await apiFetch(`/sizes/${id}`, { method: "PUT", body: JSON.stringify(body) });
      qs("#size-form-modal").classList.add("hidden");
      loadSizesTable();
      initSizeOptions();
      toast("✅ サイズを更新しました");
    };
  });
}

function openAddSizeModal() {
  qs("#size-form-label").value    = "";
  qs("#size-form-w").value        = "";
  qs("#size-form-h").value        = "";
  qs("#size-form-dpi").value      = "350";
  qs("#size-form-filename").value = "";
  qs("#size-form-modal").classList.remove("hidden");
  qs("#btn-save-size").onclick = async () => {
    const body = {
      label:     qs("#size-form-label").value,
      width_mm:  parseFloat(qs("#size-form-w").value),
      height_mm: parseFloat(qs("#size-form-h").value),
      dpi:       parseInt(qs("#size-form-dpi").value),
      filename:  qs("#size-form-filename").value,
    };
    await apiFetch("/sizes", { method: "POST", body: JSON.stringify(body) });
    qs("#size-form-modal").classList.add("hidden");
    loadSizesTable();
    initSizeOptions();
    toast("✅ サイズを追加しました");
  };
}

async function loadPresetsTable() {
  const presets = await apiFetch("/clothing_presets");
  ["formal", "casual"].forEach(cat => {
    const tbody = qs(`#presets-tbody-${cat}`);
    tbody.innerHTML = (presets[cat] || []).map(p => `
      <tr>
        <td>${p.label}</td>
        <td style="color:var(--gray-mid);font-size:11px">${p.prompt.substring(0, 40)}…</td>
        <td>
          <button class="btn btn-sm btn-danger" onclick="deletePreset('${cat}','${p.id}')">削除</button>
        </td>
      </tr>`).join("");
  });
  renderPresetButtons();
}

async function deletePreset(cat, pid) {
  await apiFetch(`/clothing_presets/${cat}/${pid}`, { method: "DELETE" });
  loadPresetsTable();
  toast("削除しました");
}

async function renderPresetButtons() {
  const presets = await apiFetch("/clothing_presets");
  ["formal", "casual"].forEach(cat => {
    const grid = qs(`#preset-grid-${cat}`);
    if (!grid) return;
    grid.innerHTML = (presets[cat] || []).map(p => `
      <button class="preset-btn" onclick="applyClothingPreset(${JSON.stringify(p.prompt)})">
        <span class="preset-label">${cat === "formal" ? "フォーマル" : "カジュアル"}</span>
        ${p.label}
      </button>`).join("");
  });
}

// ── Init ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initEnhanceSliders();
  initBgSwatches();
  initSizeOptions();
  initCompareSlider();
  initBgUpload();
  initVideoSettings();
  initStartModal();

  // Step tab clicks
  qsa(".step-tab").forEach((tab, i) => {
    tab.addEventListener("click", () => goToStep(i + 1));
  });

  // Start modal auto-open
  setTimeout(() => qs("#start-modal").classList.remove("hidden"), 300);
});
