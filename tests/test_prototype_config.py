"""The tracked three-box field config that lets a fresh clone run the prototype."""

import math
import unittest
from pathlib import Path

from whack.swarm import SwarmController
from whack.tracking import load_geometry


PROTOTYPE = Path(__file__).resolve().parents[1] / "config.prototype.json"


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


class PrototypeConfigTests(unittest.TestCase):
    def test_it_loads_as_the_three_box_field(self):
        geometry = load_geometry(str(PROTOTYPE))
        self.assertEqual(geometry.sensor_count, 3)
        self.assertEqual([geometry.sensor_x(node) for node in range(3)], [0.0, 0.75, 1.5])
        self.assertEqual(geometry.sensor_y, 0.5)
        self.assertEqual(tuple(geometry.servo_travel_deg), (0, 180))
        self.assertEqual(geometry.buzzer_node, 1)

    def test_a_simulated_player_in_the_middle_of_the_field_is_tracked(self):
        geometry = load_geometry(str(PROTOTYPE))
        middle = (geometry.width/2, (geometry.near_y + geometry.far_y)/2)
        clock = Clock()
        controller = SwarmController(geometry, simulate=True, clock=clock)
        try:
            controller.transport.target = middle
            snap = None
            for _ in range(600):            # six simulated seconds
                snap = controller.poll()
                clock.advance()
            self.assertEqual(snap.state, "track")
            self.assertTrue(snap.in_bounds)
            self.assertLess(math.dist(snap.position, middle), 0.15)
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
