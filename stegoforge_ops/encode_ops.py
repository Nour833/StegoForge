"""StegoForge ops split — canonical implementations (imported by stegoforge.py for compat)."""
from __future__ import annotations

import logging
import os

from pathlib import Path
from typing import Any


from core.errors import (
    CapacityError,
    PlaintextRefusedError,
    WeakPassphraseError,
)
from stegoforge_ops.registry import (
    auto_detect_method,
    canonical_method,
    crypto_method_label,
    get_encoder,
    get_output_path,
    _is_audio_ext,
    _is_image_ext,
    _resize_carrier_if_needed,
    _scrub_secret,
)
from stegoforge_ops.ui import (
    C_INFO,
    C_WARN,
    console,
)

log = logging.getLogger(__name__)

def op_encode(
    carrier: str,
    payload: str,
    key: str | None,
    output: str | None,
    method: str | None,
    depth: int,
    decoy: str | None,
    decoy_key: str | None,
    wet_paper: bool,
    target: str | None,
    test_survival: bool,
    preserve_fingerprint: bool,
    cover: str | None,
    topic: str | None,
    llm_model: str | None,
    json_mode: bool,
    target_ip: str | None = None,
    target_port: int | None = None,
    listen_ip: str | None = None,
    listen_port: int | None = None,
    channel: str | None = None,
    timing_delta: int = 50,
    allow_plaintext: bool = False,
    pad_block: int = 0,
    require_v2: bool = False,
    enforce_strong: bool = False,
    header_mode: str = "standard",
    i_understand_root: bool = False,
    progress_callback=None,
) -> dict:
    """Embed payload with fail-closed plaintext policy and method-bound crypto.

    Args:
        allow_plaintext: Explicit opt-in for unencrypted embeds. Without a key
            and without this flag, op_encode refuses (fail-closed).
        pad_block: If >0, pad plaintext to a multiple of this block before
            encryption to reduce ciphertext-length oracle (1-256, e.g. 128).
        require_v2: Refuse legacy v1 crypto paths (forward-looking; currently
            all new embeds are v2, so this is a no-op guard for callers).
        enforce_strong: Raise on weak passphrases instead of warning.
        header_mode: "standard" (SFRG magic) or "obfuscated" (key-derived
            header, no global static magic; incompatible with decoy mode).
        progress_callback: Optional callable(done, total) receiving real
            encoder progress (fingerprint-lsb backend; other methods call
            with coarse stage markers).
    """
    from stegoforge_ops.encode import EncodeRequest

    req = EncodeRequest(carrier, payload, key, method, depth, allow_plaintext, pad_block).validate()
    depth = req.depth
    pad_block = req.pad_block
    if header_mode not in ("standard", "obfuscated"):
        raise ValueError("header_mode must be 'standard' or 'obfuscated'")
    if cover and carrier and Path(cover) != Path(carrier):
        raise ValueError("--cover overrides --carrier; pass only one carrier path")
    carrier_path = Path(cover) if cover else Path(carrier)
    payload_path = Path(payload)

    if not carrier_path.exists():
        raise OSError(f"Carrier file not found: {carrier_path}")
    if not payload_path.exists():
        raise OSError(f"Payload file not found: {payload}")
    if len(payload_path.read_bytes()) == 0:
        raise ValueError("Payload file is empty — refusing to embed zero-length payload")

    carrier_bytes = carrier_path.read_bytes()
    payload_bytes = payload_path.read_bytes()

    if method in ("tcp-covert", "timing-covert"):
        import ipaddress

        for label, ip in (("target-ip", target_ip), ("listen-ip", listen_ip)):
            if ip:
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    raise ValueError(f"Invalid {label}: {ip!r}") from None
        if target_port is not None and not (0 < int(target_port) < 65536):
            raise ValueError(f"Invalid target-port: {target_port}")
        if listen_port is not None and not (0 < int(listen_port) < 65536):
            raise ValueError(f"Invalid listen-port: {listen_port}")
        live = bool(target_ip and target_port)
        if live:
            from core.network.guard import require_explicit_root_ack

            require_explicit_root_ack(bool(i_understand_root))

    method = method or auto_detect_method(str(carrier_path))

    # Resolve key from env var fallback before any encryption/placement logic.
    key = key or os.getenv("STEGOFORGE_KEY", "")

    profile = None
    if target:
        from detect.survival import suggest_encode_profile
        profile = suggest_encode_profile(target)
        if method is None or method == auto_detect_method(str(carrier_path)):
            method = profile.preferred_method
        wet_paper = wet_paper or profile.requires_wet_paper

    if preserve_fingerprint and method in ("lsb", "adaptive-lsb"):
        method = "fingerprint-lsb"

    encoder = get_encoder(method)  # raises "Unknown method ... Did you mean" for typos
    method = canonical_method(method)
    bind = crypto_method_label(method)  # alias-stable label authenticated inside the envelope

    # Encrypt: v3 envelope bound to the carrier method (never a silent legacy fallback).
    from core.crypto import aes
    from core.crypto.kdf import is_weak_password

    if key and is_weak_password(key):
        if enforce_strong:
            raise WeakPassphraseError(
                "Weak passphrase refused (--enforce-strong-pass). Use 12+ chars with mixed classes."
            )
        if not json_mode:
            console.print(
                f"[{C_WARN}]Weak passphrase (score ≤1). Use 12+ chars with mixed classes.[/{C_WARN}]"
            )
    if decoy and decoy_key:
        if not key:
            raise ValueError("Decoy mode requires a real payload key. Pass -k / --key or set STEGOFORGE_KEY.")
        if header_mode == "obfuscated":
            raise ValueError("Obfuscated headers are incompatible with decoy mode (decoy containers are already header-less).")
        from core.crypto import decoy as decoy_mod
        decoy_payload = Path(decoy).read_bytes()
        embed_bytes = decoy_mod.encode_dual(
            decoy_payload, decoy_key, payload_bytes, key, bind, pad_block or aes.OBF_PAD_BLOCK
        )
    elif key:
        if header_mode == "obfuscated":
            embed_bytes = aes.encrypt_obfuscated(payload_bytes, key, bind, pad_block or aes.OBF_PAD_BLOCK)
        else:
            embed_bytes = aes.encrypt_envelope(payload_bytes, key, bind, pad_block=pad_block)
    else:
        if not allow_plaintext and not os.getenv("STEGOFORGE_ALLOW_PLAINTEXT"):
            raise PlaintextRefusedError(
                "Refusing plaintext embed without a key (fail-closed). "
                "Pass -k/--key, set STEGOFORGE_KEY, or explicitly opt in with "
                "--allow-plaintext / allow_plaintext=True."
            )
        if not json_mode:
            console.print(f"[{C_WARN}]No key: embedding plaintext (detectable).[/{C_WARN}]")
        embed_bytes = payload_bytes

    if wet_paper:
        from core.image.wetpaper import encode_wet_paper
        embed_bytes = encode_wet_paper(embed_bytes)

    ext = carrier_path.suffix.lower()
    resized_from = resized_to = None
    if profile and _is_image_ext(ext):
        carrier_bytes, resized_from, resized_to = _resize_carrier_if_needed(
            carrier_bytes,
            ext,
            profile.max_dimension,
        )

    # Build kwargs before capacity check so audio ext is included
    # A decoy container must be findable with either of its two keys, so it is embedded with
    # an unkeyed traversal; every other embed is traversed in the order its passphrase selects.
    kwargs: dict[str, Any] = {"depth": depth, "key": None if (decoy and decoy_key) else key}
    if method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)
    if method == "linguistic":
        kwargs["topic"] = topic
        kwargs["llm_model"] = llm_model
    if method in ("tcp-covert", "timing-covert"):
        kwargs["target_ip"] = target_ip
        kwargs["target_port"] = target_port
        kwargs["listen_ip"] = listen_ip
        kwargs["listen_port"] = listen_port
        kwargs["channel"] = channel or ("timing" if method == "timing-covert" else "ip_id")
        kwargs["timing_delta"] = timing_delta
        console.print(
            f"[{C_WARN}]Legal notice:[/{C_WARN}] covert network channels must only be used on systems you own or are explicitly authorized to test."
        )
    if progress_callback is not None:
        try:
            progress_callback(0, 100)
        except Exception as exc:
            log.debug("progress_callback failed: %s", exc)
    if method == "fingerprint-lsb" and not json_mode:
        last_progress = {"pct": -1}

        def _progress(done: int, total: int):
            pct = int((done / max(1, total)) * 100)
            if pct >= last_progress["pct"] + 10 or pct == 100:
                last_progress["pct"] = pct
                console.print(f"[{C_INFO}]Fingerprint-preserving embed progress: {pct}%[/{C_INFO}]")
            if progress_callback is not None:
                try:
                    progress_callback(done, total)
                except Exception as exc:
                    log.debug("progress_callback failed: %s", exc)

        kwargs["progress_callback"] = _progress

    cap_kwargs = {k: v for k, v in kwargs.items() if k != "key"}  # capacity doesn't need key
    cap = encoder.capacity(carrier_bytes, **cap_kwargs)
    if len(embed_bytes) > cap:
        # Build smart suggestions
        suggestions = []
        if depth < 4 and (_is_image_ext(ext) or _is_audio_ext(ext)):
            needed_depth = 1
            for d in range(depth + 1, 5):
                test_cap = encoder.capacity(carrier_bytes, depth=d, **{k: v for k, v in cap_kwargs.items() if k != "depth"})
                if test_cap >= len(embed_bytes):
                    needed_depth = d
                    break
            if needed_depth > depth:
                suggestions.append(f"--depth {needed_depth} (gives ~{encoder.capacity(carrier_bytes, depth=needed_depth, **{k: v for k, v in cap_kwargs.items() if k != 'depth'}):,} bytes)")
        if method not in ("adaptive-lsb",) and _is_image_ext(ext):
            suggestions.append("--method adaptive-lsb (higher effective capacity + better stealth)")
        budget_needed = len(embed_bytes) - cap
        suggestions.append(f"use a larger carrier (need at least {budget_needed:,} more bytes of capacity)")
        raw_payload_size = len(payload_bytes)
        if raw_payload_size > 256:
            compressed_est = int(raw_payload_size * 0.6)
            suggestions.append(f"compress your payload first (e.g. zip — was {raw_payload_size:,} bytes, ~{compressed_est:,} compressed)")
        raise CapacityError(
            f"Encrypted payload too large: {len(embed_bytes):,} bytes, "
            f"method '{method}' capacity at depth={depth}: {cap:,} bytes.\n"
            f"  Needed: {len(embed_bytes):,} B  |  Available: {cap:,} B  |  Gap: {len(embed_bytes)-cap:,} B\n"
            f"  Suggestions:\n" + "\n".join(f"    • {s}" for s in suggestions)
        )

    stego_bytes = encoder.encode(carrier_bytes, embed_bytes, **kwargs)
    if progress_callback is not None:
        try:
            progress_callback(100, 100)
        except Exception as exc:
            log.debug("progress_callback failed: %s", exc)

    # Save output
    out_path = get_output_path(carrier, output, encoder=encoder)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(stego_bytes)
    produced_suffix = encoder.output_suffix(carrier_path.suffix).lower()

    result = {
        "status": "success",
        "method": method,
        "carrier": str(carrier_path),
        "payload_size": len(payload_bytes),
        "encrypted_size": len(embed_bytes),
        "capacity": cap,
        "output": str(out_path),
        "depth": depth,
        "decoy_mode": bool(decoy and decoy_key),
        "wet_paper": wet_paper,
        "preserve_fingerprint": preserve_fingerprint,
    }

    if output and out_path.suffix.lower() != produced_suffix:
        result["warnings"] = [
            f"{out_path.name} holds {produced_suffix} data; its extension does not match "
            f"(use a {produced_suffix} name so other tools open it correctly)"
        ]

    if profile:
        result["target_profile"] = {
            "platform": profile.name,
            "notes": profile.notes,
            "requires_wet_paper": profile.requires_wet_paper,
        }
    if resized_from and resized_to and resized_from != resized_to:
        result["resized"] = {"from": resized_from, "to": resized_to}

    if test_survival and profile:
        from detect.survival import simulate_platform_pipeline
        from core.crypto import decoy as decoy_mod
        from core.image.wetpaper import decode_wet_paper, is_wet_paper_blob

        sim_bytes, sim_meta = simulate_platform_pipeline(stego_bytes, out_path.name, profile)
        survived = False
        corrected = 0
        sim_error = None
        try:
            sim_raw = encoder.decode(sim_bytes, **kwargs)
            if wet_paper or is_wet_paper_blob(sim_raw):
                sim_raw, corrected, _ = decode_wet_paper(sim_raw)
            if not key:
                # Keyless survival: compare raw extracted bytes to embedded bytes.
                survived = sim_raw == embed_bytes
                if not survived:
                    sim_error = "Keyless survival check: extracted bytes differ after simulation"
            else:
                decoy_mod.decrypt_container(sim_raw, key, bind)
                survived = True
        except ValueError as exc:
            sim_error = str(exc)

        result["survival_test"] = {
            "target": profile.name,
            "survived": survived,
            "corrected_bits": corrected,
            "simulation": sim_meta,
            "error": sim_error,
        }

    _scrub_secret(key)
    _scrub_secret(decoy_key)
    return result


