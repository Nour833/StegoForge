"""
detect/base.py — Abstract base class and result dataclass for all StegoForge detectors.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectionResult:
    method: str
    detected: bool
    confidence: float          # 0.0 to 1.0
    details: dict              # method-specific extra data
    extracted_payload: bytes | None = None
    findings: list = field(default_factory=list)  # list of Finding dicts for EXIF/blind


class BaseDetector(ABC):
    name: str = "base"
    supported_extensions: list[str] = []

    @abstractmethod
    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        """Analyze file_bytes. Return DetectionResult."""
        ...
