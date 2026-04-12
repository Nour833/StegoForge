"""
core/video/dct.py - Keyframe-focused video embedding (PyAV required).

This implementation embeds bits in keyframes only and targets luminance-rich
pixels, following the spirit of conservative DCT-domain embedding.
"""
from __future__ import annotations

import hashlib
import io
import struct
import tempfile
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter

from core.base import BaseEncoder
from core.audio._convert import has_ffmpeg

MAGIC = b"SFVD"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


class VideoDCTEncoder(BaseEncoder):
    name = "video-dct"
    supported_extensions = [".mp4", ".webm"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        av = _require_av()
        with _temp_input(carrier_bytes, ".mp4") as inp:
            container = av.open(str(inp))
            stream = container.streams.video[0]
            keyframes = 0
            width = stream.width or 0
            height = stream.height or 0
            for frame in container.decode(video=0):
                if getattr(frame, "key_frame", False):
                    keyframes += 1
            container.close()

        blocks = (width // 8) * (height // 8)
        bits = keyframes * max(1, blocks)
        return max(0, (bits // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        _require_ffmpeg_runtime()
        av = _require_av()
        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, video-dct capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        bit_idx = 0
        key = kwargs.get("key")
        block = 8

        with _temp_input(carrier_bytes, ".mp4") as inp, tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as out_tmp:
            in_container = av.open(str(inp))
            in_stream = in_container.streams.video[0]

            out_container = av.open(out_tmp.name, mode="w")
            out_stream = out_container.add_stream("libx264", rate=in_stream.average_rate or 24)
            out_stream.width = in_stream.width
            out_stream.height = in_stream.height
            out_stream.pix_fmt = "yuv420p"

            frame_idx = 0
            for frame in in_container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                if getattr(frame, "key_frame", False) and bit_idx < len(bits):
                    y = arr[:, :, 1]
                    ordered_blocks = _ordered_block_positions(y, block, key, frame_idx, "video-dct")
                    for br, bc in ordered_blocks:
                        if bit_idx >= len(bits):
                            break
                        r = br * block + (block // 2)
                        c = bc * block + (block // 2)
                        y[r, c] = (y[r, c] & 0xFE) | bits[bit_idx]
                        bit_idx += 1
                    arr[:, :, 1] = y
                frame_idx += 1

                new_frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
                for packet in out_stream.encode(new_frame):
                    out_container.mux(packet)

            for packet in out_stream.encode(None):
                out_container.mux(packet)

            in_container.close()
            out_container.close()
            return Path(out_tmp.name).read_bytes()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        av = _require_av()
        bits = []
        key = kwargs.get("key")
        block = 8

        with _temp_input(stego_bytes, ".mp4") as inp:
            container = av.open(str(inp))
            frame_idx = 0
            for frame in container.decode(video=0):
                if not getattr(frame, "key_frame", False):
                    frame_idx += 1
                    continue
                arr = frame.to_ndarray(format="rgb24")
                y = arr[:, :, 1]
                ordered_blocks = _ordered_block_positions(y, block, key, frame_idx, "video-dct")
                for br, bc in ordered_blocks:
                    r = br * block + (block // 2)
                    c = bc * block + (block // 2)
                    bits.append(int(y[r, c]) & 1)
                frame_idx += 1
            container.close()

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("No video payload header found")

        header = _bits_to_bytes(bits[:HEADER_SIZE * 8])
        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge video payload found")

        total = (HEADER_SIZE + length) * 8
        if len(bits) < total:
            raise ValueError("Incomplete video payload")
        return _bits_to_bytes(bits[HEADER_SIZE * 8:total])


def _require_ffmpeg_runtime():
    if not has_ffmpeg():
        raise ValueError("video methods require ffmpeg. Install with: sudo apt install ffmpeg or pip install imageio-ffmpeg")


def _require_av():
    try:
        import av  # type: ignore
        return av
    except Exception as exc:
        raise ValueError("video methods require PyAV. Install with: pip install av") from exc


class _temp_input:
    def __init__(self, data: bytes, suffix: str):
        self.data = data
        self.suffix = suffix
        self.path = None

    def __enter__(self):
        f = tempfile.NamedTemporaryFile(suffix=self.suffix, delete=False)
        f.write(self.data)
        f.flush()
        f.close()
        self.path = Path(f.name)
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path and self.path.exists():
            self.path.unlink(missing_ok=True)


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = []
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)


def _ordered_block_positions(channel: np.ndarray, block: int, key: str | None, frame_idx: int, salt: str) -> list[tuple[int, int]]:
    h, w = channel.shape[:2]
    bh = h // block
    bw = w // block
    if bh <= 0 or bw <= 0:
        return []

    base = ((channel >> 1) << 1).astype(np.float32)
    gx = np.abs(np.diff(base, axis=1, prepend=base[:, :1]))
    gy = np.abs(np.diff(base, axis=0, prepend=base[:1, :]))
    texture = uniform_filter(gx + gy, size=5, mode="nearest")

    block_costs = []
    for br in range(bh):
        for bc in range(bw):
            y0 = br * block
            x0 = bc * block
            patch = texture[y0:y0 + block, x0:x0 + block]
            c = 1.0 / (float(np.mean(patch)) + 1e-3)
            block_costs.append((br, bc, c))

    if key:
        seed_material = f"{salt}:{frame_idx}:{key}".encode("utf-8")
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng(frame_idx)

    ties = rng.random(len(block_costs), dtype=np.float32)
    costs = np.array([round(x[2], 6) for x in block_costs], dtype=np.float32)
    order = np.lexsort((ties, costs))
    return [(block_costs[i][0], block_costs[i][1]) for i in order]
