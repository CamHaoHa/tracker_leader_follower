# Standing benchmark, 5 October 2026

Why the swarm tracker lost a player who stood still, what was changed, and
how the change was measured in the simulator. Code: branch
`CamHaoHa/ghost-echo-rejection`, `whack/swarm.py`; benchmark:
`tools/stand_bench.py`.

## What was seen on the boxes

Two rounds of the game on the three boxes on 5 October 2026, 02:53 and 03:03,
with the field config of that evening (arcs 30–100°, 30–120°, 80–150°; servo
travel 30–150°) and an empty-room map calibrated at 02:32. In the first round
the player stood still for 46 s on the hole at x = 0.25 m, y = 1.42 m (game
frame, x from the player's left). From the game log:

| Measure | Value |
|---|---|
| Losses ("Player lost — sweeping") | 11 in 46 s (14 per minute) |
| Time tracked by two or more boxes / one box / lost | 73 % / 15 % / 12 % |
| "Position jumped" (a fix refused as too far from the last) | 6, all while box 0 read 0.62–0.64 m and boxes 1 and 2 read 0.87 m and 0.69 m |
| "Two players detected" | 1, also with box 0 at 0.64 m |
| Losses with box 0 at 0.61–0.64 m in the second before | 5 of 11 |
| Cursor jumps of more than 0.35 m | 7: 4 right after box 0 read 0.62 m, 3 after a one-box fix |

The empty-room map had exactly three echoes within reach of the field: box 0
at 0.62 m at 30° and 35°, and box 2 at 0.66 m at 150°. Those are the inner
ends of the outer boxes' arcs, about the distance to the middle box: most
likely the outer boxes hear the middle box at the edge of their beams. (Not
confirmed; a calibration with the middle box lifted out would show it.)

Boxes 1 and 2 agreed with each other on the player throughout: their ranges
put him at x = 1.33, y = 1.37 m in the tracker frame (x from box 0), and box
0's readings of 1.33–1.49 m, when it heard him, agreed with that within 8 cm.
The box positions in the config are right.

## Why the tracker lost him

1. From that hole the player is 33–36° from box 0, inside the bearings the
   map has the object at. The tracker took every reading there that was not
   nearer than the object as background, so box 0's readings of the player
   at 1.4 m were thrown away. The position rested on boxes 1 and 2.
2. A few degrees further round (37.5° and on, where the map has nothing) box
   0 sometimes heard the object again and took it for the player.
3. When boxes disagreed, the newest reading won and the others were
   dropped: one box on the object overruled the two on the player.
4. Readings were fused on their ranges alone. Box 0's 0.80 m circle crossed
   box 1's circle of the player at x = 0.07, y = 1.30 (tracker frame; the
   game's x = 1.43), where both ranges fit exactly: a ghost, accepted as a
   two-box fix. The cursor went there at +18 s, and every box was re-aimed at
   the ghost.
5. A missed ping (an HC-SR04 misses a person now and then) made the box
   forget its last echo and jitter ±8°. A reading confirmed only one at the
   same bearing (within 5°), so after one miss the box needed two or three
   pings, 0.5–0.75 s at about four pings a second, before it counted again.
   With box 0 out, two such gaps at once left 0.5 s without a fix: lost, and
   all boxes searched.

## What was changed (`whack/swarm.py`)

- **Static echoes as a band.** A reading is background when the map has an
  echo within `background_margin_m` (0.15 m) of its range at its bearing or
  up to `BACKGROUND_SPREAD_DEG` (10°) either side. A reading clearly farther
  than the mapped echo is not background: the object did not answer that
  ping, so something behind it did.
- **Agreement.** Readings are fused only when their circles meet within
  `RESIDUAL_M` (0.30 m) and the point lies inside every box's beam
  (`beam_half_angle_deg` + `BEAM_SLACK_DEG`, 20° + 10°). A crossing outside a
  beam is a ghost.
- **Outvote.** When a new reading agrees with no other, two boxes whose
  latest pings still find the player where they agree he is outvote it: it
  is not used, the box carries on as after a miss, its status shows
  "(outvoted)" and `rejections["outvoted"]` counts it. With fewer such boxes
  the newest reading still wins, together with any others that agree with
  it, because the player may have moved.
- **Confirmation.** A missed ping, an echo of the room and an echo beyond the
  reliable range no longer erase a box's last echo. A reading confirms the
  last one when the ranges agree within 0.10 m (as before), within 1.5 s (as
  before), at a bearing up to two jitter offsets away (16°; before: 5°).
- Unchanged: the ping schedule, the jitter and search, `expect()`, the jump
  gate, the alerts and their timing, the protocol. No firmware change.

## Simulator: standing still

`python3 -m tools.stand_bench --csv results/stand-bench-2026-10-05.csv`:
`config.prototype.json` with the arcs and map of 5 October; each box hears
the object where the map has it, and on 30 % of pings up to 10° further in;
15 % of pings at the player get no echo; the nearer echo wins. The player
stands 30 s on each of the 15 hole positions, three trials each.

| Hole (x, y m) | Losses/min before | after | Jumps/min before | after | On the hole before | after |
|---|---|---|---|---|---|---|
| (0.25, 1.10) | 20.7 | 2.7 | 4.7 | 0.0 | 73% | 100% |
| (0.50, 1.10) | 16.7 | 1.3 | 2.0 | 0.0 | 86% | 98% |
| (0.75, 1.10) | 18.0 | 4.7 | 0.0 | 0.0 | 91% | 98% |
| (1.00, 1.10) | 12.0 | 2.7 | 2.7 | 0.0 | 87% | 99% |
| (1.25, 1.10) | 17.3 | 2.7 | 5.3 | 0.0 | 79% | 98% |
| (0.25, 1.42) | 18.0 | 0.7 | 8.0 | 0.0 | 78% | 99% |
| (0.50, 1.42) | 14.7 | 0.7 | 10.0 | 0.0 | 81% | 100% |
| (0.75, 1.42) | 6.7 | 0.7 | 0.7 | 0.0 | 98% | 100% |
| (1.00, 1.42) | 7.3 | 0.0 | 3.3 | 0.0 | 91% | 98% |
| (1.25, 1.42) | 16.0 | 0.0 | 8.0 | 0.0 | 80% | 100% |
| (0.25, 1.74) | 13.3 | 0.0 | 8.7 | 0.0 | 83% | 100% |
| (0.50, 1.74) | 8.0 | 0.7 | 0.7 | 0.0 | 94% | 100% |
| (0.75, 1.74) | 5.3 | 0.7 | 0.0 | 0.0 | 97% | 100% |
| (1.00, 1.74) | 4.7 | 0.0 | 0.0 | 0.0 | 98% | 100% |
| (1.25, 1.74) | 6.7 | 0.0 | 2.0 | 0.0 | 96% | 100% |

| Variant | Losses/min | Jumps/min | On the hole | Two boxes or more | Position shown |
|---|---|---|---|---|---|
| before | 12.4 | 3.7 | 87% | 82% | 96% |
| after | 1.2 | 0.0 | 99% | 97% | 100% |

The scene reproduces the field: at the hole stood on (x = 0.25, y = 1.42) the
old tracker lost the player 18 times a minute in the simulator, 14 on the
boxes, and kept him on the hole 78 % of the time (70–90 % from the game
log's drawn cursor).

Each change in turn (same scene, all holes):

| Step | Losses/min | Jumps/min | On the hole | That hole: losses/min | jumps/min | on the hole |
|---|---|---|---|---|---|---|
| before (V2, 3191700) | 12.4 | 3.7 | 87% | 18.0 | 8.0 | 78% |
| + static echo as a band, 10° either side | 10.7 | 0.3 | 95% | 16.0 | 2.0 | 94% |
| + agreement with the beam check, outvote | 10.4 | 0.0 | 95% | 12.7 | 0.7 | 96% |
| + last echo kept, confirmation across 16° (= after) | 1.2 | 0.0 | 99% | 0.7 | 0.0 | 99% |

The first two steps stop the cursor jumps; the last one stops the losses.

Other assumptions (all holes; losses/min, jumps/min, on the hole):

| Missed pings | Edge echo | Before | After |
|---|---|---|---|
| 0 % | 0 % | 0.0, 0.0, 100% | 0.0, 0.0, 100% |
| 0 % | 30 % | 1.6, 2.9, 94% | 0.0, 0.0, 100% |
| 15 % | 0 % | 6.6, 0.0, 97% | 0.8, 0.0, 99% |
| 30 % | 30 % | 29.1, 4.5, 74% | 5.9, 0.1, 97% |
| 15 % | 60 % | 18.1, 11.7, 64% | 1.8, 0.1, 99% |
| 30 % | 60 % | 32.4, 11.1, 50% | 7.7, 0.3, 96% |

## Simulator: jumps (no slowing)

`python3 -m tools.jump_bench`, first fix, median (slowest) seconds over 20
jump moments, with the mole hint the game sends ("right hint"):

| Jump | 2 October | 5 October |
|---|---|---|
| column 1 → 3 | 0.84 (0.98) | 0.84 (0.98) |
| column 3 → 1 | 0.88 (0.94) | 0.89 (0.94) |
| column 1 → 2 | 0.61 (1.12) | 0.61 (0.82) |
| column 2 → 3 | 0.62 (1.46) | 0.62 (1.34) |
| column 2 → 1 | 0.87 (1.32) | 0.79 (1.24) |
| column 3 → 2 | 0.62 (1.09) | 0.62 (0.92) |
| column 1 → 3, far | 0.84 (0.94) | 0.84 (0.94) |
| column 3 → 1, far | 0.90 (0.94) | 0.90 (0.94) |

To the first two-box fix, with the hint, the adjacent moves are as fast or
faster (column 2 → 1: 1.28 → 1.20 s, slowest 1.64 → 1.32 s). Without a hint
one case is slower: column 3 → 1, far, 1.34 → 1.43 s to the first fix and
1.48 → 1.56 s to the two-box fix; the other jumps are as fast or faster.

An earlier version of the change let an aimed box try the same bearing once
more before jittering. It also cut the losses (to 2.5 a minute) but slowed
the adjacent move column 2 → 3 from 0.62 to 0.97 s, so it was replaced by the
wider confirmation, which does neither.

## Limits

Simulation only. The object model, the 15 % miss rate and the 30 % edge rate
are assumptions chosen to match the evening's map and log; the simulator's
ranges are exact, so it says nothing about range noise. The next field round
should be recorded with the game's `--record` option, which writes each
box's readings per frame, and compared with the log figures above.
