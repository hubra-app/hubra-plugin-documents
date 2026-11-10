"""Photos are re-encoded on upload: turned the right way up, at most
2560 px on the long side, without EXIF (no location, no camera serial),
plus a 640 px thumbnail."""

from __future__ import annotations

import io

FULL = 2560
THUMB = 640
TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")


class BadImage(Exception):
    pass


def process(data: bytes) -> tuple[bytes, str, bytes, int, int]:
    """Returns (full, content type, thumbnail, width, height)."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # Pillow comes with WeasyPrint in Hubra
        raise BadImage("images can't be read on this server") from exc
    Image.MAX_IMAGE_PIXELS = 60_000_000
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - anything Pillow can't read
        raise BadImage("this is not a photo Hubra can read") from exc
    if img.format not in ("JPEG", "PNG", "WEBP", "GIF", "MPO"):
        raise BadImage("only JPEG, PNG, WebP and GIF photos")
    img = ImageOps.exif_transpose(img)
    alpha = (
        img.mode in ("RGBA", "LA", "P")
        and "transparency" in img.info
        or img.mode in ("RGBA", "LA")
    )
    img = img.convert("RGBA" if alpha else "RGB")
    img.thumbnail((FULL, FULL))
    full = io.BytesIO()
    if alpha:
        img.save(full, "WEBP", quality=85)
        kind = "image/webp"
    else:
        img.save(full, "JPEG", quality=85, optimize=True, progressive=True)
        kind = "image/jpeg"
    width, height = img.size
    thumb_img = img.copy()
    thumb_img.thumbnail((THUMB, THUMB))
    thumb = io.BytesIO()
    if alpha:
        thumb_img.save(thumb, "WEBP", quality=80)
    else:
        thumb_img.save(thumb, "JPEG", quality=80, optimize=True)
    return full.getvalue(), kind, thumb.getvalue(), width, height
