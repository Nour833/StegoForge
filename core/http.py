"""
core/http.py — SSRF-safe HTTP(S) client for user-supplied URLs.

StegoForge fetches/uploads dead-drop carriers and calls an optional local LLM.
Both take URLs from the user (or from a script), so the client must not be
steerable at internal services. Rather than pattern-matching the URL string —
which ``127.1``, ``2130706433``, ``0x7f000001`` and any DNS name that points at
a private address all defeat — this client:

* resolves the host itself with ``getaddrinfo`` (the same parser the OS uses to
  connect, so every legacy IPv4 spelling is normalised) and requires **every**
  resolved address to be globally routable;
* **connects to the validated IP** instead of resolving a second time, which
  closes the DNS-rebinding window between check and use;
* re-validates every redirect hop (each hop opens a new pinned connection) and
  allows only ``http``/``https`` redirects, at most three;
* ignores ambient proxy settings (a proxy would make the target unverifiable);
* caps the response size and applies a timeout.

``allow_private=True`` is an explicit opt-in for lab / localhost endpoints.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 3
_CHUNK = 64 * 1024


class UnsafeURLError(ValueError):
    """The URL points somewhere this client refuses to connect to."""


def validate_scheme_and_host(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"URL must be http(s), got scheme {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("URL must include a hostname")
    return parsed


def resolve_public(host: str, port: int, *, allow_private: bool = False) -> str:
    """Resolve ``host`` and return one validated IP (raises ``UnsafeURLError`` otherwise)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host {host!r}: {exc.strerror or exc}") from None
    addresses = []
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        addresses.append(ip.ipv4_mapped or ip if isinstance(ip, ipaddress.IPv6Address) else ip)
    if not addresses:
        raise ValueError(f"Cannot resolve host {host!r}")
    if not allow_private:
        blocked = next((a for a in addresses if not a.is_global), None)
        if blocked is not None:
            raise UnsafeURLError(
                f"Host {host!r} resolves to a non-public address ({blocked}); "
                "refusing to connect (pass allow_private=True / the matching opt-in to override)"
            )
    return str(addresses[0])


def _pinned(connection_cls, allow_private: bool):
    class Pinned(connection_cls):  # type: ignore[misc, valid-type]
        def connect(self):
            ip = resolve_public(self.host, self.port, allow_private=allow_private)
            sock = socket.create_connection((ip, self.port), self.timeout, self.source_address)
            if isinstance(self, http.client.HTTPSConnection):
                sock = self._context.wrap_socket(sock, server_hostname=self.host)
            self.sock = sock

    return Pinned


class _HTTP(urllib.request.HTTPHandler):
    def __init__(self, allow_private: bool):
        super().__init__()
        self._conn = _pinned(http.client.HTTPConnection, allow_private)

    def http_open(self, req):
        return self.do_open(self._conn, req)


class _HTTPS(urllib.request.HTTPSHandler):
    def __init__(self, allow_private: bool):
        super().__init__()
        self._conn = _pinned(http.client.HTTPSConnection, allow_private)

    def https_open(self, req):
        return self.do_open(self._conn, req)


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme not in ALLOWED_SCHEMES:
            raise urllib.error.HTTPError(newurl, code, "redirect to a non-http(s) URL refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(
    url: str,
    *,
    data: bytes | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20,
    max_bytes: int = 64 * 1024 * 1024,
    allow_private: bool = False,
) -> tuple[int, bytes]:
    """Request ``url`` and return ``(status, body)``.

    Raises:
        UnsafeURLError: URL scheme/host not allowed (a ``ValueError``).
        ValueError: DNS failure, HTTP error status, or response larger than ``max_bytes``.
    """
    validate_scheme_and_host(url)
    from core.config import get_config

    if get_config().offline and not allow_private:
        raise UnsafeURLError("offline mode is on (--offline / STEGOFORGE_OFFLINE): network access is disabled")
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler({}), _HTTP(allow_private), _HTTPS(allow_private),
                    _Redirects(), urllib.request.HTTPErrorProcessor(), urllib.request.UnknownHandler()):
        opener.add_handler(handler)

    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            body = bytearray()
            while True:
                chunk = resp.read(min(_CHUNK, max_bytes + 1 - len(body)))
                if not chunk:
                    break
                body += chunk
                if len(body) > max_bytes:
                    raise ValueError(f"Response exceeds the {max_bytes}-byte cap")
            return status, bytes(body)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}: {exc.reason}") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, UnsafeURLError):
            raise exc.reason from None
        raise ValueError(f"Request failed: {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        if isinstance(exc, UnsafeURLError):
            raise
        raise ValueError(f"Request failed: {exc}") from None
