"""Reacquisition time after a tracking loss, V1 (before) vs V2 (search after a full loss).

Run from the project root:

    python3 results/report/reacquire_report.py results/jump-v1-3.csv results/jump-v2-1.csv

A loss starts at the first row whose state is "find" with a "Searching" or
"Player lost" status and ends at the next "track" row. A pause, calibration or
"press Search" row cancels an open loss (the operator stopped the tracker, so
that interval is not a reacquisition). Rows come every ~0.1 s, so each time is
accurate to about 0.1 s.

Writes into results/report/: reacquire_histogram.png/.svg, reacquire_table.md,
reacquire_losses.csv (one row per loss).
"""
import csv
import random
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
BLUE, ORANGE = "#2a78d6", "#eb6834"                 # categorical slots 1 and 2, validated together
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
BINS = [(0, .25, "< 0.25"), (.25, .5, "0.25–0.5"), (.5, 1, "0.5–1"), (1, 2, "1–2"), (2, 3, "2–3"), (3, 1e9, "≥ 3")]


def losses(path):
    rows = list(csv.DictReader(open(path)))
    out, lost = [], None
    for r in rows:
        t = float(r["elapsed_s"])
        if r["state"] == "find" and r["status"].startswith(("Searching", "Player lost")) and lost is None:
            lost = t
        elif r["state"] == "track" and lost is not None:
            out.append(t - lost)
            lost = None
        elif r["status"].startswith(("Paused", "Calibration", "Keep area")):
            lost = None
    track_s = sum(r["state"] == "track" for r in rows) * 0.1
    trk = [r for r in rows if r["state"] == "track" and r["x_m"]]
    multi = 100 * sum(int(r["contributors"]) >= 2 for r in trk) / max(1, len(trk))
    return out, track_s, multi


def pct(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


def perm_p(a, b, stat, n=20000):
    """One-sided permutation test: probability of a V1-V2 difference this large by chance."""
    random.seed(1)
    obs, pool, k = stat(a) - stat(b), a + b, 0
    for _ in range(n):
        random.shuffle(pool)
        k += stat(pool[:len(a)]) - stat(pool[len(a):]) >= obs
    return k / n


def main(v1_path, v2_path):
    v1, t1, m1 = losses(v1_path)
    v2, t2, m2 = losses(v2_path)
    over = lambda v, s: 100 * sum(x > s for x in v) / len(v)

    rows = [
        ("Tracking time recorded", f"{t1:.0f} s", f"{t2:.0f} s", ""),
        ("Losses (n)", f"{len(v1)}", f"{len(v2)}", ""),
        ("Losses per tracking minute", f"{len(v1)/t1*60:.1f}", f"{len(v2)/t2*60:.1f}", ""),
        ("Fix from 2+ boxes", f"{m1:.0f} %", f"{m2:.0f} %", ""),
        ("Reacquire time, median", f"{statistics.median(v1):.2f} s", f"{statistics.median(v2):.2f} s",
         f"p = {perm_p(v1, v2, statistics.median):.3f}"),
        ("Reacquire time, mean", f"{statistics.mean(v1):.2f} s", f"{statistics.mean(v2):.2f} s",
         f"p = {perm_p(v1, v2, statistics.mean):.3f}"),
        ("Reacquire time, 90th percentile", f"{pct(v1, .9):.2f} s", f"{pct(v2, .9):.2f} s", ""),
        ("Reacquire time, longest", f"{max(v1):.2f} s", f"{max(v2):.2f} s", ""),
        ("Losses longer than 1 s", f"{over(v1, 1):.0f} %", f"{over(v2, 1):.0f} %", ""),
        ("Losses longer than 2 s", f"{over(v1, 2):.0f} %", f"{over(v2, 2):.0f} %",
         f"p = {perm_p(v1, v2, lambda v: over(v, 2)):.3f}"),
        ("Losses longer than 3 s", f"{over(v1, 3):.0f} %", f"{over(v2, 3):.0f} %", ""),
    ]
    md = ["| Metric | V1 (baseline) | V2 (search after loss) | Significance |", "|---|---|---|---|"]
    md += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    md.append("")
    md.append(f"Data: `{Path(v1_path).name}` (V1) and `{Path(v2_path).name}` (V2), three boxes, same calibration "
              "and field config. p = one-sided permutation test (20 000 shuffles), V1 slower than V2. "
              "Times are resolved to about 0.1 s (recording interval).")
    (OUT / "reacquire_table.md").write_text("\n".join(md) + "\n")
    with open(OUT / "reacquire_losses.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("version", "reacquire_s"))
        w.writerows([("V1", f"{x:.2f}") for x in v1] + [("V2", f"{x:.2f}") for x in v2])

    share = lambda v: [100 * sum(lo <= x < hi for x in v) / len(v) for lo, hi, _ in BINS]
    s1, s2 = share(v1), share(v2)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=200)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
    x = range(len(BINS)); w = 0.38; gap = 0.02
    b1 = ax.bar([i - w/2 - gap/2 for i in x], s1, w, color=BLUE, label=f"V1 baseline (n = {len(v1)})", zorder=3)
    b2 = ax.bar([i + w/2 + gap/2 for i in x], s2, w, color=ORANGE, label=f"V2 search after loss (n = {len(v2)})",
                hatch="////", edgecolor=SURFACE, linewidth=0, zorder=3)
    for bars, vals in ((b1, s1), (b2, s2)):
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width()/2, v + 0.8, f"{v:.0f}%", ha="center", va="bottom",
                        fontsize=8, color=INK2)
    ax.set_xticks(list(x), [lab for _, _, lab in BINS])
    ax.set_xlabel("Time to reacquire the player after a loss (s)", color=INK2)
    ax.set_ylabel("Share of losses (%)", color=INK2)
    ax.set_title("Reacquisition time after a tracking loss, V1 vs V2", loc="left", color=INK, fontsize=12, pad=12)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.set_ylim(0, max(s1 + s2) * 1.15)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, length=0)
    ax.legend(frameon=False, loc="upper right", labelcolor=INK2)
    fig.text(0.01, 0.01, f"Median: V1 {statistics.median(v1):.2f} s, V2 {statistics.median(v2):.2f} s.  "
             f"Losses over 2 s: V1 {over(v1, 2):.0f} %, V2 {over(v2, 2):.0f} %.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"reacquire_histogram.{ext}", facecolor=SURFACE)
    print("\n".join(md))


if __name__ == "__main__":
    main(*sys.argv[1:3])
