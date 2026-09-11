"""Single-flight acquisition scheduler; all network work runs without blocking Tk."""

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import statistics
import time

from .protocol import MAX_SEQUENCE, measure
from .tracking import Geometry, Tracker
from .transport import SimulatedTransport, UdpTransport


@dataclass(frozen=True)
class Snapshot:
    position: tuple[float, float] | None
    status: str
    node_status: tuple[str, str]
    dead_zone: bool
    in_bounds: bool


class Controller:
    def __init__(self, geometry=None, simulate=False, clock=time.monotonic, transport=None,
                 calibration_path="calibration.local.json", port=4210, node_ips=None):
        self.geometry = geometry or Geometry()
        self.clock, self.simulate = clock, simulate
        self.transport = transport or (SimulatedTransport(clock, self.geometry) if simulate else
                                       UdpTransport(clock, port, node_ips))
        self.tracker = Tracker(self.geometry)
        self.seq = int(time.time() * 1000) & MAX_SEQUENCE or 1
        self.pending = None
        self.next_send = 0.0
        self.samples = {}
        self.target = self.geometry.scan_targets()[0]
        self.hold_target = False
        self.scan_index = 0
        self.node_status = ["Waiting for left sensor", "Waiting for right sensor"]
        self.calibration_path = Path(calibration_path)
        self.background = {}
        self.calibrating = False
        self.calibration_index = 0
        self.calibration_samples = {}
        self.calibration_failed = False
        self.calibration_message = ""
        self.calibration_skip_seq = None
        if not simulate and self.calibration_path.exists():
            try:
                profile = json.loads(self.calibration_path.read_text())
                if profile["version"] != 1 or profile["geometry"] != asdict(self.geometry):
                    raise ValueError("Geometry changed")
                self.background = profile["background"]
                if not isinstance(self.background, dict):
                    raise ValueError("Background must be an object")
                expected = {f"{n}:{self.geometry.angle(n,p)}"
                            for p in self.geometry.scan_targets() for n in (0,1)}
                if set(self.background) != expected or any(
                    value is not None and (isinstance(value, bool) or not isinstance(value, (int,float))
                                           or not math.isfinite(value) or not 0.02 <= value <= 4.5)
                    for value in self.background.values()
                ):
                    raise ValueError("Invalid background ranges")
            except (ValueError, KeyError, TypeError, OSError):
                self.background = {}
                self.calibration_message = "Calibration unreadable or geometry changed; calibrate again"

    def start_calibration(self):
        if self.simulate or self.calibrating:
            return
        # Wait for any existing command to finish before moving to the calibration sweep.
        self.calibrating = True
        self.calibration_index = 0
        self.calibration_samples = {}
        self.calibration_failed = False
        self.calibration_skip_seq = self.pending[1] if self.pending else None
        self.background = {}
        self.samples.clear()
        self.next_send = max(self.next_send, self.clock() + 3.0)
        self.tracker.invalidate("Clear the area — calibration begins in three seconds")

    def set_simulated_position(self, x, y):
        if self.simulate and math.isfinite(x) and math.isfinite(y):
            self.transport.target = (x, y)

    def _next_sequence(self):
        self.seq = self.seq % MAX_SEQUENCE + 1
        return self.seq

    def _foreground(self, sample):
        r = sample[0]
        if r.status != "OK":
            return False
        nearby = [(abs(int(key.split(":")[1])-r.angle_mdeg), value)
                  for key,value in self.background.items() if key.startswith(f"{r.node}:")]
        if not nearby:
            return self.simulate
        delta, background = min(nearby, key=lambda p:p[0])
        # Profiles are valid only around measured bearings; acquisition always uses exact bearings.
        return delta <= 1 and (background is None or r.distance_mm / 1000 < background - 0.15)

    def _complete_pair(self, now):
        left, right = self.samples[0], self.samples[1]
        if self.calibrating:
            for node, (r, _) in self.samples.items():
                key = f"{node}:{r.angle_mdeg}"
                self.calibration_samples.setdefault(key, []).append(r.distance_mm/1000 if r.status == "OK" else None)
                if r.status == "INVALID":
                    self.calibration_failed = True
            self.calibration_index += 1
            if self.calibration_index >= len(self.geometry.scan_targets()) * 3:
                if self.calibration_failed:
                    self.calibration_message = "Calibration failed; check servo limits and retry"
                else:
                    self.background = {k: statistics.median([v for v in vs if v is not None])
                                       if sum(v is not None for v in vs) >= 2 else None
                                       for k,vs in self.calibration_samples.items()}
                    try:
                        self.calibration_path.write_text(json.dumps({"version":1,"geometry":asdict(self.geometry),
                                                                    "background":self.background},indent=2))
                        self.calibration_message = ""
                    except OSError as exc:
                        self.background = {}
                        self.calibration_message = f"Could not save calibration: {exc}"
                self.calibrating = False
                self.scan_index = 0
        else:
            if abs(left[1] - right[1]) > self.geometry.max_pair_skew_s:
                self.tracker.invalidate("Measurements too far apart — measuring again")
                self.hold_target = True
                self.samples.clear()
                return
            if self._foreground(left) and self._foreground(right):
                self.tracker.update(left, right, now)
            else:
                self.tracker.invalidate("No foreground player — searching")
            if not self.tracker.valid:
                self.scan_index = (self.scan_index + 1) % len(self.geometry.scan_targets())
        self.samples.clear()

    def poll(self):
        now = self.clock()
        try:
            messages = self.transport.receive()
        except OSError as exc:
            self.tracker.invalidate(f"Network receive failed: {exc}")
            messages = []
        for message,address in messages:
            if not self.pending:
                continue
            node, seq, angle, expected_address, deadline = self.pending
            if (message.node, message.seq, address) != (node,seq,expected_address):
                continue
            if message.status == "OK" and message.angle_mdeg != angle:
                continue
            if now > deadline:
                continue
            self.transport.seen(node,address)
            self.node_status[node] = (f"{message.distance_mm/1000:.2f} m" if message.status == "OK" else message.status.lower())
            self.pending = None
            self.next_send = max(self.next_send, now + 0.065)
            # Discard in-flight data if a new calibration was requested mid-pair.
            if seq == self.calibration_skip_seq:
                self.calibration_skip_seq = None
                continue
            self.samples[node] = (message, now)
            if set(self.samples) == {0,1}:
                self._complete_pair(now)
        if self.pending and now > self.pending[4]:
            node = self.pending[0]
            self.node_status[node] = "No response"
            self.pending = None
            self.samples.clear()
            # Servo has a bounded700ms settle +25ms echo; deadline leaves ample guard.
            self.next_send = max(self.next_send, now + 0.1)
            self.tracker.invalidate("Sensor did not respond — check power and Wi-Fi")
            if self.calibrating:
                self.calibrating = False
                self.background = {}
                self.calibration_message = "Calibration interrupted; check both sensors and retry"
        addresses = [self.transport.address(n) for n in (0,1)]
        if None in addresses:
            self.tracker.invalidate("Waiting for two distinct sensors — check power and Wi-Fi")
            for n in (0,1):
                if addresses[n] is None:
                    self.node_status[n] = "Offline or duplicate ID"
        ready = self.simulate or bool(self.background) or self.calibrating
        if ready and all(addresses) and self.pending is None and now >= self.next_send:
            node = 1 if 0 in self.samples else 0
            if node == 0:
                if self.calibrating:
                    self.target = self.geometry.scan_targets()[self.calibration_index // 3]
                elif self.hold_target:
                    self.hold_target = False
                elif self.tracker.valid and now-self.tracker.last_good < 1.0:
                    self.target = self.tracker.raw
                else:
                    self.target = self.geometry.scan_targets()[self.scan_index]
            angle = self.geometry.angle(node,self.target)
            if self.background and not self.calibrating:
                # Only measure calibrated bearings; unprofiled directions cannot bypass rejection.
                angles = [int(key.split(":")[1]) for key in self.background if key.startswith(f"{node}:")]
                angle = min(angles,key=lambda candidate:abs(candidate-angle))
            seq = self._next_sequence()
            try:
                self.transport.send(measure(seq,angle),addresses[node])
                self.pending = (node,seq,angle,addresses[node],now+1.0)
            except (OSError,ValueError) as exc:
                self.samples.clear()
                self.next_send = now+0.5
                self.tracker.invalidate(f"Could not request measurement: {exc}")
        position = self.tracker.position(now)
        status = self.tracker.reason
        if self.calibrating:
            position = None
            status = f"Keep area empty — calibrating {self.calibration_index + 1}/{len(self.geometry.scan_targets()) * 3}"
        elif not ready:
            position = None
            status = self.calibration_message or "Clear the area, then select Calibrate empty area"
        elif self.tracker.dead_zone:
            status = "Step back from the screen"
        elif position is not None and not self.tracker.in_bounds():
            status = "Move inside the playing area"
        return Snapshot(position,status,tuple(self.node_status),self.tracker.dead_zone,
                        position is not None and self.tracker.in_bounds())

    def close(self):
        self.transport.close()
