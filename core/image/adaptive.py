"""
core/image/adaptive.py — adaptive, content-aware LSB steganography.

A WOW-style directional residual cost map ranks every RGB sample; bits are
written into the cheapest (most textured) samples first, which keeps the
statistical footprint smaller than uniform LSB embedding.

The ranking is computed from the carrier with its LSBs masked off, so the
decoder re-derives exactly the same order from the stego image. An alpha
channel, if present, is carried through untouched.

Wire format: ``[4-byte big-endian length][payload]``, one bit per ranked sample.

Compatibility note: the key-seeded tie-break uses ``numpy.random.default_rng``
exactly as StegoForge <= 1.1.5 did. Changing it would orphan existing carriers.
"""
from __future__ import annotations

import hashlib

import numpy as np

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty
from core.image._io import load_rgb_alpha, save_rgb_alpha

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000


def _ndimage():
    from scipy.ndimage import convolve, uniform_filter  # lazy: import cost only on use

    return convolve, uniform_filter


class AdaptiveLSBEncoder(BaseEncoder):
    name = "adaptive-lsb"
    supported_extensions = [".png", ".bmp", ".webp"]

    def output_suffix(self, carrier_suffix: str) -> str:
        s = carrier_suffix.lower()
        return s if s in (".bmp", ".webp") else ".png"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        rgb, _, _ = load_rgb_alpha(carrier_bytes)
        return max(0, (rgb.size // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        rgb, alpha, fmt = load_rgb_alpha(carrier_bytes)
        flat = rgb.reshape(-1)

        cap = max(0, (flat.size // 8) - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        idx = self._ordered_channel_indices(rgb, key)[:len(bits)]
        flat[idx] = (flat[idx] & 0xFE) | bits

        return save_rgb_alpha(rgb, alpha, fmt)

    def decode(self, stego_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        rgb, _, _ = load_rgb_alpha(stego_bytes)
        flat = rgb.reshape(-1)
        if flat.size < HEADER_SIZE * 8:
            raise ValueError("Carrier too small to contain a valid payload header")
        ordered = self._ordered_channel_indices(rgb, key)

        header = bits_to_bytes_np(flat[ordered[:HEADER_SIZE * 8]] & 1)
        length = int.from_bytes(header, "big")
        max_cap = max(0, (flat.size // 8) - HEADER_SIZE)
        if length <= 0 or length > min(max_cap, MAX_PAYLOAD):
            raise ValueError(f"Invalid adaptive payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        bits = flat[ordered[:total_bits]] & 1
        return bits_to_bytes_np(bits[HEADER_SIZE * 8:])

    # ── internals ─────────────────────────────────────────────────────────────

    def _ordered_channel_indices(self, rgb: np.ndarray, key: str | None) -> np.ndarray:
        # Remove LSB impact so stego decode recomputes an identical ordering.
        gray = ((rgb >> 1).mean(axis=2)).astype(np.float32)

        # WOW-style directional high-pass residuals: smooth regions give low
        # residual energy (high embedding cost), textured regions give higher
        # residual energy (low embedding cost).
        kernels = [
            np.array([[-1.0, 2.0, -1.0], [2.0, -4.0, 2.0], [-1.0, 2.0, -1.0]], dtype=np.float32),
            np.array([[-1.0, -1.0, -1.0], [2.0, 2.0, 2.0], [-1.0, -1.0, -1.0]], dtype=np.float32),
            np.array([[-1.0, 2.0, -1.0], [-1.0, 2.0, -1.0], [-1.0, 2.0, -1.0]], dtype=np.float32),
        ]

        residual_energy = np.zeros_like(gray, dtype=np.float32)
        convolve, uniform_filter = _ndimage()
        for k in kernels:
            r = convolve(gray, k, mode="reflect")
            residual_energy += uniform_filter(np.abs(r), size=5, mode="reflect")

        # Blend in local variance to stabilise costs on natural images.
        mean = uniform_filter(gray, size=5, mode="reflect")
        mean_sq = uniform_filter(gray * gray, size=5, mode="reflect")
        var = np.maximum(mean_sq - mean * mean, 0.0)
        texture = residual_energy + np.sqrt(var + 1e-6)
        cost = 1.0 / (texture + 1e-4)

        quantized = np.round(np.repeat(cost.flatten(), 3), 4)

        if key:
            seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(seed)
        else:
            rng = np.random.default_rng(0)

        # Stable tie-breaking keeps ordering reproducible while reducing sensitivity.
        tie = rng.random(len(quantized), dtype=np.float32)
        return np.lexsort((tie, quantized))
