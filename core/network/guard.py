"""core/network/guard.py — privilege and input validation for covert network channels."""
from __future__ import annotations

import ipaddress
import os

from core.config import env_flag


def is_root() -> bool:
    """True when running with the privileges raw sockets need (always True where unknowable)."""
    return not hasattr(os, "geteuid") or os.geteuid() == 0


def require_root(feature: str) -> None:
    """Raise unless the process can open raw sockets (live send / sniff only)."""
    if not is_root():
        raise ValueError(f"{feature} requires root/administrator privileges for live packet send/capture")


def validate_ip(value: str | None, label: str = "ip") -> str:
    try:
        return str(ipaddress.ip_address(str(value)))
    except ValueError:
        raise ValueError(f"Invalid {label}: {value!r}") from None


def validate_port(value: int | str | None, label: str = "port") -> int:
    try:
        port = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {label}: {value!r}") from None
    if not 0 < port < 65536:
        raise ValueError(f"Invalid {label}: {value!r}")
    return port


def validate_listen_target(listen_ip: str | None, listen_port: int | None) -> tuple[str, int]:
    """Validate BPF filter inputs; raises ValueError on a bad IP/port."""
    if not listen_ip or listen_port is None:
        raise ValueError("Network decode requires --listen-ip and --listen-port")
    return validate_ip(listen_ip, "listen-ip"), validate_port(listen_port, "listen-port")


def require_explicit_root_ack(ack: bool | None) -> None:
    """Live covert ops need root AND an explicit operator acknowledgement."""
    require_root("Live covert network operation")
    if ack or env_flag("STEGOFORGE_I_UNDERSTAND_ROOT"):
        return
    raise ValueError(
        "Live network covert ops require --i-understand-root "
        "(you must own the systems or be explicitly authorized)."
    )


def bpf_filter(listen_ip: str, listen_port: int) -> str:
    """Build the BPF filter string (inputs must already be validated)."""
    return f"tcp and dst host {listen_ip} and dst port {int(listen_port)}"
