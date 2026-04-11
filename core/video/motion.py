"""
core/video/motion.py - P-frame focused embedding placeholder using PyAV.

This approximates motion-vector-domain embedding by targeting non-key frames.
"""
from __future__ import annotations

import struct

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

            for frame in in_container.decode(video=0):
                arr = frame.to_ndarray(format="rgb24")
                if not getattr(frame, "key_frame", False) and bit_idx < len(bits):
                    flat = arr[:, :, 2].flatten()
                    for i in range(len(flat)):
                        if bit_idx >= len(bits):
                            break
                        flat[i] = (flat[i] & 0xFE) | bits[bit_idx]
                        bit_idx += 1
                    arr[:, :, 2] = flat.reshape(arr[:, :, 2].shape)

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
        with _temp_input(stego_bytes, ".mp4") as inp:
            container = av.open(str(inp))
            for frame in container.decode(video=0):
                if getattr(frame, "key_frame", False):
                    continue
                arr = frame.to_ndarray(format="rgb24")
                for v in arr[:, :, 2].flatten():
                    bits.append(int(v) & 1)
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
