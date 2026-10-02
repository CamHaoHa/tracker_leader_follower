# Jump benchmark, 2 October 2026: reacquisition after the player changes column

Simulation results for the change "search after a full loss, mole hint"
(`docs/CHANGELOG.md`, 2026-10-02). **Nothing here was measured on hardware.**

## What was measured

The time from the instant the player leaves one spot and stands at another until
the tracker reports a position within 0.25 m of the new spot ("first fix"), and
until that position is supported by two boxes ("two-box fix").

| Item | Value |
|---|---|
| Tool | `python3 -m tools.jump_bench --csv results/jump-bench-2026-10-02.csv --timeline` |
| Field | `config.prototype.json`: boxes at x 0, 0.75, 1.50 m on the line y 0.50 m, field 1.5 m wide |
| Player spots | middle of each third of the field: x 0.25, 0.75, 1.25 m (columns 1, 2, 3); 0.6 m from the sensor line, "far" 1.2 m |
| Player model | disc of radius 0.18 m, echo from any box whose aim is within ±20° of it |
| Trials | 20 per jump and variant: the jump happens 6.00, 6.05, … 6.95 s after the player was first placed |
| Poll interval | 10 ms simulated |
| Total | 8 jumps × 4 variants × 20 trials = 640 trials, none without a fix |

Variants:

- **before**: the tracker as it was. After a miss a box dithers ±8° round the
  old spot for 1 s, then resumes its 5° sweep from there. The tool reproduces
  it by switching the search off; on eight jumps this gave the same times as
  the code of commit 612d492.
- **search**: the tracker as it is. After a full loss every box searches in 15°
  steps, toward the middle of the field first.
- **right hint**: search, and the game named the spot the player jumps to
  (`expect()`), as it would when the player follows the mole.
- **wrong hint**: search, and the game named the third column instead.

## Results

Seconds, median (fastest–slowest) of 20 trials.

Jump to first fix:

| Jump | before | search | right hint | wrong hint |
|---|---|---|---|---|
| column 1 → 3 | 3.69 (3.57–3.82) | 1.49 (1.37–1.86) | 0.84 (0.79–0.98) | 1.42 (1.33–1.50) |
| column 3 → 1 | 6.71 (6.59–6.85) | 1.35 (1.20–1.92) | 0.88 (0.80–0.94) | 1.43 (1.26–1.56) |
| column 1 → 2 | 0.61 (0.49–1.12) | 0.61 (0.49–1.12) | 0.61 (0.49–1.12) | 0.61 (0.49–1.12) |
| column 2 → 3 | 0.62 (0.57–3.58) | 0.62 (0.57–1.82) | 0.62 (0.57–1.46) | 0.62 (0.57–1.78) |
| column 2 → 1 | 1.19 (0.57–4.46) | 1.19 (0.57–1.92) | 0.87 (0.57–1.32) | 1.27 (0.57–2.08) |
| column 3 → 2 | 0.62 (0.57–1.09) | 0.62 (0.57–1.09) | 0.62 (0.57–1.09) | 0.62 (0.57–1.09) |
| column 1 → 3, far | 3.35 (3.25–3.50) | 1.45 (1.33–1.68) | 0.84 (0.79–0.94) | 1.72 (1.67–1.84) |
| column 3 → 1, far | 9.12 (8.99–9.25) | 1.34 (1.27–1.55) | 0.90 (0.87–0.94) | 1.43 (1.33–1.50) |

Jump to first two-box fix:

| Jump | before | search | right hint | wrong hint |
|---|---|---|---|---|
| column 1 → 3 | 3.76 (3.65–3.82) | 1.67 (1.55–1.86) | 1.10 (1.03–1.26) | 1.42 (1.33–1.50) |
| column 3 → 1 | 7.47 (7.35–7.53) | 1.88 (1.31–1.94) | 1.00 (0.95–1.26) | 1.43 (1.26–1.56) |
| column 1 → 2 | 1.29 (1.17–1.54) | 1.29 (1.17–1.54) | 1.29 (1.09–1.46) | 1.29 (0.95–1.90) |
| column 2 → 3 | 1.30 (1.25–3.58) | 1.30 (1.25–1.82) | 1.30 (1.25–1.54) | 1.30 (1.25–2.38) |
| column 2 → 1 | 1.28 (1.17–4.46) | 1.28 (1.17–1.92) | 1.28 (1.09–1.64) | 1.61 (1.25–2.08) |
| column 3 → 2 | 1.20 (1.11–1.32) | 1.20 (1.11–1.32) | 1.20 (1.11–1.32) | 1.20 (1.11–1.32) |
| column 1 → 3, far | 3.35 (3.25–3.50) | 1.45 (1.33–1.68) | 1.12 (0.95–1.18) | 1.72 (1.67–1.84) |
| column 3 → 1, far | 9.12 (8.99–9.25) | 1.48 (1.31–1.55) | 0.98 (0.95–1.02) | 1.43 (1.33–1.50) |

First fix by kind of jump, 80 trials each (from the CSV):

| Jumps | Variant | Median | 95th percentile | Slowest | Trials over 2 s |
|---|---|---|---|---|---|
| skip a column (4 jumps) | before | 5.21 | 9.22 | 9.25 | 80 of 80 |
| | search | 1.43 | 1.89 | 1.92 | 0 |
| | right hint | 0.88 | 0.94 | 0.98 | 0 |
| | wrong hint | 1.46 | 1.81 | 1.84 | 0 |
| next column (4 jumps) | before | 0.63 | 4.42 | 4.46 | 13 of 80 |
| | search | 0.63 | 1.88 | 1.92 | 0 |
| | right hint | 0.63 | 1.43 | 1.46 | 0 |
| | wrong hint | 0.63 | 2.04 | 2.08 | 6 of 80 |

Change of the median first fix for the jumps that skip a column:

| Jump | before | search | change | right hint | change |
|---|---|---|---|---|---|
| column 1 → 3 | 3.69 | 1.49 | −60 %, 2.5× faster | 0.84 | −77 %, 4.4× faster |
| column 3 → 1 | 6.71 | 1.35 | −80 %, 5.0× faster | 0.88 | −87 %, 7.6× faster |
| column 1 → 3, far | 3.35 | 1.45 | −57 %, 2.3× faster | 0.84 | −75 %, 4.0× faster |
| column 3 → 1, far | 9.12 | 1.34 | −85 %, 6.8× faster | 0.90 | −90 %, 10.1× faster |

What the tables show:

- A jump that skips a column always lost the player before, for 3.3 to 9.3 s.
  With the search every such trial is back within 1.92 s, with the right hint
  within 0.98 s.
- A move to the next column usually keeps the player (median unchanged at
  0.63 s), but 13 of 80 such trials lost them for more than 2 s before, the
  slowest for 4.46 s. With the search the slowest is 1.92 s.
- A wrong hint costs one look: medians stay within 0.3 s of the search without
  a hint, and the slowest trial is 2.08 s.

## Where the time went

One trial, column 1 → 3, jump at 6.00 s. Each line is a change of mode; the
angle is the bearing the box was last sent to (0° right, 90° straight out,
180° left).

Before:

```
+ 0.00 s  0: aimed   67°  1: aimed  129°  2: aimed  154°  track
+ 0.10 s  0: aimed   67°  1: aimed  129°  2: jitter 162°  track
+ 0.20 s  0: jitter  75°  1: aimed  129°  2: jitter 162°  track
+ 0.30 s  0: jitter  75°  1: jitter 137°  2: jitter 162°  track
+ 1.30 s  0: jitter  75°  1: jitter 137°  2: sweep  160°  find
+ 1.40 s  0: sweep   75°  1: jitter 137°  2: sweep  160°  find
+ 1.50 s  0: sweep   75°  1: sweep  135°  2: sweep  160°  find
+ 3.64 s  0: aimed   45°  1: aimed  100°  2: aimed  130°  track
```

Search:

```
+ 0.00 s  0: aimed   67°  1: aimed  129°  2: aimed  154°  track
+ 0.10 s  0: aimed   67°  1: aimed  129°  2: jitter 162°  track
+ 0.20 s  0: jitter  75°  1: aimed  129°  2: jitter 162°  track
+ 0.30 s  0: jitter  75°  1: jitter 137°  2: jitter 162°  track
+ 0.50 s  0: search  65°  1: search 137°  2: search 146°  find
+ 1.44 s  0: aimed   35°  1: aimed   95°  2: aimed  120°  track
```

All three boxes miss within 0.3 s. Before, each spent a further 1.0 s on
jitter round the empty spot, then swept 5° per step. Now the loss is declared
at 0.50 s (`local_search_s`) and the boxes search 15° per step.

## Time budget

Only one box may ping at a time. In the simulator the pings of a searching
field are 0.100 s apart (measured; a missed echo times out after 25 ms, the
acoustic guard adds 65 ms, and the next 10 ms poll starts the next ping), so
with three boxes each box takes one step every

    T_step = N_boxes × T_slot = 3 × 0.10 s = 0.30 s

measured as 0.300 s per step on every box, for 5° and for 15° steps alike: the
ping schedule limits the step rate, not the servo. The angular search rate is
therefore step size / T_step: 5° / 0.30 s = 16.7 °/s before, 15° / 0.30 s =
50 °/s in the search.

The time to the first fix is about

    T ≈ T_start + n × T_step + T_confirm

where T_start is when the box begins to step (jitter ends, 1.3 to 1.5 s,
before; loss declared, 0.50 s, now), n the number of steps until the aim is
within the 20° beam half-angle of the player, and T_confirm = T_step for the
second ping that confirms a first echo.

Check against the trial above, box 2 (player at 113° from box 2):

| | T_start | Steps | n × T_step | T_confirm | Model | Simulated |
|---|---|---|---|---|---|---|
| before | 1.30 s | 160° → 130°, n = 6 | 1.80 s | 0.30 s | 3.40 s | 3.64 s |
| search | 0.50 s | 146° → 135° → 120°, n = 2 | 0.60 s | 0.30 s | 1.40 s | 1.44 s |

The remainder is waiting for the box's turn in the ping schedule.

Before, the sweep also kept its old direction. In column 3 → 1 every box swept
away from the player; box 0 went from 33° down to 0°, turned and found the
player (at 67°) on the way back at 50°, 6.62 s after the jump (9.1 s in the
far row). The search starts toward the middle of the field.

## Limits

- Simulation only. The real boxes add Wi-Fi delay to every command and reply,
  so the step period, and with it every time above, will be longer on
  hardware; the step period of this tracker has not been measured there. The
  ratio before/after is expected to carry over because both depend on the same
  step period, but only a field run can show it.
- The simulated beam is an exact ±20° cone and the player a disc. A real
  HC-SR04 on a body may see less, and a 15° step could then pass over the
  player. `search_step_deg` can be lowered in the config.
- The player moves instantly. A real jump takes a few tenths of a second,
  during which the boxes may still catch the player in passing.
- The column spots assume three equal columns across the field width, as the
  game maps x to a column.

## Reproduce

```bash
python3 -m tools.jump_bench --csv results/jump-bench-2026-10-02.csv --timeline
```

The simulator runs on a simulated clock, so the numbers repeat exactly. The CSV
has one row per trial (variant, from/to column, depth, jump moment, first fix,
two-box fix); `*.csv` is not tracked by Git.

For the field: record a run with
`python3 -m whack --tracker swarm --config config.prototype.json --record results/jump-N.csv`
and summarise it with `python3 -m tools.session_metrics results/jump-N.csv`
(reacquire median and 90th percentile). The last two-box field figures, 23
September, were 1.4 s median and 15.6 s at the 90th percentile.
