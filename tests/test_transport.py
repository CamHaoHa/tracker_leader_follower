"""Deterministic checks of timing, stale grants and UDP discovery versions."""

import math
import unittest
from unittest.mock import patch

from whack.protocol import Range, Ready, aim, buzz, fire
from whack.tracking import Geometry
from whack.transport import SimulatedTransport, UdpTransport
from tools.simulate_nodes import parse_command


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SimulatorTimingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.transport = SimulatedTransport(self.clock, Geometry())
        self.addCleanup(self.transport.close)

    def send(self, node, data):
        self.transport.send(data, self.transport.address(node))

    def advance(self, now):
        self.clock.now = now
        return [message for message, _ in self.transport.receive()]

    def test_servos_settle_concurrently_and_never_ping_while_aiming(self):
        self.send(0, aim(1, 60000))
        self.send(1, aim(2, 120000))
        self.assertEqual(self.advance(.149), [])
        replies = self.advance(.151)
        self.assertEqual({r.node for r in replies}, {0, 1})
        self.assertTrue(all(isinstance(r, Ready) and r.status == "OK" for r in replies))
        self.assertEqual(self.transport.ping_times, [])
        self.assertEqual(self.transport.aim_times[0][0], self.transport.aim_times[1][0])
        self.advance(2)
        self.assertEqual(self.transport.ping_times, [])

    def test_range_captures_target_at_fire_and_reports_sample_age(self):
        self.send(0, aim(1, 60000))
        self.advance(.151)
        target = self.transport.target
        self.send(0, fire(1))
        self.transport.target = None
        replies = self.advance(.2)
        self.assertEqual(len(replies), 1)
        self.assertIsInstance(replies[0], Range)
        expected = round(math.dist((0, .2), target) * 1000)
        self.assertEqual(replies[0].distance_mm, expected)
        self.assertEqual(replies[0].sample_ms, 151)
        self.assertAlmostEqual(replies[0].age_us, 49000, delta=1)
        self.assertEqual(len(self.transport.ping_times), 1)

    def test_duplicate_fire_replays_original_result_without_second_ping(self):
        self.send(0, aim(1, 60000))
        self.advance(.151)
        self.send(0, fire(1))
        self.send(0, fire(1))
        original = self.advance(.2)[0]
        self.advance(.5)
        self.send(0, fire(1))
        self.assertEqual(self.advance(.5), [original])
        self.assertEqual(len(self.transport.ping_times), 1)
        self.send(0, aim(1, 60000))
        self.assertEqual(self.advance(.5)[0].status, "INVALID")

    def test_expired_or_premature_fire_cannot_ping_later(self):
        self.send(0, aim(1, 60000))
        self.send(0, fire(1))
        self.assertEqual(self.advance(.05)[0].status, "INVALID")
        self.advance(.2)
        self.send(0, fire(1))
        self.assertEqual(self.advance(.2)[0].status, "INVALID")
        self.send(1, aim(2, 120000))
        self.advance(.4)
        self.send(1, aim(2, 120000))
        self.assertEqual(self.advance(.6)[0].lease_ms, 1000)
        self.send(1, aim(2, 120000))
        self.assertEqual(self.advance(.6)[0].lease_ms, 800)
        self.advance(1.5)
        self.send(1, fire(2))
        self.assertEqual(self.advance(1.5)[0].status, "INVALID")
        self.assertEqual(self.transport.ping_times, [])

    def test_unchanged_bearing_ready_immediately_but_ping_guard_still_applies(self):
        self.send(0, aim(1, 60000))
        self.advance(.151)
        self.send(0, fire(1))
        self.advance(.17)
        self.send(0, aim(2, 60000))
        self.assertEqual(self.advance(.17)[0].status, "OK")
        self.send(0, fire(2))
        self.assertEqual(self.advance(.17)[0].status, "INVALID")
        self.advance(.3)
        self.send(0, fire(2))
        self.assertEqual(self.advance(.3)[0].status, "INVALID")
        self.send(0, aim(3, 60000))
        self.advance(.3)
        self.send(0, fire(3))
        self.advance(.32)
        self.assertEqual(len(self.transport.ping_times), 2)
        self.assertGreaterEqual(self.transport.ping_times[1][0] - self.transport.ping_times[0][0], .065)

    def test_unknown_newer_fire_consumes_sequence_and_revokes_older_grant(self):
        self.send(0, aim(1, 60000))
        self.advance(.2)
        self.send(0, fire(3))
        self.assertEqual(self.advance(.2)[0].status, "INVALID")
        self.send(0, aim(3, 60000))
        self.assertEqual(self.advance(.2)[0].status, "INVALID")
        self.send(0, aim(2, 60000))
        self.assertEqual(self.advance(.2)[0].status, "INVALID")
        self.send(0, fire(1))
        self.assertEqual(self.advance(.2)[0].status, "INVALID")
        self.assertEqual(self.transport.ping_times, [])
        self.send(0, aim(4, 60000))
        self.assertEqual(self.advance(.2)[0].status, "OK")
        self.send(0, fire(4))
        self.advance(.22)
        self.assertEqual(len(self.transport.ping_times), 1)

    def test_buzz_is_recorded_without_a_reply_and_expires_by_itself(self):
        self.send(1, buzz(400))
        self.assertEqual(self.transport.buzzes, [(0.0, 1, 400)])
        self.assertTrue(self.transport.buzzing(1))
        self.assertFalse(self.transport.buzzing(0))
        self.assertEqual(self.advance(.3), [])                  # no reply
        self.send(1, buzz(400))                                 # replaces the deadline
        self.assertEqual(self.advance(.69), [])
        self.assertTrue(self.transport.buzzing(1))
        self.advance(.7)                                        # a vanished laptop: silence
        self.assertFalse(self.transport.buzzing(1))
        self.send(1, buzz(2000))
        self.send(1, b"WM2 BUZZ 0\r\n")                         # silences at once
        self.assertFalse(self.transport.buzzing(1))
        self.assertEqual([d for _, _, d in self.transport.buzzes], [400, 400, 2000, 0])
        self.assertEqual(self.transport.commands, [])           # not an AIM/FIRE record

    def test_buzz_does_not_disturb_an_aim_or_its_firing_lease(self):
        self.send(0, aim(7, 60000))
        self.send(0, buzz(400))
        replies = self.advance(.151)
        self.assertEqual(replies, [Ready(0, 7, 60000, 1000, "OK")])
        self.send(0, buzz(0))
        self.send(0, fire(7))
        self.send(0, buzz(400))
        replies = self.advance(.2)
        self.assertEqual([type(r) for r in replies], [Range])
        self.assertEqual((replies[0].seq, replies[0].status), (7, "OK"))
        self.assertEqual(len(self.transport.ping_times), 1)

    def test_malformed_buzz_is_refused(self):
        for packet in (b"WM2 BUZZ 2001", b"WM2 BUZZ", b"WM2 BUZZ -1", b"WM2 BUZZ 1.5",
                       b"WM2 BUZZ 400 1", b"WM1 BUZZ 400"):
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                self.send(1, packet)
        with self.assertRaises(ValueError):
            self.transport.send(buzz(400), ("sim-9", 4211))
        self.assertEqual(self.transport.buzzes, [])

    def test_callable_target_uses_trigger_time(self):
        times = []
        self.transport.target = lambda now: times.append(now) or (.75, 1.3)
        self.send(0, aim(1, 60000))
        self.advance(.2)
        self.send(0, fire(1))
        self.advance(.3)
        self.assertEqual(times, [.2])


class DiscoveryTests(unittest.TestCase):
    def test_version_is_learned_only_from_current_endpoint_and_conflicts_block_it(self):
        clock = Clock()
        with patch("whack.transport.socket.socket") as create:
            transport = UdpTransport(clock, node_ips=("127.0.0.2", "127.0.0.3"))
            sock = create.return_value
            self.assertIsNone(transport.protocol_version(0))
            sock.recvfrom.side_effect = [(b"WM1 HELLO 0", ("127.0.0.2", 4211)), BlockingIOError()]
            transport.receive()
            self.assertEqual(transport.protocol_version(0), 1)
            sock.recvfrom.side_effect = [(b"WM2 HELLO 0", ("127.0.0.2", 4211)), BlockingIOError()]
            transport.receive()
            self.assertEqual(transport.protocol_version(0), 2)
            sock.recvfrom.side_effect = [(b"WM1 HELLO 0", ("127.0.0.9", 4211)), BlockingIOError()]
            transport.receive()
            self.assertEqual(transport.protocol_version(0), 2)
            transport.close()
        with patch("whack.transport.socket.socket") as create:
            transport = UdpTransport(clock)
            create.return_value.recvfrom.side_effect = [
                (b"WM2 HELLO 0", ("127.0.0.2", 4211)),
                (b"WM2 HELLO 0", ("127.0.0.9", 4211)), BlockingIOError()]
            transport.receive()
            self.assertIsNone(transport.address(0))
            self.assertIsNone(transport.protocol_version(0))
            transport.close()

    def test_softap_discovery_recovers_after_dhcp_change_and_conflicting_identity(self):
        clock = Clock()
        with patch("whack.transport.socket.socket") as create:
            transport = UdpTransport(clock)
            sock = create.return_value

            def announce(*messages):
                sock.recvfrom.side_effect = [*messages, BlockingIOError()]
                transport.receive()

            announce((b"WM2 HELLO 0", ("192.168.4.1", 4211)),
                     (b"WM2 HELLO 1", ("192.168.4.2", 4211)))
            self.assertEqual(transport.address(0), ("192.168.4.1", 4211))
            self.assertEqual(transport.address(1), ("192.168.4.2", 4211))
            clock.now = 1
            # A reused DHCP address claiming the wrong node and an early right
            # reassignment cannot silently replace two still-live identities.
            announce((b"WM2 HELLO 0", ("192.168.4.2", 4211)),
                     (b"WM2 HELLO 1", ("192.168.4.3", 4211)))
            self.assertIsNone(transport.address(0))
            self.assertIsNone(transport.address(1))
            self.assertEqual(transport.nodes[0][0], ("192.168.4.1", 4211))
            self.assertEqual(transport.nodes[1][0], ("192.168.4.2", 4211))
            self.assertEqual(tuple(transport.protocol_version(n) for n in (0, 1)), (None, None))
            clock.now = 6.5
            announce((b"WM2 HELLO 0", ("192.168.4.1", 4211)),
                     (b"WM2 HELLO 1", ("192.168.4.3", 4211)))
            self.assertIsNone(transport.address(1))  # Conflict hold-off remains active.
            clock.now = 7.1
            announce((b"WM2 HELLO 0", ("192.168.4.1", 4211)),
                     (b"WM2 HELLO 1", ("192.168.4.3", 4211)))
            self.assertEqual(transport.address(0), ("192.168.4.1", 4211))
            self.assertEqual(transport.address(1), ("192.168.4.3", 4211))
            self.assertEqual(tuple(transport.protocol_version(n) for n in (0, 1)), (2, 2))
            sock.sendto.assert_not_called()  # Automatic discovery needs no IP preset.
            transport.close()

    def test_manual_discovery_is_rate_limited_and_version_requires_recent_evidence(self):
        clock = Clock()
        with patch("whack.transport.socket.socket") as create:
            transport = UdpTransport(clock, node_ips=("127.0.0.2", "127.0.0.3"))
            sock = create.return_value
            sock.recvfrom.side_effect = BlockingIOError()
            transport.receive()
            self.assertEqual(sock.sendto.call_count, 2)
            self.assertEqual(sock.sendto.call_args_list[0].args, (b"WM2 DISCOVER", ("127.0.0.2", 4211)))
            clock.now = .5
            transport.receive()
            self.assertEqual(sock.sendto.call_count, 2)
            clock.now = 1
            sock.recvfrom.side_effect = [(b"WM2 HELLO 0", ("127.0.0.2", 4211)), BlockingIOError()]
            transport.receive()
            self.assertEqual(sock.sendto.call_count, 4)
            self.assertEqual(transport.protocol_version(0), 2)
            clock.now = 7.01
            self.assertIsNone(transport.protocol_version(0))
            self.assertEqual(transport.address(0), ("127.0.0.2", 4211))
            transport.seen(0, ("127.0.0.2", 4211))
            self.assertEqual(transport.protocol_version(0), 2)
            transport.close()

    def test_loopback_simulator_rejects_malformed_commands(self):
        self.assertEqual(parse_command(b"WM2 AIM 4294967295 180000"), ("AIM", 4294967295, 180000))
        self.assertEqual(parse_command(b"WM2 FIRE 1"), ("FIRE", 1, None))
        self.assertEqual(parse_command(b"WM2 DISCOVER"), ("DISCOVER", None, None))
        self.assertEqual(parse_command(b"WM2 BUZZ 400"), ("BUZZ", None, 400))
        self.assertEqual(parse_command(b"WM2 BUZZ 0\r\n"), ("BUZZ", None, 0))
        for packet in (b"WM1 MEASURE 1 90000", b"WM2 FIRE 0", b"WM2 FIRE 1 EXTRA", b"WM2 AIM 1 180001",
                       b"WM2 AIM -1 90000", b"WM2 FIRE 4294967296", b"WM2 DISCOVER extra", b"WM2 AIM 1 90000\x00", b"x"*129,
                       b"WM2 BUZZ 2001", b"WM2 BUZZ", b"WM2 BUZZ -1", b"WM2 BUZZ 400 1"):
            with self.subTest(packet=packet):
                self.assertIsNone(parse_command(packet))


if __name__ == "__main__":
    unittest.main()
