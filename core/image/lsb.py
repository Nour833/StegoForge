"""
core/image/lsb.py — LSB (Least Significant Bit) steganography for images.

Supports: PNG, BMP, RGBA variants
Supports: 1–4 bit depth, any channel order, polymorphic traversal.

Wire format embedded in pixels:
  [4 bytes big-endian uint32: payload length][payload bytes]

Capacity at depth=1: (width × height × channels) / 8 bytes
"""
import io
import struct
import numpy as np
from PIL import Image

from core.base import BaseEncoder
from core.crypto.polymorphic import derive_encoding_params, fisher_yates_indices

HEADER_FMT = ">I"
HEADER_SIZE = 4


class LSBEncoder(BaseEncoder):
    name = "lsb"
    supported_extensions = [".png", ".bmp", ".tiff", ".webp"]

    def capacity(self, carrier_bytes: bytes, depth: int = 1, **kwargs) -> int:
        """Return maximum payload bytes (excluding 4-byte header)."""
        img = self._load_image(carrier_bytes)
        arr = np.array(img)
        total_channels = arr.size  # width * height * channels
        total_bits = total_channels * depth
        return (total_bits // 8) - HEADER_SIZE

    def encode(
        self,
        carrier_bytes: bytes,
        payload_bytes: bytes,
        depth: int = 1,
        key: str | None = None,
        **kwargs,
    ) -> bytes:
        """
        Embed payload_bytes into carrier image.

        Args:
            carrier_bytes: Raw image file bytes.
            payload_bytes: Data to hide (already encrypted by caller).
            depth: Bits per channel to use (1–4). Higher = more capacity, less invisible.
            key: If provided, use polymorphic pixel traversal seeded by key.

        Returns:
            Stego image bytes in the same format as the carrier.
        """
        img = self._load_image(carrier_bytes)
        fmt = img.format or "PNG"
        arr = np.array(img, dtype=np.uint8)
        flat = arr.flatten()

        cap = self.capacity(carrier_bytes, depth=depth)
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, capacity: {cap} bytes"
            )

        # Prepend 4-byte length header
        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        # Build traversal order
        indices = self._build_indices(flat, key)

        # Embed bits into flat array
        mask = (0xFF << depth) & 0xFF  # mask to clear lower `depth` bits
        bit_idx = 0
        for idx in indices:
            if bit_idx >= len(bits):
                break
            chunk = bits[bit_idx:bit_idx + depth]
            chunk_val = _bits_to_int(chunk)
            flat[idx] = (flat[idx] & mask) | chunk_val
            bit_idx += depth

        stego_arr = flat.reshape(arr.shape)
        stego_img = Image.fromarray(stego_arr, mode=img.mode)

        buf = io.BytesIO()
        save_kwargs = {}
        if fmt.upper() == "PNG":
            save_kwargs["format"] = "PNG"
            # Preserve DPI and other info
            if hasattr(img, "info"):
                if "dpi" in img.info:
                    save_kwargs["dpi"] = img.info["dpi"]
        elif fmt.upper() in ("TIFF", "TIF"):
            save_kwargs["format"] = "TIFF"
        elif fmt.upper() == "BMP":
            save_kwargs["format"] = "BMP"
        elif fmt.upper() == "WEBP":
            save_kwargs["format"] = "WEBP"
            save_kwargs["lossless"] = True
        else:
            save_kwargs["format"] = "PNG"

        stego_img.save(buf, **save_kwargs)
        return buf.getvalue()

    def decode(
        self,
        stego_bytes: bytes,
        depth: int = 1,
        key: str | None = None,
        **kwargs,
    ) -> bytes:
        """
        Extract payload from stego image.

        Raises:
            ValueError: If no valid payload found or header is invalid.
        """
        img = self._load_image(stego_bytes)
        arr = np.array(img, dtype=np.uint8)
        flat = arr.flatten()

        indices = self._build_indices(flat, key)

        # Extract bits — enough for header first
        header_bits_needed = HEADER_SIZE * 8
        bits = []
        for idx in indices:
            if len(bits) >= header_bits_needed:
                break
            val = flat[idx]
            for bit_pos in range(depth - 1, -1, -1):
                bits.append((val >> bit_pos) & 1)

        if len(bits) < header_bits_needed:
            raise ValueError("Carrier too small to contain a valid payload header")

        length_bytes = _bits_to_bytes(bits[:header_bits_needed])
        length = struct.unpack(HEADER_FMT, length_bytes)[0]

        if length == 0 or length > 100_000_000:  # sanity: max 100MB
            raise ValueError(f"Invalid payload length in header: {length}")

        # Extract all payload bits
        total_bits_needed = (HEADER_SIZE + length) * 8
        bits = []
        for idx in indices:
            if len(bits) >= total_bits_needed:
                break
            val = flat[idx]
            for bit_pos in range(depth - 1, -1, -1):
                bits.append((val >> bit_pos) & 1)

        if len(bits) < total_bits_needed:
            raise ValueError("Carrier does not contain enough data for declared payload length")

        payload = _bits_to_bytes(bits[header_bits_needed:total_bits_needed])
        return payload

    def _load_image(self, data: bytes) -> Image.Image:
        """Load image from bytes, converting to RGB or RGBA."""
        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "RGBA", "L", "LA"):
            if img.mode == "P":
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
        return img

    def _build_indices(self, flat: np.ndarray, key: str | None) -> list[int]:
        """Return traversal order for flat pixel array."""
        n = len(flat)
        if key:
            params = derive_encoding_params(key)
            if params["row_reversed"]:
                indices = list(range(n - 1, -1, -1))
            else:
                indices = fisher_yates_indices(n, params["shuffle_seed"])
        else:
            indices = list(range(n))
        return indices


# ── Bit manipulation helpers ──────────────────────────────────────────────────

def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_int(bits: list[int]) -> int:
    val = 0
    for b in bits:
        val = (val << 1) | b
    return val


def _bits_to_bytes(bits: list[int]) -> bytes:
    result = []
    for i in range(0, len(bits) - 7, 8):
        byte_bits = bits[i:i + 8]
        result.append(_bits_to_int(byte_bits))
    return bytes(result)
