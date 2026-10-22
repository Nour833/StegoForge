"""
core/audio/spectrogram.py — spectrogram art.

VISUAL WATERMARK ONLY — this is not a reversible byte channel. ``encode``
renders a short text or an image into audible-spectrum energy so the picture
becomes visible in a spectrogram viewer; ``decode`` returns a PNG rendering of
the carrier's spectrum, NOT the original payload bytes. Use ``audio-lsb`` or
``phase`` when the data must come back out.

Because the payload is only *rendered*, it is not encrypted (a ciphertext would
just render as noise), and an image payload may be far larger than the 120-byte
text limit.
"""
from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.audio._convert import decode_audio_to_wav
from core.audio.mono import float_to_wav_mono, wav_to_float_mono
from core.base import BaseEncoder
from core.bits import validate_payload_not_empty

log = logging.getLogger(__name__)

MAX_TEXT_BYTES = 120
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RENDER_FRAMES = 4096


class SpectrogramEncoder(BaseEncoder):
    name = "spectrogram"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    AMPLITUDE_DB = -40.0
    FRAME_SIZE = 512
    HOP_SIZE = 256
    IMG_W = 256

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".wav"

    def capacity(self, carrier_bytes: bytes = b"", **kwargs) -> int:
        """Largest payload accepted: images up to 8 MiB, plain text up to 120 bytes."""
        return MAX_IMAGE_BYTES

    @staticmethod
    def _as_image(payload: bytes) -> Image.Image | None:
        if payload[:4] != b"\x89PNG" and payload[:2] != b"\xff\xd8":
            return None
        try:
            return Image.open(io.BytesIO(payload)).convert("L")
        except Exception as exc:  # noqa: BLE001 - any parse failure means "treat as text"
            log.debug("spectrogram payload is not a readable image: %s", exc)
            return None

    def _render_secret(self, payload_bytes: bytes) -> np.ndarray:
        height = self.FRAME_SIZE // 2
        image = self._as_image(payload_bytes)
        if image is not None:
            return np.array(image.resize((self.IMG_W, height), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

        canvas = Image.new("L", (self.IMG_W, height), 0)
        font = None
        for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                     "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(path, 20)
                break
            except OSError:
                continue
        ImageDraw.Draw(canvas).text(
            (5, height // 2 - 15),
            payload_bytes.decode("utf-8", errors="replace")[:30],
            fill=255,
            font=font or ImageFont.load_default(),
        )
        return np.array(canvas, dtype=np.float32) / 255.0

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        if self._as_image(payload_bytes) is None and len(payload_bytes) > MAX_TEXT_BYTES:
            raise ValueError(
                f"Payload too large for a spectrogram text watermark: {len(payload_bytes)} bytes "
                f"(limit {MAX_TEXT_BYTES}; images are accepted up to {MAX_IMAGE_BYTES // (1024 * 1024)} MiB)"
            )
        if len(payload_bytes) > MAX_IMAGE_BYTES:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes (limit {MAX_IMAGE_BYTES})")

        samples, params = wav_to_float_mono(decode_audio_to_wav(carrier_bytes, ext))
        spec_img = self._render_secret(payload_bytes)              # (freq_bins, time_steps)
        freq_bins, time_steps = spec_img.shape
        amplitude = 10 ** (self.AMPLITUDE_DB / 20.0)

        rng = np.random.default_rng(42)
        phase = rng.uniform(0, 2 * np.pi, size=(time_steps, freq_bins))
        direct = (spec_img.T * amplitude) * np.exp(1j * phase)      # (time_steps, freq_bins)
        spectrum = np.zeros((time_steps, self.FRAME_SIZE), dtype=complex)
        spectrum[:, 1:freq_bins + 1] = direct
        spectrum[:, self.FRAME_SIZE - 1 - np.arange(freq_bins)] = np.conj(direct)  # real-signal mirror
        synth: np.ndarray = np.fft.ifft(spectrum, axis=1).real[:, :self.HOP_SIZE].reshape(-1).astype(np.float32)

        synth = np.pad(synth, (0, len(samples) - len(synth))) if len(synth) < len(samples) else synth[:len(samples)]
        return float_to_wav_mono(np.clip(samples + synth, -1.0, 1.0), params["framerate"])

    def decode(self, stego_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        """Return a PNG of the carrier's spectrum (not the embedded payload).

        Only the first ``MAX_RENDER_FRAMES`` frames (~24 s) are rendered: the
        watermark is written at the start, and this bounds memory on long audio.
        """
        samples, _ = wav_to_float_mono(decode_audio_to_wav(stego_bytes, ext))
        n_frames = min((len(samples) - self.FRAME_SIZE) // self.HOP_SIZE, MAX_RENDER_FRAMES)
        if n_frames <= 0:
            raise ValueError("Audio too short to render a spectrogram")
        freq_bins = self.FRAME_SIZE // 2

        starts = np.arange(n_frames) * self.HOP_SIZE
        frames = samples[starts[:, None] + np.arange(self.FRAME_SIZE)] * np.hanning(self.FRAME_SIZE)
        spec = np.abs(np.fft.rfft(frames, axis=1))[:, :freq_bins].T
        spec_log = np.log1p(spec * 1000.0)
        top = spec_log.max()
        norm = ((spec_log / top) * 255).astype(np.uint8) if top > 0 else spec_log.astype(np.uint8)

        buf = io.BytesIO()
        Image.fromarray(np.flipud(norm)).save(buf, format="PNG")
        return buf.getvalue()
