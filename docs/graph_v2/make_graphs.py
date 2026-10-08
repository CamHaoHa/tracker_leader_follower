"""Development charts for the report and the slides: each one a 16:9 slide image
with the chart on the left and its data table on the right.

Run from the project root:

    python3 docs/graph_v2/make_graphs.py

Writes docs/graph_v2/NN-name.png (2000 x 1125 px, PowerPoint 16:9) and .svg.
The numbers are copied from the tracked bench logs named under each chart
(results/*.csv is not tracked by Git, so nothing here reads it).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
# Categorical slots 1-4 of the validated default palette, light surface.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, BASE, SURFACE, BAND = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff", "#f3f2ee"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 13, "text.color": INK,
    "axes.edgecolor": BASE, "axes.labelcolor": INK2, "axes.linewidth": 1,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 12, "ytick.labelsize": 12,
    "svg.fonttype": "none",
})


def slide(title, subtitle, source, table_width=0.40):
    """A 13.33 x 7.5 in figure: title, chart axes on the left, table axes on the right."""
    fig = plt.figure(figsize=(13.333, 7.5), dpi=150, facecolor=SURFACE)
    fig.text(0.04, 0.93, title, fontsize=24, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.865, subtitle, fontsize=14, color=INK2, va="top")
    fig.text(0.04, 0.025, source, fontsize=10, color=MUTED, va="bottom")
    split = 0.96 - table_width
    ax = fig.add_axes([0.08, 0.17, split - 0.13, 0.63])
    tab = fig.add_axes([split, 0.12, table_width, 0.70])
    tab.axis("off")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    return fig, ax, tab


def table(tab, header, rows, widths, bold_rows=(), font=11.5, left_cols=1):
    """Plain data table: header rule, zebra bands, numbers right-aligned."""
    t = tab.table(cellText=rows, colLabels=header, colWidths=widths, loc="upper center", cellLoc="right")
    t.auto_set_font_size(False)
    t.set_fontsize(font)
    t.scale(1, 1.9)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor(SURFACE)
        cell.set_linewidth(0)
        cell.PAD = 0.04
        txt = cell.get_text()
        if c < left_cols:
            cell._loc = "left"
            txt.set_ha("left")
        if r == 0:
            cell.set_facecolor(SURFACE)
            txt.set_color(INK2)
            txt.set_fontweight("bold")
            cell.visible_edges = "B"
            cell.set_edgecolor(INK2)
            cell.set_linewidth(1.2)
        else:
            cell.set_facecolor(BAND if r % 2 == 0 else SURFACE)
            txt.set_color(INK)
            if r - 1 in bold_rows:
                txt.set_fontweight("bold")
    return t


def legend(ax, loc="upper left"):
    lg = ax.legend(loc=loc, frameon=False, fontsize=12, handlelength=1.0, handleheight=1.0)
    for t in lg.get_texts():
        t.set_color(INK2)


def bar_labels(ax, bars, fmt="{:.0f}", color=INK2, size=11):
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom", fontsize=size, color=color)


def bars(ax, x, h, w, color, label=None):
    return ax.bar(x, h, w, color=color, label=label, edgecolor=SURFACE, linewidth=2, zorder=3)


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", facecolor=SURFACE)
    fig.savefig(OUT / f"{name}.svg", facecolor=SURFACE)
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


# 1. Coverage by milestone run (docs/mvp1-bench-log-2026-09-22.md, -09-23.md)
RUNS = [  # label, date, change, dot %, two-box %, fresh fixes Hz
    ("Run 10", "22 Sep", "First lock (bench)", 61, None, 4.3),
    ("Run 15", "22 Sep", "Sensors outside boxes", 75, None, 4.9),
    ("Run 18", "22 Sep", "200 s walk incl. edges", 50, None, 4.8),
    ("Paired", "23 Sep", "Paired, 1.5 m field", 14, None, 2.6),
    ("Swarm 1", "23 Sep", "Swarm tracker, first run", 92, 35, 4.4),
    ("Swarm 2", "23 Sep", "Box 1 levelled", 94, 62, 6.3),
    ("Swarm 3", "23 Sep", "Prediction removed", 89, 68, 6.6),
]


def coverage():
    fig, ax, tab = slide(
        "Tracking coverage across development",
        "Share of active time with the player on screen, and share confirmed by two boxes",
        "Source: docs/mvp1-bench-log-2026-09-22.md and -09-23.md, metrics by run. "
        "Two-box share is not defined for the two-sensor paired tracker (22–23 Sep, first four runs).")
    x = range(len(RUNS))
    b1 = bars(ax, [i - 0.2 for i in x], [r[3] for r in RUNS], 0.38, BLUE, "Player on screen")
    two = [(i + 0.2, r[4]) for i, r in zip(x, RUNS) if r[4] is not None]
    b2 = bars(ax, [p[0] for p in two], [p[1] for p in two], 0.38, ORANGE, "Two-box fix")
    bar_labels(ax, b1)
    bar_labels(ax, b2)
    ax.axvline(3.5, color=BASE, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.text(1.5, 108, "Paired tracker", ha="center", fontsize=12, color=INK2)
    ax.text(5.0, 108, "Swarm tracker (V1)", ha="center", fontsize=12, color=INK2)
    ax.set_xticks(list(x), [f"{r[0]}\n{r[1]}" for r in RUNS])
    ax.set_ylim(0, 115)
    ax.set_yticks(range(0, 101, 20), [f"{v} %" for v in range(0, 101, 20)])
    legend(ax, "upper left")
    ax.legend_.set_bbox_to_anchor((0, 0.93))
    table(tab, ["Run", "Date", "Change", "Screen", "2-box", "Fix/s"],
          [[r[0], r[1], r[2], f"{r[3]} %", "—" if r[4] is None else f"{r[4]} %", f"{r[5]}"] for r in RUNS],
          [0.15, 0.13, 0.36, 0.13, 0.12, 0.11], bold_rows=(6,), font=11, left_cols=3)
    save(fig, "01-coverage-by-run")


# 2. Losses and reacquisition, field runs of 23 Sep (docs/mvp1-bench-log-2026-09-23.md)
FIELD = [  # label, situation, losses/min, reacquire median s, 90th s, jitter x/y cm
    ("Paired", "Paired tracker", 17.6, 4.4, 12.5, "0.3 / 0.5"),
    ("Swarm 1", "First swarm run", 5.7, 0.4, 2.0, "6.2 / 6.2"),
    ("Swarm 2", "Box 1 levelled", 2.6, 1.3, 1.9, "3.8 / 5.6"),
    ("Swarm 3", "No prediction", 1.3, 1.4, 15.6, "2.1 / 2.4"),
]


def losses():
    fig, ax, tab = slide(
        "Tracking losses fell 93 % on the 1.5 m field",
        "Losses per minute of active tracking, 23 September 2026, university field",
        "Source: docs/mvp1-bench-log-2026-09-23.md, metrics by segment. "
        "Reacquire = time from a loss to the next lock, median / 90th percentile.")
    x = range(len(FIELD))
    b = bars(ax, list(x), [r[2] for r in FIELD], 0.55, BLUE)
    bar_labels(ax, b, "{:.1f}", INK, 13)
    ax.set_xticks(list(x), [r[0] for r in FIELD])
    ax.set_ylabel("Losses per minute")
    ax.set_ylim(0, 20)
    table(tab, ["Run", "Situation", "Loss/min", "Reacquire", "Jitter cm"],
          [[r[0], r[1], f"{r[2]}", f"{r[3]} / {r[4]} s", r[5]] for r in FIELD],
          [0.15, 0.30, 0.14, 0.23, 0.18], bold_rows=(3,), left_cols=2, font=11)
    save(fig, "02-losses-field")


# 3. Jump benchmark, skip-a-column jumps (docs/jump-bench-2026-10-02.md)
JUMPS = ["1 → 3", "3 → 1", "1 → 3 far", "3 → 1 far"]  # far = player 1.2 m from the sensor line
JUMP_FIX = {  # first fix, median s
    "Before": [3.69, 6.71, 3.35, 9.12],
    "Search": [1.49, 1.35, 1.45, 1.34],
    "Search, hint ok": [0.84, 0.88, 0.84, 0.90],
    "Search, hint off": [1.42, 1.43, 1.72, 1.43],
}


def jumps():
    fig, ax, tab = slide(
        "Search after a full loss: 2.3–6.8× faster reacquire",
        "Simulated time to the first fix after the player skips a column, median of 20 trials",
        "Source: docs/jump-bench-2026-10-02.md (python3 -m tools.jump_bench). Simulation only, not measured on hardware. "
        "Hint = the game names the mole the player will jump to.")
    colors = [BLUE, ORANGE, AQUA, YELLOW]
    w = 0.2
    for k, (name, vals) in enumerate(JUMP_FIX.items()):
        b = bars(ax, [i + (k - 1.5) * w for i in range(len(JUMPS))], vals, w * 0.95, colors[k], name)
        if name == "Before":
            bar_labels(ax, b, "{:.1f}", INK2, 11)
    ax.set_xticks(range(len(JUMPS)), [j.replace(" far", "\nfar row") for j in JUMPS])
    ax.set_xlabel("Column jump")
    ax.set_ylabel("Seconds to first fix")
    ax.set_ylim(0, 10)
    legend(ax, "upper left")
    rows = [[j] + [f"{JUMP_FIX[v][i]:.2f}" for v in JUMP_FIX] for i, j in enumerate(JUMPS)]
    rows.append(["All skips, 95th pct", "9.22", "1.89", "0.94", "1.81"])
    table(tab, ["Jump", "Before", "Search", "Hint ok", "Hint off"], rows,
          [0.32, 0.17, 0.17, 0.17, 0.17], bold_rows=(4,))
    save(fig, "03-jump-reacquire-sim")


# 4. Field V1 vs V2 reacquisition (results/report/reacquire_table.md, reacquire_losses.csv)
BINS = ["< 0.25", "0.25–0.5", "0.5–1", "1–2", "2–3", "≥ 3"]
V1_COUNTS, V2_COUNTS = [25, 8, 23, 7, 4, 3], [19, 7, 5, 5, 1, 0]


def field_v1_v2():
    fig, ax, tab = slide(
        "Field: V2 reacquires about twice as fast",
        "Three boxes, same calibration: share of tracking losses by time to reacquire",
        "Source: results/report/reacquire_table.md (jump-v1-3.csv vs jump-v2-1.csv). "
        "p = one-sided permutation test, 20 000 shuffles. Times resolved to ~0.1 s.")
    n1, n2 = sum(V1_COUNTS), sum(V2_COUNTS)
    x = range(len(BINS))
    p1 = [100 * c / n1 for c in V1_COUNTS]
    p2 = [100 * c / n2 for c in V2_COUNTS]
    b1 = bars(ax, [i - 0.2 for i in x], p1, 0.38, BLUE, f"V1 baseline (n = {n1})")
    b2 = bars(ax, [i + 0.2 for i in x], p2, 0.38, ORANGE, f"V2 search after loss (n = {n2})")
    bar_labels(ax, b1, "{:.0f}", INK2, 10)
    bar_labels(ax, b2, "{:.0f}", INK2, 10)
    ax.set_xticks(list(x), [f"{b} s" for b in BINS])
    ax.set_xlabel("Time to reacquire")
    ax.set_ylim(0, 60)
    ax.set_yticks(range(0, 61, 10), [f"{v} %" for v in range(0, 61, 10)])
    legend(ax, "upper right")
    table(tab, ["Metric", "V1", "V2", "p"], [
        ["Losses (n)", "70", "37", ""],
        ["Tracking time", "305 s", "112 s", ""],
        ["Losses per minute", "13.8", "19.9", ""],
        ["Fix from 2+ boxes", "70 %", "67 %", ""],
        ["Reacquire, median", "0.51 s", "0.21 s", "0.016"],
        ["Reacquire, mean", "0.79 s", "0.47 s", "0.032"],
        ["Reacquire, 90th pct", "2.25 s", "1.12 s", ""],
        ["Reacquire, longest", "6.13 s", "2.45 s", ""],
        ["Losses > 2 s", "10 %", "3 %", "0.163"],
        ["Losses > 3 s", "4 %", "0 %", ""],
    ], [0.40, 0.20, 0.20, 0.20], bold_rows=(4, 5))
    save(fig, "04-field-v1-vs-v2")


# 5. Standing player: each change in turn (docs/stand-bench-2026-10-05.md)
STEPS = [  # short label, change, losses/min, jumps/min, on the hole %
    ("Before", "V2 as of 3191700", 12.4, 3.7, 87),
    ("+ Band", "Static echo as a 10° band", 10.7, 0.3, 95),
    ("+ Agreement", "Beam check and outvote", 10.4, 0.0, 95),
    ("+ Keep echo", "Keep last echo, 16°", 1.2, 0.0, 99),
]


def stand_steps():
    fig, ax, tab = slide(
        "Ghost-echo fix: losses of a standing player −90 %",
        "Simulated losses per minute while the player stands on a hole, after each change in turn",
        "Source: docs/stand-bench-2026-10-05.md (python3 -m tools.stand_bench), 15 holes × 3 trials × 30 s. "
        "Simulation; 15 % missed pings, 30 % edge echo assumed.")
    x = range(len(STEPS))
    b = bars(ax, list(x), [s[2] for s in STEPS], 0.55, BLUE)
    bar_labels(ax, b, "{:.1f}", INK, 13)
    ax.set_xticks(list(x), [s[0] for s in STEPS])
    ax.set_ylabel("Losses per minute")
    ax.set_ylim(0, 15)
    table(tab, ["Change", "Loss/min", "Jump/min", "On hole"],
          [[s[1], f"{s[2]}", f"{s[3]}", f"{s[4]} %"] for s in STEPS],
          [0.46, 0.18, 0.18, 0.18], bold_rows=(3,), font=11)
    save(fig, "05-standing-fix-steps")


# 6. Standing player, per hole before and after (docs/stand-bench-2026-10-05.md)
HOLES = [  # x, y, losses/min before, after, on the hole % before, after
    (0.25, 1.10, 20.7, 2.7, 73, 100), (0.50, 1.10, 16.7, 1.3, 86, 98), (0.75, 1.10, 18.0, 4.7, 91, 98),
    (1.00, 1.10, 12.0, 2.7, 87, 99), (1.25, 1.10, 17.3, 2.7, 79, 98), (0.25, 1.42, 18.0, 0.7, 78, 99),
    (0.50, 1.42, 14.7, 0.7, 81, 100), (0.75, 1.42, 6.7, 0.7, 98, 100), (1.00, 1.42, 7.3, 0.0, 91, 98),
    (1.25, 1.42, 16.0, 0.0, 80, 100), (0.25, 1.74, 13.3, 0.0, 83, 100), (0.50, 1.74, 8.0, 0.7, 94, 100),
    (0.75, 1.74, 5.3, 0.7, 97, 100), (1.00, 1.74, 4.7, 0.0, 98, 100), (1.25, 1.74, 6.7, 0.0, 96, 100),
]


def stand_holes():
    fig, ax, tab = slide(
        "Every hole improves after the ghost-echo fix",
        "Simulated losses per minute for a player standing 30 s on each hole, before and after",
        "Source: docs/stand-bench-2026-10-05.md, per-hole table. x from the player's left, y from the sensor line (m). "
        "Simulation only.", table_width=0.36)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=1)
    ys = list(range(len(HOLES)))[::-1]
    for y, h in zip(ys, HOLES):
        ax.plot([h[3], h[2]], [y, y], color=BASE, linewidth=2, zorder=2)
    ax.scatter([h[2] for h in HOLES], ys, s=80, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3, label="Before")
    ax.scatter([h[3] for h in HOLES], ys, s=80, color=ORANGE, edgecolor=SURFACE, linewidth=2, zorder=3, label="After")
    ax.set_yticks(ys, [f"({h[0]:.2f}, {h[1]:.2f})" for h in HOLES], fontsize=10.5)
    ax.set_xlabel("Losses per minute")
    ax.set_xlim(-0.5, 23)
    legend(ax, "lower right")
    table(tab, ["Hole", "Before", "After", "On hole"],
          [[f"({h[0]:.2f}, {h[1]:.2f})", f"{h[2]}", f"{h[3]}", f"{h[4]} → {h[5]} %"] for h in HOLES] +
          [["All holes", "12.4", "1.2", "87 → 99 %"]],
          [0.31, 0.17, 0.17, 0.35], bold_rows=(15,), font=10.5)
    tab.tables[0].scale(1, 0.62)
    save(fig, "06-standing-per-hole")


# 7. Development activity: commits per day by area (git log, merges left out)
DAYS = ["12 Sep", "22 Sep", "23 Sep", "24 Sep", "29 Sep", "30 Sep", "1 Oct", "2 Oct", "5 Oct"]
AREAS = {  # tracker = feat/swarm/tracking/tracker/plumbing; firmware = firmware/pins; tools = tools/tests/config/chore
    "Tracker": [2, 2, 5, 0, 4, 0, 0, 1, 1],
    "Firmware": [0, 0, 0, 0, 6, 1, 2, 0, 0],
    "Tools, tests, config": [1, 0, 0, 0, 3, 0, 3, 1, 0],
    "Docs, results": [1, 0, 1, 1, 2, 0, 2, 1, 1],
}
MILESTONES = {1: "First lock", 2: "Swarm tracker", 4: "Third box", 7: "Search after loss", 8: "Ghost-echo fix"}


def activity():
    fig, ax, tab = slide(
        "Development activity, September–October 2026",
        "Commits per working day by area of the code, with the milestone each day reached",
        "Source: git log of this repository (41 commits, 2 merge commits left out).", table_width=0.42)
    colors = [BLUE, ORANGE, AQUA, YELLOW]
    bottom = [0] * len(DAYS)
    for (name, vals), c in zip(AREAS.items(), colors):
        ax.bar(range(len(DAYS)), vals, 0.6, bottom=bottom, color=c, label=name, edgecolor=SURFACE, linewidth=2, zorder=3)
        bottom = [b + v for b, v in zip(bottom, vals)]
    for i, total in enumerate(bottom):
        ax.text(i, total + 0.3, str(total), ha="center", fontsize=11, color=INK2)
    ax.set_xticks(range(len(DAYS)), DAYS, fontsize=11)
    ax.set_ylabel("Commits")
    ax.set_ylim(0, 18)
    legend(ax, "upper left")
    rows = [[d, str(AREAS["Tracker"][i]), str(AREAS["Firmware"][i]),
             str(AREAS["Tools, tests, config"][i]), str(AREAS["Docs, results"][i]), MILESTONES.get(i, "")]
            for i, d in enumerate(DAYS)]
    rows.append(["Total"] + [str(sum(v)) for v in AREAS.values()] + [""])
    table(tab, ["Day", "Tracker", "Firmware", "Tools", "Docs", "Milestone"], rows,
          [0.14, 0.13, 0.15, 0.11, 0.11, 0.36], bold_rows=(9,), font=10.5)
    for (r, c), cell in tab.tables[0].get_celld().items():
        if c == 5:
            cell._loc = "left"
            cell.get_text().set_ha("left")
    save(fig, "07-commit-activity")


# 8-11. Distributions and tests, from the per-event raw data in docs/graph_v2/data/raw/
# (copied from results/; add with git add -f). Field = hardware, three boxes; stand and jump = simulator.
RAW = OUT / "data" / "raw"


def _rows(name):
    import csv
    with open(RAW / name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _boot_median_ci(v, n=20000):
    import numpy as np
    rng = np.random.default_rng(1)
    m = np.median(rng.choice(v, (n, len(v))), axis=1)
    return np.percentile(m, 2.5), np.percentile(m, 97.5)


def _wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return 100 * (c - h), 100 * (c + h)


def _field():
    import numpy as np
    r = _rows("reacquire_losses.csv")
    return {v: np.array([float(x["reacquire_s"]) for x in r if x["version"] == v]) for v in ("V1", "V2")}


def _write_csv(name, header, rows):
    import csv
    with open(OUT / "data" / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def latency_distribution():
    """08: field reacquire times, histogram on a log axis with fitted log-normal curves."""
    import numpy as np
    from scipy import stats
    fig, ax, tab = slide(
        "Field latency: V2 reacquires in 0.21 s (median), V1 0.51 s",
        "Time from a tracking loss to the next lock, hardware, three boxes. Bars = share of losses; curves = fitted log-normal",
        "Source: data/raw/reacquire_losses.csv (jump-v1-3.csv vs jump-v2-1.csv). Times resolved to ~0.1 s, so 0.1 s is the floor.\n"
        "Log-normal = normal distribution of log(time); Shapiro-Wilk still rejects it (p < 0.01), so the rank and permutation tests carry the claim.",
        table_width=0.38)
    d = _field()
    edges = 0.075 * 2.0 ** np.arange(8)          # 0.075 0.15 0.3 0.6 1.2 2.4 4.8 9.6, equal width in log2
    xs = np.geomspace(0.06, 12, 400)
    rows, csv_rows = [], []
    for k, (name, c, lab) in enumerate((("V1", BLUE, "V1 baseline"), ("V2", ORANGE, "V2 search after loss"))):
        v = d[name]
        h, _ = np.histogram(v, edges)
        share = 100 * h / len(v)
        left = edges[:-1] * 2 ** (0.05 + 0.45 * k)
        ax.bar(left, share, width=edges[:-1] * (2 ** (0.45 + 0.45 * k) - 2 ** (0.05 + 0.45 * k)), align="edge",
               color=c, alpha=0.85, label=f"{lab} (n = {len(v)})", edgecolor=SURFACE, linewidth=2, zorder=3)
        mu, sd = np.log2(v).mean(), np.log2(v).std(ddof=1)
        ax.plot(xs, 100 * stats.norm.pdf(np.log2(xs), mu, sd), color=c, linewidth=2.2, zorder=4)
        med = np.median(v)
        ax.axvline(med, color=c, linewidth=1.5, linestyle=(0, (4, 3)), zorder=2)
        ax.text(med * (1.06 if k == 0 else 0.94), 40, f"median {med:.2f} s", color=INK2, fontsize=11,
                ha="left" if k == 0 else "right")
        lo, hi = _boot_median_ci(v)
        rows.append([name, f"{len(v)}", f"{med:.2f} ({lo:.2f}–{hi:.2f})", f"{v.mean():.2f} ± {v.std(ddof=1):.2f}",
                     f"{2 ** mu:.2f}", f"{np.sort(v)[int(len(v) * 0.9)]:.2f}", f"{v.max():.2f}"])
        csv_rows += [[name, f"{a:.3f}", f"{b:.3f}", int(n_), f"{s_:.1f}"] for a, b, n_, s_ in zip(edges[:-1], edges[1:], h, share)]
    ax.set_xscale("log")
    ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 4, 8], ["0.1", "0.25", "0.5", "1", "2", "4", "8"])
    ax.minorticks_off()
    ax.set_xlim(0.06, 12)
    ax.set_xlabel("Seconds to reacquire (log scale)")
    ax.set_ylim(0, 60)
    ax.set_yticks(range(0, 51, 10), [f"{t} %" for t in range(0, 51, 10)])
    legend(ax, "upper right")
    v1, v2 = d["V1"], d["V2"]
    mw = stats.mannwhitneyu(v1, v2, alternative="greater").pvalue
    lt = stats.ttest_ind(np.log(v1), np.log(v2), equal_var=False, alternative="greater").pvalue
    t = table(tab, ["", "n", "Median (95 % CI)", "Mean ± SD", "Geo", "P90", "Max"], rows,
              [0.07, 0.07, 0.31, 0.21, 0.11, 0.11, 0.12], font=10.5)
    tab.text(0.0, 0.62, "Tests, one-sided (V1 slower than V2)", fontsize=12, fontweight="bold", color=INK2)
    tests = [("Permutation, median", "p = 0.016"), ("Welch t on log(time)", f"p = {lt:.3f}"),
             ("Permutation, mean", "p = 0.032"), ("Mann-Whitney U (ranks)", f"p = {mw:.3f}"),
             ("Median ratio V2 / V1", f"{np.median(v2) / np.median(v1):.2f}×")]
    for i, (a, b) in enumerate(tests):
        tab.text(0.0, 0.55 - i * 0.065, a, fontsize=11.5, color=INK)
        tab.text(1.0, 0.55 - i * 0.065, b, fontsize=11.5, color=INK, ha="right")
    tab.text(0.0, 0.18, "Read: the V2 curve sits left of V1 and is narrower.\n"
             "Typical loss is about 2.4× shorter; the rank test is\n"
             "borderline (p = 0.07), so call it 'faster, n = 37'.", fontsize=11, color=INK2, va="top")
    _write_csv("08-latency-distribution.csv", ["version", "bin_from_s", "bin_to_s", "losses", "share_pct"], csv_rows)
    save(fig, "08-field-latency-distribution")


def reliability_curve():
    """09: empirical CDF of reacquire time = probability the player is back within t seconds."""
    import numpy as np
    from scipy import stats
    fig, ax, tab = slide(
        "Field reliability: 84 % of V2 losses recover within 1 s",
        "Share of losses already reacquired after t seconds (empirical CDF), with the fitted log-normal as a thin line",
        "Source: data/raw/reacquire_losses.csv. Brackets = 95 % Wilson interval. Loss rate: V1 70 losses in 305 s tracked, "
        "V2 37 in 112 s;\nPoisson rate test p = 0.10 (V2 not significantly worse, but not better either).",
        table_width=0.38)
    d = _field()
    xs = np.linspace(0, 6.5, 400)
    marks = (0.5, 1.0, 2.0, 3.0)
    tbl = {m: [] for m in marks}
    csv_rows = []
    for name, c, lab in (("V1", BLUE, "V1 baseline"), ("V2", ORANGE, "V2 search after loss")):
        v = np.sort(d[name])
        y = 100 * np.arange(1, len(v) + 1) / len(v)
        ax.step(np.r_[0, v], np.r_[0, y], where="post", color=c, linewidth=2.5, label=f"{lab} (n = {len(v)})", zorder=4)
        mu, sd = np.log(v).mean(), np.log(v).std(ddof=1)
        ax.plot(xs[1:], 100 * stats.norm.cdf(np.log(xs[1:]), mu, sd), color=c, linewidth=1, linestyle=(0, (2, 2)), zorder=3)
        for m in marks:
            k = int((v <= m).sum())
            lo, hi = _wilson(k, len(v))
            tbl[m].append(f"{100 * k / len(v):.0f} % ({lo:.0f}–{hi:.0f})")
            csv_rows.append([name, m, k, len(v), f"{100 * k / len(v):.1f}", f"{lo:.1f}", f"{hi:.1f}"])
    for m in (1.0, 2.0):
        ax.axvline(m, color=BASE, linewidth=1, zorder=1)
    ax.set_xlim(0, 6.5)
    ax.set_ylim(0, 105)
    ax.set_yticks(range(0, 101, 20), [f"{t} %" for t in range(0, 101, 20)])
    ax.set_xlabel("Seconds since the loss")
    ax.set_ylabel("Losses reacquired")
    legend(ax, "lower right")
    rows = [[f"Back within {m:g} s"] + tbl[m] for m in marks]
    rows += [["Losses / tracked min", "13.8 (10.7–17.4)", "19.9 (14.0–27.3)"],
             ["Fix from 2+ boxes", "70 %", "67 %"]]
    table(tab, ["", "V1", "V2"], rows, [0.36, 0.32, 0.32], bold_rows=(1,), font=11)
    tab.text(0.0, 0.30, "Read: at every time mark V2 has recovered a larger\n"
             "share of losses, and no V2 loss lasted past 2.5 s\n"
             "(V1: 4 % past 3 s, longest 6.1 s). V2 lost the player\n"
             "a little more often per minute: not significant, and\n"
             "it was fixed later for standing players (chart 10).",
             fontsize=11, color=INK2, va="top")
    _write_csv("09-reliability-curve.csv", ["version", "within_s", "reacquired", "losses", "pct", "ci_low", "ci_high"], csv_rows)
    save(fig, "09-field-reliability-curve")


def stand_distribution():
    """10: losses per minute over 45 simulated standing trials, before vs after the ghost-echo fix."""
    import numpy as np
    from scipy import stats
    fig, ax, tab = slide(
        "Standing reliability: 12.4 → 1.2 losses per minute",
        "Simulated losses per minute, 45 trials of 30 s each (15 holes × 3 seeds). Bars = trials; curves = fitted normal; dot = mean ± 95 % CI",
        "Source: data/raw/stand-bench-2026-10-05.csv (python3 -m tools.stand_bench). Simulation, not hardware.\n"
        "A 30 s trial counts losses in steps of 2 per minute; 'after' piles up at 0, so its normal curve is only a guide.",
        table_width=0.38)
    r = _rows("stand-bench-2026-10-05.csv")
    get = lambda var, k: np.array([float(x[k]) for x in r if x["variant"] == var])
    edges = np.arange(-1, 33, 2)                 # one bar per possible value 0, 2, 4, ...
    xs = np.linspace(-4, 34, 400)
    rows = []
    for k, (var, c, lab) in enumerate((("before", BLUE, "Before (V2 @ 3191700)"), ("after", ORANGE, "After ghost-echo fix (aee8ef0)"))):
        v = get(var, "losses_per_min")
        h, _ = np.histogram(v, edges)
        ax.bar(edges[:-1] + 0.15 + 0.85 * k, h, 0.85, align="edge", color=c, label=f"{lab}",
               edgecolor=SURFACE, linewidth=1.5, zorder=3)
        m, sd = v.mean(), v.std(ddof=1)
        ax.plot(xs, len(v) * 2 * stats.norm.pdf(xs, m, max(sd, 0.5)), color=c, linewidth=2.2, zorder=4)
        ci = stats.t.ppf(0.975, len(v) - 1) * sd / len(v) ** 0.5
        ax.errorbar([m], [32 - 2.5 * k], xerr=[[ci], [ci]], fmt="o", color=c, markersize=8,
                    markeredgecolor=SURFACE, capsize=5, linewidth=2, zorder=5)
        ax.text(m + ci + 0.8, 32 - 2.5 * k, f"mean {m:.1f} ± {ci:.1f}", va="center", fontsize=11, color=INK2)
        rows.append(v)
    b, a = rows
    t = stats.ttest_ind(b, a, equal_var=False)
    mw = stats.mannwhitneyu(b, a)
    dpool = (b.mean() - a.mean()) / (((b.var(ddof=1) + a.var(ddof=1)) / 2) ** 0.5)
    ax.set_xlim(-2, 34)
    ax.set_ylim(0, 36)
    ax.set_xlabel("Losses per minute in one trial")
    ax.set_ylabel("Trials")
    legend(ax, "upper right")
    ax.legend_.set_bbox_to_anchor((1, 0.86))
    def row(lab, k, fmt, scale=1):
        bb, aa = get("before", k) * scale, get("after", k) * scale
        return [lab, fmt.format(bb.mean()) + " ± " + fmt.format(bb.std(ddof=1)),
                fmt.format(aa.mean()) + " ± " + fmt.format(aa.std(ddof=1)),
                f"{stats.ttest_ind(bb, aa, equal_var=False).pvalue:.0e}"]
    trows = [row("Losses / min", "losses_per_min", "{:.1f}"), row("Jumps / min", "jumps_per_min", "{:.1f}"),
             row("On the hole %", "on_hole", "{:.0f}", 100), row("Two-box fix %", "two_box", "{:.0f}", 100),
             row("Cursor shown %", "shown", "{:.1f}", 100)]
    table(tab, ["Mean ± SD", "Before", "After", "Welch p"], trows, [0.34, 0.24, 0.22, 0.20], bold_rows=(0,), font=11)
    tab.text(0.0, 0.40, "Effect, losses per minute", fontsize=12, fontweight="bold", color=INK2)
    for i, (lab_, val) in enumerate((("Difference of means", f"−{b.mean() - a.mean():.1f} / min (−{100 * (1 - a.mean() / b.mean()):.0f} %)"),
                                     ("Welch t-test", f"t = {t.statistic:.1f}, p = {t.pvalue:.0e}"),
                                     ("Mann-Whitney U", f"p = {mw.pvalue:.0e}"),
                                     ("Cohen's d", f"{dpool:.1f} (very large)"),
                                     ("Trials with 0 losses", f"{(b == 0).sum()} / 45 → {(a == 0).sum()} / 45"))):
        tab.text(0.0, 0.33 - i * 0.065, lab_, fontsize=11.5, color=INK)
        tab.text(1.0, 0.33 - i * 0.065, val, fontsize=11.5, color=INK, ha="right")
    _write_csv("10-stand-distribution.csv", ["metric", "before_mean_sd", "after_mean_sd", "welch_p"], trows)
    save(fig, "10-standing-reliability-distribution")


def jump_distribution():
    """11: time to first fix after a skip-column jump, 160 simulated jumps per variant."""
    import numpy as np
    from scipy import stats
    fig, ax, tab = slide(
        "Jump latency: spread shrinks from ±2.9 s to ±0.2 s",
        "Simulated seconds to the first fix after the player skips a column. Curve = fitted normal; dots = each jump; bar = mean ± 95 % CI",
        "Source: data/raw/jump-bench-2026-10-02.csv (python3 -m tools.jump_bench), 160 jumps per variant. Simulation only.\n"
        "'Before' falls in separate clusters (one per jump direction and row), so its normal curve is a poor fit; P95 is read from the data.",
        table_width=0.36)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=1)
    r = _rows("jump-bench-2026-10-02.csv")
    variants = (("before", "Before", BLUE), ("search", "Search after loss", ORANGE),
                ("wrong hint", "Search, wrong hint", YELLOW), ("right hint", "Search, right hint", AQUA))
    xs = np.linspace(0, 10.5, 600)
    rng = np.random.default_rng(3)
    rows = []
    for i, (key, lab, c) in enumerate(variants):
        v = np.array([float(x["first_fix_s"]) for x in r if x["variant"] == key])
        base = (len(variants) - 1 - i) * 1.0
        m, sd = v.mean(), v.std(ddof=1)
        pdf = stats.norm.pdf(xs, m, sd)
        ax.fill_between(xs, base + 0.36, base + 0.36 + 0.55 * pdf / pdf.max(), color=c, alpha=0.30, linewidth=0, zorder=2)
        ax.plot(xs, base + 0.36 + 0.55 * pdf / pdf.max(), color=c, linewidth=2, zorder=3)
        ax.scatter(v, base + 0.04 + 0.18 * rng.random(len(v)), s=12, color=c, alpha=0.6, linewidth=0, zorder=3)
        ci = stats.t.ppf(0.975, len(v) - 1) * sd / len(v) ** 0.5
        ax.errorbar([m], [base + 0.29], xerr=[[ci], [ci]], fmt="|", color=INK, markersize=14, capsize=0, linewidth=2, zorder=5)
        ax.text(10.4, base + 0.55, lab, ha="right", fontsize=12, color=INK2)
        rows.append([lab, f"{m:.2f} ± {sd:.2f}", f"{np.median(v):.2f}", f"{np.percentile(v, 95):.2f}", f"{v.max():.2f}"])
    before = np.array([float(x["first_fix_s"]) for x in r if x["variant"] == "before"])
    srch = np.array([float(x["first_fix_s"]) for x in r if x["variant"] == "search"])
    ax.set_yticks([])
    ax.set_ylim(-0.05, 4.0)
    ax.set_xlim(0, 10.5)
    ax.set_xlabel("Seconds to the first fix after the jump")
    table(tab, ["Variant", "Mean ± SD", "Median", "P95", "Max"], rows, [0.36, 0.22, 0.14, 0.14, 0.14], bold_rows=(1, 3), font=11)
    tab.text(0.0, 0.50, "Before vs search after loss", fontsize=12, fontweight="bold", color=INK2)
    lv = stats.levene(before, srch)
    for i, (a, b_) in enumerate((("Welch t-test (means)", f"p = {stats.ttest_ind(before, srch, equal_var=False).pvalue:.0e}"),
                                 ("Levene test (spread)", f"p = {lv.pvalue:.0e}"),
                                 ("SD ratio", f"{before.std(ddof=1) / srch.std(ddof=1):.1f}× narrower"),
                                 ("P95", f"{np.percentile(before, 95):.1f} s → {np.percentile(srch, 95):.1f} s"))):
        tab.text(0.0, 0.43 - i * 0.065, a, fontsize=11.5, color=INK)
        tab.text(1.0, 0.43 - i * 0.065, b_, fontsize=11.5, color=INK, ha="right")
    tab.text(0.0, 0.12, "Read: search after loss makes the latency predictable;\n"
             "a correct hint from the game cuts it again, a wrong\n"
             "hint costs nothing compared with no hint.", fontsize=11, color=INK2, va="top")
    _write_csv("11-jump-distribution.csv", ["variant", "mean_sd_s", "median_s", "p95_s", "max_s"], rows)
    save(fig, "11-jump-latency-distribution")


if __name__ == "__main__":
    coverage()
    losses()
    jumps()
    field_v1_v2()
    stand_steps()
    stand_holes()
    activity()
    latency_distribution()
    reliability_curve()
    stand_distribution()
    jump_distribution()
