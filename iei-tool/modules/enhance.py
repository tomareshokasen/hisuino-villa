from PIL import Image, ImageEnhance
import io


def auto_enhance(img: Image.Image, brightness: float = 1.0,
                 contrast: float = 1.05, sharpness: float = 1.5) -> Image.Image:
    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Sharpness(img).enhance(sharpness)
    return img


def upscale_lanczos(img: Image.Image, target_short_side: int = 2000) -> Image.Image:
    w, h = img.size
    short = min(w, h)
    if short >= target_short_side:
        return img
    scale = target_short_side / short
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def preview_resize(img: Image.Image, max_px: int = 1200) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_px:
        return img
    scale = max_px / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def to_jpeg_bytes(img: Image.Image, quality: int = 88) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
