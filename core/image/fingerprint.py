"""
core/image/fingerprint.py - PRNU-aware LSB embedding.

The encoder estimates local residual statistics from the carrier and constrains
pixel adjustments to keep modifications inside a local noise envelope.
"""
import io
import struct

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter

from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4


class FingerprintEncoder(BaseEncoder):
    name = "fingerprint-lsb"
    supported_extensions = [".png", ".bmp", ".webp"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_image(carrier_bytes)
        arr = np.array(img, dtype=np.uint8)
        return max(0, (arr.size // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, progress_callback=None, **kwargs) -> bytes:
        img = self._load_image(carrier_bytes)
        fmt = (img.format or "PNG").upper()
        arr = np.array(img, dtype=np.int16)
        flat = arr.flatten()

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes")

        # Estimate residual statistics per channel.
        residual_mean, residual_std = _residual_stats(arr.astype(np.float32))
        mean_flat = residual_mean.flatten()
        std_flat = residual_std.flatten() + 1e-6

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        n = len(bits)
        for i, bit in enumerate(bits):
            cur = int(flat[i])
            if (cur & 1) == bit:
                if progress_callback and i % 10000 == 0:
                    progress_callback(i, n)
                continue

            # Candidate +/-1 values that set target bit.
            candidates = []
            for delta in (-1, 1):
                nv = cur + delta
                if 0 <= nv <= 255 and (nv & 1) == bit:
                    candidates.append(nv)

            if not candidates:
                flat[i] = cur ^ 1
            else:
                local_mu = float(mean_flat[i])
                local_sd = float(std_flat[i])
                best = candidates[0]
                best_cost = 1e18
                for cand in candidates:
                    residual = float(cand - cur)
                    z = abs((residual - local_mu) / local_sd)
                    # Penalize large residual outliers and unnecessary pixel movement.
                    cost = z + abs(cand - cur) * 0.1
                    if cost < best_cost:
                        best_cost = cost
                        best = cand
                flat[i] = best

            if progress_callback and i % 10000 == 0:
                progress_callback(i, n)

        if progress_callback:
            progress_callback(n, n)

        stego = np.clip(flat.reshape(arr.shape), 0, 255).astype(np.uint8)
        out = Image.fromarray(stego, mode="RGB")

        buf = io.BytesIO()
        if fmt == "WEBP":
            out.save(buf, format="WEBP", lossless=True)
        elif fmt == "BMP":
            out.save(buf, format="BMP")
        else:
            out.save(buf, format="PNG")
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        img = self._load_image(stego_bytes)
        arr = np.array(img, dtype=np.uint8).flatten()

        header_bits = [(int(arr[i]) & 1) for i in range(HEADER_SIZE * 8)]
        length = struct.unpack(HEADER_FMT, _bits_to_bytes(header_bits))[0]
        max_cap = self.capacity(stego_bytes)
        if length <= 0 or length > max_cap:
            raise ValueError(f"Invalid fingerprint payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        bits = [(int(arr[i]) & 1) for i in range(total_bits)]
        return _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])

    def _load_image(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img


def _residual_stats(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    blurred = gaussian_filter(arr, sigma=(1.0, 1.0, 0.0), mode="reflect")
    residual = arr - blurred
    mu = uniform_filter(residual, size=(5, 5, 1), mode="reflect")
    mu2 = uniform_filter(residual * residual, size=(5, 5, 1), mode="reflect")
    var = np.maximum(mu2 - mu * mu, 1e-6)
    return mu, np.sqrt(var)


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
