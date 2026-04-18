"""
core/image/palette.py — Indexed-color palette reordering for GIF and indexed PNG.

The palette of an indexed image is an ordered list of RGB triplets.
The order can be changed without changing visible colors — as long as
pixel index values are updated to point to the same color in its new position.

Encoding strategy:
  - Use pairs of palette entries: the relative order of each pair encodes 1 bit.
  - Pair (i, j): if palette[i] < palette[j] (by sum of RGB) → bit=0; else bit=1.
  - This is low capacity: max palette of 256 entries → ~127 bit pairs = ~15 bytes.

Note: Capacity is very small. This method is best for tiny hidden messages.
"""
import io
import struct
from PIL import Image

from core.base import BaseEncoder

HEADER_FMT = ">H"  # 2 bytes for length (max 65535 bytes, but real capacity is ~15)
HEADER_SIZE = 2


class PaletteEncoder(BaseEncoder):
    name = "palette"
    supported_extensions = [".gif", ".png"]

    def _load_indexed(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "P":
            raise ValueError(
                f"Palette encoder requires an indexed-color (mode 'P') image. "
                f"Got mode: {img.mode}. Use a GIF or indexed PNG."
            )
        return img

    def _get_palette_rgb(self, img: Image.Image) -> list[tuple[int, int, int]]:
        raw = img.getpalette()  # flat list: [R0,G0,B0, R1,G1,B1, ...]
        return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_indexed(carrier_bytes)
        palette = self._get_palette_rgb(img)
        n_pairs = len(palette) // 2
        usable_bits = n_pairs
        return max(0, (usable_bits // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        img = self._load_indexed(carrier_bytes)
        palette = self._get_palette_rgb(img)
        n_pairs = len(palette) // 2

        cap = (n_pairs // 8) - HEADER_SIZE
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, "
                f"palette capacity: {cap} bytes"
            )

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        # Encode each bit as the relative order of a palette pair
        # bit=0 → ensure palette[2i] "less than" palette[2i+1] (sum of RGB)
        # bit=1 → ensure palette[2i] "greater than" palette[2i+1]
        new_palette = list(palette)
        for i, bit in enumerate(bits):
            if i >= n_pairs:
                break
            a = new_palette[2 * i]
            b = new_palette[2 * i + 1]
            a_sum = sum(a)
            b_sum = sum(b)
            if bit == 0:
                # Ensure a < b
                if a_sum > b_sum:
                    new_palette[2 * i], new_palette[2 * i + 1] = b, a
            else:
                # Ensure a >= b
                if a_sum < b_sum:
                    new_palette[2 * i], new_palette[2 * i + 1] = b, a

        # Build pixel remapping: each pixel pointing to old index
        # needs to point to the index that now holds that color
        old_to_new = {}
        for old_idx, color in enumerate(palette):
            for new_idx, new_color in enumerate(new_palette):
                if new_color == color and new_idx not in old_to_new.values():
                    old_to_new[old_idx] = new_idx
                    break

        # Remap pixels (use numpy to avoid Pillow 14 getdata() deprecation)
        import numpy as np
        pixels = np.array(img).flatten().tolist()
        new_pixels = [old_to_new.get(p, p) for p in pixels]

        stego_img = img.copy()
        flat_palette = []
        for r, g, b in new_palette:
            flat_palette.extend([r, g, b])
        stego_img.putpalette(flat_palette)
        stego_img.putdata(new_pixels)

        buf = io.BytesIO()
        fmt = img.format or "GIF"
        stego_img.save(buf, format=fmt)
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        img = self._load_indexed(stego_bytes)
        palette = self._get_palette_rgb(img)
        n_pairs = len(palette) // 2

        bits = []
        for i in range(n_pairs):
            a = palette[2 * i]
            b = palette[2 * i + 1]
            bit = 1 if sum(a) >= sum(b) else 0
            bits.append(bit)

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("Not enough palette pairs to read header")

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:HEADER_SIZE * 8]))[0]
        if length == 0 or length > 10000:
            raise ValueError(f"Invalid payload length in palette header: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        if len(bits) < total_bits:
            raise ValueError("Not enough palette pairs to decode payload")

        return _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    result = []
    for i in range(0, len(bits) - 7, 8):
        val = 0
        for b in bits[i:i + 8]:
            val = (val << 1) | b
        result.append(val)
    return bytes(result)
