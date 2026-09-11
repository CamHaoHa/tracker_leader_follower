import math
import unittest

from whack.protocol import Range
from whack.tracking import Geometry, Tracker, locate


def samples(g, point, now):
    return tuple((Range(n, n+1, g.angle(n,point), round(math.dist((x,g.sensor_y),point)*1000), "OK"),now)
                 for n,x in enumerate((g.left_x,g.right_x)))


class TrackingTests(unittest.TestCase):
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
        g = Geometry(); tracker=Tracker(g)
        a,b=samples(g,(.75,1.3),0)
        tracker.update(a,b,0)
        self.assertIsNotNone(tracker.position(.5))
        self.assertIsNone(tracker.position(1.01))
        tracker.update(a,(b[0],1),1)
        self.assertFalse(tracker.valid)
        wrong = Range(0,1,0,a[0].distance_mm,"OK")
        tracker.update((wrong,2),(b[0],2),2)
        self.assertFalse(tracker.valid)

    def test_deadzone_uses_raw_point_before_smoothing_or_speed_gate(self):
        g=Geometry(); tracker=Tracker(g)
        tracker.update(*samples(g,(.75,1.3),1),1)
        tracker.update(*samples(g,(.75,.4),1.1),1.1)
        self.assertTrue(tracker.dead_zone)
        self.assertFalse(tracker.in_bounds())
        self.assertGreater(tracker.filtered[1],.6)

    def test_jump_cannot_score_and_reacquires_after_loss(self):
        g=Geometry(); tracker=Tracker(g)
        tracker.update(*samples(g,(.1,1),1),1)
        tracker.update(*samples(g,(1.4,1),1.1),1.1)
        self.assertFalse(tracker.valid)
        tracker.update(*samples(g,(1.4,1),3),3)
        self.assertTrue(tracker.valid)

    def test_motion_skew_rejected_and_warning_release_hysteresis(self):
        g=Geometry(); tracker=Tracker(g)
        a,b=samples(g,(.75,1.3),0)
        tracker.update(a,(b[0],.8),.8)
        self.assertFalse(tracker.valid)
        tracker.update(*samples(g,(.75,.6),1),1)
        self.assertFalse(tracker.dead_zone)
        tracker.update(*samples(g,(.75,.5),2),2)
        self.assertTrue(tracker.dead_zone)
        tracker.update(*samples(g,(.75,.61),3),3)
        self.assertTrue(tracker.dead_zone)
        tracker.update(*samples(g,(.75,.64),4),4)
        self.assertFalse(tracker.dead_zone)


if __name__ == "__main__": unittest.main()
