"""
detect/blind.py — Brute-force blind extractor (CTF killer feature).

Tries every common combination of encoding parameters on image files:
  - channel: R, G, B, A
  - bit depth: 1, 2, 3, 4
  - row order: normal, reversed
  - channel order: all 6 permutations of RGB

For each combination:
  1. Extract first 32 bits → check if it's a plausible payload length
  2. If plausible: extract that many bytes and score the result
  3. Scoring: SFRG magic header, printable ASCII ratio, known file magic bytes

Returns all candidates sorted by score, with parameters used.
Target: completes in under 2 seconds on a typical image.
"""
import io
import struct
import itertools
import time
from typing import Any

import numpy as np
from PIL import Image

from detect.base import BaseDetector, DetectionResult

# Known file magic bytes for scoring
KNOWN_MAGIC = {
    b"\x89PNG": "PNG image",
    b"\xff\xd8\xff": "JPEG image",
    b"PK\x03\x04": "ZIP/Office document",
    b"%PDF": "PDF document",
    b"RIFF": "WAV audio",
    b"fLaC": "FLAC audio",
    b"ID3": "MP3 audio",
    b"GIF8": "GIF image",
    b"BM": "BMP image",
    b"SFRG": "StegoForge encrypted payload",
}

CHANNELS = {
    "R": 0,
    "G": 1,
    "B": 2,
    "A": 3,
}

HEADER_SIZE = 4


class BlindExtractor(BaseDetector):
    name = "blind"
    supported_extensions = [
        ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff",
        ".wav", ".flac", ".mp3", ".ogg"
    ]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        start_time = time.time()
        candidates = []

        import os
        ext = os.path.splitext(filename)[1].lower() if filename else ""

        if ext in (".wav", ".flac", ".mp3", ".ogg"):
            # AUDIO BLIND EXTRACTION
            from stegoforge import get_encoder
            for method_name in ["audio-lsb", "phase"]:
                try:
                    encoder = get_encoder(method_name)
                    for depth in [1, 2, 3, 4]:
                        try:
                            raw_payload = encoder.decode(file_bytes, ext=ext, depth=depth)
                            # Let's score it.
                            score = 0.0
                            payload_type = "Unknown bin"
                            if raw_payload.startswith(b"SFRG"):
                                score = 1.0
                                payload_type = "StegoForge encrypted payload"
                            else:
                                for magic, desc in KNOWN_MAGIC.items():
                                    if raw_payload.startswith(magic):
                                        score = 0.8
                                        payload_type = desc
                                        break
                                if score == 0.0:
                                    try:
                                        text = raw_payload.decode("utf-8")
                                        if sum(1 for c in text if c.isprintable()) / max(1, len(text)) > 0.9:
                                            score = 0.6
                                            payload_type = "Text data"
                                    except UnicodeDecodeError:
                                        score = 0.1
                                        
                            if score > 0.0:
                                candidates.append({
                                    "channel": method_name,
                                    "depth": depth,
                                    "row_order": "normal",
                                    "channel_perm": None,
                                    "payload_bytes": len(raw_payload),
                                    "score": score,
                                    "payload_preview": _describe_payload(raw_payload),
                                    "payload": raw_payload,
                                })
                        except ValueError:
                            continue
                except Exception:
                    pass

        else:
            # IMAGE BLIND EXTRACTION
            try:
                img = Image.open(io.BytesIO(file_bytes))
                if img.mode not in ("RGB", "RGBA"):
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")
                arr = np.array(img, dtype=np.uint8)
            except Exception as e:
                return DetectionResult(
                    method=self.name,
                    detected=False,
                    confidence=0.0,
                    details={
                        "skipped": True,
                        "interpretation": "Format not supported or invalid image",
                        "error": str(e),
                    },
                )
                
            # NATIVE IMAGE BLIND EXTRACTION (Advanced Methods)
            from stegoforge import get_encoder
            for method_name in ["dct", "adaptive-lsb", "palette", "alpha"]:
                try:
                    encoder = get_encoder(method_name)
                    raw_payload = encoder.decode(file_bytes)
                    
                    score = 0.0
                    payload_type = "Unknown bin"
                    if raw_payload.startswith(b"SFRG"):
                        score = 1.0
                        payload_type = "StegoForge encrypted payload"
                    else:
                        for magic, desc in KNOWN_MAGIC.items():
                            if raw_payload.startswith(magic):
                                score = 0.8
                                payload_type = desc
                                break
                        if score == 0.0:
                            try:
                                text = raw_payload.decode("utf-8")
                                if sum(1 for c in text if c.isprintable()) / max(1, len(text)) > 0.9:
                                    score = 0.6
                                    payload_type = "Text data"
                            except UnicodeDecodeError:
                                score = 0.1
                                
                    if score > 0.0:
                        candidates.append({
                            "channel": method_name,
                            "depth": 1,
                            "row_order": "normal",
                            "channel_perm": None,
                            "payload_bytes": len(raw_payload),
                            "score": score,
                            "payload_preview": _describe_payload(raw_payload),
                            "payload": raw_payload,
                        })
                except Exception:
                    pass

            has_alpha = (img.mode == "RGBA")
            channel_names = ["R", "G", "B"] + (["A"] if has_alpha else [])
            depths = [1, 2, 3, 4]
            orders = ["normal", "reversed"]

            # All RGB channel order permutations
            channel_permutations = list(itertools.permutations([0, 1, 2]))

            # Include an "ALL" channel (interleaved channels)
            channel_names_to_try = channel_names + ["ALL"]

            for channel_name in channel_names_to_try:
                ch_idx = CHANNELS[channel_name] if channel_name in CHANNELS else None
                if ch_idx is not None and (ch_idx >= arr.shape[2] if len(arr.shape) == 3 else ch_idx > 0):
                    continue

                for depth in depths:
                    for row_order in orders:
                        # Try with each channel order permutation for R/G/B
                        perms_to_try = channel_permutations if channel_name in ("R", "G", "B") else [None]

                        for perm in perms_to_try:
                            try:
                                result = self._try_extract(arr, ch_idx, depth, row_order, perm)
                                if result is not None:
                                    payload, score = result
                                    candidates.append({
                                        "channel": channel_name,
                                        "depth": depth,
                                        "row_order": row_order,
                                        "channel_perm": list(perm) if perm else None,
                                        "payload_bytes": len(payload),
                                        "score": score,
                                        "payload_preview": _describe_payload(payload),
                                        "payload": payload,
                                    })
                            except Exception:
                                continue
        elapsed = time.time() - start_time
        candidates.sort(key=lambda c: c["score"], reverse=True)

        detected = len(candidates) > 0
        best_confidence = candidates[0]["score"] if candidates else 0.0

        # Build clean output (without raw payload bytes)
        clean_candidates = []
        for c in candidates:
            clean_candidates.append({
                "channel": c["channel"],
                "depth": c["depth"],
                "row_order": c["row_order"],
                "channel_perm": c["channel_perm"],
                "payload_bytes": c["payload_bytes"],
                "score": round(c["score"], 4),
                "payload_type": c["payload_preview"],
            })

        best_payload = candidates[0]["payload"] if candidates else None

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(min(1.0, best_confidence), 4),
            details={
                "candidates_found": len(candidates),
                "elapsed_seconds": round(elapsed, 3),
                "candidates": clean_candidates[:10],  # top 10
            },
            extracted_payload=best_payload,
        )

    def _try_extract(
        self,
        arr: np.ndarray,
        channel_idx: int | None,
        depth: int,
        row_order: str,
        channel_perm: tuple | None,
    ) -> tuple[bytes, float] | None:
        """
        Attempt extraction with given parameters.
        Returns (payload, confidence_score) or None if implausible.
        """
        if channel_idx is None:
            # Interleaved across all channels
            if channel_perm and len(arr.shape) == 3 and arr.shape[2] >= 3:
                channels = [arr[:, :, i] for i in range(arr.shape[2])]
                reordered = [channels[channel_perm[0]], channels[channel_perm[1]], channels[channel_perm[2]]]
                if arr.shape[2] > 3:
                    reordered.extend(channels[3:])  # keep alpha if present
                flat = np.dstack(reordered).flatten()
            else:
                flat = arr.flatten()
        else:
            if len(arr.shape) == 3:
                if channel_perm and channel_idx < 3:
                    reordered = arr[:, :, list(channel_perm)]
                    channel_data = reordered[:, :, channel_idx]
                else:
                    channel_data = arr[:, :, channel_idx]
            else:
                channel_data = arr

            flat = channel_data.flatten()
        if row_order == "reversed":
            flat = flat[::-1]

        # Extract bits
        mask = (1 << depth) - 1
        vals = flat & mask
        
        # Vectorized bit extraction
        shifts = np.arange(depth - 1, -1, -1, dtype=np.uint8)
        all_bits = (vals[:, None] >> shifts) & 1
        all_bits = all_bits.flatten()

        if len(all_bits) < HEADER_SIZE * 8:
            return None

        # Decode header
        header_bits = all_bits[:HEADER_SIZE * 8]
        length_val = int(np.packbits(header_bits).view('>u4')[0])

        # Plausibility check
        max_possible = (len(all_bits) - HEADER_SIZE * 8) // 8
        if length_val <= 0 or length_val > max_possible or length_val > 50_000_000:
            return None

        # Extract payload
        total_bits = (HEADER_SIZE + length_val) * 8
        if len(all_bits) < total_bits:
            return None

        payload_bits = all_bits[HEADER_SIZE * 8:total_bits]
        payload = np.packbits(payload_bits).tobytes()

        # Score the payload
        score = _score_payload(payload)
        if score < 0.05:
            return None

        return payload, score


def _score_payload(data: bytes) -> float:
    """Score extracted data for likelihood of being a real payload (0.0–1.0)."""
    if not data:
        return 0.0

    score = 0.0

    # Check for SFRG magic (StegoForge encrypted) — highest score
    if data[:4] == b"SFRG":
        score += 0.9
        return min(1.0, score)

    # Check known file magic bytes
    for magic, desc in KNOWN_MAGIC.items():
        if data[:len(magic)] == magic:
            score += 0.8
            return min(1.0, score)

    # Check printable ASCII ratio
    printable = sum(1 for b in data[:200] if 32 <= b <= 126 or b in (9, 10, 13))
    ascii_ratio = printable / min(len(data), 200)
    if ascii_ratio > 0.8:
        score += ascii_ratio * 0.6
    elif ascii_ratio > 0.5:
        score += ascii_ratio * 0.3

    # Check for common byte patterns (UTF-8, etc.)
    try:
        data.decode("utf-8")
        score += 0.1  # valid UTF-8
    except UnicodeDecodeError:
        pass

    # Non-zero byte diversity (random noise has ~uniform distribution)
    if len(data) >= 16:
        unique_bytes = len(set(data[:64]))
        if unique_bytes > 20:
            score += 0.05  # diverse byte values — more likely real data

    return min(1.0, score)


def _describe_payload(data: bytes) -> str:
    """Return a short human-readable description of the payload type."""
    if not data:
        return "empty"
    if data[:4] == b"SFRG":
        return "StegoForge encrypted payload"
    for magic, desc in KNOWN_MAGIC.items():
        if data[:len(magic)] == magic:
            return desc
    printable = sum(1 for b in data[:200] if 32 <= b <= 126)
    if printable / min(len(data), 200) > 0.8:
        try:
            preview = data[:60].decode("utf-8", errors="replace")
            return f"Plaintext: {preview!r}"
        except Exception:
            return "High printable ASCII — likely text"
    return "Binary data"
