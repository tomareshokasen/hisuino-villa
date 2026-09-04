import os
import numpy as np
from PIL import Image


def _pil_to_array(img: Image.Image, size: tuple) -> np.ndarray:
    return np.array(img.convert("RGB").resize(size, Image.LANCZOS))


def _overlay_person(bg_frame: np.ndarray, person_rgba: np.ndarray,
                    t: float, canvas_h: int, canvas_w: int) -> np.ndarray:
    """Composite person onto bg_frame with vertical float animation."""
    ph, pw = person_rgba.shape[:2]
    alpha = person_rgba[:, :, 3:4] / 255.0

    # Gentle float: sine wave, 4-second period, amplitude ~0.5% of canvas height
    offset_y = int(canvas_h * 0.005 * np.sin(2 * np.pi * t / 4.0))
    base_y = (canvas_h - ph) // 2 + offset_y
    base_x = (canvas_w - pw) // 2

    y1 = max(base_y, 0)
    y2 = min(base_y + ph, canvas_h)
    x1 = max(base_x, 0)
    x2 = min(base_x + pw, canvas_w)
    py1 = y1 - base_y
    py2 = py1 + (y2 - y1)
    px1 = x1 - base_x
    px2 = px1 + (x2 - x1)

    out = bg_frame.copy()
    src_rgb = person_rgba[py1:py2, px1:px2, :3]
    src_a = alpha[py1:py2, px1:px2]
    out[y1:y2, x1:x2] = (src_rgb * src_a + out[y1:y2, x1:x2] * (1 - src_a)).astype(np.uint8)
    return out


def _ken_burns_crop(img_arr: np.ndarray, t: float, duration: float,
                    zoom_start: float = 1.0, zoom_end: float = 1.04) -> np.ndarray:
    """Slow zoom-in Ken Burns effect on background."""
    h, w = img_arr.shape[:2]
    progress = t / max(duration, 0.001)
    zoom = zoom_start + (zoom_end - zoom_start) * progress
    new_h = int(h / zoom)
    new_w = int(w / zoom)
    y0 = (h - new_h) // 2
    x0 = (w - new_w) // 2
    cropped = img_arr[y0:y0 + new_h, x0:x0 + new_w]
    return np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))


def create_memorial_video(
    person_png_path: str,
    bg_paths: list,
    output_path: str,
    duration_per_bg: float = 45.0,
    fade_duration: float = 3.0,
    fps: int = 24,
    resolution: tuple = (1920, 1080),
    progress_cb=None,
):
    """
    Create a seamless-loop memorial video.

    Seamless loop: the last background cross-fades back into the first,
    so the video loops without a hard cut.
    """
    from moviepy.editor import VideoClip, concatenate_videoclips, CompositeVideoClip

    cw, ch = resolution

    # Load and resize person RGBA
    person_img = Image.open(person_png_path).convert("RGBA")
    scale = ch * 0.88 / person_img.height
    person_img = person_img.resize(
        (int(person_img.width * scale), int(person_img.height * scale)), Image.LANCZOS
    )
    person_arr = np.array(person_img)

    # Load and resize backgrounds
    bgs = []
    for p in bg_paths:
        img = Image.open(p).convert("RGB")
        # Crop to 16:9 (fill, not letterbox)
        iw, ih = img.size
        target_ratio = cw / ch
        if iw / ih > target_ratio:
            new_w = int(ih * target_ratio)
            img = img.crop(((iw - new_w) // 2, 0, (iw - new_w) // 2 + new_w, ih))
        else:
            new_h = int(iw / target_ratio)
            img = img.crop((0, (ih - new_h) // 2, iw, (ih - new_h) // 2 + new_h))
        bgs.append(np.array(img.resize(resolution, Image.LANCZOS)))

    n_bgs = len(bgs)
    total_frames = int((duration_per_bg * n_bgs) * fps)
    frames_per_bg = int(duration_per_bg * fps)
    fade_frames = int(fade_duration * fps)

    def make_frame(t):
        global_frame = int(t * fps)
        total_clip_frames = frames_per_bg * n_bgs

        # Which background segment
        seg_idx = min(global_frame // frames_per_bg, n_bgs - 1)
        seg_frame = global_frame % frames_per_bg
        seg_t = seg_frame / fps

        bg = _ken_burns_crop(bgs[seg_idx], seg_t, duration_per_bg)

        # Cross-fade at segment boundaries
        if seg_frame < fade_frames and seg_idx > 0:
            alpha = seg_frame / fade_frames
            prev_bg = _ken_burns_crop(bgs[seg_idx - 1], duration_per_bg, duration_per_bg)
            bg = (prev_bg * (1 - alpha) + bg * alpha).astype(np.uint8)
        elif seg_frame >= frames_per_bg - fade_frames:
            next_idx = (seg_idx + 1) % n_bgs
            fade_progress = (seg_frame - (frames_per_bg - fade_frames)) / fade_frames
            next_bg = _ken_burns_crop(bgs[next_idx], 0, duration_per_bg)
            bg = (bg * (1 - fade_progress) + next_bg * fade_progress).astype(np.uint8)

        return _overlay_person(bg, person_arr, t, ch, cw)

    clip = VideoClip(make_frame, duration=duration_per_bg * n_bgs)

    if progress_cb:
        progress_cb(10, "動画フレームをレンダリング中…")

    clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=2,
        logger=None,
    )

    if progress_cb:
        progress_cb(100, "完了")
