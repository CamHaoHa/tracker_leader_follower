"""Search -> lock -> window-scan controller against the timed simulator."""

import math
import unittest

from whack.lockscan import LockScanController
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
    c = LockScanController(g, simulate=True, clock=clock)
    c.transport.target = target
    return c, clock, c.transport


def aims(transport, node):
    return [a/1000 for _, n, kind, _, a in transport.commands if kind == "AIM" and n == node]


TARGET = (0.75, 1.3)
TRUE0 = math.degrees(math.atan2(1.3-0.5, 0.75))        # box 0 -> target, 46.8 deg
SURFACE0 = math.dist((0, 0.5), TARGET) - 0.18          # 0.92 m


class SettingsTests(unittest.TestCase):
    def test_sketch_defaults(self):
        g = Geometry()
        self.assertEqual((g.lock_step_deg, g.lock_window_deg, g.lock_max_jump_m, g.lock_lost_limit),
                         (3.0, 15.0, 0.25, 4))

    def test_limits(self):
        for bad in ({"lock_window_deg": 2}, {"lock_lost_limit": 0}, {"lock_max_jump_m": 0},
                    {"lock_step_deg": 0.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Geometry(**bad)


class SearchTests(unittest.TestCase):
    def test_steps_three_degrees_and_turns_round_on_the_bounds(self):
        c, clock, t = make(target=None, sweep_bounds_deg=((12, 97), (80, 170)))
        snap = run(c, clock, 8)
        left = aims(t, 0)
        self.assertEqual(left[:4], [87, 84, 81, 78])
        i = left.index(12)                                     # parks on the bound itself
        self.assertEqual(left[i:i+3], [12, 15, 18])
        self.assertEqual(aims(t, 1)[:6], [87, 84, 81, 80, 83, 86])
        self.assertEqual(snap.state, "find")
        self.assertIsNone(snap.position)
        self.assertTrue(snap.status.startswith("Searching"), snap.status)
        self.assertEqual([b["mode"] for b in snap.boxes], ["search", "search"])

    def test_pings_never_overlap(self):
        c, clock, t = make()
        run(c, clock, 8)
        gaps = [b[0]-a[0] for a, b in zip(t.ping_times, t.ping_times[1:])]
        self.assertGreaterEqual(min(gaps), 0.065)
        self.assertGreater(len(t.ping_times), 20)


class LockTests(unittest.TestCase):
    def test_first_echo_locks_then_the_window_is_scanned_both_ways(self):
        c, clock, t = make()
        snap = run(c, clock, 6)
        left = aims(t, 0)
        # Searching down from 87, the first bearing inside the 20 deg beam is 66.
        i = left.index(66)
        self.assertEqual(left[:i], [87, 84, 81, 78, 75, 72, 69])
        self.assertEqual(left[i+1:i+12], list(range(51, 82, 3)))          # lo -> hi
        back = left[i+12:i+23]
        self.assertEqual([round(b-a, 3) for a, b in zip(back, back[1:])], [-3]*10)   # hi -> lo
        lock0 = c.locks[0]
        self.assertEqual(lock0.mode, "track")
        self.assertAlmostEqual(lock0.bearing/1000, TRUE0, delta=8)
        self.assertAlmostEqual(lock0.range_m, SURFACE0, delta=0.02)
        self.assertEqual(snap.state, "track")
        self.assertEqual(snap.contributors, 2)
        self.assertFalse(snap.predicted)
        self.assertLess(math.dist(snap.position, TARGET), 0.12)
        self.assertIn("box 0", snap.status)
        info = snap.boxes[0]
        self.assertEqual(info["mode"], "track")
        self.assertEqual(info["window_deg"][1] - info["window_deg"][0], 30)
        self.assertAlmostEqual(info["lock"][1], lock0.range_m + 0.18)

    def test_one_box_fix_is_hollow(self):
        c, clock, t = make()
        t.target = lambda now, node: TARGET if node == 0 else None
        snap = run(c, clock, 6)
        self.assertEqual(snap.state, "track")
        self.assertEqual(snap.contributors, 1)
        self.assertTrue(snap.predicted)
        self.assertEqual([l.mode for l in c.locks], ["track", "search"])

    def test_moving_player_is_followed_inside_the_window(self):
        c, clock, t = make()
        run(c, clock, 6)
        t.target = (0.95, 1.3)          # 7 deg and 0.15 m from box 0: inside window and jump
        snap = run(c, clock, 6)
        self.assertEqual([l.mode for l in c.locks], ["track", "track"])
        self.assertLess(math.dist(snap.position, (0.95, 1.3)), 0.15)

    def test_echoes_off_the_locked_range_are_another_object(self):
        c, clock, t = make()
        run(c, clock, 6)
        t.target = (0.75, 1.9)          # same side, ~0.5 m further: beyond MAX_JUMP
        run(c, clock, 4)
        lock0 = c.locks[0]
        self.assertEqual(lock0.mode, "track")                       # still locked on the old range
        self.assertAlmostEqual(lock0.range_m, SURFACE0, delta=0.05)
        self.assertGreaterEqual(lock0.lost, 1)
        snap = run(c, clock, 16)                                    # LOST_LIMIT passes, search, relock
        self.assertEqual(snap.state, "track")
        self.assertAlmostEqual(lock0.range_m, math.dist((0, 0.5), (0.75, 1.9)) - 0.18, delta=0.05)
        self.assertLess(math.dist(snap.position, (0.75, 1.9)), 0.15)

    def test_lost_limit_empty_passes_drop_back_to_search_from_the_lock(self):
        c, clock, t = make()
        run(c, clock, 6)
        passes, unlocks = [], []                 # box 0: hits at each pass end; where it unlocked
        finish, unlock = c._finish_pass, c._unlock
        def spy_finish(box, lock, now):
            if box.node == 0:
                passes.append(lock.hits)
            finish(box, lock, now)
        def spy_unlock(box, lock, from_bearing):
            if box.node == 0:
                unlocks.append((from_bearing/1000, len([1 for _, n, k, _, _ in t.commands if k == "AIM" and n == 0])))
            unlock(box, lock, from_bearing)
        c._finish_pass, c._unlock = spy_finish, spy_unlock
        t.target = None
        snap = run(c, clock, 16)
        self.assertEqual(snap.state, "find")
        self.assertIsNone(snap.position)
        self.assertEqual([l.mode for l in c.locks], ["search", "search"])
        self.assertEqual(passes[-4:], [0, 0, 0, 0])            # exactly LOST_LIMIT empty passes
        self.assertGreater(passes[-5], 0)
        self.assertEqual(len(unlocks), 1)
        bearing, index = unlocks[0]
        resumed = aims(t, 0)[index:index+3]                    # search goes on from the lock in 3 deg steps
        self.assertEqual([round(a - bearing, 3) for a in resumed], [3, 6, 9] if resumed[0] > bearing else [-3, -6, -9])

    def test_space_forgets_the_lock(self):
        c, clock, t = make()
        run(c, clock, 6)
        c.start_acquisition()
        self.assertEqual([l.mode for l in c.locks], ["search", "search"])
        self.assertEqual(c.state, "find")
        snap = run(c, clock, 6)
        self.assertEqual(snap.state, "track")


class AlertTests(unittest.TestCase):
    def test_player_too_close_to_a_box(self):
        c, clock, t = make(target=(0.15, 0.7))
        seen = set()
        for _ in range(400):
            seen.add(c.poll().alert); clock.advance()
        self.assertTrue(any("too close" in a for a in seen), seen)

    def test_two_players_pause(self):
        c, clock, t = make()
        t.target = lambda now, node: (0.25, 1.2) if node == 0 else (1.3, 1.2)
        seen = set()
        for _ in range(1200):
            seen.add(c.poll().alert); clock.advance()
        self.assertIn("Two players detected", seen)


if __name__ == "__main__":
    unittest.main()
