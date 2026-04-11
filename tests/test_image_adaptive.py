"""tests/test_image_adaptive.py - Tests for adaptive content-aware LSB encoder."""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.image.lsb import LSBEncoder
from core.image.adaptive import AdaptiveLSBEncoder
from detect.chi2 import Chi2Detector


encoder = AdaptiveLSBEncoder()


def _make_mixed_image_bytes() -> bytes:
    # Left half smooth gradient, right half noisy texture.
    h, w = 256, 256
    grad = np.tile(np.linspace(20, 230, w // 2, dtype=np.uint8), (h, 1))
    left = np.stack([grad, grad, grad], axis=2)
    noise = np.random.default_rng(42).integers(0, 256, size=(h, w // 2, 3), dtype=np.uint8)
    arr = np.concatenate([left, noise], axis=1)
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_roundtrip():
    carrier = _make_mixed_image_bytes()
    payload = b"adaptive embedding payload"
    stego = encoder.encode(carrier, payload, key="k")
    result = encoder.decode(stego, key="k")
    assert result == payload


def test_capacity_positive():
    carrier = _make_mixed_image_bytes()
    assert encoder.capacity(carrier) > 0


def test_adaptive_chi2_lower_than_uniform_lsb():
    carrier = _make_mixed_image_bytes()
    payload = b"A" * 1500

    lsb_stego = LSBEncoder().encode(carrier, payload, depth=1)
    adp_stego = encoder.encode(carrier, payload, key="adaptive")

    detector = Chi2Detector()
    lsb_score = detector.analyze(lsb_stego, "lsb.png").confidence
    adp_score = detector.analyze(adp_stego, "adaptive.png").confidence

    assert adp_score <= lsb_score
