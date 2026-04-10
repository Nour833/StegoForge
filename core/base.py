"""
core/base.py — Abstract base classes for all StegoForge encoders.

Every encoder must implement this interface exactly.
"""
from abc import ABC, abstractmethod


class BaseEncoder(ABC):
    """
    Every steganography encoder implements this interface.

    Contract:
    - encode() must return bytes of the stego carrier (not write to disk itself)
    - decode() must return bytes of the extracted payload or raise ValueError
    - capacity() must return int (max bytes that can be embedded in this carrier)
    - name: str class attribute, used in CLI/report output
    - supported_extensions: list[str], e.g. ['.png', '.bmp']
    """
    name: str = "base"
    supported_extensions: list[str] = []

    @abstractmethod
    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        """Embed payload_bytes into carrier_bytes. Return stego carrier bytes."""
        ...

    @abstractmethod
    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        """Extract and return payload bytes from stego carrier. Raise ValueError if not found."""
        ...

    @abstractmethod
    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        """Return maximum payload size in bytes for this carrier."""
        ...
