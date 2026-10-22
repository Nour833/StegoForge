"""stegoforge_ops/report.py — canonical forensic report format + hash chain.

report_version=1 reports gain a deterministic canonical form (sorted keys,
compact separators) so hashes are stable across runs and machines.
chain_hash links reports into an audit chain: each entry commits to the
previous entry's hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(report: dict[str, Any]) -> str:
    """Deterministic JSON encoding (sorted keys, compact, UTF-8)."""
    return json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def report_hash(report: dict[str, Any]) -> str:
    """SHA256 of the canonical report encoding."""
    return hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()


def chain_hash(prev_hash: str, report: dict[str, Any]) -> str:
    """Hash chaining for audit trails: H(prev_hash || canonical(report))."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"|")
    h.update(canonical_json(report).encode("utf-8"))
    return h.hexdigest()


GENESIS_HASH = "0" * 64
