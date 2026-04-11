"""
detect/video_anomaly.py - Basic keyframe anomaly scan.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import numpy as np
from scipy.fft import dct

from detect.base import BaseDetector, DetectionResult


class VideoAnomalyDetector(BaseDetector):
    name = "video-anomaly"
    supported_extensions = [".mp4", ".webm"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            import av  # type: ignore
        except Exception:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={
                    "skipped": True,
                    "interpretation": "PyAV not installed; video anomaly analysis skipped",
                },
            )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp.flush()
            path = Path(tmp.name)

        scores = []
        keyframes = 0
        try:
            container = av.open(str(path))
            for frame in container.decode(video=0):
                if not getattr(frame, "key_frame", False):
                    continue
                keyframes += 1
                arr = frame.to_ndarray(format="gray")
                scores.append(_frame_score(arr))
                if keyframes >= 12:
                    break
            container.close()
        except Exception:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={
                    "skipped": True,
                    "interpretation": "Invalid or unsupported video input",
                },
            )
        finally:
            path.unlink(missing_ok=True)

        if not scores:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"skipped": True, "interpretation": "No keyframes sampled"},
            )

        m = float(np.mean(scores))
        s = float(np.std(scores) + 1e-6)
        zmax = max(abs((x - m) / s) for x in scores)
        confidence = float(min(1.0, zmax / 6.0))
        detected = confidence >= 0.35

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details={
                "keyframes_sampled": keyframes,
                "score_mean": round(m, 6),
                "score_std": round(s, 6),
                "interpretation": (
                    "I-frame DCT distribution deviates from expected baseline"
                    if detected else "No strong keyframe DCT anomaly detected"
                ),
            },
        )


def _frame_score(gray: np.ndarray) -> float:
    h, w = gray.shape
    h8 = h - (h % 8)
    w8 = w - (w % 8)
    g = gray[:h8, :w8].astype(np.float32)
    vals = []
    for r in range(0, h8, 8):
        for c in range(0, w8, 8):
            block = g[r:r + 8, c:c + 8]
            coeff = dct(dct(block.T, norm="ortho").T, norm="ortho")
            vals.append(abs(float(coeff[3, 4])) + abs(float(coeff[4, 3])))
    if not vals:
        return 0.0
    return float(np.mean(vals))
