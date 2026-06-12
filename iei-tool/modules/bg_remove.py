from PIL import Image

_session = None


def ensure_session():
    global _session
    if _session is None:
        from rembg import new_session
        _session = new_session("u2net_human_seg")
    return _session


def remove_background(img: Image.Image) -> Image.Image:
    """Return RGBA image with transparent background."""
    from rembg import remove
    session = ensure_session()
    rgba = remove(img, session=session)
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    return rgba
