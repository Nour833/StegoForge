"""tests/test_web_security.py — the local web UI must not be steerable from other sites.

Each test is one concrete attack from the security audit.
"""
import io
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "correct-horse-battery-29!"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("STEGOFORGE_WEB_TOKEN", raising=False)
    monkeypatch.delenv("STEGOFORGE_ALLOWED_HOSTS", raising=False)
    return create_app().test_client()


def _encode_form(key=KEY, **extra):
    data = {
        "carrier": (io.BytesIO((FIXTURES / "sample.png").read_bytes()), "sample.png"),
        "payload": (io.BytesIO(b"web payload"), "p.txt"),
        "method": "lsb",
        "depth": "1",
    }
    if key is not None:
        data["key"] = key
    data.update(extra)
    return data


def _sse_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


# ── CORS ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("origin", [
    "http://localhost.evil.com",
    "http://localhost:5000.evil.com",
    "http://127.0.0.1.evil.com",
    "https://evil.example",
    "null",
])
def test_cors_never_echoes_a_foreign_origin(client, origin):
    r = client.get("/api/platform-profiles", headers={"Origin": origin})
    assert "Access-Control-Allow-Origin" not in r.headers


@pytest.mark.parametrize("origin", ["http://localhost:5000", "http://127.0.0.1:8080", "http://localhost"])
def test_cors_allows_real_local_origins(client, origin):
    r = client.get("/api/platform-profiles", headers={"Origin": origin})
    assert r.headers.get("Access-Control-Allow-Origin") == origin


# ── CSRF + DNS rebinding ──────────────────────────────────────────────────────

@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost.evil.com", "null"])
def test_cross_site_post_is_refused_even_though_cors_only_hides_the_reply(client, origin):
    r = client.post("/capacity", data=_encode_form(), headers={"Origin": origin},
                    content_type="multipart/form-data")
    assert r.status_code == 403


def test_same_origin_and_non_browser_posts_are_accepted(client):
    data = {"file": (io.BytesIO((FIXTURES / "sample.png").read_bytes()), "s.png")}
    assert client.post("/capacity", data=data, content_type="multipart/form-data").status_code == 200
    data = {"file": (io.BytesIO((FIXTURES / "sample.png").read_bytes()), "s.png")}
    r = client.post("/capacity", data=data, headers={"Origin": "http://localhost:5000"},
                    content_type="multipart/form-data")
    assert r.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:5000", "localhost.evil.com", "10.0.0.5:5000"])
def test_dns_rebinding_host_is_refused_for_every_method(client, host):
    assert client.get("/", headers={"Host": host}).status_code == 403
    assert client.get("/api/platform-profiles", headers={"Host": host}).status_code == 403
    assert client.post("/capacity", headers={"Host": host}).status_code == 403


@pytest.mark.parametrize("host", ["localhost", "localhost:5000", "127.0.0.1:5000", "[::1]:5000"])
def test_loopback_hosts_work(client, host):
    assert client.get("/", headers={"Host": host}).status_code == 200


def test_extra_hosts_are_an_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("STEGOFORGE_ALLOWED_HOSTS", "stego.lan")
    c = create_app().test_client()
    assert c.get("/", headers={"Host": "stego.lan:5000"}).status_code == 200
    assert c.get("/", headers={"Host": "other.lan"}).status_code == 403


# ── token ─────────────────────────────────────────────────────────────────────

def test_token_is_required_and_compared_exactly(monkeypatch):
    monkeypatch.setenv("STEGOFORGE_WEB_TOKEN", "s3cret-token")
    c = create_app().test_client()
    form = lambda: {"file": (io.BytesIO((FIXTURES / "sample.png").read_bytes()), "s.png")}  # noqa: E731
    assert c.post("/capacity", data=form(), content_type="multipart/form-data").status_code == 401
    assert c.post("/capacity", data=form(), headers={"X-Stego-Token": "s3cret-toke"},
                  content_type="multipart/form-data").status_code == 401
    assert c.post("/capacity", data=form(), headers={"X-Stego-Token": "s3cret-token"},
                  content_type="multipart/form-data").status_code == 200


def test_auto_token_is_generated_and_enforced(monkeypatch, capsys):
    monkeypatch.setenv("STEGOFORGE_WEB_TOKEN", "auto")
    c = create_app().test_client()
    token = re.search(r"web token \(this process only\): (\w+)", capsys.readouterr().err).group(1)
    assert c.post("/capacity", content_type="multipart/form-data").status_code == 401
    r = c.post("/capacity", headers={"X-Stego-Token": token}, content_type="multipart/form-data")
    assert r.status_code == 400  # past auth: now it is only missing the file


def test_token_gates_artifact_downloads(monkeypatch):
    monkeypatch.setenv("STEGOFORGE_WEB_TOKEN", "tok")
    c = create_app().test_client()
    assert c.get("/artifact/deadbeef").status_code == 401
    assert c.get("/artifact/deadbeef?token=tok").status_code == 404


# ── fail-closed encryption ────────────────────────────────────────────────────

def test_web_encode_refuses_plaintext_unless_explicitly_allowed(client):
    r = client.post("/encode", data=_encode_form(key=""), content_type="multipart/form-data")
    assert r.status_code == 400 and "plaintext" in r.get_json()["error"].lower()

    r = client.post("/encode", data=_encode_form(key="", allow_plaintext="1"), content_type="multipart/form-data")
    assert r.status_code == 200


def test_web_stream_refuses_plaintext_by_default(client):
    r = client.post("/api/encode-stream", data=_encode_form(key=""), content_type="multipart/form-data")
    events = _sse_events(r.get_data(as_text=True))
    assert events[-1]["type"] == "error" and "plaintext" in events[-1]["text"].lower()


def test_web_survive_refuses_plaintext_by_default(client):
    data = _encode_form(key="")
    data["target"] = "twitter"
    r = client.post("/api/survive", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


# ── no server paths in responses ──────────────────────────────────────────────

def test_sse_success_exposes_no_temp_paths_and_downloads_as_attachment(client):
    r = client.post("/api/encode-stream", data=_encode_form(), content_type="multipart/form-data")
    body = r.get_data(as_text=True)
    assert tempfile.gettempdir() not in body
    done = _sse_events(body)[-1]
    assert done["type"] == "success"
    assert "artifact" not in done                      # the absolute temp path used to be sent here
    assert done["result"]["output"] == done["download_name"] == "sample_stego.png"
    assert "carrier" not in done["result"]

    dl = client.get(f"/artifact/{done['artifact_id']}")
    assert dl.status_code == 200
    assert "attachment" in dl.headers["Content-Disposition"] and "sample_stego.png" in dl.headers["Content-Disposition"]
    assert dl.data[:4] == b"\x89PNG"


def test_downloaded_stego_decodes_back(client):
    r = client.post("/api/encode-stream", data=_encode_form(), content_type="multipart/form-data")
    done = _sse_events(r.get_data(as_text=True))[-1]
    stego = client.get(f"/artifact/{done['artifact_id']}").data
    out = client.post("/decode", data={"file": (io.BytesIO(stego), "sample_stego.png"), "key": KEY},
                      content_type="multipart/form-data")
    assert out.status_code == 200 and out.data == b"web payload"


def test_scrub_strips_the_temp_directory_from_nested_values():
    from web.app import _scrub

    tmp = tempfile.gettempdir()
    obj = {"a": f"{tmp}/stegoforge_web_encode_x1/c_stego.png", "b": [f"{tmp}/stegoforge_web_artifact_zz.png"],
           "c": {"d": f"failed reading {tmp}/stegoforge_web_detect_q/f.bin: boom"}, "n": 3}
    out = _scrub(obj)
    assert out == {"a": "c_stego.png", "b": ["stegoforge_web_artifact_zz.png"],
                   "c": {"d": "failed reading f.bin: boom"}, "n": 3}


def test_survive_result_has_no_paths(client):
    data = _encode_form()
    data["target"] = "twitter"
    r = client.post("/api/survive", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert tempfile.gettempdir() not in r.get_data(as_text=True)


def test_unexpected_errors_do_not_echo_exception_text(client, monkeypatch):
    import web.app as web_app

    def boom(*a, **k):
        raise RuntimeError("secret detail at /home/someone/.ssh")

    monkeypatch.setattr(web_app, "_encode_operation", boom)
    r = client.post("/encode", data=_encode_form(), content_type="multipart/form-data")
    assert r.status_code == 500
    assert r.get_json() == {"error": "Encode failed"}


def test_security_headers_present(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Referrer-Policy"] == "no-referrer"
