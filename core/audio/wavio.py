"""core/audio/wavio.py — PCM WAV reading/writing shared by every audio encoder.

Samples are returned as an interleaved ``int32`` array for any PCM width
(8/16/24/32-bit). 8-bit WAV is unsigned on disk and is kept unsigned here
(0..255); wider formats are signed. Everything is vectorised: the old 24-bit
reader looped over samples in Python.
"""
from __future__ import annotations

import io
import wave

import numpy as np


def read_pcm(data: bytes) -> tuple[np.ndarray, dict]:
    """Read WAV bytes -> (interleaved int32 samples, params dict)."""
    with wave.open(io.BytesIO(data)) as wf:
        params = {
            "nchannels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "framerate": wf.getframerate(),
            "nframes": wf.getnframes(),
        }
        raw = wf.readframes(wf.getnframes())

    width = params["sampwidth"]
    raw = raw[: len(raw) // width * width]  # a truncated file may end mid-sample
    if width == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.int32)
    elif width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.int32)
    elif width == 3:
        u8 = np.frombuffer(raw[:len(raw) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        value = u8[:, 0] | (u8[:, 1] << 8) | (u8[:, 2] << 16)
        samples = (value ^ 0x800000) - 0x800000  # sign-extend 24 -> 32 bit
    elif width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.int32)
    else:
        raise ValueError(f"Unsupported sample width: {width}")
    return samples, params


def write_pcm(samples: np.ndarray, params: dict) -> bytes:
    """Write interleaved integer samples back to WAV bytes with ``params``."""
    width = params["sampwidth"]
    if width == 1:
        raw = samples.astype(np.uint8).tobytes()
    elif width == 2:
        raw = samples.astype("<i2").tobytes()
    elif width == 3:
        packed = (samples.astype(np.int32) & 0xFFFFFF).astype("<u4").view(np.uint8).reshape(-1, 4)[:, :3]
        raw = packed.tobytes()
    elif width == 4:
        raw = samples.astype("<i4").tobytes()
    else:
        raise ValueError(f"Unsupported sample width: {width}")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(params["nchannels"])
        wf.setsampwidth(width)
        wf.setframerate(params["framerate"])
        wf.writeframes(raw)
    return buf.getvalue()
