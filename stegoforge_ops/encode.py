"""stegoforge_ops.encode — typed encode request boundary."""
from __future__ import annotations

from dataclasses import dataclass

from core.bits import validate_depth
from core.errors import EmptyPayloadError


@dataclass
class EncodeRequest:
    """Typed boundary for op_encode arguments."""

    carrier: str
    payload: str
    key: str | None
    method: str | None
    depth: int
    allow_plaintext: bool = False
    pad_block: int = 0
    require_v2: bool = False
    enforce_strong: bool = False
    header_mode: str = "standard"
    i_understand_root: bool = False
    progress_callback: object = None

    def validate(self) -> EncodeRequest:
        self.depth = validate_depth(int(self.depth))
        if self.pad_block and not (1 <= int(self.pad_block) <= 256):
            raise ValueError("pad_block must be 0 or 1-256")
        self.pad_block = int(self.pad_block or 0)
        if self.header_mode not in ("standard", "obfuscated"):
            raise ValueError("header_mode must be 'standard' or 'obfuscated'")
        return self


def check_payload_nonempty(data: bytes) -> None:
    """Raise typed error for zero-length payloads."""
    if len(data) == 0:
        raise EmptyPayloadError("Payload file is empty — refusing to embed zero-length payload")
