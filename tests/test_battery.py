"""Battery reports: parsed from the firmware's broadcast, kept per box, exposed in the snapshot."""

import unittest

from whack.protocol import Battery, parse
from whack.swarm import SwarmController
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


def make():
    clock = Clock()
    g = Geometry(body_radius_m=0.18, smoothing_tau_s=0.25, local_search_s=1.0, sensor_y=0.5, extra_sensor_x=(0.75,))
    c = SwarmController(g, simulate=True, clock=clock)
    return c, clock, c.transport


class BatteryProtocolTests(unittest.TestCase):
    def test_broadcast_parses_as_the_firmware_formats_it(self):
        # main.cpp: snprintf("WM2 BATT %u %.2f %d", NODE_ID, voltage, percent)
        self.assertEqual(parse(b"WM2 BATT 1 4.87 42"), Battery(1, 4.87, 42))
        self.assertEqual(parse(b"WM2 BATT 0 5.50 100\n"), Battery(0, 5.5, 100))
        self.assertEqual(parse(b"WM2 BATT 2 0.00 0"), Battery(2, 0.0, 0))

    def test_rejects_malformed_reports(self):
        packets = [b"WM2 BATT 1 4.87 101", b"WM2 BATT 1 x 42", b"WM2 BATT 10 4.87 42", b"WM2 BATT 1 4.87",
                   b"WM2 BATT 1 4.87 -1", b"WM2 BATTERY 1 42", b"WM1 BATT 1 4.87 42", b"WM2 BATT 1 4.87 42 extra"]
        for packet in packets:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                parse(packet)


class BatteryTrackingTests(unittest.TestCase):
    def test_every_box_reports_once_a_second_and_the_snapshot_carries_it(self):
        c, clock, transport = make()
        snap = run(c, clock, 1.5)
        self.assertEqual(len(snap.battery), 3)
        for level in snap.battery:
            self.assertIsNotNone(level)
            percent, volts, age = level
            self.assertEqual(percent, 100)
            self.assertEqual(volts, 5.5)
            self.assertLessEqual(age, 1.0)
        self.assertEqual(c.battery_lowest(), (0, 100))

    def test_lowest_names_the_weakest_box(self):
        c, clock, transport = make()
        transport.battery_percent = [87, 42, 63]
        run(c, clock, 1.5)
        self.assertEqual(c.battery_lowest(), (1, 42))
        self.assertEqual(c.battery_levels()[1][:2], (42, SimulatedTransport.battery_volts(42)))

    def test_a_box_without_a_gauge_has_no_level(self):
        c, clock, transport = make()
        transport.battery_percent = [80, None, 60]
        snap = run(c, clock, 1.5)
        self.assertIsNone(snap.battery[1])
        self.assertEqual(c.battery_lowest(), (2, 60))

    def test_a_silent_box_goes_stale(self):
        c, clock, transport = make()
        run(c, clock, 1.5)
        transport.battery_percent = [None, None, None]
        snap = run(c, clock, SwarmController.BATTERY_STALE_S + 1)
        self.assertEqual(snap.battery, (None, None, None))
        self.assertIsNone(c.battery_lowest())

    def test_a_report_from_a_stranger_is_ignored(self):
        c, clock, transport = make()
        transport.battery_percent = [None, None, None]
        transport.messages.append((Battery(0, 4.5, 50), ("sim-9", 4211)))   # not box 0's address
        transport.messages.append((Battery(7, 4.5, 50), ("sim-0", 4211)))   # no such box
        snap = run(c, clock, 0.5)
        self.assertEqual(snap.battery, (None, None, None))

    def test_reports_do_not_disturb_tracking(self):
        c, clock, transport = make()
        transport.battery_percent = [5, 5, 5]
        snap = run(c, clock, 6)
        self.assertEqual(snap.state, "track")
        self.assertEqual(c.battery_lowest(), (0, 5))


if __name__ == "__main__":
    unittest.main()
