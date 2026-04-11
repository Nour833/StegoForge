"""tests/test_video_methods.py - Smoke tests for video method availability.

These tests intentionally skip if optional dependencies are missing.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_video_encoders_instantiation():
    from core.video.dct import VideoDCTEncoder
    from core.video.motion import VideoMotionEncoder

    assert VideoDCTEncoder().name == "video-dct"
    assert VideoMotionEncoder().name == "video-motion"


def test_video_anomaly_detector_structured_skip_or_result():
    from detect.video_anomaly import VideoAnomalyDetector

    # Random bytes should return skipped or graceful result.
    r = VideoAnomalyDetector().analyze(b"not-a-video", "bad.mp4")
    assert r.method == "video-anomaly"
    assert 0.0 <= r.confidence <= 1.0
