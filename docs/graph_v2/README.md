# Development charts (graph_v2)

Seven slide-ready charts that show how the tracker developed, each with its data
table beside it. Every PNG is 2000 × 1125 px (16:9): in PowerPoint use
Insert → Pictures and stretch it to the full slide. The SVG copies scale
without blur and stay editable (Insert → Pictures, then Convert to Shape).

| File | Shows | Data from |
|---|---|---|
| `01-coverage-by-run.png` | Player on screen and two-box share, first lock (22 Sep) to swarm tracker (23 Sep) | `docs/mvp1-bench-log-2026-09-22.md`, `-09-23.md` |
| `02-losses-field.png` | Losses per minute on the 1.5 m field, paired tracker vs swarm runs | `docs/mvp1-bench-log-2026-09-23.md` |
| `03-jump-reacquire-sim.png` | Time to first fix after a skip-column jump: before, search, search with hint (simulation) | `docs/jump-bench-2026-10-02.md` |
| `04-field-v1-vs-v2.png` | Field reacquire times, V1 vs V2, with significance | `results/report/reacquire_table.md` |
| `05-standing-fix-steps.png` | Ghost-echo fix, each change in turn (simulation) | `docs/stand-bench-2026-10-05.md` |
| `06-standing-per-hole.png` | Ghost-echo fix, losses per minute on each of the 15 holes (simulation) | `docs/stand-bench-2026-10-05.md` |
| `07-commit-activity.png` | Commits per day by area, with milestones | `git log` |
| `08-field-latency-distribution.png` | Field reacquire time V1 vs V2: histogram, fitted log-normal, medians with CI, tests | `data/raw/reacquire_losses.csv` |
| `09-field-reliability-curve.png` | Share of losses reacquired within t seconds (empirical CDF), Wilson CIs, loss rate | `data/raw/reacquire_losses.csv` |
| `10-standing-reliability-distribution.png` | Losses per minute over 45 standing trials, before vs after the ghost-echo fix, normal fit, t-test, effect size (simulation) | `data/raw/stand-bench-2026-10-05.csv` |
| `11-jump-latency-distribution.png` | Time to first fix after a jump, four variants: fitted normal, every trial, mean ± CI (simulation) | `data/raw/jump-bench-2026-10-02.csv` |

Charts 03, 05, 06, 10 and 11 come from the simulator; their footnotes say so. Keep the
footnote when you put them on a slide.

## Regenerate

```bash
python3 docs/graph_v2/make_graphs.py
```

The numbers are written into `make_graphs.py` from the logs above (the CSV files
in `results/` are not tracked by Git). After a new bench or field run, change
the constants at the top of the chart's section and run the script again.
Charts 08–11 read the per-event files in `data/raw/` instead and need numpy and scipy.
