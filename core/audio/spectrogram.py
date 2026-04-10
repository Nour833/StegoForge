"""
core/audio/spectrogram.py — Spectrogram art steganography.

Uses Python stdlib wave + numpy for Python 3.14 compatibility.
Embeds a visible image or text into the audio spectrogram.
"""
import io
import struct
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.audio._convert import decode_audio_to_wav
from core.base import BaseEncoder


def _wav_to_float_mono(data: bytes) -> tuple[np.ndarray, dict]:
    buf = io.BytesIO(data)
    with wave.open(buf) as wf:
        params = {
            "nchannels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "framerate": wf.getframerate(),
            "nframes": wf.getnframes(),
        }
        raw = wf.readframes(wf.getnframes())

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if params["nchannels"] == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    samples /= 32768.0
    return samples, params


def _float_to_wav(samples: np.ndarray, framerate: int) -> bytes:
    out_int16 = np.clip(samples * 32768, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(out_int16.tobytes())
    return buf.getvalue()


class SpectrogramEncoder(BaseEncoder):
    name = "spectrogram"
    supported_extensions = [".wav", ".flac", ".mp3", ".ogg"]

    AMPLITUDE_DB = -40.0
    FRAME_SIZE = 512
    HOP_SIZE = 256

    def _render_secret(self, payload_bytes: bytes) -> np.ndarray:
        IMG_H = self.FRAME_SIZE // 2
        IMG_W = 256

        is_image = (
            payload_bytes[:4] == b'\x89PNG' or
            payload_bytes[:2] == b'\xff\xd8'
        )

        if is_image:
            try:
                img = Image.open(io.BytesIO(payload_bytes)).convert("L")
                img = img.resize((IMG_W, IMG_H), Image.LANCZOS)
                return np.array(img, dtype=np.float32) / 255.0
            except Exception:
                pass

        text = payload_bytes.decode("utf-8", errors="replace")
        img = Image.new("L", (IMG_W, IMG_H), 0)
        draw = ImageDraw.Draw(img)
        try:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            ]
            font = None
            for fp in font_paths:
                try:
                    font = ImageFont.truetype(fp, 20)
                    break
                except OSError:
                    continue
            if font is None:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        draw.text((5, IMG_H // 2 - 15), text[:30], fill=255, font=font)
        return np.array(img, dtype=np.float32) / 255.0

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        return 32768

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(carrier_bytes, ext)
        samples, params = _wav_to_float_mono(wav_bytes)
        framerate = params["framerate"]

        spec_img = self._render_secret(payload_bytes)
        freq_bins, time_steps = spec_img.shape
        amplitude = 10 ** (self.AMPLITUDE_DB / 20.0)

        synth_samples = []
        rng = np.random.default_rng(42)

        for t in range(time_steps):
            freqs = np.zeros(self.FRAME_SIZE, dtype=complex)
            for f in range(freq_bins):
                mag = spec_img[f, t] * amplitude
                phase = rng.uniform(0, 2 * np.pi)
                freqs[f + 1] = mag * np.exp(1j * phase)
                mir = self.FRAME_SIZE - f - 1
                if mir > 0:
                    freqs[mir] = mag * np.exp(-1j * phase)
            frame = np.fft.ifft(freqs).real
            synth_samples.extend(frame[:self.HOP_SIZE].tolist())

        synth = np.array(synth_samples, dtype=np.float32)

        if len(synth) < len(samples):
            synth = np.pad(synth, (0, len(samples) - len(synth)))
        else:
            synth = synth[:len(samples)]

        mixed = np.clip(samples + synth, -1.0, 1.0)
        return _float_to_wav(mixed, framerate)

    def decode(self, stego_bytes: bytes, ext: str = ".wav", **kwargs) -> bytes:
        wav_bytes = decode_audio_to_wav(stego_bytes, ext)
        samples, params = _wav_to_float_mono(wav_bytes)
        n_frames = (len(samples) - self.FRAME_SIZE) // self.HOP_SIZE
        freq_bins = self.FRAME_SIZE // 2
        spec = np.zeros((freq_bins, n_frames))

        for i in range(n_frames):
            start = i * self.HOP_SIZE
            frame = samples[start:start + self.FRAME_SIZE]
            if len(frame) < self.FRAME_SIZE:
                break
            windowed = frame * np.hanning(self.FRAME_SIZE)
            fft_result = np.abs(np.fft.rfft(windowed))[:freq_bins]
            spec[:, i] = fft_result

        spec_log = np.log1p(spec * 1000.0)
        if spec_log.max() > 0:
            spec_norm = ((spec_log / spec_log.max()) * 255).astype(np.uint8)
        else:
            spec_norm = spec_log.astype(np.uint8)

        spec_flipped = np.flipud(spec_norm)
        img = Image.fromarray(spec_flipped, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
