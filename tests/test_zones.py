"""Player versus player: the field split into zones, each tracked by its own boxes."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from whack.protocol import Range, aim, fire
from whack.swarm import SwarmController
from whack.tracking import Geometry, load_geometry
from whack.transport import SimulatedTransport


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


# Four boxes on the wall at x = 0, 0.75, 0.85 and 1.5 m. The two middle boxes sit
# back to back: box 1 looks into the left half only, box 2 into the right half.
ARCS = ((10, 90), (90, 170), (10, 90), (90, 150))
ZONES = ((0, 0.75, (0, 1)), (0.75, 1.5, (2, 3)))
A, B = (0.35, 1.3), (1.15, 1.2)          # one player on each half


def pvp(players=(A, B), **geometry):
    clock = Clock()
    g = Geometry(body_radius_m=0.18, smoothing_tau_s=0.25, local_search_s=1.0, sensor_y=0.5,
                 extra_sensor_x=(0.75, 0.85), sweep_bounds_deg=ARCS, zones=ZONES, **geometry)
    c = SwarmController(g, simulate=True, clock=clock)
    c.transport.players = list(players)
    return c, clock, c.transport


def run(controller, clock, seconds):
    snap = None
    for _ in range(round(seconds/.01)):
        snap = controller.poll(); clock.advance()
    return snap


def snapshots(controller, clock, seconds):
    for _ in range(round(seconds/.01)):
        yield controller.poll()
        clock.advance()


class ZoneGeometryTests(unittest.TestCase):
    def test_no_zones_means_one_zone_of_the_whole_field_and_every_box(self):
        g = Geometry(extra_sensor_x=(0.75,))
        self.assertEqual(g.zone_count, 1)
        self.assertEqual(g.zone_bounds(0), (0.0, 1.5))
        self.assertEqual(g.zone_nodes(0), (0, 1, 2))
        self.assertEqual([g.zone_of(n) for n in range(3)], [0, 0, 0])
        self.assertEqual(g.zone_at(0.3), 0)
        self.assertIsNone(g.zone_at(2.0))

    def test_two_zones_name_their_boxes_and_a_shared_edge_goes_to_the_lower_one(self):
        g = Geometry(extra_sensor_x=(0.75, 0.85), zones=ZONES)
        self.assertEqual(g.zone_count, 2)
        self.assertEqual([g.zone_of(n) for n in range(4)], [0, 0, 1, 1])
        self.assertEqual(g.zone_nodes(1), (2, 3))
        self.assertEqual(g.zone_bounds(1), (0.75, 1.5))
        self.assertEqual(g.zone_at(0.75), 0)
        self.assertEqual(g.zone_at(1.0), 1)

    def test_every_box_belongs_to_exactly_one_zone_and_zones_do_not_overlap(self):
        for bad in (
            ((0, 0.75, (0, 1)),),                               # boxes 2 and 3 in no zone
            ((0, 0.75, (0, 1, 2)), (0.75, 1.5, (2, 3))),        # box 2 in two zones
            ((0, 0.8, (0, 1)), (0.7, 1.5, (2, 3))),             # overlap
            ((0.75, 1.5, (2, 3)), (0, 0.75, (0, 1))),           # not ordered along x
            ((0, 0.75, (0, 1)), (0.75, 1.6, (2, 3))),           # past the field
            ((0.75, 0, (0, 1)), (0.75, 1.5, (2, 3))),           # x reversed
            ((0, 0.75, ()), (0.75, 1.5, (0, 1, 2, 3))),         # an empty zone
        ):
            with self.subTest(zones=bad), self.assertRaises(ValueError):
                Geometry(extra_sensor_x=(0.75, 0.85), zones=bad)
        with self.assertRaises(ValueError):
            Geometry(zone_margin_m=2)

    def test_node_x_numbers_the_boxes_by_firmware_id_instead_of_left_to_right(self):
        # The three prototype boxes keep nodes 0, 1, 2; the fourth box is node 3 at 0.85 m.
        g = Geometry(extra_sensor_x=(0.75, 0.85), node_x=(0.0, 0.75, 1.5, 0.85))
        self.assertEqual([g.sensor_x(n) for n in range(4)], [0.0, 0.75, 1.5, 0.85])
        self.assertEqual(g.sensor_position(3), (0.85, 0.2))
        self.assertEqual([g.sweep_bounds(n) for n in range(4)],            # default arcs follow position
                         [(10, 100), (30, 120), (80, 170), (30, 120)])
        for bad in ((0.0, 0.75, 1.5), (0.0, 0.75, 1.5, 0.9), (0.0, 0.75, 1.5, 1.5), (0.0, 0.75, 1.5, True)):
            with self.subTest(node_x=bad), self.assertRaises(ValueError):
                Geometry(extra_sensor_x=(0.75, 0.85), node_x=bad)

    def test_zones_load_from_json_as_objects_or_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.json"
            path.write_text(json.dumps({"extra_sensor_x": [0.75, 0.85],
                                        "zones": [{"x": [0, 0.75], "nodes": [0, 1]}, [0.75, 1.5, [2, 3]]]}))
            self.assertEqual(load_geometry(str(path)).zones, ZONES)
            path.write_text(json.dumps({"zones": [{"x": [0, 1.5]}]}))
            with self.assertRaises(ValueError):
                load_geometry(str(path))


class TwoPlayerTrackingTests(unittest.TestCase):
    def test_each_zone_tracks_its_own_player_with_its_own_boxes(self):
        c, clock, t = pvp()
        snap = run(c, clock, 6)
        self.assertEqual(len(snap.zones), 2)
        for zone, player in zip(snap.zones, (A, B)):
            self.assertEqual(zone.state, "track")
            self.assertEqual(zone.contributors, 2)
            self.assertLess(math.dist(zone.position, player), 0.15)
        self.assertEqual(snap.zones[0].node_status, snap.node_status[:2])
        self.assertEqual(snap.zones[1].node_status, snap.node_status[2:])
        # the top level is player 1, and the status names both players
        self.assertEqual(snap.position, snap.zones[0].position)
        self.assertEqual(snap.status, "P1: Tracking player | P2: Tracking player")
        # every box was aimed into its own half only
        for box in c.boxes:
            lo, hi = c.geometry.zone_bounds(c.geometry.zone_of(box.node))
            self.assertTrue(lo - .2 <= box.aimed_point[0] <= hi + .2, (box.node, box.aimed_point))

    def test_a_box_ignores_the_other_zones_player(self):
        # Nobody on the left half: box 0 sweeping low bearings hears the right
        # half's player at 1.35 m, and must not call him its own.
        c, clock, t = pvp(players=(None, B))
        for snap in snapshots(c, clock, 6):
            self.assertEqual(snap.zones[0].state, "find")
            self.assertIsNone(snap.zones[0].position)
        self.assertEqual(snap.zones[1].state, "track")
        self.assertGreater(c.boxes[0].rejections.get("other zone", 0), 0)
        self.assertIsNone(snap.position)                       # the top level is player 1
        self.assertTrue(snap.status.startswith("P1: Searching"), snap.status)

    def test_one_player_leaving_does_not_disturb_the_other(self):
        c, clock, t = pvp()
        run(c, clock, 6)
        t.players = [A, None]
        for snap in snapshots(c, clock, 4):
            self.assertEqual(snap.zones[0].state, "track")
        self.assertEqual(snap.zones[0].contributors, 2)
        self.assertEqual(snap.zones[1].state, "find")
        self.assertTrue(all(c.boxes[n].search or c.boxes[n].mode == "sweep" for n in (2, 3)))
        self.assertTrue(all(c.boxes[n].mode == "aimed" for n in (0, 1)))

    def test_players_move_independently(self):
        c, clock, t = pvp()
        run(c, clock, 6)
        t.players = [(0.5, 1.7), (1.3, 1.6)]
        snap = run(c, clock, 3)
        self.assertLess(math.dist(snap.zones[0].position, (0.5, 1.7)), 0.15)
        self.assertLess(math.dist(snap.zones[1].position, (1.3, 1.6)), 0.15)

    def test_pings_never_overlap_with_four_boxes(self):
        c, clock, t = pvp()
        run(c, clock, 8)
        gaps = [b[0]-a[0] for a, b in zip(t.ping_times, t.ping_times[1:])]
        self.assertGreaterEqual(min(gaps), 0.065)
        self.assertGreater(len(t.ping_times), 40)

    def test_an_expectation_goes_to_the_zone_of_its_x(self):
        c, clock, t = pvp()
        c.expect((1.2, 1.4))
        self.assertEqual([z.expected for z in c.zones], [None, (1.2, 1.4)])
        c.expect((0.3, 1.4))
        self.assertEqual([z.expected for z in c.zones], [(0.3, 1.4), (1.2, 1.4)])
        self.assertEqual(c.expected, (0.3, 1.4))              # the single-player view is zone 0
        c.expect(None, zone=1)
        self.assertEqual([z.expected for z in c.zones], [(0.3, 1.4), None])
        c.expect((1.2, 1.4)); c.expect(None)
        self.assertEqual([z.expected for z in c.zones], [None, None])
        c.expect((2.0, 1.4))                                   # outside the field: nothing
        self.assertEqual([z.expected for z in c.zones], [None, None])

    def test_after_a_loss_a_zones_boxes_look_where_its_player_is_expected(self):
        c, clock, t = pvp()
        run(c, clock, 6)
        target = (1.3, 1.7)
        c.expect(target)
        t.players = [A, None]
        run(c, clock, 2)                                       # player 2 lost: his boxes search
        mark = len(t.commands)
        t.players = [A, target]
        run(c, clock, 3)
        for node in (2, 3):
            first = next(a for _, n, kind, _, a in t.commands[mark - 300:] if kind == "AIM" and n == node
                         and a == c.geometry.angle(node, target))
            self.assertEqual(first, c.geometry.angle(node, target))
        self.assertEqual(c.boxes[0].aimed_point, c.boxes[1].aimed_point)   # player 1's boxes stayed on him


class ZoneAlertTests(unittest.TestCase):
    def test_a_dead_zone_alert_belongs_to_its_zone_and_reaches_the_top(self):
        # Four boxes share the air, so each sweeps at about 3 pings/s and box 0
        # needs most of 6 s to step down from 90 to the 10 degree bearing.
        c, clock, t = pvp(players=((0.375, 0.55), B), buzzer_node=1)
        alerts = [[], []]
        tops = set()
        for snap in snapshots(c, clock, 10):
            for z, zone in enumerate(snap.zones):
                alerts[z].append(zone.alert)
            tops.add(snap.alert)
        self.assertIn("Player in the dead zone", alerts[0])
        self.assertEqual(set(alerts[1]), {""})
        self.assertIn("Player in the dead zone", tops)
        self.assertTrue(t.buzzes)                              # a near-wall alert in any zone sounds the buzzer

    def test_too_close_names_the_box_of_the_other_zone(self):
        c, clock, t = pvp(players=(A, (1.0, 0.65)))            # 3 cm from box 2's surface
        seen = [set(), set()]
        for snap in snapshots(c, clock, 4):
            for z, zone in enumerate(snap.zones):
                seen[z].add(zone.alert)
        self.assertIn("Player too close to box 2", seen[1])
        self.assertEqual(seen[0], {""})


class SinglePlayerViewTests(unittest.TestCase):
    def test_one_zone_carries_itself_as_zone_zero(self):
        clock = Clock()
        c = SwarmController(Geometry(body_radius_m=0.18, sensor_y=0.5), simulate=True, clock=clock)
        snap = run(c, clock, 4)
        self.assertEqual(snap.state, "track")
        self.assertEqual(len(snap.zones), 1)
        only = snap.zones[0]
        self.assertEqual(only.zones, ())
        self.assertEqual((only.position, only.status, only.node_status, only.state, only.contributors),
                         (snap.position, snap.status, snap.node_status, snap.state, snap.contributors))

    def test_set_simulated_position_moves_one_player(self):
        c, clock, t = pvp()
        c.set_simulated_position(0.5, 1.5, 1)
        self.assertEqual(t.players, [A, (0.5, 1.5)])
        c.set_simulated_position(float("nan"), 1.5, 0)
        self.assertEqual(t.players, [A, (0.5, 1.5)])
        clock = Clock()
        single = SwarmController(Geometry(), simulate=True, clock=clock)
        single.set_simulated_position(0.3, 1.0)
        self.assertEqual(single.transport.target, (0.3, 1.0))
        self.assertIsNone(single.transport.players)


class SimulatedPlayersTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.transport = SimulatedTransport(self.clock, Geometry())
        self.addCleanup(self.transport.close)

    def ping(self, seq):
        self.transport.send(aim(seq, 60000), self.transport.address(0))
        self.clock.now += .151
        self.transport.receive()
        self.transport.send(fire(seq), self.transport.address(0))
        self.clock.now += .2
        return [m for m, _ in self.transport.receive() if isinstance(m, Range)][0]

    def test_the_echo_is_the_nearest_player_in_the_beam(self):
        near = (0.4*math.cos(math.radians(60)), 0.2 + 0.4*math.sin(math.radians(60)))
        far = (1.0*math.cos(math.radians(60)), 0.2 + 1.0*math.sin(math.radians(60)))
        self.transport.players = [far, near]
        self.assertEqual(self.ping(1).distance_mm, 400)
        self.transport.players = [far, None]
        self.assertEqual(self.ping(2).distance_mm, 1000)
        self.transport.players = [None, None]
        self.assertEqual(self.ping(3).status, "TIMEOUT")

    def test_set_player_keeps_the_others(self):
        self.transport.set_player(1, (0.5, 1.0))
        self.assertEqual(self.transport.players, [None, (0.5, 1.0)])
        self.transport.set_player(0, (0.2, 1.0))
        self.assertEqual(self.transport.players, [(0.2, 1.0), (0.5, 1.0)])


if __name__ == "__main__":
    unittest.main()
