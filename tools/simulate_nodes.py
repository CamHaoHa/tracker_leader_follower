#!/usr/bin/env python3
"""Two virtual ESP32s using real UDP sockets; no external packages required.

Run alongside the normal hardware mode of the application, on the same computer.
This is an ideal single-reflector model, not a simulation of human reflections.
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
COMMAND = re.compile(rb"WM1 MEASURE ([0-9]+) ([0-9]+)\r?\n?")


def parse_command(packet):
    """Match the firmware's integer-only, bounded command syntax."""
    if len(packet) >= 96:
        return None
    match = COMMAND.fullmatch(packet)
    if match is None:
        return None
    seq, angle = map(int, match.groups())
    if not 1 <= seq <= MAX_SEQUENCE or not 0 <= angle <= 180000:
        return None
    return seq, angle


@dataclass
class Pending:
    sequence: int
    angle: int
    address: tuple
    ready_at: float
    response: bytes | None = None


@dataclass
class Node:
    node_id: int
    sock: socket.socket
    angle: int = 90000
    pending: Pending | None = None
    latest_sequence: int | None = None
    last_command: float = float("-inf")
    last_ping: float = float("-inf")
    cache: OrderedDict = field(default_factory=OrderedDict)


class Simulator:
    def __init__(self, x=0.75, y=1.3, empty=False, drop_node=None):
        self.target = None if empty else (x, y)
        self.drop_node = drop_node
        self.selector = selectors.DefaultSelector()
        self.nodes = []
        self.running = True
        self.next_hello = 0.0
        self.last_ping = None
        self.pings = [0, 0]
        self.min_ping_gap = None
        self.overlapping_commands = 0
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

    def receive(self, node, now):
        for _ in range(16):
            try:
                packet, address = node.sock.recvfrom(129)
            except BlockingIOError:
                break
            if node.node_id == self.drop_node or address[1] != HOST[1]:
                continue
            command = parse_command(packet)
            if command is None:
                self.malformed_commands += 1
                continue
            seq, angle = command
            if node.pending is None and now - node.last_command >= 30:
                node.latest_sequence = None
                node.cache.clear()
            if seq in node.cache:
                old_angle, response = node.cache[seq]
                if angle == old_angle:
                    node.sock.sendto(response, address)
                continue
            if node.pending is not None:
                continue
            if node.latest_sequence is not None:
                delta = (seq - node.latest_sequence) & MAX_SEQUENCE
                if not 0 < delta < 0x80000000:
                    continue
            if any(other.pending is not None for other in self.nodes):
                self.overlapping_commands += 1
            delay = min(0.7, 0.06 + abs(angle - node.angle) / 1000 * 0.003)
            ready_at = max(now + delay, node.last_ping + 0.065)
            node.pending = Pending(seq, angle, address, ready_at)
            node.angle = angle
            node.latest_sequence = seq
            node.last_command = now

    def start_ping(self, node, request, now):
        self.pings[node.node_id] += 1
        node.last_ping = now
        if self.last_ping is not None:
            gap = now - self.last_ping
            self.min_ping_gap = gap if self.min_ping_gap is None else min(self.min_ping_gap, gap)
        self.last_ping = now
        distance, status = 0, "TIMEOUT"
        if self.target is not None:
            sensor = (1.5 * node.node_id, 0.2)
            bearing = math.degrees(math.atan2(self.target[1] - sensor[1], self.target[0] - sensor[0]))
            raw_distance = round(math.dist(sensor, self.target) * 1000)
            if abs(bearing - request.angle / 1000) <= 20 and 20 <= raw_distance <= 4000:
                distance, status = raw_distance, "OK"
        request.response = (
            f"WM1 RANGE {node.node_id} {request.sequence} {request.angle} {distance} {status}"
        ).encode("ascii")
        request.ready_at = now + (distance * 2 / 343000 if status == "OK" else 0.025)

    def tick(self, now):
        if now >= self.next_hello:
            self.next_hello = now + 2
            for node in self.nodes:
                if node.node_id != self.drop_node:
                    node.sock.sendto(f"WM1 HELLO {node.node_id}".encode("ascii"), HOST)
        for node in self.nodes:
            request = node.pending
            if request is None or now < request.ready_at:
                continue
            if request.response is None:
                self.start_ping(node, request, now)
            else:
                node.sock.sendto(request.response, request.address)
                node.cache[request.sequence] = (request.angle, request.response)
                while len(node.cache) > 16:
                    node.cache.popitem(last=False)
                node.pending = None

    def run(self, seconds):
        deadline = time.monotonic() + seconds
        print(json.dumps({"event": "ready", "nodes": ["127.0.0.2:4211", "127.0.0.3:4211"],
                          "target": self.target, "drop_node": self.drop_node}), flush=True)
        while self.running and time.monotonic() < deadline:
            now = time.monotonic()
            self.tick(now)
            deadlines = [deadline, self.next_hello] + [
                node.pending.ready_at for node in self.nodes if node.pending is not None
            ]
            timeout = max(0, min(0.05, min(deadlines) - time.monotonic()))
            for key, _ in self.selector.select(timeout):
                self.receive(key.data, time.monotonic())
        print(json.dumps({"event": "summary", "pings": self.pings,
                          "overlapping_commands": self.overlapping_commands,
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
    parser.add_argument("--drop-node", type=int, choices=(0, 1), help="Suppress one node's HELLO and replies")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        simulator = Simulator(args.x, args.y, args.empty, args.drop_node)
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
