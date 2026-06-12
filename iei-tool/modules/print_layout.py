"""
Generate print-ready composite layouts for A3-nobi and A5 paper.

A3ノビ layout  (329×483mm @350dpi = 4537×6661px):
  Top row:    四つ切り (254×305mm) centered horizontally
  Bottom row: キャビネ (130×178mm) + 3×mini (48×68mm each) side by side

A5 layout (148×210mm @350dpi = 2040×2894px):
  One キャビネ centred, OR grid of mini prints
"""

import json
from PIL import Image, ImageDraw


MM_TO_PX_350 = 350 / 25.4  # pixels per mm at 350 dpi


def mm_px(mm: float) -> int:
    return round(mm * MM_TO_PX_350)


# Paper sizes at 350 dpi
A3NOBI_W = mm_px(329)
A3NOBI_H = mm_px(483)
A5_W = mm_px(148)
A5_H = mm_px(210)

# Photo sizes at 350 dpi
Y_W, Y_H = mm_px(254), mm_px(305)   # 四つ切り
C_W, C_H = mm_px(130), mm_px(178)   # キャビネ
M_W, M_H = mm_px(48),  mm_px(68)    # アスカネットmini (portrait)

GAP = mm_px(4)   # 4mm gutter between photos


def _paste_center_x(canvas: Image.Image, photo: Image.Image, y: int):
    x = (canvas.width - photo.width) // 2
    canvas.paste(photo, (x, y))


def _cut_marks(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
               tick: int = mm_px(3), color=(180, 180, 180)):
    """Draw small corner cut marks around the photo area."""
    for cx, cy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
        dx = tick if cx == x else -tick
        dy = tick if cy == y else -tick
        draw.line([(cx + dx, cy), (cx, cy)], fill=color, width=2)
        draw.line([(cx, cy + dy), (cx, cy)], fill=color, width=2)


def build_a3nobi(yotsugiri: Image.Image, cabinet: Image.Image,
                 minis: list) -> Image.Image:
    """
    yotsugiri: PIL RGB image (already at 四つ切りサイズ or will be resized)
    cabinet:   PIL RGB image
    minis:     list of up to 3 PIL RGB images
    Returns A3ノビ composite at 350 dpi.
    """
    canvas = Image.new("RGB", (A3NOBI_W, A3NOBI_H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # --- Top: 四つ切り centered ---
    y_top = GAP
    yo = yotsugiri.convert("RGB").resize((Y_W, Y_H), Image.LANCZOS)
    _paste_center_x(canvas, yo, y_top)
    _cut_marks(draw, (A3NOBI_W - Y_W) // 2, y_top, Y_W, Y_H)

    # --- Bottom row: キャビネ + up to 3 mini ---
    y_bottom = y_top + Y_H + GAP
    x_left = GAP

    cab = cabinet.convert("RGB").resize((C_W, C_H), Image.LANCZOS)
    canvas.paste(cab, (x_left, y_bottom))
    _cut_marks(draw, x_left, y_bottom, C_W, C_H)

    x_mini = x_left + C_W + GAP * 2
    for i, m in enumerate(minis[:3]):
        mini = m.convert("RGB").resize((M_W, M_H), Image.LANCZOS)
        mx = x_mini + i * (M_W + GAP)
        my = y_bottom + (C_H - M_H) // 2   # vertically centered relative to cabinet
        canvas.paste(mini, (mx, my))
        _cut_marks(draw, mx, my, M_W, M_H)

    return canvas


def build_a5_cabinet(cabinet: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (A5_W, A5_H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    cab = cabinet.convert("RGB").resize((C_W, C_H), Image.LANCZOS)
    x = (A5_W - C_W) // 2
    y = (A5_H - C_H) // 2
    canvas.paste(cab, (x, y))
    _cut_marks(draw, x, y, C_W, C_H)
    return canvas


def build_a5_mini(minis: list) -> Image.Image:
    """Arrange up to 6 mini prints on A5 in a 3-column grid."""
    canvas = Image.new("RGB", (A5_W, A5_H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    cols = 3
    margin_x = (A5_W - cols * M_W - (cols - 1) * GAP) // 2
    for i, m in enumerate(minis[:6]):
        mini = m.convert("RGB").resize((M_W, M_H), Image.LANCZOS)
        col = i % cols
        row = i // cols
        x = margin_x + col * (M_W + GAP)
        y = GAP + row * (M_H + GAP)
        canvas.paste(mini, (x, y))
        _cut_marks(draw, x, y, M_W, M_H)
    return canvas
