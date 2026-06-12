"""Create Full HD memorial video with ken burns + person float + crossfade loop."""
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image


W, H = 1920, 1080


def _load_bg(path: str) -> np.ndarray:
    """Load background image/first-frame-of-video as (H, W, 3) uint8 array."""
    img = Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
    return np.array(img)


def _load_person(path: str, target_height_ratio: float = 0.88) -> np.ndarray:
    """Load RGBA person PNG, scale to target height, return (h, w, 4) array."""
    img = Image.open(path).convert("RGBA")
    target_h = int(H * target_height_ratio)
    scale = target_h / img.height
    img = img.resize((int(img.width * scale), target_h), Image.LANCZOS)
    return np.array(img)


def _ken_burns_frame(bg: np.ndarray, t: float, duration: float,
                     zoom_start: float = 1.0, zoom_end: float = 1.03) -> np.ndarray:
    """Apply slow zoom (Ken Burns) to background frame."""
    from PIL import Image as PILImage
    zoom = zoom_start + (zoom_end - zoom_start) * (t / max(duration, 0.001))
    zh = int(H * zoom)
    zw = int(W * zoom)
    frame = PILImage.fromarray(bg).resize((zw, zh), PILImage.BILINEAR)
    top = (zh - H) // 2
    left = (zw - W) // 2
    return np.array(frame)[top:top+H, left:left+W]


def _composite_person(frame: np.ndarray, person: np.ndarray, float_offset: int) -> np.ndarray:
    """Alpha-blend person onto frame with vertical float offset."""
    ph, pw = person.shape[:2]
    x = (W - pw) // 2
    base_y = H - ph - int(H * 0.02)
    y = base_y + float_offset

    # Clamp bounds
    y_start = max(0, y)
    y_end = min(H, y + ph)
    x_start = max(0, x)
    x_end = min(W, x + pw)
    p_y0 = y_start - y
    p_y1 = p_y0 + (y_end - y_start)
    p_x0 = x_start - x
    p_x1 = p_x0 + (x_end - x_start)

    out = frame.copy().astype(np.float32)
    alpha = person[p_y0:p_y1, p_x0:p_x1, 3:4].astype(np.float32) / 255.0
    rgb = person[p_y0:p_y1, p_x0:p_x1, :3].astype(np.float32)
    out[y_start:y_end, x_start:x_end] = (
        alpha * rgb + (1 - alpha) * out[y_start:y_end, x_start:x_end]
    )
    return out.astype(np.uint8)


def create_memorial_video(
    person_png_path: str,
    bg_paths: list,
    output_path: str,
    duration_per_bg: float = 45.0,
    fade_duration: float = 3.0,
    fps: int = 24,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """
    Create a seamlessly looping Full HD MP4 memorial video.

    Each background is shown for duration_per_bg seconds with ken burns effect.
    Cross-fades of fade_duration seconds connect each background (including last→first loop).
    The person floats gently throughout.

    progress_cb(current_frame, total_frames) is called periodically.
    """
    try:
        from moviepy.editor import VideoClip, concatenate_videoclips, ImageClip
    except ImportError:
        raise RuntimeError("moviepyがインストールされていません。セットアップを実行してください。")

    bgs = [_load_bg(p) for p in bg_paths]
    person = _load_person(person_png_path)

    n = len(bgs)
    float_amp = int(H * 0.006)   # ±float_amp pixels
    float_period = 4.0            # seconds per breath cycle

    def make_clip(bg_idx: int) -> VideoClip:
        bg = bgs[bg_idx]
        d = duration_per_bg

        def make_frame(t):
            zoom_t = t % d
            zoom = 1.0 + 0.03 * (zoom_t / d)
            frame = _ken_burns_frame(bg, zoom_t, d, 1.0, 1.03)
            offset = int(float_amp * np.sin(2 * np.pi * t / float_period))
            return _composite_person(frame, person, offset)

        return VideoClip(make_frame, duration=d)

    clips = []
    for i in range(n):
        c = make_clip(i)
        if i > 0:
            c = c.crossfadein(fade_duration)
        clips.append(c)

    # Add seamless loop: crossfade last→first
    first_clip = make_clip(0)
    first_clip = first_clip.crossfadein(fade_duration)
    first_clip = first_clip.set_duration(fade_duration)
    clips.append(first_clip)

    from moviepy.editor import CompositeVideoClip
    final = concatenate_videoclips(clips, padding=-fade_duration, method="compose")

    total_frames = int(final.duration * fps)
    rendered = [0]

    original_make = final.make_frame

    def tracked_make(t):
        rendered[0] += 1
        if progress_cb and rendered[0] % (fps * 2) == 0:
            progress_cb(rendered[0], total_frames)
        return original_make(t)

    final.make_frame = tracked_make

    final.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=2,
        logger=None,
    )
