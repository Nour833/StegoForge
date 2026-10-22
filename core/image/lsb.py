"""
core/image/lsb.py — LSB (least significant bit) steganography for raster images.

Supports PNG, BMP, TIFF and (lossless) WebP carriers in RGB / RGBA / L / LA,
1-4 bits per sample, sequential or key-seeded traversal.

Wire format embedded in the samples::

    [4-byte big-endian payload length][payload bytes]

written MSB-first, ``depth`` bits per sample, into the low bits of each sample.
The final group is zero-padded so the decoder (which reads whole groups) stays
in sync.

Traversal order
---------------
* no key  — samples in file order;
* ``v2``  — every new keyed embed: a key-seeded permutation of *all* samples
  (frozen ``RandomState`` stream, see ``core/crypto/polymorphic.py``);
* ``legacy`` — what StegoForge <= 1.1.5 wrote for keyed embeds: half of all
  keys produced a reversed sequential scan and the rest an LCG shuffle. Kept
  for decoding only; a keyed decode tries ``v2`` first, then ``legacy``.
"""
from __future__ import annotations

import io
import warnings

import numpy as np
from PIL import Image

from core.base import BaseEncoder
from core.bits import (
    bits_to_bytes_np,
    bytes_to_bits_np,
    pack_depth_chunks_np,
    unpack_depth_chunks_np,
    validate_depth,
    validate_payload_not_empty,
)
from core.config import get_config
from core.crypto.polymorphic import derive_encoding_params, fisher_yates_indices, keyed_permutation

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000          # sanity cap on a declared payload length
_SAVE_FORMATS = {"PNG", "BMP", "TIFF", "WEBP"}
_CHANNELS = {"L": 1, "LA": 2, "RGB": 3, "RGBA": 4}
_NATIVE_MODES = tuple(_CHANNELS)


class LSBEncoder(BaseEncoder):
    name = "lsb"
    supported_extensions = [".png", ".bmp", ".tiff", ".webp"]

    def output_suffix(self, carrier_suffix: str) -> str:
        s = carrier_suffix.lower()
        return s if s in (".png", ".bmp", ".tiff", ".webp") else (".tiff" if s == ".tif" else ".png")

    # ── public API ────────────────────────────────────────────────────────────

    def capacity(self, carrier_bytes: bytes, depth: int = 1, **kwargs) -> int:
        """Maximum payload bytes (excluding the 4-byte length header)."""
        validate_depth(depth)
        w, h, channels, _ = self._probe(carrier_bytes)
        return max(0, (w * h * channels * depth) // 8 - HEADER_SIZE)

    def encode(
        self,
        carrier_bytes: bytes,
        payload_bytes: bytes,
        depth: int = 1,
        key: str | None = None,
        **kwargs,
    ) -> bytes:
        """Embed ``payload_bytes`` (already encrypted by the caller) into the carrier."""
        validate_depth(depth)
        validate_payload_not_empty(payload_bytes)
        img, fmt = self._load_image(carrier_bytes)
        arr = np.array(img, dtype=np.uint8)
        flat = arr.reshape(-1)

        cap = max(0, (flat.size * depth) // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes")

        data = len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes)
        chunks = pack_depth_chunks_np(bytes_to_bits_np(data), depth)
        order = self._traversal(flat.size, key, kwargs.get("traversal", "v2"))
        mask = np.uint8((0xFF << depth) & 0xFF)
        if order is None:
            flat[:len(chunks)] = (flat[:len(chunks)] & mask) | chunks
        else:
            idx = order[:len(chunks)]
            flat[idx] = (flat[idx] & mask) | chunks

        return self._save(arr, fmt, img.info)

    def decode(
        self,
        stego_bytes: bytes,
        depth: int = 1,
        key: str | None = None,
        **kwargs,
    ) -> bytes:
        """Extract the payload.

        Raises:
            ValueError: no valid payload header / declared length impossible.
        """
        validate_depth(depth)
        img, _ = self._load_image(stego_bytes)
        flat = np.array(img, dtype=np.uint8).reshape(-1)

        last_exc: ValueError | None = None
        for scheme in (("v2", "legacy") if key else ("plain",)):
            try:
                return self._decode_with(flat, depth, self._traversal(flat.size, key, scheme))
            except ValueError as exc:
                last_exc = exc
        raise last_exc if last_exc is not None else ValueError("LSB decode failed")

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _decode_with(flat: np.ndarray, depth: int, order: np.ndarray | None) -> bytes:
        low = np.uint8((1 << depth) - 1)
        hdr_groups = -(-HEADER_SIZE * 8 // depth)
        if flat.size < hdr_groups:
            raise ValueError("Carrier too small to contain a valid payload header")

        def read(groups: int) -> np.ndarray:
            vals = flat[:groups] if order is None else flat[order[:groups]]
            return unpack_depth_chunks_np(vals & low, depth)

        length = int.from_bytes(bits_to_bytes_np(read(hdr_groups)[:HEADER_SIZE * 8]), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid payload length in header: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        groups = -(-total_bits // depth)
        if groups > flat.size:
            raise ValueError("Carrier does not contain enough data for declared payload length")
        return bits_to_bytes_np(read(groups)[HEADER_SIZE * 8:total_bits])

    @staticmethod
    def _traversal(n: int, key: str | None, scheme: str) -> np.ndarray | None:
        """Sample visit order: ``None`` means plain file order."""
        if not key or scheme == "plain":
            return None
        if scheme not in ("v2", "legacy"):
            raise ValueError(f"Unknown traversal scheme: {scheme!r}")
        if n > get_config().max_keyed_samples:
            raise ValueError(
                "Carrier is too large for a keyed traversal "
                f"({n:,} samples > {get_config().max_keyed_samples:,}); use a smaller image or no key"
            )
        params = derive_encoding_params(key)
        if scheme == "v2":
            return keyed_permutation(n, params["shuffle_seed"])
        if params["row_reversed"]:
            return np.arange(n - 1, -1, -1, dtype=np.int64)
        return np.asarray(fisher_yates_indices(n, params["shuffle_seed"]), dtype=np.int64)

    @staticmethod
    def _probe(data: bytes) -> tuple[int, int, int, str | None]:
        """(width, height, channels after normalisation, source format) without decoding pixels."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > get_config().max_image_pixels:
            raise ValueError(f"Image too large ({w}x{h} px exceeds the {get_config().max_image_pixels:,} pixel limit)")
        mode = img.mode
        if mode not in _NATIVE_MODES:
            mode = "RGBA" if mode == "P" else "RGB"
        return w, h, _CHANNELS[mode], img.format

    def _load_image(self, data: bytes) -> tuple[Image.Image, str]:
        """Open and normalise to RGB/RGBA/L/LA. Returns (image, output format)."""
        self._probe(data)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            opened = Image.open(io.BytesIO(data))
            fmt = (opened.format or "PNG").upper()
            opened.load()
        img: Image.Image = opened
        if img.mode not in _NATIVE_MODES:
            img = img.convert("RGBA" if img.mode == "P" else "RGB")
        return img, (fmt if fmt in _SAVE_FORMATS else "PNG")

    @staticmethod
    def _save(arr: np.ndarray, fmt: str, info: dict) -> bytes:
        out = Image.fromarray(arr)
        kwargs: dict = {"format": fmt}
        if fmt == "PNG":
            for k in ("dpi", "icc_profile"):
                if k in info:
                    kwargs[k] = info[k]
        elif fmt == "WEBP":
            # exact=True: libwebp otherwise zeroes RGB under fully transparent pixels.
            kwargs.update(lossless=True, exact=True)
        buf = io.BytesIO()
        out.save(buf, **kwargs)
        return buf.getvalue()
