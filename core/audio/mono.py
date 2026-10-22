"""core/audio/mono.py — shared WAV -> mono float converter (single source).

Supports 8/16/24/32-bit PCM and any channel count (channels are averaged).
"""
from __future__ import annotations

import io
import wave

import numpy as np

from core.audio.wavio import read_pcm

_FULL_SCALE = {1: 128.0, 2: 32768.0, 3: 8388608.0, 4: 2147483648.0}


def wav_to_float_mono(data: bytes) -> tuple[np.ndarray, dict]:
    """Read WAV bytes -> (mono float32 samples in [-1, 1], params dict)."""
    samples, params = read_pcm(data)
    width = params["sampwidth"]
    values = samples.astype(np.float32)
    if width == 1:
        values -= 128.0  # unsigned 8-bit
    values /= np.float32(_FULL_SCALE[width])
    channels = params["nchannels"]
    if channels > 1:
        values = values[: len(values) // channels * channels].reshape(-1, channels).mean(axis=1)
    return values, params


def float_to_wav_mono(samples: np.ndarray, framerate: int) -> bytes:
    """Write mono float32 samples back to 16-bit WAV bytes."""
    out_int16 = np.clip(samples * 32768, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(out_int16.tobytes())
    return buf.getvalue()
