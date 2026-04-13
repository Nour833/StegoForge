"""
detect/rs.py — Regular-Singular (RS) analysis for LSB steganography.

RS analysis can estimate the fraction of pixels carrying hidden data
without having the key. It's based on how LSB embedding disrupts the
spatial smoothness of natural images.

Method:
  1. Divide image into groups of n pixels
  2. Apply a "flipping" function F (toggle pixel LSBs)
  3. Measure "smoothness" of each group with a discriminant function
  4. Classify groups as Regular (R) or Singular (S) based on smoothness change
  5. Track ratio R/S — this changes predictably with embedding rate

For a clean image: R ≈ S ≈ 50%
For a fully embedded image: R and S equalize further

Confidence is proportional to deviation from expected natural image ratios.
"""
import io
import numpy as np
from PIL import Image

from detect.base import BaseDetector, DetectionResult

GROUP_SIZE = 4  # pixels per analysis group


class RSDetector(BaseDetector):
    name = "rs"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("L")  # grayscale
        except Exception as e:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": str(e)},
            )

        arr = np.array(img, dtype=np.int32).flatten()

        n_groups = len(arr) // GROUP_SIZE
        if n_groups == 0:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": "Image too small for RS analysis"},
            )

        arr_trunc = arr[:n_groups * GROUP_SIZE]
        groups = arr_trunc.reshape(-1, GROUP_SIZE)

        # Discriminant function: sum of absolute differences between adjacent pixels in group
        d_orig = np.sum(np.abs(np.diff(groups, axis=1)), axis=1)

        # Flipped groups (toggle LSB) and their discriminants
        groups_flip = groups ^ 1
        d_flip = np.sum(np.abs(np.diff(groups_flip, axis=1)), axis=1)

        # Inverse flip groups and discriminants (for simplicity same as flip in original)
        groups_flip_n = groups ^ 1
        d_flip_n = np.sum(np.abs(np.diff(groups_flip_n, axis=1)), axis=1)

        # Count Regular and Singular groups
        R = int(np.sum(d_flip > d_orig))
        S = int(np.sum(d_flip < d_orig))
        R_n = int(np.sum(d_flip_n > d_orig))
        S_n = int(np.sum(d_flip_n < d_orig))

        r_ratio = R / n_groups
        s_ratio = S / n_groups
        r_n_ratio = R_n / n_groups
        s_n_ratio = S_n / n_groups

        # Estimate payload fraction using RS formula
        # p ≈ (R - S) / (2 * (R - S) - (R_n - S_n)) — simplified Fridrich formula
        rs_diff = r_ratio - s_ratio
        neg_diff = r_n_ratio - s_n_ratio
        denominator = 2 * rs_diff - neg_diff

        if abs(denominator) < 1e-10:
            estimated_fraction = 0.0
        else:
            estimated_fraction = min(1.0, max(0.0, rs_diff / denominator if denominator != 0 else 0.0))

        # Confidence: high fraction → more confident in detection
        confidence = min(1.0, estimated_fraction * 2.0)
        # Natural images have |estimated_fraction| ≈ 0
        detected = estimated_fraction > 0.05 and confidence > 0.1

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details={
                "estimated_payload_fraction": round(float(estimated_fraction), 4),
                "regular_groups": R,
                "singular_groups": S,
                "total_groups": n_groups,
                "r_ratio": round(r_ratio, 4),
                "s_ratio": round(s_ratio, 4),
                "interpretation": (
                    f"~{int(estimated_fraction * 100)}% of pixels estimated to carry hidden data"
                    if detected
                    else "No significant payload detected by RS analysis"
                ),
            },
        )
