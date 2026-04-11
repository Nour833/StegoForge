"""
core/network/timing.py - Inter-packet timing covert channel abstraction.
"""
from __future__ import annotations

import os
import struct
import time

from core.base import BaseEncoder

MAGIC = b"SFTM"
HEADER_FMT = ">4sHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def require_privileges():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise ValueError(
            "timing-covert requires elevated privileges on most systems for controlled packet capture/send"
        )


def _scapy():
    try:
        from scapy.all import IP, TCP, Raw, send, sniff  # type: ignore

        return IP, TCP, Raw, send, sniff
    except Exception as exc:
        raise ValueError("timing-covert operational mode requires scapy. Install with: pip install scapy") from exc


class TimingCovertEncoder(BaseEncoder):
    name = "timing-covert"
    supported_extensions = []

    def capacity(self, carrier_bytes: bytes = b"", **kwargs) -> int:
        return 2_000_000

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, timing_delta: int = 50, **kwargs) -> bytes:
        require_privileges()
        if timing_delta <= 0:
            raise ValueError("timing-delta must be > 0 milliseconds")

        trace_blob = struct.pack(HEADER_FMT, MAGIC, int(timing_delta), len(payload_bytes)) + payload_bytes

        target_ip = kwargs.get("target_ip")
        target_port = kwargs.get("target_port")
        if not target_ip or not target_port:
            return trace_blob

        IP, TCP, Raw, send, _ = _scapy()
        sport = int(kwargs.get("listen_port") or 42424)
        base_delay = float(kwargs.get("base_delay_ms", 8.0)) / 1000.0
        one_delay = base_delay + (float(timing_delta) / 1000.0)

        framed = struct.pack(">I", len(payload_bytes)) + payload_bytes
        bits = []
        for byte in framed:
            for bit in range(7, -1, -1):
                bits.append((byte >> bit) & 1)

        # Initial synchronization packet; each following inter-packet gap carries one bit.
        base_pkt = IP(dst=str(target_ip)) / TCP(sport=sport, dport=int(target_port), flags="PA") / Raw(load=b"SFTM")
        send(base_pkt, verbose=False)
        for bit in bits:
            time.sleep(one_delay if bit else base_delay)
            send(base_pkt, verbose=False)

        return trace_blob

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        require_privileges()

        # Artifact mode decode.
        if stego_bytes.startswith(MAGIC):
            if len(stego_bytes) < HEADER_SIZE:
                raise ValueError("No timing covert payload found")
            magic, _, length = struct.unpack(HEADER_FMT, stego_bytes[:HEADER_SIZE])
            if magic != MAGIC:
                raise ValueError("Invalid timing covert payload format")
            payload = stego_bytes[HEADER_SIZE:HEADER_SIZE + length]
            if len(payload) < length:
                raise ValueError("Incomplete timing covert payload")
            return payload

        listen_ip = kwargs.get("listen_ip")
        listen_port = kwargs.get("listen_port")
        timeout = int(kwargs.get("timeout", 14))
        threshold_ms = float(kwargs.get("threshold_ms", kwargs.get("timing_delta", 50)))
        expected_packets = int(kwargs.get("expected_packets", 0))

        if not listen_ip or not listen_port:
            raise ValueError("No timing covert payload found")

        _, _, _, _, sniff = _scapy()
        filt = f"tcp and dst host {listen_ip} and dst port {int(listen_port)}"
        packets = sniff(filter=filt, timeout=timeout, count=(expected_packets if expected_packets > 0 else 0))
        if len(packets) < 2:
            raise ValueError("Not enough packets captured for timing decode")

        bits = []
        prev_t = float(packets[0].time)
        for pkt in packets[1:]:
            t = float(pkt.time)
            delta_ms = (t - prev_t) * 1000.0
            bits.append(1 if delta_ms >= threshold_ms else 0)
            prev_t = t

        out = bytearray()
        for i in range(0, len(bits) // 8 * 8, 8):
            val = 0
            for b in bits[i:i + 8]:
                val = (val << 1) | b
            out.append(val)

        if len(out) < 4:
            raise ValueError("Decoded stream too short")

        length = struct.unpack(">I", bytes(out[:4]))[0]
        payload = bytes(out[4:4 + length])
        if len(payload) < length:
            raise ValueError("Incomplete timing covert payload")
        return payload
