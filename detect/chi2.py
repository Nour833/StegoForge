"""
detect/chi2.py — Chi-square attack on LSB steganography.

In a natural image, pixel value pairs (2k, 2k+1) appear with roughly
equal frequency. LSB embedding disrupts this by replacing pixel LSBs
with payload bits, which equalizes the pair frequencies.

The chi-square test measures this equalization: a p-value close to 1.0
indicates uniform LSB distribution = likely LSB steganography.

Confidence score: 0.0 = natural image, 1.0 = almost certainly stego.

How the verdict is reached
==========================
The classic test only fires when *the whole image* is embedded. StegoForge's
unkeyed LSB embed is sequential, so a payload equalises a **prefix** of the
sample stream and leaves the tail untouched. The detector therefore

* scans prefix windows (the full stream, then halves, quarters, ...) and keeps
  the best p-value (``p_head``), and
* tests the untouched tail (the last quarter, ``p_tail``).

``p_head`` is evidence only when the tail is *clearly not equalised*
(``p_tail < TAIL_MAX_P``): then the carrier has real pair statistics and a
prefix that has lost them has been modified. If the tail is equalised as well
(noise-like carrier, or a payload filling the image) the test cannot tell clean
from stego, so it reports ``reliable=False`` with confidence 0.0 instead of
guessing. Pairs with fewer than ``MIN_PAIR_TOTAL`` samples are skipped (the
chi-square approximation needs an expected count of at least 5) and constant
planes, such as an opaque alpha channel, are excluded: they add a term as large
as the pixel count and would mask every embed.
"""
import io
import os

import numpy as np
from scipy.stats import chi2 as chi2_dist
from scipy.fft import dctn as scipy_dctn
from PIL import Image

from detect.base import BaseDetector, DetectionResult

# Threshold above which we flag as detected.
CONFIDENCE_THRESHOLD = 0.7
# JPEG-DCT sub-signal threshold (calibrated 2026-09-22: clean JPEGs score
# <=0.09, DCT embeds score >=0.55; spatial threshold stays at 0.7 because
# clean high-entropy images reach 0.68 there).
JPEG_DCT_THRESHOLD = 0.5

JPEG_BLOCK = 8
JPEG_TARGET_ROW = 4
JPEG_TARGET_COL = 4
JPEG_EMBED_FLOOR = 18.0

MIN_PAIR_TOTAL = 10      # expected count per cell >= 5
MIN_WINDOW = 2048        # smallest prefix window (samples)
MAX_HALVINGS = 6         # full stream, 1/2, ... 1/64
TAIL_FRACTION = 0.25
TAIL_MAX_P = 0.01        # the untouched tail must be clearly non-equalised


class Chi2Detector(BaseDetector):
    name = "chi2"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        try:
            opened = Image.open(io.BytesIO(file_bytes))
            if opened.mode in ("RGBA", "LA", "PA") or "transparency" in opened.info:
                img = opened.convert("RGBA")
                channels = ["R", "G", "B", "A"]
            else:
                img = opened.convert("RGB")
                channels = ["R", "G", "B"]
        except Exception as e:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": str(e)},
            )

        arr = np.array(img, dtype=np.int32)

        # Constant planes (an opaque alpha channel) carry no LSB information.
        live = [i for i in range(arr.shape[2]) if np.min(arr[:, :, i]) != np.max(arr[:, :, i])]
        channel_stats = {}
        for c_idx, c_name in enumerate(channels):
            c_pval, c_chi2, c_n_pairs = self._chi2_pvalue(arr[:, :, c_idx].reshape(-1))
            if c_n_pairs > 0:
                channel_stats[c_name] = {
                    "chi2": round(float(c_chi2), 4),
                    "p_value": round(float(c_pval), 4),
                }
        stream = arr[:, :, live].reshape(-1) if live else np.empty(0, dtype=np.int32)

        p_value, chi2_stat, n_pairs = self._chi2_pvalue(stream)
        if n_pairs == 0:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"error": "No valid pixel pairs found"},
            )
        p_head, head_fraction, p_tail = self._head_tail(stream)
        reliable = p_tail is None or p_tail < TAIL_MAX_P

        jpeg_dct_confidence = 0.0
        jpeg_dct_details: dict = {}
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        is_jpeg = ext in (".jpg", ".jpeg") or str(getattr(opened, "format", "")).upper() == "JPEG"
        if is_jpeg:
            jpeg_dct_confidence, jpeg_dct_details = self._jpeg_dct_signal(img)

        # Decoded JPEG pixels carry no LSB information (the codec rewrote them), so a
        # spatial verdict on a JPEG could only be a false alarm: use the DCT signal alone.
        spatial_confidence = 0.0 if is_jpeg or not reliable else float(p_head)
        confidence = max(spatial_confidence, jpeg_dct_confidence)
        detected = (
            spatial_confidence >= CONFIDENCE_THRESHOLD
            or jpeg_dct_confidence >= JPEG_DCT_THRESHOLD
        )

        if jpeg_dct_confidence >= JPEG_DCT_THRESHOLD and jpeg_dct_confidence >= spatial_confidence:
            interpretation = "Potential JPEG DCT sign-pattern embedding detected"
        elif spatial_confidence >= CONFIDENCE_THRESHOLD:
            interpretation = "High probability of LSB steganography"
        elif not is_jpeg and not reliable:
            interpretation = (
                "Pair statistics are equalised across the whole image (noise-like carrier or a "
                "payload filling it): chi-square cannot tell clean from stego here"
            )
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
                "p_head": round(float(p_head), 4),
                "head_fraction": round(float(head_fraction), 6),
                "p_tail": None if p_tail is None else round(float(p_tail), 6),
                "reliable": bool(reliable),
                "spatial_confidence": round(spatial_confidence, 4),
                "jpeg_dct_confidence": round(jpeg_dct_confidence, 4),
                "jpeg_dct": jpeg_dct_details,
                "channels": channel_stats,
                "interpretation": interpretation,
            },
        )

    def _chi2_pvalue(self, values: np.ndarray) -> tuple[float, float, int]:
        """Westfeld-Pfitzmann pair test. Returns ``(p_value, statistic, pairs_used)``."""
        clipped = np.clip(values, 0, 255).astype(np.int64)
        pairs = np.bincount(clipped, minlength=256).reshape(-1, 2)
        pairs = pairs[pairs.sum(axis=1) >= MIN_PAIR_TOTAL]
        n_pairs = int(len(pairs))
        if n_pairs == 0:
            return 0.0, 0.0, 0

        lo = pairs[:, 0].astype(np.float64)
        hi = pairs[:, 1].astype(np.float64)
        # per pair: ((a-e)^2 + (b-e)^2) / e with e = (a+b)/2  ==  (a-b)^2 / (a+b), one degree of freedom
        chi2_stat = float(np.sum((lo - hi) ** 2 / (lo + hi)))
        p_value = float(chi2_dist.sf(chi2_stat, df=n_pairs))
        return p_value, chi2_stat, n_pairs

    def _head_tail(self, stream: np.ndarray) -> tuple[float, float, float | None]:
        """Best prefix-window p-value, the fraction it covers, and the tail p-value (None if too short)."""
        total = int(stream.size)
        best_p, best_fraction = 0.0, 1.0
        for k in range(MAX_HALVINGS + 1):
            n = total >> k
            if n < MIN_WINDOW and k > 0:
                break
            p, _, used = self._chi2_pvalue(stream[:n])
            if used and p >= best_p:
                best_p, best_fraction = p, n / total
        tail_n = int(total * TAIL_FRACTION)
        if tail_n < MIN_WINDOW:
            return best_p, best_fraction, None
        p_tail, _, used = self._chi2_pvalue(stream[-tail_n:])
        return best_p, best_fraction, (p_tail if used else None)

    def _jpeg_dct_signal(self, img: Image.Image) -> tuple[float, dict]:
        rgb = np.array(img.convert("RGB"), dtype=np.float64)
        channel = rgb[:, :, 1]
        h, w = channel.shape
        if h < JPEG_BLOCK or w < JPEG_BLOCK:
            return 0.0, {"reason": "image too small for 8x8 DCT blocks"}

        bh, bw = h // JPEG_BLOCK, w // JPEG_BLOCK
        blocks = channel[:bh * JPEG_BLOCK, :bw * JPEG_BLOCK].reshape(bh, JPEG_BLOCK, bw, JPEG_BLOCK).swapaxes(1, 2)
        coeff = scipy_dctn(blocks, axes=(2, 3), norm="ortho")[:, :, JPEG_TARGET_ROW, JPEG_TARGET_COL]
        values = coeff.reshape(-1).astype(np.float64)  # row-major block order, as embedded
        n_blocks = int(values.size)
        if n_blocks < 64:
            return 0.0, {"reason": "not enough blocks", "blocks": n_blocks}

        front_n = min(max(512, n_blocks // 20), n_blocks // 2) if n_blocks >= 1024 else max(16, n_blocks // 4)

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
