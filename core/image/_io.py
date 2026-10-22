"""core/image/_io.py — shared image loading/saving for the RGB-based encoders.

``adaptive-lsb`` and ``fingerprint-lsb`` embed into the RGB samples only. These
helpers split off an alpha plane (so transparency is carried through untouched
instead of being silently flattened) and pick a lossless output format.
"""
from __future__ import annotations

import io
import warnings

import numpy as np
from PIL import Image

from core.config import get_config

RGB_OUTPUT_FORMATS = ("PNG", "BMP", "WEBP")


def check_pixel_budget(size: tuple[int, int]) -> None:
    """Refuse images larger than the configured pixel limit (memory guard)."""
    w, h = size
    limit = get_config().max_image_pixels
    if w * h > limit:
        raise ValueError(f"Image too large ({w}x{h} px exceeds the {limit:,} pixel limit)")


def load_rgb_alpha(data: bytes) -> tuple[np.ndarray, np.ndarray | None, str]:
    """Return ``(writable contiguous RGB uint8 array, alpha plane or None, output format)``."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        img = Image.open(io.BytesIO(data))
        check_pixel_budget(img.size)
        fmt = (img.format or "PNG").upper()
        img.load()
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = np.array(img.convert("RGBA"), dtype=np.uint8)
        return rgba[:, :, :3].copy(), rgba[:, :, 3].copy(), (fmt if fmt in RGB_OUTPUT_FORMATS else "PNG")
    return np.array(img.convert("RGB"), dtype=np.uint8), None, (fmt if fmt in RGB_OUTPUT_FORMATS else "PNG")


def save_rgb_alpha(rgb: np.ndarray, alpha: np.ndarray | None, fmt: str) -> bytes:
    """Encode ``rgb`` (+ optional alpha) losslessly as PNG / BMP / WebP bytes."""
    arr = np.dstack([rgb, alpha]) if alpha is not None else rgb
    buf = io.BytesIO()
    if fmt == "WEBP":
        # exact=True: libwebp otherwise zeroes RGB under fully transparent pixels.
        Image.fromarray(arr).save(buf, format="WEBP", lossless=True, exact=True)
    elif fmt == "BMP":
        Image.fromarray(arr).save(buf, format="BMP")
    else:
        Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()
