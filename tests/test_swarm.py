"""Leader-follower N-box controller against the timed simulator."""

import json
import math
import tempfile
from types import SimpleNamespace
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from whack.swarm import SwarmController, fuse, Contribution
from whack.tracking import Geometry, load_geometry
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


class TravelTests(unittest.TestCase):
    def test_default_arcs_are_clipped_to_the_servo_travel(self):
        g = Geometry(servo_travel_deg=(30, 150), extra_sensor_x=(0.75,))
        self.assertEqual([g.sweep_bounds(n) for n in range(3)], [(30, 100), (30, 120), (80, 150)])

    def test_explicit_arcs_must_fit_the_travel(self):
        with self.assertRaises(ValueError):
            Geometry(servo_travel_deg=(30, 150), sweep_bounds_deg=((10, 100), (80, 150)))
        with self.assertRaises(ValueError):
            Geometry(servo_travel_deg=(150, 30))

    def test_travel_loads_from_json_as_a_pair(self):
        from whack.tracking import load_geometry
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.json"
            path.write_text(json.dumps({"servo_travel_deg": [30, 150], "sensor_y": 0.5}))
            self.assertEqual(load_geometry(str(path)).servo_travel_deg, (30, 150))

    def test_aims_never_leave_the_servo_travel(self):
        # Player near the right wall: node 0's true bearing is ~18 deg, past its 30 deg stop.
        c, clock, t = make(target=(1.4, 0.95), servo_travel_deg=(30, 150), extra_sensor_x=(0.75,))
        snap = run(c, clock, 6)
        self.assertEqual(snap.state, "track")
        sent = aims(t, 0)
        self.assertTrue(sent)
        self.assertTrue(all(30 <= a <= 150 for a in sent), sent)
        self.assertEqual(c.boxes[0].aimed_bearing, 30000)


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

    def test_loss_jitters_then_searches_then_resumes_the_sweep(self):
        c, clock, t = make()
        run(c, clock, 4)
        before = len(t.commands)
        t.target = None
        snap = run(c, clock, 9)
        self.assertEqual(snap.state, "find")
        modes = [b.mode for b in c.boxes]
        self.assertEqual(modes, ["sweep", "sweep"])
        later = [a//1000 for _, n, kind, _, a in t.commands[before:] if kind == "AIM" and n == 0]
        # jitter offsets of 8 deg appear first...
        self.assertTrue(any(abs(later[i+1]-later[i]) in (8, 16) for i in range(min(8, len(later)-1))), later[:10])
        # ...then the search in 15-degree steps, and 5-degree stepping resumes after it
        self.assertTrue(any(abs(b-a) == 15 for a, b in zip(later, later[1:])), later)
        tail = later[-4:]
        self.assertTrue(all(abs(tail[i+1]-tail[i]) == 5 for i in range(len(tail)-1)))


PROTOTYPE = Path(__file__).resolve().parents[1] / "config.prototype.json"
COLUMNS = {1: (0.25, 1.1), 2: (0.75, 1.1), 3: (1.25, 1.1)}      # the player's spot in front of each column
FAR_ROW = {1: (0.25, 1.7), 3: (1.25, 1.7)}


def prototype(target, **changes):
    """The three-box prototype field with a player already tracked at `target`."""
    clock = Clock()
    c = SwarmController(replace(load_geometry(str(PROTOTYPE)), **changes), simulate=True, clock=clock)
    c.transport.target = target
    run(c, clock, 6)
    return c, clock, c.transport


def reacquire(controller, clock, spot, limit=20):
    """Move the player to `spot`; seconds until the tracker reports a fix there."""
    controller.transport.target = spot
    start = clock.now
    for _ in range(round(limit/.01)):
        snap = controller.poll()
        if snap.position is not None and math.dist(snap.position, spot) < .25:
            return clock.now - start
        clock.advance()
    raise AssertionError("player not found again in the simulator")


def until_lost(controller, clock, seconds=3):
    """Poll until the player is declared lost; index of the first command sent from that poll on."""
    for _ in range(round(seconds/.01)):
        mark = len(controller.transport.commands)
        snap = controller.poll(); clock.advance()
        if snap.state == "find":
            return mark
    raise AssertionError("player not lost in the simulator")


def aims_since(transport, mark, node):
    return [a//1000 for _, n, kind, _, a in transport.commands[mark:] if kind == "AIM" and n == node]


class JumpTests(unittest.TestCase):
    """The player leaves every beam at once, e.g. jumps from column 1 to column 3."""

    def test_a_player_who_skips_a_column_is_found_again_quickly(self):
        # Before the search these took 3.3 to 9.1 simulated seconds.
        for a, b in ((COLUMNS[1], COLUMNS[3]), (COLUMNS[3], COLUMNS[1]),
                     (FAR_ROW[1], FAR_ROW[3]), (FAR_ROW[3], FAR_ROW[1])):
            with self.subTest(jump=(a, b)):
                c, clock, t = prototype(a)
                self.assertLess(reacquire(c, clock, b), 2.5)

    def test_a_step_to_the_next_column_is_no_slower(self):
        for a, b in ((1, 2), (2, 3), (2, 1), (3, 2)):
            with self.subTest(jump=(a, b)):
                c, clock, t = prototype(COLUMNS[a])
                self.assertLess(reacquire(c, clock, COLUMNS[b]), 1.5)

    def test_full_loss_searches_each_end_once_in_big_steps_then_sweeps(self):
        c, clock, t = prototype(COLUMNS[1])
        t.target = None
        mark = until_lost(c, clock)
        self.assertTrue(all(box.search and box.mode == "sweep" for box in c.boxes))   # no jitter left
        run(c, clock, 14)
        for node in range(3):
            with self.subTest(node=node):
                seq = aims_since(t, mark, node)
                self.assertTrue(all(0 <= a <= 180 for a in seq), seq)
                low, high = seq.index(0), seq.index(180)
                # Column 1 is on the high-bearing side of the field centre for
                # every box, so each searches downward, across the field, first.
                down = seq[:low+1]
                self.assertTrue(all(0 < a-b <= 15 for a, b in zip(down, down[1:])), down)
                self.assertEqual(seq[low:high+1], list(range(0, 181, 15)))
                after = seq[high:high+6]
                self.assertEqual(after, list(range(180, 150, -5)))
                self.assertFalse(c.boxes[node].search)

    def test_one_box_losing_the_player_still_jitters_and_starts_no_search(self):
        c, clock, t = prototype(COLUMNS[1])
        mark = len(t.commands)
        t.target = lambda now, node: None if node == 2 else COLUMNS[1]
        for _ in range(600):
            snap = c.poll(); clock.advance()
            self.assertEqual(snap.state, "track")
            self.assertFalse(any(box.search for box in c.boxes))
        seq = aims_since(t, mark, 2)
        steps = {abs(b-a) for a, b in zip(seq, seq[1:])}
        self.assertTrue(steps & {8, 16}, seq[:12])               # jitter round the aimed bearing
        self.assertIn(5, steps)                                  # then the plain sweep
        self.assertNotIn(15, steps)

    def test_search_step_equal_to_the_sweep_step_searches_in_sweep_steps(self):
        c, clock, t = prototype(COLUMNS[1], search_step_deg=5.0)
        t.target = None
        mark = until_lost(c, clock)
        run(c, clock, 4)
        seq = aims_since(t, mark, 1)
        self.assertGreater(len(seq), 5)
        self.assertTrue(all(abs(b-a) <= 5 for a, b in zip(seq, seq[1:])), seq)

    def test_search_step_limits(self):
        for bad in (4.0, 46.0):
            with self.assertRaises(ValueError):
                Geometry(search_step_deg=bad)
        self.assertNotIn("search_step_deg", SwarmController.LAYOUT_FIELDS)   # a saved map stays valid


class ExpectTests(unittest.TestCase):
    """The game says where it expects the player (the mole's column)."""

    def test_after_a_loss_every_box_looks_at_the_expected_spot_first(self):
        c, clock, t = prototype(COLUMNS[1])
        c.expect(COLUMNS[3])
        t.target = COLUMNS[3]
        start = clock.now
        mark = until_lost(c, clock)
        poll_while(c, clock, 3, lambda snap: snap.state == "track")
        self.assertLess(clock.now - start, 1.5)
        for node in range(3):
            first = next(a for _, n, kind, _, a in t.commands[mark:] if kind == "AIM" and n == node)
            self.assertEqual(first, c.geometry.angle(node, COLUMNS[3]))

    def test_a_wrong_expectation_only_costs_one_look(self):
        for a, b, wrong in ((1, 3, 2), (3, 1, 2), (1, 2, 3)):
            with self.subTest(jump=(a, b), expected=wrong):
                c, clock, t = prototype(COLUMNS[a])
                c.expect(COLUMNS[wrong])
                self.assertLess(reacquire(c, clock, COLUMNS[b]), 2.5)

    def test_an_expectation_is_never_reported_as_the_position(self):
        c, clock, t = prototype(COLUMNS[1])
        c.expect(COLUMNS[3])
        t.target = None
        until_lost(c, clock)
        for _ in range(500):
            snap = c.poll(); clock.advance()
            self.assertEqual(snap.state, "find")
            self.assertIsNone(snap.position)

    def test_a_point_outside_the_field_or_none_withdraws_it(self):
        c, clock, t = prototype(COLUMNS[1])
        c.expect(COLUMNS[3])
        self.assertEqual(c.expected, COLUMNS[3])
        c.expect((2.0, 1.1))
        self.assertIsNone(c.expected)
        c.expect(COLUMNS[3]); c.expect(None)
        self.assertIsNone(c.expected)
        c.expect(COLUMNS[3]); c.start_acquisition()              # a new search forgets it too
        self.assertIsNone(c.expected)


def field_controller(background):
    """A controller on the real-network path (the empty-room map is used) with a simulated transport."""
    clock = Clock()
    g = replace(load_geometry(str(PROTOTYPE)), sweep_bounds_deg=((30, 100), (30, 120), (80, 150)),
                servo_travel_deg=(30, 150))
    t = SimulatedTransport(clock, g)
    with tempfile.TemporaryDirectory() as temp:
        c = SwarmController(g, clock=clock, transport=t, calibration_path=Path(temp)/"none.json")
    c.background = {f"{n}:{b}": None for n in range(c.count) for b in c._grid(n)}
    c.background.update(background)
    return c, clock, t


def echo(degrees, metres, status="OK"):
    return SimpleNamespace(status=status, distance_mm=round(metres*1000), angle_mdeg=round(degrees*1000))


class StaticEchoTests(unittest.TestCase):
    """An object of the empty-room map: box 0 heard 0.62 m at 30 and 35 degrees (the field on 5 October)."""

    def setUp(self):
        self.c, self.clock, _ = field_controller({"0:30000": .62, "0:35000": .62})
        self.box = self.c.boxes[0]

    def kind(self, degrees, metres):
        return self.c._classify(self.box, echo(degrees, metres), self.clock.now)[0]

    def test_the_object_is_background_at_its_bearings_and_next_to_them(self):
        for degrees in (30, 33, 35, 41, 45):
            with self.subTest(degrees=degrees):
                self.assertEqual(self.kind(degrees, .62), "none")
        self.assertEqual(self.kind(33, .70), "none")                 # within background_margin_m of it
        self.assertEqual(self.box.rejections["background"], 6)

    def test_further_round_or_further_out_it_is_something_else(self):
        self.assertEqual(self.kind(46, .62), "candidate")            # more than 10 degrees from 35
        self.assertEqual(self.kind(70, .62), "candidate")

    def test_an_echo_beyond_the_object_is_not_background(self):
        # The object did not answer this ping, so something behind it did:
        # the player, 1.40 m away, where the old map test threw everything away.
        self.assertEqual(self.kind(33, 1.40), "candidate")
        self.assertEqual(self.kind(33, 1.41), "reliable")


class ConfirmTests(unittest.TestCase):
    def setUp(self):
        self.c, self.clock, _ = field_controller({})
        self.box = self.c.boxes[1]

    def kind(self, degrees, metres, status="OK"):
        self.clock.advance(.2)
        return self.c._classify(self.box, echo(degrees, metres, status), self.clock.now)[0]

    def test_a_missed_ping_does_not_forget_the_last_echo(self):
        self.assertEqual(self.kind(90, .87), "candidate")
        self.assertEqual(self.kind(90, 0, "TIMEOUT"), "none")
        self.assertEqual(self.kind(90, .88), "reliable")

    def test_a_reading_confirms_one_up_to_two_jitter_offsets_round(self):
        self.assertEqual(self.c.confirm_mdeg, 16000)                # jitter_deg 8
        self.assertEqual(self.kind(90, .87), "candidate")
        self.assertEqual(self.kind(98, .87), "reliable")             # jittered one way
        self.assertEqual(self.kind(82, .88), "reliable")             # and the other
        self.assertEqual(self.kind(103, .88), "candidate")           # 21 degrees on
        self.assertEqual(self.kind(103, 1.0), "candidate")           # another range

    def test_an_old_echo_confirms_nothing(self):
        self.assertEqual(self.kind(90, .87), "candidate")
        self.clock.advance(1.5)
        self.assertEqual(self.kind(90, .87), "candidate")


class AgreementTests(unittest.TestCase):
    PLAYER = (1.25, 1.42)                   # the hole the player stood on, in the tracker frame
    OBJECT = (0.61, 1.01)                   # where box 0's echo of the object puts him: 0.80 m at 40 degrees

    def setUp(self):
        self.c, self.clock, _ = field_controller({})
        self.clock.now = 10.0

    def reading(self, node, point, bearing_towards=None, age=0.0):
        g = self.c.geometry
        aim = g.angle(node, bearing_towards or point)
        return Contribution(node, self.clock.now - age, aim, math.dist(g.sensor_position(node), point), point)

    def track_with_boxes_1_and_2(self):
        for node in (1, 2):
            self.assertTrue(self.c._absorb(self.reading(node, self.PLAYER, age=.1), self.clock.now))
        self.assertEqual(set(self.c.contributions), {1, 2})
        return self.c.estimate.point

    def test_a_crossing_outside_a_beam_is_a_ghost(self):
        g = self.c.geometry
        # Box 0's 0.80 m circle crosses box 1's circle of the player at (0.07, 1.30):
        # the ranges agree there, but box 0 was aimed at 40 degrees, not 85.
        ghost = [self.reading(0, (0.067, 1.297), bearing_towards=self.OBJECT), self.reading(1, self.PLAYER)]
        point, worst = fuse(g, ghost)
        self.assertLess(worst, .05)
        self.assertIsNone(self.c._agreement(ghost))
        true = [self.reading(1, self.PLAYER), self.reading(2, self.PLAYER)]
        self.assertLess(math.dist(self.c._agreement(true), self.PLAYER), .01)

    def test_two_boxes_that_still_see_the_player_outvote_a_third(self):
        before = self.track_with_boxes_1_and_2()
        self.assertFalse(self.c._absorb(self.reading(0, self.OBJECT), self.clock.now))
        self.assertEqual(self.c.estimate.point, before)
        self.assertEqual(set(self.c.contributions), {1, 2})
        self.assertEqual(self.c.boxes[0].rejections["outvoted"], 1)

    def test_the_newest_reading_wins_when_the_others_have_missed_since(self):
        self.track_with_boxes_1_and_2()
        self.c.boxes[2].last_no_hit = self.clock.now          # box 2 lost him: he may have moved
        self.assertTrue(self.c._absorb(self.reading(0, self.OBJECT), self.clock.now))
        self.assertEqual(set(self.c.contributions), {0})

    def test_a_reading_is_kept_with_the_boxes_it_agrees_with(self):
        self.track_with_boxes_1_and_2()
        moved = (1.20, 1.45)
        self.c.contributions[2] = self.reading(2, self.OBJECT, age=.1)    # box 2's last reading was something else
        self.assertTrue(self.c._absorb(self.reading(1, moved), self.clock.now))
        self.assertTrue(self.c._absorb(self.reading(0, moved), self.clock.now))
        self.assertEqual(set(self.c.contributions), {0, 1})


class StandStillTests(unittest.TestCase):
    """The player stands still where box 0 hears the middle box next to its mapped bearings (tools/stand_bench.py)."""

    def test_the_player_is_held_while_standing_still(self):
        from tools import stand_bench as bench
        geometry = bench.field_geometry(str(PROTOTYPE))
        spot = (1.25, 1.42)                         # the hole stood on in the field, tracker frame
        after = [bench.stand("after", geometry, spot, 30, .15, .3, seed) for seed in range(3)]
        before = [bench.stand("before", geometry, spot, 30, .15, .3, seed) for seed in range(3)]
        self.assertLessEqual(bench.mean(after, "losses_per_min"), 2.0)
        self.assertEqual(bench.mean(after, "jumps_per_min"), 0.0)
        self.assertGreaterEqual(bench.mean(after, "on_hole"), .95)
        # The scene reproduces what was seen on the boxes with the old tracker.
        self.assertGreaterEqual(bench.mean(before, "losses_per_min"), 8.0)
        self.assertGreater(bench.mean(before, "jumps_per_min"), 2.0)


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


def poll_while(controller, clock, seconds, condition):
    """Poll until `condition(snapshot)` holds; fail the caller's assumption otherwise."""
    for _ in range(round(seconds/.01)):
        snap = controller.poll(); clock.advance()
        if condition(snap):
            return snap
    raise AssertionError("condition not reached in the simulator")


class BuzzerTests(unittest.TestCase):
    DEAD_ZONE = (0.75, 0.55)
    IN_FIELD = (0.75, 1.3)

    def alarm(self, target=DEAD_ZONE, text="Player in the dead zone", **geometry):
        geometry.setdefault("buzzer_node", 1)
        c, clock, t = make(target=target, **geometry)
        poll_while(c, clock, 8, lambda snap: snap.alert == text)
        return c, clock, t

    def test_buzzer_node_must_be_none_or_a_box(self):
        self.assertEqual(Geometry().buzzer_node, -1)
        self.assertEqual(Geometry(buzzer_node=1).buzzer_node, 1)
        self.assertEqual(Geometry(buzzer_node=2, extra_sensor_x=(0.75,)).buzzer_node, 2)
        for bad in (2, -2, 1.0, True, "1", None):
            with self.subTest(buzzer_node=bad), self.assertRaises((ValueError, TypeError)):
                Geometry(buzzer_node=bad)

    def test_buzzer_node_loads_from_json(self):
        from whack.tracking import load_geometry
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.json"
            path.write_text(json.dumps({"extra_sensor_x": [0.75], "sensor_y": 0.5, "buzzer_node": 1}))
            self.assertEqual(load_geometry(str(path)).buzzer_node, 1)
            path.write_text(json.dumps({"buzzer_node": 2}))          # only two boxes
            with self.assertRaises(ValueError):
                load_geometry(str(path))

    def test_example_config_names_the_buzzer_box(self):
        from whack.tracking import load_geometry
        example = Path(__file__).resolve().parents[1] / "config.example.json"
        self.assertEqual(load_geometry(str(example)).buzzer_node, 1)

    def test_dead_zone_sounds_the_buzzer_repeatedly_then_silences_it_once(self):
        c, clock, t = self.alarm()
        self.assertEqual(t.buzzes, [(t.buzzes[0][0], 1, 400)])     # at once, to the buzzer box
        for _ in range(200):                                       # two seconds in the dead zone
            snap = c.poll(); clock.advance()
            self.assertEqual(snap.alert, "Player in the dead zone")
            self.assertTrue(t.buzzing(1))                          # never lapses between repeats
        self.assertTrue(all((n, d) == (1, 400) for _, n, d in t.buzzes), t.buzzes)
        gaps = [b[0]-a[0] for a, b in zip(t.buzzes, t.buzzes[1:])]
        self.assertEqual(len(gaps), 10)
        self.assertTrue(all(abs(gap-.2) < .011 for gap in gaps), gaps)

        t.target = self.IN_FIELD                                   # the player steps back
        poll_while(c, clock, 6, lambda snap: not snap.alert)
        self.assertEqual(t.buzzes[-1][1:], (1, 0))
        self.assertEqual([d for _, _, d in t.buzzes].count(0), 1)
        self.assertFalse(t.buzzing(1))
        sent = len(t.buzzes)
        run(c, clock, 3)                                           # tracking goes on, silently
        self.assertEqual(len(t.buzzes), sent)

    def test_too_close_to_a_box_sounds_the_buzzer(self):
        c, clock, t = self.alarm(target=(0.15, 0.7), text="Player too close to box 0")
        run(c, clock, 1)
        self.assertGreaterEqual(len(t.buzzes), 5)
        self.assertTrue(all((n, d) == (1, 400) for _, n, d in t.buzzes), t.buzzes)

    def test_three_boxes_buzz_only_the_middle_one(self):
        c, clock, t = self.alarm(extra_sensor_x=(0.75,))
        run(c, clock, 1)
        self.assertTrue(t.buzzes)
        self.assertEqual({n for _, n, _ in t.buzzes}, {1})

    def test_no_buzzer_node_sends_nothing(self):
        for target, text in ((self.DEAD_ZONE, "Player in the dead zone"),
                             ((0.15, 0.7), "Player too close to box 0")):
            with self.subTest(alert=text):
                c, clock, t = self.alarm(target=target, text=text, buzzer_node=-1)
                run(c, clock, 2)
                c.pause(); c.close()
                self.assertEqual(t.buzzes, [])

    def test_other_alerts_do_not_sound_the_buzzer(self):
        c, clock, t = self.alarm(target=(0.75, 2.2), text="Player outside the field")
        run(c, clock, 2)
        self.assertEqual(t.buzzes, [])
        c, clock, t = make(buzzer_node=1)
        t.target = lambda now, node: (0.25, 1.2) if node == 0 else (1.3, 1.2)
        poll_while(c, clock, 10, lambda snap: snap.alert == "Two players detected")
        run(c, clock, 1)
        self.assertEqual(t.buzzes, [])

    def test_pause_reset_and_close_silence_once(self):
        for action in ("pause", "reset", "close", "start_acquisition"):
            with self.subTest(action=action):
                c, clock, t = self.alarm()
                run(c, clock, .5)
                getattr(c, action)()
                self.assertEqual(t.buzzes[-1][1:], (1, 0))          # without waiting for a poll
                self.assertFalse(t.buzzing(1))
                if action != "close":
                    t.target = None
                    run(c, clock, 3)
                self.assertEqual([d for _, _, d in t.buzzes].count(0), 1)
                self.assertEqual(t.buzzes[-1][1:], (1, 0))

    def test_paused_controller_stays_silent_while_the_alert_is_shown(self):
        c, clock, t = self.alarm(target=(0.15, 0.7), text="Player too close to box 0")
        c.pause()
        sent = len(t.buzzes)
        snap = run(c, clock, 1)
        self.assertEqual(snap.alert, "Player too close to box 0")
        self.assertEqual(len(t.buzzes), sent)

    def test_a_box_that_stops_reporting_cannot_keep_the_buzzer_sounding(self):
        # Only a later reading from box 0 withdraws "too close to box 0". If the
        # box goes offline or quiet it never sends one: the report must age out.
        for fault in ("offline", "quiet"):
            with self.subTest(fault=fault):
                c, clock, t = self.alarm(target=(0.15, 0.7), text="Player too close to box 0",
                                         extra_sensor_x=(0.75,))
                run(c, clock, .5)
                self.assertTrue(t.buzzing(1))
                if fault == "offline":
                    t.address = lambda node: None if node == 0 else (f"sim-{node}", 4211)
                else:                                              # still listed, replies lost
                    receive = t.receive
                    t.receive = lambda receive=receive: [(m, a) for m, a in receive() if m.node != 0]
                t.target = self.IN_FIELD                           # the player steps back
                poll_while(c, clock, 5, lambda snap: not snap.alert)
                self.assertEqual(t.buzzes[-1][1:], (1, 0))
                self.assertFalse(t.buzzing(1))
                sent = len(t.buzzes)
                snap = run(c, clock, 10)                           # boxes 1 and 2 carry on, silently
                self.assertEqual(snap.alert, "")
                self.assertEqual(len(t.buzzes), sent)
                self.assertEqual([d for _, _, d in t.buzzes].count(0), 1)
                self.assertEqual((c.too_close_since, c.too_close_seen), ({}, {}))

    def test_a_box_that_keeps_reporting_keeps_the_alert(self):
        c, clock, t = self.alarm(target=(0.15, 0.7), text="Player too close to box 0")
        self.assertGreater(8, c.TOO_CLOSE_STALE_S + c.ALERT_LATCH_S)
        for _ in range(800):                                       # well past the ageing limit
            snap = c.poll(); clock.advance()
            self.assertEqual(snap.alert, "Player too close to box 0")
        self.assertTrue(t.buzzing(1))
        self.assertNotIn(0, [d for _, _, d in t.buzzes])

    def test_resume_is_silent_when_the_player_stepped_back_during_the_pause(self):
        c, clock, t = self.alarm(target=(0.15, 0.7), text="Player too close to box 0")
        run(c, clock, .5)
        c.pause()
        self.assertEqual(t.buzzes[-1][1:], (1, 0))
        sent = len(t.buzzes)
        t.target = self.IN_FIELD
        snap = run(c, clock, 5)
        self.assertEqual(snap.alert, "")                           # the banner ends with its latch
        c.resume()
        for _ in range(300):
            snap = c.poll(); clock.advance()
            self.assertEqual(snap.alert, "")
        self.assertEqual(snap.state, "track")
        self.assertEqual(len(t.buzzes), sent)

    def test_calibration_start_silences_the_buzzer(self):
        clock = Clock()
        g = Geometry(body_radius_m=0.18, smoothing_tau_s=0.25, local_search_s=1.0, sensor_y=0.5,
                     buzzer_node=1)
        t = SimulatedTransport(clock, g); t.target = (0.15, 0.7)
        with tempfile.TemporaryDirectory() as temp:
            c = SwarmController(g, clock=clock, transport=t, calibration_path=Path(temp)/"cal.json")
            c.background = {f"{n}:{b}": None for n in (0, 1) for b in c._grid(n)}   # a loaded map
            poll_while(c, clock, 8, lambda snap: snap.alert == "Player too close to box 0")
            run(c, clock, .5)
            c.start_calibration()
            self.assertEqual(t.buzzes[-1][1:], (1, 0))
            run(c, clock, 2)                                       # the stale alert stays silent
            self.assertTrue(c.calibrating)
            self.assertEqual([d for _, _, d in t.buzzes].count(0), 1)
            self.assertEqual(t.buzzes[-1][1:], (1, 0))

    def test_offline_or_old_buzzer_box_gets_nothing(self):
        for fault in ("offline", "old firmware"):
            with self.subTest(fault=fault):
                c, clock, t = make(target=self.DEAD_ZONE, buzzer_node=1, extra_sensor_x=(0.75,))
                if fault == "offline":
                    t.address = lambda node: None if node == 1 else (f"sim-{node}", 4211)
                else:
                    t.protocol_version = lambda node: 1 if node == 1 else 2
                poll_while(c, clock, 10, lambda snap: snap.alert == "Player in the dead zone")
                run(c, clock, 1)
                self.assertEqual(t.buzzes, [])

    def test_a_send_that_recovers_sounds_at_the_next_interval(self):
        c, clock, t = make(target=self.DEAD_ZONE, buzzer_node=1)
        send, down = t.send, [True]

        def flaky(data, address):
            if down[0] and data.startswith(b"WM2 BUZZ"):
                raise OSError("network unreachable")
            send(data, address)
        t.send = flaky
        poll_while(c, clock, 8, lambda snap: snap.alert == "Player in the dead zone")
        run(c, clock, .5)
        self.assertEqual(t.buzzes, [])
        down[0] = False
        run(c, clock, .21)
        self.assertEqual([b[1:] for b in t.buzzes], [(1, 400)])
        self.assertTrue(t.buzzing(1))

    def test_a_failing_send_never_escapes_poll(self):
        for error in (OSError("network unreachable"), ValueError("bad packet")):
            with self.subTest(error=type(error).__name__):
                c, clock, t = make(target=self.DEAD_ZONE, buzzer_node=1)
                send, refused, times = t.send, [], []

                def failing(data, address, error=error, send=send, refused=refused, times=times,
                            clock=clock):
                    if data.startswith(b"WM2 BUZZ"):
                        refused.append(data); times.append(clock.now)
                        raise error
                    send(data, address)
                t.send = failing
                poll_while(c, clock, 8, lambda snap: snap.alert == "Player in the dead zone")
                pings = len(t.ping_times)
                run(c, clock, 1)
                c.pause(); c.close()
                self.assertTrue(refused)
                self.assertEqual(set(refused), {b"WM2 BUZZ 400"})     # never sounded: no BUZZ 0 owed
                self.assertGreater(len(t.ping_times), pings)          # tracking carried on
                # Retried at the BUZZ interval, not on every 10 ms poll.
                self.assertIn(len(refused), (5, 6), times)
                gaps = [b-a for a, b in zip(times, times[1:])]
                self.assertTrue(all(abs(gap-.2) < .011 for gap in gaps), gaps)

    def test_buzz_stays_out_of_the_acoustic_schedule(self):
        quiet, clock_q, tq = make(target=self.DEAD_ZONE)
        loud, clock_l, tl = make(target=self.DEAD_ZONE, buzzer_node=1)
        quiet.seq = loud.seq = 1000          # the start is wall-clock based: make them comparable
        run(quiet, clock_q, 8); run(loud, clock_l, 8)
        self.assertTrue(tl.buzzes)
        self.assertEqual(tl.ping_times, tq.ping_times)               # same pings, same instants
        self.assertEqual(tl.commands, tq.commands)                   # same AIM/FIRE, same sequences
        self.assertEqual(loud.seq, quiet.seq)                        # BUZZ uses no sequence number
        gaps = [b[0]-a[0] for a, b in zip(tl.ping_times, tl.ping_times[1:])]
        self.assertGreaterEqual(min(gaps), 0.065)


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

    def test_naming_the_buzzer_box_keeps_a_saved_map_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"cal.json"
            clock = Clock()
            before = Geometry(sensor_y=0.5, body_radius_m=0.18, extra_sensor_x=(0.75,))
            t = SimulatedTransport(clock, before)
            first = SwarmController(before, clock=clock, transport=t, calibration_path=path)
            background = {f"{n}:{b}": 1.5 for n in range(3) for b in first._grid(n)}
            saved = first._json(asdict(before))
            del saved["buzzer_node"]                 # a map written before the field existed
            path.write_text(json.dumps({"version": 3, "geometry": saved, "background": background}))
            for buzzer_node in (-1, 1):
                after = Geometry(sensor_y=0.5, body_radius_m=0.18, extra_sensor_x=(0.75,),
                                 buzzer_node=buzzer_node)
                loaded = SwarmController(after, clock=clock, transport=t, calibration_path=path)
                self.assertEqual(loaded.background, background)
                self.assertEqual(loaded.calibration_message, "")


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
