"""
core/audio/lsb.py — LSB steganography for PCM audio.

Embeds the payload in the ``depth`` least significant bits of PCM samples
(8/16/24/32-bit, any channel count). MP3 / FLAC / OGG carriers are decoded to
16-bit WAV first, so the output is always WAV (see ``output_suffix``).

Samples are visited cheapest-first: the cost map is computed from the signal
with its low ``depth`` bits masked off, so encoder and decoder derive the same
order. Loud, transient passages mask the change best; near-silence is
penalised. The key (if any) only seeds the tie-break among equal-cost samples.

Wire format: ``[4-byte big-endian length][payload]``.

Compatibility note: the ordering and tie-break (``numpy.random.default_rng``)
are exactly those of StegoForge <= 1.1.5, so existing carriers stay readable.
"""
from __future__ import annotations

import hashlib

import numpy as np

from core.audio._convert import decode_audio_to_wav
from core.audio.wavio import read_pcm, write_pcm
from core.base import BaseEncoder
from core.bits import (
    bits_to_bytes_np,
    bytes_to_bits_np,
    pack_depth_chunks_np,
    unpack_depth_chunks_np,
    validate_depth,
    validate_payload_not_empty,
)
from core.config import get_config

HEADER_SIZE = 4
MAX_PAYLOAD = 100_000_000
_COST_WINDOW = 1536
_TRANSIENT_WINDOW = 768


class AudioLSBEncoder(BaseEncoder):
    name = "audio-lsb"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".wav"

    def capacity(self, carrier_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> int:
        validate_depth(depth)
        samples, _ = self._samples(carrier_bytes, ext)
        return max(0, (len(samples) * depth // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> bytes:
        validate_depth(depth)
        validate_payload_not_empty(payload_bytes)
        samples, params = self._samples(carrier_bytes, ext)
        cap = max(0, (len(samples) * depth // 8) - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, audio capacity: {cap} bytes")

        bits = bytes_to_bits_np(len(payload_bytes).to_bytes(HEADER_SIZE, "big") + bytes(payload_bytes))
        chunks = pack_depth_chunks_np(bits, depth)
        idx = self._ordered_indices(samples, depth, kwargs.get("key"))[:len(chunks)]
        mask = np.int32(~((1 << depth) - 1))
        samples[idx] = (samples[idx] & mask) | chunks.astype(np.int32)
        return write_pcm(samples, params)

    def decode(self, stego_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> bytes:
        validate_depth(depth)
        samples, _ = self._samples(stego_bytes, ext)
        low = np.int32((1 << depth) - 1)
        hdr_groups = -(-HEADER_SIZE * 8 // depth)
        if len(samples) < hdr_groups:
            raise ValueError("Audio too short to contain a payload header")
        ordered = self._ordered_indices(samples, depth, kwargs.get("key"))

        def read(groups: int) -> np.ndarray:
            return unpack_depth_chunks_np((samples[ordered[:groups]] & low).astype(np.uint8), depth)

        length = int.from_bytes(bits_to_bytes_np(read(hdr_groups)[:HEADER_SIZE * 8]), "big")
        if length == 0 or length > MAX_PAYLOAD:
            raise ValueError(f"Invalid audio payload length: {length}")
        total_bits = (HEADER_SIZE + length) * 8
        groups = -(-total_bits // depth)
        if groups > len(samples):
            raise ValueError("Audio too short for the declared payload length")
        return bits_to_bytes_np(read(groups)[HEADER_SIZE * 8:total_bits])

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _samples(data: bytes, ext: str) -> tuple[np.ndarray, dict]:
        samples, params = read_pcm(decode_audio_to_wav(data, ext))
        # The cost ordering holds ~3 float arrays; cap at ~8x the upload budget in samples.
        if len(samples) > get_config().max_upload_bytes * 8:
            raise ValueError("Audio carrier too large (sample count exceeds memory guard)")
        return samples, params

    @staticmethod
    def _ordered_indices(samples: np.ndarray, depth: int, key: str | None) -> np.ndarray:
        from scipy.ndimage import uniform_filter1d  # lazy: import cost only on use

        # Remove embedded LSB influence so encode/decode derive matching order.
        base = ((samples >> depth) << depth).astype(np.float32)
        amp = np.abs(base)
        d = np.abs(np.diff(base, prepend=base[0]))

        # Psychoacoustic approximation: higher local energy/transients mask changes better.
        energy = uniform_filter1d(amp, size=_COST_WINDOW, mode="nearest")
        transients = uniform_filter1d(d, size=_TRANSIENT_WINDOW, mode="nearest")
        mask_strength = energy + 0.85 * transients

        # Penalise near-silent zones where LSB edits are easier to detect.
        silence_penalty = np.where(amp < 16.0, 4.0, 1.0)
        quantized = np.round(silence_penalty / (mask_strength + 1.0), 6)

        if key:
            seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(seed)
        else:
            rng = np.random.default_rng(0)
        tie = rng.random(len(samples), dtype=np.float32)
        return np.lexsort((tie, quantized))
