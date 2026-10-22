"""
core/audio/_convert.py — audio format conversion utilities.

Converts MP3 / FLAC / OGG to PCM WAV in memory with an ``ffmpeg`` subprocess.
ffmpeg is located, in order, from ``STEGOFORGE_FFMPEG``, the ``PATH``, and the
binary bundled with the ``imageio-ffmpeg`` dependency. StegoForge never
downloads executables.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

_BASE_TIMEOUT_S = 30
_TIMEOUT_PER_MB_S = 2


def ffmpeg_path() -> str | None:
    """Return the path of a usable ffmpeg binary, or None."""
    override = os.getenv("STEGOFORGE_FFMPEG", "").strip()
    if override and os.access(override, os.X_OK):
        return override
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001 - optional dependency may be absent or broken
        log.debug("imageio-ffmpeg unavailable: %s", exc)
        return None


# Backwards-compatible name used by other modules.
_ffmpeg_cmd = ffmpeg_path


def has_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    return ffmpeg_path() is not None


def decode_audio_to_wav(audio_bytes: bytes, ext: str) -> bytes:
    """Convert any supported audio format to PCM WAV bytes.

    Raises:
        ValueError: if ffmpeg is missing or the conversion fails.
    """
    ext = ext.lower()
    if ext == ".wav" or audio_bytes.startswith(b"RIFF"):
        return audio_bytes  # already WAV, no conversion needed

    cmd = ffmpeg_path()
    if not cmd:
        raise ValueError(
            f"ffmpeg is required to process {ext} files but was not found. "
            "Install ffmpeg (e.g. `sudo apt install ffmpeg`) or `pip install imageio-ffmpeg`."
        )

    timeout = _BASE_TIMEOUT_S + _TIMEOUT_PER_MB_S * (len(audio_bytes) // (1024 * 1024))
    try:
        result = subprocess.run(
            [
                cmd, "-hide_banner", "-loglevel", "error", "-y",
                "-f", ext.lstrip("."),   # input format
                "-i", "pipe:0",          # read from stdin
                "-f", "wav",             # output format
                "-acodec", "pcm_s16le",  # 16-bit signed little-endian PCM
                "-ar", "44100",          # 44.1 kHz
                "pipe:1",                # write to stdout
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(f"ffmpeg timed out converting {ext}") from None
    except FileNotFoundError:
        raise ValueError("ffmpeg not found — install ffmpeg or `pip install imageio-ffmpeg`") from None
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-300:]
        raise ValueError(f"ffmpeg failed to convert {ext}: {detail}")
    return result.stdout
