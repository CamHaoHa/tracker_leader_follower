# MVP1 bench log — 23 September 2026 (university, 1.5 m field)

Second full-day session, on the official field width. The morning showed the
paired tracker cannot hold a player once the boxes are 1.5 m apart; the
afternoon replaced it with the independent-sweep, leader-follower "swarm"
tracker (branch `leader-follower-tracking`). All figures come from the CSV
recordings in `results/`; the segment table below was computed with the same
definitions as `tools/session_metrics.py`, restricted to time windows.

## Setup

| Item | Value |
| --- | --- |
| Boards / sensors | as on 22 September (Freenove ESP32-WROOM-32E, HC-SR04, SG90; GPIO 25/32/35) |
| Network | phone hotspot (Wi-Fi profile 1); laptop 172.20.10.2, node 0 172.20.10.3, node 1 172.20.10.4 |
| Layout | boxes 1.5 m apart on the table edge, field 1.5 m wide, 0.6–2.0 m from the sensor line (`config.local.json`: sensor_y 0.5, near_y 0.6, far_y 2.0, body_radius 0.18) |
| Sweep bounds | box 0: 10–100°, box 1: 80–170°, 5° steps, 90° = straight out |
| Reliable range | 1.7 m; readings beyond it are hints only |

## Timeline: problem → change → measured effect

| # | Time | Problem observed | Change | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 10:30 | University Wi-Fi blocks node-to-laptop UDP | Phone hotspot for laptop + both boxes (profile 1) | HELLO from both nodes within 6 s |
| 2 | 11:20 | Paired tracker at 1.5 m: no lock; both sensors must see the player at once, edges beyond one sensor's reach | — (diagnosed with live data) | `uni-field15-run2`: dot 14 %, 17.6 losses/min, 2.6 Hz |
| 3 | 12:00 | — | Redesign: each box sweeps on its own in 5° steps; a reliable hit makes every box aim at that point; jitter ±8° then resume sweep; fusion by least squares on range circles; hollow dot for one-box fixes; pause alerts (too close, dead zone/outside, two players); N-box plumbing | `whack/swarm.py`, commits 40f9f4e, 1c9836b |
| 4 | 13:45 | First swarm run tracked at once, but 65 false "Player outside the field" pauses from one-box fixes | Two-box rule for the dead-zone alert, 0.4 m margin for one-box fixes, 2 s latch | `swarm-run1`: dot 92 %, two-box 35 %; run 2: 0 alerts (3ebfc40) |
| 5 | 13:55 | Node 1 echo rate 35 %: box 1 read a constant 1.3 m floor echo | User levelled and straightened box 1, recalibrated | `swarm-run2` 415–483 s: node 1 echo 85 %, two-box 62 % |
| 6 | 14:05 | Two-box share fell to 39 % on a long walk; dot lagged and overshot on turns | Removed velocity prediction (`Estimate` replaces the alpha-beta `Motion` filter); the spot is the last measured point, smoothed | `swarm-run3` 40–266 s: two-box 68 %, jitter 2.1 / 2.4 cm, 1.3 losses/min (84fc859) |
| 7 | 14:17 | Box 0 USB dropped (kernel: `usb 1-8 disconnect`); after re-plugging, node 0 echo rate fell from 75 % to 40 % at every distance | None yet: box 0 was disturbed physically (tilt or loose sensor wire) | `swarm-run3` 400–692 s: dot 73 %, two-box 31 % |
| 8 | 14:24 | Box 1 USB dropped too; session ended | — | — |

## Metrics by segment

Dot % = share of active time with a spot on screen. Two-box % = share of spots
where both boxes agreed within 0.30 m (solid dot). Echo = share of active rows
where that node reported a usable range. Jitter = median 2 s standard deviation
of x / y. Reacquire = loss to next lock, median / 90th percentile.

| Segment | Situation | Dot % | Two-box % | Fresh fixes | Jitter x / y | Losses / min | Reacquire | Echo n0 / n1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| uni-field15-run2 | paired tracker, 1.5 m apart | 14 | — | 2.6 Hz | 0.3 / 0.5 cm | 17.6 | 4.4 / 12.5 s | — |
| swarm-run1 | first swarm run, walking | 92 | 35 | 4.4 Hz | 6.2 / 6.2 cm | 5.7 | 0.4 / 2.0 s | 73 / 45 % |
| swarm-run2 0–58 s | box 1 tilted (floor echo) | 89 | 25 | 4.0 Hz | 5.7 / 7.2 cm | 10.3 | 0.5 / 1.1 s | 74 / 35 % |
| swarm-run2 415–483 s | box 1 straightened | 94 | 62 | 6.3 Hz | 3.8 / 5.6 cm | 2.6 | 1.3 / 1.9 s | 68 / 85 % |
| swarm-run2 670–864 s | long walk, with prediction | 88 | 39 | 4.2 Hz | 7.3 / 5.1 cm | 3.4 | 0.4 / 3.8 s | 56 / 66 % |
| **swarm-run3 40–266 s** | **prediction removed** | **89** | **68** | **6.6 Hz** | **2.1 / 2.4 cm** | **1.3** | 1.4 / 15.6 s | 75 / 74 % |
| swarm-run3 400–692 s | after box 0 USB re-plug | 73 | 31 | 4.9 Hz | 3.1 / 3.9 cm | 4.3 | 0.8 / 7.4 s | 40 / 55 % |

Box 0 echo rate by player distance, before and after the re-plug (same run):

| Distance from box 0 | Before (40–282 s) | After (400–566 s) |
| --- | --- | --- |
| < 1.0 m | 91 % | 56 % |
| 1.0–1.4 m | 84 % | 70 % |
| 1.4–1.7 m | 75 % | 40 % |

The drop at every distance, including close range, points at the box, not the
geometry. Node 1 stayed within a few points of its earlier rates.

## How the swarm tracker agrees on one target

1. Each box classifies its own reading: `< 0.10 m` too close; at or beyond the
   calibrated background minus 0.15 m → wall, rejected; `> 1.7 m` → hint only;
   otherwise a candidate that must repeat within 0.10 m at the same bearing
   within 1.5 s to count as reliable.
2. A reliable reading becomes a point: sensor position plus distance plus the
   0.18 m body radius along the bearing.
3. Fresh points from different boxes (within 0.6 s) are fused by least squares
   on their range circles. If the worst circle residual is ≤ 0.30 m the boxes
   agree (solid dot); otherwise only the newest box is kept (hollow dot) and,
   if the two polar points are ≥ 0.6 m apart, a two-player count is started.
4. Every box is then aimed at the fused point; a follower whose aimed ping
   misses jitters 0 / +8° / −8° for 1 s and then resumes its sweep from there.

## What works now

- Lock within ~1 s of pressing Search anywhere in the middle of the field,
  6–7 fresh fixes per second when both boxes see the player, ±2 cm standing.
- Dot on screen ~90 % of a walking run; two-box agreement ~two thirds of that.
- Recovery after a loss is automatic (jitter → sweep → re-lock), median 1.4 s.
- Calibration map on the 5° grid (19 bearings per box) in ~22 s, no walls.

## Known limits and next steps

1. **Box 0 after the USB re-plug** reads half as many echoes as before. Check
   it is level, faces 90° straight out, the sensor is horizontal and its four
   wires are seated. Then re-run and compare with the table above.
2. **USB power drops** (both boxes today, port 1-8 and 1-2) end a run. Servo
   supply separate from USB, or a powered hub.
3. **Far corners**: from either box the opposite far corner is 1.86 m away,
   beyond the 1.7 m reliable range, so only one box sees it. The third (centre)
   box at x = 0.75 m sweeping 30–120° covers it: `extra_sensor_x: [0.75]` in the
   config, protocol/geometry/transport already accept it, needs a live test.
4. **Follower confirmation** still needs two same-bearing pings within 0.10 m,
   which a walking player breaks. Option: accept an aimed ping as reliable when
   it lands within 0.30 m of the current fix.
5. **Body model** is still a circle of 0.18 m; the ellipse/prism model is later
   work.
6. Loopback UDP tests (`tests/test_udp.py`) are flaky on the hotspot (discovery),
   independent of the tracker code; run them off the hotspot.
