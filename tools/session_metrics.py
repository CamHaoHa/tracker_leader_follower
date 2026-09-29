"""Summarise tracking recordings: dot coverage, rate, jitter, reacquisition.

Run from the project root:

    python3 -m tools.session_metrics results/*.csv

Each CSV comes from ``python3 -m whack ... --record FILE``.
"""
from __future__ import annotations

import csv
import statistics
import sys

SEARCH_STATES = ("find", "confirm", "track", "local_search", "lost")
IDLE_PREFIXES = ("Paused", "Clear the area", "Calibration saved", "Calibration interrupted",
                 "Calibration cancelled", "Waiting for two")


def summarise(path: str) -> dict:
    with open(path, newline="") as file:
        rows = list(csv.DictReader(file))
    active = [r for r in rows if r["state"] in SEARCH_STATES and not r["status"].startswith(IDLE_PREFIXES)]
    fixes = [r for r in active if r["x_m"]]
    rates = [float(r["update_hz"]) for r in fixes if float(r["update_hz"]) > 0]
    windows: dict[int, list[tuple[float, float]]] = {}
    for r in fixes:
        windows.setdefault(int(float(r["elapsed_s"]) // 2), []).append((float(r["x_m"]), float(r["y_m"])))
    spreads = [(statistics.pstdev([p[0] for p in w]), statistics.pstdev([p[1] for p in w]))
               for w in windows.values() if len(w) >= 15]
    losses = sum(1 for a, b in zip(active, active[1:]) if a["state"] == "track" and b["state"] != "track")
    spells, start = [], None
    for r in active:
        if r["state"] in ("find", "confirm", "lost"):
            start = start or float(r["elapsed_s"])
        elif start is not None:
            spells.append(float(r["elapsed_s"]) - start)
            start = None
    spells.sort()
    completed = sum(1 for a, b in zip(rows, rows[1:]) if a["state"] == "calibration" and b["state"] != "calibration"
                    and "interrupted" not in b["status"] and "cancelled" not in b["status"])
    interrupted = sum(1 for a, b in zip(rows, rows[1:]) if a["state"] == "calibration" and "interrupted" in b["status"])
    duration = float(active[-1]["elapsed_s"]) - float(active[0]["elapsed_s"]) if active else 0.0
    return {
        "file": path, "active_s": round(duration), "dot_pct": round(100 * len(fixes) / len(active)) if active else None,
        "hz": round(statistics.mean(rates), 1) if rates else None,
        "jitter_cm": (round(statistics.median(s[0] for s in spreads) * 100, 1),
                      round(statistics.median(s[1] for s in spreads) * 100, 1)) if spreads else None,
        "losses_per_min": round(losses / (duration / 60), 1) if duration > 30 else losses,
        "reacquire_s": (round(spells[len(spells) // 2], 1), round(spells[int(len(spells) * .9)], 1)) if spells else None,
        "calibrations": {"completed": completed, "interrupted": interrupted},
    }


def main(argv: list[str] | None = None) -> int:
    paths = (argv if argv is not None else sys.argv[1:]) or []
    if not paths:
        print(__doc__)
        return 2
    for path in paths:
        print(summarise(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
