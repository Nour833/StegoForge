"""
protocol/deadrop.py — dead-drop polling and posting helpers.

All network I/O goes through ``core.http`` (SSRF-safe: resolved-address checks,
connection pinning, bounded redirects, size caps). Pass ``allow_private=True``
(CLI: ``--allow-private``) to use a dead drop on a private/lab network.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from pathlib import Path

from core.config import get_config
from core.http import fetch, validate_scheme_and_host
from core.version import __version__

log = logging.getLogger(__name__)

_SEEN_LIMIT = 1024


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {"User-Agent": f"StegoForge/{__version__}", **(extra or {})}


def fetch_url_bytes(
    url: str,
    timeout: int | None = None,
    max_bytes: int | None = None,
    *,
    allow_private: bool = False,
) -> bytes:
    """Download ``url`` (size-capped, SSRF-safe) and return the body."""
    cfg = get_config()
    _, body = fetch(
        url,
        headers=_headers(),
        timeout=cfg.fetch_timeout if timeout is None else timeout,
        max_bytes=cfg.deadrop_max_bytes if max_bytes is None else max_bytes,
        allow_private=allow_private,
    )
    return body


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def monitor_loop(
    url: str,
    interval: int,
    on_new,
    *,
    max_iterations: int | None = None,
    allow_private: bool = False,
    on_error=None,
):
    """Poll ``url`` forever (or ``max_iterations`` times), calling ``on_new(blob, digest)``.

    The first successful poll only establishes the baseline. Poll failures are
    reported once per distinct message through ``on_error(message)`` (default:
    a ``WARNING`` log) instead of being silently swallowed.
    """
    validate_scheme_and_host(url)
    seen: OrderedDict[str, None] = OrderedDict()
    baseline_taken = False
    last_error: str | None = None
    iterations = 0
    while True:
        try:
            blob = fetch_url_bytes(url, allow_private=allow_private)
            last_error = None
            digest = hash_bytes(blob)
            if digest not in seen:
                if baseline_taken:  # the first poll is the baseline, not "new"
                    on_new(blob, digest)
                seen[digest] = None
                while len(seen) > _SEEN_LIMIT:
                    seen.popitem(last=False)  # evict the oldest, never the newest
            baseline_taken = True
        except Exception as exc:  # noqa: BLE001 - a poll must never kill the monitor
            message = str(exc)
            if message != last_error:
                (on_error or (lambda m: log.warning("dead-drop poll failed: %s", m)))(message)
                last_error = message
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        time.sleep(max(1, interval))


def save_local_output(data: bytes, path: str | None, default_name: str) -> str:
    p = Path(path) if path else Path(default_name)
    p.write_bytes(data)
    return str(p)


def upload_bytes(url: str, data: bytes, method: str = "PUT", timeout: int = 30, *, allow_private: bool = False) -> dict:
    """PUT/POST ``data`` to ``url`` and return ``{status, reason, response}``."""
    m = (method or "PUT").upper()
    if m not in {"PUT", "POST"}:
        raise ValueError("upload method must be PUT or POST")
    cap = get_config().deadrop_max_bytes
    if len(data) > cap:
        raise ValueError(f"Upload payload exceeds {cap} byte cap")
    status, body = fetch(
        url,
        data=data,
        method=m,
        headers=_headers({"Content-Type": "application/octet-stream"}),
        timeout=timeout,
        max_bytes=1024 * 1024,
        allow_private=allow_private,
    )
    return {"status": status, "reason": "OK" if 200 <= status < 300 else str(status),
            "response": body.decode("utf-8", errors="replace")[:500]}
