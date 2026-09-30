"""Independent-sweep, leader-follower tracking for N ultrasonic boxes.

Runs on the LAPTOP next to controller.py (the paired two-box scheduler this
replaces on the leader-follower branch). Each box is driven on its own:

    sweep    step the servo 5 degrees at a time across the box's own arc,
             one ping per bearing, bouncing at the bounds
    aimed    point at the shared player estimate, whoever produced it
    jitter   dither around that bearing after misses, then go back to sweep

The first box with a RELIABLE echo (status OK, inside the reliable range,
nearer than the empty-room map, and repeated) becomes the leader: its aim and
range give a polar position estimate, and every other box is aimed at that
point at once, in range or not. Boxes that also see the player refine the
estimate: two or more ranges are combined by least squares over their
circles; a single range keeps a coarse polar fix.

Pings never overlap: one acoustic slot at a time with the 65 ms guard, exactly
as before. Servos move concurrently. The wire protocol is unchanged.

Alerts (for the game layer, shown as a banner by the UI): a player nearer
than min_player_range_m to a box, a player outside the field, and two
players (two mutually inconsistent reliable detections that persist). A
too-close report lasts only while its box keeps reporting it: it is dropped
when that box goes offline or quiet, and on pause.

Buzzer: while a near-wall alert is up (dead zone, or too close to a box) the
box named by geometry.buzzer_node is sent WM2 BUZZ again and again, and one
BUZZ 0 when that ends. BUZZ is not a ping and has no part in the acoustic
schedule. The box silences itself if the laptop stops asking.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import statistics
import time

from .controller import Snapshot
from .protocol import MAX_SEQUENCE, Range, Ready, aim, buzz, fire
from .tracking import Geometry
from .transport import SimulatedTransport, UdpTransport


@dataclass
class Transaction:
    """One AIM (and at most one FIRE) for one box."""
    seq: int
    angle: int
    address: tuple
    aim_time: float
    aim_sent: float
    ready: tuple | None = None      # (Ready message, receipt time)
    fire_time: float | None = None
    done: bool = False
    mode: str = "sweep"             # box mode when this ping was planned


@dataclass
class Box:
    node: int
    mode: str = "sweep"             # sweep | aimed | jitter
    bearing: int = 90000            # last commanded world bearing, millidegrees
    step: int = -5000               # sweep direction: negative = clockwise first
    txn: Transaction | None = None
    status: str = "Waiting for sensor"
    last_reading: tuple | None = None   # (bearing, distance_m, time) of the last OK echo
    hold_bearing: int | None = None     # repeat this bearing once to confirm a candidate
    last_hit: float = float("-inf")     # time of the last reliable detection
    jitter_started: float = float("-inf")
    jitter_index: int = 0
    aimed_bearing: int = 90000
    aimed_point: tuple | None = None    # estimate this box was last sent to look at
    aim_cooldown_until: float = float("-inf")  # after a failed jitter, sweep at least until then
    rejections: dict = field(default_factory=dict)  # reason -> count, diagnostics


@dataclass
class Contribution:
    node: int
    time: float
    bearing: int
    range_m: float           # to the body CENTRE (surface + body radius)
    point: tuple             # polar estimate from this box alone


class Estimate:
    """Smoothed position from the fused fixes. No extrapolation: the spot is
    the last measured point, lightly smoothed so one noisy ping cannot jump it.
    Leader-follower aims every box at this point and re-aims when it moves."""

    def __init__(self, geometry):
        self.g = geometry
        self.reset()

    def reset(self):
        self.point = None
        self.last_good = float("-inf")
        self.confidence = 0.0

    def update(self, point, stamp, contributors):
        g = self.g
        recent = self.point is not None and stamp - self.last_good <= g.local_search_s
        residual = 0.0
        if recent:
            dt = max(stamp - self.last_good, 0.001)
            residual = math.dist(point, self.point)
            if residual > g.max_speed_m_s*dt + .3:
                return False                      # nobody moves that fast: noise
            alpha = 1.0 if g.smoothing_tau_s == 0 else min(.9, max(.35, 1-math.exp(-dt/g.smoothing_tau_s)))
            # A single-box polar fix is coarse sideways: trust it less.
            if contributors < 2:
                alpha *= .5
            point = (self.point[0] + alpha*(point[0]-self.point[0]),
                     self.point[1] + alpha*(point[1]-self.point[1]))
        self.point = point
        self.last_good = stamp
        self.confidence = max(.1, min(1.0, 1.0-residual/.5)) * (1.0 if contributors >= 2 else .5)
        return True


def fuse(geometry, contributions):
    """Least-squares point from several range circles (Gauss-Newton).

    Starts from the mean of the polar estimates, which is already close, and
    refines a few steps. Returns (point, worst residual in metres).
    """
    g = geometry
    pts = [c.point for c in contributions]
    x = sum(p[0] for p in pts)/len(pts)
    y = sum(p[1] for p in pts)/len(pts)
    for _ in range(6):
        jtj = [[0.0, 0.0], [0.0, 0.0]]; jtr = [0.0, 0.0]
        for c in contributions:
            sx, sy = g.sensor_position(c.node)
            dx, dy = x-sx, y-sy
            dist = math.hypot(dx, dy)
            if dist < 1e-6:
                continue
            res = dist - c.range_m
            jx, jy = dx/dist, dy/dist
            jtj[0][0] += jx*jx; jtj[0][1] += jx*jy; jtj[1][0] += jx*jy; jtj[1][1] += jy*jy
            jtr[0] += jx*res; jtr[1] += jy*res
        det = jtj[0][0]*jtj[1][1] - jtj[0][1]*jtj[1][0]
        if abs(det) < 1e-9:
            break
        dxs = (jtj[1][1]*jtr[0] - jtj[0][1]*jtr[1])/det
        dys = (-jtj[1][0]*jtr[0] + jtj[0][0]*jtr[1])/det
        x -= dxs; y -= dys
        if abs(dxs) + abs(dys) < 1e-4:
            break
    y = max(y, g.sensor_y + .01)  # the player is in front of the sensor line
    worst = max(abs(math.dist((x, y), g.sensor_position(c.node)) - c.range_m) for c in contributions)
    return (x, y), worst


class SwarmController:
    ACOUSTIC_GUARD_S = .065
    ECHO_TIMEOUT_S = .025
    FIRE_TIMEOUT_S = .4
    AIM_TIMEOUT_S = 1.5
    AIM_RETRY_S = .3
    FUSE_WINDOW_S = .6          # contributions this fresh are combined
    REAIM_COOLDOWN_S = 2.0      # a box that jittered without success sweeps this long
    REAIM_MOVE_M = .3           # unless the estimate moved at least this far
    CONSISTENT_M = .10          # repeated reading tolerance
    RESIDUAL_M = .30            # a contribution further off than this is another object
    OUTSIDE_MARGIN_M = .10
    OUTSIDE_S = .5
    TWO_PLAYER_S = 1.0
    TOO_CLOSE_S = .3
    TOO_CLOSE_STALE_S = 1.5     # a too-close report is dropped when its box says nothing for this long
    ALERT_LATCH_S = 2.0         # an alert stays up at least this long
    BUZZ_MS = 400               # each BUZZ asks for this much sound...
    BUZZ_INTERVAL_S = .2        # ...and is repeated this often, so one lost packet is not heard
    DEAD_ZONE_ALERT = "Player in the dead zone"
    TOO_CLOSE_ALERT = "Player too close to box "     # followed by the node number
    PINGS_PER_CALIBRATION_BEARING = 3
    LAYOUT_FIELDS = ("width", "near_y", "far_y", "left_x", "right_x", "sensor_y", "extra_sensor_x",
                     "sweep_bounds_deg", "sweep_step_deg")

    def __init__(self, geometry=None, simulate=False, clock=time.monotonic, transport=None,
                 calibration_path="calibration.local.json", port=4210, node_ips=None,
                 start_mode="center", start_paused=False):
        self.geometry = geometry or Geometry()
        self.clock, self.simulate = clock, simulate
        self.transport = transport or (SimulatedTransport(clock, self.geometry) if simulate else
                                       UdpTransport(clock, port, node_ips))
        self.count = self.geometry.sensor_count
        self.boxes = [Box(n) for n in range(self.count)]
        self.seq = int(time.time()*1000) & MAX_SEQUENCE or 1
        self.step_mdeg = round(self.geometry.sweep_step_deg*1000)
        self.estimate = Estimate(self.geometry)
        self.contributions: dict[int, Contribution] = {}
        self.good_times = deque(maxlen=12)
        self.acoustic_safe_at = 0.0
        self.firing: int | None = None          # node with a ping in the air
        self.state = "find"
        self.reason = "Waiting for measurements"
        self.alert = ""
        self.alert_until = 0.0
        self.alert_since = {}
        self.buzzing = False                   # a BUZZ > 0 was sent and not yet followed by BUZZ 0
        self.buzz_sent_at = float("-inf")      # last attempt to request sound, sent or not
        self.buzz_address = None               # where the sound was last requested
        self.inconsistent = deque(maxlen=32)   # times two boxes disagreed about where the player is
        self.outside_since = None
        self.too_close_since = {}              # node -> when it began reporting a player too close
        self.too_close_seen = {}               # node -> its latest such report
        self.paused = self.idle_after_calibration = bool(start_paused)
        self.calibration_path = Path(calibration_path)
        self.background = {}
        self.calibrating = False
        self.calibration_samples = {}
        self.calibration_message = ""
        self.calibration_plan = {}      # node -> list of bearings still to do
        self.calibration_total = 0
        self.node_status = [f"Waiting for sensor {n}" for n in range(self.count)]
        self._load_calibration()
        for box in self.boxes:
            box.bearing = 90000

    # ----- persistence --------------------------------------------------
    def _grid(self, node):
        lo, hi = self.geometry.sweep_bounds(node)
        lo_m, hi_m = round(lo*1000), round(hi*1000)
        first = math.ceil(lo_m/self.step_mdeg)*self.step_mdeg
        return list(range(first, hi_m+1, self.step_mdeg))

    def _load_calibration(self):
        if self.simulate or not self.calibration_path.exists():
            return
        try:
            profile = json.loads(self.calibration_path.read_text())
            saved, current = profile["geometry"], asdict(self.geometry)
            if profile.get("version") != 3 or any(
                    self._json(saved.get(k)) != self._json(current[k]) for k in self.LAYOUT_FIELDS):
                raise ValueError("layout changed")
            expected = {f"{n}:{b}" for n in range(self.count) for b in self._grid(n)}
            background = profile["background"]
            if set(background) != expected or any(
                    v is not None and (not isinstance(v, (int, float)) or not .02 <= v <= 4.5)
                    for v in background.values()):
                raise ValueError("bad map")
            self.background = background
        except (ValueError, KeyError, TypeError, OSError):
            self.background = {}
            self.calibration_message = "Calibration unreadable or layout changed; calibrate again"

    @staticmethod
    def _json(value):
        return json.loads(json.dumps(value))

    # ----- operator controls ---------------------------------------------
    def start_calibration(self):
        if self.simulate or self.calibrating:
            return
        self._cancel_all()
        self._silence_buzzer()
        self.paused = False
        self.calibrating, self.state = True, "calibration"
        self.background = {}
        self.calibration_samples = {}
        self.calibration_message = ""
        self.calibration_plan = {n: [b for b in self._grid(n) for _ in range(self.PINGS_PER_CALIBRATION_BEARING)]
                                 for n in range(self.count)}
        self.calibration_total = sum(len(v) for v in self.calibration_plan.values())
        self.estimate.reset(); self.contributions.clear()
        for box in self.boxes:
            box.mode = "sweep"

    def start_acquisition(self):
        if self.calibrating:
            return
        self._clear_player()
        self.paused = False

    def pause(self):
        if self.paused:
            return
        self.paused = True
        self._cancel_all()
        self._silence_buzzer()
        self._forget_too_close()               # nothing is measured while paused: do not resume on old reports
        if self.calibrating:
            self.calibrating = False
            self.background = {}
            self.calibration_message = "Calibration cancelled; retry with the area empty"
            self.state = "find"
        self.park_servos()

    def resume(self):
        self.paused = False

    def set_simulated_position(self, x, y):
        """Mouse in the simulation window moves the ideal reflector."""
        if self.simulate and hasattr(self.transport, "target"):
            self.transport.target = (float(x), float(y))

    def reset(self):
        self.pause()
        self._clear_player()
        self.park_servos()

    def park_servos(self):
        for n in range(self.count):
            address = self.transport.address(n)
            if address and self.transport.protocol_version(n) == 2:
                try:
                    self.transport.send(aim(self._next_seq(), 90000), address)
                except (OSError, ValueError):
                    pass
                self.boxes[n].bearing = 90000

    def close(self):
        self._cancel_all()
        try:
            self._silence_buzzer()
            self.park_servos()
        finally:
            self.transport.close()

    def _clear_player(self):
        self._cancel_all()
        self._silence_buzzer()
        self.estimate.reset(); self.contributions.clear(); self.good_times.clear()
        self.state, self.reason, self.alert = "find", "Waiting for measurements", ""
        self.alert_since.clear(); self.outside_since = None; self._forget_too_close()
        for box in self.boxes:
            box.mode, box.hold_bearing, box.last_reading = "sweep", None, None

    def _cancel_all(self):
        for box in self.boxes:
            if box.txn and box.txn.fire_time is not None and not box.txn.done and box.txn.ready:
                ready, receipt = box.txn.ready
                self.acoustic_safe_at = max(self.acoustic_safe_at, receipt + ready.lease_ms/1000
                                            + self.ECHO_TIMEOUT_S + self.ACOUSTIC_GUARD_S)
            box.txn = None
        self.firing = None

    def _next_seq(self):
        self.seq = self.seq % MAX_SEQUENCE + 1
        return self.seq

    # ----- bearings -----------------------------------------------------
    def _bounds(self, node):
        lo, hi = self.geometry.sweep_bounds(node)
        return round(lo*1000), round(hi*1000)

    def _next_sweep_bearing(self, box):
        lo, hi = self._bounds(box.node)
        s = self.step_mdeg
        b = box.bearing
        if b % s != 0:
            b = b - b % s if box.step < 0 else b + (s - b % s)   # snap in the sweep direction
        else:
            b += box.step
        if b < lo or b > hi:
            box.step = -box.step                 # bounce: continue from where we are
            b = box.bearing - box.bearing % s + (box.step if box.bearing % s == 0 else (s if box.step > 0 else 0))
            if b < lo:
                b = math.ceil(lo/s)*s
            elif b > hi:
                b = math.floor(hi/s)*s
        return max(lo, min(hi, b))

    def _clamp_travel(self, node, bearing):
        # The firmware answers READY INVALID for a bearing outside its travel
        # and the box then pings nothing. Aim as close as the servo can get.
        lo, hi = self.geometry.servo_travel_deg
        return max(round(lo*1000), min(round(hi*1000), bearing))

    def _choose_bearing(self, box, now):
        g = self.geometry
        if self.calibrating:
            plan = self.calibration_plan.get(box.node) or []
            return plan[0] if plan else None
        if box.hold_bearing is not None:            # repeat once to confirm a candidate
            b, box.hold_bearing = box.hold_bearing, None
            return b
        estimate = self.estimate.point
        fresh = now - self.estimate.last_good <= g.local_search_s
        if box.mode == "aimed" and estimate is not None and fresh:
            box.aimed_bearing = self._clamp_travel(box.node, g.angle(box.node, estimate))
            return box.aimed_bearing
        if box.mode == "jitter":
            if now - box.jitter_started <= g.jitter_s:
                offsets = (0, round(g.jitter_deg*1000), -round(g.jitter_deg*1000))
                offset = offsets[box.jitter_index % len(offsets)]
                box.jitter_index += 1
                return self._clamp_travel(box.node, box.aimed_bearing + offset)
            box.mode = "sweep"          # jitter exhausted: resume the sweep from here
            box.aim_cooldown_until = now + self.REAIM_COOLDOWN_S
        if box.mode == "aimed":
            box.mode = "sweep"
        return self._next_sweep_bearing(box)

    # ----- readings -----------------------------------------------------
    def _background_at(self, node, bearing):
        exact = self.background.get(f"{node}:{bearing}", ...)
        if exact is not ...:
            return exact, True
        # nearest grid bearing within one step
        best = None
        for b in self._grid(node):
            if abs(b - bearing) <= self.step_mdeg and (best is None or abs(b-bearing) < abs(best-bearing)):
                best = b
        if best is None:
            return None, False
        return self.background.get(f"{node}:{best}"), True

    def _classify(self, box, message, now):
        """Return ('reliable', d) | ('candidate', d) | ('hint', d) | ('close', d) | ('none', None)."""
        g = self.geometry
        if message.status != "OK":
            box.last_reading = None
            return "none", None
        d = message.distance_mm/1000
        if d < g.min_player_range_m:
            return "close", d
        if self.background and not self.simulate:
            baseline, known = self._background_at(box.node, message.angle_mdeg)
            if known and baseline is not None and d >= baseline - g.background_margin_m:
                box.rejections["background"] = box.rejections.get("background", 0) + 1
                box.last_reading = None
                return "none", d
        if d > g.reliable_range_m:
            box.last_reading = None
            return "hint", d
        last = box.last_reading
        box.last_reading = (message.angle_mdeg, d, now)
        if last and abs(last[0]-message.angle_mdeg) <= self.step_mdeg and abs(last[1]-d) <= self.CONSISTENT_M \
                and now - last[2] <= 1.5:
            return "reliable", d
        return "candidate", d

    def _polar(self, node, bearing, distance_m):
        g = self.geometry
        r = distance_m + g.body_radius_m
        sx, sy = g.sensor_position(node)
        a = math.radians(bearing/1000)
        return (sx + r*math.cos(a), sy + r*math.sin(a)), r

    def _on_range(self, box, message, stamp, now, txn_mode="sweep"):
        g = self.geometry
        if self.calibrating:
            self._calibration_sample(box, message)
            return
        kind, d = self._classify(box, message, now)
        box.status = f"{d:.2f} m" if d is not None else message.status.lower()
        if kind == "close":
            box.status = f"{d:.2f} m TOO CLOSE"
            self.too_close_since.setdefault(box.node, now)
            self.too_close_seen[box.node] = now
            return
        self._forget_too_close(box.node)
        if kind == "candidate":
            box.status += " ?"
            box.hold_bearing = message.angle_mdeg        # ping the same bearing again
            return
        if kind == "hint":
            box.status += " (far)"
        if kind != "reliable":
            self._on_miss(box, txn_mode, now)
            return
        point, r = self._polar(box.node, message.angle_mdeg, d)
        box.last_hit = now
        contribution = Contribution(box.node, stamp, message.angle_mdeg, r, point)
        self._absorb(contribution, now)

    def _absorb(self, contribution, now):
        g = self.geometry
        fresh = {n: c for n, c in self.contributions.items() if now - c.time <= self.FUSE_WINDOW_S}
        fresh[contribution.node] = contribution
        if len(fresh) >= 2:
            point, worst = fuse(g, list(fresh.values()))
            if worst > self.RESIDUAL_M:
                # Inconsistent boxes: keep the newest, drop the others, note it.
                others = [c for c in fresh.values() if c.node != contribution.node]
                spread = max(math.dist(contribution.point, c.point) for c in others)
                if spread >= g.two_player_separation_m:
                    self.inconsistent.append(now)
                fresh = {contribution.node: contribution}
                point, worst = contribution.point, 0.0
        else:
            point, worst = contribution.point, 0.0
        self.contributions = fresh
        if not self.estimate.update(point, contribution.time, len(fresh)):
            self.reason = "Position jumped"
            return
        self.good_times.append(contribution.time)
        self.reason = "Tracking" if len(fresh) >= 2 else "Tracking (one box)"
        self.state = "track"
        for box in self.boxes:
            moved = box.aimed_point is None or math.dist(box.aimed_point, point) >= self.REAIM_MOVE_M
            if box.node == contribution.node or box.mode == "aimed":
                box.mode = "aimed"
            elif box.mode == "jitter" and not moved:
                continue                      # let the jitter finish before deciding
            elif box.mode == "sweep" and not moved and now < box.aim_cooldown_until:
                continue                      # it already looked there and found nothing
            else:
                box.mode, box.jitter_index = "aimed", 0
            box.aimed_bearing = self._clamp_travel(box.node, g.angle(box.node, point))
            box.aimed_point = point

    def _on_miss(self, box, txn_mode, now):
        """A ping planned in `txn_mode` found nothing. Sweep pings just move on."""
        g = self.geometry
        if txn_mode == "aimed" and box.mode == "aimed":
            box.mode, box.jitter_started, box.jitter_index = "jitter", now, 1
        elif txn_mode == "jitter" and box.mode == "jitter" and now - box.jitter_started > g.jitter_s:
            box.mode = "sweep"
            box.aim_cooldown_until = now + self.REAIM_COOLDOWN_S

    # ----- calibration ----------------------------------------------------
    def _calibration_sample(self, box, message):
        plan = self.calibration_plan.get(box.node)
        if not plan or plan[0] != message.angle_mdeg:
            return
        plan.pop(0)
        key = f"{box.node}:{message.angle_mdeg}"
        self.calibration_samples.setdefault(key, []).append(
            message.distance_mm/1000 if message.status == "OK" else None)
        box.status = f"{message.distance_mm/1000:.2f} m" if message.status == "OK" else message.status.lower()
        self._maybe_finish_calibration()

    def _calibration_skip(self, box, bearing):
        plan = self.calibration_plan.get(box.node)
        while plan and plan[0] == bearing:
            plan.pop(0)
            self.calibration_samples.setdefault(f"{box.node}:{bearing}", []).append(None)
        self._maybe_finish_calibration()

    def _maybe_finish_calibration(self):
        if any(self.calibration_plan.values()):
            return
        background = {}
        for n in range(self.count):
            for b in self._grid(n):
                vs = [v for v in self.calibration_samples.get(f"{n}:{b}", []) if v is not None]
                background[f"{n}:{b}"] = statistics.median(vs) if len(vs) >= 2 else None
        try:
            self.calibration_path.write_text(json.dumps(
                {"version": 3, "geometry": self._json(asdict(self.geometry)), "background": background}, indent=2))
            self.background = background
            self.calibration_message = "Calibration saved — press Search to track"
        except OSError as exc:
            self.background = {}
            self.calibration_message = f"Could not save calibration: {exc}"
        self.calibrating = False
        self._clear_player()
        if self.idle_after_calibration:
            self.paused = True

    def calibration_progress(self):
        remaining = sum(len(v) for v in self.calibration_plan.values())
        return self.calibration_total - remaining, self.calibration_total

    # ----- network ------------------------------------------------------
    def _receive(self, now):
        try:
            messages = self.transport.receive()
        except OSError as exc:
            self.reason = f"Network receive failed: {exc}"
            return
        for message, address in messages:
            if not isinstance(message, (Range, Ready)) or not 0 <= message.node < self.count:
                continue
            box = self.boxes[message.node]
            txn = box.txn
            if not txn or txn.done or (message.seq, address) != (txn.seq, txn.address):
                continue
            if isinstance(message, Ready):
                if txn.ready or txn.fire_time is not None:
                    continue
                if message.status != "OK":
                    box.status = "bearing outside servo travel"
                    if self.calibrating:
                        self._calibration_skip(box, txn.angle)
                    txn.done = True; box.txn = None
                    continue
                if message.angle_mdeg == txn.angle:
                    txn.ready = (message, now)
                    self.transport.seen(message.node, address)
                continue
            if txn.fire_time is None or message.version != 2 or now - txn.fire_time > self.FIRE_TIMEOUT_S:
                continue
            self.transport.seen(message.node, address)
            txn.done = True; box.txn = None
            if self.firing == box.node:
                self.firing = None
            self.acoustic_safe_at = max(self.acoustic_safe_at, now + self.ACOUSTIC_GUARD_S)
            if message.status == "INVALID" and not message.age_us and not message.sample_ms:
                box.status = "sensor busy"       # ECHO still high after a missed echo; just retry
                box.hold_bearing = txn.angle
                continue
            upper = now - message.age_us/1_000_000
            uncertainty = upper - txn.fire_time
            if message.status == "INVALID" or message.sample_ms is None or uncertainty < -.003 \
                    or uncertainty > self.geometry.max_network_delay_s:
                box.status = "invalid"
                if self.calibrating:
                    box.hold_bearing = txn.angle
                continue
            stamp = (txn.fire_time + max(txn.fire_time, upper))/2
            self._on_range(box, message, stamp, now, txn.mode)

    def _connected(self):
        addresses = [self.transport.address(n) for n in range(self.count)]
        versions = [self.transport.protocol_version(n) for n in range(self.count)]
        for n in range(self.count):
            if not addresses[n]:
                self.node_status[n] = "offline"
            elif versions[n] != 2:
                self.node_status[n] = "no WM2 HELLO yet" if versions[n] is None else "old firmware"
            else:
                self.node_status[n] = self.boxes[n].status if self.boxes[n].status != "Waiting for sensor" else f"Connected {addresses[n][0]}"
        online = [n for n in range(self.count) if addresses[n] and versions[n] == 2]
        return online, addresses

    # ----- main loop ----------------------------------------------------
    def poll(self):
        g = self.geometry
        now = self.clock()
        self._receive(now)
        online, addresses = self._connected()
        ready_to_run = (self.simulate or bool(self.background) or self.calibrating) and not self.paused \
            and len(online) >= 2
        # timeouts and retries per box
        for box in self.boxes:
            txn = box.txn
            if not txn or txn.done:
                continue
            if txn.fire_time is not None and now - txn.fire_time > self.FIRE_TIMEOUT_S:
                box.status = "no range reply"
                if txn.ready:
                    ready, receipt = txn.ready
                    self.acoustic_safe_at = max(self.acoustic_safe_at, receipt + ready.lease_ms/1000
                                                + self.ECHO_TIMEOUT_S + self.ACOUSTIC_GUARD_S)
                txn.done = True; box.txn = None
                if self.firing == box.node:
                    self.firing = None
            elif txn.ready is None and now - txn.aim_time > self.AIM_TIMEOUT_S:
                box.status = "servo did not settle"
                txn.done = True; box.txn = None
            elif txn.ready is None and now - txn.aim_sent >= self.AIM_RETRY_S:
                txn.aim_sent = now
                try:
                    self.transport.send(aim(txn.seq, txn.angle), txn.address)
                except (OSError, ValueError):
                    txn.done = True; box.txn = None
        if len(online) < 2:
            self._cancel_all()
        self._expire(now)
        if ready_to_run:
            # aim every idle box
            for box in self.boxes:
                if box.node not in online or (box.txn and not box.txn.done):
                    continue
                bearing = self._choose_bearing(box, now)
                if bearing is None:
                    continue
                txn = Transaction(self._next_seq(), bearing, addresses[box.node], now, now, mode=box.mode)
                box.txn = txn
                box.bearing = bearing
                try:
                    self.transport.send(aim(txn.seq, bearing), txn.address)
                except (OSError, ValueError) as exc:
                    box.status = f"aim failed: {exc}"
                    box.txn = None
            # fire one settled box at a time
            if self.firing is None and now >= self.acoustic_safe_at:
                candidates = [b for b in self.boxes if b.txn and b.txn.ready and b.txn.fire_time is None]
                candidates.sort(key=lambda b: b.txn.ready[1])
                for box in candidates:
                    ready, receipt = box.txn.ready
                    if now >= receipt + ready.lease_ms/1000 - .05:
                        box.txn.done = True; box.txn = None      # lease expired: aim again
                        continue
                    box.txn.fire_time = now
                    self.firing = box.node
                    try:
                        self.transport.send(fire(box.txn.seq), box.txn.address)
                    except (OSError, ValueError):
                        box.txn.done = True; box.txn = None; self.firing = None
                    break
        self._update_alerts(now, online)
        self._update_buzzer(now)
        return self._snapshot(now, online, ready_to_run)

    # ----- freshness hooks (lockscan.py overrides these) --------------------
    def _expire(self, now):
        """Loss rule: no fused fix within local_search_s means the player is gone."""
        if self.state == "track" and now - self.estimate.last_good > self.geometry.local_search_s:
            self.state = "find"
            self.reason = "Player lost — sweeping"
            self.contributions.clear()

    def _fresh_fix(self, now):
        """Is the estimate recent enough to alert on and to report a rate for?"""
        return now - self.estimate.last_good <= self.geometry.local_search_s

    def _confidence(self, now):
        age = max(0.0, now - self.estimate.last_good)
        return self.estimate.confidence*max(0.0, 1-age/self.geometry.local_search_s)

    def _box_info(self):
        """Per-box view for the diagnostics overlay: where each servo points."""
        return tuple({"node": b.node, "mode": b.mode, "bearing_deg": b.bearing/1000} for b in self.boxes)

    def _raise(self, text, now):
        self.alert, self.alert_until = text, now + self.ALERT_LATCH_S

    # ----- buzzer ---------------------------------------------------------
    def _near_wall_alert(self):
        """Only the alerts that mean 'step back from the wall' sound the buzzer."""
        return self.alert == self.DEAD_ZONE_ALERT or self.alert.startswith(self.TOO_CLOSE_ALERT)

    def _send_buzz(self, duration_ms, address):
        try:
            self.transport.send(buzz(duration_ms), address)
        except (OSError, ValueError):
            return False        # like a failed AIM: never let it out of poll()
        return True

    def _silence_buzzer(self):
        """One BUZZ 0 after the sound was requested; nothing if it never was."""
        self.buzz_sent_at = float("-inf")     # the next alert sounds without delay
        if not self.buzzing:
            return
        self.buzzing = False
        # A lost BUZZ 0 is covered by the box itself: it stops at its deadline.
        self._send_buzz(0, self.buzz_address)

    def _update_buzzer(self, now):
        node = self.geometry.buzzer_node
        if node < 0:
            return
        address = None
        if self._near_wall_alert() and not self.paused and not self.calibrating:
            address = self.transport.address(node)
            if address and self.transport.protocol_version(node) != 2:
                address = None
        if not address:
            self._silence_buzzer()
            return
        if self.buzzing and address != self.buzz_address:
            self._silence_buzzer()             # the box moved: quiet the old address, sound the new at once
        if now - self.buzz_sent_at < self.BUZZ_INTERVAL_S - 1e-9:
            return
        # buzz_sent_at is the time of the last ATTEMPT: a send that fails waits
        # for the next interval too, instead of being retried on every poll.
        self.buzz_sent_at = now
        if self._send_buzz(self.BUZZ_MS, address):
            self.buzzing, self.buzz_address = True, address

    def _forget_too_close(self, node=None):
        if node is None:
            self.too_close_since.clear(); self.too_close_seen.clear()
        else:
            self.too_close_since.pop(node, None); self.too_close_seen.pop(node, None)

    def _update_alerts(self, now, online):
        g = self.geometry
        # Only a later reading from the same box withdraws its too-close report.
        # A box that went offline or quiet never sends one, so its report is
        # dropped here; otherwise the alert, and the buzzer, would never end.
        for node in [n for n, seen in self.too_close_seen.items()
                     if n not in online or now - seen > self.TOO_CLOSE_STALE_S]:
            self._forget_too_close(node)
        close = [n for n, t in self.too_close_since.items() if now - t >= self.TOO_CLOSE_S]
        if close:
            self._raise(f"{self.TOO_CLOSE_ALERT}{close[0]}", now)
            return
        recent = [t for t in self.inconsistent if now - t <= 3.0]
        if len(recent) >= 2 and recent[-1] - recent[0] >= self.TWO_PLAYER_S:
            self._raise("Two players detected", now)
            return
        point = self.estimate.point
        fresh_contrib = [c for c in self.contributions.values() if now - c.time <= self.FUSE_WINDOW_S]
        fresh = fresh_contrib and self._fresh_fix(now)
        if point is not None and fresh:
            # A single box only knows the bearing to within its cone, so its fix
            # can poke past an edge while the player is inside. Demand a clear
            # margin for one-box fixes; two-box fixes use the tight margin.
            margin = self.OUTSIDE_MARGIN_M if len(fresh_contrib) >= 2 else self.OUTSIDE_MARGIN_M + .3
            dead_zone = point[1] < g.near_y - (0 if len(fresh_contrib) >= 2 else .05)
            outside = dead_zone or not (-margin <= point[0] <= g.width + margin and point[1] <= g.far_y + margin)
            if outside:
                self.outside_since = self.outside_since or now
                if now - self.outside_since >= self.OUTSIDE_S:
                    self._raise(self.DEAD_ZONE_ALERT if dead_zone else "Player outside the field", now)
                    return
            else:
                self.outside_since = None
        if self.alert and now >= self.alert_until:
            self.alert = ""

    def _snapshot(self, now, online, ready_to_run):
        g = self.geometry
        fresh_contrib = sum(1 for c in self.contributions.values() if now - c.time <= self.FUSE_WINDOW_S)
        position = self.estimate.point if self.state == "track" else None
        age = max(0.0, now - self.estimate.last_good)
        predicted = position is not None and fresh_contrib < 2   # hollow spot: one box only
        if self.calibrating:
            done, total = self.calibration_progress()
            status = f"Keep area empty — calibrating {done}/{total}"
        elif self.paused:
            status = self.calibration_message if self.calibration_message.startswith("Calibration saved") \
                else "Paused — Search (Space) to track, Calibrate (C) for a new map"
        elif not (self.simulate or self.background):
            status = self.calibration_message or "Clear the area, then select Calibrate empty area"
        elif len(online) < 2:
            status = f"Waiting for sensors: {len(online)} of {self.count} online"
        elif self.state == "track":
            status = "Tracking player" if fresh_contrib >= 2 else "Tracking player (one box)"
        else:
            modes = ", ".join(f"{b.node}:{b.mode}" for b in self.boxes)
            status = f"Searching — {modes}"
        if self.alert:
            status = f"PAUSE: {self.alert}"
        rate = ((len(self.good_times)-1)/(self.good_times[-1]-self.good_times[0])
                if len(self.good_times) > 1 and self._fresh_fix(now) else 0.0)
        in_bounds = position is not None and 0 <= position[0] <= g.width and g.near_y <= position[1] <= g.far_y
        dead_zone = position is not None and 0 <= position[0] <= g.width and position[1] < g.near_y
        confidence = self._confidence(now) if position else 0.0
        return Snapshot(position, status, tuple(self.node_status), dead_zone, in_bounds, self.state,
                        predicted, confidence, age, rate, self.alert, fresh_contrib, self._box_info())
