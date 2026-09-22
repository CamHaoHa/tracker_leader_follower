"""Versioned, bounded ASCII datagrams shared with the ESP32 firmware.

WM2 separates servo aiming from ultrasonic firing so both servos may move at
once while the host keeps the two acoustic measurement windows separate.
"""

from dataclasses import dataclass
import re

MAX_PACKET = 128
MAX_SEQUENCE = 0xFFFFFFFF
MAX_READY_LEASE_MS = 1000


@dataclass(frozen=True)
class Hello:
    node: int
    version: int = 1


@dataclass(frozen=True)
class Range:
    node: int
    seq: int
    angle_mdeg: int
    distance_mm: int
    status: str
    sample_ms: int | None = None
    age_us: int = 0
    version: int = 1


@dataclass(frozen=True)
class Ready:
    node: int
    seq: int
    angle_mdeg: int
    lease_ms: int
    status: str


def _command_bounds(seq, angle_mdeg=None):
    if type(seq) is not int or not 1 <= seq <= MAX_SEQUENCE:
        raise ValueError("Sequence out of bounds")
    if angle_mdeg is not None and (type(angle_mdeg) is not int or not 0 <= angle_mdeg <= 180000):
        raise ValueError("Angle out of bounds")


def parse(data: bytes) -> Hello | Range | Ready:
    if len(data) > MAX_PACKET:
        raise ValueError("Oversized datagram")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Non-ASCII datagram") from exc
    hello = re.fullmatch(r"WM([12]) HELLO ([01])\n?", text)
    if hello:
        return Hello(int(hello[2]), int(hello[1]))
    ready = re.fullmatch(
        r"WM2 READY ([01]) ([0-9]{1,10}) ([0-9]{1,6}) ([0-9]{1,4}) (OK|INVALID)\n?", text
    )
    if ready:
        node, seq, angle, lease = map(int, ready.groups()[:4])
        _command_bounds(seq, angle)
        status = ready[5]
        if (status == "OK" and not 1 <= lease <= MAX_READY_LEASE_MS) or (status == "INVALID" and lease != 0):
            raise ValueError("Invalid ready lease/status combination")
        return Ready(node, seq, angle, lease, status)
    match = re.fullmatch(
        r"WM([12]) RANGE ([01]) ([0-9]{1,10}) ([0-9]{1,6}) ([0-9]{1,4}) (OK|TIMEOUT|INVALID)"
        r"(?: ([0-9]{1,10}) ([0-9]{1,10}))?\n?", text
    )
    if not match:
        raise ValueError("Malformed datagram")
    version, node, seq, angle, distance = map(int, match.groups()[:5])
    status = match[6]
    _command_bounds(seq, angle)
    if (status == "OK" and not 20 <= distance <= 4500) or (status != "OK" and distance != 0):
        raise ValueError("Invalid range/status combination")
    if (version == 2) != (match[7] is not None):
        raise ValueError("Range timestamp fields do not match protocol version")
    sample_ms = int(match[7]) if version == 2 else None
    age_us = int(match[8]) if version == 2 else 0
    if sample_ms is not None and (sample_ms > MAX_SEQUENCE or age_us > MAX_SEQUENCE):
        raise ValueError("Range timestamp out of bounds")
    return Range(node, seq, angle, distance, status, sample_ms, age_us, version)


def measure(seq: int, angle_mdeg: int) -> bytes:
    """Legacy WM1 command, kept for diagnostics and older consumers."""
    _command_bounds(seq, angle_mdeg)
    return f"WM1 MEASURE {seq} {angle_mdeg}".encode("ascii")


def aim(seq: int, angle_mdeg: int) -> bytes:
    _command_bounds(seq, angle_mdeg)
    return f"WM2 AIM {seq} {angle_mdeg}".encode("ascii")


def fire(seq: int) -> bytes:
    _command_bounds(seq)
    return f"WM2 FIRE {seq}".encode("ascii")
