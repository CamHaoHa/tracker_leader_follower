"""Versioned, bounded ASCII datagrams shared with the ESP32 firmware."""

from dataclasses import dataclass
import re

MAX_PACKET = 128
MAX_SEQUENCE = 0xFFFFFFFF


@dataclass(frozen=True)
class Hello:
    node: int


@dataclass(frozen=True)
class Range:
    node: int
    seq: int
    angle_mdeg: int
    distance_mm: int
    status: str


def parse(data: bytes) -> Hello | Range:
    if len(data) > MAX_PACKET:
        raise ValueError("Oversized datagram")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Non-ASCII datagram") from exc
    hello = re.fullmatch(r"WM1 HELLO ([01])\n?", text)
    if hello:
        return Hello(int(hello[1]))
    match = re.fullmatch(
        r"WM1 RANGE ([01]) ([0-9]{1,10}) ([0-9]{1,6}) ([0-9]{1,4}) (OK|TIMEOUT|INVALID)\n?",
        text,
    )
    if not match:
        raise ValueError("Malformed datagram")
    node, seq, angle, distance = map(int, match.groups()[:4])
    status = match[5]
    if not 1 <= seq <= MAX_SEQUENCE or not 0 <= angle <= 180000:
        raise ValueError("Sequence or angle out of bounds")
    if (status == "OK" and not 20 <= distance <= 4500) or (status != "OK" and distance != 0):
        raise ValueError("Invalid range/status combination")
    return Range(node, seq, angle, distance, status)


def measure(seq: int, angle_mdeg: int) -> bytes:
    if not 1 <= seq <= MAX_SEQUENCE or not 0 <= angle_mdeg <= 180000:
        raise ValueError("Invalid measurement command")
    return f"WM1 MEASURE {seq} {angle_mdeg}".encode("ascii")
