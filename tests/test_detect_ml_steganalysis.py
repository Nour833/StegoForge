"""tests/test_detect_ml_steganalysis.py - Tests for ML detector fallback behavior."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect.ml_steganalysis import MLSteganalysisDetector

FIXTURES = Path(__file__).parent / "fixtures"


def test_ml_detector_returns_structured_result():
    det = MLSteganalysisDetector()
    data = (FIXTURES / "sample.png").read_bytes()
    r = det.analyze(data, "sample.png", classical={"chi2": 0.2, "rs": 0.1})
    assert r.method == "ml"
    assert 0.0 <= r.confidence <= 1.0
    assert "verdict" in r.details
