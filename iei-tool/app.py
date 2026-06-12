"""ひすい野ヴィラ 遺影写真作成ツール — Flask backend."""
import io
import json
import os
import shutil
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, abort
from PIL import Image

# ── Paths ────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
TMP = BASE / "tmp"
TMP.mkdir(exist_ok=True)

CONFIG_PATH = BASE / "config.json"
SIZES_PATH = BASE / "sizes.json"
PRESETS_PATH = BASE / "clothing_presets.json"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB


# ── Config helpers ────────────────────────────────────────────────────────────
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_sizes() -> list:
    with open(SIZES_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_sizes(data: list) -> None:
    with open(SIZES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_presets() -> dict:
    with open(PRESETS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_presets(data: dict) -> None:
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Session helpers ───────────────────────────────────────────────────────────
def session_dir(sid: str) -> Path:
    d = TMP / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_path(sid: str, name: str) -> Path:
    return session_dir(sid) / name


def load_session_img(sid: str, name: str = "current.png") -> Image.Image:
    p = session_path(sid, name)
    if not p.exists():
        abort(404, f"セッション画像が見つかりません: {name}")
    return Image.open(p)


def save_session_img(sid: str, img: Image.Image, name: str = "current.png") -> None:
    p = session_path(sid, name)
    if img.mode in ("RGBA", "LA"):
        img.save(p, format="PNG", optimize=True)
    else:
        img.convert("RGB").save(p, format="PNG", optimize=True)


# ── Job manager (for long-running background tasks) ───────────────────────────
class JobManager:
    def __init__(self):
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        jid = str(uuid.uuid4())[:8]
        with self._lock:
            self._jobs[jid] = {"status": "running", "progress": 0,
                                "message": "処理中...", "error": None}
        return jid

    def update(self, jid: str, **kw) -> None:
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].update(kw)

    def get(self, jid: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(jid, {"status": "not_found"}))

    def done(self, jid: str, message: str = "完了") -> None:
        self.update(jid, status="done", progress=100, message=message)

    def fail(self, jid: str, error: str) -> None:
        self.update(jid, status="error", error=error)


jobs = JobManager()


def _configure_gemini():
    cfg = load_config()
    key = cfg.get("gemini_api_key", "")
    if key:
        from modules.gemini_edit import configure
        configure(key)
    return key


# ── Utility ───────────────────────────────────────────────────────────────────
def _img_response(img: Image.Image, fmt: str = "JPEG", quality: int = 85):
    buf = io.BytesIO()
    if fmt == "PNG":
        img.save(buf, format="PNG", optimize=True)
    else:
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return send_file(buf, mimetype=mime)


def _preview(img: Image.Image, max_px: int = 1200) -> Image.Image:
    from modules.enhance import preview_resize
    return preview_resize(img, max_px)


def _px(mm: float, dpi: int = 350) -> int:
    from modules.compose import mm_to_px
    return mm_to_px(mm, dpi)


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Main page
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Session / Upload
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/new", methods=["POST"])
def new_session():
    sid = str(uuid.uuid4())[:12]
    session_dir(sid)
    return jsonify({"session_id": sid})


@app.route("/session/<sid>/upload", methods=["POST"])
def upload(sid):
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "ファイルがありません"}), 400
    img = Image.open(f.stream)
    img = img.convert("RGB")
    # Auto-upscale very small images (e.g., old scans at 96dpi)
    from modules.enhance import upscale_if_small
    img = upscale_if_small(img, target_short_side=1800)
    save_session_img(sid, img, "original.png")
    save_session_img(sid, img, "current.png")
    # Save preview
    prev = _preview(img)
    save_session_img(sid, prev, "preview.jpg")
    return jsonify({"ok": True, "w": img.width, "h": img.height})


@app.route("/session/<sid>/preview")
def get_preview(sid):
    name = request.args.get("name", "current.png")
    img = load_session_img(sid, name)
    prev = _preview(img)
    return _img_response(prev, "JPEG")


@app.route("/session/<sid>/download_current")
def download_current(sid):
    img = load_session_img(sid, "current.png")
    return _img_response(img, "PNG")


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Person detection & selection
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/detect_persons", methods=["POST"])
def detect_persons(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    img = load_session_img(sid, "original.png")
    from modules.gemini_edit import detect_persons as dp
    persons = dp(img)
    return jsonify({"persons": persons})


@app.route("/session/<sid>/select_person", methods=["POST"])
def select_person(sid):
    data = request.get_json()
    label = data.get("label", "")
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400

    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "original.png")
            from modules.gemini_edit import isolate_person
            jobs.update(jid, message="故人様を選択中...")
            result = isolate_person(img, label)
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Enhancement
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/enhance", methods=["POST"])
def enhance(sid):
    data = request.get_json() or {}
    brightness = float(data.get("brightness", 1.0))
    contrast = float(data.get("contrast", 1.05))
    sharpness = float(data.get("sharpness", 1.5))
    img = load_session_img(sid, "current.png")
    from modules.enhance import auto_enhance
    result = auto_enhance(img.convert("RGB"), brightness, contrast, sharpness)
    save_session_img(sid, result, "current.png")
    return jsonify({"ok": True})


@app.route("/session/<sid>/gemini_enhance", methods=["POST"])
def gemini_enhance(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "current.png")
            from modules.gemini_edit import enhance_quality
            jobs.update(jid, message="AI高画質化処理中...")
            result = enhance_quality(img.convert("RGB"))
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Background removal
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/remove_bg", methods=["POST"])
def remove_bg(sid):
    jid = jobs.create()

    def _run():
        try:
            jobs.update(jid, message="AIモデルを準備中（初回は1〜2分かかります）...", progress=5)
            img = load_session_img(sid, "current.png")
            from modules.bg_remove import remove_background
            jobs.update(jid, message="背景を除去中...", progress=30)
            rgba = remove_background(img.convert("RGB"))
            save_session_img(sid, rgba, "cutout.png")
            save_session_img(sid, rgba, "current.png")
            jobs.done(jid, "背景除去が完了しました")
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — AI editing
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/gemini_necktie", methods=["POST"])
def gemini_necktie(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "current.png")
            from modules.gemini_edit import change_necktie_black
            jobs.update(jid, message="ネクタイを黒色に変更中...")
            result = change_necktie_black(img.convert("RGB"))
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/gemini_clothing", methods=["POST"])
def gemini_clothing(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    data = request.get_json() or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "プロンプトが空です"}), 400
    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "current.png")
            from modules.gemini_edit import change_clothing
            jobs.update(jid, message="衣装を変更中...")
            result = change_clothing(img.convert("RGB"), prompt)
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/gemini_remove_props", methods=["POST"])
def gemini_remove_props(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "current.png")
            from modules.gemini_edit import remove_props
            jobs.update(jid, message="持ち物・小道具を除去中...")
            result = remove_props(img.convert("RGB"))
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/gemini_remove_others", methods=["POST"])
def gemini_remove_others(sid):
    if not _configure_gemini():
        return jsonify({"error": "Gemini APIキーが設定されていません"}), 400
    jid = jobs.create()

    def _run():
        try:
            img = load_session_img(sid, "current.png")
            from modules.gemini_edit import remove_others_fill
            jobs.update(jid, message="他の人物を除去・体を補完中...")
            result = remove_others_fill(img.convert("RGB"))
            save_session_img(sid, result, "current.png")
            jobs.done(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Job status polling
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/job/<jid>")
def job_status(jid):
    return jsonify(jobs.get(jid))


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Photo output
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/compose_photo", methods=["POST"])
def compose_photo(sid):
    data = request.get_json() or {}
    size_id = data.get("size_id", "yotsugiri")
    bg_color = data.get("bg_color", "#ffffff")
    filename = data.get("filename", size_id)

    sizes = load_sizes()
    entry = next((s for s in sizes if s["id"] == size_id), None)
    if not entry:
        return jsonify({"error": f"サイズが見つかりません: {size_id}"}), 400

    # Use cutout if it exists, else use current
    cutout_path = session_path(sid, "cutout.png")
    person = load_session_img(sid, "cutout.png" if cutout_path.exists() else "current.png")

    from modules.compose import compose_portrait
    result = compose_portrait(person if person.mode == "RGBA" else person.convert("RGBA"),
                              bg_color, entry)

    # Save to NAS output if configured
    cfg = load_config()
    nas_out = cfg.get("nas_output_path", "")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{filename}_{date_str}.jpg"

    if nas_out and Path(nas_out).exists():
        out_path = Path(nas_out) / out_name
        result.save(out_path, format="JPEG", quality=95, dpi=(350, 350))

    # Also return for download
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=95, dpi=(350, 350))
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=True, download_name=out_name)


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Print layout
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/print_layout/a3nobi", methods=["POST"])
def print_layout_a3nobi(sid):
    data = request.get_json() or {}
    bg_color = data.get("bg_color", "#ffffff")

    sizes = load_sizes()
    person = load_session_img(sid, "cutout.png"
                              if session_path(sid, "cutout.png").exists() else "current.png")
    if person.mode != "RGBA":
        person = person.convert("RGBA")

    from modules.compose import compose_portrait, get_pixel_size
    from modules.print_layout import a3nobi_layout

    yo_e = next(s for s in sizes if s["id"] == "yotsugiri")
    cab_e = next(s for s in sizes if s["id"] == "cabinet")
    mini_e = next(s for s in sizes if s["id"] == "askanet_mini")

    yo_img = compose_portrait(person, bg_color, yo_e)
    cab_img = compose_portrait(person, bg_color, cab_e)
    mini_imgs = [compose_portrait(person, bg_color, mini_e) for _ in range(3)]

    layout = a3nobi_layout(yo_img, cab_img, mini_imgs)
    buf = io.BytesIO()
    layout.save(buf, format="JPEG", quality=95, dpi=(350, 350))
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=False, download_name="print_a3nobi.jpg")


@app.route("/session/<sid>/print_layout/a5", methods=["POST"])
def print_layout_a5(sid):
    data = request.get_json() or {}
    bg_color = data.get("bg_color", "#ffffff")
    size_type = data.get("size_type", "cabinet")  # "cabinet" or "mini"

    sizes = load_sizes()
    person = load_session_img(sid, "cutout.png"
                              if session_path(sid, "cutout.png").exists() else "current.png")
    if person.mode != "RGBA":
        person = person.convert("RGBA")

    from modules.compose import compose_portrait
    from modules.print_layout import a5_layout

    if size_type == "cabinet":
        e = next(s for s in sizes if s["id"] == "cabinet")
        photos = [compose_portrait(person, bg_color, e)]
    else:
        e = next(s for s in sizes if s["id"] == "askanet_mini")
        photos = [compose_portrait(person, bg_color, e) for _ in range(6)]

    layout = a5_layout(photos, size_type)
    buf = io.BytesIO()
    layout.save(buf, format="JPEG", quality=95, dpi=(350, 350))
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=False, download_name=f"print_a5_{size_type}.jpg")


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Video
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/session/<sid>/upload_bg", methods=["POST"])
def upload_bg(sid):
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "背景ファイルがありません"}), 400
    saved = []
    for i, f in enumerate(files[:6]):
        dest = session_path(sid, f"bg_{i:02d}.png")
        img = Image.open(f.stream).convert("RGB")
        img.save(dest, format="PNG")
        saved.append(str(dest.name))
    return jsonify({"ok": True, "files": saved})


@app.route("/session/<sid>/compose_video", methods=["POST"])
def compose_video(sid):
    data = request.get_json() or {}
    duration_per_bg = float(data.get("duration_per_bg", 45))
    fade_duration = float(data.get("fade_duration", 3))
    fps = int(data.get("fps", 24))

    # Collect background files in order
    bg_paths = sorted(session_dir(sid).glob("bg_*.png"))
    if not bg_paths:
        return jsonify({"error": "背景素材がアップロードされていません"}), 400

    cutout_path = session_path(sid, "cutout.png")
    if not cutout_path.exists():
        return jsonify({"error": "人物切り抜き画像がありません。STEP 3を完了してください"}), 400

    jid = jobs.create()
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"saidaniei_{date_str}.mp4"
    out_path = session_path(sid, out_name)

    def _run():
        try:
            jobs.update(jid, message="動画を生成中...", progress=5)
            from modules.video_compose import create_memorial_video

            def prog(cur, total):
                pct = min(95, int(cur / max(total, 1) * 95))
                jobs.update(jid, progress=pct, message=f"動画生成中 {pct}%")

            create_memorial_video(
                str(cutout_path),
                [str(p) for p in bg_paths],
                str(out_path),
                duration_per_bg=duration_per_bg,
                fade_duration=fade_duration,
                fps=fps,
                progress_cb=prog,
            )

            # Copy to NAS if configured
            cfg = load_config()
            nas_out = cfg.get("nas_output_path", "")
            if nas_out and Path(nas_out).exists():
                shutil.copy(out_path, Path(nas_out) / out_name)

            jobs.done(jid, "動画が完成しました")
            jobs.update(jid, filename=out_name)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/download_video/<filename>")
def download_video(sid, filename):
    path = session_path(sid, filename)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=filename)


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Settings
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        cfg = load_config()
        # Never expose API key fully; mask it
        key = cfg.get("gemini_api_key", "")
        cfg["gemini_api_key_masked"] = ("*" * (len(key) - 4) + key[-4:]) if len(key) > 4 else key
        return jsonify(cfg)
    data = request.get_json() or {}
    cfg = load_config()
    for k in ("nas_input_path", "nas_output_path", "nas_bg_assets_path",
              "default_bg_color", "video_duration_per_bg",
              "video_fade_duration", "video_fps"):
        if k in data:
            cfg[k] = data[k]
    if "gemini_api_key" in data and data["gemini_api_key"] and "*" not in data["gemini_api_key"]:
        cfg["gemini_api_key"] = data["gemini_api_key"]
    save_config(cfg)
    return jsonify({"ok": True})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Sizes CRUD
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/sizes", methods=["GET"])
def get_sizes():
    sizes = load_sizes()
    from modules.compose import mm_to_px
    for s in sizes:
        s["px_w"] = mm_to_px(s["width_mm"], s["dpi"])
        s["px_h"] = mm_to_px(s["height_mm"], s["dpi"])
    return jsonify(sizes)


@app.route("/sizes", methods=["POST"])
def add_size():
    data = request.get_json() or {}
    sizes = load_sizes()
    new_id = data.get("id") or str(uuid.uuid4())[:8]
    entry = {
        "id": new_id,
        "label": data.get("label", "新しいサイズ"),
        "width_mm": float(data.get("width_mm", 100)),
        "height_mm": float(data.get("height_mm", 140)),
        "dpi": int(data.get("dpi", 350)),
    }
    sizes.append(entry)
    save_sizes(sizes)
    return jsonify({"ok": True, "entry": entry})


@app.route("/sizes/<sid_>", methods=["PUT"])
def update_size(sid_):
    data = request.get_json() or {}
    sizes = load_sizes()
    for s in sizes:
        if s["id"] == sid_:
            for k in ("label", "width_mm", "height_mm", "dpi"):
                if k in data:
                    s[k] = data[k]
            save_sizes(sizes)
            return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@app.route("/sizes/<sid_>", methods=["DELETE"])
def delete_size(sid_):
    sizes = load_sizes()
    original = len(sizes)
    sizes = [s for s in sizes if s["id"] != sid_]
    if len(sizes) == original:
        return jsonify({"error": "Not found"}), 404
    save_sizes(sizes)
    return jsonify({"ok": True})


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — Clothing presets CRUD
# ═════════════════════════════════════════════════════════════════════════════
@app.route("/presets", methods=["GET"])
def get_presets():
    return jsonify(load_presets())


@app.route("/presets/<category>", methods=["POST"])
def add_preset(category):
    data = request.get_json() or {}
    presets = load_presets()
    if category not in presets:
        presets[category] = []
    new_id = data.get("id") or f"{category}_{len(presets[category])+1}"
    entry = {"id": new_id,
             "label": data.get("label", "新しいプリセット"),
             "prompt": data.get("prompt", "")}
    presets[category].append(entry)
    save_presets(presets)
    return jsonify({"ok": True, "entry": entry})


@app.route("/presets/<category>/<pid>", methods=["PUT"])
def update_preset(category, pid):
    data = request.get_json() or {}
    presets = load_presets()
    for p in presets.get(category, []):
        if p["id"] == pid:
            for k in ("label", "prompt"):
                if k in data:
                    p[k] = data[k]
            save_presets(presets)
            return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@app.route("/presets/<category>/<pid>", methods=["DELETE"])
def delete_preset(category, pid):
    presets = load_presets()
    original = len(presets.get(category, []))
    presets[category] = [p for p in presets.get(category, []) if p["id"] != pid]
    if len(presets[category]) == original:
        return jsonify({"error": "Not found"}), 404
    save_presets(presets)
    return jsonify({"ok": True})


# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 50)
    print("  ひすい野ヴィラ 遺影写真作成ツール 起動中...")
    print("  ブラウザで http://localhost:5001 を開いてください")
    print("=" * 50)
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5001")).start()
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
