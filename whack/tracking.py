"""The movement-estimation maths, running on the LAPTOP.

Each ESP32 reports one distance and the direction its servo was commanded to
face. This module combines two distances into an approximate player position,
then estimates velocity so the spot and servo aims can follow movement.

Reading order:
    Geometry.angle()      position -> direction for each servo
    locate()              two distances -> one forward circle intersection
    Tracker.update()      timed distance pair -> corrected position + velocity
    Tracker.position()    recent measured state -> current display estimate

Controller in controller.py decides WHEN to measure and whether echoes belong
to a foreground candidate. It also confirms acquisition and searches after loss.
The ESP32 firmware moves the motors and measures echoes; it does not run this
position/velocity filter, even when the left ESP32 hosts the Wi-Fi network.

Units: positions/ranges in metres, velocity in metres/second, time in seconds
on the laptop's monotonic clock, and wire-protocol angles in millidegrees.
Coordinates: +x is right along the screen wall; +y is away from the wall.
This is a single-reflector approximation: different parts of a human body can
produce inconsistent ranges, so the result is not a measured body centre.
"""

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Geometry:
    """Measured layout and tunable assumptions shared by the tracking stages.

    These defaults describe the example field, not an automatic measurement of
    the room. A JSON file supplied through --config overrides individual values.
    Both sensors must have the same height/depth for this 2-D circle model.
    The immutable object also lets scan plans be cached and calibration profiles
    be invalidated when the geometry or tracking parameters change.
    """

    # Field edges and acoustic sensor centres, measured from the screen wall.
    width: float = 1.5
    near_y: float = 0.6
    far_y: float = 2.0
    left_x: float = 0.0
    right_x: float = 1.5
    sensor_y: float = 0.2
    # Additive corrections for measured sensor range bias, not human body width.
    left_offset_m: float = 0.0
    right_offset_m: float = 0.0
    # Assumed acoustic half-cone: the target can be to either side of the aim.
    # A servo command is not an exact bearing measurement of the player.
    beam_half_angle_deg: float = 20.0
    max_speed_m_s: float = 3.0
    # Larger smoothing time gives less weight to each new position correction.
    smoothing_tau_s: float = 0.12
    # Reject two observations taken too far apart to combine usefully.
    max_pair_skew_s: float = 0.15
    # The visible spot expires after this age; prediction does not refresh it.
    prediction_horizon_s: float = 0.20
    # Aim ahead of the estimated current position to allow for motor motion.
    aim_lead_s: float = 0.08
    # Keep a recent motion model for nearby reacquisition, even after the spot
    # has expired. This longer aiming window does not extend display freshness.
    local_search_s: float = 0.50
    calibration_step_deg: float = 3.0
    # Controller rejects a range if its timing interval has this much uncertainty.
    max_network_delay_s: float = 0.12

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in asdict(self).values()):
            raise ValueError("Geometry values must be finite numbers")
        if not (0 < self.width <= 5 and 0 <= self.left_x < self.right_x <= self.width):
            raise ValueError("Sensor x coordinates must be ordered within the field")
        if not (0 <= self.sensor_y <= 0.5 and self.sensor_y < self.near_y < self.far_y <= 4):
            raise ValueError("Require sensors within 0.5m of wall and ahead of playable area")
        if not (1 <= self.beam_half_angle_deg <= 30 and 0 < self.max_speed_m_s <= 10
                and 0 <= self.smoothing_tau_s <= 1 and 0.12 <= self.max_pair_skew_s <= 0.5):
            raise ValueError("Invalid tracking limits")
        if not (0.05 <= self.prediction_horizon_s <= 0.5 and
                0 <= self.aim_lead_s <= 0.3 and 0.2 <= self.local_search_s <= 2 and
                0.5 <= self.calibration_step_deg <= 10 and
                0.01 <= self.max_network_delay_s <= 0.5):
            raise ValueError("Invalid prediction, search, calibration or network limits")
        if max(abs(self.left_offset_m), abs(self.right_offset_m)) > 0.3:
            raise ValueError("Range offsets must be within 0.3m")

    def angle(self, node: int, point: tuple[float, float]) -> int:
        """Point one sensor toward a field position using atan2(dy, dx).

        Example: at a point directly in front of either sensor dx=0, so its
        bearing is 90 degrees (90000 millidegrees). Both nodes use the SAME
        world axes: 0 is right, 90 forward, 180 left. The right node will usually
        need a different angle from the left to look at the same player.
        Firmware separately applies that mount's reversal, trim and travel bounds.
        """
        sx = self.left_x if node == 0 else self.right_x
        return round(math.degrees(math.atan2(point[1] - self.sensor_y, point[0] - sx)) * 1000)

    @lru_cache(maxsize=16)
    def scan_targets(self) -> tuple[tuple[float, float], ...]:
        """Cover paired bearings across the field and front warning strip.

        A sensor's bearing extrema over a rectangle occur at its corners. A
        cell is covered only when one shared aim puts all four corners inside
        *both* beams, with a 10% angular margin. This is geometric coverage for
        the configured beam model, not a guarantee of echoes from a person.
        """
        centre = (self.width / 2, (self.near_y + self.far_y) / 2)
        # Start with intuitive targets (centre, edges, several depths). Extra
        # subdivision below fills gaps left by this coarse set of directions.
        # The front strip is included for position diagnostics, not game logic.
        targets = [(self.width * x, y)
                   for y in (self.near_y, centre[1], self.far_y, (self.sensor_y + self.near_y) / 2)
                   for x in (0, 0.25, 0.5, 0.75, 1)]
        targets = [centre] + [point for point in targets if point != centre]
        margin = self.beam_half_angle_deg * 900  # millidegrees, 90% of half-angle
        aim_bins = {}

        def add_aim(point):
            aim = tuple(self.angle(node, point) for node in (0, 1))
            key = tuple(math.floor(angle / margin) for angle in aim)
            aim_bins.setdefault(key, []).append(aim)

        def covered(bounds):
            # Index in paired angle space so narrow beams do not require an
            # O(N^2) search through every earlier aim during subdivision.
            (lo0, hi0), (lo1, hi1) = bounds
            for a in range(math.floor((hi0-margin)/margin), math.floor((lo0+margin)/margin)+1):
                for b in range(math.floor((hi1-margin)/margin), math.floor((lo1+margin)/margin)+1):
                    if any(hi0-margin <= x <= lo0+margin and hi1-margin <= y <= lo1+margin
                           for x, y in aim_bins.get((a, b), ())):
                        return True
            return False

        for point in targets:
            add_aim(point)
        cells = [(0.0, self.width, (self.sensor_y+self.near_y)/2, self.far_y, 0)]
        visited = 0
        while cells:
            x0, x1, y0, y1, depth = cells.pop()
            visited += 1
            if visited > 32768:
                raise ValueError("Scan geometry needs too many cells; increase sensor clearance or beam angle")
            corners = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
            angles = [tuple(self.angle(node, p) for p in corners) for node in (0, 1)]
            bounds = [(min(values), max(values)) for values in angles]
            # Already-covered rectangles need no more servo stops. Otherwise add
            # a midpoint aim if its two beams cover the cell, or divide the cell.
            if covered(bounds):
                continue
            midpoint = ((x0+x1)/2, (y0+y1)/2)
            if all(hi-margin <= self.angle(node, midpoint) <= lo+margin
                   for node, (lo, hi) in enumerate(bounds)):
                if len(targets) >= 8192:
                    raise ValueError("Scan geometry needs more than 8192 aims; use a wider measured beam angle")
                targets.append(midpoint)
                add_aim(midpoint)
                continue
            if depth >= 64:
                raise ValueError("Sensor clearance is too small to construct a bounded scan")
            # Split along the direction with greater angular variation.
            dx = max(abs(a[i]-a[j]) for a in angles for i, j in ((0, 1), (2, 3)))
            dy = max(abs(a[i]-a[j]) for a in angles for i, j in ((0, 2), (1, 3)))
            if dx >= dy:
                mid = midpoint[0]
                cells.extend(((mid, x1, y0, y1, depth+1), (x0, mid, y0, y1, depth+1)))
            else:
                mid = midpoint[1]
                cells.extend(((x0, x1, mid, y1, depth+1), (x0, x1, y0, mid, depth+1)))
        # Geometry is immutable. Cache an immutable result for the acquisition
        # loop; callers cannot corrupt a later calibration by editing this list.
        return tuple(targets)


    @lru_cache(maxsize=16)
    def calibration_aims(self) -> tuple[tuple[int, int], ...]:
        """Dense independent bearing sweeps, including every search bearing.

        Calibration need not aim both sensors at the same point. Each motor moves
        monotonically through its own bearings, avoiding long zigzag movements.
        Every search bearing is included, and gaps are filled to the configured
        step so later tracking can compare nearby directions to the background.

        These are geometric bearings; this planner does not know each motor's
        physical travel. Unreachable angles are rejected by firmware. In
        particular, the current temporary 30..150 degree SG90 test bounds do
        not permit the full default empty-field sweep.
        """
        step = round(self.calibration_step_deg * 1000)
        bearings = []
        for node in (0, 1):
            required = {self.angle(node, point) for point in self.scan_targets()}
            lo, hi = min(required), max(required)
            required.update(range(lo, hi + 1, step))
            bearings.append(sorted(required, reverse=(node == 1)))
        return tuple((bearings[0][min(i, len(bearings[0])-1)],
                      bearings[1][min(i, len(bearings[1])-1)])
                     for i in range(max(map(len, bearings))))


def load_geometry(path: str | None) -> Geometry:
    return Geometry(**json.loads(Path(path).read_text())) if path else Geometry()


def locate(geometry: Geometry, left_m: float, right_m: float) -> tuple[float, float]:
    """Locate a common reflector from two corrected distances.

    Let u = x - left_x, h = y - sensor_y and b = right_x - left_x.
    Each measured distance defines a circle around that sensor:

        u**2       + h**2 = r0**2
        (u-b)**2   + h**2 = r1**2

    Subtracting the equations eliminates h and gives:

        u = (r0**2 - r1**2 + b**2) / (2*b)
        h = sqrt(r0**2 - u**2)

    Choose positive h because the player is assumed in front of the sensors.
    This is range-based circle intersection, not intersection of two measured
    bearings. Servo angles are used later as broad consistency checks only.
    Two ranges cannot identify a person or prove they hit the same body surface.
    """
    r0, r1 = left_m + geometry.left_offset_m, right_m + geometry.right_offset_m
    if not all(math.isfinite(v) and 0.02 <= v <= 4.5 for v in (r0, r1)):
        raise ValueError("Invalid range")
    baseline = geometry.right_x - geometry.left_x
    # Triangle inequalities reject circles that do not intersect. Tangency is
    # also rejected: near the baseline, small range errors can cause large errors.
    if r0 + r1 <= baseline or abs(r0 - r1) >= baseline:
        raise ValueError("Ranges have no stable forward intersection")
    x_relative = (r0*r0 - r1*r1 + baseline*baseline) / (2*baseline)
    height_squared = r0*r0 - x_relative*x_relative
    if height_squared <= 0:
        raise ValueError("Ranges have no forward intersection")
    return geometry.left_x + x_relative, geometry.sensor_y + math.sqrt(height_squared)


class Tracker:
    """Timestamped two-range localization with a bounded alpha-beta motion model.

    Range-pair times are common host-clock estimates, not raw ESP32 millis.
    Prediction is an estimate and never refreshes last_good.
    The stored state is effectively [x, y, vx, vy]. Controller owns the search
    state machine; this class owns the numeric position and motion estimate.
    """

    def __init__(self, geometry: Geometry):
        self.geometry = geometry
        self.reset()

    def reset(self):
        # raw is the newest accepted, motion-aligned circle intersection.
        # filtered is the smoothed estimate AT last_good, not at display time.
        self.raw = None
        self.filtered = None
        # One position alone says nothing about movement, so start at rest.
        self.velocity = (0.0, 0.0)
        self.last_good = float("-inf")
        self.valid = False
        self.allow_prediction = False
        self.reason = "Waiting for measurements"
        self.dead_zone = False
        self.confidence = 0.0

    def invalidate(self, reason: str, *, allow_prediction: bool = False):
        """Reject a measurement without pretending an old position is a new fix.

        A brief bad echo can preserve the recent model for prediction. A network
        failure or explicit reset can instead hide it immediately. Neither path
        changes last_good; the normal prediction expiry still applies.
        """
        self.valid = False
        self.allow_prediction = allow_prediction
        self.reason = reason

    def predict(self, now: float, *, horizon: float | None = None):
        """Constant-velocity extrapolation: position + velocity * elapsed time.

        Example: x=0.75 m and vx=0.30 m/s predict x=0.78 m after 0.10 s.
        The elapsed time is capped; calling this repeatedly cannot project an
        old track indefinitely into the future. Aiming may supply a longer
        horizon, whereas position() additionally enforces display expiry.
        This predicts continued motion, not the player's next intention or turn.
        """
        if self.filtered is None:
            return None
        limit = self.geometry.prediction_horizon_s if horizon is None else horizon
        dt = min(max(now - self.last_good, 0.0), limit)
        return tuple(self.filtered[i] + self.velocity[i] * dt for i in (0, 1))

    def update(self, left, right, now: float):
        """Accept or reject one pair, then update position and velocity.

        left/right are (Range message, estimated host-clock acquisition time).
        now is the current host time. Return True only for a new accepted fix.
        Background filtering and two-pair acquisition confirmation belong to
        Controller; this method never identifies a player from ultrasound alone.
        """
        g = self.geometry
        # 1. Both nodes must provide a usable echo. A missing echo is not a zero
        # distance, and one distance alone cannot determine a full 2-D position.
        if any(sample[0].status != "OK" for sample in (left, right)):
            self.invalidate("No player echo", allow_prediction=True)
            return False
        times = (left[1], right[1])
        stamp = max(times)
        # 2. Combine only sufficiently fresh observations. The later acquisition
        # becomes the new state's time. Reject replayed, future or widely spaced
        # samples rather than interpreting network delays as player movement.
        if (not all(math.isfinite(t) for t in (*times, now)) or stamp > now + .002
                or abs(times[0] - times[1]) > g.max_pair_skew_s
                or now - min(times) > g.prediction_horizon_s + g.max_pair_skew_s
                or stamp <= self.last_good):
            self.invalidate("Measurements too old or too far apart", allow_prediction=True)
            return False

        # 3. The sensors ping one after the other to avoid acoustic interference.
        # A moving player can therefore be at different positions for the two
        # ranges. Advance the earlier range to the later sample's time using the
        # previous velocity estimate; the first fix assumes no velocity.
        ranges = [left[0].distance_mm / 1000, right[0].distance_mm / 1000]
        model_recent = self.filtered is not None and stamp - self.last_good <= g.local_search_s
        if model_recent:
            for node, sample in enumerate((left, right)):
                predicted = self.predict(sample[1], horizon=g.local_search_s)
                sx = g.left_x if node == 0 else g.right_x
                dx, dy = predicted[0] - sx, predicted[1] - g.sensor_y
                radius = math.hypot(dx, dy)
                if radius > .02:
                    # Dot velocity with the sensor-to-player unit vector. Only
                    # motion toward/away from THIS sensor changes its distance.
                    # Units: (metres * metres/second) / metres = metres/second.
                    radial_speed = (dx*self.velocity[0] + dy*self.velocity[1]) / radius
                    # r_later ~= r_observed + radial_speed * time_difference.
                    # This linear approximation cannot correct abrupt turns or
                    # echoes that came from different objects/body surfaces.
                    ranges[node] += radial_speed * (stamp - sample[1])
        # 4. Solve the two-circle equations at that common estimated time.
        try:
            point = locate(g, *ranges)
        except ValueError:
            self.invalidate("Inconsistent echoes", allow_prediction=True)
            return False

        # 5. Check each acoustic cone at its own observation time. Back-project
        # the candidate to the earlier sample before comparing its bearing with
        # the commanded aim. Passing this gate does not prove echo identity.
        for node, sample in enumerate((left, right)):
            dt = stamp - sample[1]
            observation = tuple(point[i] - self.velocity[i]*dt for i in (0, 1)) if model_recent else point
            if abs(g.angle(node, observation)-sample[0].angle_mdeg) > g.beam_half_angle_deg*1000:
                self.invalidate("Echoes outside aimed beams", allow_prediction=True)
                return False
        dt = stamp - self.last_good
        if model_recent and self.raw is not None:
            # 6. Bound the movement since the last accepted raw position. The
            # extra 0.15 m is noise tolerance, not a claimed sensor accuracy.
            if math.dist(point, self.raw) > g.max_speed_m_s*dt + .15:
                self.invalidate("Position jumped", allow_prediction=True)
                return False

        if not model_recent:
            # First fix, or a model too old to reuse: initialize position only.
            # Controller still requires another consistent pair before lock-on.
            self.filtered = point
            self.velocity = (0.0, 0.0)
            residual = 0.0
        else:
            # 7. Alpha-beta filter: first predict, then correct from the echo pair.
            # A useful intuition is that alpha adjusts WHERE the player is and
            # beta adjusts HOW FAST and in which direction they are moving.
            expected = self.predict(stamp, horizon=g.local_search_s)
            error = tuple(point[i]-expected[i] for i in (0, 1))
            residual = math.hypot(*error)
            # alpha grows with time between samples. Bounds prevent the filter
            # either ignoring a new observation or responding with full gain
            # when smoothing is enabled. beta is coupled to alpha empirically.
            alpha = 1.0 if g.smoothing_tau_s == 0 else min(.9, max(.35, 1-math.exp(-dt/g.smoothing_tau_s)))
            beta = .5 * alpha * alpha
            # p_new = p_predicted + alpha * (p_measured - p_predicted)
            self.filtered = tuple(expected[i]+alpha*error[i] for i in (0, 1))
            # v_new = v_old + (beta/dt) * position_error.
            # Repeated consistent errors teach the filter the movement speed.
            # The millisecond denominator floor avoids an unstable tiny divisor.
            velocity = tuple(self.velocity[i]+beta*error[i]/max(dt, .001) for i in (0, 1))
            speed = math.hypot(*velocity)
            if speed > g.max_speed_m_s:
                velocity = tuple(v*g.max_speed_m_s/speed for v in velocity)
            self.velocity = velocity
        # 8. Only an accepted observation updates this timestamp. Drawing a spot,
        # predicting the next aim or receiving an invalid echo cannot refresh it.
        self.raw = point
        self.last_good = stamp
        self.valid = True
        self.allow_prediction = True
        self.dead_zone = 0 <= point[0] <= g.width and point[1] < g.near_y-.002
        # A heuristic consistency score based on prediction error. It is not a
        # probability, a calibrated accuracy figure or a gameplay decision.
        self.confidence = max(.1, min(1.0, 1.0-residual/.5))
        self.reason = "Tracking"
        return True

    def position(self, now: float):
        """Return a display estimate only while a measured fix is recent enough.

        This can animate between sensor updates, but creates no new measurement.
        With the default 0.20 s horizon a prolonged dropout returns None and the
        UI removes the spot. Controller also hides unconfirmed/lost candidates.
        """
        if not (self.valid or self.allow_prediction) or self.filtered is None:
            return None
        if now-self.last_good > self.geometry.prediction_horizon_s:
            return None
        return self.predict(now)

    def in_bounds(self, now: float | None = None) -> bool:
        """Require both the raw fix and displayed estimate to be in the field.

        Smoothing must not turn a real out-of-field observation into a valid edge
        point. The 2 mm tolerance accommodates integer-millimetre quantization;
        it is unrelated to the much larger possible error on a moving person.
        """
        point = self.filtered if now is None else self.position(now)
        if point is None or not (self.valid or self.allow_prediction) or self.raw is None:
            return False
        g = self.geometry
        return all(-.002 <= p[0] <= g.width+.002 and
                   g.near_y-.002 <= p[1] <= g.far_y+.002
                   for p in (self.raw, point))
