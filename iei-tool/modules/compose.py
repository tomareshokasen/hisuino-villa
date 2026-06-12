"""Image composition: place person on background at output resolution."""
import json
import math
from pathlib import Path
from PIL import Image


def load_sizes(path: str = "sizes.json") -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mm_to_px(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def get_pixel_size(entry: dict) -> tuple:
    return (mm_to_px(entry["width_mm"], entry["dpi"]),
            mm_to_px(entry["height_mm"], entry["dpi"]))


def _fit_person(person: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """Scale person to fill ~90% of canvas height, keep aspect ratio."""
    avail_h = int(canvas_h * 0.92)
    avail_w = int(canvas_w * 0.90)
    scale = min(avail_w / person.width, avail_h / person.height)
    new_w = max(1, int(person.width * scale))
    new_h = max(1, int(person.height * scale))
    return person.resize((new_w, new_h), Image.LANCZOS)


def compose_portrait(person_rgba: Image.Image, bg_color: str, size_entry: dict) -> Image.Image:
    """Compose person over solid background at the specified output size."""
    w, h = get_pixel_size(size_entry)
    canvas = Image.new("RGBA", (w, h), bg_color)
    person = _fit_person(person_rgba, w, h)
    # Center horizontally, pin to bottom with 2% margin
    x = (w - person.width) // 2
    y = h - person.height - int(h * 0.02)
    canvas.paste(person, (x, y), person)
    return canvas.convert("RGB")


def compose_with_bg_image(person_rgba: Image.Image, bg_img: Image.Image,
                          canvas_w: int, canvas_h: int) -> Image.Image:
    """Compose person over a background image at given pixel size."""
    bg = bg_img.convert("RGB").resize((canvas_w, canvas_h), Image.LANCZOS)
    canvas = bg.copy().convert("RGBA")
    person = _fit_person(person_rgba, canvas_w, canvas_h)
    x = (canvas_w - person.width) // 2
    y = canvas_h - person.height - int(canvas_h * 0.02)
    canvas.paste(person, (x, y), person)
    return canvas.convert("RGB")
