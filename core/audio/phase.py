"""
core/audio/phase.py — phase-coding steganography for audio.

The (mono-mixed) signal is cut into fixed 1024-sample segments. Each segment
carries one bit in the *phase* of FFT bin 256 (11 kHz at 44.1 kHz): +pi/2 for a
1, -pi/2 for a 0. The conjugate bin is set too, so the segment stays real.

Why a magnitude floor: in a silent segment the bin has magnitude 0, so any
phase written to it vanishes and the bit is lost. The bin is therefore raised
to at least ``MAGNITUDE_FLOOR`` — a tone of about one 16-bit LSB, far above the
int16 rounding noise and inaudible — so the bit survives quantisation even in
digital silence.

Output is always 16-bit mono WAV. Capacity is one bit per 1024 samples, so
this method suits short messages.

Wire format: ``[4-byte big-endian length][payload]``.
"""
from __future__ import annotations

import numpy as np

from core.audio._convert import decode_audio_to_wav
from core.audio.mono import float_to_wav_mono, wav_to_float_mono
from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000
SEGMENT_SIZE = 1024
BIN = SEGMENT_SIZE // 4
MIRROR_BIN = SEGMENT_SIZE - BIN
PHASE_SHIFT = np.pi / 2
# FFT-bin magnitude of ~1 LSB tone (amplitude 2*0.02/1024 ≈ 3.9e-5 of full scale);
# int16 rounding noise in the bin is ~2.8e-4, i.e. a >70x margin.
MAGNITUDE_FLOOR = 0.02
_CHUNK_SEGMENTS = 4096


class PhaseEncoder(BaseEncoder):
    name = "phase"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".wav"

    def capacity(self, carrier_bytes: bytes, ext: str = ".wav", **kwargs) -> int:
        samples, _ = wav_to_float_mono(decode_audio_to_wav(carrier_bytes, ext))
        return max(0, (len(samples) // SEGMENT_SIZE) // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        samples, params = wav_to_float_mono(decode_audio_to_wav(carrier_bytes, ext))
        n_segments = len(samples) // SEGMENT_SIZE
        cap = max(0, n_segments // 8 - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, phase capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        out = samples.copy()
        for first in range(0, len(bits), _CHUNK_SEGMENTS):
            chunk = bits[first:first + _CHUNK_SEGMENTS]
            lo = first * SEGMENT_SIZE
            segs = samples[lo:lo + len(chunk) * SEGMENT_SIZE].reshape(len(chunk), SEGMENT_SIZE).astype(np.float64)
            spectrum = np.fft.fft(segs, axis=1)
            magnitude = np.maximum(np.abs(spectrum[:, BIN]), MAGNITUDE_FLOOR)
            bin_value = magnitude * np.exp(1j * np.where(chunk == 1, PHASE_SHIFT, -PHASE_SHIFT))
            spectrum[:, BIN] = bin_value
            spectrum[:, MIRROR_BIN] = np.conj(bin_value)
            out[lo:lo + len(chunk) * SEGMENT_SIZE] = np.fft.ifft(spectrum, axis=1).real.reshape(-1)

        stego = float_to_wav_mono(out, params["framerate"])
        # Never report success on a payload that quantisation destroyed.
        if self.decode(stego) != bytes(payload_bytes):
            raise ValueError("Phase embedding did not survive 16-bit quantisation for this carrier")
        return stego

    def decode(self, stego_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        samples, _ = wav_to_float_mono(decode_audio_to_wav(stego_bytes, ext))
        n_segments = len(samples) // SEGMENT_SIZE
        if n_segments < HEADER_SIZE * 8:
            raise ValueError("Not enough segments to read phase header")

        def read(count: int) -> np.ndarray:
            parts = []
            for first in range(0, count, _CHUNK_SEGMENTS):
                n = min(_CHUNK_SEGMENTS, count - first)
                lo = first * SEGMENT_SIZE
                segs = samples[lo:lo + n * SEGMENT_SIZE].reshape(n, SEGMENT_SIZE).astype(np.float64)
                parts.append((np.angle(np.fft.fft(segs, axis=1)[:, BIN]) > 0).astype(np.uint8))
            return np.concatenate(parts) if parts else np.empty(0, dtype=np.uint8)

        length = int.from_bytes(bits_to_bytes_np(read(HEADER_SIZE * 8)), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid phase payload length: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        if n_segments < total_bits:
            raise ValueError("Not enough audio segments to decode phase payload")
        return bits_to_bytes_np(read(total_bits)[HEADER_SIZE * 8:])
