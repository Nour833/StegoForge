"""core/video/scan.py — single-scan video metadata helper.

``scan_video`` reads the container once (demux only, no pixel decode) and
caches the result by a hash of the *whole* file, so capacity, encode and
``video_context`` share one scan. The key covers every byte: a cheaper
head+tail key collides for files that differ only in the middle.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

_CACHE_MAX = 32
_CACHE: dict[str, VideoScan] = {}
_LOCK = threading.Lock()


@dataclass
class VideoScan:
    width: int
    height: int
    keyframes: int
    frames: int
    duration_sec: float


def _cache_key(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def scan_video(carrier_bytes: bytes) -> VideoScan:
    """Return dimensions, keyframe/frame counts and duration of the first video stream."""
    from core.video._luma import require_av, temp_file

    key = _cache_key(carrier_bytes)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit

    av = require_av()
    with temp_file(carrier_bytes) as path:
        try:
            container = av.open(str(path))
        except av.error.FFmpegError:
            raise ValueError("Not a readable video file") from None
        try:
            streams = container.streams.video
            if not streams:
                raise ValueError("No video stream found in this file")
            stream = streams[0]
            frames = keyframes = 0
            for packet in container.demux(stream):
                if packet.size:
                    frames += 1
                    keyframes += bool(packet.is_keyframe)
            if stream.duration and stream.time_base:
                duration_sec = float(stream.duration * stream.time_base)
            elif container.duration:
                duration_sec = container.duration / av.time_base
            else:
                duration_sec = 0.0
            scan = VideoScan(stream.width or 0, stream.height or 0, keyframes, frames, duration_sec)
        except av.error.FFmpegError:
            raise ValueError("Video file is truncated or corrupted") from None
        finally:
            container.close()

    with _LOCK:
        _CACHE[key] = scan
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
    return scan
