"""
core/network/tcp.py - Packet-field covert channel abstraction.

This module enforces privilege checks and provides a deterministic packet-trace
artifact format for encode/decode workflows.
"""
from __future__ import annotations

import os
import random
import struct
import time

from core.base import BaseEncoder

MAGIC = b"SFTC"
HEADER_FMT = ">4sBHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
CHANNELS = {"ip_id": 1, "tcp_seq": 2, "ttl": 3}
INV_CHANNELS = {v: k for k, v in CHANNELS.items()}


def require_privileges():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise ValueError(
            "tcp-covert requires root/administrator privileges for raw packet operations"
        )


def _scapy():
    try:
        from scapy.all import IP, TCP, Raw, send, sniff  # type: ignore

        return IP, TCP, Raw, send, sniff
    except Exception as exc:
        raise ValueError("tcp-covert operational mode requires scapy. Install with: pip install scapy") from exc


class TCPCovertEncoder(BaseEncoder):
    name = "tcp-covert"
    supported_extensions = []

    def capacity(self, carrier_bytes: bytes = b"", **kwargs) -> int:
        return 2_000_000

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, channel: str = "ip_id", **kwargs) -> bytes:
        require_privileges()
        if channel not in CHANNELS:
            raise ValueError("channel must be one of: ip_id, tcp_seq, ttl")

        trace_blob = struct.pack(HEADER_FMT, MAGIC, CHANNELS[channel], 0, len(payload_bytes)) + payload_bytes

        target_ip = kwargs.get("target_ip")
        target_port = kwargs.get("target_port")
        if not target_ip or not target_port:
            # Artifact mode remains available for reproducible decode/tests.
            return trace_blob

        IP, TCP, Raw, send, _ = _scapy()
        listen_port = int(kwargs.get("listen_port") or random.randint(20000, 50000))

        framed = struct.pack(">I", len(payload_bytes)) + payload_bytes
        for idx, b in enumerate(framed):
            ip = IP(dst=str(target_ip))
            tcp = TCP(sport=listen_port, dport=int(target_port), flags="PA", seq=random.randint(0, 2**31 - 1))

            if channel == "ip_id":
                ip.id = (0x1200 | int(b))
            elif channel == "tcp_seq":
                tcp.seq = (0xABCD0000 | int(b))
            else:  # ttl
                ip.ttl = max(1, min(255, int(b)))

            pkt = ip / tcp / Raw(load=b"SF" + bytes([idx & 0xFF]))
            send(pkt, verbose=False)
            time.sleep(0.003)

        return trace_blob

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        require_privileges()

        # Artifact mode decode.
        if len(stego_bytes) < HEADER_SIZE:
            stego_bytes = b""

        if stego_bytes.startswith(MAGIC):
            magic, channel_id, _, length = struct.unpack(HEADER_FMT, stego_bytes[:HEADER_SIZE])
            if magic != MAGIC or channel_id not in INV_CHANNELS:
                raise ValueError("Invalid TCP covert payload format")
            payload = stego_bytes[HEADER_SIZE:HEADER_SIZE + length]
            if len(payload) < length:
                raise ValueError("Incomplete TCP covert payload")
            return payload

        listen_ip = kwargs.get("listen_ip")
        listen_port = kwargs.get("listen_port")
        channel = kwargs.get("channel") or "ip_id"
        timeout = int(kwargs.get("timeout", 12))
        expected_packets = int(kwargs.get("expected_packets", 0))

        if not listen_ip or not listen_port:
            raise ValueError("No TCP covert payload found")
        if channel not in CHANNELS:
            raise ValueError("channel must be one of: ip_id, tcp_seq, ttl")

        _, _, _, _, sniff = _scapy()
        filt = f"tcp and dst host {listen_ip} and dst port {int(listen_port)}"
        packets = sniff(filter=filt, timeout=timeout, count=(expected_packets if expected_packets > 0 else 0))
        if not packets:
            raise ValueError("No covert packets captured")

        data = bytearray()
        for pkt in packets:
            if not hasattr(pkt, "payload"):
                continue
            if channel == "ip_id":
                data.append(int(pkt[0].id) & 0xFF)
            elif channel == "tcp_seq":
                data.append(int(pkt[1].seq) & 0xFF)
            else:
                data.append(int(pkt[0].ttl) & 0xFF)

        if len(data) < 4:
            raise ValueError("Captured packet stream too short")

        length = struct.unpack(">I", bytes(data[:4]))[0]
        payload = bytes(data[4:4 + length])
        if len(payload) < length:
            raise ValueError("Incomplete TCP covert payload")
        return payload
