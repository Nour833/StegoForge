"""
core/image/fingerprint.py — PRNU-aware LSB embedding.

Bits are written to the RGB samples in file order, but instead of overwriting
the least significant bit (LSB *replacement*), a sample whose parity is wrong
is moved by +1 or -1 (LSB *matching*): whichever step stays closest to the
local noise residual statistics of the carrier.

Wire format: ``[4-byte big-endian length][payload]``, one bit per sample.
"""
from __future__ import annotations

import numpy as np

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty
from core.image._io import load_rgb_alpha, save_rgb_alpha

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000
# Cost of moving a sample by one level, on top of its z-score against the local residual.
MOVE_PENALTY = 0.1


class FingerprintEncoder(BaseEncoder):
    name = "fingerprint-lsb"
    supported_extensions = [".png", ".bmp", ".webp"]

    def output_suffix(self, carrier_suffix: str) -> str:
        s = carrier_suffix.lower()
        return s if s in (".bmp", ".webp") else ".png"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        rgb, _, _ = load_rgb_alpha(carrier_bytes)
        return max(0, rgb.size // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, progress_callback=None, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        rgb, alpha, fmt = load_rgb_alpha(carrier_bytes)
        cap = max(0, rgb.size // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        n = len(bits)
        if progress_callback:
            progress_callback(0, n)

        mean, std = _residual_stats(rgb.astype(np.float32))
        mu = mean.reshape(-1)[:n]
        sd = std.reshape(-1)[:n] + 1e-6

        flat = rgb.reshape(-1)
        cur = flat[:n].astype(np.int16)
        wrong = (cur & 1) != bits
        # A wrong-parity sample moves one level; pick the step closest to the local residual.
        cost_down = np.abs((-1.0 - mu) / sd) + MOVE_PENALTY
        cost_up = np.abs((1.0 - mu) / sd) + MOVE_PENALTY
        can_down, can_up = cur >= 1, cur <= 254
        go_up = can_up & (~can_down | (cost_up < cost_down))
        step = np.where(go_up, 1, -1).astype(np.int16)
        flat[:n] = np.where(wrong, cur + step, cur).astype(np.uint8)

        if progress_callback:
            progress_callback(n, n)
        return save_rgb_alpha(rgb, alpha, fmt)

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        rgb, _, _ = load_rgb_alpha(stego_bytes)
        flat = rgb.reshape(-1)
        if flat.size < HEADER_SIZE * 8:
            raise ValueError("Carrier too small to contain a valid payload header")
        length = int.from_bytes(bits_to_bytes_np(flat[:HEADER_SIZE * 8] & 1), "big")
        max_cap = max(0, flat.size // 8 - HEADER_SIZE)
        if length <= 0 or length > min(max_cap, MAX_PAYLOAD):
            raise ValueError(f"Invalid fingerprint payload length: {length}")
        return bits_to_bytes_np(flat[:(HEADER_SIZE + length) * 8] & 1)[HEADER_SIZE:]


def _residual_stats(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    from scipy.ndimage import gaussian_filter, uniform_filter  # lazy: import cost only on use

    blurred = gaussian_filter(arr, sigma=(1.0, 1.0, 0.0), mode="reflect")
    residual = arr - blurred
    mu = uniform_filter(residual, size=(5, 5, 1), mode="reflect")
    mu2 = uniform_filter(residual * residual, size=(5, 5, 1), mode="reflect")
    var = np.maximum(mu2 - mu * mu, 1e-6)
    return mu, np.sqrt(var)
