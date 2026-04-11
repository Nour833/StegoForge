"""tests/test_image_wetpaper.py - Tests for wet paper wrapper."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.image.wetpaper import encode_wet_paper, decode_wet_paper, is_wet_paper_blob


def test_roundtrip_or_missing_dep():
    payload = b"wet paper payload bytes" * 8
    try:
        wrapped = encode_wet_paper(payload, redundancy_bytes=16)
        decoded, corrected, used = decode_wet_paper(wrapped)
        assert used is True
        assert decoded == payload
        assert corrected >= 0
        assert is_wet_paper_blob(wrapped)
    except ValueError as exc:
        # If reedsolo is not installed in environment, module must fail gracefully.
        assert "reedsolo" in str(exc).lower()
