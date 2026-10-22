"""
core/image/palette.py — indexed-colour palette reordering (GIF / palette PNG).

The order of an indexed image's palette can change without changing any visible
colour, as long as every pixel index (and the transparency index) is remapped
to follow its colour.

Encoding: palette entries are taken in pairs. The relative order of a pair's
colour sums encodes one bit: ``sum(a) <  sum(b)`` -> 0, otherwise -> 1.
Capacity is tiny (a 256-colour palette holds 128 bits, i.e. 14 payload bytes
after the 2-byte length header), so this method suits very short messages —
it cannot carry an AES envelope, which alone is larger than that. Use it with
``--allow-plaintext`` for a few bytes, or pick another method.

Wire format: ``[2-byte big-endian length][payload]``.
"""
from __future__ import annotations

import io
from collections import defaultdict, deque

import numpy as np
from PIL import Image

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty

HEADER_SIZE = 2
MAX_PAYLOAD = 10_000


class PaletteEncoder(BaseEncoder):
    name = "palette"
    supported_extensions = [".gif", ".png"]

    def output_suffix(self, carrier_suffix: str) -> str:
        return carrier_suffix if carrier_suffix.lower() in (".gif", ".png") else ".gif"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        palette = self._palette_rgb(self._load_indexed(carrier_bytes))
        return max(0, (len(palette) // 2) // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        img = self._load_indexed(carrier_bytes)
        palette = self._palette_rgb(img)
        n_pairs = len(palette) // 2

        cap = max(0, n_pairs // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, palette capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        new_palette = list(palette)
        for i, bit in enumerate(bits.tolist()):
            a, b = new_palette[2 * i], new_palette[2 * i + 1]
            if bit == 0:
                if sum(a) > sum(b):
                    new_palette[2 * i], new_palette[2 * i + 1] = b, a
                elif sum(a) == sum(b):
                    # Equal sums decode as 1: nudge one channel by 1 to encode 0.
                    r, g, bl = a
                    if r > 0:
                        new_palette[2 * i] = (r - 1, g, bl)
                    elif g > 0:
                        new_palette[2 * i] = (r, g - 1, bl)
                    elif bl > 0:
                        new_palette[2 * i] = (r, g, bl - 1)
                    else:
                        r2, g2, b2 = b
                        new_palette[2 * i + 1] = (min(255, r2 + 1), g2, b2)
            elif sum(a) < sum(b):
                new_palette[2 * i], new_palette[2 * i + 1] = b, a

        # old index -> new index: each colour follows its new position
        # (a queue per colour handles duplicate palette entries).
        slots: dict[tuple[int, int, int], deque[int]] = defaultdict(deque)
        for new_idx, colour in enumerate(new_palette):
            slots[colour].append(new_idx)
        old_to_new = np.arange(len(palette), dtype=np.uint16)
        for old_idx, colour in enumerate(palette):
            if slots.get(colour):
                old_to_new[old_idx] = slots[colour].popleft()

        pixels = np.array(img, dtype=np.uint16)
        limit = len(old_to_new)
        pixels = np.where(pixels < limit, old_to_new[np.minimum(pixels, limit - 1)], pixels).astype(np.uint8)

        out = Image.new("P", img.size)
        out.putpalette([c for rgb in new_palette for c in rgb])
        out.putdata(pixels.ravel().tolist())
        info = self._remap_transparency(img.info, old_to_new)

        buf = io.BytesIO()
        out.save(buf, format=img.format or "GIF", **info)
        stego = buf.getvalue()
        # Never report success on a payload that cannot be read back.
        if self.decode(stego) != bytes(payload_bytes):
            raise ValueError("Palette embedding did not survive saving this image; use another method")
        return stego

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        palette = self._palette_rgb(self._load_indexed(stego_bytes))
        sums = np.array([sum(c) for c in palette], dtype=np.int32)
        n_pairs = len(palette) // 2
        bits = (sums[0:2 * n_pairs:2] >= sums[1:2 * n_pairs:2]).astype(np.uint8)

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("Not enough palette pairs to read header")
        length = int.from_bytes(bits_to_bytes_np(bits[:HEADER_SIZE * 8]), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid payload length in palette header: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        if len(bits) < total_bits:
            raise ValueError("Not enough palette pairs to decode payload")
        return bits_to_bytes_np(bits[HEADER_SIZE * 8:total_bits])

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _load_indexed(data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "P":
            raise ValueError(
                f"Palette encoder requires an indexed-color (mode 'P') image. "
                f"Got mode: {img.mode}. Use a GIF or indexed PNG."
            )
        if getattr(img, "n_frames", 1) > 1:
            raise ValueError("Animated images are not supported by the palette method (only one frame would survive)")
        img.load()
        return img

    @staticmethod
    def _palette_rgb(img: Image.Image) -> list[tuple[int, int, int]]:
        raw = img.getpalette() or []
        return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw) - 2, 3)]

    @staticmethod
    def _remap_transparency(info: dict, old_to_new: np.ndarray) -> dict:
        """Carry the transparency index/table along with the reordered palette."""
        t = info.get("transparency")
        if t is None:
            return {}
        if isinstance(t, int):
            return {"transparency": int(old_to_new[t]) if t < len(old_to_new) else t}
        if isinstance(t, (bytes, bytearray)):
            table = bytearray([255]) * len(old_to_new)
            for old_idx, alpha in enumerate(bytes(t)):
                if old_idx < len(old_to_new):
                    table[int(old_to_new[old_idx])] = alpha
            return {"transparency": bytes(table)}
        return {}
