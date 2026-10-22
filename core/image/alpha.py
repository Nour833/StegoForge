"""
core/image/alpha.py — alpha-channel steganography for PNG / WebP.

The payload is written into the LSB of the alpha channel. Only pixels with
alpha >= 128 are used: clearing or setting the LSB never moves such a pixel
across that threshold, so the decoder selects exactly the same pixels, and
fully/semi-transparent pixels (where changes could become visible when the
image is composited) are never touched.

Wire format: ``[4-byte big-endian length][payload]``, one bit per usable pixel.
"""
from __future__ import annotations

import io
import warnings

import numpy as np
from PIL import Image

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty
from core.config import get_config

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000
OPAQUE_THRESHOLD = 128


class AlphaEncoder(BaseEncoder):
    name = "alpha"
    supported_extensions = [".png", ".webp"]

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".webp" if carrier_suffix.lower() == ".webp" else ".png"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        rgba, _ = self._load_rgba(carrier_bytes)
        return max(0, int((rgba[:, :, 3] >= OPAQUE_THRESHOLD).sum()) // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        rgba, fmt = self._load_rgba(carrier_bytes)
        height, width = rgba.shape[:2]
        # A strided channel slice reshapes to a *copy*: work on a contiguous plane
        # and write it back, otherwise the embedded bits never reach the image.
        alpha = rgba[:, :, 3].copy().reshape(-1)
        usable = np.flatnonzero(alpha >= OPAQUE_THRESHOLD)

        cap = max(0, len(usable) // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, alpha channel capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        idx = usable[:len(bits)]
        alpha[idx] = (alpha[idx] & 0xFE) | bits
        rgba[:, :, 3] = alpha.reshape(height, width)

        buf = io.BytesIO()
        out = Image.fromarray(rgba)
        if fmt == "WEBP":
            out.save(buf, format="WEBP", lossless=True, exact=True)
        else:
            out.save(buf, format="PNG")
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        rgba, _ = self._load_rgba(stego_bytes)
        alpha = rgba[:, :, 3].reshape(-1)
        usable = np.flatnonzero(alpha >= OPAQUE_THRESHOLD)

        if len(usable) < HEADER_SIZE * 8:
            raise ValueError("Not enough opaque pixels to read header")
        length = int.from_bytes(bits_to_bytes_np(alpha[usable[:HEADER_SIZE * 8]] & 1), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid payload length: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        if len(usable) < total_bits:
            raise ValueError("Not enough pixels to decode payload")
        return bits_to_bytes_np(alpha[usable[:total_bits]][HEADER_SIZE * 8:] & 1)

    @staticmethod
    def _load_rgba(data: bytes) -> tuple[np.ndarray, str]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            w, h = img.size
            if w * h > get_config().max_image_pixels:
                raise ValueError(f"Image too large ({w}x{h} px exceeds the {get_config().max_image_pixels:,} pixel limit)")
            fmt = (img.format or "PNG").upper()
            img.load()
        return np.array(img.convert("RGBA"), dtype=np.uint8), ("WEBP" if fmt == "WEBP" else "PNG")
