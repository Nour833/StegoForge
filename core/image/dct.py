"""
core/image/dct.py — DCT coefficient steganography for JPEG images.

This implementation takes a more reliable approach:
1. Load the JPEG → pixel array
2. Hide bits using a mid-frequency DCT approach with Watson-style JND constraints:
   - Work in 8×8 DCT blocks on the spatial domain
    - Compute a perceptual threshold per block/coefficient
    - Encode by setting coefficient sign (positive = 0, negative = 1) with minimum
      magnitude constrained by the local JND threshold
3. Save as JPEG quality 95 with no chroma subsampling

Capacity: ~(W/8 × H/8) bits per channel, minus header overhead
"""
import io
import struct
import numpy as np
from PIL import Image
from scipy.fft import dct as scipy_dct, idct as scipy_idct

from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4
BLOCK = 8
# Use coefficient (4, 4) — mid-frequency, carries good signal, survives JPEG
TARGET_ROW = 4
TARGET_COL = 4
JND_EMBED_FLOOR = 18.0
JND_EMBED_MULT = 1.15

# Watson-style perceptual controls (practical approximation).
WATSON_LUMA_ALPHA = 0.649
WATSON_CONTRAST_GAMMA = 0.7
JND_SAFE_MAX_THRESHOLD = 42.0
MEAN_LUMA_REF = 128.0

# JPEG luminance quantization table (quality 50 baseline) used as masking prior.
JPEG_LUMA_QTABLE = np.array([
    [16, 11, 10, 16, 24, 40, 51, 61],
    [12, 12, 14, 19, 26, 58, 60, 55],
    [14, 13, 16, 24, 40, 57, 69, 56],
    [14, 17, 22, 29, 51, 87, 80, 62],
    [18, 22, 37, 56, 68, 109, 103, 77],
    [24, 35, 55, 64, 81, 104, 113, 92],
    [49, 64, 78, 87, 103, 121, 120, 101],
    [72, 92, 95, 98, 112, 100, 103, 99],
], dtype=np.float64)


class DCTEncoder(BaseEncoder):
    name = "dct"
    supported_extensions = [".jpg", ".jpeg"]

    def _load_jpeg(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode == "RGBA":
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return img

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_jpeg(carrier_bytes)
        w, h = img.size
        n_blocks = (w // BLOCK) * (h // BLOCK)
        return (n_blocks // 8) - HEADER_SIZE

    def jnd_safe_capacity(self, carrier_bytes: bytes) -> int:
        """
        Estimate a conservative perceptual (JND-safe) payload budget.

        This heuristic models that only a subset of mid-frequency coefficients in
        each 8x8 block can be modified without noticeable artifacts.
        """
        img = self._load_jpeg(carrier_bytes)
        arr = np.array(img.convert("L"), dtype=np.float32)
        h, w = arr.shape

        usable_bits = 0
        for row in range(0, h - BLOCK + 1, BLOCK):
            for col in range(0, w - BLOCK + 1, BLOCK):
                block = arr[row:row + BLOCK, col:col + BLOCK]
                coeff = _dct2(block)
                jnd = _watson_jnd_threshold(coeff, block)
                if jnd <= JND_SAFE_MAX_THRESHOLD:
                    usable_bits += 1

        return max(0, (usable_bits // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        img = self._load_jpeg(carrier_bytes)
        arr = np.array(img, dtype=np.float64)
        h, w = arr.shape[:2]
        channels = 1 if len(arr.shape) == 2 else arr.shape[2]

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, DCT capacity: {cap} bytes"
            )

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        bit_idx = 0

        # Work on green channel for RGB (index 1), or the only channel
        chan_idx = 1 if channels >= 3 else 0

        if channels >= 3:
            work_chan = arr[:, :, chan_idx].copy()
        else:
            work_chan = arr.copy()

        for row in range(0, h - BLOCK + 1, BLOCK):
            for col in range(0, w - BLOCK + 1, BLOCK):
                if bit_idx >= len(bits):
                    break
                block = work_chan[row:row + BLOCK, col:col + BLOCK]
                block_dct = _dct2(block)
                jnd = _watson_jnd_threshold(block_dct, block)

                bit = bits[bit_idx]
                target_sign = 1.0 if bit == 0 else -1.0
                target_abs = max(JND_EMBED_FLOOR, jnd * JND_EMBED_MULT)
                cur = block_dct[TARGET_ROW, TARGET_COL]
                block_dct[TARGET_ROW, TARGET_COL] = target_sign * max(abs(cur), target_abs)

                work_chan[row:row + BLOCK, col:col + BLOCK] = _idct2(block_dct)
                bit_idx += 1

        if channels >= 3:
            arr[:, :, chan_idx] = work_chan
        else:
            arr = work_chan

        arr = np.clip(arr, 0, 255).astype(np.uint8)
        stego_img = Image.fromarray(arr, mode=img.mode)

        buf = io.BytesIO()
        stego_img.save(buf, format="JPEG", quality=95, subsampling=0)
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        img = self._load_jpeg(stego_bytes)
        arr = np.array(img, dtype=np.float64)
        h, w = arr.shape[:2]
        channels = 1 if len(arr.shape) == 2 else arr.shape[2]

        chan_idx = 1 if channels >= 3 else 0
        if channels >= 3:
            work_chan = arr[:, :, chan_idx]
        else:
            work_chan = arr

        all_bits = []
        for row in range(0, h - BLOCK + 1, BLOCK):
            for col in range(0, w - BLOCK + 1, BLOCK):
                block = work_chan[row:row + BLOCK, col:col + BLOCK]
                block_dct = _dct2(block)
                coeff = block_dct[TARGET_ROW, TARGET_COL]
                # Positive = 0, Negative = 1
                all_bits.append(0 if coeff >= 0 else 1)

        if len(all_bits) < HEADER_SIZE * 8:
            raise ValueError("Carrier too small to contain DCT header")

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(all_bits[:HEADER_SIZE * 8]))[0]
        if length == 0 or length > 100_000_000:
            raise ValueError(f"Invalid DCT payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        if len(all_bits) < total_bits:
            raise ValueError("Not enough DCT blocks to decode payload")

        return _bits_to_bytes(all_bits[HEADER_SIZE * 8:total_bits])


def _dct2(block: np.ndarray) -> np.ndarray:
    return scipy_dct(scipy_dct(block.T, norm="ortho").T, norm="ortho")


def _idct2(block: np.ndarray) -> np.ndarray:
    return scipy_idct(scipy_idct(block.T, norm="ortho").T, norm="ortho")


def _watson_jnd_threshold(block_dct: np.ndarray, block_spatial: np.ndarray) -> float:
    base = float(JPEG_LUMA_QTABLE[TARGET_ROW, TARGET_COL])

    # Luminance masking: brighter blocks can tolerate slightly stronger changes.
    block_mean = max(float(np.mean(block_spatial)), 1.0)
    luma_scale = (block_mean / MEAN_LUMA_REF) ** WATSON_LUMA_ALPHA
    t_luma = base * luma_scale

    # Contrast masking: if coefficient energy already exists, larger changes blend in.
    c_abs = abs(float(block_dct[TARGET_ROW, TARGET_COL]))
    t_contrast = max(t_luma, (c_abs + 1e-6) ** WATSON_CONTRAST_GAMMA * (t_luma ** (1.0 - WATSON_CONTRAST_GAMMA)))

    return float(max(1.0, t_contrast))


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
