"""How well the swarm tracker holds a player who stands still on a hole.

Run from the project root:

    python3 -m tools.stand_bench
    python3 -m tools.stand_bench --miss 0.3 --edge 0.5 --csv results/stand-bench.csv

The field is the one played on 5 October 2026: config.prototype.json with
that evening's arcs (box 0 30-100 degrees, box 1 30-120, box 2 80-150, servo
travel 30-150) and its empty-room map. In that map box 0 heard something
0.62 m away at 30 and 35 degrees and box 2 something 0.66 m away at 150
degrees, about the distance to the middle box, at the inner ends of their
arcs; nothing else was within reach.

What a simulated box hears on each ping (SimulatedTransport, with a target
function that knows where the box is aimed):

- the player, a disc of body_radius_m, when inside the beam; a fraction
  --miss of those pings get no echo, as an HC-SR04 does miss a person;
- the static object at its mapped range whenever box 0 is aimed at 37.5
  degrees or less and box 2 at 147.5 degrees or more, the bearings the map
  has it at; and, with probability --edge, when they are aimed up to 10
  degrees further in: there it is heard at the edge of the beam on some
  pings only, too rarely to be mapped from three pings per bearing;
- the nearer of the two when both answer: the sensor reports the first echo.

The player stands for --seconds at each point the game puts holes on, after
the tracker has found them there. The game mirrors x (its box 0 is on the
player's right); the lattice is symmetric, so the points are the same.

Variants:

    before   the tracker before the change of 5 October 2026: anything at or
             beyond a mapped echo at the nearest mapped bearing is
             background, a missed ping forgets the last echo and a reading
             confirms only one at the same bearing (within one sweep step),
             readings are fused on their ranges alone, and when boxes
             disagree the newest reading wins
    after    the tracker as it is

Simulation only. The echo model, the miss rate and the edge probability are
assumptions; the numbers say how the two versions treat the same echoes, not
how often a real room produces them.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import math
from pathlib import Path
import random
import statistics
import tempfile

from whack.swarm import SwarmController, fuse
from whack.tracking import load_geometry
from whack.transport import SimulatedTransport

ARCS = ((30, 100), (30, 120), (80, 150))
TRAVEL = (30, 150)
# The empty-room map of 5 October 2026 02:32: box, bearing in degrees, range in metres.
MAPPED = ((0, 30, .62), (0, 35, .62), (2, 150, .66))
# Where each object is heard: always while the box is aimed inside `always`,
# on some pings (--edge) while it is aimed inside `edge`.
OBJECTS = (
    {"node": 0, "range_m": .62, "always": (0, 37.5), "edge": (37.5, 47.5)},
    {"node": 2, "range_m": .66, "always": (147.5, 180), "edge": (137.5, 147.5)},
)
COLUMNS_M = (.25, .50, .75, 1.00, 1.25)        # hole lattice of the game, metres from the field's left edge
ROWS_M = (1.10, 1.42, 1.74)                    # metres from the screen wall
HOLE_HALF_M = (.1727, .1402)                   # the game's contact area of a hole: half width, half depth
SETTLE_S = 10.0                                # the tracker must have found the player by then
JUMP_M = .35                                   # an estimate this far from the player counts as a jump
VARIANTS = ("before", "after")


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Before(SwarmController):
    """The tracker as it was at commit 3191700: classification and fusion as they were."""

    def _classify(self, box, message, now):
        g = self.geometry
        if message.status != "OK":
            box.last_reading = None
            return "none", None
        d = message.distance_mm/1000
        if d < g.min_player_range_m:
            return "close", d
        if self.background and not self.simulate and self._is_background(box.node, message.angle_mdeg, d):
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

    def _is_background(self, node, bearing, d):
        best = None
        for b in self._grid(node):
            if abs(b - bearing) <= self.step_mdeg and (best is None or abs(b - bearing) < abs(best - bearing)):
                best = b
        if best is None:
            return False
        mapped = self.background.get(f"{node}:{best}")
        return mapped is not None and d >= mapped - self.geometry.background_margin_m

    def _absorb(self, contribution, now):
        g = self.geometry
        fresh = {n: c for n, c in self.contributions.items() if now - c.time <= self.FUSE_WINDOW_S}
        fresh[contribution.node] = contribution
        point = contribution.point
        if len(fresh) >= 2:
            point, worst = fuse(g, list(fresh.values()))
            if worst > self.RESIDUAL_M:
                others = [c for c in fresh.values() if c.node != contribution.node]
                if max(math.dist(contribution.point, c.point) for c in others) >= g.two_player_separation_m:
                    self.inconsistent.append(now)
                fresh = {contribution.node: contribution}
                point = contribution.point
        self._accept(contribution, fresh, point, now)
        return True


def field_geometry(config):
    return replace(load_geometry(config), sweep_bounds_deg=ARCS, servo_travel_deg=TRAVEL)


def field_map(controller):
    background = {f"{n}:{b}": None for n in range(controller.count) for b in controller._grid(n)}
    for node, degrees, range_m in MAPPED:
        background[f"{node}:{degrees*1000}"] = range_m
    return background


def scene(transport, player, miss, edge, rng):
    """Target function for SimulatedTransport: what box `node` hears on the ping it fires now."""
    g = transport.geometry

    def target(now, node):
        aim = transport.angles[node]/1000
        sx, sy = g.sensor_position(node)
        echoes = []
        if player is not None and abs(g.angle(node, player)/1000 - aim) <= g.beam_half_angle_deg \
                and rng.random() >= miss:
            echoes.append((math.dist((sx, sy), player) - g.body_radius_m, player))
        for thing in OBJECTS:
            low, high = thing["always"]
            near, far = thing["edge"]
            if thing["node"] == node and (low <= aim <= high or (near <= aim <= far and rng.random() < edge)):
                # A point straight along the beam whose echo comes back from the object's range.
                reach = thing["range_m"] + g.body_radius_m
                a = math.radians(aim)
                echoes.append((thing["range_m"], (sx + reach*math.cos(a), sy + reach*math.sin(a))))
        return min(echoes)[1] if echoes else None

    return target


def stand(variant, geometry, spot, seconds, miss, edge, seed, tick=.01):
    """Stand at `spot` (tracker frame); what the tracker made of it over `seconds` once found."""
    clock = Clock()
    transport = SimulatedTransport(clock, geometry)
    with tempfile.TemporaryDirectory() as folder:
        kind = Before if variant == "before" else SwarmController
        controller = kind(geometry, clock=clock, transport=transport,
                          calibration_path=Path(folder) / "none.json")
    controller.background = field_map(controller)
    transport.target = scene(transport, spot, miss, edge, random.Random(seed))
    found = None
    while clock.now < SETTLE_S:
        snap = controller.poll()
        clock.now += tick
        if snap.position is not None and math.dist(snap.position, spot) < .25:
            found = clock.now
            break
    if found is None:
        return None
    polls = on_hole = two_box = shown = jumps = losses = 0
    errors = []
    tracking, away = True, False
    end = clock.now + seconds
    while clock.now < end:
        snap = controller.poll()
        clock.now += tick
        polls += 1
        two_box += snap.contributors >= 2
        if (snap.state == "track") != tracking:
            tracking = not tracking
            losses += not tracking
        if snap.position is None:
            continue
        shown += 1
        dx, dy = snap.position[0] - spot[0], snap.position[1] - spot[1]
        on_hole += (dx/HOLE_HALF_M[0])**2 + (dy/HOLE_HALF_M[1])**2 <= 1
        error = math.hypot(dx, dy)
        errors.append(error)
        if (error > JUMP_M) != away:
            away = not away
            jumps += away
    minutes = seconds/60
    return {
        "losses_per_min": losses/minutes, "jumps_per_min": jumps/minutes, "on_hole": on_hole/polls,
        "two_box": two_box/polls, "shown": shown/polls,
        "median_error_m": statistics.median(errors) if errors else None,
        "outvoted": sum(box.rejections.get("outvoted", 0) for box in controller.boxes),
    }


def spots():
    """(game x, y) of every hole the game uses, and the same point in the tracker frame (x mirrored)."""
    return [((x, y), (1.5 - x, y)) for y in ROWS_M for x in COLUMNS_M]


def mean(rows, key):
    values = [row[key] for row in rows if row is not None and row[key] is not None]
    return statistics.mean(values) if values else float("nan")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="config.prototype.json")
    parser.add_argument("--seconds", type=float, default=30.0, help="standing time per trial once found")
    parser.add_argument("--trials", type=int, default=3, help="trials per hole, each with its own random seed")
    parser.add_argument("--miss", type=float, default=.15, help="share of pings at the player that get no echo")
    parser.add_argument("--edge", type=float, default=.3, help="chance a box hears the object at the edge of its beam")
    parser.add_argument("--csv", help="write one row per trial to this file")
    args = parser.parse_args()
    geometry = field_geometry(args.config)
    results = {}
    for variant in VARIANTS:
        for game_spot, tracker_spot in spots():
            results[variant, game_spot] = [
                stand(variant, geometry, tracker_spot, args.seconds, args.miss, args.edge, seed)
                for seed in range(args.trials)]
    print(f"{args.config} with the arcs and empty-room map of 5 October 2026; {args.trials} trials of "
          f"{args.seconds:g} s per hole; {args.miss:.0%} of pings at the player missed; the object heard "
          f"on {args.edge:.0%} of pings at the edge of a beam. Mean over the trials.\n")
    print("| Hole (x, y m) | Losses/min before | after | Jumps/min before | after | On the hole before | after |")
    print("|---|---|---|---|---|---|---|")
    for game_spot, _ in spots():
        before, after = results["before", game_spot], results["after", game_spot]
        print(f"| ({game_spot[0]:.2f}, {game_spot[1]:.2f}) | {mean(before, 'losses_per_min'):.1f} | "
              f"{mean(after, 'losses_per_min'):.1f} | {mean(before, 'jumps_per_min'):.1f} | "
              f"{mean(after, 'jumps_per_min'):.1f} | {mean(before, 'on_hole'):.0%} | {mean(after, 'on_hole'):.0%} |")
    print("\n| Variant | Losses/min | Jumps/min | On the hole | Two boxes or more | Position shown | "
          "Median error | Not found in 10 s |")
    print("|---|---|---|---|---|---|---|---|")
    for variant in VARIANTS:
        rows = [row for (v, _), trials in results.items() if v == variant for row in trials]
        print(f"| {variant} | {mean(rows, 'losses_per_min'):.1f} | {mean(rows, 'jumps_per_min'):.1f} | "
              f"{mean(rows, 'on_hole'):.0%} | {mean(rows, 'two_box'):.0%} | {mean(rows, 'shown'):.0%} | "
              f"{mean(rows, 'median_error_m')*100:.1f} cm | {sum(row is None for row in rows)} of {len(rows)} |")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("variant", "hole_x_m", "hole_y_m", "seed", "losses_per_min", "jumps_per_min",
                             "on_hole", "two_box", "shown", "median_error_m", "outvoted"))
            for (variant, (x, y)), trials in results.items():
                for seed, row in enumerate(trials):
                    if row is None:
                        writer.writerow((variant, x, y, seed, "", "", "", "", "", "", ""))
                        continue
                    writer.writerow((variant, x, y, seed, f"{row['losses_per_min']:.2f}", f"{row['jumps_per_min']:.2f}",
                                     f"{row['on_hole']:.3f}", f"{row['two_box']:.3f}", f"{row['shown']:.3f}",
                                     "" if row["median_error_m"] is None else f"{row['median_error_m']:.4f}",
                                     row["outvoted"]))


if __name__ == "__main__":
    main()
