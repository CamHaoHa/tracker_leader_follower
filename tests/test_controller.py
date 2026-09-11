import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from whack.controller import Controller
from whack.protocol import Range
from whack.tracking import Geometry
from whack.transport import SimulatedTransport


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def advance(self, dt=.01): self.now += dt


def run(controller, clock, seconds):
    result = None
    for _ in range(round(seconds/.01)):
        result=controller.poll(); clock.advance()
    return result


class InjectedTransport(SimulatedTransport):
    inbox = None
    def receive(self):
        result=self.inbox or []; self.inbox=[]
        return result


class ControllerTests(unittest.TestCase):
    def test_simulated_acquisition_and_loss(self):
        clock=Clock(); c=Controller(simulate=True,clock=clock)
        snap=run(c,clock,3)
        self.assertTrue(snap.in_bounds)
        self.assertAlmostEqual(snap.position[0],.75,places=2)
        c.transport.target=None
        snap=run(c,clock,2)
        self.assertIsNone(snap.position)
        self.assertFalse(snap.in_bounds)
        self.assertTrue(all(a[1]!=b[1] for a,b in zip(c.transport.sent,c.transport.sent[1:])))
        self.assertTrue(all(b[0]-a[0]>=.12 for a,b in zip(c.transport.sent,c.transport.sent[1:])))

    def test_acquisition_covers_near_edges_and_deadzone(self):
        for point in ((0,.6),(1.5,.6),(.05,.65),(1.45,.65),(.75,.4)):
            with self.subTest(point=point):
                clock=Clock(); c=Controller(Geometry(beam_half_angle_deg=15),simulate=True,clock=clock)
                c.transport.target=point
                found=False
                for _ in range(6000):
                    snap=c.poll();clock.advance()
                    if snap.position is not None:
                        found=True;break
                self.assertTrue(found)
                self.assertEqual(snap.dead_zone,point[1]<.6)

    def test_wrong_address_sequence_and_stale_pair_rejected(self):
        clock=Clock(); t=InjectedTransport(clock,Geometry())
        c=Controller(simulate=True,clock=clock,transport=t)
        c.poll();node,seq,angle,address,deadline=c.pending
        for message,source in [(Range(0,seq+1,angle,1300,"OK"),address),
                               (Range(0,seq,angle,1300,"OK"),("other",4211)),
                               (Range(1,seq,angle,1300,"OK"),address)]:
            t.inbox=[(message,source)];c.poll()
            self.assertEqual(c.pending[1],seq)
        clock.advance(1.01);c.poll()
        self.assertIsNone(c.pending)
        t.inbox=[(Range(0,seq,angle,1300,"OK"),address)];c.poll()
        self.assertEqual(c.samples,{})

    def test_hardware_requires_calibration_and_bad_profile_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=Clock();t=SimulatedTransport(clock,Geometry())
            path=Path(temp)/"cal.json"
            c=Controller(clock=clock,transport=t,calibration_path=path)
            self.assertIn("Calibrate",c.poll().status)
            self.assertEqual(t.sent,[])
            path.write_text(json.dumps({"version":1,"geometry":asdict(Geometry()),"background":{"0:90":float('nan')}}))
            c=Controller(clock=clock,transport=t,calibration_path=path)
            self.assertEqual(c.background,{})

    def test_calibration_timeout_echo_is_empty_but_dropped_packet_aborts(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=Clock();t=SimulatedTransport(clock,Geometry());t.target=None
            path=Path(temp)/"cal.json"
            c=Controller(clock=clock,transport=t,calibration_path=path)
            c.start_calibration();run(c,clock,120)
            self.assertFalse(c.calibrating)
            self.assertTrue(path.exists())
            self.assertTrue(c.background)
            self.assertTrue(all(v is None for v in c.background.values()))
            t=InjectedTransport(clock,Geometry());c=Controller(clock=clock,transport=t,calibration_path=path)
            c.start_calibration();run(c,clock,5)
            self.assertFalse(c.calibrating)
            self.assertFalse(c.background)
            self.assertIn("interrupted",c.poll().status)

    def test_starting_calibration_discards_in_flight_tracking_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=Clock();t=SimulatedTransport(clock,Geometry());t.target=None
            c=Controller(simulate=True,clock=clock,transport=t,calibration_path=Path(temp)/"cal.json")
            c.poll();c.simulate=False;c.start_calibration()
            run(c,clock,2)
            self.assertEqual(c.samples,{})
            self.assertEqual(c.calibration_index,0)

    def test_unprofiled_bearing_never_bypasses_background_filter(self):
        clock=Clock(); c=Controller(simulate=True,clock=clock)
        c.background={"0:90000":1.5}
        self.assertFalse(c._foreground((Range(0,1,60000,1000,"OK"),0)))
        self.assertFalse(c._foreground((Range(0,1,90000,1400,"OK"),0)))
        self.assertTrue(c._foreground((Range(0,1,90000,1000,"OK"),0)))

    def test_invalid_servo_reply_can_report_unchanged_angle(self):
        clock=Clock();t=InjectedTransport(clock,Geometry());c=Controller(simulate=True,clock=clock,transport=t)
        c.poll();node,seq,angle,address,_=c.pending
        t.inbox=[(Range(node,seq,90000,0,"INVALID"),address)];c.poll()
        self.assertIsNone(c.pending)
        self.assertEqual(c.node_status[0],"invalid")


if __name__ == "__main__": unittest.main()
