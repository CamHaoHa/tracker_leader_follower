"""Search -> lock -> window-scan tracking for N ultrasonic boxes (--tracker lock).

A laptop-side port of the single-box Arduino sketch from 30 September 2026:

    SEARCH  step the servo STEP_DEG at a time across the box's arc, one ping
            per bearing, bouncing at the bounds; the first in-range echo locks
    TRACK   scan a +/-WINDOW_DEG window around the locked bearing in STEP_DEG
            steps, alternating direction each pass; every echo within
            MAX_JUMP of the locked range is a hit; at the end of the pass
            locked bearing = mean hit bearing (centre of the object) and
            locked range = 0.7 old + 0.3 mean hit range; LOST_LIMIT empty
            passes in a row drop back to SEARCH from the locked bearing

Every box runs the state machine on its own; nothing aims a box at another
box's fix. The laptop plays the sketch's loop through the WM2 AIM/FIRE
protocol: the servo settle is the firmware's READY, so the sketch's
delay(SETTLE_MS) does not exist here. The acoustic slot is still shared,
one ping in the air at a time with the 65 ms guard, so a pass with N boxes
takes about N times longer than the sketch's 11 x 65 ms.

The spot is the fusion of every locked box: one box gives a polar point
(bearing, range + body radius), two or more give the least-squares point
over their range circles, exactly as in swarm.py. A box's fix keeps counting
until the box unlocks (LOST_LIMIT empty passes), not until a timer runs out.

Sketch constant -> setting:
    STEP_DEG      lock_step_deg        WINDOW_DEG   lock_window_deg
    MAX_JUMP_CM   lock_max_jump_m      LOST_LIMIT   lock_lost_limit
    MAX_RANGE_CM  reliable_range_m     MIN/MAX_ANGLE  the box's sweep bounds
                                                      (search) and the servo
                                                      travel (window)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

from .swarm import Contribution, SwarmController, fuse


@dataclass
class Lock:
    """One box's search/track state: the sketch's globals."""
    mode: str = "search"            # search | track
    search_bearing: int = 90000     # searchAngle, millidegrees
    search_step: int = -3000        # searchDir * STEP_DEG, signed millidegrees
    bearing: int = 90000            # lockedAngle
    range_m: float = 0.0            # lockedDist, smoothed surface range
    fix_time: float | None = None   # when bearing/range were last measured
    lost: int = 0                   # lostCount: empty passes in a row
    forward: bool = True            # scanForward
    pending: list = field(default_factory=list)   # bearings still to ping this pass
    window: tuple | None = None     # (lo, hi) millidegrees of the current pass
    pass_length: int = 0
    angle_sum: int = 0
    range_sum: float = 0.0
    stamp_sum: float = 0.0
    hits: int = 0
    last_hits: int = 0              # hits in the previous pass, for the display


class LockScanController(SwarmController):
    RANGE_SMOOTHING = 0.3           # lockedDist = 0.7 old + 0.3 new
    FUSE_WINDOW_S = float("inf")    # a locked box's fix counts until it unlocks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock_step = round(self.geometry.lock_step_deg*1000)
        self.window_mdeg = round(self.geometry.lock_window_deg*1000)
        self.locks = [Lock() for _ in self.boxes]
        for box, lock in zip(self.boxes, self.locks):
            self._unlock(box, lock, box.bearing)

    # ----- state ----------------------------------------------------------
    def _unlock(self, box, lock, from_bearing):
        """Back to SEARCH, continuing from `from_bearing` in the current direction."""
        lock.mode = box.mode = "search"
        lock.search_bearing = from_bearing
        if abs(lock.search_step) != self.lock_step:
            lock.search_step = -self.lock_step
        lock.pending, lock.window, lock.fix_time = [], None, None
        lock.lost = lock.hits = lock.last_hits = lock.pass_length = 0
        lock.angle_sum, lock.range_sum, lock.stamp_sum = 0, 0.0, 0.0

    def _clear_player(self):
        super()._clear_player()
        for box, lock in zip(self.boxes, self.locks):
            self._unlock(box, lock, box.bearing)

    def _expire(self, now):
        pass    # a lock is dropped by LOST_LIMIT empty passes, never by a timer

    def _fresh_fix(self, now):
        return any(l.mode == "track" and l.fix_time is not None for l in self.locks)

    def _confidence(self, now):
        locked = [l for l in self.locks if l.mode == "track" and l.fix_time is not None]
        if not locked:
            return 0.0
        return self.estimate.confidence*(1-min(l.lost for l in locked)/self.geometry.lock_lost_limit)

    # ----- bearings ---------------------------------------------------------
    def _choose_bearing(self, box, now):
        if self.calibrating:
            return super()._choose_bearing(box, now)
        if box.hold_bearing is not None:            # "sensor busy": ping the same bearing again
            b, box.hold_bearing = box.hold_bearing, None
            return b
        lock = self.locks[box.node]
        if lock.mode == "track" and not lock.pending:
            self._finish_pass(box, lock, now)
        if lock.mode == "track":
            return lock.pending.pop(0)
        return self._next_search_bearing(box, lock)

    def _next_search_bearing(self, box, lock):
        """search(): advance STEP_DEG, park on a bound and turn round there."""
        lo, hi = self._bounds(box.node)
        b = lock.search_bearing + lock.search_step
        if b >= hi:
            b, lock.search_step = hi, -self.lock_step
        elif b <= lo:
            b, lock.search_step = lo, self.lock_step
        lock.search_bearing = b
        return b

    def _start_pass(self, box, lock):
        """track(): plan one window scan, lo->hi or hi->lo, alternating."""
        t_lo, t_hi = (round(v*1000) for v in self.geometry.servo_travel_deg)
        lo = max(t_lo, lock.bearing - self.window_mdeg)
        hi = min(t_hi, lock.bearing + self.window_mdeg)
        s = self.lock_step
        lock.pending = list(range(lo, hi+1, s)) if lock.forward else list(range(hi, lo-1, -s))
        lock.forward = not lock.forward
        lock.window = (lo, hi)
        lock.pass_length = len(lock.pending)
        lock.angle_sum, lock.range_sum, lock.stamp_sum, lock.hits = 0, 0.0, 0.0, 0

    def _finish_pass(self, box, lock, now):
        """End of a window scan: re-centre on the hits, or count a miss."""
        lock.last_hits = lock.hits
        if lock.hits:
            lock.bearing = round(lock.angle_sum/lock.hits)               # centre of the object
            lock.range_m = ((1-self.RANGE_SMOOTHING)*lock.range_m
                            + self.RANGE_SMOOTHING*lock.range_sum/lock.hits)  # smoothed distance
            lock.fix_time = lock.stamp_sum/lock.hits
            lock.lost = 0
            self._publish(box.node, now)
        else:
            lock.lost += 1
            if lock.lost >= self.geometry.lock_lost_limit:
                box.status = f"lost near {lock.bearing/1000:.0f} deg - searching"
                self._unlock(box, lock, lock.bearing)
                self._publish(None, now)
                return
        self._start_pass(box, lock)

    # ----- readings ---------------------------------------------------------
    def _echo(self, box, message):
        """('hit' | 'close' | 'background' | 'far' | 'none', surface range or None)."""
        g = self.geometry
        if message.status != "OK":
            return "none", None
        d = message.distance_mm/1000
        if d < g.min_player_range_m:
            return "close", d
        if self.background and not self.simulate:
            baseline, known = self._background_at(box.node, message.angle_mdeg)
            if known and baseline is not None and d >= baseline - g.background_margin_m:
                box.rejections["background"] = box.rejections.get("background", 0) + 1
                return "background", d
        if d > g.reliable_range_m:
            return "far", d
        return "hit", d

    @staticmethod
    def _describe(kind, d, message):
        if kind == "none":
            return message.status.lower()
        return f"{d:.2f} m {'far' if kind == 'far' else 'background'}"

    def _on_range(self, box, message, stamp, now, txn_mode="search"):
        g = self.geometry
        if self.calibrating:
            self._calibration_sample(box, message)
            return
        lock = self.locks[box.node]
        kind, d = self._echo(box, message)
        here = f"{message.angle_mdeg/1000:.0f} deg"
        if kind == "close":
            box.status = f"{here}: {d:.2f} m TOO CLOSE"
            self.too_close_since.setdefault(box.node, now)
            return
        self.too_close_since.pop(box.node, None)
        if lock.mode == "search":
            if kind != "hit":
                box.status = f"search {here}: {self._describe(kind, d, message)}"
                return
            # Target found -> TRACK
            lock.mode = box.mode = "track"
            lock.bearing, lock.range_m, lock.fix_time, lock.lost = message.angle_mdeg, d, stamp, 0
            lock.forward = True
            self._start_pass(box, lock)
            box.status = f"{here}: {d:.2f} m locked"
            self._publish(box.node, now)
            return
        # sample(): accumulate the reading if it looks like our object
        if kind == "hit" and abs(d - lock.range_m) < g.lock_max_jump_m:
            lock.angle_sum += message.angle_mdeg
            lock.range_sum += d
            lock.stamp_sum += stamp
            lock.hits += 1
            box.status = f"window {here}: {d:.2f} m hit {lock.hits}/{lock.pass_length}"
        elif kind == "hit":
            box.status = f"window {here}: {d:.2f} m other object"
        else:
            box.status = f"window {here}: {self._describe(kind, d, message)}"

    def _publish(self, node, now):
        """Fuse every locked box into the spot. `node` is the box that just changed."""
        g = self.geometry
        fresh = {}
        for box, lock in zip(self.boxes, self.locks):
            if lock.mode == "track" and lock.fix_time is not None:
                point, r = self._polar(box.node, lock.bearing, lock.range_m)
                fresh[box.node] = Contribution(box.node, lock.fix_time, lock.bearing, r, point)
        if not fresh:
            self.contributions.clear()
            if self.state == "track":
                self.state, self.reason = "find", "Player lost - searching"
            return
        newest = fresh[node] if node in fresh else max(fresh.values(), key=lambda c: c.time)
        stamp = max(c.time for c in fresh.values())
        if len(fresh) >= 2:
            point, worst = fuse(g, list(fresh.values()))
            if worst > self.RESIDUAL_M:
                # Inconsistent boxes: keep the one that just reported, note it.
                others = [c for c in fresh.values() if c.node != newest.node]
                if max(math.dist(newest.point, c.point) for c in others) >= g.two_player_separation_m:
                    self.inconsistent.append(now)
                fresh, point = {newest.node: newest}, newest.point
        else:
            point = newest.point
        self.contributions = fresh
        if not self.estimate.update(point, stamp, len(fresh)):
            self.reason = "Position jumped"
            return
        self.good_times.append(stamp)
        self.state = "track"
        self.reason = "Tracking" if len(fresh) >= 2 else "Tracking (one box)"

    # ----- display ----------------------------------------------------------
    def _box_info(self):
        g = self.geometry
        info = []
        for box, lock in zip(self.boxes, self.locks):
            entry = {"node": box.node, "mode": lock.mode, "bearing_deg": box.bearing/1000,
                     "lost": lock.lost, "hits": lock.hits, "last_hits": lock.last_hits,
                     "pass": (lock.pass_length - len(lock.pending), lock.pass_length)}
            if lock.mode == "track":
                entry["window_deg"] = tuple(v/1000 for v in lock.window) if lock.window else None
                entry["lock"] = (lock.bearing/1000, lock.range_m + g.body_radius_m)
            info.append(entry)
        return tuple(info)

    def _snapshot(self, now, online, ready_to_run):
        snap = super()._snapshot(now, online, ready_to_run)
        if snap.state == "track" and snap.status.startswith("Tracking"):
            locks = ", ".join(f"box {b.node} {l.bearing/1000:.0f} deg {l.range_m:.2f} m"
                              for b, l in zip(self.boxes, self.locks) if l.mode == "track")
            snap = replace(snap, status=f"{snap.status} - {locks}")
        return snap
