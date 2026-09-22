"""Exercise the independently implemented UDP node state machine without I/O."""

from collections import deque
import unittest

from tools.simulate_nodes import HOST, Node, Simulator
from whack.protocol import Range, Ready, parse


class DatagramSocket:
    def __init__(self):
        self.inbox, self.outbox = deque(), []

    def recvfrom(self, _size):
        if not self.inbox:
            raise BlockingIOError()
        return self.inbox.popleft()

    def sendto(self, packet, address):
        self.outbox.append((packet, address))


class IndependentSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulator.__new__(Simulator)
        self.sim.target, self.sim.motion, self.sim.started = (.75, 1.3), False, 0
        self.sim.nodes = [Node(node, DatagramSocket()) for node in (0, 1)]
        self.sim.drop_node, self.sim.last_ping = None, None
        self.sim.next_hello = float("inf")
        self.sim.pings = [0, 0]
        self.sim.min_ping_gap = None
        self.sim.overlapping_commands = self.sim.overlapping_pings = self.sim.malformed_commands = 0

    def send(self, node, command, now):
        target = self.sim.nodes[node]
        target.sock.inbox.append((command, HOST))
        self.sim.receive(target, now)

    def replies(self, node):
        result = [parse(packet) for packet, _ in self.sim.nodes[node].sock.outbox]
        self.sim.nodes[node].sock.outbox.clear()
        return result

    def test_aim_does_not_ping_and_expired_grant_cannot_be_reactivated(self):
        self.send(0, b"WM2 AIM 1 60000", 0)
        self.send(1, b"WM2 AIM 2 120000", 0)
        self.sim.tick(.2)
        self.assertEqual(self.replies(0), [Ready(0, 1, 60000, 1000, "OK")])
        self.assertEqual(self.replies(1), [Ready(1, 2, 120000, 1000, "OK")])
        self.assertEqual(self.sim.pings, [0, 0])
        self.assertEqual(self.sim.overlapping_commands, 1)
        self.send(0, b"WM2 AIM 1 60000", .5)
        self.assertEqual(self.replies(0)[0].lease_ms, 700)
        self.sim.tick(1.3)
        self.send(0, b"WM2 FIRE 1", 1.3)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 AIM 1 60000", 1.4)
        self.assertEqual(self.replies(0), [Ready(0, 1, 60000, 0, "INVALID")])
        self.assertEqual(self.sim.pings, [0, 0])

    def test_discovery_replies_to_arbitrary_port_without_changing_grant(self):
        self.send(0, b"WM2 AIM 1 60000", 0)
        self.sim.tick(.2)
        self.replies(0)
        node = self.sim.nodes[0]
        expires_at = node.aim.expires_at
        node.sock.inbox.append((b"WM2 DISCOVER", ("127.0.0.7", 8000)))
        self.sim.receive(node, .4)
        self.assertEqual(node.sock.outbox, [(b"WM2 HELLO 0", ("127.0.0.7", 8000))])
        self.assertEqual(node.aim.expires_at, expires_at)
        self.assertEqual(node.last_command, 0)
        self.assertEqual(self.sim.pings, [0, 0])

    def test_duplicate_fire_keeps_original_timestamp_and_never_retriggers(self):
        self.send(1, b"WM2 AIM 2 120000", 0)
        self.sim.tick(.2)
        self.replies(1)
        self.send(1, b"WM2 FIRE 2", .2)
        self.send(1, b"WM2 FIRE 2", .201)
        self.sim.target = None
        self.sim.tick(.22)
        response = self.replies(1)[0]
        self.assertIsInstance(response, Range)
        self.assertEqual(response.status, "OK")
        self.assertEqual(response.sample_ms, 123656)
        self.assertEqual(response.age_us, 20000)
        self.send(1, b"WM2 FIRE 2", .8)
        self.assertEqual(self.replies(1), [response])
        self.assertEqual(self.sim.pings, [0, 1])

    def test_unknown_newer_fire_revokes_current_grant_and_consumes_sequence(self):
        self.send(0, b"WM2 AIM 1 60000", 0)
        self.sim.tick(.2)
        self.replies(0)
        self.send(0, b"WM2 FIRE 3", .2)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 AIM 3 60000", .2)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 AIM 2 60000", .2)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 FIRE 1", .2)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.assertEqual(self.sim.pings, [0, 0])

    def test_early_fire_is_rejected_permanently_and_next_grant_honours_gap(self):
        self.send(0, b"WM2 AIM 1 60000", 0)
        self.send(0, b"WM2 FIRE 1", .01)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.sim.tick(.2)
        self.replies(0)
        self.send(0, b"WM2 FIRE 1", .2)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 AIM 2 60000", .2)
        self.sim.tick(.2)
        self.assertEqual(self.replies(0)[0].status, "OK")
        self.send(0, b"WM2 FIRE 2", .2)
        self.sim.tick(.22)
        self.replies(0)
        self.send(0, b"WM2 AIM 3 60000", .22)
        self.sim.tick(.22)
        self.replies(0)
        self.send(0, b"WM2 FIRE 3", .22)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.send(0, b"WM2 FIRE 3", .4)
        self.assertEqual(self.replies(0)[0].status, "INVALID")
        self.assertEqual(self.sim.pings, [1, 0])


if __name__ == "__main__":
    unittest.main()
