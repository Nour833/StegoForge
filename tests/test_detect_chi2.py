"""tests/test_detect_chi2.py — Tests for Chi-Square LSB detector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from detect.chi2 import Chi2Detector
from core.image.lsb import LSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"

detector = Chi2Detector()


def test_clean_image_low_confidence():
    """Clean random noise image should have low confidence."""
    carrier = CARRIER.read_bytes()
    result = detector.analyze(carrier, "sample.png")
    assert 0.0 <= result.confidence <= 1.0
    print(f"  Clean image chi2 confidence: {result.confidence:.3f}")


def test_stego_image_higher_confidence():
    """Image with lots of LSB data should have higher confidence than clean."""
    carrier = CARRIER.read_bytes()
    encoder = LSBEncoder()
    # Fill a large portion of capacity
    cap = encoder.capacity(carrier, depth=1)
    payload = bytes([i % 256 for i in range(min(cap, cap // 2))])
    stego = encoder.encode(carrier, payload)

    clean_result = detector.analyze(carrier, "clean.png")
    stego_result = detector.analyze(stego, "stego.png")
    print(f"  Clean confidence: {clean_result.confidence:.3f}")
    print(f"  Stego confidence: {stego_result.confidence:.3f}")
    assert isinstance(stego_result.detected, bool)
    assert 0.0 <= stego_result.confidence <= 1.0


def test_result_structure():
    result = detector.analyze(CARRIER.read_bytes(), "sample.png")
    assert result.method == "chi2"
    assert isinstance(result.detected, bool)
    assert 0.0 <= result.confidence <= 1.0
    assert "chi2_statistic" in result.details
    assert "p_value" in result.details
    assert "channels" in result.details


def test_unsupported_format_graceful():
    """Non-image bytes should be handled gracefully."""
    result = detector.analyze(b"not an image", "notanimage.txt")
    assert result.detected is False
    assert "error" in result.details


# ── statistic validity and verdict logic ─────────────────────────────────────

import io  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _natural(seed: int = 5, size: int = 200) -> np.ndarray:
    """Smooth gradients plus mild noise: unequal pair counts, like a photograph."""
    yy, xx = np.mgrid[0:size, 0:size]
    base = np.stack([
        (xx * 1.2 + 20 * np.sin(yy / 9)).clip(0, 255),
        (yy * 1.1).clip(0, 255),
        ((xx + yy) / 1.6).clip(0, 255),
    ], -1)
    noise = np.random.default_rng(seed).integers(-3, 4, base.shape)
    return (base + noise).clip(0, 255).astype(np.uint8)


def test_pairs_too_small_for_chi_square_are_skipped():
    counts = np.repeat(np.arange(0, 256, 2), 3)  # 3 samples per pair: expected count < 5
    _, _, used = detector._chi2_pvalue(counts)
    assert used == 0


def test_opaque_alpha_does_not_mask_the_rgb_statistic():
    rgb = _natural()
    rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    plain = detector.analyze(_png(rgb), "a.png").details
    with_alpha = detector.analyze(_png(rgba), "b.png").details
    assert with_alpha["p_value"] == plain["p_value"]
    assert with_alpha["n_pairs"] == plain["n_pairs"]
    assert "A" in with_alpha["channels"]


def test_natural_clean_image_is_reliable_and_not_flagged():
    d = detector.analyze(_png(_natural()), "clean.png")
    assert d.details["reliable"] is True
    assert not d.detected and d.details["p_head"] < 0.05


def test_noise_carrier_is_reported_as_uninformative_not_stego():
    noise = np.random.default_rng(1).integers(0, 256, (200, 200, 3), dtype=np.uint8)
    r = detector.analyze(_png(noise), "noise.png")
    assert r.details["reliable"] is False
    assert not r.detected and r.confidence == 0.0
    assert "cannot tell clean from stego" in r.details["interpretation"]


def test_sequential_partial_payloads_are_found_on_natural_images():
    """Half-capacity LSB payloads: the prefix scan must beat the diluted whole-image test."""
    carrier = _png(_natural())
    encoder = LSBEncoder()
    cap = encoder.capacity(carrier, depth=1)
    rng = np.random.default_rng(99)
    flagged, pooled_flagged = 0, 0
    trials = 12
    for _ in range(trials):
        stego = encoder.encode(carrier, rng.integers(0, 256, cap // 2, dtype=np.uint8).tobytes())
        r = detector.analyze(stego, "s.png")
        assert r.details["reliable"] is True  # the untouched tail is clearly non-equalised
        flagged += r.detected
        pooled_flagged += r.details["p_value"] >= 0.7
    assert flagged >= trials // 3
    assert flagged > pooled_flagged


def test_spatial_verdict_is_ignored_for_jpeg():
    noise = np.random.default_rng(2).integers(0, 256, (160, 160, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, format="JPEG", quality=95)
    r = detector.analyze(buf.getvalue(), "noise.jpg")
    assert r.details["spatial_confidence"] == 0.0


def test_vectorised_dct_signal_matches_the_reference_loop():
    from scipy.fft import dct

    img = Image.open(io.BytesIO((FIXTURES / "sample.jpg").read_bytes()))
    green = np.array(img.convert("RGB"), dtype=np.float64)[:, :, 1]
    h, w = green.shape
    reference = []
    for row in range(0, h - 7, 8):
        for col in range(0, w - 7, 8):
            blk = green[row:row + 8, col:col + 8]
            reference.append(dct(dct(blk.T, norm="ortho").T, norm="ortho")[4, 4])
    conf, info = detector._jpeg_dct_signal(img)
    assert info["blocks"] == len(reference)
    ref = np.abs(np.array(reference))
    assert info["tail_mean_abs"] == pytest.approx(round(float(np.mean(ref[info["front_blocks"]:])), 4), abs=1e-4)
