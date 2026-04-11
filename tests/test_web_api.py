"""tests/test_web_api.py - Web API integration checks for new parity endpoints."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_platform_profiles_endpoint():
    c = _client()
    r = c.get("/api/platform-profiles")
    assert r.status_code == 200
    data = r.get_json()
    assert "profiles" in data
    assert "twitter" in data["profiles"]
    assert "facebook" in data["profiles"]


def test_capacity_matrix_endpoint():
    c = _client()
    carrier = (FIXTURES / "sample.png").read_bytes()
    payload = (FIXTURES / "sample.txt").read_bytes()
    r = c.post(
        "/api/capacity-matrix",
        data={
            "file": (io.BytesIO(carrier), "sample.png"),
            "payload": (io.BytesIO(payload), "sample.txt"),
            "depth": "1",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "rows" in data
    assert len(data["rows"]) > 0


def test_detect_requires_at_least_one_detector_when_explicitly_disabled():
    c = _client()
    carrier = (FIXTURES / "sample.png").read_bytes()
    r = c.post(
        "/detect",
        data={
            "file": (io.BytesIO(carrier), "sample.png"),
            "chi2": "0",
            "rs": "0",
            "exif": "0",
            "blind": "0",
            "ml": "0",
            "fingerprint": "0",
            "binary": "0",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data


def test_web_detect_audio_includes_audio_anomaly():
    c = _client()
    audio = (FIXTURES / "sample.wav").read_bytes()
    r = c.post(
        "/detect",
        data={
            "file": (io.BytesIO(audio), "sample.wav"),
            "chi2": "1",
            "rs": "1",
            "exif": "1",
            "blind": "1",
            "ml": "1",
            "fingerprint": "1",
            "binary": "1",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    methods = [x["method"] for x in r.get_json().get("results", [])]
    assert "audio-anomaly" in methods


def test_web_detect_pdf_includes_pdf_anomaly():
    c = _client()
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    r = c.post(
        "/detect",
        data={
            "file": (io.BytesIO(pdf), "sample.pdf"),
            "chi2": "1",
            "rs": "1",
            "exif": "1",
            "blind": "1",
            "ml": "1",
            "fingerprint": "1",
            "binary": "1",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    methods = [x["method"] for x in r.get_json().get("results", [])]
    assert "pdf-anomaly" in methods


def test_encode_stream_endpoint_emits_success():
    c = _client()
    carrier = (FIXTURES / "sample.png").read_bytes()
    payload = (FIXTURES / "sample.txt").read_bytes()
    r = c.post(
        "/api/encode-stream",
        data={
            "carrier": (io.BytesIO(carrier), "sample.png"),
            "payload": (io.BytesIO(payload), "sample.txt"),
            "key": "test-key",
            "method": "lsb",
            "depth": "1",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '"type": "success"' in body
