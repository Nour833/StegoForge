"""
core/image/adaptive.py - Adaptive content-aware LSB steganography.

This encoder uses a WOW-style directional residual cost map and writes bits in
the lowest-cost regions first (textured/high-entropy pixels), which reduces the
statistical footprint compared to uniform LSB embedding.
"""
import hashlib
import io
import struct

import numpy as np
from PIL import Image
from scipy.ndimage import convolve, uniform_filter

from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4


class AdaptiveLSBEncoder(BaseEncoder):
    name = "adaptive-lsb"
    supported_extensions = [".png", ".bmp", ".webp"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_image(carrier_bytes)
        arr = np.array(img, dtype=np.uint8)
        return max(0, (arr.size // 8) - HEADER_SIZE)

    def encode(
        self,
        carrier_bytes: bytes,
        payload_bytes: bytes,
        key: str | None = None,
        **kwargs,
    ) -> bytes:
        img = self._load_image(carrier_bytes)
        fmt = (img.format or "PNG").upper()
        arr = np.array(img, dtype=np.uint8)
        flat = arr.flatten()

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        ordered = self._ordered_channel_indices(arr, key)
        if len(bits) > len(ordered):
            raise ValueError("Carrier too small for adaptive embedding")

        for i, bit in enumerate(bits):
            idx = int(ordered[i])
            flat[idx] = (flat[idx] & 0xFE) | bit

        stego = flat.reshape(arr.shape)
        out = Image.fromarray(stego, mode="RGB")

        buf = io.BytesIO()
        if fmt == "WEBP":
            out.save(buf, format="WEBP", lossless=True)
        elif fmt == "BMP":
            out.save(buf, format="BMP")
        else:
            out.save(buf, format="PNG")
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        img = self._load_image(stego_bytes)
        arr = np.array(img, dtype=np.uint8)
        flat = arr.flatten()
        ordered = self._ordered_channel_indices(arr, key)

        header_bits = []
        for i in range(HEADER_SIZE * 8):
            idx = int(ordered[i])
            header_bits.append(int(flat[idx]) & 1)

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(header_bits))[0]
        max_cap = self.capacity(stego_bytes)
        if length <= 0 or length > max_cap:
            raise ValueError(f"Invalid adaptive payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        if total_bits > len(ordered):
            raise ValueError("Carrier does not contain enough adaptive-ordered bits")

        bits = []
        for i in range(total_bits):
            idx = int(ordered[i])
            bits.append(int(flat[idx]) & 1)

        return _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])

    def _ordered_channel_indices(self, arr: np.ndarray, key: str | None) -> np.ndarray:
        # Remove LSB impact so stego decode recomputes an identical ordering.
        gray = ((arr >> 1).mean(axis=2)).astype(np.float32)

        # WOW-style directional high-pass residuals: smooth regions produce low
        # residual energy (high embedding cost), textured regions produce higher
        # residual energy (low embedding cost).
        kernels = [
            np.array([[-1.0, 2.0, -1.0], [2.0, -4.0, 2.0], [-1.0, 2.0, -1.0]], dtype=np.float32),
            np.array([[-1.0, -1.0, -1.0], [2.0, 2.0, 2.0], [-1.0, -1.0, -1.0]], dtype=np.float32),
            np.array([[-1.0, 2.0, -1.0], [-1.0, 2.0, -1.0], [-1.0, 2.0, -1.0]], dtype=np.float32),
        ]

        residual_energy = np.zeros_like(gray, dtype=np.float32)
        for k in kernels:
            r = convolve(gray, k, mode="reflect")
            residual_energy += uniform_filter(np.abs(r), size=5, mode="reflect")

        # Blend in local variance to stabilize costs on natural images.
        mean = uniform_filter(gray, size=5, mode="reflect")
        mean_sq = uniform_filter(gray * gray, size=5, mode="reflect")
        var = np.maximum(mean_sq - mean * mean, 0.0)
        texture = residual_energy + np.sqrt(var + 1e-6)
        cost = 1.0 / (texture + 1e-4)

        cost_flat = np.repeat(cost.flatten(), 3)
        quantized = np.round(cost_flat, 4)

        if key:
            seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(seed)
        else:
            rng = np.random.default_rng(0)

        # Stable tie-breaking keeps ordering reproducible while reducing sensitivity.
        tie = rng.random(len(quantized), dtype=np.float32)
        return np.lexsort((tie, quantized))

    def _load_image(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = []
    for i in range(0, len(bits) - 7, 8):
        val = 0
        for b in bits[i:i + 8]:
            val = (val << 1) | b
        out.append(val)
    return bytes(out)
