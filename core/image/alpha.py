"""
core/image/alpha.py — Alpha channel steganography for PNG/WebP.

Embeds payload in the LSB of the alpha (transparency) channel.
Only pixels with alpha >= 128 are used — fully/semi-transparent pixels
are skipped to avoid visible artifacts when images are composited.

Visually, changing alpha LSB from 254→255 is completely imperceptible.
"""
import io
import struct
import numpy as np
from PIL import Image

from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4


class AlphaEncoder(BaseEncoder):
    name = "alpha"
    supported_extensions = [".png", ".webp"]

    def _load_rgba(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img

    def _usable_indices(self, alpha: np.ndarray) -> np.ndarray:
        """Return flat indices of pixels with alpha >= 128."""
        return np.where(alpha.flatten() >= 128)[0]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_rgba(carrier_bytes)
        alpha = np.array(img)[:, :, 3]
        usable = len(self._usable_indices(alpha))
        return (usable // 8) - HEADER_SIZE

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        img = self._load_rgba(carrier_bytes)
        fmt = img.format or "PNG"
        arr = np.array(img, dtype=np.uint8)

        alpha_flat = arr[:, :, 3].flatten()
        indices = self._usable_indices(arr[:, :, 3])

        cap = (len(indices) // 8) - HEADER_SIZE
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, "
                f"alpha channel capacity: {cap} bytes"
            )

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        arr_flat = arr.reshape(-1, 4)  # shape: (n_pixels, 4)
        bit_idx = 0
        for pixel_idx in indices:
            if bit_idx >= len(bits):
                break
            bit = bits[bit_idx]
            arr_flat[pixel_idx, 3] = (arr_flat[pixel_idx, 3] & 0xFE) | bit
            bit_idx += 1

        stego_arr = arr_flat.reshape(arr.shape)
        stego_img = Image.fromarray(stego_arr, mode="RGBA")
        buf = io.BytesIO()
        save_fmt = "WEBP" if fmt and fmt.upper() == "WEBP" else "PNG"
        save_kwargs = {"format": save_fmt}
        if save_fmt == "WEBP":
            save_kwargs["lossless"] = True
        stego_img.save(buf, **save_kwargs)
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        img = self._load_rgba(stego_bytes)
        arr = np.array(img, dtype=np.uint8)
        alpha_flat = arr[:, :, 3].flatten()
        indices = self._usable_indices(arr[:, :, 3])

        header_count = HEADER_SIZE * 8
        bits = []
        for idx in indices[:header_count]:
            bits.append(int(alpha_flat[idx]) & 1)

        if len(bits) < header_count:
            raise ValueError("Not enough opaque pixels to read header")

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:header_count]))[0]
        if length == 0 or length > 100_000_000:
            raise ValueError(f"Invalid payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        bits = []
        for idx in indices[:total_bits]:
            bits.append(int(alpha_flat[idx]) & 1)

        if len(bits) < total_bits:
            raise ValueError("Not enough pixels to decode payload")

        return _bits_to_bytes(bits[header_count:total_bits])


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
