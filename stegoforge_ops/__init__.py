"""stegoforge_ops — canonical operation implementations.

`stegoforge.py` keeps CLI/Typer commands and re-exports these for backward
compatibility (`from stegoforge import op_encode` keeps working).
New code should import from here directly.
"""
from stegoforge_ops.capacity_ops import op_batch_encode, op_capacity, op_diff
from stegoforge_ops.decode_ops import op_decode
from stegoforge_ops.detect_ops import op_ctf, op_detect
from stegoforge_ops.encode import EncodeRequest, check_payload_nonempty
from stegoforge_ops.encode_ops import op_encode
from stegoforge_ops.registry import (
    ENCODE_METHODS,
    EXT_TO_METHOD,
    auto_detect_method,
    get_encoder,
)
from stegoforge_ops.report import canonical_json, chain_hash, report_hash

__all__ = [
    "EncodeRequest",
    "ENCODE_METHODS",
    "EXT_TO_METHOD",
    "auto_detect_method",
    "canonical_json",
    "chain_hash",
    "check_payload_nonempty",
    "get_encoder",
    "op_batch_encode",
    "op_capacity",
    "op_ctf",
    "op_decode",
    "op_detect",
    "op_diff",
    "op_encode",
    "report_hash",
]
