"""
web/app.py - StegoForge Flask web interface.
"""
import contextlib
import hmac
import io
import json
import logging
import os
import re
import sys
import tempfile
import urllib.parse

from pathlib import Path


from flask import Flask, Response, render_template, request, send_file, stream_with_context
from flask import jsonify as _flask_jsonify
from flask_cors import CORS

log = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

ARTIFACT_PREFIX = "stegoforge_web_artifact_"
_ARTIFACT_REGISTRY: dict[str, str] = {}
_ARTIFACT_NAMES: dict[str, str] = {}

# Origins allowed to call the API cross-origin: this machine only. The pattern is
# anchored: flask-cors matches with re.match, so an unanchored "http://localhost:*"
# also accepted "http://localhost.evil.com".
_LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]{1,5})?$"
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Server-side temp locations must never reach the client.
_TMP_PATH_RE = re.compile(re.escape(tempfile.gettempdir()) + r"[\\/]+(?:[^\\/\"\s]+[\\/]+)?")


def _scrub_text(text: str) -> str:
    return _TMP_PATH_RE.sub("", text)


def _scrub(obj):
    """Recursively strip the server's temp directory from every string in a response."""
    if isinstance(obj, str):
        return _scrub_text(obj)
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub(v) for v in obj]
    return obj


def jsonify(*args, **kwargs):
    """``flask.jsonify`` that never discloses temp-file paths."""
    return _flask_jsonify(*[_scrub(a) for a in args], **{k: _scrub(v) for k, v in kwargs.items()})


def _request_hostname() -> str:
    return (urllib.parse.urlsplit("//" + request.host).hostname or "").lower()


def _allowed_hosts() -> set[str]:
    extra = {h.strip().lower() for h in os.getenv("STEGOFORGE_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return set(_LOOPBACK_HOSTS) | extra


def _origin_allowed(origin: str) -> bool:
    if re.match(_LOCAL_ORIGIN_RE, origin, flags=re.IGNORECASE):
        return True
    host = (urllib.parse.urlsplit(origin).hostname or "").lower()
    return host in _allowed_hosts() - _LOOPBACK_HOSTS


def _require_web_token() -> tuple[bool, str]:
    """Optional shared-token auth for the local UI.

    Set STEGOFORGE_WEB_TOKEN (or ``auto``) to require the ``X-Stego-Token`` header
    or ``?token=`` (the latter only so plain download links can carry it).
    Returns (allowed, error_message).
    """
    expected = os.getenv("STEGOFORGE_WEB_TOKEN", "")
    if not expected:
        return True, ""
    provided = request.headers.get("X-Stego-Token", "") or request.args.get("token", "")
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        return False, "Missing or invalid web token"
    return True, ""


def _register_artifact(path: str, download_name: str | None = None) -> str:
    """Register artifact path under an opaque ID (no path disclosure)."""
    import secrets

    aid = secrets.token_hex(16)
    _ARTIFACT_REGISTRY[aid] = path
    if download_name:
        _ARTIFACT_NAMES[aid] = download_name
    # Bound registry size; an evicted artifact's file goes with it.
    while len(_ARTIFACT_REGISTRY) > 256:
        old = next(iter(_ARTIFACT_REGISTRY))
        Path(_ARTIFACT_REGISTRY.pop(old)).unlink(missing_ok=True)
        _ARTIFACT_NAMES.pop(old, None)
    return aid


_RATE_BUCKETS: dict[str, list[float]] = {}
RATE_LIMIT_POST_PER_MIN = 120


def _check_rate(ip: str) -> bool:
    """In-memory per-IP POST rate limit (120/min). Returns True if allowed."""
    import time as _t

    now = _t.time()
    bucket = _RATE_BUCKETS.get(ip, [])
    bucket = [t for t in bucket if now - t < 60.0]
    if len(bucket) >= RATE_LIMIT_POST_PER_MIN:
        _RATE_BUCKETS[ip] = bucket
        return False
    bucket.append(now)
    _RATE_BUCKETS[ip] = bucket
    if len(_RATE_BUCKETS) > 1024:
        _RATE_BUCKETS.pop(next(iter(_RATE_BUCKETS)))
    return True


def _as_bool(form, key: str, default: bool = False) -> bool:
    if key not in form:
        return default
    return str(form.get(key, "")).strip().lower() in {"1", "true", "yes", "on"}


def _json_sse(payload: dict) -> str:
    return f"data: {json.dumps(_scrub(payload))}\n\n"


def _artifact_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.is_symlink():
        return False
    if not resolved.exists() or not resolved.is_file():
        return False
    tmp_root = Path(tempfile.gettempdir()).resolve()
    try:
        if resolved.parent != tmp_root:
            return False
    except Exception:
        return False
    return resolved.name.startswith(ARTIFACT_PREFIX)


def _persist_artifact(data: bytes, suffix: str = ".bin") -> str:
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.NamedTemporaryFile(prefix=ARTIFACT_PREFIX, suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        return tmp.name


def _safe_upload_name(raw: str | None, fallback: str) -> str:
    """Sanitize multipart filenames: no paths, no traversal, safe chars only."""
    import re as _re

    name = (raw or "").strip() or fallback
    # Strip directories (both POSIX and Windows separators).
    name = name.replace("\\", "/").split("/")[-1]
    name = name.strip(". ")
    if name in ("", ".", ".."):
        name = fallback
    # Allowlist chars.
    name = _re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if name in ("", ".", ".."):
        name = fallback
    # Enforce length cap.
    return name[:128]


def _detect_payload_type(data: bytes) -> tuple[str, str]:
    """Return (mime_type, extension) guessed from the payload (shared with the CLI)."""
    from core.guess import guess_payload_type

    return guess_payload_type(data)


def _cleanup_old_artifacts(max_age_seconds: int = 3600):
    """Delete web artifact temp files older than max_age_seconds."""
    import time
    now = time.time()
    tmp_dir = Path(tempfile.gettempdir())
    for f in tmp_dir.glob(f"{ARTIFACT_PREFIX}*"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink(missing_ok=True)
        except OSError:
            pass


def _public_result(result: dict, download_name: str) -> dict:
    """The encode result as the client may see it: no server-side paths."""
    public = {k: v for k, v in result.items() if k not in ("output", "carrier", "file")}
    public["output"] = download_name
    return public


def _encode_operation(form, files, progress_callback=None) -> tuple[dict, bytes, str]:
    carrier_file = files.get("carrier")
    payload_file = files.get("payload")
    key = form.get("key", "")
    method = form.get("method", None) or None
    try:
        depth = int(form.get("depth", 1))
    except (TypeError, ValueError):
        raise ValueError("Depth must be an integer 1-4") from None
    if depth not in (1, 2, 3, 4):
        raise ValueError("Depth must be 1-4")
    decoy_file = files.get("decoy")
    decoy_key = form.get("decoy_key", None)
    wet_paper = _as_bool(form, "wet_paper", False)
    preserve_fingerprint = _as_bool(form, "preserve_fingerprint", False)
    target = form.get("target", None) or None
    test_survival = _as_bool(form, "test_survival", False)
    topic = form.get("topic", None) or None
    llm_model = form.get("llm_model", None) or None
    allow_plaintext = _as_bool(form, "allow_plaintext", False)

    if not carrier_file or not payload_file:
        raise ValueError("Both carrier and payload files are required")

    from stegoforge import op_encode

    carrier_name = _safe_upload_name(getattr(carrier_file, "filename", None), "carrier.bin")
    payload_name = _safe_upload_name(getattr(payload_file, "filename", None), "payload.bin")

    with tempfile.TemporaryDirectory(prefix="stegoforge_web_encode_") as td:
        td_path = Path(td)
        carrier_path = td_path / carrier_name
        payload_path = td_path / payload_name
        carrier_path.write_bytes(carrier_file.read())
        payload_path.write_bytes(payload_file.read())

        decoy_path = None
        if decoy_file and decoy_key:
            decoy_name = _safe_upload_name(getattr(decoy_file, "filename", None), "decoy.bin")
            decoy_path = td_path / decoy_name
            decoy_path.write_bytes(decoy_file.read())

        result = op_encode(
            str(carrier_path),
            str(payload_path),
            key,
            None,
            method,
            depth,
            str(decoy_path) if decoy_path else None,
            decoy_key,
            wet_paper,
            target,
            test_survival,
            preserve_fingerprint,
            None,
            topic,
            llm_model,
            False,
            allow_plaintext=allow_plaintext,
            progress_callback=progress_callback,
        )

        stego_bytes = Path(result["output"]).read_bytes()
        # The extension reflects what the encoder produced (mp3 -> wav, png+dct -> jpg, ...).
        download_name = f"{Path(carrier_name).stem}_stego{Path(result['output']).suffix or '.bin'}"

    return _public_result(result, download_name), stego_bytes, download_name


def _decode_operation(form, files) -> tuple[dict, bytes]:
    stego_file = files.get("file")
    key = form.get("key", "")
    method = form.get("method", None) or None
    wet_paper = _as_bool(form, "wet_paper", False)

    if not stego_file:
        raise ValueError("Stego file is required")

    from stegoforge import op_decode

    filename = _safe_upload_name(getattr(stego_file, "filename", None), "stego.bin")

    with tempfile.TemporaryDirectory(prefix="stegoforge_web_decode_") as td:
        td_path = Path(td)
        stego_path = td_path / filename
        stego_path.write_bytes(stego_file.read())

        result = op_decode(str(stego_path), key, None, method, wet_paper, False)
        payload = Path(result["output"]).read_bytes()

    # Detect payload MIME type and choose a smarter filename
    mime, detected_ext = _detect_payload_type(payload)
    # Honor any explicit output extension from op_decode if set
    out_path = Path(result.get("output", ""))
    ext = out_path.suffix if out_path.suffix and out_path.suffix != ".bin" else detected_ext
    dl_name = f"decoded_payload{ext}"
    result["download_name"] = dl_name
    result["detected_mime"] = mime
    result["detected_ext"] = ext

    return result, payload


def create_app():
    if getattr(sys, 'frozen', False):
        template_folder = os.path.join(sys._MEIPASS, 'web', 'templates')
        static_folder = os.path.join(sys._MEIPASS, 'web', 'static')
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    else:
        app = Flask(__name__, template_folder="templates", static_folder="static")
    # Restrict CORS to local origins only — the UI is a localhost tool and
    # must not be drivable by arbitrary external websites.
    local = [_LOCAL_ORIGIN_RE]
    CORS(app, resources={r"/api/*": {"origins": local},
                         r"/encode": {"origins": local},
                         r"/decode": {"origins": local},
                         r"/detect": {"origins": local}})
    from core.config import get_config as _get_cfg

    app.config["MAX_CONTENT_LENGTH"] = _get_cfg().max_upload_bytes

    _cleanup_old_artifacts()

    # Per-process token: STEGOFORGE_WEB_TOKEN=auto generates one per boot and
    # prints it to stderr (operator must present it as X-Stego-Token/?token=).
    _boot_token = os.getenv("STEGOFORGE_WEB_TOKEN", "")
    if _boot_token == "auto":
        import secrets as _sec

        _boot_token = _sec.token_hex(16)
        os.environ["STEGOFORGE_WEB_TOKEN"] = _boot_token
        print(f"[StegoForge] web token (this process only): {_boot_token}", file=sys.stderr)

    @app.before_request
    def _web_guard():
        from flask import request as _rq

        # DNS rebinding: a page on evil.example can resolve its own name to 127.0.0.1 and then
        # talk to this server as "same origin"; the Host header still names evil.example.
        if _request_hostname() not in _allowed_hosts():
            return jsonify({"error": "Invalid Host header"}), 403
        if _rq.method != "POST":
            return None
        # Cross-site form posts reach the server even when CORS blocks reading the reply.
        origin = _rq.headers.get("Origin")
        if origin and (origin == "null" or not _origin_allowed(origin)):
            return jsonify({"error": "Cross-origin request refused"}), 403
        ip = (_rq.remote_addr or "local")
        if not _check_rate(ip):
            return jsonify({"error": "Rate limit exceeded (120 POST/min)"}), 429
        ok, err = _require_web_token()
        if not ok:
            return jsonify({"error": err}), 401
        # CSRF: when a token is configured it doubles as the CSRF secret —
        # cross-origin forms cannot read it, so require it on POSTs.
        # (Enforced inside _require_web_token; nothing extra when unset.)
        with contextlib.suppress(Exception):
            log.info(
                "web %s %s from=%s len=%s",
                _rq.method, _rq.path, ip, _rq.content_length,
            )
        return None

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        if request.path.startswith(("/api/", "/artifact")) or request.method == "POST":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.route("/")
    def index():
        offline_fonts = os.getenv("STEGOFORGE_OFFLINE_FONTS", "") in ("1", "true", "yes") or os.getenv(
            "STEGOFORGE_OFFLINE", "") in ("1", "true", "yes")
        return render_template("index.html", initial_tab="encode", offline_fonts=offline_fonts)

    @app.route("/survive")
    def survive_page():
        offline_fonts = os.getenv("STEGOFORGE_OFFLINE_FONTS", "") in ("1", "true", "yes") or os.getenv(
            "STEGOFORGE_OFFLINE", "") in ("1", "true", "yes")
        return render_template("index.html", initial_tab="survive", offline_fonts=offline_fonts)

    @app.route("/artifact")
    def artifact_file():
        ok, err = _require_web_token()
        if not ok:
            return jsonify({"error": err}), 401
        # Opaque ?id= only — filesystem paths are never accepted (no disclosure).
        aid = request.args.get("id", "")
        if not aid:
            return jsonify({"error": "Missing artifact id"}), 400
        path = _ARTIFACT_REGISTRY.get(aid)
        if not path:
            return jsonify({"error": "Artifact not found"}), 404
        artifact = Path(path)
        if not _artifact_allowed(artifact):
            return jsonify({"error": "Artifact not found"}), 404
        return send_file(str(artifact), as_attachment=True, download_name=_ARTIFACT_NAMES.get(aid))

    @app.route("/artifact/<aid>")
    def artifact_by_id(aid: str):
        ok, err = _require_web_token()
        if not ok:
            return jsonify({"error": err}), 401
        path = _ARTIFACT_REGISTRY.get(aid or "")
        if not path:
            return jsonify({"error": "Artifact not found"}), 404
        artifact = Path(path)
        if not _artifact_allowed(artifact):
            return jsonify({"error": "Artifact not found"}), 404
        return send_file(str(artifact), as_attachment=True, download_name=_ARTIFACT_NAMES.get(aid))

    @app.errorhandler(413)
    def _too_large(_e):
        return jsonify({"error": "Upload exceeds limit"}), 413

    @app.route("/api/platform-profiles", methods=["GET"])
    def api_platform_profiles():
        from detect.survival import PROFILES

        out = {}
        for key, profile in PROFILES.items():
            out[key] = {
                "name": profile.name,
                "preferred_method": profile.preferred_method,
                "requires_wet_paper": profile.requires_wet_paper,
                "max_dimension": profile.max_dimension,
                "recompress_to_jpeg": profile.recompress_to_jpeg,
                "jpeg_quality": profile.jpeg_quality,
                "strips_exif": profile.strips_exif,
                "notes": profile.notes,
            }
        return jsonify({"profiles": out})

    @app.route("/api/capacity", methods=["POST"])
    def api_capacity():
        return capacity()

    @app.route("/api/capacity-matrix", methods=["POST"])
    def api_capacity_matrix():
        try:
            upload = request.files.get("file")
            payload = request.files.get("payload")
            try:
                depth = int(request.form.get("depth", 1))
            except (TypeError, ValueError):
                return jsonify({"error": "Depth must be an integer 1-4"}), 400
            if depth not in (1, 2, 3, 4):
                return jsonify({"error": "Depth must be 1-4"}), 400
            if not upload:
                return jsonify({"error": "No carrier file provided"}), 400

            from stegoforge import op_capacity

            payload_size = len(payload.read()) if payload else 0
            # What gets embedded is the encrypted envelope, a little larger than the payload itself.
            from core.crypto import aes

            encrypted_size = payload_size + aes.HEADER_LEN_V3 + aes.TAG_LEN if payload_size else 0
            filename = _safe_upload_name(getattr(upload, "filename", None), "carrier.bin")
            carrier_bytes = upload.read()
            if len(carrier_bytes) > _get_cfg().max_upload_bytes:
                return jsonify({"error": "Carrier exceeds upload limit"}), 400

            methods = [
                "lsb",
                "adaptive-lsb",
                "dct",
                "fingerprint-lsb",
                "alpha",
                "palette",
                "video-dct",
                "video-motion",
                "audio-lsb",
                "phase",
                "spectrogram",
                "unicode",
                "linguistic",
                "pdf",
                "docx",
                "xlsx",
            ]

            rows = []
            with tempfile.TemporaryDirectory(prefix="stegoforge_web_capmatrix_") as td:
                carrier_path = Path(td) / filename
                carrier_path.write_bytes(carrier_bytes)
                for method in methods:
                    try:
                        r = op_capacity(str(carrier_path), method, depth)
                        cap_bytes = int(r.get("capacity_bytes", 0))
                        util = round((encrypted_size / cap_bytes) * 100.0, 2) if cap_bytes > 0 and encrypted_size > 0 else 0.0
                        rows.append(
                            {
                                "method": method,
                                "capacity_bytes": cap_bytes,
                                "capacity_kb": r.get("capacity_kb", 0.0),
                                "utilization_pct": util,
                                "jnd_safe_dct_capacity": r.get("jnd_safe_dct_capacity"),
                                "video_context": r.get("video_context"),
                            }
                        )
                    except Exception as exc:
                        log.debug("capacity-matrix %s failed: %s", method, exc)
                        continue

            rows.sort(key=lambda x: x["capacity_bytes"], reverse=True)
            return jsonify(
                {
                    "file": filename,
                    "payload_size": payload_size,
                    "encrypted_size": encrypted_size,
                    "depth": depth,
                    "rows": rows,
                }
            )
        except (OSError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "Capacity check failed"}), 500

    @app.route("/api/survive", methods=["POST"])
    def api_survive():
        try:
            carrier_file = request.files.get("carrier")
            payload_file = request.files.get("payload")
            key = request.form.get("key", "")
            target = request.form.get("target", "twitter")
            method = request.form.get("method", None) or None
            try:
                depth = int(request.form.get("depth", 1))
            except (TypeError, ValueError):
                return jsonify({"error": "Depth must be an integer 1-4"}), 400
            if depth not in (1, 2, 3, 4):
                return jsonify({"error": "Depth must be 1-4"}), 400

            if not carrier_file or not payload_file:
                return jsonify({"error": "carrier and payload are required"}), 400

            from stegoforge import op_encode

            with tempfile.TemporaryDirectory(prefix="stegoforge_web_survive_") as td:
                td_path = Path(td)
                carrier_path = td_path / _safe_upload_name(getattr(carrier_file, "filename", None), "carrier.bin")
                payload_path = td_path / _safe_upload_name(getattr(payload_file, "filename", None), "payload.bin")
                carrier_path.write_bytes(carrier_file.read())
                payload_path.write_bytes(payload_file.read())

                result = op_encode(
                    str(carrier_path),
                    str(payload_path),
                    key,
                    None,
                    method,
                    depth,
                    None,
                    None,
                    False,
                    target,
                    True,
                    False,
                    None,
                    None,
                    None,
                    False,
                    allow_plaintext=_as_bool(request.form, "allow_plaintext", False),
                )

            return jsonify(_public_result(result, "survival-test"))
        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Survival simulation failed"}), 500

    @app.route("/api/encode-stream", methods=["POST"])
    def api_encode_stream():
        def _stream():
            import queue
            import threading
            import time as _time

            # Snapshot request data (streaming must not touch `request` in threads).
            form = request.form.to_dict()
            files = {k: (getattr(v, "filename", ""), v.read()) for k, v in request.files.items()}

            class _MemFile:
                def __init__(self, name: str, data: bytes):
                    self.filename = name
                    self._data = data

                def read(self) -> bytes:
                    return self._data

            mem_files = {k: _MemFile(name, data) for k, (name, data) in files.items()}
            events: queue.Queue[dict] = queue.Queue()
            done = {"finished": False}

            def _progress(done_n: int, total_n: int):
                pct = int((done_n / max(1, total_n)) * 100)
                events.put({"type": "progress", "pct": 5 + int(pct * 0.85), "text": f"Embedding… {pct}%"})

            def _worker():
                try:
                    result, stego_bytes, download_name = _encode_operation(form, mem_files, _progress)
                    events.put({"type": "done", "result": result,
                                "stego": stego_bytes.hex(), "download_name": download_name})
                except (OSError, ValueError) as exc:
                    events.put({"type": "error", "text": str(exc)})
                except Exception:
                    log.exception("encode-stream worker failed")
                    events.put({"type": "error", "text": "Encode failed"})
                finally:
                    done["finished"] = True

            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            yield _json_sse({"type": "progress", "pct": 5, "text": "Validating encode request..."})
            start = _time.time()
            last_tick = 0
            while True:
                try:
                    ev = events.get(timeout=0.5)
                except Exception:
                    ev = None
                if ev is None:
                    # Keepalive ticks while the worker runs (cap at 90%).
                    if not done["finished"] and _time.time() - start < 300:
                        last_tick = min(90, last_tick + 2)
                        yield _json_sse({"type": "progress", "pct": last_tick,
                                         "text": "Embedding…"})
                        continue
                    break
                kind = ev.get("type")
                if kind == "progress":
                    last_tick = max(last_tick, int(ev.get("pct", 0)))
                    yield _json_sse(ev)
                elif kind == "error":
                    yield _json_sse(ev)
                    break
                elif kind == "done":
                    result = ev["result"]
                    stego_bytes = bytes.fromhex(ev["stego"])
                    download_name = ev["download_name"]
                    artifact = _persist_artifact(stego_bytes, Path(download_name).suffix or ".bin")
                    aid = _register_artifact(artifact, download_name)
                    yield _json_sse({
                        "type": "success",
                        "pct": 100,
                        "text": "Encode completed",
                        "result": result,
                        "artifact_id": aid,
                        "download_name": download_name,
                    })
                    break
            thread.join(timeout=5)

        return Response(stream_with_context(_stream()), mimetype="text/event-stream")

    @app.route("/api/detect-stream", methods=["POST"])
    def api_detect_stream():
        def _stream():
            yield _json_sse({"type": "info", "text": "Loading file..."})
            try:
                upload = request.files.get("file")
                if not upload:
                    yield _json_sse({"type": "error", "text": "No file provided"})
                    return

                filename = _safe_upload_name(getattr(upload, "filename", None), "file.bin")
                raw = upload.read()
                if len(raw) > 200 * 1024 * 1024:
                    yield _json_sse({"type": "error", "text": "File exceeds upload limit"})
                    return

                from web.blueprints.forms import parse_detector_flags

                flags = parse_detector_flags(request.form)
                chi2 = flags["chi2"]
                rs = flags["rs"]
                exif = flags["exif"]
                blind = flags["blind"]
                ml = flags["ml"]
                fingerprint = flags["fingerprint"]
                binary = flags["binary"]

                if not any([chi2, rs, exif, blind, ml, fingerprint, binary]):
                    yield _json_sse({"type": "error", "text": "Select at least one detector"})
                    return

                from stegoforge import op_detect

                with tempfile.TemporaryDirectory(prefix="stegoforge_web_detectstream_") as td:
                    path = Path(td) / filename
                    path.write_bytes(raw)
                    report = op_detect(
                        str(path),
                        chi2,
                        rs,
                        exif,
                        blind,
                        ml,
                        fingerprint,
                        binary,
                        False,
                        False,
                    )

                for row in report.get("results", []):
                    status = "DETECTED" if row.get("detected") else "CLEAN"
                    yield _json_sse(
                        {
                            "type": "log",
                            "text": f"{row.get('method', 'detector')}: {status} ({int(float(row.get('confidence', 0.0)) * 100)}%)",
                        }
                    )

                yield _json_sse({"type": "success", "text": "Detection completed", "report": report})
            except (OSError, ValueError) as exc:
                yield _json_sse({"type": "error", "text": str(exc)})
            except Exception:
                log.exception("detect-stream failed")
                yield _json_sse({"type": "error", "text": "Detection failed"})

        return Response(stream_with_context(_stream()), mimetype="text/event-stream")

    @app.route("/encode", methods=["POST"])
    def encode():
        try:
            _result, stego_bytes, out_name = _encode_operation(request.form, request.files)

            buf = io.BytesIO(stego_bytes)
            buf.seek(0)
            return send_file(
                buf,
                as_attachment=True,
                download_name=out_name,
                mimetype="application/octet-stream",
            )

        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            log.exception("encode failed")
            return jsonify({"error": "Encode failed"}), 500

    @app.route("/decode", methods=["POST"])
    def decode():
        try:
            result, payload = _decode_operation(request.form, request.files)

            mime = result.get("detected_mime", "application/octet-stream")
            dl_name = result.get("download_name", "decoded_payload.bin")

            # For encrypted/opaque blobs, add a hint in the header
            extra_headers = {}
            if payload[:4] == b"SFRG":
                extra_headers["X-StegoForge-Hint"] = (
                    "Payload appears to be another StegoForge-encrypted blob. "
                    "Use 'stegoforge decode' with the correct key to unwrap it."
                )

            buf = io.BytesIO(payload)
            buf.seek(0)
            response = send_file(
                buf,
                as_attachment=True,
                download_name=dl_name,
                mimetype=mime,
            )
            for k, v in extra_headers.items():
                response.headers[k] = v
            return response

        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Decode failed"}), 500


    @app.route("/detect", methods=["POST"])
    def detect():
        try:
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "No file provided"}), 400

            from web.blueprints.forms import parse_detector_flags

            flags = parse_detector_flags(request.form)
            chi2 = flags["chi2"]
            rs = flags["rs"]
            exif = flags["exif"]
            blind = flags["blind"]
            ml = flags["ml"]
            fingerprint = flags["fingerprint"]
            binary = flags["binary"]

            if not any([chi2, rs, exif, blind, ml, fingerprint, binary]):
                return jsonify({"error": "Select at least one detector"}), 400

            from stegoforge import op_detect

            filename = _safe_upload_name(getattr(upload, "filename", None), "file.bin")
            with tempfile.TemporaryDirectory(prefix="stegoforge_web_detect_") as td:
                td_path = Path(td)
                file_path = td_path / filename
                file_path.write_bytes(upload.read())
                report = op_detect(
                    str(file_path),
                    chi2,
                    rs,
                    exif,
                    blind,
                    ml,
                    fingerprint,
                    binary,
                    False,
                    False,
                )

            return jsonify({"file": filename, "results": report["results"]})

        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Detection failed"}), 500

    @app.route("/ctf", methods=["POST"])
    def ctf():
        try:
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "No file provided"}), 400

            from stegoforge import op_ctf

            filename = _safe_upload_name(getattr(upload, "filename", None), "file.bin")
            extracted = None
            with tempfile.TemporaryDirectory(prefix="stegoforge_web_ctf_") as td:
                td_path = Path(td)
                file_path = td_path / filename
                file_path.write_bytes(upload.read())
                report = op_ctf(str(file_path), False)
                for r in report.get("results", []):
                    if r.get("has_payload"):
                        extracted_path = Path(report["saved_payloads"][0]) if report.get("saved_payloads") else None
                        if extracted_path and extracted_path.exists():
                            extracted = extracted_path.read_bytes()
                            break

            # Determine smart extension and MIME for extracted payload
            extracted_ext = ".bin"
            extracted_mime = "application/octet-stream"
            extra_notes = list(report.get("notes", []))
            if extracted is not None:
                extracted_mime, extracted_ext = _detect_payload_type(extracted)
                if extracted[:4] == b"SFRG":
                    extra_notes.append(
                        "⚠ Extracted payload starts with SFRG magic — this is a StegoForge "
                        "AES-256-GCM encrypted blob. Use 'stegoforge decode -f <carrier> -k <key>' "
                        "with the correct passphrase to decrypt it."
                    )
                else:
                    extra_notes.append(
                        "✔ Extracted raw payload successfully! The payload was embedded in plain text "
                        "(no encryption key was used)."
                    )
            elif report.get("overall_verdict") == "STEGO DETECTED":
                extra_notes.append(
                    "ℹ Steganography was detected structurally/statistically, but the raw payload "
                    "could not be blindly extracted. This usually happens if the payload was scattered "
                    "using an adaptive method, or protected by an encryption key. You must use the 'Decode' tab."
                )

            response = {
                "file": filename,
                "verdict": report.get("overall_verdict", "CLEAN"),
                "confidence": report.get("overall_confidence", 0.0),
                "results": report.get("results", []),
                "has_extracted_payload": extracted is not None,
                "notes": extra_notes,
                "report_json": report,
                "extracted_payload_ext": extracted_ext,
                "extracted_payload_mime": extracted_mime,
            }

            if extracted:
                response["extracted_payload_b64"] = __import__("base64").b64encode(extracted).decode()

            return jsonify(response)

        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "CTF analysis failed"}), 500


    @app.route("/capacity", methods=["GET", "POST"])
    def capacity():
        try:
            if request.method == "GET":
                return jsonify({"message": "POST a file to check capacity"})

            upload = request.files.get("file")
            method = request.form.get("method", None)
            try:
                depth = int(request.form.get("depth", 1))
            except (TypeError, ValueError):
                return jsonify({"error": "Depth must be an integer 1-4"}), 400
            if depth not in (1, 2, 3, 4):
                return jsonify({"error": "Depth must be 1-4"}), 400

            if not upload:
                return jsonify({"error": "No file provided"}), 400

            from stegoforge import op_capacity

            filename = _safe_upload_name(getattr(upload, "filename", None), "file.bin")
            with tempfile.TemporaryDirectory(prefix="stegoforge_web_capacity_") as td:
                td_path = Path(td)
                file_path = td_path / filename
                file_path.write_bytes(upload.read())
                result = op_capacity(str(file_path), method, depth)

            result["file"] = filename
            return jsonify(result)

        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Capacity check failed"}), 500

    @app.route("/diff", methods=["POST"])
    def diff():
        try:
            cover_file = request.files.get("cover")
            stego_file = request.files.get("stego")
            if not cover_file or not stego_file:
                return jsonify({"error": "Both cover and stego files are required"}), 400

            from stegoforge import op_diff
            import base64

            with tempfile.TemporaryDirectory(prefix="stegoforge_web_diff_") as td:
                td_path = Path(td)
                c_path = td_path / _safe_upload_name(getattr(cover_file, "filename", None), "cover.bin")
                s_path = td_path / _safe_upload_name(getattr(stego_file, "filename", None), "stego.bin")
                map_path = td_path / "heatmap.png"

                c_path.write_bytes(cover_file.read())
                s_path.write_bytes(stego_file.read())

                result = op_diff(str(c_path), str(s_path), str(map_path))

                if map_path.exists():
                    img_bytes = map_path.read_bytes()
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    result["heatmap_b64"] = f"data:image/png;base64,{b64}"

            return jsonify(result)
        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            log.exception("diff failed")
            return jsonify({"error": "Diff failed"}), 500

    return app


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    app = create_app()
    print(f"StegoForge Web UI -> http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
