"""StegoForge ops split — canonical implementations (imported by stegoforge.py for compat)."""
from __future__ import annotations

import logging
import os
import struct
import zlib

from pathlib import Path
from typing import Any


from core.errors import (
    DecryptionError,
)
from stegoforge_ops.registry import (
    auto_detect_method,
    crypto_method_label,
    get_encoder,
    _guess_payload_ext,
    _scrub_secret,
)
from stegoforge_ops.ui import (
    C_WARN,
    console,
)

log = logging.getLogger(__name__)

def op_decode(
    file: str,
    key: str | None,
    output: str | None,
    method: str | None,
    wet_paper: bool,
    json_mode: bool,
    target_ip: str | None = None,
    target_port: int | None = None,
    listen_ip: str | None = None,
    listen_port: int | None = None,
    channel: str | None = None,
    timing_delta: int = 50,
    require_v2: bool = False,
    i_understand_root: bool = False,
) -> dict:
    file_path = Path(file)
    if not file_path.exists():
        raise OSError(f"File not found: {file}")

    stego_bytes = file_path.read_bytes()
    # Resolve key from env var fallback
    key = key or os.getenv("STEGOFORGE_KEY", "")
    ext = file_path.suffix.lower()
    methods_to_try = [method] if method else []
    if not methods_to_try:
        suggested = auto_detect_method(file)
        if suggested in ("audio-lsb", "phase", "spectrogram"):
            # Spectrogram is a visual watermark (decode returns PNG art, not
            # bytes), so never auto-try it — it would report false success.
            methods_to_try = ["audio-lsb", "phase"]
        elif suggested in ("video-dct", "video-motion"):
            methods_to_try = ["video-dct", "video-motion"]
        elif suggested in ("lsb", "adaptive-lsb", "dct", "alpha", "palette", "fingerprint-lsb"):
            methods_to_try = ["adaptive-lsb", "lsb", "fingerprint-lsb", "dct", "alpha", "palette"]
        elif suggested in ("elf", "pe"):
            methods_to_try = ["elf", "pe"]
        else:
            methods_to_try = [suggested]

    from core.crypto import decoy as decoy_mod
    from core.image.wetpaper import decode_wet_paper, is_wet_paper_blob

    payload = None
    last_error = None
    found_but_locked = False

    for try_method in methods_to_try:
        if try_method == "sfrg":
            if not key:
                # Keyless decode for .sfrg means "extract as-is".
                payload = stego_bytes
                method = "sfrg"
                wet_paper = False
                wet_corrected_bits = 0
                break
            try:
                payload = decoy_mod.decrypt_container(stego_bytes, key, None, require_v3=require_v2)
                method = "sfrg"
                wet_paper = False
                wet_corrected_bits = 0
                break
            except ValueError as e:
                last_error = str(e)
            continue

        encoder = get_encoder(try_method)
        kwargs: dict[str, Any] = {"key": key}
        if try_method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
            kwargs["ext"] = ext
        if try_method in ("docx", "xlsx", "office"):
            kwargs["filename"] = str(file_path)
        if try_method in ("tcp-covert", "timing-covert"):
            kwargs["target_ip"] = target_ip
            kwargs["target_port"] = target_port
            kwargs["listen_ip"] = listen_ip
            kwargs["listen_port"] = listen_port
            kwargs["channel"] = channel
            kwargs["timing_delta"] = timing_delta
            # Live sniff path needs explicit ack; artifact path does not.
            live_decode = not stego_bytes.startswith((b"SFTC", b"SFTM"))
            if live_decode:
                from core.network.guard import require_explicit_root_ack

                require_explicit_root_ack(bool(i_understand_root))
            console.print(
                f"[{C_WARN}]Legal notice:[/{C_WARN}] covert network channels must only be used on systems you own or are explicitly authorized to test."
            )

        depth_methods = {"lsb", "adaptive-lsb", "fingerprint-lsb", "audio-lsb"}
        depths = [1, 2, 3, 4] if try_method in depth_methods else [1]

        # The passphrase doubles as the traversal key. A decoy container is embedded with an
        # unkeyed traversal (either of its two keys must be able to find it), so try that too.
        traversals = [key, None] if key else [None]

        for depth in depths:
            kwargs["depth"] = depth
            for traversal in traversals:
                kwargs["key"] = traversal
                try:
                    raw_bytes = encoder.decode(stego_bytes, **kwargs)

                    corrected_bits = 0
                    wet_used = False
                    if wet_paper or is_wet_paper_blob(raw_bytes):
                        raw_bytes, corrected_bits, wet_used = decode_wet_paper(raw_bytes)

                    if not key:
                        # For keyless decode, return extracted bytes directly (encrypted or plaintext).
                        payload = raw_bytes
                    else:
                        try:
                            payload = decoy_mod.decrypt_container(
                                raw_bytes, key, crypto_method_label(try_method), require_v3=require_v2
                            )
                        except ValueError as e:
                            found_but_locked = True  # a payload structure was found: the key/method is wrong
                            last_error = str(e)
                            continue
                    method = try_method
                    wet_paper = wet_used
                    wet_corrected_bits = corrected_bits
                    break
                except (ValueError, struct.error, zlib.error, ImportError) as e:
                    # Decoders raise ValueError for bad input (BaseEncoder translates parser
                    # errors); a missing optional dependency is reported, not fatal. Anything
                    # else is a bug and must surface rather than read as "wrong key".
                    if not found_but_locked:
                        last_error = str(e)
            if payload is not None:
                break

        if payload is not None:
            break

    if payload is None:
        # With several auto-tried methods the last error belongs to an arbitrary one and only
        # misleads; report it when it is informative (explicit method, or a payload was found).
        if found_but_locked or len(methods_to_try) == 1:
            detail = f"Last error: {last_error}"
        else:
            detail = "Tried: " + ", ".join(methods_to_try)
        raise DecryptionError(f"Failed to decode payload: wrong key, wrong method, or corrupted file. {detail}")

    # Save output
    if output:
        out_path = Path(output)
    else:
        stem = file_path.stem.replace("_stego", "")
        detected_ext = _guess_payload_ext(payload)
        out_path = file_path.with_name(f"{stem}_decoded{detected_ext}")

    out_path.write_bytes(payload)

    _scrub_secret(key)
    result = {
        "status": "success",
        "method": method,
        "file": str(file_path),
        "payload_size": len(payload),
        "output": str(out_path),
        "wet_paper": bool(wet_paper),
        "wet_corrected_bits": int(locals().get("wet_corrected_bits", 0)),
    }
    return result


