"""Nonblocking UDP transport and a timed two-node simulator."""

from collections import OrderedDict
from dataclasses import dataclass
import math
import re
import socket

from .protocol import MAX_PACKET, MAX_SEQUENCE, Hello, Range, Ready, parse


class UdpTransport:
    def __init__(self, clock, port=4210, node_ips=None):
        self.clock = clock
        if node_ips:
            if len(node_ips) != 2 or node_ips[0] == node_ips[1]:
                raise ValueError("Provide distinct left and right node IP addresses")
            for ip in node_ips:
                socket.inet_aton(ip)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind(("0.0.0.0", port))
            self.socket.setblocking(False)
        except OSError:
            self.socket.close()
            raise
        self.nodes = {}
        self.conflicts = {}
        self.configured = {}
        self.versions = {}
        self.last_discovery = float("-inf")
        if node_ips:
            for node, ip in enumerate(node_ips):
                self.nodes[node] = ((ip, 4211), self.clock())
                self.configured[node] = (ip,4211)

    def receive(self):
        # Unicast discovery works on routed networks that suppress broadcast.
        # Probing is nonblocking and does not move servos or grant a ping.
        now = self.clock()
        if self.configured and now-self.last_discovery >= 1.0:
            self.last_discovery = now
            for address in self.configured.values():
                try:
                    self.socket.sendto(b"WM2 DISCOVER", address)
                except OSError:
                    pass  # Retry next second while receive remains responsive.
        messages = []
        for _ in range(64):  # Bound work per UI frame even on a noisy network.
            try:
                data, address = self.socket.recvfrom(MAX_PACKET + 1)
            except BlockingIOError:
                break
            except ConnectionResetError:  # Windows UDP ICMP from a rebooting node.
                continue
            try:
                message = parse(data)
            except ValueError:
                continue
            now = self.clock()
            if isinstance(message, Hello):
                if address[1] != 4211:
                    continue
                if message.node in self.configured and address != self.configured[message.node]:
                    continue
                existing = self.nodes.get(message.node)
                if existing and existing[0] != address and now - existing[1] < 6:
                    self.conflicts[message.node] = now
                    continue
                self.nodes[message.node] = (address, now)
                self.versions[message.node] = (address, message.version)
            else:
                messages.append((message, address))
        return messages

    def address(self, node):
        now = self.clock()
        item = self.nodes.get(node)
        if now - self.conflicts.get(node, -100) < 6:
            return None
        if node in self.configured:
            return self.configured[node]
        if not item or now - item[1] > 6:
            return None
        return item[0]

    def protocol_version(self, node):
        """None until HELLO confirms the firmware used by this exact endpoint."""
        address = self.address(node)
        entry = self.versions.get(node)
        seen = self.nodes.get(node)
        return entry[1] if (entry and entry[0] == address and seen
                            and self.clock()-seen[1] <= 6) else None

    def seen(self, node, address):
        self.nodes[node] = (address, self.clock())

    def send(self, data, address):
        self.socket.sendto(data, address)

    def close(self):
        self.socket.close()


@dataclass
class _Aim:
    seq: int
    angle: int
    settled_at: float
    lease_until: float | None = None
    fired: bool = False


@dataclass
class _Echo:
    node: int
    seq: int
    angle: int
    trigger: float
    done_at: float
    distance: int
    status: str


class SimulatedTransport:
    """Timed single reflector with independent servos and explicit ping grants.

    ``target`` can be a point, None, or a callable receiving simulation time.
    The echo captures that target at FIRE, never at later response delivery.
    This models ideal geometry and scheduling, not reflections from a body.
    """

    def __init__(self, clock, geometry):
        self.clock, self.geometry = clock, geometry
        self.target = (geometry.width / 2, (geometry.near_y + geometry.far_y) / 2)
        self.angles = [90000, 90000]
        self.aims = [None, None]
        self.last_ping = [float("-inf"), float("-inf")]
        self.latest_sequence = [None, None]
        self.last_command = [float("-inf"), float("-inf")]
        self.cache = [OrderedDict(), OrderedDict()]
        self.pending = []
        self.messages = []
        self.sent, self.aim_times, self.ping_times, self.commands = [], [], [], []

    def address(self, node):
        return (f"sim-{node}", 4211)

    def protocol_version(self, node):
        return 2

    def seen(self, node, address):
        pass

    def _reply(self, node, message):
        self.messages.append((message, self.address(node)))

    def _ready(self, node, request, now):
        lease = max(0, math.floor((request.lease_until - now) * 1000 + 1e-6)) if request.lease_until else 0
        self._reply(node, Ready(node, request.seq, request.angle, lease if not request.fired else 0,
                               "OK" if lease and not request.fired else "INVALID"))

    def _cache(self, node, response):
        self.cache[node][response.seq] = response
        while len(self.cache[node]) > 16:
            self.cache[node].popitem(last=False)

    def _advance(self, now):
        for node, request in enumerate(self.aims):
            if request and request.lease_until is None and now >= request.settled_at:
                # The lease starts when READY is created, as on the ESP32.
                request.lease_until = now + 1.0
                self._ready(node, request, now)
        due = [echo for echo in self.pending if now >= echo.done_at]
        self.pending = [echo for echo in self.pending if now < echo.done_at]
        for echo in due:
            response = Range(echo.node, echo.seq, echo.angle, echo.distance, echo.status,
                             int(echo.trigger * 1000) & MAX_SEQUENCE,
                             max(0, round((now - echo.trigger) * 1_000_000)), 2)
            self._cache(echo.node, response)
            self._reply(echo.node, response)

    def send(self, data, address):
        now = self.clock()
        self._advance(now)
        if data in (b"WM2 DISCOVER", b"WM2 DISCOVER\n", b"WM2 DISCOVER\r\n"):
            if address not in (self.address(0), self.address(1)):
                raise ValueError("Invalid simulator node")
            node = 0 if address == self.address(0) else 1
            self._reply(node, Hello(node, version=2))
            return
        aim_match = re.fullmatch(rb"WM2 AIM ([0-9]{1,10}) ([0-9]{1,6})\r?\n?", data)
        fire_match = re.fullmatch(rb"WM2 FIRE ([0-9]{1,10})\r?\n?", data)
        if len(data) >= 96 or not (aim_match or fire_match):
            raise ValueError("Simulator requires bounded WM2 AIM/FIRE commands")
        kind = "AIM" if aim_match else "FIRE"
        seq = int((aim_match or fire_match)[1])
        angle = int(aim_match[2]) if aim_match else None
        if not 1 <= seq <= MAX_SEQUENCE or (angle is not None and not 0 <= angle <= 180000):
            raise ValueError("Invalid simulator sequence or angle")
        if address not in (self.address(0), self.address(1)):
            raise ValueError("Invalid simulator node")
        node = 0 if address == self.address(0) else 1
        self.commands.append((now, node, kind, seq, angle))
        if now - self.last_command[node] >= 30:
            self.aims[node] = None
            self.latest_sequence[node] = None
            self.cache[node].clear()
        request = self.aims[node]
        if kind == "AIM":
            self.aim_times.append((now, node, seq))
            if request and request.seq == seq:
                self.last_command[node] = now
                if request.angle != angle:
                    self._reply(node, Ready(node, seq, angle, 0, "INVALID"))
                elif request.lease_until is not None:
                    self._ready(node, request, now)
                return
            if seq in self.cache[node]:
                self.last_command[node] = now
                self._reply(node, Ready(node, seq, angle, 0, "INVALID"))
                return
            if any(echo.node == node for echo in self.pending):
                return
            latest = self.latest_sequence[node]
            if latest is not None and not 0 < ((seq - latest) & MAX_SEQUENCE) < 0x80000000:
                self._reply(node, Ready(node, seq, angle, 0, "INVALID"))
                return
            remaining = max(0, request.settled_at - now) if request else 0
            movement = abs(angle - self.angles[node]) / 1000
            delay = remaining if movement == 0 else min(0.7, 0.06 + movement * 0.003 + remaining)
            self.angles[node] = angle
            self.aims[node] = _Aim(seq, angle, now + delay)
            self.latest_sequence[node], self.last_command[node] = seq, now
            self._advance(now)
            return
        self.sent.append((now, node, seq))
        if seq in self.cache[node]:
            self.last_command[node] = now
            self._reply(node, self.cache[node][seq])
            return
        if any(echo.node == node and echo.seq == seq for echo in self.pending):
            return
        if not (request and request.seq == seq and not request.fired and request.lease_until is not None
                and now < request.lease_until and now - self.last_ping[node] >= 0.065):
            response = Range(node, seq, self.angles[node], 0, "INVALID", 0, 0, 2)
            latest = self.latest_sequence[node]
            newer = latest is None or 0 < ((seq - latest) & MAX_SEQUENCE) < 0x80000000
            if newer or (request and request.seq == seq):
                self.latest_sequence[node] = seq
                self.last_command[node] = now
                self._cache(node, response)
                if request:
                    request.fired = True
                    request.lease_until = now
            self._reply(node, response)
            return
        self.last_command[node] = now
        request.fired = True
        self.last_ping[node] = now
        self.ping_times.append((now, node, seq))
        target = self.target(now) if callable(self.target) else self.target
        distance, status = 0, "TIMEOUT"
        if target is not None:
            x = self.geometry.left_x if node == 0 else self.geometry.right_x
            visible = abs(self.geometry.angle(node, target) - request.angle) <= self.geometry.beam_half_angle_deg * 1000
            raw = round(math.dist((x, self.geometry.sensor_y), target) * 1000)
            if visible and 20 <= raw <= 4000:
                distance, status = raw, "OK"
        flight = distance * 2 / 343000 if status == "OK" else 0.025
        self.pending.append(_Echo(node, seq, request.angle, now, now + flight, distance, status))

    def receive(self):
        self._advance(self.clock())
        messages, self.messages = self.messages, []
        return messages

    def close(self):
        self.pending.clear()
        self.messages.clear()
