"""
protocol/deadrop.py - Dead drop polling/post helpers.
"""
from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path


def fetch_url_bytes(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "StegoForge/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def monitor_loop(url: str, interval: int, on_new):
    seen = set()
    while True:
        try:
            blob = fetch_url_bytes(url)
            digest = hash_bytes(blob)
            if digest not in seen:
                seen.add(digest)
                on_new(blob, digest)
        except Exception:
            pass
        time.sleep(max(1, interval))


def save_local_output(data: bytes, path: str | None, default_name: str) -> str:
    p = Path(path) if path else Path(default_name)
    p.write_bytes(data)
    return str(p)


def upload_bytes(url: str, data: bytes, method: str = "PUT", timeout: int = 30) -> dict:
    m = (method or "PUT").upper()
    if m not in {"PUT", "POST"}:
        raise ValueError("upload method must be PUT or POST")

    req = urllib.request.Request(
        url,
        data=data,
        method=m,
        headers={
            "User-Agent": "StegoForge/1.0",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return {
                "status": int(getattr(resp, "status", 200)),
                "reason": getattr(resp, "reason", "OK"),
                "response": body.decode("utf-8", errors="replace")[:500],
            }
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Upload failed with HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Upload failed: {exc.reason}") from exc
