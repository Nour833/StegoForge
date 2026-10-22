"""
core/video/motion.py — inter-frame luma embedding ("video-motion").

The complement of ``video-dct``: every frame that is *not* an anchor. Blocks are
ranked by texture plus temporal change against the previous frame, so bits land
where the picture is already busy or moving. This is a pixel-domain method that
targets motion; it does not touch H.264 motion vectors. See
``core/video/_luma.py`` for the shared engine and the limits of the method.
"""
from __future__ import annotations

from core.video._luma import ANCHOR_STRIDE, HEADER_FMT, HEADER_SIZE, LumaVideoEncoder

MAGIC = b"SFVM"
__all__ = ["VideoMotionEncoder", "MAGIC", "HEADER_FMT", "HEADER_SIZE"]


class VideoMotionEncoder(LumaVideoEncoder):
    name = "video-motion"
    magic = MAGIC
    salt = "video-motion"
    uses_motion = True

    def eligible(self, frame_idx: int) -> bool:
        return frame_idx % ANCHOR_STRIDE != 0

    def eligible_frames(self, frames: int) -> int:
        return frames - -(-frames // ANCHOR_STRIDE)
