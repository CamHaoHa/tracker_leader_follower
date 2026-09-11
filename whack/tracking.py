"""Two-circle localization. Coordinates are metres from the left screen corner."""

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Geometry:
    width: float = 1.5
    near_y: float = 0.6
    far_y: float = 2.0
    left_x: float = 0.0
    right_x: float = 1.5
    sensor_y: float = 0.2
    left_offset_m: float = 0.0
    right_offset_m: float = 0.0
    beam_half_angle_deg: float = 20.0
    max_speed_m_s: float = 3.0
    smoothing_tau_s: float = 0.12
    max_pair_skew_s: float = 0.25

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
        if max(abs(self.left_offset_m), abs(self.right_offset_m)) > 0.3:
            raise ValueError("Range offsets must be within 0.3m")

    def angle(self, node: int, point: tuple[float, float]) -> int:
        sx = self.left_x if node == 0 else self.right_x
        return round(math.degrees(math.atan2(point[1] - self.sensor_y, point[0] - sx)) * 1000)

    def scan_targets(self) -> list[tuple[float, float]]:
        centre = (self.width / 2, (self.near_y + self.far_y) / 2)
        targets = [(self.width * x, y)
                   for y in (self.near_y, centre[1], self.far_y, (self.sensor_y + self.near_y) / 2)
                   for x in (0, 0.25, 0.5, 0.75, 1)]
        return [centre] + [point for point in targets if point != centre]


def load_geometry(path: str | None) -> Geometry:
    return Geometry(**json.loads(Path(path).read_text())) if path else Geometry()


def locate(geometry: Geometry, left_m: float, right_m: float) -> tuple[float, float]:
    """Choose the forward intersection; reject impossible or singular circles."""
    r0, r1 = left_m + geometry.left_offset_m, right_m + geometry.right_offset_m
    if not all(math.isfinite(v) and 0.02 <= v <= 4.5 for v in (r0, r1)):
        raise ValueError("Invalid range")
    baseline = geometry.right_x - geometry.left_x
    if r0 + r1 <= baseline or abs(r0 - r1) >= baseline:
        raise ValueError("Ranges have no stable forward intersection")
    x_relative = (r0*r0 - r1*r1 + baseline*baseline) / (2*baseline)
    height_squared = r0*r0 - x_relative*x_relative
    if height_squared <= 0:
        raise ValueError("Ranges have no forward intersection")
    return geometry.left_x + x_relative, geometry.sensor_y + math.sqrt(height_squared)


class Tracker:
    def __init__(self, geometry: Geometry):
        self.geometry = geometry
        self.raw = None
        self.filtered = None
        self.last_good = float("-inf")
        self.valid = False
        self.reason = "Waiting for measurements"
        self.dead_zone = False

    def invalidate(self, reason: str):
        self.valid = False
        self.reason = reason

    def update(self, left, right, now: float):
        # Each sample is (protocol.Range, receive_time). Never mix acquisition pairs.
        if any(s[0].status != "OK" for s in (left, right)):
            self.invalidate("No player echo — searching")
            return
        if abs(left[1] - right[1]) > self.geometry.max_pair_skew_s or now - min(left[1], right[1]) > 1.0:
            self.invalidate("Measurements too far apart — searching")
            return
        try:
            point = locate(self.geometry, left[0].distance_mm / 1000, right[0].distance_mm / 1000)
        except ValueError:
            self.invalidate("Inconsistent echoes — searching")
            return
        if any(abs(self.geometry.angle(node, point) - s[0].angle_mdeg) >
               self.geometry.beam_half_angle_deg * 1000 for node, s in enumerate((left, right))):
            self.invalidate("Echoes outside aimed beams — searching")
            return
        # A raw near-wall observation must not be delayed by display smoothing/speed gate.
        # Tiny numerical tolerance at the boundary; once warned, require3cm clearance.
        unsafe = (-0.002 <= point[0] <= self.geometry.width + 0.002 and
                  point[1] < self.geometry.near_y + (0.03 if self.dead_zone else -0.000001))
        if unsafe:
            self.dead_zone = True
        dt = now - self.last_good
        if self.raw is not None and dt < 1.5 and not unsafe:
            if math.dist(point, self.raw) > self.geometry.max_speed_m_s * dt + 0.15:
                self.invalidate("Position jumped — searching")
                return
        alpha = 1 if self.filtered is None or dt > 1.5 or self.geometry.smoothing_tau_s == 0 else (
            1 - math.exp(-dt / self.geometry.smoothing_tau_s))
        self.filtered = tuple(point[i] if alpha == 1 else self.filtered[i] + alpha*(point[i]-self.filtered[i])
                              for i in (0, 1))
        self.raw, self.last_good, self.valid, self.dead_zone = point, now, True, unsafe
        self.reason = "Tracking"

    def position(self, now: float):
        if self.valid and now - self.last_good > 1.0:
            self.invalidate("Tracking lost — move into the playing area")
        return self.filtered if self.valid else None

    def in_bounds(self) -> bool:
        if not self.valid or self.dead_zone or self.raw is None or self.filtered is None:
            return False
        g = self.geometry
        return all(-0.002 <= p[0] <= g.width + 0.002 and g.near_y - 0.000001 <= p[1] <= g.far_y + 0.002
                   for p in (self.raw, self.filtered))
