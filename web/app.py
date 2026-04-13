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
    if not key:
        raise ValueError("Encryption key is required")

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
    if not key:
        raise ValueError("Decryption key is required")

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

            if not carrier_file or not payload_file or not key:
                return jsonify({"error": "carrier, payload, and key are required"}), 400

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
            _, payload = _decode_operation(request.form, request.files)

            ext_out = ".bin"
            if payload[:4] == b"\x89PNG":
                ext_out = ".png"
            elif payload[:2] == b"\xff\xd8":
                ext_out = ".jpg"
            elif payload[:4] == b"PK\x03\x04":
                ext_out = ".zip"
            elif payload[:4] == b"%PDF":
                ext_out = ".pdf"
            else:
                try:
                    payload.decode("utf-8")
                    ext_out = ".txt"
                except UnicodeDecodeError:
                    pass

            buf = io.BytesIO(payload)
            buf.seek(0)
            return send_file(
                buf,
                as_attachment=True,
                download_name=f"decoded_payload{ext_out}",
                mimetype="application/octet-stream",
            )

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

            response = {
                "file": filename,
                "verdict": report.get("overall_verdict", "CLEAN"),
                "confidence": report.get("overall_confidence", 0.0),
                "results": report.get("results", []),
                "has_extracted_payload": extracted is not None,
                "notes": report.get("notes", []),
                "report_json": report,
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
