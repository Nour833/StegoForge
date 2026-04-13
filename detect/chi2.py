"""
detect/chi2.py — Chi-square attack on LSB steganography.

In a natural image, pixel value pairs (2k, 2k+1) appear with roughly
equal frequency. LSB embedding disrupts this by replacing pixel LSBs
with payload bits, which equalizes the pair frequencies.

The chi-square test measures this equalization: a p-value close to 1.0
indicates uniform LSB distribution = likely LSB steganography.

Confidence score: 0.0 = natural image, 1.0 = almost certainly stego.
"""
import io
import os

import numpy as np
from scipy.stats import chi2 as chi2_dist
from scipy.fft import dct as scipy_dct
from PIL import Image

from detect.base import BaseDetector, DetectionResult

# Threshold above which we flag as detected.
CONFIDENCE_THRESHOLD = 0.7

JPEG_BLOCK = 8
JPEG_TARGET_ROW = 4
JPEG_TARGET_COL = 4
JPEG_EMBED_FLOOR = 18.0


class Chi2Detector(BaseDetector):
    name = "chi2"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
                img = img.convert("RGBA")
                channels = ["R", "G", "B", "A"]
            else:
                img = img.convert("RGB")
                channels = ["R", "G", "B"]
        except Exception as e:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": str(e)},
            )

        arr = np.array(img, dtype=np.int32)

        p_value, chi2_stat, n_pairs = self._chi2_pvalue(arr.reshape(-1))
        if n_pairs == 0:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": "No valid pixel pairs found"},
            )

        channel_stats = {}
        for c_idx, c_name in enumerate(channels):
            c_pval, c_chi2, c_n_pairs = self._chi2_pvalue(arr[:, :, c_idx].reshape(-1))
            if c_n_pairs > 0:
                channel_stats[c_name] = {
                    "chi2": round(float(c_chi2), 4),
                    "p_value": round(float(c_pval), 4),
                }

        jpeg_dct_confidence = 0.0
        jpeg_dct_details = {}
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        is_jpeg = ext in (".jpg", ".jpeg") or str(getattr(img, "format", "")).upper() == "JPEG"
        if is_jpeg:
            jpeg_dct_confidence, jpeg_dct_details = self._jpeg_dct_signal(img)

        spatial_confidence = float(p_value)
        confidence = max(spatial_confidence, jpeg_dct_confidence)
        detected = confidence >= CONFIDENCE_THRESHOLD

        if jpeg_dct_confidence >= CONFIDENCE_THRESHOLD and jpeg_dct_confidence >= spatial_confidence:
            interpretation = "Potential JPEG DCT sign-pattern embedding detected"
        elif spatial_confidence >= CONFIDENCE_THRESHOLD:
            interpretation = "High probability of LSB steganography"
        else:
            interpretation = "No significant LSB/DCT anomaly detected"

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details={
                "chi2_statistic": round(float(chi2_stat), 4),
                "p_value": round(float(p_value), 4),
                "n_pairs": n_pairs,
                "spatial_confidence": round(spatial_confidence, 4),
                "jpeg_dct_confidence": round(jpeg_dct_confidence, 4),
                "jpeg_dct": jpeg_dct_details,
                "channels": channel_stats,
                "interpretation": interpretation,
            },
        )

    def _chi2_pvalue(self, values: np.ndarray) -> tuple[float, float, int]:
        clipped = np.clip(values, 0, 255).astype(np.int32)
        counts = np.bincount(clipped, minlength=256)
        pairs = counts.reshape(-1, 2)
        totals = np.sum(pairs, axis=1)

        valid = totals > 0
        n_pairs = int(np.sum(valid))
        if n_pairs == 0:
            return 0.0, 0.0, 0

        valid_pairs = pairs[valid]
        expected = np.sum(valid_pairs, axis=1) / 2.0
        chi2_stat = float(np.sum(((valid_pairs[:, 0] - expected) ** 2 + (valid_pairs[:, 1] - expected) ** 2) / expected))
        p_value = float(chi2_dist.sf(chi2_stat, df=n_pairs))
        return p_value, chi2_stat, n_pairs

    def _jpeg_dct_signal(self, img: Image.Image) -> tuple[float, dict]:
        rgb = np.array(img.convert("RGB"), dtype=np.float64)
        channel = rgb[:, :, 1]
        h, w = channel.shape
        if h < JPEG_BLOCK or w < JPEG_BLOCK:
            return 0.0, {"reason": "image too small for 8x8 DCT blocks"}

        coeffs: list[float] = []
        for row in range(0, h - JPEG_BLOCK + 1, JPEG_BLOCK):
            for col in range(0, w - JPEG_BLOCK + 1, JPEG_BLOCK):
                block = channel[row:row + JPEG_BLOCK, col:col + JPEG_BLOCK]
                block_dct = self._dct2(block)
                coeffs.append(float(block_dct[JPEG_TARGET_ROW, JPEG_TARGET_COL]))

        values = np.array(coeffs, dtype=np.float64)
        n_blocks = int(values.size)
        if n_blocks < 64:
            return 0.0, {"reason": "not enough blocks", "blocks": n_blocks}

        if n_blocks >= 1024:
            front_n = min(max(512, n_blocks // 20), n_blocks // 2)
        else:
            front_n = max(16, n_blocks // 4)

        abs_vals = np.abs(values)
        front = abs_vals[:front_n]
        tail = abs_vals[front_n:] if front_n < n_blocks else abs_vals[:front_n]

        front_mean = float(np.mean(front))
        tail_mean = float(np.mean(tail))
        front_frac_ge = float(np.mean(front >= JPEG_EMBED_FLOOR))
        tail_frac_ge = float(np.mean(tail >= JPEG_EMBED_FLOOR))
        front_sign_pos = float(np.mean(values[:front_n] >= 0))

        delta_frac = front_frac_ge - tail_frac_ge
        delta_mean = front_mean - tail_mean

        score_frac = float(np.clip((delta_frac - 0.08) / 0.35, 0.0, 1.0))
        score_mean = float(np.clip((delta_mean - 2.5) / 12.0, 0.0, 1.0))
        score_sign = float(np.clip((0.18 - abs(front_sign_pos - 0.5)) / 0.18, 0.0, 1.0))
        confidence = float(np.clip(0.65 * score_frac + 0.25 * score_mean + 0.10 * score_sign, 0.0, 1.0))

        return confidence, {
            "blocks": n_blocks,
            "front_blocks": int(front_n),
            "front_mean_abs": round(front_mean, 4),
            "tail_mean_abs": round(tail_mean, 4),
            "front_frac_ge18": round(front_frac_ge, 4),
            "tail_frac_ge18": round(tail_frac_ge, 4),
            "front_sign_positive": round(front_sign_pos, 4),
            "delta_frac_ge18": round(delta_frac, 4),
            "delta_mean_abs": round(delta_mean, 4),
        }

    def _dct2(self, block: np.ndarray) -> np.ndarray:
        return scipy_dct(scipy_dct(block.T, norm="ortho").T, norm="ortho")
