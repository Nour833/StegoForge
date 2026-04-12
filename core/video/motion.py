"""
core/video/motion.py - P-frame focused embedding placeholder using PyAV.

This approximates motion-vector-domain embedding by targeting non-key frames.
"""
from __future__ import annotations

import hashlib
import struct
import numpy as np
from scipy.ndimage import uniform_filter

from core.video.dct import VideoDCTEncoder, _bytes_to_bits, _bits_to_bytes, _require_av, _temp_input
from core.base import BaseEncoder

MAGIC = b"SFVM"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


class VideoMotionEncoder(BaseEncoder):
    name = "video-motion"
    supported_extensions = [".mp4"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        # Conservative estimate: half of keyframe method for non-keyframes.
        return max(0, VideoDCTEncoder().capacity(carrier_bytes) // 2)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        av = _require_av()
        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, video-motion capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        bit_idx = 0
        key = kwargs.get("key")
        block = 8

        import tempfile
        from pathlib import Path

        with _temp_input(carrier_bytes, ".mp4") as inp, tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as out_tmp:
            in_container = av.open(str(inp))
            in_stream = in_container.streams.video[0]

            out_container = av.open(out_tmp.name, mode="w")
            out_stream = out_container.add_stream("libx264", rate=in_stream.average_rate or 24)
            out_stream.width = in_stream.width
            out_stream.height = in_stream.height
            out_stream.pix_fmt = "yuv420p"

            prev_base = None
            frame_idx = 0
            for frame in in_container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                if not getattr(frame, "key_frame", False) and bit_idx < len(bits):
                    ch = arr[:, :, 2]
                    ordered_blocks, prev_base = _ordered_motion_blocks(ch, block, key, frame_idx, prev_base)
                    for br, bc in ordered_blocks:
                        if bit_idx >= len(bits):
                            break
                        r = br * block + (block // 2)
                        c = bc * block + (block // 2)
                        ch[r, c] = (ch[r, c] & 0xFE) | bits[bit_idx]
                        bit_idx += 1
                    arr[:, :, 2] = ch
                else:
                    # Keep temporal baseline aligned across encode/decode.
                    prev_base = ((arr[:, :, 2] >> 1) << 1).astype(np.float32)
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
            prev_base = None
            frame_idx = 0
            for frame in container.decode(video=0):
                if getattr(frame, "key_frame", False):
                    arr = frame.to_ndarray(format="rgb24")
                    prev_base = ((arr[:, :, 2] >> 1) << 1).astype(np.float32)
                    frame_idx += 1
                    continue
                arr = frame.to_ndarray(format="rgb24")
                ch = arr[:, :, 2]
                ordered_blocks, prev_base = _ordered_motion_blocks(ch, block, key, frame_idx, prev_base)
                for br, bc in ordered_blocks:
                    r = br * block + (block // 2)
                    c = bc * block + (block // 2)
                    bits.append(int(ch[r, c]) & 1)
                frame_idx += 1
            container.close()

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("No video-motion payload header found")

        magic, length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:HEADER_SIZE * 8]))
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge video-motion payload found")

        total = (HEADER_SIZE + length) * 8
        if len(bits) < total:
            raise ValueError("Incomplete video-motion payload")
        return _bits_to_bytes(bits[HEADER_SIZE * 8:total])


def _ordered_motion_blocks(channel: np.ndarray, block: int, key: str | None, frame_idx: int, prev_base: np.ndarray | None):
    h, w = channel.shape[:2]
    bh = h // block
    bw = w // block
    if bh <= 0 or bw <= 0:
        return [], prev_base

    base = ((channel >> 1) << 1).astype(np.float32)
    gx = np.abs(np.diff(base, axis=1, prepend=base[:, :1]))
    gy = np.abs(np.diff(base, axis=0, prepend=base[:1, :]))
    texture = uniform_filter(gx + gy, size=5, mode="nearest")

    if prev_base is None or prev_base.shape != base.shape:
        motion = np.zeros_like(base, dtype=np.float32)
    else:
        motion = uniform_filter(np.abs(base - prev_base), size=5, mode="nearest")

    strength = texture + 1.2 * motion

    block_costs = []
    for br in range(bh):
        for bc in range(bw):
            y0 = br * block
            x0 = bc * block
            patch = strength[y0:y0 + block, x0:x0 + block]
            c = 1.0 / (float(np.mean(patch)) + 1e-3)
            block_costs.append((br, bc, c))

    if key:
        seed_material = f"video-motion:{frame_idx}:{key}".encode("utf-8")
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng(frame_idx)

    ties = rng.random(len(block_costs), dtype=np.float32)
    costs = np.array([round(x[2], 6) for x in block_costs], dtype=np.float32)
    order = np.lexsort((ties, costs))
    ordered = [(block_costs[i][0], block_costs[i][1]) for i in order]
    return ordered, base
