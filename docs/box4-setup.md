# Fourth box (node 3): wiring, flashing, bring-up and acceptance tests

25 October 2026. The fourth box is the player-versus-player box: it stands
back to back with the middle box at `x = 0.85 m` and looks only into the
right half of the field (as the boxes see it; the players' left). Firmware
`node_fourth` (`NODE_ID 3`), geometry `config.pvp.json`, commands from the
`Makefile` in this repository. Every box uses the **same pin map**; only the
node number in the build differs.

## 1. Wiring

Board: ESP32 DevKit V1 style (Freenove ESP32-WROOM-32E or ELEGOO CP2102
30-pin). Read the **GPIO number on the silkscreen**, not the header position.

| Wire | ESP32 pin | Why |
|---|---|---|
| HC-SR04 VCC | **3V3** | Sensor runs on 3.3 V so ECHO is a 3.3 V signal |
| HC-SR04 GND | **GND** | Common ground |
| HC-SR04 TRIG | **GPIO32** | Output, no boot restriction |
| HC-SR04 ECHO | **GPIO34**, wired straight | Input-only pin, no divider needed at 3.3 V |
| Servo signal (orange or yellow) | **GPIO33** | PWM output |
| Servo V+ (red) | **VIN / 5V pin** (the USB 5 V rail) | Never the 3V3 pin or a GPIO: brown-outs and Wi-Fi drops |
| Servo GND (brown or black) | **GND** | Must share ground with the ESP32 |
| Power | **USB** from a supply that holds 5 V at 1 A (laptop, or a battery pack with a USB lead) | Box 4 has no battery pack of its own. A phone power bank sags under the servo and makes it hunt and buzz |
| Buzzer | none | Only the middle box (node 1) has one, on GPIO25 |

Rules that keep the box alive:

- Box 4 runs from USB. **Not a phone power bank**: on 26 October 2026 a
  90 → 10° move on a power bank sagged the 5 V rail, the servo overshot and
  hunted at 10° with a loud buzz, while the same move on laptop USB was
  silent. Use a battery pack like the other boxes, or a USB supply that
  holds 5 V at 1 A.
- Do not move the sensor to 5 V. With a 5 V supply ECHO is 5 V and GPIO34
  then needs a 2.2 kΩ / 3.3 kΩ divider. Only HC-SR04 revisions rated 3–5.5 V
  range reliably on 3V3; a classic 5 V-only one shows `TIMEOUT` on every ping.
- Never use GPIO1 / GPIO3 (USB serial), GPIO6–11 (flash), GPIO34–39 as
  outputs (input only), or GPIO0 / 2 / 12 / 15 (boot strapping pins).
- Battery sense: the other boxes read their pack on GPIO39 through a
  50 kΩ / 10 kΩ divider. Box 4 has no battery, so leave GPIO39 empty: the
  `make fourth` build (`BATTERY_SENSE=0`) always reports `5.00 V, 100 %`.

Checks with a multimeter before the first power-up: 3V3 pin to GND about
3.3 V with USB in; VIN to GND about 5 V; no short between VIN and GND; servo
red lead on VIN, not 3V3.

## 2. Flash

```bash
cd ~/Desktop/tracker_leader_follower
make status        # commit, "plain tracker firmware", which USB port is present
make fourth        # plug ONLY box 4 in; uploads node_fourth, then opens the monitor
```

The boot banner must read `Tracker node 3`, then
`Pins: servo=33, TRIG=32, ECHO=34 (sensor on 3V3, ECHO wired directly)`,
`Buzzer: none`, `Joining Wi-Fi "<hotspot>"` and
`Node 3 ready at <ip>:4211 (WM2 AIM/FIRE)`. Any other node number means the
wrong target was used (`make left` / `middle` / `right` flash nodes 2 / 1 / 0).
Ctrl+C leaves the monitor. If the upload fails twice, hold **BOOT** on the
board while it retries.

## 3. Bench checks before mounting

Run from the repository root with the box on the hotspot (IP from the
banner). These are the first three rows of the test table below.

| # | Check | Command | Pass when |
|---|---|---|---|
| B1 | Servo moves and centres | `python3 -m tools.probe_node --ip <ip> --node 3 --angle 90 --count 3` then `--angle 10` and `--angle 90` again | Horn swings about 80° one way for 10° and comes back to the same centre; no buzzing or stall. Which way is the right half is confirmed in A1/A2: node 3 must range a target standing at x > 0.85 m |
| B2 | Sensor ranges a flat target | board or box lid at 0.50 m, then 1.00 m, facing the sensor: `python3 -m tools.probe_node --ip <ip> --node 3 --angle 90 --count 10` | At least 9 of 10 `OK` with distance within ±3 cm of the tape measure |
| B3 | No echo = TIMEOUT, not a crash | point the sensor at open space > 4 m | `TIMEOUT` rows, the box keeps answering |

Seen on 25 October 2026 with box 4: every command answered and ranges
came back, but the horn never moved; the firmware banner had no servo
error. The servo itself was dead; a swap fixed it. A box that answers but
does not turn is a servo, power (red lead on VIN, not 3V3) or signal-pin
(GPIO33, not 32) problem, never the radio.

A box that returns `TIMEOUT` with a target at 0.5 m has a sensor or wiring
fault (box 0 behaved like this on 20 October): check VCC on 3V3, ECHO on
GPIO34, and swap the sensor before anything else.

## 4. Place and calibrate

1. Boxes at `y = 0.50 m`: node 0 at `x = 0`, node 1 at `0.75`, node 3 at
   `0.85` (back to back with node 1), node 2 at `1.50`. Sensors at the same
   torso height, beams level.
2. Dividing line at `x = 0.75 m`; holes at least 0.25 m from it.
3. Clear the field, then:

```bash
make calibrate-pvp     # writes calibration.pvp.json (empty-field map of all four boxes)
```

   The status line reports progress; wait for `Calibration saved`.
   Recalibrate after moving any box.
4. Tracking only: `make tracker-pvp`. With the game: `make game`, then choose
   two players on the title screen (**V** or the toggle under the mode cards);
   the game restarts its tracker on `config/swarm-field-pvp.json`.

## 5. Acceptance tests for the report

Each row is one record for `docs/test-evidence-template.md` in the game
repository. Evidence files follow `WEEK-STORY_OR_REQ-TEST-DATE-VERSION.ext`;
the Makefile writes recordings as `results/field/<date>-<LABEL>-*.csv`, so
pick `LABEL` as the test id (for example `make record-pvp LABEL=W13-PVP-A2`).

| # | Test | Procedure | Pass criterion | Evidence |
|---|---|---|---|---|
| A1 | Four boxes online | `make tracker-pvp`, press **D** | Status shows nodes 0, 1, 2, 3 with no `offline` or `no range reply` | Screenshot of the status line |
| A2 | One player per half, standing | Player 1 stands on the centre of the left half for 60 s, then player 2 on the right half | Dot on the correct player ≥ 85 % of the time, no spot in the empty half | `make record-pvp LABEL=A2-stand`, then `make metrics` (dot %, losses/min) |
| A3 | Both players walking | Both walk their own half slowly for 2 min | Each half keeps its player; losses ≤ 5 per minute per player; reacquire median ≤ 2 s | `make record-pvp LABEL=A3-walk`, `make metrics` |
| A4 | Half boundary | A player stands 0.20 m from the line on either side, 30 s each | The spot stays in the player's own half; the other half shows nothing | Recording with `LABEL=A4-line`; `zones` column in the CSV |
| A5 | Game round, two players | `make game`, two players, Easy, one full round | Both hammers follow their player; moles only on each player's own half; scores counted separately | `make game-record LABEL=A5-round`; `runtime-logs/game.log` in the game repo |
| A6 | Single player still works | Power box 4 on, `make game`, one player | Three-box tracking unchanged: box 4 is ignored by the single-player config | Recording with `LABEL=A6-single` |
| A7 | Power bank runtime | Box 4 on its power bank, `make tracker-pvp` idle sweeping | Still answering after 60 min; the bank does not switch off between pings | Timestamps of start and last reply in the tracker window |

Baseline numbers for comparison, three boxes, one player (field runs
22–23 September and 5 October, see `docs/mvp1-bench-log-2026-09-23.md`,
`docs/stand-bench-2026-10-05.md`): dot 89 %, losses 1.3 per minute walking,
reacquire 1.4 s median. With two players each box pings half as often, so
expect lower rates per player; report both numbers side by side.

## 6. Fallback: two players on three boxes

If box 4 is not ready, the tracker still splits the field with three boxes:
the left half keeps its pair (nodes 0 and 1), the right half is tracked by
node 2 alone, sweeping 90–170° from `x = 1.50 m`. The tracker allows a zone
with one box; its fixes are polar (servo bearing plus range), carry half the
confidence and read `Tracking player (one box)`. Expect more jitter on the
right half and slower reacquisition there. Checked in the simulator on
25 October 2026: both players tracked for 1107 of 1170 polls.

```bash
make tracker-pvp3   # config.pvp-3box.json, calibration.pvp-3box.local.json
make game-pvp3      # game with config/swarm-field-pvp-3box.json
```

Same acceptance tests A1–A6 apply; record them with `LABEL=...-3box` so the
report can show the three-box and four-box numbers side by side.

## 7. Automated gate before any field day

```bash
make check     # tracker tests (182), game tests (527), firmware parser test, compile, smoke runs
```

Run it after `make update` and before flashing. Results on 25 October 2026:
tracker `Ran 182 tests OK`, game `Ran 527 tests OK`.
