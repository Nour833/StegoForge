"""
web/app.py — StegoForge Flask web interface.

Routes:
  GET  /         — main UI
  POST /encode   — embed payload, return stego file
  POST /decode   — extract payload from stego file
  POST /detect   — run detectors, return JSON report
  POST /ctf      — full CTF analysis report
  GET  /capacity — check carrier capacity
"""
import io
import json
import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max upload

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/encode", methods=["POST"])
    def encode():
        try:
            carrier_file = request.files.get("carrier")
            payload_file = request.files.get("payload")
            key = request.form.get("key", "")
            method = request.form.get("method", None) or None
            depth = int(request.form.get("depth", 1))
            decoy_file = request.files.get("decoy")
            decoy_key = request.form.get("decoy_key", None)

            if not carrier_file or not payload_file:
                return jsonify({"error": "Both carrier and payload files are required"}), 400
            if not key:
                return jsonify({"error": "Encryption key is required"}), 400

            carrier_bytes = carrier_file.read()
            payload_bytes = payload_file.read()
            carrier_name = carrier_file.filename or "carrier"

            from cli import get_encoder, auto_detect_method, EXT_TO_METHOD
            from core.crypto import aes
            from pathlib import Path as P

            method = method or auto_detect_method(carrier_name)
            encoder = get_encoder(method)

            # Build kwargs before capacity check so ext is included for audio
            ext = P(carrier_name).suffix.lower()
            cap_kwargs = {"depth": depth}
            if method in ("audio-lsb", "phase", "spectrogram"):
                cap_kwargs["ext"] = ext
            if method in ("docx", "xlsx", "office"):
                cap_kwargs["filename"] = carrier_name

            # Encrypt
            if decoy_file and decoy_key:
                from core.crypto import decoy as decoy_mod
                decoy_bytes = decoy_file.read()
                embed_bytes = decoy_mod.encode_dual(decoy_bytes, decoy_key, payload_bytes, key)
            else:
                embed_bytes = aes.encrypt(payload_bytes, key)

            cap = encoder.capacity(carrier_bytes, **cap_kwargs)
            if len(embed_bytes) > cap:
                return jsonify({
                    "error": f"Payload too large: {len(embed_bytes)} bytes encrypted, capacity: {cap} bytes. "
                             "Try a larger carrier, smaller payload, or higher bit depth."
                }), 400

            encode_kwargs = {"depth": depth, "key": key, **cap_kwargs}
            stego_bytes = encoder.encode(carrier_bytes, embed_bytes, **encode_kwargs)

            # Output uses original extension to fulfill user request
            stem = P(carrier_name).stem
            out_name = f"{stem}_stego{ext}"

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
            stego_file = request.files.get("file")
            key = request.form.get("key", "")
            method = request.form.get("method", None) or None

            if not stego_file:
                return jsonify({"error": "Stego file is required"}), 400
            if not key:
                return jsonify({"error": "Decryption key is required"}), 400

            stego_bytes = stego_file.read()
            filename = stego_file.filename or "stego"

            from cli import get_encoder, auto_detect_method
            from core.crypto import aes, decoy as decoy_mod
            from pathlib import Path as P

            ext = P(filename).suffix.lower()
            methods_to_try = [method] if method else []
            if not methods_to_try:
                suggested = auto_detect_method(filename)
                if suggested in ("audio-lsb", "phase", "spectrogram"):
                    methods_to_try = ["audio-lsb", "phase", "spectrogram"]
                elif suggested in ("lsb", "dct", "alpha", "palette"):
                    methods_to_try = ["lsb", "dct", "alpha", "palette"]
                else:
                    methods_to_try = [suggested]

            payload = None
            last_error = None

            for try_method in methods_to_try:
                encoder = get_encoder(try_method)
                kwargs = {"key": key}
                if try_method in ("audio-lsb", "phase", "spectrogram"):
                    kwargs["ext"] = ext
                if try_method in ("docx", "xlsx", "office"):
                    kwargs["filename"] = filename
                
                for depth in [1, 2, 3, 4]:
                    try:
                        kwargs["depth"] = depth
                        raw_bytes = encoder.decode(stego_bytes, **kwargs)
                        try:
                            payload = decoy_mod.decode_dual(raw_bytes, key)
                            break
                        except ValueError:
                            payload = aes.decrypt(raw_bytes, key)
                            break
                    except ValueError as e:
                        last_error = str(e)
                        payload = None
                
                if payload is not None:
                    break

            if payload is None:
                raise ValueError(f"Failed to decode payload: wrong key, wrong method, or corrupted file. Last error: {last_error}")

            # Try to guess extension
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

            file_bytes = upload.read()
            filename = upload.filename or "file"

            from detect.chi2 import Chi2Detector
            from detect.rs import RSDetector
            from detect.exif import EXIFDetector
            from detect.blind import BlindExtractor

            results = []
            for det in [Chi2Detector(), RSDetector(), EXIFDetector(), BlindExtractor()]:
                r = det.analyze(file_bytes, filename)
                results.append({
                    "method": r.method,
                    "detected": r.detected,
                    "confidence": r.confidence,
                    "details": r.details,
                    "findings": getattr(r, "findings", []),
                })

            return jsonify({
                "file": filename,
                "results": results,
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/ctf", methods=["POST"])
    def ctf():
        try:
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "No file provided"}), 400

            file_bytes = upload.read()
            filename = upload.filename or "file"

            from detect.chi2 import Chi2Detector
            from detect.rs import RSDetector
            from detect.exif import EXIFDetector
            from detect.blind import BlindExtractor

            results = []
            extracted = None
            for det in [Chi2Detector(), RSDetector(), EXIFDetector(), BlindExtractor()]:
                r = det.analyze(file_bytes, filename)
                if r.extracted_payload:
                    extracted = r.extracted_payload
                results.append({
                    "method": r.method,
                    "detected": r.detected,
                    "confidence": r.confidence,
                    "details": r.details,
                    "findings": getattr(r, "findings", []),
                })

            overall = max((r["confidence"] for r in results), default=0.0)
            any_detected = any(r["detected"] for r in results)

            response = {
                "file": filename,
                "verdict": "STEGO DETECTED" if any_detected else "CLEAN",
                "confidence": round(overall, 4),
                "results": results,
                "has_extracted_payload": extracted is not None,
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

            file_bytes = upload.read()
            filename = upload.filename or "file"

            from cli import get_encoder, auto_detect_method
            from pathlib import Path as P

            method = method or auto_detect_method(filename)
            encoder = get_encoder(method)

            ext = P(filename).suffix.lower()
            kwargs = {"depth": depth}
            if method in ("audio-lsb", "phase", "spectrogram"):
                kwargs["ext"] = ext
            if method in ("docx", "xlsx", "office"):
                kwargs["filename"] = filename

            cap = encoder.capacity(file_bytes, **kwargs)

            return jsonify({
                "file": filename,
                "method": method,
                "depth": depth,
                "capacity_bytes": cap,
                "capacity_kb": round(cap / 1024, 2),
                "capacity_mb": round(cap / (1024 * 1024), 4),
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    app = create_app()
    print(f"StegoForge Web UI → http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
