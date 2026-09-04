"""
遺影写真作成ツール - Flask application
Run with: python app.py
Access at: http://localhost:5001
"""
import io
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import (Flask, Response, jsonify, render_template, request,
                   send_file, stream_with_context)
from PIL import Image

BASE_DIR = Path(__file__).parent
TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    p = BASE_DIR / "config.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict):
    p = BASE_DIR / "config.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_sizes() -> list:
    p = BASE_DIR / "sizes.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_sizes(data: list):
    p = BASE_DIR / "sizes.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_presets() -> dict:
    p = BASE_DIR / "clothing_presets.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_presets(data: dict):
    p = BASE_DIR / "clothing_presets.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mm_to_px(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


# ---------------------------------------------------------------------------
# Job manager (for long-running tasks)
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        jid = str(uuid.uuid4())[:8]
        with self._lock:
            self._jobs[jid] = {"status": "running", "progress": 0,
                                "message": "処理中…", "result": None, "error": None}
        return jid

    def update(self, jid: str, **kw):
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].update(kw)

    def get(self, jid: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(jid, {}))

    def finish(self, jid: str, result=None):
        self.update(jid, status="done", progress=100, message="完了", result=result)

    def fail(self, jid: str, error: str):
        self.update(jid, status="error", message=error, error=error)


jobs = JobManager()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def session_dir(sid: str) -> Path:
    d = TMP_DIR / sid
    d.mkdir(exist_ok=True)
    return d


def load_session_img(sid: str, name: str = "current.png") -> Image.Image:
    return Image.open(session_dir(sid) / name)


def save_session_img(sid: str, img: Image.Image, name: str = "current.png"):
    path = session_dir(sid) / name
    if img.mode == "RGBA":
        img.save(path, format="PNG")
    else:
        img.convert("RGB").save(path, format="JPEG", quality=92)


def preview_bytes(sid: str, name: str = "current.png") -> bytes:
    from modules.enhance import preview_resize, to_jpeg_bytes, to_png_bytes
    img = load_session_img(sid, name)
    img = preview_resize(img, 1200)
    if img.mode == "RGBA":
        return to_png_bytes(img)
    return to_jpeg_bytes(img)


# ---------------------------------------------------------------------------
# Routes: UI
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes: Config / Sizes / Presets
# ---------------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify(load_config())
    data = request.json
    save_config(data)
    # Re-configure Gemini if key changed
    key = data.get("gemini_api_key", "")
    if key:
        from modules.gemini_edit import configure
        configure(key)
    return jsonify({"ok": True})


@app.route("/sizes", methods=["GET"])
def get_sizes():
    sizes = load_sizes()
    for s in sizes:
        s["px_w"] = mm_to_px(s["width_mm"], s["dpi"])
        s["px_h"] = mm_to_px(s["height_mm"], s["dpi"])
    return jsonify(sizes)


@app.route("/sizes", methods=["POST"])
def add_size():
    sizes = load_sizes()
    data = request.json
    data["id"] = str(uuid.uuid4())[:8]
    data.setdefault("filename", data["label"])
    sizes.append(data)
    save_sizes(sizes)
    return jsonify({"ok": True, "id": data["id"]})


@app.route("/sizes/<sid>", methods=["PUT"])
def update_size(sid):
    sizes = load_sizes()
    for s in sizes:
        if s["id"] == sid:
            s.update(request.json)
            s["id"] = sid  # protect id
    save_sizes(sizes)
    return jsonify({"ok": True})


@app.route("/sizes/<sid>", methods=["DELETE"])
def delete_size(sid):
    sizes = [s for s in load_sizes() if s["id"] != sid]
    save_sizes(sizes)
    return jsonify({"ok": True})


@app.route("/clothing_presets", methods=["GET"])
def get_presets():
    return jsonify(load_presets())


@app.route("/clothing_presets/<category>", methods=["POST"])
def add_preset(category):
    presets = load_presets()
    data = request.json
    data["id"] = str(uuid.uuid4())[:8]
    presets.setdefault(category, []).append(data)
    save_presets(presets)
    return jsonify({"ok": True})


@app.route("/clothing_presets/<category>/<pid>", methods=["PUT"])
def update_preset(category, pid):
    presets = load_presets()
    for p in presets.get(category, []):
        if p["id"] == pid:
            p.update(request.json)
            p["id"] = pid
    save_presets(presets)
    return jsonify({"ok": True})


@app.route("/clothing_presets/<category>/<pid>", methods=["DELETE"])
def delete_preset(category, pid):
    presets = load_presets()
    if category in presets:
        presets[category] = [p for p in presets[category] if p["id"] != pid]
    save_presets(presets)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes: Session / Upload
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "ファイルが見つかりません"}), 400
    sid = str(uuid.uuid4())[:8]
    d = session_dir(sid)
    img = Image.open(f.stream)
    # Auto-rotate from EXIF
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    save_session_img(sid, img, "original.jpg")
    save_session_img(sid, img, "current.png")
    return jsonify({"session_id": sid})


@app.route("/session/<sid>/preview")
def session_preview(sid):
    name = request.args.get("name", "current.png")
    data = preview_bytes(sid, name)
    mime = "image/png" if name.endswith(".png") or load_session_img(sid, name).mode == "RGBA" else "image/jpeg"
    return Response(data, mimetype=mime)


# ---------------------------------------------------------------------------
# Routes: Enhance
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/enhance", methods=["POST"])
def enhance(sid):
    body = request.json or {}
    brightness = float(body.get("brightness", 1.0))
    contrast = float(body.get("contrast", 1.05))
    sharpness = float(body.get("sharpness", 1.5))
    from modules.enhance import auto_enhance, upscale_lanczos
    img = load_session_img(sid, "original.jpg")
    img = upscale_lanczos(img)
    img = auto_enhance(img, brightness, contrast, sharpness)
    save_session_img(sid, img, "enhanced.jpg")
    save_session_img(sid, img, "current.png")
    return jsonify({"ok": True})


@app.route("/session/<sid>/gemini_enhance", methods=["POST"])
def gemini_enhance(sid):
    jid = jobs.create()

    def work():
        try:
            cfg = load_config()
            from modules.gemini_edit import configure, enhance_quality
            configure(cfg["gemini_api_key"])
            img = load_session_img(sid, "current.png")
            result = enhance_quality(img)
            save_session_img(sid, result, "enhanced.jpg")
            save_session_img(sid, result, "current.png")
            jobs.finish(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": jid})


# ---------------------------------------------------------------------------
# Routes: Person detection & isolation
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/detect_persons", methods=["POST"])
def detect_persons(sid):
    jid = jobs.create()

    def work():
        try:
            cfg = load_config()
            from modules.gemini_edit import configure, detect_persons as dp
            configure(cfg["gemini_api_key"])
            img = load_session_img(sid, "current.png")
            persons = dp(img)
            jobs.finish(jid, result={"persons": persons})
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/isolate_person", methods=["POST"])
def isolate_person(sid):
    label = (request.json or {}).get("label", "人物1")
    jid = jobs.create()

    def work():
        try:
            cfg = load_config()
            from modules.gemini_edit import configure, isolate_person as ip
            configure(cfg["gemini_api_key"])
            img = load_session_img(sid, "current.png")
            result = ip(img, label)
            save_session_img(sid, result, "current.png")
            jobs.finish(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": jid})


# ---------------------------------------------------------------------------
# Routes: Background removal
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/remove_bg", methods=["POST"])
def remove_bg(sid):
    jid = jobs.create()

    def work():
        try:
            jobs.update(jid, progress=5, message="AIモデルを準備中…（初回は数分かかります）")
            from modules.bg_remove import remove_background
            img = load_session_img(sid, "current.png")
            jobs.update(jid, progress=30, message="背景を解析中…")
            rgba = remove_background(img)
            save_session_img(sid, rgba, "cutout.png")
            save_session_img(sid, rgba, "current.png")
            jobs.finish(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": jid})


# ---------------------------------------------------------------------------
# Routes: AI editing (Gemini)
# ---------------------------------------------------------------------------

def _gemini_job(sid: str, fn, *args) -> str:
    """Generic helper: run a gemini_edit function in a background job."""
    jid = jobs.create()

    def work():
        try:
            cfg = load_config()
            from modules import gemini_edit
            gemini_edit.configure(cfg["gemini_api_key"])
            img = load_session_img(sid, "current.png")
            result = fn(img, *args)
            save_session_img(sid, result, "current.png")
            jobs.finish(jid)
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jid


@app.route("/session/<sid>/necktie_black", methods=["POST"])
def necktie_black(sid):
    from modules.gemini_edit import change_necktie_black
    jid = _gemini_job(sid, change_necktie_black)
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/clothing", methods=["POST"])
def clothing(sid):
    prompt = (request.json or {}).get("prompt", "")
    if not prompt:
        return jsonify({"error": "プロンプトが空です"}), 400
    from modules.gemini_edit import change_clothing
    jid = _gemini_job(sid, change_clothing, prompt)
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/remove_objects", methods=["POST"])
def remove_objects(sid):
    from modules.gemini_edit import remove_objects as ro
    jid = _gemini_job(sid, ro)
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/remove_others", methods=["POST"])
def remove_others(sid):
    from modules.gemini_edit import remove_others_fill
    jid = _gemini_job(sid, remove_others_fill)
    return jsonify({"job_id": jid})


# ---------------------------------------------------------------------------
# Routes: Save before/after snapshots for comparison
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/snapshot", methods=["POST"])
def snapshot(sid):
    """Save current.png as before.png for before/after comparison."""
    src = session_dir(sid) / "current.png"
    dst = session_dir(sid) / "before.png"
    shutil.copy2(src, dst)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes: Compose photo output
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/compose_photo", methods=["POST"])
def compose_photo(sid):
    body = request.json or {}
    size_id = body.get("size_id")
    bg_color = body.get("bg_color", "#ffffff")

    sizes = load_sizes()
    entry = next((s for s in sizes if s["id"] == size_id), None)
    if not entry:
        return jsonify({"error": "サイズが見つかりません"}), 400

    from modules.compose import compose_portrait
    img = load_session_img(sid, "current.png")
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    result = compose_portrait(img, bg_color, entry)

    fname = entry.get("filename", size_id)
    out_name = f"{fname}_preview.jpg"
    save_session_img(sid, result, out_name)
    return jsonify({"ok": True, "preview_name": out_name})


@app.route("/session/<sid>/download_photo", methods=["POST"])
def download_photo(sid):
    body = request.json or {}
    size_id = body.get("size_id")
    bg_color = body.get("bg_color", "#ffffff")
    quality = int(body.get("quality", 95))

    sizes = load_sizes()
    entry = next((s for s in sizes if s["id"] == size_id), None)
    if not entry:
        return jsonify({"error": "サイズが見つかりません"}), 400

    from modules.compose import compose_portrait
    from modules.enhance import to_jpeg_bytes
    img = load_session_img(sid, "current.png")
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    result = compose_portrait(img, bg_color, entry)

    fname = entry.get("filename", size_id)
    buf = io.BytesIO(to_jpeg_bytes(result, quality=quality))
    buf.seek(0)

    # Save to NAS if configured
    cfg = load_config()
    nas_out = cfg.get("nas_output_path", "")
    if nas_out and Path(nas_out).exists():
        out_path = Path(nas_out) / f"{fname}.jpg"
        result.save(out_path, format="JPEG", quality=quality, dpi=(350, 350))

    import datetime
    date_str = datetime.date.today().strftime("%Y%m%d")
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=True,
                     download_name=f"{fname}_{date_str}.jpg")


# ---------------------------------------------------------------------------
# Routes: Print layouts
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/print_a3nobi", methods=["POST"])
def print_a3nobi(sid):
    body = request.json or {}
    bg_color = body.get("bg_color", "#ffffff")
    sizes = load_sizes()

    from modules.compose import compose_portrait, get_pixel_size
    from modules.print_layout import build_a3nobi
    from modules.enhance import to_jpeg_bytes

    def get_composed(size_id: str) -> Image.Image:
        entry = next((s for s in sizes if s["id"] == size_id), None)
        if not entry:
            return None
        img = load_session_img(sid, "current.png")
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return compose_portrait(img, bg_color, entry)

    yo = get_composed("yotsugiri")
    cab = get_composed("cabinet")
    mn = get_composed("askanet_mini")

    if not yo or not cab or not mn:
        return jsonify({"error": "サイズ設定が見つかりません"}), 400

    layout = build_a3nobi(yo, cab, [mn, mn, mn])
    buf = io.BytesIO(to_jpeg_bytes(layout, quality=95))
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=True, download_name="print_a3nobi.jpg")


@app.route("/session/<sid>/print_a5", methods=["POST"])
def print_a5(sid):
    body = request.json or {}
    bg_color = body.get("bg_color", "#ffffff")
    mode = body.get("mode", "cabinet")  # "cabinet" or "mini"
    sizes = load_sizes()

    from modules.compose import compose_portrait
    from modules.print_layout import build_a5_cabinet, build_a5_mini
    from modules.enhance import to_jpeg_bytes

    img = load_session_img(sid, "current.png")
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    if mode == "cabinet":
        entry = next((s for s in sizes if s["id"] == "cabinet"), None)
        if not entry:
            return jsonify({"error": "キャビネサイズが設定されていません"}), 400
        cab = compose_portrait(img, bg_color, entry)
        layout = build_a5_cabinet(cab)
    else:
        entry = next((s for s in sizes if s["id"] == "askanet_mini"), None)
        if not entry:
            return jsonify({"error": "miniサイズが設定されていません"}), 400
        mn = compose_portrait(img, bg_color, entry)
        layout = build_a5_mini([mn] * 6)

    buf = io.BytesIO(to_jpeg_bytes(layout, quality=95))
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg",
                     as_attachment=True, download_name=f"print_a5_{mode}.jpg")


# ---------------------------------------------------------------------------
# Routes: Video
# ---------------------------------------------------------------------------

@app.route("/session/<sid>/compose_video", methods=["POST"])
def compose_video(sid):
    body = request.json or {}
    bg_names = body.get("bg_names", [])   # filenames stored in session tmp
    duration_per_bg = float(body.get("duration_per_bg", 45))
    fade_duration = float(body.get("fade_duration", 3))
    fps = int(body.get("fps", 24))

    if not bg_names:
        return jsonify({"error": "背景素材が選択されていません"}), 400

    d = session_dir(sid)
    bg_paths = [str(d / name) for name in bg_names if (d / name).exists()]
    person_path = str(d / "current.png")

    if not Path(person_path).exists():
        return jsonify({"error": "人物画像が見つかりません"}), 400

    jid = jobs.create()

    def work():
        try:
            jobs.update(jid, progress=5, message="動画を生成中…")
            import datetime
            date_str = datetime.date.today().strftime("%Y%m%d")
            out_path = str(d / f"saidaniei_{date_str}.mp4")

            from modules.video_compose import create_memorial_video

            def cb(pct, msg):
                jobs.update(jid, progress=pct, message=msg)

            create_memorial_video(
                person_path, bg_paths, out_path,
                duration_per_bg=duration_per_bg,
                fade_duration=fade_duration,
                fps=fps,
                progress_cb=cb,
            )
            jobs.finish(jid, result={"filename": Path(out_path).name})
        except Exception as e:
            jobs.fail(jid, str(e))

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/session/<sid>/upload_bg", methods=["POST"])
def upload_bg(sid):
    files = request.files.getlist("files")
    saved = []
    for f in files:
        name = f"bg_{uuid.uuid4().hex[:6]}_{Path(f.filename).suffix or '.jpg'}"
        path = session_dir(sid) / name
        f.save(str(path))
        saved.append(name)
    return jsonify({"names": saved})


@app.route("/session/<sid>/download_video")
def download_video(sid):
    fname = request.args.get("filename")
    path = session_dir(sid) / fname
    if not path.exists():
        return jsonify({"error": "ファイルが見つかりません"}), 404

    # Copy to NAS if configured
    cfg = load_config()
    nas_out = cfg.get("nas_output_path", "")
    if nas_out and Path(nas_out).exists():
        shutil.copy2(path, Path(nas_out) / fname)

    return send_file(str(path), mimetype="video/mp4",
                     as_attachment=True, download_name=fname)


# ---------------------------------------------------------------------------
# Routes: Job polling
# ---------------------------------------------------------------------------

@app.route("/job/<jid>")
def job_status(jid):
    return jsonify(jobs.get(jid))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Pre-load Gemini key if configured
    cfg = load_config()
    key = cfg.get("gemini_api_key", "")
    if key:
        from modules.gemini_edit import configure
        configure(key)
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
