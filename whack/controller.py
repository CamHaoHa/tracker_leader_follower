"""Coordinate the two ESP32s and decide when one player is being followed.

This module runs on the LAPTOP. Each ESP32 only aims its own servo and reports
its own ultrasonic distance. Even when the left ESP32 hosts the Wi-Fi network,
the laptop owns acquisition, the acoustic schedule, and the tracking state.
Tracker in tracking.py performs the position/velocity maths; the UI draws the
position returned in Snapshot and does not turn screen refreshes into samples.

One measurement cycle is:
    predict a target -> AIM both servos -> wait for both READY replies
    -> FIRE left -> receive left range -> acoustic guard -> FIRE right
    -> receive right range -> validate the pair -> correct the motion estimate

The servo movements overlap to reduce waiting. The ultrasonic pings never
intentionally overlap: a sensor could otherwise hear the other sensor's pulse.
All scheduling uses seconds on the laptop's monotonic clock. Wire angles are
millidegrees, wire distances are millimetres, and tracking positions are metres.
"""

from collections import deque
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import statistics
import time

from .protocol import MAX_SEQUENCE, Range, Ready, aim, fire
from .tracking import Geometry, Tracker
from .transport import SimulatedTransport, UdpTransport


@dataclass(frozen=True)
class Snapshot:
    """One UI update, including whether the single spot is fresh enough to draw.

    position may be a short extrapolation from the latest accepted range pair;
    None means hide the spot. fix_age_s is time since acquisition of that pair,
    not time since the last UI redraw. update_hz counts accepted fixes, not FPS.
    confidence is a heuristic that fades with age, not a measured probability.
    """

    position: tuple[float, float] | None
    status: str
    node_status: tuple[str, str]
    dead_zone: bool
    in_bounds: bool
    state: str = "find"
    predicted: bool = False
    confidence: float = 0.0
    fix_age_s: float = float("inf")
    update_hz: float = 0.0
    alert: str = ""            # game-facing pause condition, empty when none
    contributors: int = 0      # boxes whose fresh ranges built the position


@dataclass
class Frame:
    """One paired measurement transaction shared by the left and right nodes.

    Both AIM commands use seq, but each node has its own bearing and endpoint.
    ready stores each grant with its host receipt time. samples stores each
    Range with an estimated host acquisition time. firing names the only node
    currently allowed an outstanding FIRE; None means no such reply is pending.
    This structure prevents a left reading from one cycle being combined with
    a right reading from a different cycle or from a different network address.
    """

    seq: int
    angles: tuple[int, int]
    addresses: tuple
    aim_time: float
    ready: dict = field(default_factory=dict)  # node -> (reply, receipt time)
    samples: dict = field(default_factory=dict)
    firing: int | None = None
    fire_time: float = 0.0
    aim_sent: float = 0.0  # Last AIM (re)send time; READY loss is retried, not fatal.


class Controller:
    """Nonblocking state machine for calibration, acquisition, and following.

    A valid saved calibration lets hardware start directly at find. Otherwise
    the user clears the field and starts calibration before acquisition:

        calibration -> find -> confirm -> track
                         ^         |        |
                         |         v        v
                         +------- find   local_search -> track on a good pair
                         ^                  |
                         +----- lost <------+ after the recent model expires

    find aims at the centre initially, or searches the field. confirm requires
    two nearby, recent accepted pairs before exposing the spot. track aims from
    position and velocity instead of restarting a full scan after every pair.
    local_search retains that recent motion estimate and probes nearby points.
    lost clears the lock before returning to wide acquisition.

    Geometry supplies tunable limits: by default the spot expires after 200 ms
    without a fresh fix, while aiming/local recovery can use the old motion
    model for 500 ms. A --config geometry file can override those values; these
    are freshness policies, not promises of measured end-to-end latency.
    """

    # A lost FIRE reply leaves an uncertain acoustic window until its lease
    # expires. A successful reply permits the normal short guard instead.
    ACOUSTIC_GUARD_S = .065
    ECHO_TIMEOUT_S = .025
    FIRE_TIMEOUT_S = .4
    AIM_TIMEOUT_S = .95
    # A lost READY datagram is re-requested; firmware answers a repeated AIM with
    # READY once settled and never repeats the movement.
    AIM_RETRY_S = .3
    # Calibration tolerates a few transient network failures per step before
    # abandoning the partial map; persistent silence still aborts.
    CALIBRATION_RETRIES = 3
    SOFT_FAILURES = 8
    CONFIRM_PAIRS = 2
    LAYOUT_FIELDS = ("width", "near_y", "far_y", "left_x", "right_x", "sensor_y",
                     "left_offset_m", "right_offset_m", "beam_half_angle_deg", "calibration_step_deg")

    def __init__(self, geometry=None, simulate=False, clock=time.monotonic, transport=None,
                 calibration_path="calibration.local.json", port=4210, node_ips=None,
                 start_mode="center", start_paused=False):
        """Create the scheduler; no sensor command is sent until poll() runs.

        The injected clock/transport let tests exercise the same scheduling
        without physical motors. A supplied Geometry controls both layout and
        tracking limits; simulator mode bypasses empty-room calibration only.
        """
        if start_mode not in ("center", "search"):
            raise ValueError("Start mode must be center or search")
        self.geometry = geometry or Geometry()
        self.clock, self.simulate, self.start_mode = clock, simulate, start_mode
        self.transport = transport or (SimulatedTransport(clock, self.geometry) if simulate else
                                       UdpTransport(clock, port, node_ips))
        self.tracker = Tracker(self.geometry)
        self.seq = int(time.time() * 1000) & MAX_SEQUENCE or 1
        self.pending = None
        self.next_send = 0.0
        self.acoustic_safe_at = 0.0
        self.target = self.geometry.scan_targets()[0]
        self.scan_index = 0
        self.local_index = 0
        self.confirmations = 0
        self.follow_misses = 0
        self.state = "find"
        self.find_started = clock()
        self.lost_at = None
        self.good_times = deque(maxlen=12)
        self.node_status = ["Waiting for left sensor", "Waiting for right sensor"]
        self.calibration_path = Path(calibration_path)
        self.background = {}
        self.calibrating = False
        self.calibration_index = 0
        self.calibration_samples = {}
        self.calibration_failures = 0
        self.calibration_skipped = 0
        self.calibration_message = ""
        # Consecutive "sensor busy" replies; a stuck ECHO line must not spin forever.
        self.soft_failures = 0
        # start_paused: wait for an explicit Search/Calibrate instead of moving
        # servos the moment two sensors appear, and return to idle after a sweep.
        self.paused = self.idle_after_calibration = bool(start_paused)
        self._load_calibration()

    @property
    def samples(self):
        """Expose readings for the current cycle, never an older completed pair."""
        return self.pending.samples if self.pending else {}

    def _load_calibration(self):
        """Accept only a complete background map for this exact configuration.

        Each key is node:bearing, with a distance in metres or None for no
        repeatable echo. A changed layout, tracking configuration, or missing
        angle requires calibration again rather than using a misleading map.
        """
        if self.simulate or not self.calibration_path.exists():
            return
        try:
            profile = json.loads(self.calibration_path.read_text())
            saved = profile["geometry"]
            current = asdict(self.geometry)
            # Only the physical layout and sweep plan define the map. Tracking
            # tunables (smoothing, speed, body radius, timing) can change freely.
            if profile["version"] != 2 or not isinstance(saved, dict) or any(
                    saved.get(k) != current[k] for k in self.LAYOUT_FIELDS):
                raise ValueError("Geometry or calibration format changed")
            background = profile["background"]
            expected = {f"{n}:{angles[n]}" for angles in self.geometry.calibration_aims() for n in (0, 1)}
            if not isinstance(background, dict) or set(background) != expected or any(
                v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) or not .02 <= v <= 4.5)
                for v in background.values()
            ):
                raise ValueError("Invalid background profile")
            self.background = background
        except (ValueError, KeyError, TypeError, OSError):
            self.background = {}
            self.calibration_message = "Calibration unreadable or geometry changed; calibrate again"

    def _cancel_frame(self):
        """Discard a transaction while preserving any uncertain acoustic window.

        If FIRE was sent but its reply is missing, the command may still arrive
        late and produce a ping. Waiting only FIRE_TIMEOUT_S would be unsafe.
        READY receipt + remaining lease is a conservative expiry bound on the
        host clock; add maximum echo time and the guard before firing elsewhere.
        Cancelling an AIM-only frame needs no extra hold: AIM cannot emit sound.
        """
        f = self.pending
        if f and f.firing is not None:
            ready, receipt = f.ready[f.firing]
            self.acoustic_safe_at = max(self.acoustic_safe_at, receipt + ready.lease_ms / 1000
                                        + self.ECHO_TIMEOUT_S + self.ACOUSTIC_GUARD_S)
        self.pending = None

    def _clear_player(self):
        self._cancel_frame()
        self.tracker.reset()
        self.good_times.clear()
        self.state, self.scan_index, self.confirmations = "find", 0, 0
        self.follow_misses, self.local_index = 0, 0
        self.soft_failures = 0
        self.find_started, self.lost_at = self.clock(), None

    def start_acquisition(self):
        """Search for the player from scratch; also leaves pause/idle.

        Keep the calibrated background and any outstanding acoustic hold-off;
        restarting acquisition must not accidentally overlap an earlier ping.
        """
        if self.calibrating:
            return
        self._clear_player()
        self.resume()

    def pause(self):
        """Stop commanding the sensors: servos hold their last aim, nothing pings.

        A calibration in progress is abandoned because a partial map is useless.
        Pausing never sends a command, so any outstanding acoustic hold-off from
        the cancelled frame is still respected when work resumes.
        """
        if self.paused:
            return
        self.paused = True
        self._cancel_frame()
        if self.calibrating:
            self.calibrating = False
            self.background = {}
            self.calibration_message = "Calibration cancelled; retry with the area empty"
            self.state = "find"
        self.park_servos()

    def park_servos(self):
        """Aim both sensors straight out (90 degrees) without pinging.

        Used when pausing, resetting and closing so the boxes are left in their
        reference position. An AIM never emits ultrasound; its READY reply is
        ignored because no frame is pending.
        """
        for node in (0, 1):
            address = self.transport.address(node)
            if not address or self.transport.protocol_version(node) != 2:
                continue
            try:
                self.transport.send(aim(self._next_sequence(), 90000), address)
            except (OSError, ValueError):
                pass

    def resume(self):
        """Allow new measurement frames again after pause()."""
        if not self.paused:
            return
        self.paused = False
        self.next_send = max(self.next_send, self.clock()+.1)

    def reset(self):
        """Stop everything and forget the player; stays idle until Search or Calibrate.

        The calibrated background is kept. An in-progress calibration is abandoned.
        """
        self.pause()
        self._clear_player()
        self.park_servos()

    def start_calibration(self):
        """Begin an empty-field sweep after a three-second clearing countdown.

        Calibration uses the same alternating ping schedule as normal tracking.
        It clears the previous player model and builds a new background map;
        no player is localized or drawn while those baseline readings are taken.
        """
        if self.simulate or self.calibrating:
            return
        self._cancel_frame()
        self.paused = False  # A sweep needs frames even when started from idle.
        self.calibrating, self.state = True, "calibration"
        self.calibration_index = 0
        self.calibration_samples = {}
        self.calibration_failures = 0
        self.calibration_skipped = 0
        self.background = {}
        self.calibration_message = ""
        self.tracker.reset()
        self.good_times.clear()
        self.confirmations = 0
        self.next_send = self.clock() + 3.0

    def set_simulated_position(self, x, y):
        """Move the ideal reflector in simulation; hardware ignores this input."""
        if self.simulate and math.isfinite(x) and math.isfinite(y):
            self.transport.target = (x, y)

    def _nearest_scan_index(self, point):
        """Index of the scan target closest to a field point; centre when unknown."""
        if point is None:
            return 0
        targets = self.geometry.scan_targets()
        return min(range(len(targets)), key=lambda i: math.dist(targets[i], point))

    def _next_sequence(self):
        """Allocate a nonzero 32-bit transaction ID shared by both node commands."""
        self.seq = self.seq % MAX_SEQUENCE + 1
        return self.seq

    def _foreground(self, sample):
        """Check whether an echo is nearer than the calibrated room background.

        Following produces bearings between calibration stops. Use an exact
        baseline when available, otherwise inspect the two bracketing bearings.
        At a wall/object edge, averaging their distances could invent clear
        space, so use the nearer valid baseline. Reject gaps larger than the
        configured calibration step and bearings outside the calibrated span.

        A candidate must be more than 15 cm nearer than that baseline. None
        means calibration found no repeatable echo, so any valid range passes
        this stage. This gate detects a change in the scene, not a human identity;
        the second sensor, geometry checks, and confirmation still have to pass.
        """
        r = sample[0]
        if r.status != "OK":
            return False
        bearings = sorted((int(key.split(":")[1]), value) for key, value in self.background.items()
                          if key.startswith(f"{r.node}:"))
        if not bearings:
            return self.simulate and not self.background
        exact = next((v for a, v in bearings if abs(a-r.angle_mdeg) <= 1), ...)
        if exact is not ...:
            baseline = exact
        else:
            lower = [(a, v) for a, v in bearings if a < r.angle_mdeg]
            upper = [(a, v) for a, v in bearings if a > r.angle_mdeg]
            if not lower or not upper:
                return False
            (a, va), (b, vb) = lower[-1], upper[0]
            if b-a > self.geometry.calibration_step_deg*1000+1:
                return False
            # At wall/object boundaries use the nearer baseline conservatively.
            valid = [v for v in (va, vb) if v is not None]
            baseline = min(valid) if valid else None
        return baseline is None or r.distance_mm/1000 < baseline-.15

    def _miss(self, now, reason):
        """Choose local recovery for an established track, full search otherwise.

        A brief bad echo preserves the previous velocity for bounded prediction;
        it does not refresh the timestamp or keep the spot visible indefinitely.
        During acquisition, a miss instead clears the candidate. Centre mode
        holds the initial aim for roughly two seconds before advancing the scan.
        """
        self.follow_misses += 1
        if self.state in ("track", "local_search"):
            self.tracker.invalidate(reason, allow_prediction=True)
            self.state = "local_search"
        elif self.state == "confirm" and now - self.tracker.last_good <= self.geometry.local_search_s:
            # One missed echo must not throw away a fresh candidate: keep aiming
            # at it for the local-search window and try for the second pair.
            self.tracker.invalidate(reason, allow_prediction=True)
        else:
            self.tracker.reset()
            self.tracker.reason = reason
            self.confirmations = 0
            self.state = "find"
            if self.start_mode == "search" or now-self.find_started >= 2.0:
                self.scan_index = (self.scan_index+1) % len(self.geometry.scan_targets())

    def _fail_frame(self, now, reason, soft=False):
        """Handle transport/timing failure without immediately issuing more work.

        soft: the sensor refused to ping because its ECHO line was still high
        from a previous no-echo cycle (HC-SR04 modules hold it for up to a few
        hundred ms). That is neither a lost player nor a broken calibration:
        re-aim the same target after a short wait. A line stuck high for many
        cycles escalates to a normal failure so the operator sees it.

        Calibration must be complete to be useful, so a failed frame abandons
        that partial map. Tracking can attempt recovery after a short backoff,
        still respecting any longer acoustic hold imposed by _cancel_frame().
        """
        self._cancel_frame()
        if soft:
            self.soft_failures += 1
            if self.soft_failures <= self.SOFT_FAILURES:
                self.next_send = max(self.next_send, now+.15)
                return
            reason = f"{reason}; sensor ECHO stuck, check wiring"
        self.soft_failures = 0
        if self.calibrating:
            self.calibration_failures += 1
            if self.calibration_failures <= self.CALIBRATION_RETRIES:
                # Keep the samples gathered so far; the same step is aimed again.
                self.calibration_message = f"Retrying calibration step: {reason}"
            else:
                self.calibrating = False
                self.background = {}
                self.calibration_message = f"Calibration interrupted: {reason}; retry with the area empty"
                self.state = "find"
        else:
            self._miss(now, reason)
        self.next_send = max(self.next_send, now+.1)

    def _skip_calibration_entry(self, frame):
        """Treat an unreachable sweep entry as measured with no repeatable echo."""
        for node in (0, 1):
            self.calibration_samples.setdefault(f"{node}:{frame.angles[node]}", []).append(None)
        self.calibration_skipped += 1
        self._cancel_frame()
        self.next_send = max(self.next_send, self.clock() + .05)
        self._complete_calibration({})

    def _complete_calibration(self, samples):
        """Collect three pairs per scheduled bearing entry, then save baselines.

        Geometry.calibration_aims() provides dense angular coverage for later
        following. _aim_angles() repeats each entry three times before advancing.
        For each node:bearing, require at least two valid echoes and take their
        median; otherwise store None. Repeated endpoint bearings can accumulate
        more readings when the two independent sweeps have different lengths.
        Never publish a partial map as a completed calibration.
        """
        for node, (r, _) in samples.items():
            key = f"{node}:{r.angle_mdeg}"
            self.calibration_samples.setdefault(key, []).append(r.distance_mm/1000 if r.status == "OK" else None)
        self.calibration_index += 1
        self.calibration_failures = self.soft_failures = 0
        if self.calibration_index < len(self.geometry.calibration_aims())*3:
            return
        background = {k: statistics.median([v for v in vs if v is not None])
                      if sum(v is not None for v in vs) >= 2 else None
                      for k, vs in self.calibration_samples.items()}
        try:
            self.calibration_path.write_text(json.dumps({"version": 2, "geometry": asdict(self.geometry),
                                                        "background": background}, indent=2))
            self.background = background
            self.calibration_message = ""
        except OSError as exc:
            self.background = {}
            self.calibration_message = f"Could not save calibration: {exc}"
        self.calibrating = False
        if self.idle_after_calibration:
            self._clear_player()
            self.paused = True
            skipped = f" ({self.calibration_skipped} bearings outside servo travel)" if self.calibration_skipped else ""
            self.calibration_message = f"Calibration saved{skipped} — press Search to track"
        else:
            self.start_acquisition()

    def _complete_pair(self, samples, now):
        """Validate a matched pair and advance acquisition or movement following.

        First reject unchanged room echoes. Tracker.update() then checks timing,
        corrects for sequential sample times using recent velocity, intersects
        the distance circles, checks beam agreement, and updates position/speed.
        Only accepted pairs add a measurement timestamp to the rate history.

        Two accepted acquisition pairs are required before track becomes visible.
        The second must follow within 0.5 s and lie within 0.3 m of the first;
        otherwise it starts a new candidate. An already established track can
        recover from local_search after one acceptable pair while its model is
        still recent. This is approximate single-target association, not proof
        that two echoes came from the same person or body surface.
        """
        if self.calibrating:
            self._complete_calibration(samples)
            return
        left, right = samples[0], samples[1]
        if not (self._foreground(left) and self._foreground(right)):
            self._miss(now, "No matching foreground echoes")
            return
        previous_point, previous_stamp = self.tracker.raw, self.tracker.last_good
        if not self.tracker.update(left, right, now):
            self._miss(now, self.tracker.reason)
            return
        self.follow_misses = 0
        self.good_times.append(self.tracker.last_good)
        if self.state in ("track", "local_search"):
            self.state = "track"
            self.local_index = 0
        else:
            if self.state == "confirm" and (self.tracker.last_good-previous_stamp > self.geometry.local_search_s or
                    previous_point is None or math.dist(previous_point, self.tracker.raw) > .3):
                self.confirmations = 0
            self.confirmations += 1
            self.state = "track" if self.confirmations >= self.CONFIRM_PAIRS else "confirm"

    def _aim_angles(self, now):
        """Convert the next predicted target into one bearing for each servo.

        In track/confirm, project the motion model to now + aim_lead_s (80 ms
        ahead by default) to allow for movement/measurement time. The projection
        is capped by local_search_s, so an old velocity cannot steer forever.
        The ESP32 uses these commanded bearings; they are not measured bearings
        of the echo. Both beams still need compatible distance observations.

        During local recovery, cycle around the prediction: centre, 12 cm left,
        12 cm right, 12 cm nearer, and 12 cm farther. One offset is tried per
        measurement cycle; the time limit does not guarantee all five are tried.
        After loss, find uses the wide scan plan again. Calibration instead uses
        independent dense sweeps, with each scheduled pair repeated three times.
        """
        g = self.geometry
        if self.calibrating:
            return g.calibration_aims()[self.calibration_index//3]
        if self.state in ("track", "local_search", "confirm") and self.tracker.filtered is not None:
            point = self.tracker.predict(now+g.aim_lead_s, horizon=g.local_search_s)
            if self.state == "local_search":
                offsets = ((0, 0), (-.12, 0), (.12, 0), (0, -.12), (0, .12))
                dx, dy = offsets[self.local_index % len(offsets)]
                self.local_index += 1
                point = (point[0]+dx, point[1]+dy)
            # Only servo targets are clamped. Observations outside the field are
            # never turned into valid edge positions.
            self.target = (min(g.width, max(0, point[0])),
                           min(g.far_y, max((g.sensor_y+g.near_y)/2, point[1])))
        else:
            self.target = g.scan_targets()[self.scan_index]
        return tuple(g.angle(n, self.target) for n in (0, 1))

    def _receive(self, now):
        """Consume replies only for the pending node, sequence, aim, and phase.

        Discovery runs inside transport.receive(). A delayed/duplicate reply
        from another cycle cannot refresh this frame or the player estimate.
        Both READY grants are needed before either sensor is fired, and only
        the currently firing node may supply the next usable RANGE.
        """
        try:
            messages = self.transport.receive()
        except OSError as exc:
            self._fail_frame(now, f"Network receive failed: {exc}")
            return
        for message, address in messages:
            f = self.pending
            if not f or not isinstance(message, (Range, Ready)):
                continue
            n = message.node
            if n not in (0, 1) or (message.seq, address) != (f.seq, f.addresses[n]):
                continue
            if isinstance(message, Ready):
                if n in f.ready or f.firing is not None or now-f.aim_time > self.AIM_TIMEOUT_S:
                    continue
                if message.status != "OK":
                    if self.calibrating:
                        # Bearing outside this servo's travel: not a fault. Record
                        # "no background" for both bearings of this entry and move on.
                        self._skip_calibration_entry(f)
                        self.node_status[n] = "Bearing outside servo travel; skipped"
                        continue
                    self.node_status[n] = "Aim rejected; check servo limits"
                    self._fail_frame(now, self.node_status[n])
                elif message.angle_mdeg == f.angles[n]:
                    f.ready[n] = (message, now)
                    self.transport.seen(n, address)
                continue
            if (f.firing != n or message.version != 2 or now-f.fire_time > self.FIRE_TIMEOUT_S
                    or (message.status == "OK" and message.angle_mdeg != f.angles[n])):
                continue
            self.transport.seen(n, address)
            self.node_status[n] = f"{message.distance_mm/1000:.2f} m" if message.status == "OK" else message.status.lower()
            # Receipt proves this command's ping has finished. Even a rejected
            # timestamp cannot shorten the following acoustic guard.
            self.acoustic_safe_at = max(self.acoustic_safe_at, now+self.ACOUSTIC_GUARD_S)
            f.firing = None
            # The boards' sample_ms clocks have different boot epochs. Do not
            # subtract left millis from right millis or compare them to the PC.
            # age_us measures trigger -> reply creation on this one board.
            # Therefore the trigger lies between:
            #   lower = host FIRE send time
            #   upper = host receipt time - board's measured age
            # Remaining interval width includes command/reply transport and
            # host polling delay. Reject excessive uncertainty, tolerate only
            # 3 ms of small negative timing error, and use the interval midpoint
            # as the common host-clock acquisition estimate. This is bounded
            # estimation, not synchronized device clocks or measured one-way
            # network latency. Tracker uses these sample times to compensate
            # for player movement between the left and right pings.
            if message.status == "INVALID" and not message.age_us and not message.sample_ms:
                # Firmware refused to trigger: ECHO was still high (no-echo hold-off).
                self._fail_frame(now, "Sensor busy after a missed echo", soft=True)
                continue
            upper = now-message.age_us/1_000_000
            uncertainty = upper-f.fire_time
            if (message.status == "INVALID" or message.sample_ms is None or uncertainty < -.003
                    or uncertainty > self.geometry.max_network_delay_s):
                self._fail_frame(now, "Invalid or excessively delayed measurement")
                continue
            stamp = (f.fire_time+max(f.fire_time, upper))/2
            f.samples[n] = (message, stamp)
            if len(f.samples) == 2:
                self.pending = None
                self.soft_failures = 0
                self._complete_pair(f.samples, now)

    def poll(self):
        """Advance available work without waiting, then return one screen update.

        Call frequently from the UI loop. Most calls only inspect state: neither
        a redraw nor a prediction triggers a new accepted position measurement.
        Servo readiness, ping replies, guards, and deadlines determine the actual
        sampling rate. Network/servo failures leave the UI able to keep updating.
        """
        now = self.clock()
        # 1. Receive first: a reply may finish a pair or release the normal guard.
        self._receive(now)
        f = self.pending
        if f:
            if f.firing is not None and now-f.fire_time > self.FIRE_TIMEOUT_S:
                self.node_status[f.firing] = "No range reply"
                self._fail_frame(now, "Sensor did not respond")
            elif len(f.ready) < 2 and now-f.aim_time > self.AIM_TIMEOUT_S:
                self._fail_frame(now, "Servo readiness timed out")
            elif len(f.ready) < 2 and now-f.aim_sent >= self.AIM_RETRY_S:
                # Re-request only the missing grants. A duplicate AIM never moves
                # the servo again; it just repeats READY once settling is over.
                f.aim_sent = now
                try:
                    for n in (0, 1):
                        if n not in f.ready:
                            self.transport.send(aim(f.seq, f.angles[n]), f.addresses[n])
                except (OSError, ValueError) as exc:
                    self._fail_frame(now, f"Could not aim sensors: {exc}")
        # 2. Both live WM2 identities are required. One range cannot recover a
        # full 2-D point, and a duplicate node ID must not silently change roles.
        addresses = tuple(self.transport.address(n) for n in (0, 1))
        versions = tuple(self.transport.protocol_version(n) for n in (0, 1))
        connected = all(addresses) and versions == (2, 2)
        if not connected:
            self._cancel_frame()
            for n in (0, 1):
                self.node_status[n] = ("Offline or duplicate ID" if not addresses[n] else
                                       "Upload WM2 tracker firmware" if versions[n] == 1 else
                                       "Waiting for WM2 HELLO" if versions[n] is None else self.node_status[n])
            self.tracker.invalidate("Waiting for two WM2 sensors")
        else:
            # HELLO proves the link; a range replaces this text after the first ping.
            for n in (0, 1):
                if self.node_status[n].startswith("Waiting for"):
                    self.node_status[n] = f"Connected {addresses[n][0]}"
        # 3. Give nearby recovery a bounded window measured from acquisition of
        # the last good pair. The visible spot has its own, shorter expiry in
        # Tracker.position(); hiding the spot does not require waiting 500 ms.
        # Cancel the old frame on loss so late replies cannot restore an old lock.
        if self.state in ("track", "local_search") and now-self.tracker.last_good > self.geometry.local_search_s:
            self._cancel_frame()
            self.confirmations = 0
            self.good_times.clear()
            self.state, self.lost_at = "lost", now
            self.tracker.invalidate("Player lost — searching again")
        elif self.state == "lost" and now-self.lost_at >= .1:
            # Full search after a lost track, but start it where the player was
            # last seen: the scan path is spatially ordered, so nearby targets
            # come first and the sweep widens from there.
            self.scan_index = self._nearest_scan_index(self.tracker.raw)
            self.tracker.reset()
            self.confirmations = 0
            self.find_started = now-2.0
            self.state = "find"
        # 4. Prepare both servo movements together. AIM does not emit ultrasound,
        # so movements may overlap each other and an acoustic hold-off interval.
        # Normal player acquisition needs a usable background calibration; the
        # calibration sweep itself is also allowed through this gate.
        ready = self.simulate or bool(self.background) or self.calibrating
        if connected and ready and not self.paused and self.state != "lost" and now >= self.next_send:
            if self.pending is None:
                angles = self._aim_angles(now)
                f = Frame(self._next_sequence(), angles, addresses, now, aim_sent=now)
                self.pending = f
                try:
                    for n in (0, 1):
                        self.transport.send(aim(f.seq, angles[n]), addresses[n])
                except (OSError, ValueError) as exc:
                    self._fail_frame(now, f"Could not aim sensors: {exc}")
            f = self.pending
            # 5. Once both servos report settled, alternate left then right.
            # Wait at least 65 ms after a completed reply before another FIRE.
            # This is conservative: echo duration and transport time add to the
            # trigger-to-trigger interval. A missing reply uses the longer lease
            # expiry guard instead. Do not fire near the end of a READY lease;
            # re-aim with a new sequence instead of queuing a delayed trigger.
            if f and len(f.ready) == 2 and f.firing is None and now >= self.acoustic_safe_at:
                n = 1 if 0 in f.samples else 0
                response, receipt = f.ready[n]
                if now >= receipt+response.lease_ms/1000-.05:
                    self._fail_frame(now, "Firing lease expired; aiming again")
                else:
                    # Mark before send, so even a socket error keeps the lease guard.
                    f.firing, f.fire_time = n, now
                    try:
                        self.transport.send(fire(f.seq), f.addresses[n])
                    except (OSError, ValueError) as exc:
                        self._fail_frame(now, f"Could not request range: {exc}")
        # 6. Build the display estimate separately from acquisition. Prediction
        # can move the spot between accepted pairs but never changes last_good.
        # The default 200 ms expiry can therefore hide the spot even while the
        # scheduler continues local recovery for its default 500 ms window.
        position = self.tracker.position(now) if self.state in ("track", "local_search") and connected else None
        age = max(0.0, now-self.tracker.last_good)
        # UI hint: mark nearby recovery or a fix older than 50 ms as predicted.
        # Position extrapolation can also occur between fresher measurements;
        # this flag is a display convention, not an additional sensor result.
        predicted = position is not None and (self.state == "local_search" or age > .05)
        status = {"find": "Finding player — stand near the centre" if self.start_mode == "center" and now-self.find_started < 2 else "Searching the field",
                  "confirm": "Confirming player", "track": "Tracking player", "local_search": "Brief echo loss — searching nearby",
                  "lost": "Player lost — searching again"}.get(self.state, self.tracker.reason)
        if self.calibrating:
            status = f"Keep area empty — calibrating {self.calibration_index+1}/{len(self.geometry.calibration_aims())*3}"
        elif not ready:
            status = self.calibration_message or "Clear the area, then select Calibrate empty area"
        elif not connected:
            status = "Waiting for two WM2 sensors — check power, firmware and network"
        if self.paused:
            status = (self.calibration_message if self.calibration_message.startswith("Calibration saved")
                      else "Paused — Search (Space) to track, Calibrate (C) for a new map")
        # Use accepted acquisition timestamps for Hz. A fast rendering loop does
        # not imply a fast sensor: many snapshots can share the same last fix.
        rate = ((len(self.good_times)-1)/(self.good_times[-1]-self.good_times[0])
                if len(self.good_times) > 1 and age <= self.geometry.local_search_s else 0.0)
        confidence = self.tracker.confidence*max(0.0, 1-age/self.geometry.prediction_horizon_s) if position else 0.0
        return Snapshot(position, status, tuple(self.node_status), self.tracker.dead_zone,
                        position is not None and self.tracker.in_bounds(now), self.state,
                        predicted, confidence, age, rate)

    def close(self):
        """Park the servos, then release transport resources."""
        self._cancel_frame()
        try:
            self.park_servos()
        finally:
            self.transport.close()
