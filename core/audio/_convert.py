"""
core/audio/_convert.py — Audio format conversion utilities.

Converts MP3/FLAC/OGG → WAV in-memory using ffmpeg subprocess.
Falls back gracefully if ffmpeg is not installed.
"""
import io
import subprocess
import shutil
import wave
from pathlib import Path


def _ffmpeg_cmd() -> str | None:
    try:
        from core import sysmgr
        sys_ffmpeg = sysmgr.get_ffmpeg_path()
        if sys_ffmpeg.exists():
            return str(sys_ffmpeg)
    except ImportError:
        pass

    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def has_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    return _ffmpeg_cmd() is not None


def decode_audio_to_wav(audio_bytes: bytes, ext: str) -> bytes:
    """
    Convert any audio format to PCM WAV bytes using ffmpeg.
    Returns WAV bytes. Raises ValueError if conversion fails.
    ext: file extension including dot, e.g. '.mp3', '.flac', '.ogg'
    """
    ext = ext.lower()
    if ext == ".wav" or audio_bytes.startswith(b"RIFF"):
        return audio_bytes  # already WAV, no conversion needed

    if not has_ffmpeg():
        raise ValueError(
            f"ffmpeg is required to process {ext} files but was not found. "
            "Install ffmpeg: sudo apt install ffmpeg"
        )

    cmd = _ffmpeg_cmd()
    if not cmd:
        raise ValueError(
            f"ffmpeg is required to process {ext} files but was not found. "
            "Install ffmpeg: sudo apt install ffmpeg (or pip install imageio-ffmpeg)"
        )

    try:
        result = subprocess.run(
            [
                cmd,
                "-y",                    # overwrite
                "-f", ext.lstrip("."),   # input format
                "-i", "pipe:0",          # read from stdin
                "-f", "wav",             # output format WAV
                "-acodec", "pcm_s16le",  # 16-bit signed little-endian PCM
                "-ar", "44100",          # 44.1kHz sample rate
                "pipe:1",                # write to stdout
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ValueError(
                f"ffmpeg failed to convert {ext}: {result.stderr.decode('utf-8', errors='replace')[-300:]}"
            )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise ValueError(f"ffmpeg timed out converting {ext}")
    except FileNotFoundError:
        raise ValueError("ffmpeg not found — install with: sudo apt install ffmpeg or pip install imageio-ffmpeg")


def encode_wav_to_format(wav_bytes: bytes, ext: str) -> bytes:
    """
    Convert WAV bytes to target format using ffmpeg.
    Only needed for MP3 output (encoding back to MP3 is not supported
    since MP3 encoding would destroy the embedded data).
    For StegoForge: stego output is always WAV regardless of input format.
    """
    return wav_bytes  # stego output is always WAV
