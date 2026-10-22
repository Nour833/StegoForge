"""
core/image/dct.py — DCT sign-modulation steganography for JPEG.

Method (honest summary): the image is decoded to pixels, the **green channel**
is split into 8x8 blocks, and the sign of the mid-frequency DCT coefficient
(4, 4) of each block carries one bit (positive = 0, negative = 1). The
coefficient magnitude is raised to a Watson-style perceptual floor so the sign
survives JPEG quantisation, and the result is saved as JPEG (quality 95, 4:4:4).

This works on the *pixel-domain* DCT of the decoded image, not on the stored
quantised JPEG coefficients, so it is a robust, simple scheme rather than an
F5/OutGuess-class one. Measured bit-error rate after re-compression is 0 down
to JPEG quality 76 (see ``tests/test_image_dct.py``).

Wire format: ``[4-byte big-endian length][payload]``, one bit per 8x8 block.
"""
from __future__ import annotations

import io
import warnings

import numpy as np
from PIL import Image

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty
from core.image._io import check_pixel_budget

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000
BLOCK = 8
# Coefficient (4, 4): mid-frequency, carries signal and survives quantisation.
TARGET_ROW = 4
TARGET_COL = 4
JND_EMBED_FLOOR = 18.0
JND_EMBED_MULT = 1.15

# Watson-style perceptual controls (practical approximation).
WATSON_LUMA_ALPHA = 0.649
WATSON_CONTRAST_GAMMA = 0.7
JND_SAFE_MAX_THRESHOLD = 42.0
MEAN_LUMA_REF = 128.0

# JPEG luminance quantisation table (quality 50 baseline) used as masking prior.
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


def _fft():
    from scipy.fft import dctn, idctn  # lazy: keeps import fast without scipy

    return dctn, idctn


def _blocks(plane: np.ndarray) -> np.ndarray:
    """Reshape a 2-D plane to (rows, cols, 8, 8) blocks, cropping any ragged edge."""
    nbh, nbw = plane.shape[0] // BLOCK, plane.shape[1] // BLOCK
    return plane[:nbh * BLOCK, :nbw * BLOCK].reshape(nbh, BLOCK, nbw, BLOCK).transpose(0, 2, 1, 3)


class DCTEncoder(BaseEncoder):
    name = "dct"
    supported_extensions = [".jpg", ".jpeg"]

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".jpeg" if carrier_suffix.lower() == ".jpeg" else ".jpg"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        img = self._load_jpeg(carrier_bytes)
        w, h = img.size
        return max(0, ((w // BLOCK) * (h // BLOCK)) // 8 - HEADER_SIZE)

    def jnd_safe_capacity(self, carrier_bytes: bytes) -> int:
        """Conservative perceptual (JND-safe) payload budget for this carrier."""
        arr = np.array(self._load_jpeg(carrier_bytes).convert("L"), dtype=np.float32)
        if arr.shape[0] < BLOCK or arr.shape[1] < BLOCK:
            return 0
        dctn, _ = _fft()
        blocks = _blocks(arr)
        coeffs = dctn(blocks, type=2, norm="ortho", axes=(-2, -1))
        target = np.abs(coeffs[:, :, TARGET_ROW, TARGET_COL])
        means = blocks.mean(axis=(-2, -1))
        t_luma = JPEG_LUMA_QTABLE[TARGET_ROW, TARGET_COL] * np.power(
            np.maximum(means, 1.0) / MEAN_LUMA_REF, WATSON_LUMA_ALPHA
        )
        t_contrast = np.maximum(
            t_luma,
            np.power(target + 1e-6, WATSON_CONTRAST_GAMMA) * np.power(t_luma, 1.0 - WATSON_CONTRAST_GAMMA),
        )
        usable_bits = int(np.sum(t_contrast <= JND_SAFE_MAX_THRESHOLD))
        return max(0, usable_bits // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        img = self._load_jpeg(carrier_bytes)
        arr = np.array(img, dtype=np.float64)
        h, w = arr.shape[:2]

        cap = max(0, ((w // BLOCK) * (h // BLOCK)) // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, DCT capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))

        # Work on the green channel for colour images, or the only channel.
        chan_idx = 1 if arr.ndim == 3 else None
        work = arr[:, :, chan_idx].copy() if chan_idx is not None else arr.copy()

        dctn, idctn = _fft()
        blocks = _blocks(work)
        nbh, nbw = blocks.shape[:2]
        dcts = dctn(blocks, type=2, norm="ortho", axes=(-2, -1))

        nbits = min(len(bits), nbh * nbw)
        flat_dcts = dcts.reshape(-1, BLOCK, BLOCK)
        cur = np.abs(flat_dcts[:nbits, TARGET_ROW, TARGET_COL])
        means = blocks.reshape(-1, BLOCK, BLOCK)[:nbits].mean(axis=(-2, -1))
        t_luma = float(JPEG_LUMA_QTABLE[TARGET_ROW, TARGET_COL]) * np.power(
            np.maximum(means, 1.0) / MEAN_LUMA_REF, WATSON_LUMA_ALPHA
        )
        t_contrast = np.maximum(
            t_luma,
            np.power(cur + 1e-6, WATSON_CONTRAST_GAMMA) * np.power(t_luma, 1.0 - WATSON_CONTRAST_GAMMA),
        )
        target_abs = np.maximum(JND_EMBED_FLOOR, t_contrast * JND_EMBED_MULT)
        signs = np.where(bits[:nbits] == 0, 1.0, -1.0)
        flat_dcts[:nbits, TARGET_ROW, TARGET_COL] = signs * np.maximum(cur, target_abs)

        restored = idctn(flat_dcts.reshape(nbh, nbw, BLOCK, BLOCK), norm="ortho", axes=(-2, -1))
        work[:nbh * BLOCK, :nbw * BLOCK] = restored.transpose(0, 2, 1, 3).reshape(nbh * BLOCK, nbw * BLOCK)
        if chan_idx is not None:
            arr[:, :, chan_idx] = work
        else:
            arr = work

        save_kwargs: dict = {"format": "JPEG", "quality": 95, "subsampling": 0}
        for k in ("icc_profile", "exif"):
            if img.info.get(k):
                save_kwargs[k] = img.info[k]
        buf = io.BytesIO()
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(buf, **save_kwargs)
        stego = buf.getvalue()

        # Never report success on a payload that JPEG quantisation destroyed.
        if self.decode(stego) != bytes(payload_bytes):
            raise ValueError("DCT embedding did not survive JPEG quantisation for this carrier; use a larger or more textured image")
        return stego

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        img = self._load_jpeg(stego_bytes)
        arr = np.array(img, dtype=np.float64)
        plane = arr[:, :, 1] if arr.ndim == 3 else arr
        if plane.shape[0] < BLOCK or plane.shape[1] < BLOCK:
            raise ValueError("Carrier too small to contain DCT header")

        dctn, _ = _fft()
        coeffs = dctn(_blocks(plane), type=2, norm="ortho", axes=(-2, -1))[:, :, TARGET_ROW, TARGET_COL].reshape(-1)
        bits = (coeffs < 0).astype(np.uint8)  # positive = 0, negative = 1

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("Carrier too small to contain DCT header")
        length = int.from_bytes(bits_to_bytes_np(bits[:HEADER_SIZE * 8]), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid DCT payload length: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        if len(bits) < total_bits:
            raise ValueError("Not enough DCT blocks to decode payload")
        return bits_to_bytes_np(bits[HEADER_SIZE * 8:total_bits])

    @staticmethod
    def _load_jpeg(data: bytes) -> Image.Image:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            opened = Image.open(io.BytesIO(data))
            check_pixel_budget(opened.size)
            opened.load()
        if opened.mode in ("RGB", "L"):
            return opened
        img = opened.convert("RGB")
        img.info.pop("icc_profile", None)  # e.g. a CMYK profile no longer describes the pixels
        return img
