"""
core/audio/lsb.py — LSB steganography for WAV audio files.

Uses Python stdlib wave + numpy for Python 3.14 compatibility.
Embeds payload in the least-significant bits of PCM audio samples.
- Capacity at 1-bit depth, 44100Hz stereo: ~11KB/second
- Preserves sample rate, bit depth, channels

Wire format: [4-byte big-endian length header][payload bytes]
"""
import io
import hashlib
import struct
import wave
import numpy as np
from scipy.ndimage import uniform_filter1d

from core.audio._convert import decode_audio_to_wav
from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4


def _wav_to_samples(data: bytes) -> tuple[np.ndarray, dict]:
    """Read WAV bytes → (samples_int16_array, wav_params_dict)."""
    buf = io.BytesIO(data)
    with wave.open(buf) as wf:
        params = {
            "nchannels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "framerate": wf.getframerate(),
            "nframes": wf.getnframes(),
        }
        raw = wf.readframes(wf.getnframes())

    if params["sampwidth"] == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.int32)
    elif params["sampwidth"] == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.int32)
    elif params["sampwidth"] == 3:
        # 24-bit: read as bytes groups
        n = len(raw) // 3
        samples = np.zeros(n, dtype=np.int32)
        for i in range(n):
            b = raw[i*3:(i+1)*3]
            val = int.from_bytes(b, 'little', signed=True)
            samples[i] = val
    elif params["sampwidth"] == 4:
        samples = np.frombuffer(raw, dtype=np.int32).copy()
    else:
        raise ValueError(f"Unsupported sample width: {params['sampwidth']}")

    return samples, params


def _samples_to_wav(samples: np.ndarray, params: dict) -> bytes:
    """Write samples back to WAV bytes."""
    sw = params["sampwidth"]
    if sw == 1:
        raw = samples.astype(np.uint8).tobytes()
    elif sw == 2:
        raw = samples.astype(np.int16).tobytes()
    elif sw == 3:
        raw = b""
        for v in samples:
            raw += int(v).to_bytes(3, 'little', signed=True)
    else:
        raw = samples.astype(np.int32).tobytes()

    buf = io.BytesIO()
    with wave.open(buf, 'w') as wf:
        wf.setnchannels(params["nchannels"])
        wf.setsampwidth(sw)
        wf.setframerate(params["framerate"])
        wf.writeframes(raw)
    return buf.getvalue()


class AudioLSBEncoder(BaseEncoder):
    name = "audio-lsb"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    def capacity(self, carrier_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> int:
        wav_bytes = decode_audio_to_wav(carrier_bytes, ext)
        samples, _ = _wav_to_samples(wav_bytes)
        return (len(samples) * depth // 8) - HEADER_SIZE

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(carrier_bytes, ext)
        samples, params = _wav_to_samples(wav_bytes)
        cap = (len(samples) * depth // 8) - HEADER_SIZE

        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, audio capacity: {cap} bytes"
            )

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        key = kwargs.get("key")
        ordered = self._ordered_indices(samples, depth, key)

        mask = ~((1 << depth) - 1)
        bit_idx = 0
        for i in ordered:
            if bit_idx >= len(bits):
                break
            chunk = bits[bit_idx:bit_idx + depth]
            chunk_val = _bits_to_int(chunk)
            samples[i] = (int(samples[i]) & mask) | chunk_val
            bit_idx += depth

        return _samples_to_wav(samples, params)

    def decode(self, stego_bytes: bytes, depth: int = 1, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(stego_bytes, ext)
        samples, _ = _wav_to_samples(wav_bytes)
        key = kwargs.get("key")
        ordered = self._ordered_indices(samples, depth, key)

        header_bit_count = HEADER_SIZE * 8
        bits = []
        for i in ordered:
            if len(bits) >= header_bit_count:
                break
            val = int(samples[i])
            for bit_pos in range(depth - 1, -1, -1):
                bits.append((val >> bit_pos) & 1)

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:header_bit_count]))[0]
        if length == 0 or length > 100_000_000:
            raise ValueError(f"Invalid audio payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        bits = []
        for i in ordered:
            if len(bits) >= total_bits:
                break
            val = int(samples[i])
            for bit_pos in range(depth - 1, -1, -1):
                bits.append((val >> bit_pos) & 1)

        return _bits_to_bytes(bits[header_bit_count:total_bits])

    def _ordered_indices(self, samples: np.ndarray, depth: int, key: str | None) -> np.ndarray:
        # Remove embedded LSB influence so encode/decode derive matching order.
        base = ((samples >> depth) << depth).astype(np.float32)
        amp = np.abs(base)
        d = np.abs(np.diff(base, prepend=base[0]))

        # Psychoacoustic approximation: higher local energy/transients mask changes better.
        energy = uniform_filter1d(amp, size=1536, mode="nearest")
        transients = uniform_filter1d(d, size=768, mode="nearest")
        mask_strength = energy + 0.85 * transients

        # Penalize near-silent zones where LSB edits are easier to detect.
        silence_penalty = np.where(amp < 16.0, 4.0, 1.0)
        cost = silence_penalty / (mask_strength + 1.0)

        quantized = np.round(cost, 6)
        if key:
            seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
            rng = np.random.default_rng(seed)
        else:
            rng = np.random.default_rng(0)
        tie = rng.random(len(samples), dtype=np.float32)
        return np.lexsort((tie, quantized))


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_int(bits: list[int]) -> int:
    val = 0
    for b in bits:
        val = (val << 1) | b
    return val


def _bits_to_bytes(bits: list[int]) -> bytes:
    result = []
    for i in range(0, len(bits) - 7, 8):
        val = 0
        for b in bits[i:i + 8]:
            val = (val << 1) | b
        result.append(val)
    return bytes(result)
