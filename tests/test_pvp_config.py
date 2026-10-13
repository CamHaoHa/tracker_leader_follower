"""The tracked four-box, two-zone field config for player versus player."""

import math
import unittest
from pathlib import Path

from whack.swarm import SwarmController
from whack.tracking import load_geometry


PVP = Path(__file__).resolve().parents[1] / "config.pvp.json"


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


class PvpConfigTests(unittest.TestCase):
    def test_it_loads_as_two_halves_with_two_boxes_each(self):
        geometry = load_geometry(str(PVP))
        self.assertEqual(geometry.sensor_count, 4)
        self.assertEqual([geometry.sensor_x(node) for node in range(4)], [0.0, 0.75, 0.85, 1.5])
        self.assertEqual(geometry.zone_count, 2)
        self.assertEqual([geometry.zone_nodes(z) for z in range(2)], [(0, 1), (2, 3)])
        self.assertEqual([geometry.zone_bounds(z) for z in range(2)], [(0.0, 0.75), (0.75, 1.5)])
        # the middle pair sit back to back and look away from each other
        self.assertEqual(geometry.sweep_bounds(1), (90, 170))
        self.assertEqual(geometry.sweep_bounds(2), (10, 90))
        self.assertEqual(geometry.buzzer_node, 1)

    def test_a_simulated_player_in_the_middle_of_each_half_is_tracked(self):
        geometry = load_geometry(str(PVP))
        clock = Clock()
        controller = SwarmController(geometry, simulate=True, clock=clock)
        try:
            players = controller.transport.players       # one per zone, in the middle of its half
            self.assertEqual(players, [(0.375, 1.3), (1.125, 1.3)])
            snap = None
            for _ in range(600):            # six simulated seconds
                snap = controller.poll()
                clock.advance()
            for zone, player in zip(snap.zones, players):
                self.assertEqual(zone.state, "track")
                self.assertTrue(zone.in_bounds)
                self.assertEqual(zone.contributors, 2)
                self.assertLess(math.dist(zone.position, player), 0.15)
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
