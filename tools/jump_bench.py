"""Time how fast the swarm tracker finds a player who jumps to another column.

Run from the project root:

    python3 -m tools.jump_bench
    python3 -m tools.jump_bench --csv results/jump-bench.csv --timeline

Simulation only (``SimulatedTransport`` on a field config, by default
``config.prototype.json``): there is no Wi-Fi delay, and a player anywhere
inside the modelled beam returns an echo. A player stands at one spot until
tracked and is at another spot from one instant to the next. Each jump is
repeated at ``--trials`` moments, ``--spacing`` seconds apart, because the
result depends on where each box is in its ping cycle when the player leaves.

Variants:

    before       the tracker before the search after a full loss: jitter round
                 the old spot, then the plain sweep
    search       the tracker as it is
    right hint   search, and expect() names the spot the player jumps to
    wrong hint   search, and expect() names the third column

The summary is printed as Markdown tables: median (fastest-slowest) seconds.
``--csv`` writes one row per trial.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics

from whack.swarm import SwarmController
from whack.tracking import load_geometry

COLUMNS = 3
NEAR_M, FAR_M = 0.6, 1.2    # the player's distance from the sensor line in the two rows
SETTLE_S = 6.0              # every box tracks the player well before this
HORIZON_S = 20.0            # a trial that takes longer counts as not found
FIX_RADIUS_M = 0.25         # a fix this near the new spot counts as found
VARIANTS = ("before", "search", "right hint", "wrong hint")
JUMPS = ((1, 3, NEAR_M), (3, 1, NEAR_M), (1, 2, NEAR_M), (2, 3, NEAR_M), (2, 1, NEAR_M), (3, 2, NEAR_M),
         (1, 3, FAR_M), (3, 1, FAR_M))


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Before(SwarmController):
    """The tracker without the search: a full loss leaves each box to its jitter and sweep."""

    def _start_search(self):
        pass


def spot(geometry, column, depth_m):
    """Where the player stands for a column: the middle of that third of the field."""
    return ((column - .5)*geometry.width/COLUMNS, geometry.sensor_y + depth_m)


def label(jump):
    a, b, depth = jump
    return f"column {a} → {b}" + (", far" if depth == FAR_M else "")


def tracked_player(variant, geometry, start, jump_at, tick):
    clock = Clock()
    controller = (Before if variant == "before" else SwarmController)(geometry, simulate=True, clock=clock)
    controller.transport.target = start
    while clock.now < jump_at:
        controller.poll()
        clock.now += tick
    return controller, clock


def hint_for(variant, geometry, jump):
    a, b, depth = jump
    if variant == "right hint":
        return spot(geometry, b, depth)
    if variant == "wrong hint":
        return spot(geometry, 6 - a - b, depth)     # the column that is neither the old nor the new one
    return None


def trial(variant, geometry, jump, jump_at, tick):
    """Seconds from the jump to the first fix at the new spot, and to the first two-box fix there."""
    a, b, depth = jump
    controller, clock = tracked_player(variant, geometry, spot(geometry, a, depth), jump_at, tick)
    target = spot(geometry, b, depth)
    controller.transport.target = target
    controller.expect(hint_for(variant, geometry, jump))
    start, first, two_box = clock.now, None, None
    while clock.now - start < HORIZON_S:
        snap = controller.poll()
        if snap.position is not None and math.dist(snap.position, target) < FIX_RADIUS_M:
            if first is None:
                first = clock.now - start
            if snap.contributors >= 2:
                two_box = clock.now - start
                break
        clock.now += tick
    return first, two_box


def timeline(variant, geometry, jump, tick):
    """What each box does after the jump: one line per change of mode."""
    a, b, depth = jump
    controller, clock = tracked_player(variant, geometry, spot(geometry, a, depth), SETTLE_S, tick)
    target = spot(geometry, b, depth)
    controller.transport.target = target
    start, last, lines = clock.now, None, []
    while clock.now - start < HORIZON_S:
        snap = controller.poll()
        modes = tuple("search" if box.search else box.mode for box in controller.boxes)
        if modes != last:
            boxes = "  ".join(f"{box.node}: {mode:<6} {box.bearing//1000:>3}°" for box, mode in zip(controller.boxes, modes))
            lines.append(f"+{clock.now - start:5.2f} s  {boxes}  {snap.state}")
            last = modes
        if snap.position is not None and math.dist(snap.position, target) < FIX_RADIUS_M:
            break
        clock.now += tick
    return lines


def cell(values):
    found = [v for v in values if v is not None]
    if not found:
        return "not found"
    text = f"{statistics.median(found):.2f} ({min(found):.2f}–{max(found):.2f})"
    return text if len(found) == len(values) else f"{text}, {len(values) - len(found)} not found"


def table(title, results, index):
    lines = [f"{title}\n", "| Jump | " + " | ".join(VARIANTS) + " |", "|---|" + "---|"*len(VARIANTS)]
    for jump in JUMPS:
        cells = [cell([r[index] for r in results[variant, jump]]) for variant in VARIANTS]
        lines.append(f"| {label(jump)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="config.prototype.json")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--spacing", type=float, default=.05, help="seconds between the jump moments")
    parser.add_argument("--tick", type=float, default=.01, help="simulated seconds per poll")
    parser.add_argument("--csv", help="write one row per trial to this file")
    parser.add_argument("--timeline", action="store_true", help="also print what each box does after one jump")
    args = parser.parse_args()
    geometry = load_geometry(args.config)
    moments = [SETTLE_S + n*args.spacing for n in range(args.trials)]
    results = {(variant, jump): [trial(variant, geometry, jump, at, args.tick) for at in moments]
               for variant in VARIANTS for jump in JUMPS}
    print(f"{args.config}, {args.trials} jump moments {args.spacing} s apart, {args.tick*1000:g} ms poll, "
          f"search step {geometry.search_step_deg:g}°. Seconds: median (fastest–slowest).\n")
    print(table("Jump to first fix", results, 0))
    print()
    print(table("Jump to first two-box fix", results, 1))
    if args.timeline:
        for variant in ("before", "search"):
            print(f"\n{label(JUMPS[0])}, {variant}: box: mode, commanded bearing")
            print("\n".join(timeline(variant, geometry, JUMPS[0], args.tick)))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("variant", "from_column", "to_column", "depth_m", "jump_at_s", "first_fix_s", "two_box_fix_s"))
            for (variant, (a, b, depth)), rows in results.items():
                for at, (first, two_box) in zip(moments, rows):
                    writer.writerow((variant, a, b, depth, f"{at:.2f}",
                                     "" if first is None else f"{first:.2f}", "" if two_box is None else f"{two_box:.2f}"))


if __name__ == "__main__":
    main()
