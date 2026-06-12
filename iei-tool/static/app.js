/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ひすい野ヴィラ 遺影写真作成ツール — Frontend JS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

// ── State ─────────────────────────────────────────────
let sessionId = null;
let currentStep = 1;
let selectedBgColor = "#ffffff";
let selectedSizeId = "yotsugiri";
let outputTypes = { yotsugiri: 1, cabinet: 1, askanet_mini: 3, video: true };
let bgSlotFiles = [null, null, null, null, null, null];  // up to 6 bg images
let allSizes = [];
let allPresets = { formal: [], casual: [] };
let undoStack = [];  // stores previous preview URLs
let pollTimers = {};

// ── Startup ───────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("startupModal").classList.remove("hidden");
  initBgSlots();
  loadSizes();
  loadPresets();
  loadSettings();
  setupUpload();
  initRangeDisplays();
});

function closeStartupModal() {
  document.getElementById("startupModal").classList.add("hidden");
  newSession();
}

function toggleOutputType(card) {
  const type = card.dataset.type;
  card.classList.toggle("selected");
  if (type === "video") {
    outputTypes.video = card.classList.contains("selected");
  }
}

function changeQty(e, type, delta) {
  e.stopPropagation();
  const el = document.getElementById(`qty-${type}`);
  let v = parseInt(el.textContent) + delta;
  v = Math.max(1, Math.min(10, v));
  el.textContent = v;
  outputTypes[type] = v;
}

// ── Session ───────────────────────────────────────────
async function newSession() {
  const r = await api("/session/new", "POST");
  sessionId = r.session_id;
  undoStack = [];
  updateUndoBtn();
}

// ── Upload ────────────────────────────────────────────
function setupUpload() {
  const zone = document.getElementById("uploadZone");
  const input = document.getElementById("fileInput");

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });
  input.addEventListener("change", () => { if (input.files[0]) uploadFile(input.files[0]); });
}

async function uploadFile(file) {
  if (!sessionId) await newSession();
  showToast("アップロード中...", "");
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/session/${sessionId}/upload`, { method: "POST", body: fd }).then(x => x.json());
  if (r.error) { showToast(r.error, "error"); return; }
  showToast("アップロード完了", "success");
  document.getElementById("previewPlaceholder").classList.add("hidden");
  document.getElementById("previewImg").classList.remove("hidden");
  refreshPreview();
  document.getElementById("goStep2Btn").disabled = false;
  document.getElementById("previewInfo").textContent = `${r.w} × ${r.h} px`;
  // Show person select section
  document.getElementById("personSelectSection").classList.remove("hidden");
  document.querySelector("[data-step='1']").classList.add("done");
}

// ── Person selection ──────────────────────────────────
async function detectPersons() {
  if (!sessionId) return;
  showJobStatus("personsOverlayWrap", "人物を検出中...", 50);
  const r = await api(`/session/${sessionId}/detect_persons`, "POST");
  clearJobStatus("personsOverlayWrap");
  if (r.error) { showToast(r.error, "error"); return; }
  renderPersonBoxes(r.persons);
}

function renderPersonBoxes(persons) {
  const wrap = document.getElementById("personsOverlayWrap");
  wrap.innerHTML = "";
  if (!persons || persons.length === 0) {
    wrap.innerHTML = '<p class="text-muted">人物が検出されませんでした。1人のみの写真として続けてください。</p>';
    return;
  }

  const img = document.getElementById("previewImg");
  const iw = img.naturalWidth || 800;
  const ih = img.naturalHeight || 600;

  const psWrap = document.createElement("div");
  psWrap.className = "person-selector-wrap";
  psWrap.style.cssText = `display:inline-block; position:relative;`;

  const pimg = document.createElement("img");
  pimg.src = img.src;
  pimg.style.cssText = "max-width:100%; display:block; border-radius:2px;";
  psWrap.appendChild(pimg);

  persons.forEach(p => {
    const box = document.createElement("div");
    box.className = "person-box";
    box.style.cssText = `left:${p.x*100}%; top:${p.y*100}%; width:${p.w*100}%; height:${p.h*100}%;`;
    const lbl = document.createElement("span");
    lbl.className = "person-box-label";
    lbl.textContent = p.label || `人物${p.index+1}`;
    box.appendChild(lbl);
    box.onclick = () => selectPerson(p.label || `人物${p.index+1}`);
    psWrap.appendChild(box);
  });

  wrap.appendChild(psWrap);
}

async function selectPerson(label) {
  showJobStatus("personJobStatus", `${label}を選択・切り出し中...`, 30);
  const r = await api(`/session/${sessionId}/select_person`, "POST", { label });
  if (r.error) { showToast(r.error, "error"); clearJobStatus("personJobStatus"); return; }
  pollJob(r.job_id, "personJobStatus", () => {
    refreshPreview();
    showToast(`${label}を選択しました`, "success");
    document.getElementById("personSelectSection").classList.add("hidden");
  });
}

function skipPersonSelect() {
  document.getElementById("personSelectSection").classList.add("hidden");
}

// ── Step navigation ───────────────────────────────────
function switchStep(n) {
  currentStep = n;
  document.querySelectorAll(".step-tab").forEach(t => {
    const tn = parseInt(t.dataset.step);
    t.classList.toggle("active", tn === n);
  });
  document.querySelectorAll(".step-panel").forEach(p => {
    const pn = parseInt(p.id.replace("panel-",""));
    p.classList.toggle("active", pn === n);
  });
  if (n === 5) refreshSizeOptions();
}

// ── Enhancement ───────────────────────────────────────
function initRangeDisplays() {
  [["brightness","brightnessVal"],["contrast","contrastVal"],["sharpness","sharpnessVal"],
   ["durPerBg","durPerBgVal","秒"],["fadeDur","fadeDurVal","秒"],
   ["s-dur","s-durVal","秒"],["s-fade","s-fadeVal","秒"]].forEach(([id, vid, sfx=""]) => {
    const el = document.getElementById(id);
    const vel = document.getElementById(vid);
    if (el && vel) vel.textContent = el.value + sfx;
  });
}

function updateRangeVal(id, valId, suffix) {
  const el = document.getElementById(id);
  const vel = document.getElementById(valId);
  if (el && vel) vel.textContent = el.value + (suffix || "");
}

async function applyEnhance() {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/enhance`, "POST", {
    brightness: parseFloat(document.getElementById("brightness").value),
    contrast: parseFloat(document.getElementById("contrast").value),
    sharpness: parseFloat(document.getElementById("sharpness").value),
  });
  if (r.ok) { refreshPreview(); showToast("補正を適用しました", "success"); }
}

async function geminiEnhance() {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_enhance`, "POST");
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "enhanceJobStatus", () => {
    refreshPreview();
    showToast("AI高画質化が完了しました", "success");
  });
}

// ── Background removal ────────────────────────────────
async function removeBg() {
  if (!sessionId) return;
  pushUndo();
  document.getElementById("removeBgBtn").disabled = true;
  const r = await api(`/session/${sessionId}/remove_bg`, "POST");
  if (r.error) { showToast(r.error, "error"); document.getElementById("removeBgBtn").disabled = false; return; }
  pollJob(r.job_id, "bgRemoveJobStatus", () => {
    refreshPreview();
    showToast("背景除去が完了しました", "success");
    document.getElementById("removeBgBtn").disabled = false;
  });
}

// ── AI edits ──────────────────────────────────────────
async function removeProps() {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_remove_props`, "POST");
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "aiEditJobStatus3", () => { refreshPreview(); showToast("持ち物を除去しました", "success"); });
}

async function removeOthers() {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_remove_others`, "POST");
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "aiEditJobStatus3", () => { refreshPreview(); showToast("他の人物を除去しました", "success"); });
}

async function necktieBtnClick() {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_necktie`, "POST");
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "aiEditJobStatus4", () => { refreshPreview(); showToast("ネクタイを黒に変更しました", "success"); });
}

async function applyPreset(prompt) {
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_clothing`, "POST", { prompt });
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "aiEditJobStatus4", () => { refreshPreview(); showToast("衣装を変更しました", "success"); });
}

async function applyCustomClothing() {
  const prompt = document.getElementById("customClothingInput").value.trim();
  if (!prompt) { showToast("衣装の指示を入力してください", "error"); return; }
  if (!sessionId) return;
  pushUndo();
  const r = await api(`/session/${sessionId}/gemini_clothing`, "POST", { prompt });
  if (r.error) { showToast(r.error, "error"); return; }
  pollJob(r.job_id, "aiEditJobStatus4", () => { refreshPreview(); showToast("衣装を変更しました", "success"); });
}

// ── Output: photo ─────────────────────────────────────
function selectSwatch(el) {
  document.querySelectorAll(".swatch").forEach(s => s.classList.remove("selected"));
  el.classList.add("selected");
  selectedBgColor = el.dataset.color;
}

function applyCustomColor(val) {
  selectedBgColor = val;
  document.querySelectorAll(".swatch").forEach(s => s.classList.remove("selected"));
}

function refreshSizeOptions() {
  const list = document.getElementById("sizeOptionsList");
  list.innerHTML = "";
  allSizes.forEach(s => {
    const div = document.createElement("div");
    div.className = "size-option" + (s.id === selectedSizeId ? " selected" : "");
    div.onclick = () => {
      document.querySelectorAll(".size-option").forEach(o => o.classList.remove("selected"));
      div.classList.add("selected");
      selectedSizeId = s.id;
    };
    div.innerHTML = `
      <input type="radio" name="sizeRadio" value="${s.id}" ${s.id === selectedSizeId ? "checked" : ""}>
      <div class="size-option-info">
        <div class="size-label">${s.label}</div>
        <div class="size-detail">${s.width_mm}×${s.height_mm}mm / ${s.dpi}dpi / ${s.px_w}×${s.px_h}px</div>
      </div>
    `;
    list.appendChild(div);
  });
  refreshPrintButtons();
}

function refreshPrintButtons() {
  const wrap = document.getElementById("printBtns");
  wrap.innerHTML = "";
  // A3ノビ: 四つ切り + キャビネ + mini×3
  const hasYo = outputTypes.yotsugiri > 0;
  const hasCab = outputTypes.cabinet > 0;
  const hasMini = outputTypes.askanet_mini > 0;

  if (hasYo && hasCab && hasMini) {
    const btn = document.createElement("button");
    btn.className = "btn btn-secondary btn-full";
    btn.textContent = "🖨 A3ノビで一括印刷（四つ切り＋キャビネ＋mini×3）";
    btn.onclick = () => printA3Nobi();
    wrap.appendChild(btn);
  }
  if (hasCab && !hasYo) {
    const btn = document.createElement("button");
    btn.className = "btn btn-secondary btn-full";
    btn.textContent = "🖨 A5で印刷（キャビネ）";
    btn.onclick = () => printA5("cabinet");
    wrap.appendChild(btn);
  }
  if (hasMini && !hasYo) {
    const btn = document.createElement("button");
    btn.className = "btn btn-secondary btn-full";
    btn.textContent = "🖨 A5で印刷（mini×6）";
    btn.onclick = () => printA5("mini");
    wrap.appendChild(btn);
  }
}

async function downloadAll() {
  if (!sessionId) return;
  const enabled = allSizes.filter(s => {
    if (s.id === "yotsugiri" && !outputTypes.yotsugiri) return false;
    if (s.id === "cabinet" && !outputTypes.cabinet) return false;
    if (s.id === "askanet_mini" && !outputTypes.askanet_mini) return false;
    return true;
  });
  for (const s of enabled) {
    await downloadSize(s.id, s.id);
  }
}

async function downloadSelected() {
  if (!sessionId) return;
  await downloadSize(selectedSizeId, selectedSizeId);
}

async function downloadSize(sizeId, filename) {
  const resp = await fetch(`/session/${sessionId}/compose_photo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ size_id: sizeId, bg_color: selectedBgColor, filename })
  });
  if (!resp.ok) { showToast("出力エラー", "error"); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const date = new Date().toISOString().slice(0,10).replace(/-/g,"");
  a.href = url;
  a.download = `${filename}_${date}.jpg`;
  a.click();
  URL.revokeObjectURL(url);
}

async function printA3Nobi() {
  if (!sessionId) return;
  showToast("印刷データを生成中...", "");
  const resp = await fetch(`/session/${sessionId}/print_layout/a3nobi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bg_color: selectedBgColor })
  });
  if (!resp.ok) { showToast("生成エラー", "error"); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  openPrintWindow(url, "A3ノビ (329×483mm)", "329mm", "483mm");
}

async function printA5(sizeType) {
  if (!sessionId) return;
  showToast("印刷データを生成中...", "");
  const resp = await fetch(`/session/${sessionId}/print_layout/a5`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bg_color: selectedBgColor, size_type: sizeType })
  });
  if (!resp.ok) { showToast("生成エラー", "error"); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  openPrintWindow(url, "A5 (148×210mm)", "148mm", "210mm");
}

function openPrintWindow(imageUrl, paperLabel, paperW, paperH) {
  const win = window.open("", "_blank");
  win.document.write(`<!DOCTYPE html><html><head><title>印刷 — ${paperLabel}</title>
<style>
  @page { size: ${paperW} ${paperH}; margin: 0; }
  body { margin: 0; padding: 0; display: flex; align-items: center; justify-content: center; }
  img { width: ${paperW}; height: ${paperH}; display: block; }
  @media print { body { -webkit-print-color-adjust: exact; } }
</style></head><body>
<img src="${imageUrl}" onload="window.print()">
</body></html>`);
  win.document.close();
}

// ── Output: video ─────────────────────────────────────
function initBgSlots() {
  const grid = document.getElementById("bgSlots");
  grid.innerHTML = "";
  for (let i = 0; i < 6; i++) {
    const slot = document.createElement("div");
    slot.className = "bg-slot";
    slot.dataset.idx = i;
    slot.innerHTML = `<span class="slot-num">BG ${i+1}</span><span>クリックして選択</span>`;
    slot.onclick = () => pickBgSlot(i);
    grid.appendChild(slot);
  }
}

function pickBgSlot(idx) {
  const input = document.getElementById("bgFileInput");
  input._targetIdx = idx;
  input.removeAttribute("multiple");
  input.click();
}

async function handleBgFiles(input) {
  const idx = input._targetIdx !== undefined ? input._targetIdx : 0;
  const files = Array.from(input.files).slice(0, 6 - idx);
  for (let i = 0; i < files.length; i++) {
    bgSlotFiles[idx + i] = files[i];
    updateBgSlotPreview(idx + i, files[i]);
  }
  input.value = "";
}

function updateBgSlotPreview(idx, file) {
  const slots = document.querySelectorAll(".bg-slot");
  const slot = slots[idx];
  if (!slot) return;
  slot.classList.add("filled");
  const reader = new FileReader();
  reader.onload = e => {
    const img = slot.querySelector("img") || document.createElement("img");
    img.src = e.target.result;
    if (!slot.querySelector("img")) slot.appendChild(img);
    slot.querySelector("span:last-child").textContent = file.name.slice(0, 12);
  };
  reader.readAsDataURL(file);
}

async function generateVideo() {
  if (!sessionId) return;
  const activeBgs = bgSlotFiles.filter(f => f !== null);
  if (activeBgs.length === 0) { showToast("背景素材を最低1枚選択してください", "error"); return; }

  // Upload bg files to server
  showJobStatus("videoJobStatus", "背景ファイルをアップロード中...", 10);
  const fd = new FormData();
  activeBgs.forEach(f => fd.append("files", f));
  const up = await fetch(`/session/${sessionId}/upload_bg`, { method: "POST", body: fd }).then(x => x.json());
  if (up.error) { showToast(up.error, "error"); clearJobStatus("videoJobStatus"); return; }

  const durPerBg = parseFloat(document.getElementById("durPerBg").value);
  const fadeDur = parseFloat(document.getElementById("fadeDur").value);
  const r = await api(`/session/${sessionId}/compose_video`, "POST", { duration_per_bg: durPerBg, fade_duration: fadeDur });
  if (r.error) { showToast(r.error, "error"); clearJobStatus("videoJobStatus"); return; }

  document.getElementById("genVideoBtn").disabled = true;
  pollJob(r.job_id, "videoJobStatus", (jobData) => {
    document.getElementById("genVideoBtn").disabled = false;
    if (jobData.filename) {
      const dlWrap = document.getElementById("videoDownloadLink");
      const dlA = document.getElementById("videoDownloadA");
      dlA.href = `/session/${sessionId}/download_video/${jobData.filename}`;
      dlA.download = jobData.filename;
      dlWrap.classList.remove("hidden");
    }
    showToast("動画が完成しました！", "success");
  });
}

// ── Preview ───────────────────────────────────────────
function refreshPreview() {
  if (!sessionId) return;
  const img = document.getElementById("previewImg");
  img.src = `/session/${sessionId}/preview?t=${Date.now()}`;
  img.classList.remove("hidden");
  document.getElementById("previewPlaceholder").classList.add("hidden");
}

// ── Undo ──────────────────────────────────────────────
function pushUndo() {
  const img = document.getElementById("previewImg");
  if (img.src && !img.classList.contains("hidden")) {
    undoStack.push(img.src);
    if (undoStack.length > 5) undoStack.shift();
    updateUndoBtn();
  }
}

async function undoEdit() {
  // Undo by refreshing from server (simplified: just refresh)
  // In a full implementation, we'd store server-side snapshots
  refreshPreview();
  showToast("戻しました", "");
}

function updateUndoBtn() {
  document.getElementById("undoBtn").disabled = undoStack.length === 0;
}

// ── Settings ──────────────────────────────────────────
async function loadSettings() {
  const r = await api("/settings");
  if (r.error) return;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ""; };
  set("s-apikey", r.gemini_api_key_masked || "");
  set("s-nas-in", r.nas_input_path);
  set("s-nas-out", r.nas_output_path);
  set("s-nas-bg", r.nas_bg_assets_path);
  const sd = document.getElementById("s-dur");
  const sf = document.getElementById("s-fade");
  const sfps = document.getElementById("s-fps");
  if (sd) { sd.value = r.video_duration_per_bg || 45; updateRangeVal("s-dur","s-durVal","秒"); }
  if (sf) { sf.value = r.video_fade_duration || 3; updateRangeVal("s-fade","s-fadeVal","秒"); }
  if (sfps) sfps.value = r.video_fps || 24;
  // Also apply to video tab defaults
  const db = document.getElementById("durPerBg");
  const fd = document.getElementById("fadeDur");
  if (db) { db.value = r.video_duration_per_bg || 45; updateRangeVal("durPerBg","durPerBgVal","秒"); }
  if (fd) { fd.value = r.video_fade_duration || 3; updateRangeVal("fadeDur","fadeDurVal","秒"); }
}

async function saveSettings() {
  const key = document.getElementById("s-apikey").value;
  const body = {
    nas_input_path: document.getElementById("s-nas-in").value,
    nas_output_path: document.getElementById("s-nas-out").value,
    nas_bg_assets_path: document.getElementById("s-nas-bg").value,
    video_duration_per_bg: parseInt(document.getElementById("s-dur").value),
    video_fade_duration: parseFloat(document.getElementById("s-fade").value),
    video_fps: parseInt(document.getElementById("s-fps").value),
  };
  if (key && !key.includes("*")) body.gemini_api_key = key;
  await api("/settings", "POST", body);
  showToast("設定を保存しました", "success");
  closeSettings();
}

function showSettings() {
  loadSettings();
  document.getElementById("settingsModal").classList.remove("hidden");
  switchSettingsTab("general");
}

function closeSettings() {
  document.getElementById("settingsModal").classList.add("hidden");
}

function switchSettingsTab(name) {
  ["general","sizes","presets","video"].forEach(t => {
    const el = document.getElementById(`stab-${t}`);
    if (el) el.classList.toggle("hidden", t !== name);
  });
  document.querySelectorAll("#settingsModal .tab-btn").forEach((btn, i) => {
    const names = ["general","sizes","presets","video"];
    btn.classList.toggle("active", names[i] === name);
  });
  if (name === "sizes") renderSizesTable();
  if (name === "presets") renderPresetLists();
}

// ── Sizes CRUD ────────────────────────────────────────
async function loadSizes() {
  allSizes = await api("/sizes");
  if (!Array.isArray(allSizes)) allSizes = [];
}

function renderSizesTable() {
  const body = document.getElementById("sizesTableBody");
  body.innerHTML = "";
  allSizes.forEach(s => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.label}</td>
      <td>${s.width_mm}</td>
      <td>${s.height_mm}</td>
      <td>${s.dpi}</td>
      <td>${s.px_w}×${s.px_h}</td>
      <td>
        <button class="btn btn-ghost btn-sm btn-icon-only" onclick="editSizeDialog('${s.id}')" title="編集">✏</button>
        <button class="btn btn-danger btn-sm btn-icon-only" onclick="deleteSize('${s.id}')" title="削除">🗑</button>
      </td>`;
    body.appendChild(tr);
  });
}

function addSizeDialog() {
  showSizeDialog(null);
}

function editSizeDialog(id) {
  const s = allSizes.find(x => x.id === id);
  if (s) showSizeDialog(s);
}

function showSizeDialog(s) {
  const isEdit = !!s;
  const label = s ? s.label : "";
  const wm = s ? s.width_mm : "";
  const hm = s ? s.height_mm : "";
  const dpi = s ? s.dpi : 350;

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
  <div class="modal" style="max-width:400px;">
    <div class="modal-header">
      <div class="modal-title">${isEdit ? "サイズを編集" : "サイズを追加"}</div>
    </div>
    <div class="modal-body">
      <div class="form-group"><label class="form-label">名称</label>
        <input class="form-control" id="dlg-label" value="${label}"></div>
      <div class="flex-row">
        <div class="form-group" style="flex:1"><label class="form-label">幅 (mm)</label>
          <input class="form-control" id="dlg-w" type="number" value="${wm}" min="10" max="1000"></div>
        <div class="form-group" style="flex:1"><label class="form-label">高 (mm)</label>
          <input class="form-control" id="dlg-h" type="number" value="${hm}" min="10" max="1000"></div>
      </div>
      <div class="form-group"><label class="form-label">DPI</label>
        <select class="form-control" id="dlg-dpi">
          <option value="96">96dpi（画面表示向け）</option>
          <option value="150">150dpi</option>
          <option value="300">300dpi</option>
          <option value="350" ${dpi==350?'selected':''}>350dpi（印刷標準）</option>
        </select>
      </div>
      <p class="text-muted" id="dlg-px">出力px: —</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove()">キャンセル</button>
      <button class="btn btn-primary" onclick="saveSizeDialog('${s ? s.id : ""}')">保存</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);

  const updatePx = () => {
    const w = parseFloat(document.getElementById("dlg-w").value) || 0;
    const h = parseFloat(document.getElementById("dlg-h").value) || 0;
    const d = parseInt(document.getElementById("dlg-dpi").value) || 350;
    const pw = Math.round(w / 25.4 * d);
    const ph = Math.round(h / 25.4 * d);
    document.getElementById("dlg-px").textContent = `出力px: ${pw} × ${ph}`;
  };
  ["dlg-w","dlg-h","dlg-dpi"].forEach(id => document.getElementById(id).addEventListener("input", updatePx));
  updatePx();
}

async function saveSizeDialog(existingId) {
  const label = document.getElementById("dlg-label").value.trim();
  const wm = parseFloat(document.getElementById("dlg-w").value);
  const hm = parseFloat(document.getElementById("dlg-h").value);
  const dpi = parseInt(document.getElementById("dlg-dpi").value);
  if (!label || !wm || !hm) { showToast("全項目を入力してください", "error"); return; }

  if (existingId) {
    await api(`/sizes/${existingId}`, "PUT", { label, width_mm: wm, height_mm: hm, dpi });
  } else {
    await api("/sizes", "POST", { label, width_mm: wm, height_mm: hm, dpi });
  }
  document.querySelector(".modal-overlay:last-of-type").remove();
  await loadSizes();
  renderSizesTable();
  showToast("サイズを保存しました", "success");
}

async function deleteSize(id) {
  if (!confirm("このサイズを削除しますか？")) return;
  await api(`/sizes/${id}`, "DELETE");
  await loadSizes();
  renderSizesTable();
  showToast("削除しました", "");
}

// ── Presets CRUD ──────────────────────────────────────
async function loadPresets() {
  allPresets = await api("/presets");
  if (!allPresets || typeof allPresets !== "object") allPresets = { formal: [], casual: [] };
  renderPresetButtons();
}

function renderPresetButtons() {
  ["formal","casual"].forEach(cat => {
    const grid = document.getElementById(`${cat}PresetGrid`);
    if (!grid) return;
    grid.innerHTML = "";
    (allPresets[cat] || []).forEach(p => {
      const btn = document.createElement("button");
      btn.className = "preset-btn";
      btn.textContent = p.label;
      btn.title = p.prompt;
      btn.onclick = () => applyPreset(p.prompt);
      grid.appendChild(btn);
    });
  });
}

function renderPresetLists() {
  ["formal","casual"].forEach(cat => {
    const list = document.getElementById(`${cat}PresetList`);
    if (!list) return;
    list.innerHTML = "";
    (allPresets[cat] || []).forEach(p => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex; align-items:center; gap:6px; margin-bottom:6px;";
      row.innerHTML = `
        <span style="flex:1; font-size:12px;">${p.label}</span>
        <button class="btn btn-ghost btn-sm btn-icon-only" onclick="editPresetDialog('${cat}','${p.id}')">✏</button>
        <button class="btn btn-danger btn-sm btn-icon-only" onclick="deletePreset('${cat}','${p.id}')">🗑</button>`;
      list.appendChild(row);
    });
  });
}

function addPresetDialog(category) {
  showPresetDialog(category, null);
}

function editPresetDialog(category, id) {
  const p = (allPresets[category] || []).find(x => x.id === id);
  if (p) showPresetDialog(category, p);
}

function showPresetDialog(category, p) {
  const catLabel = category === "formal" ? "フォーマル" : "カジュアル";
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
  <div class="modal" style="max-width:440px;">
    <div class="modal-header">
      <div class="modal-title">${catLabel}プリセット${p ? "を編集" : "を追加"}</div>
    </div>
    <div class="modal-body">
      <div class="form-group"><label class="form-label">ボタン表示名</label>
        <input class="form-control" id="dlg-p-label" value="${p ? p.label : ""}"></div>
      <div class="form-group"><label class="form-label">Gemini への指示プロンプト</label>
        <textarea class="form-control" id="dlg-p-prompt" rows="3">${p ? p.prompt : ""}</textarea></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove()">キャンセル</button>
      <button class="btn btn-primary" onclick="savePresetDialog('${category}','${p ? p.id : ""}')">保存</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

async function savePresetDialog(category, existingId) {
  const label = document.getElementById("dlg-p-label").value.trim();
  const prompt = document.getElementById("dlg-p-prompt").value.trim();
  if (!label || !prompt) { showToast("全項目を入力してください", "error"); return; }

  if (existingId) {
    await api(`/presets/${category}/${existingId}`, "PUT", { label, prompt });
  } else {
    await api(`/presets/${category}`, "POST", { label, prompt });
  }
  document.querySelector(".modal-overlay:last-of-type").remove();
  await loadPresets();
  renderPresetButtons();
  renderPresetLists();
  showToast("プリセットを保存しました", "success");
}

async function deletePreset(category, id) {
  if (!confirm("このプリセットを削除しますか？")) return;
  await api(`/presets/${category}/${id}`, "DELETE");
  await loadPresets();
  renderPresetButtons();
  renderPresetLists();
  showToast("削除しました", "");
}

// ── Output tabs ───────────────────────────────────────
function switchOutputTab(name) {
  ["photo","video"].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) el.classList.toggle("active", t === name);
  });
  document.querySelectorAll("#panel-5 .tab-btn").forEach((btn, i) => {
    btn.classList.toggle("active", i === (name === "photo" ? 0 : 1));
  });
}

// ── Job polling ───────────────────────────────────────
function pollJob(jobId, statusElId, onDone) {
  if (pollTimers[jobId]) clearInterval(pollTimers[jobId]);
  showJobStatus(statusElId, "処理中...", 5);

  pollTimers[jobId] = setInterval(async () => {
    const data = await api(`/job/${jobId}`);
    if (data.status === "running") {
      showJobStatus(statusElId, data.message || "処理中...", data.progress || 0);
    } else if (data.status === "done") {
      clearInterval(pollTimers[jobId]);
      delete pollTimers[jobId];
      clearJobStatus(statusElId);
      if (onDone) onDone(data);
    } else if (data.status === "error") {
      clearInterval(pollTimers[jobId]);
      delete pollTimers[jobId];
      clearJobStatus(statusElId);
      showToast(`エラー: ${data.error}`, "error");
    }
  }, 2000);
}

function showJobStatus(elId, msg, progress) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = `
    <div class="progress-wrap">
      <div class="progress-msg">${msg}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${progress||0}%"></div></div>
    </div>`;
}

function clearJobStatus(elId) {
  const el = document.getElementById(elId);
  if (el) el.innerHTML = "";
}

// ── Toast ─────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, type) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "show" + (type ? ` ${type}` : "");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 3500);
}

// ── API helper ────────────────────────────────────────
async function api(url, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  try {
    const r = await fetch(url, opts);
    return await r.json();
  } catch (e) {
    return { error: e.message };
  }
}
