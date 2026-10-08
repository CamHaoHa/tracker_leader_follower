# Chart data (graph_v2)

The numbers behind each slide chart in `docs/graph_v2/`, as CSV (UTF-8, opens in
Excel) plus one workbook, `tracker-charts.xlsx`, with a sheet and a native Excel
chart for each slide. Every CSV row names its source.

| File | Chart | Origin |
|---|---|---|
| `01-coverage-by-run.csv` | 01 coverage | bench logs 22–23 Sep (raw recordings lost) |
| `01b-bench-runs-2026-09-22.csv` | — | full 22 Sep run table, incl. runs not charted |
| `02-losses-field.csv` | 02 losses | bench log 23 Sep (raw recordings lost) |
| `02b-field-segments-2026-09-23.csv` | — | all 23 Sep segments, incl. the weaker windows |
| `03-jump-reacquire-sim.csv` | 03 jump (simulation) | `raw/jump-bench-2026-10-02.csv` |
| `04-field-v1-vs-v2-histogram.csv` | 04 V1 vs V2 | `raw/reacquire_losses.csv` (from `raw/jump-v1-3.csv`, `raw/jump-v2-1.csv`) |
| `04b-field-v1-vs-v2-summary.csv` | 04 table | `results/report/reacquire_table.md` |
| `05-standing-fix-steps.csv` | 05 steps (simulation) | `docs/stand-bench-2026-10-05.md` |
| `06-standing-per-hole.csv` | 06 per hole (simulation) | `raw/stand-bench-2026-10-05.csv` |
| `07-commit-activity.csv` | 07 commits | `raw/commits.csv` (git log, merges left out) |
| `08-latency-distribution.csv` | 08 field latency | `raw/reacquire_losses.csv` |
| `09-reliability-curve.csv` | 09 field reliability | `raw/reacquire_losses.csv` |
| `10-stand-distribution.csv` | 10 standing (simulation) | `raw/stand-bench-2026-10-05.csv` |
| `11-jump-distribution.csv` | 11 jump latency (simulation) | `raw/jump-bench-2026-10-02.csv` |

The 22–23 Sep recordings (`bench-live*`, `uni-field15-run2`, `swarm-run1..3`)
were never committed and are not on this machine, so charts 01 and 02 rest on
the bench log tables only.

`*.csv` is in `.gitignore`; add these with `git add -f docs/graph_v2/data`.
