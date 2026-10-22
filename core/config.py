"""core/config.py — central runtime configuration for StegoForge.

Every tunable limit lives here and can be overridden from the environment.
``get_config()`` re-reads the environment on each call, so tests and long
running processes (the web UI) always see current values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

_FALSE = ("", "0", "false", "no", "off")


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable (``0/false/no/off`` and unset are False)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class StegoConfig:
    """Runtime limits and switches."""

    max_upload_bytes: int = field(default_factory=lambda: _env_int("STEGOFORGE_MAX_BYTES", 200 * 1024 * 1024))
    max_image_pixels: int = field(default_factory=lambda: _env_int("STEGOFORGE_MAX_PIXELS", 120_000_000))
    max_keyed_samples: int = field(default_factory=lambda: _env_int("STEGOFORGE_MAX_KEYED_SAMPLES", 128_000_000))
    deadrop_max_bytes: int = field(default_factory=lambda: _env_int("STEGOFORGE_DEADDROP_MAX_BYTES", 64 * 1024 * 1024))
    decomp_max_bytes: int = field(default_factory=lambda: _env_int("STEGOFORGE_DECOMP_MAX_BYTES", 64 * 1024 * 1024))
    zip_max_entries: int = field(default_factory=lambda: _env_int("STEGOFORGE_ZIP_MAX_ENTRIES", 4096))
    zip_max_total_bytes: int = field(default_factory=lambda: _env_int("STEGOFORGE_ZIP_MAX_BYTES", 256 * 1024 * 1024))
    fetch_timeout: int = field(default_factory=lambda: _env_int("STEGOFORGE_FETCH_TIMEOUT", 20))
    web_token: str = field(default_factory=lambda: os.getenv("STEGOFORGE_WEB_TOKEN", ""))
    allow_plaintext_env: bool = field(default_factory=lambda: env_flag("STEGOFORGE_ALLOW_PLAINTEXT"))
    offline: bool = field(default_factory=lambda: env_flag("STEGOFORGE_OFFLINE"))


def get_config() -> StegoConfig:
    """Return the current configuration (environment re-read on every call)."""
    return StegoConfig()
