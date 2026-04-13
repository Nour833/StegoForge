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
import numpy as np
from scipy.stats import chi2 as chi2_dist
from PIL import Image

from detect.base import BaseDetector, DetectionResult

# Threshold above which we flag as detected
CONFIDENCE_THRESHOLD = 0.7


class Chi2Detector(BaseDetector):
    name = "chi2"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception as e:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": str(e)},
            )

        arr = np.array(img).flatten().astype(np.int32)

        # Count occurrences of each pixel value 0–255
        counts = np.bincount(arr, minlength=256)

        # Group into pairs (2k, 2k+1)
        pairs = counts[:256].reshape(-1, 2)
        valid_pairs = np.sum(pairs, axis=1) > 0
        valid_p = pairs[valid_pairs]
        expected = np.sum(valid_p, axis=1) / 2.0
        
        n_pairs = len(valid_p)
        if n_pairs == 0:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": "No valid pixel pairs found"},
            )
            
        chi2_stat = np.sum(((valid_p[:, 0] - expected) ** 2 + (valid_p[:, 1] - expected) ** 2) / expected)

        # Degrees of freedom = number of pairs
        p_value = chi2_dist.sf(chi2_stat, df=n_pairs)

        # High p-value = data fits the "equal pair" hypothesis = stego
        confidence = float(p_value)
        detected = confidence >= CONFIDENCE_THRESHOLD

        # Per-channel analysis for details
        channel_stats = {}
        for c_idx, c_name in enumerate(["R", "G", "B"]):
            channel = np.array(img)[:, :, c_idx].flatten().astype(np.int32)
            c_counts = np.bincount(channel, minlength=256)
            c_pairs = c_counts[:256].reshape(-1, 2)
            c_valid_mask = np.sum(c_pairs, axis=1) > 0
            c_valid = c_pairs[c_valid_mask]
            
            c_n_pairs = len(c_valid)
            if c_n_pairs > 0:
                c_exp = np.sum(c_valid, axis=1) / 2.0
                c_chi2 = np.sum(((c_valid[:, 0] - c_exp) ** 2 + (c_valid[:, 1] - c_exp) ** 2) / c_exp)
                c_pval = float(chi2_dist.sf(c_chi2, df=c_n_pairs))
                channel_stats[c_name] = {"chi2": round(c_chi2, 4), "p_value": round(c_pval, 4)}

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details={
                "chi2_statistic": round(chi2_stat, 4),
                "p_value": round(p_value, 4),
                "n_pairs": n_pairs,
                "channels": channel_stats,
                "interpretation": (
                    "High probability of LSB steganography" if detected
                    else "No significant LSB anomaly detected"
                ),
            },
        )
