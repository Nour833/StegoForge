"""tests/test_detect_survival.py - Tests for survivability profiles and simulation."""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect.survival import suggest_encode_profile, simulate_platform_pipeline


def _sample_png() -> bytes:
    img = Image.new("RGB", (128, 128), color=(120, 140, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_profile_lookup():
    p = suggest_encode_profile("twitter")
    assert p.name == "twitter"
    assert p.preferred_method in ("dct", "lsb")


def test_additional_platform_profiles_available():
    for name in ("facebook", "tiktok", "linkedin", "reddit", "signal"):
        p = suggest_encode_profile(name)
        assert p.name == name


def test_simulation_returns_structured_result():
    data = _sample_png()
    p = suggest_encode_profile("instagram")
    out, meta = simulate_platform_pipeline(data, "sample.png", p)
    assert isinstance(out, (bytes, bytearray))
    assert meta.get("simulated") in (True, False)
