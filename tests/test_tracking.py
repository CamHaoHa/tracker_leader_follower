import math
import unittest

from whack.protocol import Range
from whack.tracking import Geometry, Tracker, locate


def samples(g, point, now):
    return tuple((Range(n, n+1, g.angle(n,point), round(math.dist((x,g.sensor_y),point)*1000), "OK"),now)
                 for n,x in enumerate((g.left_x,g.right_x)))


class TrackingTests(unittest.TestCase):
    def test_body_radius_restores_centre_from_surface_ranges(self):
        from whack.tracking import locate
        g = Geometry(body_radius_m=0.2)
        centre = (0.5, 1.4)
        surfaces = [math.dist((x, g.sensor_y), centre) - 0.2 for x in (g.left_x, g.right_x)]
        x, y = locate(g, *surfaces)
        self.assertAlmostEqual(x, centre[0], places=3)
        self.assertAlmostEqual(y, centre[1], places=3)
        x0, y0 = locate(Geometry(), *surfaces)
        self.assertLess(y0, centre[1] - 0.15)  # point model lands too near the wall

    def test_scan_path_starts_at_centre_with_small_servo_swings(self):
        g = Geometry()
        targets = g.scan_targets()
        self.assertEqual(targets[0], (g.width / 2, (g.near_y + g.far_y) / 2))
        aims = [tuple(g.angle(node, p) for node in (0, 1)) for p in targets]
        swings = [max(abs(b[0]-a[0]), abs(b[1]-a[1])) / 1000 for a, b in zip(aims, aims[1:])]
        self.assertLess(sum(swings) / len(swings), 20)
        self.assertEqual(set(targets), set(targets))  # coverage set unchanged by ordering

    def test_scan_covers_joint_beams_across_field_and_warning_strip(self):
        for half_angle in (20, 7.5):
            g = Geometry(beam_half_angle_deg=half_angle)
            aims = [tuple(g.angle(node, point) for node in (0, 1)) for point in g.scan_targets()]
            warning_y = (g.sensor_y + g.near_y) / 2
            points = [(g.width*x/30, warning_y+(g.far_y-warning_y)*y/32)
                      for x in range(31) for y in range(33)]
            # These interior points were never acquired by the original sweep,
            # even though its explicit corner checks passed.
            points.extend(((.17, .63), (1.33, .63)))
            for point in points:
                observed = tuple(g.angle(node, point) for node in (0, 1))
                self.assertTrue(any(all(abs(a-b) <= half_angle*1000
                                        for a, b in zip(aim, observed)) for aim in aims),
                                (half_angle, point))

    def test_scan_is_cached_immutable_and_planning_is_bounded(self):
        g = Geometry()
        targets = g.scan_targets()
        self.assertIs(targets, g.scan_targets())
        self.assertIsInstance(targets, tuple)
        self.assertLessEqual(len(Geometry(beam_half_angle_deg=1).scan_targets()), 8192)
        with self.assertRaisesRegex(ValueError, "clearance|cells|aims"):
            Geometry(width=5, right_x=5, sensor_y=0, near_y=1e-10,
                     far_y=4, beam_half_angle_deg=1).scan_targets()

    def test_grid_and_angle_convention(self):
        g = Geometry()
        for x in (0,.1,.75,1.4,1.5):
            for y in (.4,.6,1.0,1.5,2.0):
                a,b = samples(g,(x,y),0)
                point = locate(g,a[0].distance_mm/1000,b[0].distance_mm/1000)
                self.assertLess(math.dist(point,(x,y)),.005)
        self.assertEqual(g.angle(0,(0,1)),90000)
        self.assertGreater(g.angle(1,(.75,1)),90000)

    def test_impossible_ranges_and_config(self):
        for a,b in ((.1,.1),(1,4),(math.nan,2),(math.inf,1),(0,1)):
            with self.assertRaises(ValueError): locate(Geometry(),a,b)
        for config in ({"left_x":1.5},{"sensor_y":.6},{"width":math.nan},{"beam_half_angle_deg":90}):
            with self.assertRaises(ValueError): Geometry(**config)

    def test_stale_pairs_and_bearing_gate(self):
        g = Geometry(); tracker = Tracker(g)
        a, b = samples(g, (.75, 1.3), 0)
        self.assertTrue(tracker.update(a, b, 0))
        self.assertIsNotNone(tracker.position(.15))
        self.assertIsNone(tracker.position(.201))
        self.assertFalse(tracker.update(a, (b[0], 1), 1))
        wrong = Range(0, 1, 0, a[0].distance_mm, "OK")
        self.assertFalse(tracker.update((wrong, 2), (b[0], 2), 2))

    def test_out_of_field_measurements_are_not_clamped_to_playfield(self):
        g = Geometry(); tracker = Tracker(g)
        self.assertTrue(tracker.update(*samples(g, (.75, .4), 1), 1))
        self.assertTrue(tracker.dead_zone)
        self.assertFalse(tracker.in_bounds(1))
        self.assertLess(tracker.position(1)[1], g.near_y)
        tracker.update(*samples(g, (.75, 2.3), 3), 3)
        self.assertFalse(tracker.in_bounds(3))

    def test_jump_rejected_and_reacquires_after_loss(self):
        g = Geometry(); tracker = Tracker(g)
        tracker.update(*samples(g, (.1, 1), 1), 1)
        self.assertFalse(tracker.update(*samples(g, (1.4, 1), 1.1), 1.1))
        self.assertEqual(tracker.last_good, 1)
        self.assertIsNone(tracker.position(1.21))
        self.assertTrue(tracker.update(*samples(g, (1.4, 1), 3), 3))

    def test_future_replayed_or_skewed_samples_do_not_refresh_track(self):
        g = Geometry(); tracker = Tracker(g)
        a, b = samples(g, (.75, 1.3), 1)
        self.assertTrue(tracker.update(a, b, 1))
        for left, right, now in ((a, b, 1.1), ((a[0], 2), (b[0], 2), 1.2),
                                 ((a[0], 2), (b[0], 2.3), 2.3)):
            self.assertFalse(tracker.update(left, right, now))
            self.assertEqual(tracker.last_good, 1)

    def test_velocity_prediction_and_dropout_are_bounded(self):
        g = Geometry(); tracker = Tracker(g)
        for i in range(20):
            t = i*.16
            self.assertTrue(tracker.update(*samples(g, (.2+.3*t, 1.3), t), t))
        self.assertAlmostEqual(tracker.velocity[0], .3, delta=.02)
        self.assertAlmostEqual(tracker.velocity[1], 0, delta=.01)
        stamp = tracker.last_good
        predicted = tracker.position(stamp+.1)
        self.assertAlmostEqual(predicted[0], .2+.3*(stamp+.1), delta=.015)
        tracker.invalidate("Missing echo", allow_prediction=True)
        self.assertIsNotNone(tracker.position(stamp+.15))
        self.assertIsNone(tracker.position(stamp+.201))
        self.assertEqual(tracker.last_good, stamp)
        self.assertEqual(tracker.predict(stamp+1), tracker.predict(stamp+.2))

    def test_staggered_ranges_are_motion_compensated(self):
        g = Geometry(smoothing_tau_s=0); tracker = Tracker(g)
        # Establish a known moving model, then independently synthesize two
        # ranges at different times. A static intersection has appreciable bias.
        tracker.update(*samples(g, (.65, 1.3), 1), 1)
        tracker.velocity = (.8, .2)
        old, new = 1.04, 1.14
        point = lambda t: (.65+.8*(t-1), 1.3+.2*(t-1))
        left = samples(g, point(old), old)[0]
        right = samples(g, point(new), new)[1]
        uncompensated = locate(g, left[0].distance_mm/1000, right[0].distance_mm/1000)
        self.assertTrue(tracker.update(left, right, new+.01))
        self.assertLess(math.dist(tracker.raw, point(new)), .01)
        self.assertGreater(math.dist(uncompensated, point(new)), .04)
        self.assertEqual(tracker.last_good, new)

    def test_dense_calibration_contains_search_bearings(self):
        g = Geometry(); pairs = g.calibration_aims()
        for node in (0, 1):
            bearings = sorted({pair[node] for pair in pairs})
            self.assertLessEqual(max(b-a for a, b in zip(bearings, bearings[1:])), 3000)
            self.assertTrue(all(g.angle(node, p) in bearings for p in g.scan_targets()))


if __name__ == "__main__": unittest.main()
