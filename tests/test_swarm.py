"""Leader-follower N-box controller against the timed simulator."""

import json
import math
import tempfile
import unittest
from dataclasses import asdict
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

    def test_a_failing_send_never_escapes_poll(self):
        for error in (OSError("network unreachable"), ValueError("bad packet")):
            with self.subTest(error=type(error).__name__):
                c, clock, t = make(target=self.DEAD_ZONE, buzzer_node=1)
                send, refused = t.send, []

                def failing(data, address, error=error, send=send, refused=refused):
                    if data.startswith(b"WM2 BUZZ"):
                        refused.append(data)
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
