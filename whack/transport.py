"""Nonblocking UDP transport and a timed two-node simulator."""

import math
import socket

from .protocol import MAX_PACKET, Hello, Range, parse


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
        if node_ips:
            for node, ip in enumerate(node_ips):
                self.nodes[node] = ((ip, 4211), self.clock())
                self.configured[node] = (ip,4211)

    def receive(self):
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

    def seen(self, node, address):
        self.nodes[node] = (address, self.clock())

    def send(self, data, address):
        self.socket.sendto(data, address)

    def close(self):
        self.socket.close()


class SimulatedTransport:
    """Ideal single reflector with beam gates and servo delay; not a hardware model."""

    def __init__(self, clock, geometry):
        self.clock, self.geometry = clock, geometry
        self.target = (geometry.width / 2, (geometry.near_y + geometry.far_y) / 2)
        self.angles = [90000, 90000]
        self.pending = []
        self.sent = []

    def address(self, node):
        return (f"sim-{node}", 4211)

    def seen(self, node, address):
        pass

    def send(self, data, address):
        _, kind, seq, angle = data.decode("ascii").split()
        assert kind == "MEASURE"
        node = int(address[0][-1]); angle = int(angle)
        delay = min(0.7, 0.06 + abs(angle - self.angles[node]) / 1000 * 0.004)
        self.angles[node] = angle
        self.pending.append((self.clock() + delay, node, int(seq), angle))
        self.sent.append((self.clock(), node, int(seq)))
        self.sent = self.sent[-200:]

    def receive(self):
        ready = [p for p in self.pending if p[0] <= self.clock()]
        self.pending = [p for p in self.pending if p[0] > self.clock()]
        result = []
        for _, node, seq, angle in ready:
            g = self.geometry
            if self.target is None:
                distance, status = 0, "TIMEOUT"
            else:
                x = g.left_x if node == 0 else g.right_x
                visible = abs(g.angle(node, self.target) - angle) <= g.beam_half_angle_deg * 1000
                distance = round(math.dist((x, g.sensor_y), self.target) * 1000)
                status = "OK" if visible and 20 <= distance <= 4300 else "TIMEOUT"
                if status != "OK":
                    distance = 0
            packet = f"WM1 RANGE {node} {seq} {angle} {distance} {status}".encode()
            result.append((parse(packet), self.address(node)))
        return result

    def close(self):
        self.pending.clear()
