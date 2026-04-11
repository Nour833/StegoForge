"""
detect/audio_anomaly.py - Lightweight audio stego anomaly detector.
"""
from __future__ import annotations

import io
import wave

import numpy as np

from core.audio._convert import decode_audio_to_wav
from detect.base import BaseDetector, DetectionResult


class AudioAnomalyDetector(BaseDetector):
    name = "audio-anomaly"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        ext = ".wav"
        if "." in filename:
            ext = filename[filename.rfind("."):].lower()

        try:
            wav_bytes = decode_audio_to_wav(file_bytes, ext)
            samples = _read_wav_samples(wav_bytes)
            if samples.size < 2048:
                return DetectionResult(
                    method=self.name,
                    detected=False,
                    confidence=0.0,
                    details={"skipped": True, "interpretation": "Audio too short for anomaly scoring"},
                )

            lsb = (samples & 1).astype(np.float32)
            p1 = float(np.mean(lsb))
            lsb_bias = abs(p1 - 0.5)

            d = np.diff(samples.astype(np.float32))
            deriv_var = float(np.var(d))
            if not np.isfinite(deriv_var):
                deriv_var = 0.0

            abs_d = np.abs(d)
            smooth_ratio = float(np.mean(abs_d < 2.0))

            # Suspicion rises when LSB distribution is too uniform while derivative
            # statistics indicate otherwise naturally structured audio.
            lsb_uniformity = float(np.clip(1.0 - (lsb_bias * 4.0), 0.0, 1.0))
            deriv_signal = float(np.clip((smooth_ratio - 0.08) * 1.8, 0.0, 1.0))
            conf = float(np.clip(0.65 * lsb_uniformity + 0.35 * deriv_signal, 0.0, 1.0))

            detected = conf >= 0.35
            return DetectionResult(
                method=self.name,
                detected=detected,
                confidence=round(conf, 4),
                details={
                    "lsb_one_ratio": round(p1, 6),
                    "lsb_bias": round(lsb_bias, 6),
                    "smooth_derivative_ratio": round(smooth_ratio, 6),
                    "derivative_variance": round(deriv_var, 6),
                    "interpretation": (
                        "Sample-level bit-plane statistics look suspicious for audio stego"
                        if detected else "No strong sample-level stego anomaly detected"
                    ),
                },
            )
        except Exception as exc:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"skipped": True, "interpretation": f"Audio anomaly scan failed: {exc}"},
            )


def _read_wav_samples(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sample_width == 1:
        arr = np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128
    elif sample_width == 2:
        arr = np.frombuffer(raw, dtype=np.int16)
    elif sample_width == 4:
        arr = (np.frombuffer(raw, dtype=np.int32) >> 16).astype(np.int16)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if n_channels > 1:
        arr = arr.reshape(-1, n_channels)[:, 0]
    return arr
