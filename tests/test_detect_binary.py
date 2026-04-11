"""tests/test_detect_binary.py - Tests for binary anomaly detector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect.binary import BinaryDetector
from core.binary.elf import ELFEncoder
from core.binary.pe import PEEncoder
from tests.test_binary_elf import _fake_elf
from tests.test_binary_pe import _fake_pe


def test_detector_confidence_range_elf():
    det = BinaryDetector()
    r = det.analyze(_fake_elf(), "sample.elf")
    assert 0.0 <= r.confidence <= 1.0


def test_detector_confidence_range_pe():
    det = BinaryDetector()
    r = det.analyze(_fake_pe(), "sample.exe")
    assert 0.0 <= r.confidence <= 1.0


def test_detector_on_stego_binary():
    det = BinaryDetector()
    carrier = _fake_elf()
    stego = ELFEncoder().encode(carrier, b"binary hidden payload")
    r = det.analyze(stego, "stego.elf")
    assert r.method == "binary"
    assert 0.0 <= r.confidence <= 1.0
