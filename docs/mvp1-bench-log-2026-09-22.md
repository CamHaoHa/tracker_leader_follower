# MVP1 bench log — 22 September 2026

First full-day bench session with both physical boxes. This records what was
found, what was changed, and the measured effect, so MVP1 can show the
development process with numbers. All figures come from the CSV recordings in
`results/` (`python3 -m tools.session_metrics` reproduces the table).

## Setup

| Item | Value |
| --- | --- |
| Boards | 2 × Freenove ESP32-WROOM-32E, CH340 USB, Arduino core 2.0.17 via PlatformIO |
| Sensors | HC-SR04 (ECHO direct to GPIO35), SG90 servo on GPIO25, TRIG GPIO32 |
| Servo mapping | 500–2500 µs, verified travel 15°–165° |
| Network | Home Wi-Fi (profile 0), node 0 = 192.168.0.50, node 1 = 192.168.0.38, UDP 4210/4211 |
| Layout | Boxes 1.0 m apart, field 1.0 m wide, 0.8–2.0 m from the wall (`config.bench-1.0m-deep.json`) |
| Laptop | Ubuntu, Python 3.12, Tk |

The brief's field is 1.5 m × 1.4 m (0.6–2.0 m from the wall). The bench is
narrower; the same geometry model runs with `config.local.json` for the full field.

## Timeline: problem → change → measured effect

| # | Time | Problem observed | Change | Evidence |
| --- | --- | --- | --- | --- |
| 1 | 13:00 | Box 1 returned `INVALID` on every ping, servo fine | Diagnostic sketch: GPIO35 pinned at ≥3.1 V, no pulse | ECHO stuck high; cleared by power cycle at 14:37, then 3/3 OK ranges |
| 2 | 14:40 | Box 1 ranging OK; box 2 flashed | Both boxes: Wi-Fi, servo 90→60→120→90, ranges 3/3 OK each step | `probe_node` logs |
| 3 | 15:53 | First two-node run: calibration aborted 3× in 20 steps ("Servo readiness timed out") | Controller: re-request lost READY every 0.3 s; tolerate 3 failed frames per calibration step | Next sweep: 111/111 pairs in 30 s, no abort |
| 4 | 16:30 | No position ever produced; UI unreadable, no way to stop | UI: 24 px status, buttons Pause/Reset, later Search; idle at start; diagnostics show `Connected <ip>` | Screenshot check |
| 5 | 20:20 | Node 0 servo "runs like crazy"; USB link dropped 6× on port 1-3 | Search path reordered: nearest-neighbour in bearing space; search restarts at last known position | Mean swing per step 12–14° (default field), was field-wide jumps |
| 6 | 21:30 | Calibration interrupted by `INVALID` bursts after no-echo cycles | Firmware refused to trigger while ECHO still high; controller now treats age-0 `INVALID` as "sensor busy" and re-aims (soft retry) | 0 interrupted sweeps after the change (11 sweeps completed) |
| 7 | 22:05 | 73° calibration start move rocked the box | Firmware: servo ramp 150°/s, auto-faster only to meet the 700 ms settle cap; READY waits for the ramp | 73° move ≈ 0.5 s, reply ≈ 0.8 s incl. settle |
| 8 | 22:33 | First lock | — | Run 10: dot 61 %, 4.3 Hz, jitter 7.8 / 3.2 cm, reacquire 0.8 s |
| 9 | 22:50 | Dot ~0.2 m too near the wall; arm swing jitter | `body_radius_m` 0.18 (surface → centre), `smoothing_tau_s` 0.25, beam tolerance widened by body angle; saved map no longer invalidated by tuning changes | Run 15 standing: y within 0.1 m of the mark; jitter 2.2 / 0.7 cm |
| 10 | 23:00 | After box reassembly every bearing read 4–6 cm | Direct sampling proved the enclosure was in the beam; sensor+servo modules moved outside the boxes | Map: 0 bearings under 0.5 m (was 43/46 and 33/46) |
| 11 | 23:26 | — | Longest clean run | Run 15: dot 75 % over 228 s incl. walking, 4.9 Hz, 100 % for 40 s stationary |
| 12 | 23:35 | Dot moved opposite to the player | Display mirrored (player faces the screen) | Verified by user |
| 13 | 23:45 | No reference on screen | Field frame, 0.25 m grid, metre labels, centre cross | Screenshot check |

## Metrics by run

Dot % = share of active (searching or tracking) time with a position on screen.
Jitter = median 2-second standard deviation of x / y while a fix exists.
Reacquire = time from loss to next lock (median / 90th percentile).

| Run (file) | Situation | Calibration | Dot % | Fresh fixes | Jitter x / y | Reacquire |
| --- | --- | --- | --- | --- | --- | --- |
| 15:53 | first two-node attempt, no retry logic | 0 of 3 sweeps completed | 0 | — | — | — |
| bench-live2 | retries added; right sensor mis-aimed | 111/111 in 30 s | 0 | — | — | — |
| bench-live5..9 | travel widened, deeper field, ramp | completed each time | 0 | — | — | — |
| bench-live10 | first lock, point-target model | 138/138 in 32 s ×2 | 61 | 4.3 Hz | 7.8 / 3.2 cm | 0.8 s / 0.9 s |
| bench-live13 | boxes reassembled, sensors blocked | maps contaminated | 0 | — | — | — |
| bench-live15 | sensors outside boxes, body model | 138/138 in 31 s | 75 | 4.9 Hz | 2.2 / 0.7 cm | 0.8 s / 10.5 s |
| bench-live16 | mirrored display, fast moves | (reused) | 47 | 4.5 Hz | 3.0 / 1.9 cm | 1.0 s / 6.2 s |
| bench-live18 | grid, 200 s walking incl. edges | (reused) | 50 | 4.8 Hz | 4.3 / 3.2 cm | 0.8 s / 7.4 s |

Loss analysis of bench-live18 (46 losses): left sensor missed the player while
the right still saw them in 26 cases, right missed in 9, both in 4. During
searching the right sensor saw a person-range echo 61 % of the time, the left
36 %. Node 0's aim or level is the next thing to fix (aim-trim check).

## What works now

- Both boxes flash from PlatformIO, join Wi-Fi, announce, aim and range.
- Empty-field calibration completes reliably in ~31 s (138 pairs) and survives
  lost packets and sensor hold-offs.
- Tracking locks in under 1 s when the player stands in the middle of the field,
  updates 4–5 times per second, and is stable to ±2 cm when standing still.
- Idle start, Search / Pause / Reset / Calibrate buttons, servo parking at 90°,
  mirrored display with a metre grid.

## Known limits and next steps

1. **Enclosure**: the sensors must sit at or in front of the box face with a
   clear ±75° arc; inside the box they see the wall at 4–6 cm.
2. **Node 0 USB link** dropped repeatedly under servo load (port 1-3). Separate
   servo supply (the brief's 4×AA) and a better cable.
3. **Node 0 aim**: run the aim-trim check and set `SERVO_CENTER_TRIM_MDEG`.
4. **Edges**: coverage falls to ~20 % near either box. Brief spacing (1.5 m)
   helps; a third box in the middle would remove the weak zone (software: N-node
   frames, 3-range solve, ~1 day).
5. **Fast depth moves** (>0.4 m/s toward or away) drop the lock for ~1 s.
6. Loopback UDP tests fail while a real box broadcasts on the LAN (duplicate
   node ID guard). Run them with the boxes off.
