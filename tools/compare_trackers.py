"""Compare swarm trackers from different commits on the same simulated scenes.

Run from the project root:

    python3 -m tools.compare_trackers                         # 3191700 vs aee8ef0 vs the working tree
    python3 -m tools.compare_trackers 3191700 HEAD --miss .3 --edge .6

Each argument is a git commit (its whack/swarm.py is loaded) or "worktree"
(the file on disk). Every tracker meets the same scenes and seeds:

stand   the player stands still for --seconds on each of the 15 hole
        positions in the 5 October 2026 field: its arcs, its empty-room map
        (box 0 heard something 0.62 m away at 30-35 degrees, box 2 0.66 m at
        150), that object also heard up to 10 degrees further in on --edge of
        the pings, and --miss of the pings at the player missed. The scene is
        the one of tools/stand_bench.py on CamHaoHa/ghost-echo-rejection.
jump    tools/jump_bench.py: the player jumps between the three columns; the
        seconds to the first fix and the first two-box fix at the new spot,
        without a hint and with the right mole hint.
walk    the player walks across at 0.5 m/s, 0.92 m out from the sensor line.

Simulation only: the echo model, miss rate and edge probability are
assumptions. The numbers say how the trackers treat the same echoes, not how
often a real room produces them.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import types

from whack.tracking import load_geometry
from whack.transport import SimulatedTransport
from tools import jump_bench

ARCS = ((30, 100), (30, 120), (80, 150))
TRAVEL = (30, 150)
MAPPED = ((0, 30, .62), (0, 35, .62), (2, 150, .66))     # box, bearing in degrees, range in metres
OBJECTS = (
    {"node": 0, "range_m": .62, "always": (0, 37.5), "edge": (37.5, 47.5)},
    {"node": 2, "range_m": .66, "always": (147.5, 180), "edge": (137.5, 147.5)},
)
HOLES = [(x, y) for y in (1.10, 1.42, 1.74) for x in (.25, .50, .75, 1.00, 1.25)]
HOLE_HALF_M = (.1727, .1402)
SETTLE_S = 10.0
JUMP_M = .35


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def load_tracker(ref):
    """The SwarmController class of `ref`: a git commit, or "worktree"."""
    if ref == "worktree":
        source = Path("whack/swarm.py").read_text()
    else:
        source = subprocess.run(["git", "show", f"{ref}:whack/swarm.py"], check=True,
                                capture_output=True, text=True).stdout
    name = f"whack._swarm_{len(sys.modules)}"
    module = types.ModuleType(name)
    sys.modules[name] = module                      # dataclasses look their module up by name
    exec(compile(source.replace("from .", "from whack."), f"{ref}:whack/swarm.py", "exec"), module.__dict__)
    return module.SwarmController


def scene(transport, player, miss, edge, rng):
    g = transport.geometry

    def target(now, node):
        aim = transport.angles[node]/1000
        sx, sy = g.sensor_position(node)
        echoes = []
        if abs(g.angle(node, player)/1000 - aim) <= g.beam_half_angle_deg and rng.random() >= miss:
            echoes.append((math.dist((sx, sy), player) - g.body_radius_m, player))
        for thing in OBJECTS:
            low, high = thing["always"]
            near, far = thing["edge"]
            if thing["node"] == node and (low <= aim <= high or (near <= aim <= far and rng.random() < edge)):
                reach, a = thing["range_m"] + g.body_radius_m, math.radians(aim)
                echoes.append((thing["range_m"], (sx + reach*math.cos(a), sy + reach*math.sin(a))))
        return min(echoes)[1] if echoes else None

    return target


def stand(tracker, geometry, spot, seconds, miss, edge, seed, tick=.01):
    clock = Clock()
    transport = SimulatedTransport(clock, geometry)
    with tempfile.TemporaryDirectory() as folder:
        controller = tracker(geometry, clock=clock, transport=transport, calibration_path=Path(folder) / "none.json")
    controller.background = {f"{n}:{b}": None for n in range(controller.count) for b in controller._grid(n)}
    for node, degrees, range_m in MAPPED:
        controller.background[f"{node}:{degrees*1000}"] = range_m
    transport.target = scene(transport, spot, miss, edge, random.Random(seed))
    while clock.now < SETTLE_S:
        snap = controller.poll()
        clock.now += tick
        if snap.position is not None and math.dist(snap.position, spot) < .25:
            break
    else:
        return None
    polls = on_hole = two_box = losses = jumps = 0
    tracking, away, end = True, False, clock.now + seconds
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
        dx, dy = snap.position[0] - spot[0], snap.position[1] - spot[1]
        on_hole += (dx/HOLE_HALF_M[0])**2 + (dy/HOLE_HALF_M[1])**2 <= 1
        if (math.hypot(dx, dy) > JUMP_M) != away:
            away = not away
            jumps += away
    return {"losses": losses*60/seconds, "jumps": jumps*60/seconds, "on_hole": on_hole/polls, "two_box": two_box/polls}


def walk(tracker, geometry, seconds=60, tick=.01):
    clock = Clock()
    controller = tracker(geometry, simulate=True, clock=clock)

    def where(t):
        return (.2 + abs((t*.5) % 2.2 - 1.1), geometry.sensor_y + .92)

    controller.transport.target = lambda now, node=None: where(now)
    while clock.now < 5:
        controller.poll()
        clock.now += tick
    errors, losses, tracking = [], 0, True
    while clock.now < 5 + seconds:
        snap = controller.poll()
        clock.now += tick
        if (snap.state == "track") != tracking:
            tracking = not tracking
            losses += not tracking
        if snap.position is not None:
            errors.append(math.dist(snap.position, where(clock.now)))
    errors.sort()
    return statistics.median(errors), errors[int(.9*len(errors))], losses


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else float("nan")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("refs", nargs="*", default=["3191700", "aee8ef0", "worktree"],
                        help='git commits, or "worktree" for whack/swarm.py on disk')
    parser.add_argument("--config", default="config.prototype.json")
    parser.add_argument("--seconds", type=float, default=30.0, help="standing time per trial")
    parser.add_argument("--trials", type=int, default=6, help="standing trials per hole")
    parser.add_argument("--miss", type=float, default=.15, help="share of pings at the player that get no echo")
    parser.add_argument("--edge", type=float, default=.3, help="chance a box hears the object at the edge of its beam")
    args = parser.parse_args()
    trackers = {ref: load_tracker(ref) for ref in args.refs}
    geometry = load_geometry(args.config)
    field = replace(geometry, sweep_bounds_deg=ARCS, servo_travel_deg=TRAVEL)

    print(f"Standing still: {len(HOLES)} holes x {args.trials} trials x {args.seconds:g} s, "
          f"{args.miss:.0%} of pings at the player missed, object heard on {args.edge:.0%} at the beam edge\n")
    print("| Tracker | Losses/min | Jumps/min | On the hole | Two boxes | Not found |")
    print("|---|---|---|---|---|---|")
    for ref, tracker in trackers.items():
        rows = [stand(tracker, field, (1.5 - x, y), args.seconds, args.miss, args.edge, seed)
                for x, y in HOLES for seed in range(args.trials)]
        found = [r for r in rows if r]
        mean = lambda key: statistics.mean(r[key] for r in found) if found else float("nan")
        print(f"| {ref} | {mean('losses'):.1f} | {mean('jumps'):.1f} | {mean('on_hole'):.0%} | "
              f"{mean('two_box'):.0%} | {len(rows) - len(found)} of {len(rows)} |")

    moments = [jump_bench.SETTLE_S + n*.05 for n in range(20)]
    print("\nJumps between columns: seconds to the first fix / first two-box fix, median of 20\n")
    print("| Jump | Hint | " + " | ".join(trackers) + " |")
    print("|---|---|" + "---|"*len(trackers))
    firsts = {ref: [] for ref in trackers}
    for variant, hint in (("search", "none"), ("right hint", "right")):
        for jump in jump_bench.JUMPS:
            cells = []
            for ref, tracker in trackers.items():
                jump_bench.SwarmController = tracker
                results = [jump_bench.trial(variant, geometry, jump, at, .01) for at in moments]
                firsts[ref] += [r[0] for r in results]
                cells.append(f"{median([r[0] for r in results]):.2f} / {median([r[1] for r in results]):.2f}")
            print(f"| {jump_bench.label(jump)} | {hint} | " + " | ".join(cells) + " |")
    print("| all | | " + " | ".join(f"{median(v):.2f}" for v in firsts.values()) + " |")

    print("\nWalking across at 0.5 m/s for 60 s\n")
    print("| Tracker | Median error | 90th percentile | Losses |")
    print("|---|---|---|---|")
    for ref, tracker in trackers.items():
        mid, p90, losses = walk(tracker, geometry)
        print(f"| {ref} | {mid*100:.1f} cm | {p90*100:.1f} cm | {losses} |")


if __name__ == "__main__":
    main()
