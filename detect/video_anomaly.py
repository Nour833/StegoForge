"""
detect/video_anomaly.py — video steganography check.

The only positive verdict is a *validated extraction*: an unkeyed ``video-dct``
or ``video-motion`` payload whose magic and length fields check out (a chance
match is about 2**-32 per method). Statistics over a handful of frames cannot
separate stego from clean video — a z-score of a sample against its own mean and
spread flags roughly one clean clip in three — so none is used for a verdict.
Keyed or non-StegoForge embeddings are therefore reported as inconclusive,
never as clean.
"""
from __future__ import annotations

import logging
from importlib import import_module

from detect.base import BaseDetector, DetectionResult

log = logging.getLogger(__name__)

_EXTRACTORS = (
    ("video-dct", "core.video.dct", "VideoDCTEncoder"),
    ("video-motion", "core.video.motion", "VideoMotionEncoder"),
)


def _skipped(reason: str) -> DetectionResult:
    return DetectionResult(
        method=VideoAnomalyDetector.name,
        detected=False,
        confidence=0.0,
        details={"skipped": True, "interpretation": reason},
    )


class VideoAnomalyDetector(BaseDetector):
    name = "video-anomaly"
    supported_extensions = [".mp4", ".webm"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            import av  # type: ignore  # noqa: F401
        except Exception:  # noqa: BLE001 - optional dependency
            return _skipped("PyAV not installed; video analysis skipped")

        from core.video.scan import scan_video

        try:
            scan = scan_video(file_bytes)
        except ValueError as exc:
            log.debug("video-anomaly: unreadable input: %s", exc)
            return _skipped("Invalid or unsupported video input")

        details: dict = {
            "width": scan.width,
            "height": scan.height,
            "frames": scan.frames,
            "keyframes": scan.keyframes,
        }
        for method, module, cls in _EXTRACTORS:
            encoder = getattr(import_module(module), cls)()
            try:
                payload = encoder.decode(file_bytes)
            except ValueError as exc:
                log.debug("video-anomaly: %s extraction failed: %s", method, exc)
                continue
            details.update(
                extracted_by=method,
                interpretation=f"StegoForge {method} payload extracted ({len(payload)} bytes)",
            )
            res = DetectionResult(method=self.name, detected=True, confidence=1.0, details=details)
            res.extracted_payload = payload
            return res

        details["interpretation"] = (
            "No unkeyed StegoForge video payload found; keyed or other embeddings are not ruled out"
        )
        details["inconclusive"] = True
        return DetectionResult(method=self.name, detected=False, confidence=0.0, details=details)
