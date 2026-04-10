"""
core/audio/phase.py — Phase coding steganography for audio.

Uses Python stdlib wave + numpy for Python 3.14 compatibility.
Encodes payload by adding small phase shifts (±π/2) to specific
frequency bins in fixed-size audio segments.

Wire format: [4-byte big-endian length][payload bytes]
"""
import io
import struct
import wave
import numpy as np

from core.audio._convert import decode_audio_to_wav
from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4
SEGMENT_SIZE = 1024
PHASE_SHIFT = np.pi / 2


def _wav_to_float_mono(data: bytes) -> tuple[np.ndarray, dict]:
    """Read WAV → mono float32 samples in [-1, 1], plus params."""
    buf = io.BytesIO(data)
    with wave.open(buf) as wf:
        params = {
            "nchannels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "framerate": wf.getframerate(),
            "nframes": wf.getnframes(),
        }
        raw = wf.readframes(wf.getnframes())

    if params["sampwidth"] == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        # Convert stereo to mono if needed
        if params["nchannels"] == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)
        samples /= 32768.0
    elif params["sampwidth"] == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        if params["nchannels"] == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)
        samples = (samples - 128.0) / 128.0
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if params["nchannels"] == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)

    return samples, params


def _float_to_wav(samples: np.ndarray, params: dict) -> bytes:
    """Write float32 mono samples back to WAV."""
    out_int16 = np.clip(samples * 32768, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(params["framerate"])
        wf.writeframes(out_int16.tobytes())
    return buf.getvalue()


class PhaseEncoder(BaseEncoder):
    name = "phase"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    def capacity(self, carrier_bytes: bytes, ext: str = ".wav", **kwargs) -> int:
        wav_bytes = decode_audio_to_wav(carrier_bytes, ext)
        samples, _ = _wav_to_float_mono(wav_bytes)
        n_segments = len(samples) // SEGMENT_SIZE
        return (n_segments // 8) - HEADER_SIZE

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(carrier_bytes, ext)
        samples, params = _wav_to_float_mono(wav_bytes)
        n_segments = len(samples) // SEGMENT_SIZE

        cap = (n_segments // 8) - HEADER_SIZE
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, phase capacity: {cap} bytes"
            )

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        result_samples = samples.copy()
        for seg_idx, bit in enumerate(bits):
            if seg_idx >= n_segments:
                break
            start = seg_idx * SEGMENT_SIZE
            segment = samples[start:start + SEGMENT_SIZE]

            spectrum = np.fft.fft(segment)
            bin_idx = SEGMENT_SIZE // 4

            magnitude = np.abs(spectrum[bin_idx])
            target_phase = PHASE_SHIFT if bit == 1 else -PHASE_SHIFT

            spectrum[bin_idx] = magnitude * np.exp(1j * target_phase)
            spectrum[SEGMENT_SIZE - bin_idx] = magnitude * np.exp(-1j * target_phase)

            modified = np.fft.ifft(spectrum).real
            result_samples[start:start + SEGMENT_SIZE] = modified

        return _float_to_wav(result_samples, params)

    def decode(self, stego_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(stego_bytes, ext)
        samples, _ = _wav_to_float_mono(wav_bytes)
        n_segments = len(samples) // SEGMENT_SIZE

        bits = []
        for seg_idx in range(n_segments):
            start = seg_idx * SEGMENT_SIZE
            segment = samples[start:start + SEGMENT_SIZE]
            spectrum = np.fft.fft(segment)
            bin_idx = SEGMENT_SIZE // 4
            phase = np.angle(spectrum[bin_idx])
            bits.append(1 if phase > 0 else 0)

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("Not enough segments to read phase header")

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:HEADER_SIZE * 8]))[0]
        if length == 0 or length > 100_000_000:
            raise ValueError(f"Invalid phase payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        if len(bits) < total_bits:
            raise ValueError("Not enough audio segments to decode phase payload")

        return _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    result = []
    for i in range(0, len(bits) - 7, 8):
        val = 0
        for b in bits[i:i + 8]:
            val = (val << 1) | b
        result.append(val)
    return bytes(result)
