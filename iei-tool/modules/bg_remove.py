from PIL import Image

_session = None


def _ensure_session():
    global _session
    if _session is None:
        from rembg import new_session
        _session = new_session("u2net_human_seg")
    return _session


def remove_background(img: Image.Image) -> Image.Image:
    """Returns RGBA image with transparent background."""
    from rembg import remove
    session = _ensure_session()
    rgba = remove(img, session=session)
    return rgba
