import json
import math
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from whack.controller import Controller
from whack.protocol import Range, Ready
from whack.tracking import Geometry
from whack.transport import SimulatedTransport


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


def run(controller, clock, seconds):
    result = None
    for _ in range(round(seconds/.01)):
        result = controller.poll(); clock.advance()
    return result


class InjectedTransport(SimulatedTransport):
    inbox = None
    def receive(self):
        result = self.inbox or []; self.inbox = []
        return result


class ControllerTests(unittest.TestCase):
    def test_two_pairs_confirm_target_and_concurrent_aims_keep_pings_exclusive(self):
        clock = Clock(); c = Controller(simulate=True, clock=clock)
        confirmed = False
        for _ in range(300):
            snap = c.poll(); clock.advance()
            if c.state == "confirm":
                confirmed = True
                self.assertIsNone(snap.position)
        self.assertTrue(confirmed)
        self.assertTrue(snap.in_bounds)
        self.assertAlmostEqual(snap.position[0], .75, places=2)
        self.assertGreater(snap.update_hz, 5)
        pings = c.transport.ping_times
        self.assertTrue(all(a[1] != b[1] for a, b in zip(pings, pings[1:])))
        self.assertTrue(all(b[0]-a[0] >= .065 for a, b in zip(pings, pings[1:])))
        aims = c.transport.aim_times
        self.assertTrue(all(a[0] == b[0] for a, b in zip(aims[::2], aims[1::2])))

    def test_acquisition_covers_near_edges_and_front_strip(self):
        for point in ((0, .6), (1.5, .6), (.05, .65), (1.45, .65), (.75, .4), (.17, .63), (1.33, .63)):
            with self.subTest(point=point):
                clock = Clock(); c = Controller(Geometry(beam_half_angle_deg=15), simulate=True,
                                                clock=clock, start_mode="search")
                c.transport.target = point
                for _ in range(6000):
                    snap = c.poll(); clock.advance()
                    if snap.position is not None: break
                self.assertIsNotNone(snap.position)
                self.assertEqual(snap.dead_zone, point[1] < .6)
                self.assertEqual(snap.in_bounds, point[1] >= .6)

    def test_brief_dropout_predicts_then_recovers_without_full_search(self):
        clock = Clock(); c = Controller(simulate=True, clock=clock)
        self.assertTrue(run(c, clock, 3).in_bounds)
        last_good = c.tracker.last_good
        c.transport.target = None
        states = []
        for _ in range(25):
            snap = c.poll(); clock.advance(); states.append(snap.state)
            self.assertLessEqual(c.tracker.last_good, last_good+.1)  # An already fired echo may finish.
            if clock()-c.tracker.last_good > .21:
                self.assertIsNone(snap.position)
        self.assertIn("local_search", states)
        c.transport.target = (.75, 1.3)
        snap = run(c, clock, .4)
        self.assertEqual(snap.state, "track")
        self.assertTrue(snap.in_bounds)
        self.assertEqual(c.scan_index, 0)

    def test_persistent_dropout_hides_spot_and_resumes_full_search(self):
        clock = Clock(); c = Controller(simulate=True, clock=clock)
        run(c, clock, 3); c.transport.target = None
        states = []
        for _ in range(200):
            snap = c.poll(); clock.advance(); states.append(snap.state)
        self.assertIn("lost", states)
        self.assertEqual(snap.state, "find")
        self.assertIsNone(snap.position)
        self.assertGreater(c.scan_index, 0)

    def test_moving_target_remains_live_with_bounded_prediction_error(self):
        clock = Clock(); c = Controller(simulate=True, clock=clock)
        path = lambda t: (.75+.35*math.sin(.8*t), 1.3+.15*math.sin(.5*t))
        c.transport.target = path
        errors = []; fixes = []
        for _ in range(1500):
            snap = c.poll()
            if clock() > 2:
                self.assertIsNotNone(snap.position)
                errors.append(math.dist(snap.position, path(clock())))
                fixes.append(snap.fix_age_s)
            clock.advance()
        self.assertLess(max(errors), .065)
        self.assertLess(max(fixes), .20)
        self.assertGreater(snap.update_hz, 4)

    def test_wrong_endpoint_sequence_bearing_and_unsolicited_range_rejected(self):
        clock = Clock(); t = InjectedTransport(clock, Geometry())
        c = Controller(simulate=True, clock=clock, transport=t)
        c.poll(); f = c.pending
        bad = [(Ready(0, f.seq+1, f.angles[0], 1000, "OK"), f.addresses[0]),
               (Ready(0, f.seq, f.angles[0], 1000, "OK"), ("other", 4211)),
               (Ready(1, f.seq, f.angles[1], 1000, "OK"), f.addresses[0]),
               (Ready(0, f.seq, 0, 1000, "OK"), f.addresses[0]),
               (Range(0, f.seq, f.angles[0], 1300, "OK", 0, 0, 2), f.addresses[0])]
        for message in bad:
            t.inbox = [message]; c.poll()
            self.assertEqual(f.ready, {})
            self.assertEqual(f.samples, {})
        clock.advance(1); c.poll()
        self.assertIsNone(c.pending)
        t.inbox = [(Ready(0, f.seq, f.angles[0], 1000, "OK"), f.addresses[0])]
        c.poll(); self.assertEqual(c.samples, {})

    def test_lost_fire_reply_holds_other_sensor_until_entire_lease_expires(self):
        class DroppedReply(SimulatedTransport):
            ready_deadlines = None
            def receive(self):
                results = super().receive()
                if self.ready_deadlines is None: self.ready_deadlines = {}
                for m, _ in results:
                    if isinstance(m, Ready):
                        self.ready_deadlines[(m.node, m.seq)] = self.clock()+m.lease_ms/1000
                return [(m, a) for m, a in results if not isinstance(m, Range)]
        clock = Clock(); t = DroppedReply(clock, Geometry())
        c = Controller(simulate=True, clock=clock, transport=t)
        run(c, clock, 3)
        self.assertGreaterEqual(len(t.ping_times), 2)
        for a, b in zip(t.ping_times, t.ping_times[1:]):
            self.assertGreaterEqual(b[0], t.ready_deadlines[(a[1], a[2])]+.09-1e-6)
        self.assertIsNone(c.tracker.position(clock()))

    def test_timestamp_uncertainty_rejected_without_localizing(self):
        class Delayed(SimulatedTransport):
            def receive(self):
                results = super().receive()
                return [(Range(m.node, m.seq, m.angle_mdeg, m.distance_mm, m.status,
                               m.sample_ms, 1_000_000, 2) if isinstance(m, Range) else m, a)
                        for m, a in results]
        clock = Clock(); c = Controller(simulate=True, clock=clock, transport=Delayed(clock, Geometry()))
        self.assertIsNone(run(c, clock, 3).position)
        self.assertEqual(c.tracker.last_good, -math.inf)

    def test_legacy_firmware_and_absent_nodes_cannot_start_acoustic_test(self):
        class Legacy(SimulatedTransport):
            def protocol_version(self, node): return 1 if node == 1 else 2
        clock = Clock(); t = Legacy(clock, Geometry()); c = Controller(simulate=True, clock=clock, transport=t)
        snap = run(c, clock, 3)
        self.assertEqual(t.commands, [])
        self.assertIn("Upload WM2", snap.node_status[1])

    def test_hardware_requires_calibration_and_bad_profile_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(); t = SimulatedTransport(clock, Geometry()); path = Path(temp)/"cal.json"
            c = Controller(clock=clock, transport=t, calibration_path=path)
            self.assertIn("Calibrate", c.poll().status); self.assertEqual(t.sent, [])
            path.write_text(json.dumps({"version": 1, "geometry": asdict(Geometry()), "background": {"0:90": float("nan")}}))
            self.assertEqual(Controller(clock=clock, transport=t, calibration_path=path).background, {})

    def test_calibration_empty_echoes_persist_but_dropped_packet_aborts(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(); t = SimulatedTransport(clock, Geometry()); t.target = None
            path = Path(temp)/"cal.json"
            c = Controller(clock=clock, transport=t, calibration_path=path)
            c.start_calibration(); run(c, clock, 120)
            self.assertFalse(c.calibrating)
            self.assertTrue(path.exists()); self.assertTrue(c.background)
            self.assertTrue(all(v is None for v in c.background.values()))
            reloaded = Controller(clock=clock, transport=t, calibration_path=path)
            self.assertEqual(reloaded.background, c.background)
            t = InjectedTransport(clock, Geometry()); c = Controller(clock=clock, transport=t, calibration_path=path)
            c.start_calibration(); run(c, clock, 5)
            self.assertFalse(c.calibrating); self.assertFalse(c.background)
            self.assertIn("interrupted", c.poll().status)

    def test_calibration_cancels_in_flight_samples_and_waits_for_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(); t = SimulatedTransport(clock, Geometry())
            c = Controller(simulate=True, clock=clock, transport=t, calibration_path=Path(temp)/"cal.json")
            for _ in range(100):
                c.poll()
                if c.pending and c.pending.firing is not None: break
                clock.advance()
            c.simulate = False; c.start_calibration()
            run(c, clock, 2)
            self.assertEqual(c.samples, {}); self.assertEqual(c.calibration_index, 0)
            self.assertEqual(len(t.ping_times), 1)

    def test_dense_background_bearings_reject_walls_and_unprofiled_angles(self):
        clock = Clock(); c = Controller(simulate=True, clock=clock)
        c.background = {"0:90000": 1.5, "0:93000": 1.8, "0:99000": None}
        def fg(angle, distance): return c._foreground((Range(0, 1, angle, distance, "OK"), 0))
        self.assertFalse(fg(60000, 1000)); self.assertFalse(fg(90000, 1400))
        self.assertTrue(fg(90000, 1000)); self.assertTrue(fg(91000, 1000))
        self.assertFalse(fg(91500, 1400)); self.assertFalse(fg(95000, 1000))


if __name__ == "__main__": unittest.main()
