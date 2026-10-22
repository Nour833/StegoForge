"""
core/base.py — the encoder interface and its error contract.

Every steganography encoder implements :class:`BaseEncoder`.

Error contract (enforced for *every* subclass, see ``__init_subclass__``):

* ``encode`` / ``decode`` / ``capacity`` raise :class:`ValueError` (or a
  subclass such as ``CorruptedCarrierError``) for any bad or hostile input.
* Exceptions that escape from the parsers we rely on — Pillow, wave, zipfile,
  pypdf, PyAV, zlib, struct, truncated reads — are translated to
  ``CorruptedCarrierError`` with a readable message, never leaked raw.
* Genuine programming errors (``TypeError``, ``AttributeError``, ...) are NOT
  swallowed: they propagate so they get noticed and fixed.
"""
from __future__ import annotations

import functools
import re
import struct
import wave
import zipfile
import zlib
from abc import ABC, abstractmethod

from core.errors import CorruptedCarrierError

# Exception types that mean "this carrier is malformed", wherever they come from.
_MALFORMED_INPUT: tuple[type[BaseException], ...] = (
    OSError,            # includes PIL.UnidentifiedImageError, truncated files
    EOFError,
    IndexError,         # short buffers read past the end
    SyntaxError,        # Pillow raises this for broken PNG chunks
    struct.error,
    zlib.error,
    wave.Error,
    zipfile.BadZipFile,
)
# Third-party packages whose own exception hierarchies mean the same thing.
_PARSER_PACKAGES = frozenset({"PIL", "pypdf", "av", "reedsolo"})

_WRAPPED = "__stegoforge_contract__"
_QUOTED_PATH_SUFFIX = re.compile(r":?\s*'[^']*[\\/][^']*'\s*$")
_ERRNO_PREFIX = re.compile(r"^\[Errno \d+\]\s*")


def _is_malformed_input(exc: BaseException) -> bool:
    if isinstance(exc, MemoryError):
        return False
    # Checked before the ValueError exemption: PyAV's errors subclass ValueError
    # but carry FFmpeg's raw message (including our temp-file path).
    if type(exc).__module__.split(".", 1)[0] in _PARSER_PACKAGES:
        return True
    if isinstance(exc, ValueError):
        return False
    if isinstance(exc, OSError) and exc.errno is not None:
        # A real system failure (disk full, permission denied, ...): not the carrier's fault.
        return False
    return isinstance(exc, _MALFORMED_INPUT)


def _describe(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc).strip()
    if name == "UnidentifiedImageError":
        return "not a valid or supported image file"
    if name == "DecompressionBombError":
        return "image dimensions exceed the safety limit"
    if isinstance(exc, EOFError) or "truncated" in text.lower():
        return "file is truncated or corrupted"
    if isinstance(exc, wave.Error):
        return f"invalid WAV data ({text})"
    if isinstance(exc, zipfile.BadZipFile):
        return "invalid ZIP container"
    if isinstance(exc, (IndexError, struct.error)):
        return "file is too short or structurally invalid"
    # Library messages often end in the (temporary) path they were handed; never echo it.
    text = _ERRNO_PREFIX.sub("", _QUOTED_PATH_SUFFIX.sub("", text)).strip()
    return f"{name}: {text[:160]}" if text else name


def _carrier_size_limit() -> int:
    from core.config import get_config

    return int(get_config().max_upload_bytes)


def _enforce_contract(fn):
    """Wrap an encoder method with the size guard and error translation."""
    if getattr(fn, _WRAPPED, False):
        return fn

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if args and isinstance(args[0], (bytes, bytearray, memoryview)) and len(args[0]) > _carrier_size_limit():
            raise ValueError("Carrier file exceeds the configured size limit")
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:
            if _is_malformed_input(exc):
                raise CorruptedCarrierError(
                    f"{getattr(self, 'name', 'encoder')}: corrupted or unsupported carrier — {_describe(exc)}"
                ) from exc
            raise

    setattr(wrapper, _WRAPPED, True)
    return wrapper


class BaseEncoder(ABC):
    """
    Every steganography encoder implements this interface.

    Contract:
    - encode() returns the bytes of the stego carrier (it does not write to disk)
    - decode() returns the extracted payload bytes or raises ValueError
    - capacity() returns an int: max payload bytes this carrier can hold
    - name: str class attribute used in CLI/report output
    - supported_extensions: list[str], e.g. ['.png', '.bmp']
    """

    name: str = "base"
    supported_extensions: list[str] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for method in ("encode", "decode", "capacity"):
            fn = cls.__dict__.get(method)
            if callable(fn):
                setattr(cls, method, _enforce_contract(fn))

    @abstractmethod
    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        """Embed payload_bytes into carrier_bytes. Return stego carrier bytes."""

    @abstractmethod
    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        """Extract and return payload bytes from stego carrier. Raise ValueError if not found."""

    @abstractmethod
    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        """Return maximum payload size in bytes for this carrier."""

    def output_suffix(self, carrier_suffix: str) -> str:
        """File suffix of the stego output given the carrier's suffix.

        Encoders that always re-encode to a fixed format (e.g. LSB on a JPEG
        yields PNG, audio always yields WAV) override this so the saved file's
        name never lies about its contents.
        """
        return carrier_suffix
