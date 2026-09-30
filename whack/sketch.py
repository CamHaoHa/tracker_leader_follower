"""Spot display for boxes running the lock-scan sketch (--tracker sketch).

The tracking algorithm runs ON EACH BOX, unchanged, in
firmware/src/lockscan_main.cpp (the SEARCH/TRACK sketch of 30 September
2026). Every box searches and tracks on its own, at the sketch's own pace
(one ping per SETTLE_MS + echo, about 65 ms), and reports over Wi-Fi:

    LS <node> HELLO                      every 2 s
    LS <node> PING <angle> <cm>          every reading (-1.0 = no echo)
    LS <node> LOCK <angle> <cm>          Target found -> TRACK
    LS <node> TRACK <angle> <cm> <hits>  end of a pass with hits
    LS <node> MISS <lost>                end of an empty pass
    LS <node> LOST                       Target lost -> SEARCH

The laptop never commands a box. It listens, keeps each box's lockedAngle
and lockedDist, and draws one spot: a single locked box gives a polar point
(bearing, range + body radius); two or more give the least-squares point
over their range circles (swarm.fuse). Nothing else is filtered, scheduled
or calibrated here: no background map, no ping slot, no servo commands.

``--simulate`` runs SketchBox, a line-by-line Python twin of the sketch,
per box against the ideal reflector under the mouse, with the sketch's
timing. Boxes ping independently and may overlap, as the real ones do.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import re
import socket
import time

from .controller import Snapshot
from .swarm import Contribution, Estimate, fuse
from .tracking import Geometry

HOST_PORT = 4210
NODE_PORT = 4211
HELLO = b"LS HELLO"

_HEAD = re.compile(r"LS ([0-9]) (HELLO|PING|LOCK|TRACK|MISS|LOST)((?: [-0-9.]{1,8}){0,3})\n?")
_ANGLE, _CM, _COUNT = r"([0-9]{1,3})", r"(-1(?:\.0+)?|[0-9]{1,4}(?:\.[0-9]{1,2})?)", r"([0-9]{1,3})"
_TAIL = {
    "HELLO": re.compile(""), "LOST": re.compile(""),
    "PING": re.compile(f" {_ANGLE} {_CM}"), "LOCK": re.compile(f" {_ANGLE} {_CM}"),
    "TRACK": re.compile(f" {_ANGLE} {_CM} {_COUNT}"), "MISS": re.compile(f" {_COUNT}"),
}


@dataclass(frozen=True)
class Report:
    node: int
    kind: str
    angle: int | None = None
    cm: float | None = None
    count: int | None = None


def parse_report(data: bytes) -> Report | None:
    """One `LS` line from a box, or None for anything else."""
    if len(data) > 96:
        return None
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    head = _HEAD.fullmatch(text)
    if not head:
        return None
    node, kind = int(head[1]), head[2]
    tail = _TAIL[kind].fullmatch(head[3])
    if not tail:
        return None
    if kind in ("PING", "LOCK", "TRACK"):
        angle, cm = int(tail[1]), float(tail[2])
        if angle > 180 or cm > 1000:
            return None
        return Report(node, kind, angle, cm, int(tail[3]) if kind == "TRACK" else None)
    if kind == "MISS":
        return Report(node, kind, count=int(tail[1]))
    return Report(node, kind)


# ----- the sketch, line for line, as a Python generator ------------------------
class SketchBox:
    """One box running the sketch. `requested` is the angle it is pinging;
    ping(cm) delivers that reading and advances to the next request.
    Reports accumulate in `reports` as (kind, angle, cm, count)."""

    MIN_ANGLE, MAX_ANGLE, STEP_DEG, WINDOW_DEG = 0, 180, 3, 15
    SETTLE_S = 0.040
    MAX_RANGE_CM, MAX_JUMP_CM, LOST_LIMIT = 100.0, 25.0, 4

    def __init__(self, node):
        self.node = node
        self.mode = "SEARCH"
        self.searchAngle, self.searchDir = self.MIN_ANGLE, 1
        self.lockedAngle, self.lockedDist, self.lostCount, self.scanForward = 90, 0.0, 0, True
        self.angle = 90                      # servo.write(90) in setup()
        self.reports = []
        self._loop = self._run()
        self.requested = next(self._loop)

    def ping(self, cm):
        self.requested = self._loop.send(cm)
        return self.requested

    def _aim_and_read(self, angle):
        self.angle = angle
        d = yield angle
        self.reports.append(("PING", angle, d, None))
        return d

    def _sample(self, angle, acc):
        d = yield from self._aim_and_read(angle)
        in_range = d > 0 and d < self.MAX_RANGE_CM
        same_object = abs(d - self.lockedDist) < self.MAX_JUMP_CM
        if in_range and same_object:
            acc[0] += angle; acc[1] += d; acc[2] += 1

    def _search(self):
        d = yield from self._aim_and_read(self.searchAngle)
        if d > 0 and d < self.MAX_RANGE_CM:
            self.lockedAngle, self.lockedDist, self.lostCount, self.mode = self.searchAngle, d, 0, "TRACK"
            self.reports.append(("LOCK", self.lockedAngle, self.lockedDist, None))
            return
        self.searchAngle += self.searchDir*self.STEP_DEG
        if self.searchAngle >= self.MAX_ANGLE:
            self.searchAngle, self.searchDir = self.MAX_ANGLE, -1
        elif self.searchAngle <= self.MIN_ANGLE:
            self.searchAngle, self.searchDir = self.MIN_ANGLE, 1

    def _track(self):
        lo = max(self.MIN_ANGLE, self.lockedAngle - self.WINDOW_DEG)
        hi = min(self.MAX_ANGLE, self.lockedAngle + self.WINDOW_DEG)
        acc = [0, 0.0, 0]                    # angleSum, distSum, hits
        bearings = range(lo, hi+1, self.STEP_DEG) if self.scanForward else range(hi, lo-1, -self.STEP_DEG)
        for a in bearings:
            yield from self._sample(a, acc)
        self.scanForward = not self.scanForward
        if acc[2] > 0:
            self.lockedAngle = acc[0] // acc[2]                        # centre of the object (C integer division)
            self.lockedDist = 0.7*self.lockedDist + 0.3*(acc[1]/acc[2])  # smoothed distance
            self.lostCount = 0
            self.angle = self.lockedAngle                              # servo.write(lockedAngle)
            self.reports.append(("TRACK", self.lockedAngle, self.lockedDist, acc[2]))
        else:
            self.lostCount += 1
            if self.lostCount >= self.LOST_LIMIT:
                self.reports.append(("LOST", None, None, None))
                self.mode, self.searchAngle = "SEARCH", self.lockedAngle
            else:
                self.reports.append(("MISS", None, None, self.lostCount))

    def _run(self):
        while True:
            if self.mode == "SEARCH":
                yield from self._search()
            else:
                yield from self._track()


class SketchSimulator:
    """N SketchBox instances against one ideal reflector, each on its own
    clock: a ping costs SETTLE_S plus the echo flight (25 ms when nothing
    returns), exactly the sketch's loop. receive() returns (Report, address,
    stamp) triples like the UDP transport."""

    def __init__(self, clock, geometry):
        self.clock, self.geometry = clock, geometry
        self.target = (geometry.width/2, (geometry.near_y + geometry.far_y)/2)
        self.boxes = [SketchBox(n) for n in range(geometry.sensor_count)]
        self.due = [None]*geometry.sensor_count      # next ping start per box; None = not started
        self.hello_at = [float("-inf")]*geometry.sensor_count
        self.pings = deque(maxlen=4096)      # (stamp, node, angle, cm) for tests

    def address(self, node):
        return (f"sim-{node}", NODE_PORT)

    def close(self):
        pass

    def _echo(self, node, angle, now):
        target = self.target(now) if callable(self.target) else self.target
        if target is None:
            return -1.0
        g = self.geometry
        visible = abs(g.angle(node, target)/1000 - angle) <= g.beam_half_angle_deg
        raw = (math.dist(g.sensor_position(node), target) - g.body_radius_m)*100
        return round(raw, 1) if visible and 2 <= raw <= 400 else -1.0

    def receive(self):
        now = self.clock()
        out = []
        for box in self.boxes:
            n = box.node
            if now - self.hello_at[n] >= 2.0:
                self.hello_at[n] = now
                out.append((Report(n, "HELLO"), self.address(n), now))
            if self.due[n] is None or now - self.due[n] > 1.0:
                self.due[n] = now                 # first poll, or a stalled display: no replay
            while self.due[n] <= now:
                start = self.due[n]
                cm = self._echo(n, box.requested, start + box.SETTLE_S)
                flight = cm/100*2/343 if cm > 0 else 0.025
                stamp = start + box.SETTLE_S + flight
                self.due[n] = stamp
                self.pings.append((stamp, n, box.requested, cm))
                box.ping(cm)
                for kind, angle, value, count in box.reports:
                    out.append((Report(n, kind, angle, value, count), self.address(n), stamp))
                box.reports.clear()
        return out


class SketchUdp:
    """Listen for box reports on the host port; HELLO configured boxes each
    second so they learn this laptop's address, and answer every box HELLO."""

    HELLO_S = 1.0

    def __init__(self, clock, port=HOST_PORT, node_ips=None):
        self.clock = clock
        if node_ips:
            if len(set(node_ips)) != len(node_ips):
                raise ValueError("Node IP addresses must be distinct, left to right")
            for ip in node_ips:
                socket.inet_aton(ip)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.socket.bind(("0.0.0.0", port))
            self.socket.setblocking(False)
        except OSError:
            self.socket.close()
            raise
        self.configured = {n: (ip, NODE_PORT) for n, ip in enumerate(node_ips or ())}
        self.nodes = {}
        self.last_hello = float("-inf")

    def receive(self):
        now = self.clock()
        if self.configured and now - self.last_hello >= self.HELLO_S:
            self.last_hello = now
            for address in self.configured.values():
                try:
                    self.socket.sendto(HELLO, address)
                except OSError:
                    pass
        out = []
        for _ in range(256):
            try:
                data, address = self.socket.recvfrom(128)
            except BlockingIOError:
                break
            except ConnectionResetError:
                continue
            report = parse_report(data)
            if report is None:
                continue
            now = self.clock()
            self.nodes[report.node] = (address, now)
            if report.kind == "HELLO":
                try:
                    self.socket.sendto(HELLO, address)      # so the box learns where to report
                except OSError:
                    pass
            out.append((report, address, now))
        return out

    def address(self, node):
        item = self.nodes.get(node)
        return item[0] if item else self.configured.get(node)

    def close(self):
        self.socket.close()


@dataclass
class BoxView:
    node: int
    mode: str = "offline"            # offline | SEARCH | TRACK
    bearing: float = 90.0            # last reported servo angle
    reading: float | None = None     # last PING in cm, None = no echo
    lock: tuple | None = None        # (lockedAngle, lockedDist cm) while TRACK
    hits: int = 0
    lost: int = 0
    pings: int = 0
    last_seen: float = float("-inf")
    fix_time: float | None = None


class SketchController:
    """Snapshot source for the window: the boxes do the tracking."""

    STALE_S = 6.0
    RESIDUAL_M = 0.30                # two locks further apart than this: keep the newest
    RATE_WINDOW_S = 5.0

    def __init__(self, geometry=None, simulate=False, clock=time.monotonic, transport=None,
                 calibration_path=None, port=HOST_PORT, node_ips=None, start_mode="center",
                 start_paused=False):
        self.geometry = geometry or Geometry()
        self.clock, self.simulate = clock, simulate
        self.transport = transport or (SketchSimulator(clock, self.geometry) if simulate
                                       else SketchUdp(clock, port, node_ips))
        self.count = self.geometry.sensor_count
        self.views = [BoxView(n) for n in range(self.count)]
        self.estimate = Estimate(self.geometry)
        self.contributions = {}
        self.good_times = deque(maxlen=64)
        self.state, self.reason = "find", "Waiting for boxes"
        self.paused = False              # the boxes run on their own; pause only freezes the display
        self.background, self.calibrating = {}, False
        self.calibration_message = ""
        self.message_until = 0.0

    # ----- operator controls (the boxes ignore all of them) -------------------
    def start_calibration(self):
        self.calibration_message = "No calibration: the sketch locks on anything nearer than 1 m"
        self.message_until = self.clock() + 4.0

    def start_acquisition(self):
        self.paused = False
        self._clear()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def reset(self):
        self._clear()

    def park_servos(self):
        pass

    def set_simulated_position(self, x, y):
        if self.simulate and hasattr(self.transport, "target"):
            self.transport.target = (float(x), float(y))

    def close(self):
        self.transport.close()

    def _clear(self):
        self.estimate.reset(); self.contributions.clear(); self.good_times.clear()
        self.state, self.reason = "find", "Waiting for boxes"

    # ----- reports --------------------------------------------------------------
    def _apply(self, report, stamp, now):
        v = self.views[report.node]
        v.last_seen = now
        if v.mode == "offline":
            v.mode = "SEARCH"
        if report.kind == "PING":
            v.bearing, v.pings = float(report.angle), v.pings + 1
            v.reading = None if report.cm < 0 else report.cm
        elif report.kind == "LOCK":
            v.mode, v.lock, v.hits, v.lost, v.fix_time = "TRACK", (report.angle, report.cm), 0, 0, stamp
            self._publish(report.node, now)
        elif report.kind == "TRACK":
            v.mode, v.lock, v.hits, v.lost, v.fix_time = "TRACK", (report.angle, report.cm), report.count, 0, stamp
            self._publish(report.node, now)
        elif report.kind == "MISS":
            v.mode, v.lost = "TRACK", report.count
        elif report.kind == "LOST":
            v.mode, v.lock, v.lost = "SEARCH", None, 0
            self._publish(None, now)

    def _polar(self, node, angle, cm):
        g = self.geometry
        r = cm/100 + g.body_radius_m
        sx, sy = g.sensor_position(node)
        a = math.radians(angle)
        return (sx + r*math.cos(a), sy + r*math.sin(a)), r

    def _publish(self, node, now):
        g = self.geometry
        fresh = {}
        for v in self.views:
            if v.mode == "TRACK" and v.lock and v.fix_time is not None:
                point, r = self._polar(v.node, *v.lock)
                fresh[v.node] = Contribution(v.node, v.fix_time, round(v.lock[0]*1000), r, point)
        if not fresh:
            self.contributions.clear()
            if self.state == "track":
                self.state, self.reason = "find", "Every box is searching"
            return
        newest = fresh[node] if node in fresh else max(fresh.values(), key=lambda c: c.time)
        stamp = max(c.time for c in fresh.values())
        if len(fresh) >= 2:
            point, worst = fuse(g, list(fresh.values()))
            if worst > self.RESIDUAL_M:
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

    # ----- main loop -------------------------------------------------------------
    def poll(self):
        now = self.clock()
        try:
            reports = self.transport.receive()
        except OSError as exc:
            self.reason = f"Network receive failed: {exc}"
            reports = []
        for report, address, stamp in reports:
            if 0 <= report.node < self.count:
                self._apply(report, stamp if stamp is not None else now, now)
        for v in self.views:
            if v.mode != "offline" and now - v.last_seen > self.STALE_S:
                v.mode, v.lock, v.reading = "offline", None, None
                self._publish(None, now)
        return self._snapshot(now)

    def _status(self, v):
        if v.mode == "offline":
            return "offline"
        echo = "no echo" if v.reading is None else f"{v.reading/100:.2f} m"
        if v.mode == "TRACK" and v.lock:
            return (f"TRACK lock {v.lock[0]:.0f} deg {v.lock[1]/100:.2f} m, hits {v.hits}, lost {v.lost}"
                    f" | ping {v.bearing:.0f} deg: {echo}")
        return f"SEARCH {v.bearing:.0f} deg: {echo}"

    def _box_info(self):
        g = self.geometry
        info = []
        for v in self.views:
            entry = {"node": v.node, "mode": "track" if v.mode == "TRACK" else "search",
                     "bearing_deg": v.bearing, "lost": v.lost, "hits": v.hits}
            if v.mode == "TRACK" and v.lock:
                angle, cm = v.lock
                entry["window_deg"] = (max(0, angle - SketchBox.WINDOW_DEG), min(180, angle + SketchBox.WINDOW_DEG))
                entry["lock"] = (float(angle), cm/100 + g.body_radius_m)
            info.append(entry)
        return tuple(info)

    def _snapshot(self, now):
        g = self.geometry
        online = [v for v in self.views if v.mode != "offline"]
        locked = [v for v in self.views if v.mode == "TRACK" and v.lock]
        contributors = len(self.contributions)
        position = self.estimate.point if self.state == "track" and locked and not self.paused else None
        fix_times = [v.fix_time for v in locked if v.fix_time is not None]
        age = max(0.0, now - max(fix_times)) if fix_times else float("inf")
        node_status = tuple(self._status(v) for v in self.views)
        if self.paused:
            status = "Paused: display frozen, the boxes keep running"
        elif now < self.message_until:
            status = self.calibration_message
        elif not online:
            status = f"Waiting for boxes: 0 of {self.count} reporting"
        elif self.state == "track" and position is not None:
            locks = ", ".join(f"box {v.node} {v.lock[0]:.0f} deg {v.lock[1]/100:.2f} m" for v in locked)
            status = ("Tracking player" if contributors >= 2 else "Tracking player (one box)") + " - " + locks
        else:
            modes = ", ".join(f"{v.node}:{v.mode.lower()}" for v in self.views)
            status = f"Searching - {modes}"
        recent = [t for t in self.good_times if now - t <= self.RATE_WINDOW_S]
        rate = (len(recent)-1)/(recent[-1]-recent[0]) if len(recent) > 1 and recent[-1] > recent[0] else 0.0
        in_bounds = position is not None and 0 <= position[0] <= g.width and g.near_y <= position[1] <= g.far_y
        dead_zone = position is not None and 0 <= position[0] <= g.width and position[1] < g.near_y
        confidence = (self.estimate.confidence*(1-min(v.lost for v in locked)/SketchBox.LOST_LIMIT)
                      if position is not None else 0.0)
        return Snapshot(position, status, node_status, dead_zone, in_bounds, self.state,
                        contributors < 2, confidence, age, rate, "", contributors, self._box_info())
