"""
core/video/dct.py — anchor-frame luma embedding ("video-dct").

One payload bit per 8x8 luma block, busiest blocks first, on every
``ANCHOR_STRIDE``-th frame (frames 0, 12, 24, ...) — the frames a typical GOP
starts on. Frames are chosen by index, not by the encoder's keyframe flag, so
the lossless re-encode cannot move them. See ``core/video/_luma.py`` for the
shared engine and the limits of the method.
"""
from __future__ import annotations

from core.video._luma import ANCHOR_STRIDE, HEADER_FMT, HEADER_SIZE, LumaVideoEncoder

MAGIC = b"SFVD"
__all__ = ["VideoDCTEncoder", "MAGIC", "HEADER_FMT", "HEADER_SIZE"]


class VideoDCTEncoder(LumaVideoEncoder):
    name = "video-dct"
    magic = MAGIC
    salt = "video-dct"
    uses_motion = False

    def eligible(self, frame_idx: int) -> bool:
        return frame_idx % ANCHOR_STRIDE == 0

    def eligible_frames(self, frames: int) -> int:
        return -(-frames // ANCHOR_STRIDE)
