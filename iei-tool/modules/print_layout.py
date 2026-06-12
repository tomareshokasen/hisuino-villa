"""Generate print-ready layout images for A3ノビ and A5 paper."""
from PIL import Image, ImageDraw, ImageFont
import math


def mm_to_px(mm: float, dpi: int = 350) -> int:
    return round(mm / 25.4 * dpi)


# Paper sizes
A3NOBI_W = mm_to_px(329)
A3NOBI_H = mm_to_px(483)
A5_W = mm_to_px(148)
A5_H = mm_to_px(210)

# Photo sizes (350dpi)
YOTSUGIRI_W = mm_to_px(254)
YOTSUGIRI_H = mm_to_px(305)
CABINET_W = mm_to_px(130)
CABINET_H = mm_to_px(178)
MINI_W = mm_to_px(48)
MINI_H = mm_to_px(68)

GAP = mm_to_px(3)   # 3mm gap between photos


def _place(canvas: Image.Image, photo: Image.Image, x: int, y: int) -> None:
    if photo.mode == "RGBA":
        canvas.paste(photo, (x, y), photo)
    else:
        canvas.paste(photo, (x, y))


def a3nobi_layout(yotsugiri: Image.Image, cabinet: Image.Image,
                  minis: list) -> Image.Image:
    """
    Layout on A3ノビ (329×483mm @ 350dpi):
      Top: 四つ切り centered horizontally
      Bottom row: キャビネ + up to 3 minis side by side
    """
    canvas = Image.new("RGB", (A3NOBI_W, A3NOBI_H), "#ffffff")
    draw = ImageDraw.Draw(canvas)

    # Scale 四つ切り to fit width with margin
    margin = mm_to_px(5)
    yo = yotsugiri.convert("RGB").resize((YOTSUGIRI_W, YOTSUGIRI_H), Image.LANCZOS)
    yo_x = (A3NOBI_W - YOTSUGIRI_W) // 2
    yo_y = margin
    _place(canvas, yo, yo_x, yo_y)

    # Bottom row starts below 四つ切り
    bottom_y = yo_y + YOTSUGIRI_H + GAP

    # キャビネ
    cab = cabinet.convert("RGB").resize((CABINET_W, CABINET_H), Image.LANCZOS)
    cab_x = margin
    cab_y = bottom_y + (A3NOBI_H - bottom_y - CABINET_H) // 2
    _place(canvas, cab, cab_x, cab_y)

    # Minis (up to 3)
    mini_start_x = cab_x + CABINET_W + GAP
    mini_start_y = bottom_y + GAP
    for i, mini_img in enumerate(minis[:3]):
        m = mini_img.convert("RGB").resize((MINI_W, MINI_H), Image.LANCZOS)
        mx = mini_start_x + i * (MINI_W + GAP)
        my = mini_start_y
        _place(canvas, m, mx, my)

    # Cut marks (thin lines between photos)
    lc = "#cccccc"
    # Below 四つ切り
    draw.line([(0, bottom_y - GAP // 2), (A3NOBI_W, bottom_y - GAP // 2)], fill=lc, width=2)

    return canvas


def a5_layout(photos: list, size_label: str = "cabinet") -> Image.Image:
    """
    A5 layout. キャビネ: 1 per sheet centered. mini: up to 6 per sheet in a grid.
    """
    canvas = Image.new("RGB", (A5_W, A5_H), "#ffffff")
    margin = mm_to_px(5)

    if size_label == "cabinet":
        pw, ph = CABINET_W, CABINET_H
    else:
        pw, ph = MINI_W, MINI_H

    if size_label == "cabinet":
        # Single cabinet centered
        p = photos[0].convert("RGB").resize((pw, ph), Image.LANCZOS)
        x = (A5_W - pw) // 2
        y = (A5_H - ph) // 2
        _place(canvas, p, x, y)
    else:
        # Grid of minis
        cols = (A5_W - 2 * margin + GAP) // (MINI_W + GAP)
        cols = max(1, cols)
        x0 = margin
        y0 = margin
        for i, photo in enumerate(photos[:12]):
            row = i // cols
            col = i % cols
            p = photo.convert("RGB").resize((MINI_W, MINI_H), Image.LANCZOS)
            x = x0 + col * (MINI_W + GAP)
            y = y0 + row * (MINI_H + GAP)
            if y + MINI_H > A5_H - margin:
                break
            _place(canvas, p, x, y)

    return canvas
