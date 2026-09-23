"""Leader-follower N-box controller against the timed simulator."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from whack.swarm import SwarmController, fuse, Contribution
from whack.tracking import Geometry
from whack.transport import SimulatedTransport


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


def run(controller, clock, seconds):
    snap = None
    for _ in range(round(seconds/.01)):
        snap = controller.poll(); clock.advance()
    return snap


def alerts_seen(controller, clock, seconds):
    seen = set()
    for _ in range(round(seconds/.01)):
        seen.add(controller.poll().alert); clock.advance()
    seen.discard("")
    return seen


def make(target=(0.75, 1.3), **geometry):
    clock = Clock()
    g = Geometry(body_radius_m=0.18, smoothing_tau_s=0.25, local_search_s=1.0, sensor_y=0.5, **geometry)
    c = SwarmController(g, simulate=True, clock=clock)
    c.transport.target = target
    return c, clock, c.transport


def aims(transport, node):
    return [a//1000 for _, n, kind, _, a in transport.commands if kind == "AIM" and n == node]


class SweepTests(unittest.TestCase):
    def test_steps_five_degrees_clockwise_and_bounces_at_bounds(self):
        c, clock, t = make(target=None, sweep_bounds_deg=((12, 97), (80, 170)))
        run(c, clock, 6)
        seq = aims(t, 0)
        self.assertEqual(seq[:5], [85, 80, 75, 70, 65])          # 90 -> down in 5s
        self.assertIn(15, seq)                                   # reaches the last grid step above 12
        i = seq.index(15)
        self.assertEqual(seq[i:i+3], [15, 20, 25])               # bounces upward
        self.assertTrue(all(b % 5 == 0 for b in seq))
        right = aims(t, 1)
        self.assertEqual(right[:4], [85, 80, 85, 90])            # bound 80: bounce immediately

    def test_snaps_to_the_grid_from_an_off_grid_start(self):
        c, clock, t = make(target=None)
        c.boxes[0].bearing = 93000
        run(c, clock, 2)
        self.assertEqual(aims(t, 0)[:3], [90, 85, 80])

    def test_pings_never_overlap(self):
        c, clock, t = make()
        run(c, clock, 8)
        gaps = [b[0]-a[0] for a, b in zip(t.ping_times, t.ping_times[1:])]
        self.assertGreaterEqual(min(gaps), 0.065)
        self.assertGreater(len(t.ping_times), 20)


class AcquisitionTests(unittest.TestCase):
    def test_first_box_locks_then_follower_is_aimed_and_confirms(self):
        c, clock, t = make()
        snap = run(c, clock, 4)
        self.assertEqual(snap.state, "track")
        self.assertEqual(snap.contributors, 2)
        self.assertLess(math.dist(snap.position, (0.75, 1.3)), 0.12)
        # the follower was aimed toward the estimate, not left sweeping
        bearing1 = c.boxes[1].bearing/1000
        self.assertAlmostEqual(bearing1, 133, delta=6)

    def test_single_box_fix_is_hollow_and_less_confident(self):
        c, clock, t = make()
        # node 1 never sees anything: everything beyond its range
        t.target = lambda now, node: (0.75, 1.3) if node == 0 else None
        snap = run(c, clock, 4)
        self.assertEqual(snap.state, "track")
        self.assertEqual(snap.contributors, 1)
        self.assertTrue(snap.predicted)
        self.assertLess(snap.confidence, 0.6)
        self.assertIn("one box", snap.status)

    def test_moving_player_is_followed(self):
        c, clock, t = make()
        run(c, clock, 4)
        t.target = (1.1, 1.0)
        snap = run(c, clock, 3)
        self.assertEqual(snap.state, "track")
        self.assertLess(math.dist(snap.position, (1.1, 1.0)), 0.15)

    def test_loss_jitters_then_resumes_sweep_from_current_bearing(self):
        c, clock, t = make()
        run(c, clock, 4)
        before = len(t.commands)
        t.target = None
        snap = run(c, clock, 3)
        self.assertEqual(snap.state, "find")
        modes = [b.mode for b in c.boxes]
        self.assertEqual(modes, ["sweep", "sweep"])
        later = [a//1000 for _, n, kind, _, a in t.commands[before:] if kind == "AIM" and n == 0]
        # jitter offsets of 8 deg appear before 5-degree stepping resumes
        self.assertTrue(any(abs(later[i+1]-later[i]) in (8, 16) for i in range(min(8, len(later)-1))), later[:10])
        tail = later[-4:]
        self.assertTrue(all(abs(tail[i+1]-tail[i]) == 5 for i in range(len(tail)-1)))


class AlertTests(unittest.TestCase):
    def test_player_too_close_to_a_box(self):
        c, clock, t = make(target=(0.15, 0.7))          # 0.25 m from box 0: surface 7 cm away
        seen = alerts_seen(c, clock, 4)
        self.assertTrue(any("too close" in a for a in seen), seen)

    def test_player_outside_the_field(self):
        c, clock, t = make(target=(0.75, 0.55))         # in the 10 cm dead zone, seen by both boxes
        seen = alerts_seen(c, clock, 5)
        self.assertIn("Player in the dead zone", seen)

    def test_two_players_pause(self):
        c, clock, t = make()
        t.target = lambda now, node: (0.25, 1.2) if node == 0 else (1.3, 1.2)
        seen = alerts_seen(c, clock, 10)
        self.assertIn("Two players detected", seen)


class CalibrationTests(unittest.TestCase):
    def test_empty_room_map_is_saved_on_the_sweep_grid_and_reloaded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"cal.json"
            clock = Clock()
            g = Geometry(sensor_y=0.5, body_radius_m=0.18)
            t = SimulatedTransport(clock, g); t.target = None
            c = SwarmController(g, clock=clock, transport=t, calibration_path=path, start_paused=True)
            c.start_calibration()
            run(c, clock, 120)
            self.assertFalse(c.calibrating)
            self.assertTrue(path.exists())
            profile = json.loads(path.read_text())
            self.assertEqual(profile["version"], 3)
            keys = set(profile["background"])
            self.assertEqual(keys, {f"{n}:{b}" for n in (0, 1) for b in c._grid(n)})
            self.assertTrue(c.paused)
            again = SwarmController(g, clock=clock, transport=t, calibration_path=path)
            self.assertEqual(again.background, profile["background"])


class FuseTests(unittest.TestCase):
    def test_two_exact_circles_recover_the_point(self):
        g = Geometry(sensor_y=0.5)
        target = (0.6, 1.4)
        cs = [Contribution(n, 0.0, g.angle(n, target), math.dist(g.sensor_position(n), target),
                           target) for n in (0, 1)]
        point, worst = fuse(g, cs)
        self.assertLess(math.dist(point, target), 1e-3)
        self.assertLess(worst, 1e-3)


if __name__ == "__main__":
    unittest.main()
