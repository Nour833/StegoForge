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
        chi2_stat = 0.0
        n_pairs = 0
        for k in range(0, 256, 2):
            observed_0 = counts[k]
            observed_1 = counts[k + 1]
            expected = (observed_0 + observed_1) / 2.0
            if expected > 0:
                chi2_stat += ((observed_0 - expected) ** 2 + (observed_1 - expected) ** 2) / expected
                n_pairs += 1

        if n_pairs == 0:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": "No valid pixel pairs found"},
            )

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
            c_chi2 = 0.0
            c_pairs = 0
            for k in range(0, 256, 2):
                exp = (c_counts[k] + c_counts[k + 1]) / 2.0
                if exp > 0:
                    c_chi2 += ((c_counts[k] - exp) ** 2 + (c_counts[k + 1] - exp) ** 2) / exp
                    c_pairs += 1
            if c_pairs > 0:
                c_pval = float(chi2_dist.sf(c_chi2, df=c_pairs))
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
