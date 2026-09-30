"""The lock-scan sketch's Python twin, its simulator, the report parser, the
UDP listener and the display-only controller (--tracker sketch)."""

import math
import socket
import unittest

from whack.sketch import (HELLO, Report, SketchBox, SketchController, SketchSimulator, SketchUdp,
                          parse_report)
from whack.tracking import Geometry


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


def run(controller, clock, seconds):
    snap = None
    for _ in range(round(seconds/.01)):
        snap = controller.poll(); clock.advance()
    return snap


def make(target=(0.75, 1.3), **geometry):
    clock = Clock()
    g = Geometry(body_radius_m=0.18, smoothing_tau_s=0.25, local_search_s=1.0, sensor_y=0.5, **geometry)
    c = SketchController(g, simulate=True, clock=clock)
    c.transport.target = target
    return c, clock, c.transport


TARGET = (0.75, 1.3)
TRUE0 = math.degrees(math.atan2(0.8, 0.75))                 # 46.8 deg from box 0
SURFACE0_CM = (math.dist((0, 0.5), TARGET) - 0.18)*100      # 91.7 cm


class ParserTests(unittest.TestCase):
    def test_every_report_kind(self):
        self.assertEqual(parse_report(b"LS 0 HELLO"), Report(0, "HELLO"))
        self.assertEqual(parse_report(b"LS 2 PING 87 -1.0\n"), Report(2, "PING", 87, -1.0))
        self.assertEqual(parse_report(b"LS 1 LOCK 66 91.7"), Report(1, "LOCK", 66, 91.7))
        self.assertEqual(parse_report(b"LS 0 TRACK 58 90.3 6"), Report(0, "TRACK", 58, 90.3, 6))
        self.assertEqual(parse_report(b"LS 0 MISS 2"), Report(0, "MISS", None, None, 2))
        self.assertEqual(parse_report(b"LS 1 LOST"), Report(1, "LOST"))

    def test_rejects_wrong_shapes_and_ranges(self):
        for bad in (b"LS 0 PING 87", b"LS 0 TRACK 58 90.3", b"LS 0 LOST 3", b"WM2 HELLO 0",
                    b"LS 0 PING 200 10.0", b"LS 0 PING 90 5000.0", b"LS 0 P\xffNG 1 1.0", b"LS 0 " + b"x"*100):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_report(bad))


class TwinTests(unittest.TestCase):
    def test_search_steps_three_degrees_from_zero_and_turns_at_180(self):
        box = SketchBox(0)
        seen = [box.requested]
        for _ in range(62):
            seen.append(box.ping(-1.0))
        self.assertEqual(seen[:4], [0, 3, 6, 9])
        self.assertEqual(seen[59:63], [177, 180, 177, 174])
        self.assertEqual(box.mode, "SEARCH")

    def test_first_echo_locks_and_the_window_scans_both_ways(self):
        box = SketchBox(0)
        while box.requested < 66:
            box.ping(-1.0)
        box.reports.clear()
        nxt = box.ping(90.0)                                   # 90 cm at 66 deg
        self.assertEqual(box.reports, [("PING", 66, 90.0, None), ("LOCK", 66, 90.0, None)])
        self.assertEqual((box.mode, box.lockedAngle, box.lockedDist), ("TRACK", 66, 90.0))
        self.assertEqual(nxt, 51)                              # lo of the 51..81 window
        pinged = []
        for _ in range(11):                                    # forward pass: hits at 51, 54, 57 only
            a = box.requested; pinged.append(a)
            box.ping(90.0 if a <= 57 else 130.0)               # 130 cm: same object? no (jump 40 > 25)
        self.assertEqual(pinged, list(range(51, 82, 3)))
        self.assertEqual(box.reports[-1], ("TRACK", 54, 90.0, 3))   # (51+54+57)//3, 0.7*90+0.3*90
        self.assertEqual(box.requested, 69)                    # backward pass from hi = 54+15
        self.assertFalse(box.scanForward)

    def test_four_empty_passes_drop_to_search_from_the_lock(self):
        box = SketchBox(0)
        while box.requested < 66:
            box.ping(-1.0)
        box.ping(90.0)
        box.reports.clear()
        kinds = []
        while box.mode == "TRACK":
            box.ping(-1.0)
            kinds += [r[0] for r in box.reports if r[0] != "PING"]; box.reports.clear()
        self.assertEqual(kinds, ["MISS", "MISS", "MISS", "LOST"])
        self.assertEqual((box.searchAngle, box.requested), (66, 66))   # search() pings the lock first


class SimulationTests(unittest.TestCase):
    def test_boxes_lock_and_the_spot_lands_on_the_target(self):
        c, clock, t = make()
        snap = run(c, clock, 4)
        self.assertEqual(snap.state, "track")
        self.assertEqual(snap.contributors, 2)
        self.assertLess(math.dist(snap.position, TARGET), 0.12)
        lock0 = c.views[0].lock
        self.assertAlmostEqual(lock0[0], TRUE0, delta=8)
        self.assertAlmostEqual(lock0[1], SURFACE0_CM, delta=2)
        self.assertGreater(snap.update_hz, 2)
        self.assertEqual(snap.boxes[0]["mode"], "track")
        self.assertEqual(snap.boxes[0]["window_deg"][1] - snap.boxes[0]["window_deg"][0], 30)

    def test_boxes_run_independently_at_the_sketch_pace(self):
        c, clock, t = make(target=None)
        run(c, clock, 3)
        by_box = {0: [], 1: []}
        for stamp, node, angle, cm in t.pings:
            by_box[node].append(stamp)
        gaps0 = [b-a for a, b in zip(by_box[0], by_box[0][1:])]
        self.assertTrue(all(abs(g-0.065) < 1e-6 for g in gaps0), gaps0[:5])      # 40 ms settle + 25 ms timeout
        overlaps = sum(1 for s0 in by_box[0] for s1 in by_box[1] if abs(s0-s1) < 0.03)
        self.assertGreater(overlaps, 5)                                          # no shared ping slot

    def test_one_box_fix_is_hollow_and_loss_hides_the_spot(self):
        c, clock, t = make()
        t.target = lambda now: TARGET
        run(c, clock, 3)
        t.target = lambda now: None
        snap = run(c, clock, 4)                    # 4 empty passes of 11 pings at 65 ms: ~2.9 s
        self.assertEqual(snap.state, "find")
        self.assertIsNone(snap.position)
        self.assertEqual([v.mode for v in c.views], ["SEARCH", "SEARCH"])

    def test_moving_target_is_followed(self):
        c, clock, t = make()
        run(c, clock, 3)
        t.target = (0.95, 1.3)
        snap = run(c, clock, 3)
        self.assertEqual(snap.state, "track")
        self.assertLess(math.dist(snap.position, (0.95, 1.3)), 0.15)


class FakeTransport:
    def __init__(self):
        self.queue = []
    def receive(self):
        out, self.queue = self.queue, []
        return out
    def address(self, node): return ("fake", 4211)
    def close(self): pass


class ControllerTests(unittest.TestCase):
    def controller(self):
        clock = Clock()
        g = Geometry(body_radius_m=0.18, sensor_y=0.5)
        t = FakeTransport()
        return SketchController(g, clock=clock, transport=t), clock, t

    def test_reports_drive_the_spot(self):
        c, clock, t = self.controller()
        g = c.geometry
        r0 = (math.dist(g.sensor_position(0), TARGET) - 0.18)*100
        r1 = (math.dist(g.sensor_position(1), TARGET) - 0.18)*100
        t.queue = [(Report(0, "LOCK", 66, round(r0, 1)), None, 0.0)]
        snap = c.poll()
        self.assertEqual((snap.state, snap.contributors, snap.predicted), ("track", 1, True))
        clock.advance(.5)
        t.queue = [(Report(1, "TRACK", 133, round(r1, 1), 7), None, 0.5)]
        snap = c.poll()
        self.assertEqual(snap.contributors, 2)
        self.assertLess(math.dist(snap.position, TARGET), 0.05)
        self.assertIn("box 1 133 deg", snap.status)
        t.queue = [(Report(1, "MISS", None, None, 2), None, 1.0)]
        snap = c.poll()
        self.assertEqual(c.views[1].lost, 2)
        self.assertLess(snap.confidence, 0.6)
        t.queue = [(Report(1, "LOST"), None, 1.5), (Report(0, "LOST"), None, 1.5)]
        snap = c.poll()
        self.assertIsNone(snap.position)
        self.assertEqual(snap.state, "find")

    def test_silent_box_goes_offline_and_its_lock_is_dropped(self):
        c, clock, t = self.controller()
        t.queue = [(Report(0, "LOCK", 66, 91.7), None, 0.0)]
        self.assertIsNotNone(c.poll().position)
        clock.advance(7)
        snap = c.poll()
        self.assertEqual(c.views[0].mode, "offline")
        self.assertIsNone(snap.position)
        self.assertTrue(snap.status.startswith("Waiting for boxes"), snap.status)

    def test_controls_never_touch_the_boxes(self):
        c, clock, t = self.controller()
        c.start_calibration()
        self.assertIn("No calibration", c.poll().status)
        c.pause()
        self.assertIn("Paused", c.poll().status)
        c.start_acquisition()
        self.assertFalse(c.paused)


class UdpTests(unittest.TestCase):
    def test_listener_parses_reports_and_answers_hello(self):
        clock = Clock()
        listener = SketchUdp(clock, port=0)
        port = listener.socket.getsockname()[1]
        box = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        box.bind(("127.0.0.1", 0)); box.settimeout(1)
        try:
            box.sendto(b"LS 0 TRACK 66 91.7 6", ("127.0.0.1", port))
            box.sendto(b"garbage", ("127.0.0.1", port))
            box.sendto(b"LS 0 HELLO", ("127.0.0.1", port))
            reports = []
            for _ in range(20):
                reports += listener.receive()
                if len(reports) >= 2:
                    break
            kinds = [r.kind for r, _, _ in reports]
            self.assertEqual(kinds, ["TRACK", "HELLO"])
            self.assertEqual(reports[0][0], Report(0, "TRACK", 66, 91.7, 6))
            self.assertEqual(listener.address(0)[0], "127.0.0.1")
            data, _ = box.recvfrom(64)
            self.assertEqual(data, HELLO)                    # the box learns where to report
        finally:
            box.close(); listener.close()


if __name__ == "__main__":
    unittest.main()
