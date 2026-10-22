"""core/errors.py — typed error hierarchy for StegoForge.

Replaces ad-hoc ValueError/IOError strings with structured codes that map
to docs/ERRORS.md and stable --json messages.
"""
from __future__ import annotations


class StegoForgeError(ValueError):
    """Base error with a stable machine-readable code."""

    code = "stegoforge-error"


class DepthError(StegoForgeError):
    code = "bad-depth"


class EmptyPayloadError(StegoForgeError):
    code = "empty-payload"


class PlaintextRefusedError(StegoForgeError):
    code = "plaintext-refused"


class CapacityError(StegoForgeError):
    code = "capacity-exceeded"


class CorruptedCarrierError(StegoForgeError):
    code = "corrupted-carrier"


class DecryptionError(StegoForgeError):
    code = "decryption-failed"


class DetectorMismatchError(StegoForgeError):
    code = "detector-mismatch"


class NetworkValidationError(StegoForgeError):
    code = "bad-network-args"


class WeakPassphraseError(StegoForgeError):
    code = "weak-passphrase"
