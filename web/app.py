"""
web/app.py - StegoForge Flask web interface.
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

ARTIFACT_PREFIX = "stegoforge_web_artifact_"


def _as_bool(form, key: str, default: bool = False) -> bool:
    if key not in form:
        return default
    return str(form.get(key, "")).strip().lower() in {"1", "true", "yes", "on"}


def _json_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _artifact_allowed(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.name.startswith(ARTIFACT_PREFIX):
        return True
    if path.name.endswith("_fingerprint_heatmap.png") and path.parent.resolve() == Path.cwd().resolve():
        return True
    return False


def _persist_artifact(data: bytes, suffix: str = ".bin") -> str:
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.NamedTemporaryFile(prefix=ARTIFACT_PREFIX, suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        return tmp.name


def _is_video_name(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in {".mp4", ".webm"}


def _is_video_method(method: str | None) -> bool:
    return method in {"video-dct", "video-motion"}


# Magic bytes → (mime, extension)
_MAGIC_MAP = [
    (b"\x89PNG",           "image/png",        ".png"),
    (b"\xff\xd8\xff",      "image/jpeg",       ".jpg"),
    (b"GIF8",              "image/gif",        ".gif"),
    (b"BM",                "image/bmp",        ".bmp"),
    (b"II*\x00",           "image/tiff",       ".tiff"),
    (b"MM\x00*",           "image/tiff",       ".tiff"),
    (b"RIFF",              "audio/wav",        ".wav"),
    (b"ID3",               "audio/mpeg",       ".mp3"),
    (b"\xff\xfb",          "audio/mpeg",       ".mp3"),
    (b"fLaC",              "audio/flac",       ".flac"),
    (b"OggS",              "audio/ogg",        ".ogg"),
    (b"\x00\x00\x00",      None,               None),   # placeholder (mp4 check below)
    (b"%PDF",              "application/pdf",  ".pdf"),
    (b"PK\x03\x04",        "application/zip",  ".zip"),  # also docx/xlsx
    (b"\x7fELF",           "application/x-elf", ".elf"),
    (b"MZ",                "application/x-pe",  ".exe"),
    (b"{\n", None, None),   # placeholder JSON
]


def _detect_payload_type(data: bytes) -> tuple[str, str]:
    """Return (mime_type, extension) guessed from magic bytes."""
    if len(data) >= 12:
        # ISO base media (mp4/mov) — ftyp box at offset 4
        if data[4:8] == b"ftyp":
            return "video/mp4", ".mp4"
    if data[:4] == b"PK\x03\x04":
        # Could be DOCX or XLSX inside a zip
        return "application/zip", ".zip"
    if data[:4] == b"SFRG":
        return "application/octet-stream", ".sfrg"
    for magic, mime, ext in _MAGIC_MAP:
        if mime and data[:len(magic)] == magic:
            return mime, ext
    # Try UTF-8 text heuristic
    try:
        text = data[:512].decode("utf-8")
        printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
        if text and (printable / max(len(text), 1)) > 0.85:
            return "text/plain", ".txt"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream", ".bin"


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


def _encode_operation(form, files) -> tuple[dict, bytes, str]:
    carrier_file = files.get("carrier")
    payload_file = files.get("payload")
    key = form.get("key", "")
    method = form.get("method", None) or None
    depth = int(form.get("depth", 1))
    decoy_file = files.get("decoy")
    decoy_key = form.get("decoy_key", None)
    wet_paper = _as_bool(form, "wet_paper", False)
    preserve_fingerprint = _as_bool(form, "preserve_fingerprint", False)
    target = form.get("target", None) or None
    test_survival = _as_bool(form, "test_survival", False)
    topic = form.get("topic", None) or None
    llm_model = form.get("llm_model", None) or None

    if not carrier_file or not payload_file:
        raise ValueError("Both carrier and payload files are required")

    from stegoforge import op_encode
    from core.audio._convert import has_ffmpeg

    carrier_name = carrier_file.filename or "carrier.bin"
    payload_name = payload_file.filename or "payload.bin"

    if _is_video_method(method) or (not method and _is_video_name(carrier_name)):
        if not has_ffmpeg():
            raise ValueError("Video methods require ffmpeg. Install with: sudo apt install ffmpeg")

    with tempfile.TemporaryDirectory(prefix="stegoforge_web_encode_") as td:
        td_path = Path(td)
        carrier_path = td_path / carrier_name
        payload_path = td_path / payload_name
        carrier_path.write_bytes(carrier_file.read())
        payload_path.write_bytes(payload_file.read())

        decoy_path = None
        if decoy_file and decoy_key:
            decoy_name = decoy_file.filename or "decoy.bin"
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
        )

        stego_bytes = Path(result["output"]).read_bytes()

    return result, stego_bytes, carrier_name


def _decode_operation(form, files) -> tuple[dict, bytes]:
    stego_file = files.get("file")
    key = form.get("key", "")
    method = form.get("method", None) or None
    wet_paper = _as_bool(form, "wet_paper", False)

    if not stego_file:
        raise ValueError("Stego file is required")

    from stegoforge import op_decode
    from core.audio._convert import has_ffmpeg

    filename = stego_file.filename or "stego.bin"
    if _is_video_method(method) or (not method and _is_video_name(filename)):
        if not has_ffmpeg():
            raise ValueError("Video methods require ffmpeg. Install with: sudo apt install ffmpeg")

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
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB max upload

    _cleanup_old_artifacts()

    @app.route("/")
    def index():
        return render_template("index.html", initial_tab="encode")

    @app.route("/survive")
    def survive_page():
        return render_template("index.html", initial_tab="survive")

    @app.route("/artifact")
    def artifact_file():
        p = request.args.get("path", "")
        if not p:
            return jsonify({"error": "Missing path"}), 400
        artifact = Path(p)
        if not _artifact_allowed(artifact):
            return jsonify({"error": "Artifact not found"}), 404
        return send_file(str(artifact), as_attachment=False)

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
            depth = int(request.form.get("depth", 1))
            if not upload:
                return jsonify({"error": "No carrier file provided"}), 400

            from stegoforge import op_capacity

            payload_size = len(payload.read()) if payload else 0
            filename = upload.filename or "carrier.bin"
            carrier_bytes = upload.read()

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
                        util = round((payload_size / cap_bytes) * 100.0, 2) if cap_bytes > 0 and payload_size > 0 else 0.0
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
                    except Exception:
                        continue

            rows.sort(key=lambda x: x["capacity_bytes"], reverse=True)
            return jsonify(
                {
                    "file": filename,
                    "payload_size": payload_size,
                    "depth": depth,
                    "rows": rows,
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/survive", methods=["POST"])
    def api_survive():
        try:
            carrier_file = request.files.get("carrier")
            payload_file = request.files.get("payload")
            key = request.form.get("key", "")
            target = request.form.get("target", "twitter")
            method = request.form.get("method", None) or None
            depth = int(request.form.get("depth", 1))

            if not carrier_file or not payload_file:
                return jsonify({"error": "carrier and payload are required"}), 400

            from stegoforge import op_encode

            with tempfile.TemporaryDirectory(prefix="stegoforge_web_survive_") as td:
                td_path = Path(td)
                carrier_path = td_path / (carrier_file.filename or "carrier.bin")
                payload_path = td_path / (payload_file.filename or "payload.bin")
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
                )

            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/encode-stream", methods=["POST"])
    def api_encode_stream():
        def _stream():
            yield _json_sse({"type": "info", "text": "Validating encode request..."})
            try:
                result, stego_bytes, carrier_name = _encode_operation(request.form, request.files)
                yield _json_sse({"type": "info", "text": "Embedding complete, preparing artifact..."})

                ext = Path(carrier_name).suffix or ".bin"
                artifact = _persist_artifact(stego_bytes, ext)
                download_name = f"{Path(carrier_name).stem}_stego{ext}"

                payload = {
                    "type": "success",
                    "text": "Encode completed",
                    "result": result,
                    "artifact": artifact,
                    "download_name": download_name,
                }
                yield _json_sse(payload)
            except Exception as exc:
                yield _json_sse({"type": "error", "text": str(exc)})

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

                filename = upload.filename or "file.bin"
                raw = upload.read()

                toggle_keys = ["chi2", "rs", "exif", "blind", "ml", "fingerprint", "binary"]
                explicit = any(k in request.form for k in toggle_keys)
                chi2 = _as_bool(request.form, "chi2", not explicit)
                rs = _as_bool(request.form, "rs", not explicit)
                exif = _as_bool(request.form, "exif", not explicit)
                blind = _as_bool(request.form, "blind", not explicit)
                ml = _as_bool(request.form, "ml", not explicit)
                fingerprint = _as_bool(request.form, "fingerprint", not explicit)
                binary = _as_bool(request.form, "binary", not explicit)

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
            except Exception as exc:
                yield _json_sse({"type": "error", "text": str(exc)})

        return Response(stream_with_context(_stream()), mimetype="text/event-stream")

    @app.route("/encode", methods=["POST"])
    def encode():
        try:
            result, stego_bytes, carrier_name = _encode_operation(request.form, request.files)
            _ = result

            stem = Path(carrier_name).stem
            ext = Path(carrier_name).suffix.lower()
            out_name = f"{stem}_stego{ext or '.bin'}"

            buf = io.BytesIO(stego_bytes)
            buf.seek(0)
            return send_file(
                buf,
                as_attachment=True,
                download_name=out_name,
                mimetype="application/octet-stream",
            )

        except (ValueError, IOError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

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

        except (ValueError, IOError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


    @app.route("/detect", methods=["POST"])
    def detect():
        try:
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "No file provided"}), 400

            toggle_keys = ["chi2", "rs", "exif", "blind", "ml", "fingerprint", "binary"]
            explicit = any(k in request.form for k in toggle_keys)
            chi2 = _as_bool(request.form, "chi2", not explicit)
            rs = _as_bool(request.form, "rs", not explicit)
            exif = _as_bool(request.form, "exif", not explicit)
            blind = _as_bool(request.form, "blind", not explicit)
            ml = _as_bool(request.form, "ml", not explicit)
            fingerprint = _as_bool(request.form, "fingerprint", not explicit)
            binary = _as_bool(request.form, "binary", not explicit)

            if not any([chi2, rs, exif, blind, ml, fingerprint, binary]):
                return jsonify({"error": "Select at least one detector"}), 400

            from stegoforge import op_detect

            filename = upload.filename or "file.bin"
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

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/ctf", methods=["POST"])
    def ctf():
        try:
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "No file provided"}), 400

            from stegoforge import op_ctf

            filename = upload.filename or "file.bin"
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

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route("/capacity", methods=["GET", "POST"])
    def capacity():
        try:
            if request.method == "GET":
                return jsonify({"message": "POST a file to check capacity"})

            upload = request.files.get("file")
            method = request.form.get("method", None)
            depth = int(request.form.get("depth", 1))

            if not upload:
                return jsonify({"error": "No file provided"}), 400

            from stegoforge import op_capacity

            filename = upload.filename or "file.bin"
            with tempfile.TemporaryDirectory(prefix="stegoforge_web_capacity_") as td:
                td_path = Path(td)
                file_path = td_path / filename
                file_path.write_bytes(upload.read())
                result = op_capacity(str(file_path), method, depth)

            result["file"] = filename
            return jsonify(result)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

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
                c_path = td_path / (cover_file.filename or "cover.bin")
                s_path = td_path / (stego_file.filename or "stego.bin")
                map_path = td_path / "heatmap.png"

                c_path.write_bytes(cover_file.read())
                s_path.write_bytes(stego_file.read())

                result = op_diff(str(c_path), str(s_path), str(map_path))

                if map_path.exists():
                    img_bytes = map_path.read_bytes()
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    result["heatmap_b64"] = f"data:image/png;base64,{b64}"

            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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
