#!/usr/bin/env python3
"""Two independent WM2 ESP32 models using real loopback UDP sockets.

Run alongside the application in hardware mode. Servos aim concurrently; only a
valid, unexpired FIRE grant causes a ping. This is an ideal reflector model,
not a simulation of the echoes from a moving person's body.
"""

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
import json
import math
import re
import selectors
import signal
import socket
import time

HOST = ("127.0.0.1", 4210)
NODE_PORT = 4211
MAX_SEQUENCE = 0xFFFFFFFF
AIM_COMMAND = re.compile(rb"WM2 AIM ([0-9]{1,10}) ([0-9]{1,6})\r?\n?")
FIRE_COMMAND = re.compile(rb"WM2 FIRE ([0-9]{1,10})\r?\n?")


def parse_command(packet):
    """Match the firmware's integer-only, bounded command syntax."""
    if len(packet) >= 96:
        return None
    if packet in (b"WM2 DISCOVER", b"WM2 DISCOVER\n", b"WM2 DISCOVER\r\n"):
        return "DISCOVER", None, None
    match = AIM_COMMAND.fullmatch(packet)
    if match:
        seq, angle = map(int, match.groups())
        if 1 <= seq <= MAX_SEQUENCE and 0 <= angle <= 180000:
            return "AIM", seq, angle
    match = FIRE_COMMAND.fullmatch(packet)
    if match:
        seq = int(match[1])
        if 1 <= seq <= MAX_SEQUENCE:
            return "FIRE", seq, None
    return None


@dataclass
class Aim:
    sequence: int
    angle: int
    address: tuple
    settled_at: float
    expires_at: float | None = None
    fired: bool = False


@dataclass
class Echo:
    sequence: int
    angle: int
    address: tuple
    trigger_at: float
    done_at: float
    distance: int
    status: str


@dataclass
class Node:
    node_id: int
    sock: socket.socket
    angle: int = 90000
    aim: Aim | None = None
    echo: Echo | None = None
    latest_sequence: int | None = None
    last_command: float = float("-inf")
    last_ping: float = float("-inf")
    cache: OrderedDict = field(default_factory=OrderedDict)


class Simulator:
    def __init__(self, x=0.75, y=1.3, empty=False, drop_node=None, motion=False, no_broadcast=False):
        self.target = None if empty else (x, y)
        self.motion, self.started = motion, time.monotonic()
        self.drop_node, self.no_broadcast = drop_node, no_broadcast
        self.selector = selectors.DefaultSelector()
        self.nodes = []
        self.running = True
        self.next_hello = 0.0
        self.last_ping = None
        self.pings = [0, 0]
        self.min_ping_gap = None
        self.overlapping_commands = 0  # Concurrent AIM operations are intentional.
        self.overlapping_pings = 0
        self.malformed_commands = 0
        try:
            for node_id in (0, 1):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                node = Node(node_id, sock)
                self.nodes.append(node)
                sock.bind((f"127.0.0.{node_id + 2}", NODE_PORT))
                sock.setblocking(False)
                self.selector.register(sock, selectors.EVENT_READ, node)
        except Exception:
            self.close()
            raise

    def close(self):
        self.selector.close()
        for node in self.nodes:
            node.sock.close()

    def stop(self, *_):
        self.running = False

    def target_at(self, now):
        if self.target is None or not self.motion:
            return self.target
        elapsed = now - self.started
        return (self.target[0] + 0.35 * math.sin(elapsed * 1.2),
                self.target[1] + 0.15 * math.sin(elapsed * 0.7))

    def send_ready(self, node, request, now):
        remaining = max(0, math.floor((request.expires_at - now) * 1000 + 1e-6))
        lease = remaining if not request.fired else 0
        status = "OK" if lease else "INVALID"
        node.sock.sendto(
            f"WM2 READY {node.node_id} {request.sequence} {request.angle} {lease} {status}".encode(),
            request.address,
        )

    def remember(self, node, seq, angle, response):
        node.cache[seq] = (angle, response)
        while len(node.cache) > 16:
            node.cache.popitem(last=False)

    def invalid_fire(self, node, seq, address, now):
        response = f"WM2 RANGE {node.node_id} {seq} {node.angle} 0 INVALID 0 0".encode()
        newer = node.latest_sequence is None or 0 < ((seq - node.latest_sequence) & MAX_SEQUENCE) < 0x80000000
        if newer or (node.aim and node.aim.sequence == seq):
            self.remember(node, seq, node.angle, response)
            node.latest_sequence, node.last_command = seq, now
            if node.aim:
                node.aim.fired = True
                node.aim.expires_at = now
        node.sock.sendto(response, address)

    def receive(self, node, now):
        for _ in range(16):
            try:
                packet, address = node.sock.recvfrom(129)
            except BlockingIOError:
                break
            if node.node_id == self.drop_node:
                continue
            command = parse_command(packet)
            if command is None:
                self.malformed_commands += 1
                continue
            kind, seq, angle = command
            if kind == "DISCOVER":
                node.sock.sendto(f"WM2 HELLO {node.node_id}".encode(), address)
                continue
            if address[1] != HOST[1]:
                continue
            if now - node.last_command >= 30:
                node.latest_sequence, node.aim = None, None
                node.cache.clear()
            if kind == "FIRE":
                if seq in node.cache:
                    node.last_command = now
                    node.sock.sendto(node.cache[seq][1], address)
                    continue
                if node.echo and node.echo.sequence == seq:
                    continue
                request = node.aim
                if not (request and request.sequence == seq and request.address == address
                        and not request.fired and request.expires_at is not None
                        and now < request.expires_at and now - node.last_ping >= 0.065):
                    self.invalid_fire(node, seq, address, now)
                    continue
                node.last_command = now
                request.fired = True
                self.start_ping(node, request, now)
                continue
            if node.aim and node.aim.sequence == seq:
                node.last_command = now
                if node.aim.address == address:
                    if node.aim.angle != angle:
                        node.sock.sendto(f"WM2 READY {node.node_id} {seq} {angle} 0 INVALID".encode(), address)
                    elif node.aim.expires_at is not None:
                        self.send_ready(node, node.aim, now)
                continue
            if node.echo is not None:
                continue
            if seq in node.cache:
                node.last_command = now
                node.sock.sendto(f"WM2 READY {node.node_id} {seq} {angle} 0 INVALID".encode(), address)
                continue
            if node.latest_sequence is not None:
                delta = (seq - node.latest_sequence) & MAX_SEQUENCE
                if not 0 < delta < 0x80000000:
                    node.sock.sendto(f"WM2 READY {node.node_id} {seq} {angle} 0 INVALID".encode(), address)
                    continue
            if any(other.aim and now < other.aim.settled_at for other in self.nodes if other is not node):
                self.overlapping_commands += 1
            remaining = max(0, node.aim.settled_at - now) if node.aim else 0
            movement = abs(angle - node.angle) / 1000
            delay = remaining if movement == 0 else min(0.7, 0.06 + movement * 0.003 + remaining)
            node.aim = Aim(seq, angle, address, now + delay)
            node.angle, node.latest_sequence, node.last_command = angle, seq, now

    def sample_ms(self, node, now):
        # Distinct device clocks ensure the host cannot compare board millis as
        # though they share an epoch. The age field relates samples to replies.
        return (int((now - self.started) * 1000) + node.node_id * 123456) & MAX_SEQUENCE

    def start_ping(self, node, request, now):
        if any(other.echo and now < other.echo.done_at for other in self.nodes if other is not node):
            self.overlapping_pings += 1
        self.pings[node.node_id] += 1
        node.last_ping = now
        if self.last_ping is not None:
            gap = now - self.last_ping
            self.min_ping_gap = gap if self.min_ping_gap is None else min(self.min_ping_gap, gap)
        self.last_ping = now
        distance, status = 0, "TIMEOUT"
        target = self.target_at(now)
        if target is not None:
            sensor = (1.5 * node.node_id, 0.2)
            bearing = math.degrees(math.atan2(target[1] - sensor[1], target[0] - sensor[0]))
            raw_distance = round(math.dist(sensor, target) * 1000)
            if abs(bearing - request.angle / 1000) <= 20 and 20 <= raw_distance <= 4000:
                distance, status = raw_distance, "OK"
        flight = distance * 2 / 343000 if status == "OK" else 0.025
        node.echo = Echo(request.sequence, request.angle, request.address, now, now + flight, distance, status)

    def tick(self, now):
        if now >= self.next_hello:
            self.next_hello = now + 2
            for node in self.nodes:
                if node.node_id != self.drop_node and not self.no_broadcast:
                    node.sock.sendto(f"WM2 HELLO {node.node_id}".encode("ascii"), HOST)
        for node in self.nodes:
            request = node.aim
            if request and request.expires_at is None and now >= request.settled_at:
                request.expires_at = now + 1.0
                self.send_ready(node, request, now)
            echo = node.echo
            if echo and now >= echo.done_at:
                age_us = max(0, round((now - echo.trigger_at) * 1_000_000))
                response = (f"WM2 RANGE {node.node_id} {echo.sequence} {echo.angle} {echo.distance} "
                            f"{echo.status} {self.sample_ms(node, echo.trigger_at)} {age_us}").encode()
                node.sock.sendto(response, echo.address)
                self.remember(node, echo.sequence, echo.angle, response)
                node.echo = None

    def run(self, seconds):
        deadline = time.monotonic() + seconds
        print(json.dumps({"event": "ready", "nodes": ["127.0.0.2:4211", "127.0.0.3:4211"],
                          "target": self.target, "motion": self.motion, "drop_node": self.drop_node}), flush=True)
        while self.running and time.monotonic() < deadline:
            now = time.monotonic()
            self.tick(now)
            deadlines = [deadline, self.next_hello]
            for node in self.nodes:
                if node.aim and node.aim.expires_at is None:
                    deadlines.append(node.aim.settled_at)
                if node.echo:
                    deadlines.append(node.echo.done_at)
            timeout = max(0, min(0.01, min(deadlines) - time.monotonic()))
            for key, _ in self.selector.select(timeout):
                self.receive(key.data, time.monotonic())
        print(json.dumps({"event": "summary", "pings": self.pings,
                          "overlapping_commands": self.overlapping_commands,
                          "overlapping_pings": self.overlapping_pings,
                          "malformed_commands": self.malformed_commands,
                          "min_ping_gap_ms": None if self.min_ping_gap is None else self.min_ping_gap * 1000}),
              flush=True)


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("Value must be finite")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x", type=finite, default=0.75, help="Reflector x position in metres")
    parser.add_argument("--y", type=finite, default=1.3, help="Reflector y position in metres")
    parser.add_argument("--seconds", type=finite, default=60, help="Run duration (default: 60)")
    parser.add_argument("--empty", action="store_true", help="Both nodes return TIMEOUT")
    parser.add_argument("--no-broadcast", action="store_true", help="Respond only to unicast discovery probes")
    parser.add_argument("--motion", action="store_true", help="Move reflector on a smooth path around x,y")
    parser.add_argument("--drop-node", type=int, choices=(0, 1), help="Suppress one node's HELLO and replies")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        simulator = Simulator(args.x, args.y, args.empty, args.drop_node, args.motion, args.no_broadcast)
    except OSError as exc:
        parser.exit(1, f"Could not bind loopback sensor sockets: {exc}\n")
    signal.signal(signal.SIGINT, simulator.stop)
    signal.signal(signal.SIGTERM, simulator.stop)
    try:
        simulator.run(args.seconds)
    finally:
        simulator.close()


if __name__ == "__main__":
    main()
