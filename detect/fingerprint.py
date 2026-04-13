"""
detect/fingerprint.py - PRNU inconsistency detector.
"""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter

from detect.base import BaseDetector, DetectionResult


class FingerprintDetector(BaseDetector):
    name = "fingerprint"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            arr = np.array(img, dtype=np.float32)
        except Exception as exc:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": str(exc), "skipped": True},
            )

        residual = self._noise_residual(arr)
        score_map = self._anomaly_map(residual)

        # High z-score regions imply local residual inconsistency.
        threshold = float(np.mean(score_map) + 4.0 * np.std(score_map))
        anomalous_fraction = float(np.mean(score_map > threshold))

        # Natural images often keep a non-trivial heavy-tail residual; calibrate against it.
        baseline = 0.006
        excess = max(0.0, anomalous_fraction - baseline)

        confidence = float(min(1.0, excess * 80.0))
        detected = confidence >= 0.55

        heatmap_b64 = None
        if detected:
            heatmap_b64 = self._heatmap_png_b64(score_map)

        details = {
            "anomalous_fraction": round(anomalous_fraction, 6),
            "threshold": round(threshold, 6),
            "heatmap_b64": heatmap_b64,
            "interpretation": (
                "Residual statistics contain spatial inconsistencies suggestive of tampering"
                if detected
                else "No strong PRNU inconsistency pattern detected"
            ),
        }

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details=details,
        )

    def _noise_residual(self, arr: np.ndarray) -> np.ndarray:
        den = gaussian_filter(arr, sigma=(1.0, 1.0, 0.0), mode="reflect")
        return arr - den

    def _anomaly_map(self, residual: np.ndarray) -> np.ndarray:
        mag = np.mean(np.abs(residual), axis=2)
        local_mu = uniform_filter(mag, size=9, mode="reflect")
        local_mu2 = uniform_filter(mag * mag, size=9, mode="reflect")
        local_std = np.sqrt(np.maximum(local_mu2 - local_mu * local_mu, 1e-6))
        return np.abs((mag - local_mu) / (local_std + 1e-6))

    def _heatmap_png_b64(self, score_map: np.ndarray) -> str:
        scaled = np.clip(score_map / max(1e-6, np.percentile(score_map, 99)), 0.0, 1.0)
        rgb = np.zeros((scaled.shape[0], scaled.shape[1], 3), dtype=np.uint8)
        rgb[:, :, 0] = (scaled * 255).astype(np.uint8)
        rgb[:, :, 1] = (scaled * 180).astype(np.uint8)
        rgb[:, :, 2] = (scaled * 40).astype(np.uint8)

        buf = io.BytesIO()
        Image.fromarray(rgb, mode="RGB").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
