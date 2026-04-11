"""
core/document/linguistic.py - Lexical choice steganography.

Tier A (default): synonym substitution in provided cover text.
Tier B: optional LLM-assisted generation hook (best-effort local/compatible API).
"""
from __future__ import annotations

import json
import re
import struct
import urllib.request

from core.base import BaseEncoder

HEADER_FMT = ">I"
HEADER_SIZE = 4
WORD_RE = re.compile(r"\w+|\W+", re.UNICODE)


# 64+ synonym pairs; left token encodes 0, right token encodes 1.
SYNONYM_PAIRS = [
    ("quick", "fast"), ("small", "tiny"), ("big", "large"), ("smart", "clever"),
    ("begin", "start"), ("end", "finish"), ("buy", "purchase"), ("ask", "inquire"),
    ("help", "assist"), ("hard", "tough"), ("easy", "simple"), ("calm", "quiet"),
    ("loud", "noisy"), ("happy", "glad"), ("sad", "unhappy"), ("error", "mistake"),
    ("job", "task"), ("safe", "secure"), ("show", "display"), ("hide", "conceal"),
    ("near", "close"), ("far", "distant"), ("old", "ancient"), ("new", "modern"),
    ("build", "construct"), ("fix", "repair"), ("plan", "design"), ("test", "check"),
    ("look", "watch"), ("think", "consider"), ("talk", "speak"), ("tell", "inform"),
    ("use", "utilize"), ("keep", "retain"), ("send", "dispatch"), ("receive", "obtain"),
    ("open", "unlock"), ("close", "shut"), ("clear", "plain"), ("brief", "short"),
    ("strong", "robust"), ("weak", "fragile"), ("true", "valid"), ("false", "invalid"),
    ("story", "narrative"), ("idea", "concept"), ("result", "outcome"), ("risk", "hazard"),
    ("trust", "rely"), ("care", "concern"), ("watch", "observe"), ("note", "remark"),
    ("plain", "simple"), ("rapid", "swift"), ("solid", "firm"), ("value", "worth"),
    ("light", "bright"), ("dark", "dim"), ("legal", "lawful"), ("moral", "ethical"),
    ("choice", "option"), ("route", "path"), ("merge", "combine"), ("split", "divide"),
]

BIT_FOR = {}
for a, b in SYNONYM_PAIRS:
    BIT_FOR[a] = 0
    BIT_FOR[b] = 1

PAIR_BY_TOKEN = {}
for a, b in SYNONYM_PAIRS:
    PAIR_BY_TOKEN[a] = (a, b)
    PAIR_BY_TOKEN[b] = (a, b)


class LinguisticEncoder(BaseEncoder):
    name = "linguistic"
    supported_extensions = [".txt"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        text = carrier_bytes.decode("utf-8", errors="replace")
        eligible = self._eligible_positions(text)
        return max(0, (len(eligible) // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, topic: str | None = None, llm_model: str | None = None, **kwargs) -> bytes:
        cover = carrier_bytes.decode("utf-8", errors="replace")
        if topic and llm_model:
            cover = self._generate_cover_with_llm(topic, llm_model, cover)

        cap = self.capacity(cover.encode("utf-8"))
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, linguistic capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)

        tokens = WORD_RE.findall(cover)
        bit_idx = 0
        for i, tok in enumerate(tokens):
            key = tok.lower()
            if key in PAIR_BY_TOKEN and bit_idx < len(bits):
                zero, one = PAIR_BY_TOKEN[key]
                target = zero if bits[bit_idx] == 0 else one
                tokens[i] = _match_case(tok, target)
                bit_idx += 1

        if bit_idx < len(bits):
            raise ValueError("Cover text does not contain enough eligible synonym tokens")

        return "".join(tokens).encode("utf-8")

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        text = stego_bytes.decode("utf-8", errors="replace")
        bits = []
        for tok in WORD_RE.findall(text):
            key = tok.lower()
            if key in BIT_FOR:
                bits.append(BIT_FOR[key])

        if len(bits) < HEADER_SIZE * 8:
            raise ValueError("No linguistic payload header found")

        length = struct.unpack(HEADER_FMT, _bits_to_bytes(bits[:HEADER_SIZE * 8]))[0]
        if length <= 0 or length > 10_000_000:
            raise ValueError(f"Invalid linguistic payload length: {length}")

        total_bits = (HEADER_SIZE + length) * 8
        if len(bits) < total_bits:
            raise ValueError("Incomplete linguistic payload")

        return _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])

    def _eligible_positions(self, text: str) -> list[int]:
        toks = WORD_RE.findall(text)
        return [i for i, tok in enumerate(toks) if tok.lower() in PAIR_BY_TOKEN]

    def _generate_cover_with_llm(self, topic: str, llm_model: str, fallback_cover: str) -> str:
        # Optional best-effort hook for OpenAI-compatible local endpoint.
        endpoint = None
        model = llm_model
        if ":" in llm_model and llm_model.startswith("http"):
            endpoint, model = llm_model.rsplit(":", 1)
        if not endpoint:
            return fallback_cover

        prompt = (
            "Write a natural paragraph on this topic: "
            f"{topic}. Include common synonyms and plain language."
        )
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }

        try:
            req = urllib.request.Request(
                endpoint.rstrip("/") + "/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return fallback_cover


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original.istitle():
        return replacement.title()
    return replacement


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = []
    for i in range(0, len(bits) - 7, 8):
        val = 0
        for b in bits[i:i + 8]:
            val = (val << 1) | b
        out.append(val)
    return bytes(out)
