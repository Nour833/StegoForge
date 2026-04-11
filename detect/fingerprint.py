"""
detect/fingerprint.py - PRNU inconsistency detector.
"""
from __future__ import annotations

import io
from pathlib import Path

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
        threshold = float(np.mean(score_map) + 2.5 * np.std(score_map))
        anomalous_fraction = float(np.mean(score_map > threshold))
        confidence = float(min(1.0, anomalous_fraction * 12.0))
        detected = confidence >= 0.25

        heatmap_path = None
        if detected:
            heatmap_path = self._write_heatmap(score_map, filename)

        details = {
            "anomalous_fraction": round(anomalous_fraction, 6),
            "threshold": round(threshold, 6),
            "heatmap": heatmap_path,
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

    def _write_heatmap(self, score_map: np.ndarray, filename: str) -> str:
        scaled = np.clip(score_map / max(1e-6, np.percentile(score_map, 99)), 0.0, 1.0)
        rgb = np.zeros((scaled.shape[0], scaled.shape[1], 3), dtype=np.uint8)
        rgb[:, :, 0] = (scaled * 255).astype(np.uint8)
        rgb[:, :, 1] = (scaled * 180).astype(np.uint8)
        rgb[:, :, 2] = (scaled * 40).astype(np.uint8)

        stem = Path(filename).stem if filename else "stegoforge"
        path = Path.cwd() / f"{stem}_fingerprint_heatmap.png"
        Image.fromarray(rgb, mode="RGB").save(path, format="PNG")
        return str(path)
