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
    return (
        mm_to_px(entry["width_mm"], entry["dpi"]),
        mm_to_px(entry["height_mm"], entry["dpi"]),
    )


def _fit_person(person: Image.Image, canvas_w: int, canvas_h: int,
                top_margin: float = 0.04, bottom_margin: float = 0.02,
                side_margin: float = 0.04) -> Image.Image:
    avail_h = canvas_h * (1 - top_margin - bottom_margin)
    avail_w = canvas_w * (1 - 2 * side_margin)
    scale = min(avail_w / person.width, avail_h / person.height)
    new_w = int(person.width * scale)
    new_h = int(person.height * scale)
    return person.resize((new_w, new_h), Image.LANCZOS)


def compose_portrait(person_rgba: Image.Image, bg_color: str,
                     size_entry: dict) -> Image.Image:
    """Composite transparent-bg person onto solid background at output size."""
    w, h = get_pixel_size(size_entry)
    canvas = Image.new("RGBA", (w, h), bg_color)
    person = _fit_person(person_rgba, w, h)
    x = (w - person.width) // 2
    y = h - person.height - int(h * 0.02)
    canvas.paste(person, (x, y), person)
    return canvas.convert("RGB")
