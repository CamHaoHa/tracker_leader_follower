## 2026-10-02 — search after a full loss, mole hint

- Problem: when the player skipped a column (mole at column 1, then column 3)
  the tracker needed seconds to find them again. All three boxes were aimed at
  the old spot and missed together; each then dithered ±8° round that empty spot
  for `jitter_s` (1 s) and only then resumed its 5° sweep from the old bearing,
  in whichever direction it had last swept, sometimes out to the end stop first.
  The boxes only obey `AIM`/`FIRE`, so this is laptop logic in `whack/swarm.py`.
- Swarm tracker: when no box has seen the player for `local_search_s` (the
  existing "Player lost" moment) every box stops its jitter and searches: steps
  of `search_step_deg` (new setting, default 15, between `sweep_step_deg` and
  45), first toward the middle of the field, once out to each end of its arc,
  then the plain 5° sweep again. Search bearings stay on the sweep grid, so a
  saved calibration map remains valid. `search_step_deg` equal to
  `sweep_step_deg` searches in plain sweep steps.
- Unchanged: one box missing while another still tracks (jitter 1 s, sweep,
  2 s re-aim cooldown), the first sweep after Search/Reset, the two-ping
  confirmation of an echo, the ping schedule. No firmware change, no reflash.
- New `SwarmController.expect(point)`: the game says where it expects the
  player, e.g. the column the mole moved to. After a full loss each box looks
  there first, then searches as above. It is never reported as a position; a
  fix still needs a reliable echo. `None` or a point outside the field
  withdraws it, and Search/Reset forgets it. The game repository does not call
  it yet.
- Status line while searching shows `search` instead of `sweep` for a box that
  is in the search pass.
- Simulator, `config.prototype.json`, median seconds from the jump to the first
  fix within 0.25 m over 20 jump moments (10 ms poll; player 0.6 m from the
  sensor line, "far" 1.2 m):

  | Jump | Before | Search | Search + right hint | Search + wrong hint |
  |---|---|---|---|---|
  | column 1 → 3 | 3.69 | 1.49 | 0.84 | 1.42 |
  | column 3 → 1 | 6.71 | 1.35 | 0.88 | 1.43 |
  | column 1 → 3, far | 3.35 | 1.45 | 0.84 | 1.72 |
  | column 3 → 1, far | 9.12 | 1.34 | 0.90 | 1.43 |
  | next column (four jumps) | 0.61–1.19 | same | 0.61–0.87 | 0.61–1.27 |

  A move to the next column usually keeps the player, but 13 of 80 such trials
  lost them for more than 2 s before (slowest 4.46 s); with the search the
  slowest is 1.92 s. Full tables, the per-box timeline and the time budget are
  in `docs/jump-bench-2026-10-02.md`.

  Not measured on hardware. The simulator has no Wi-Fi delay and sees a player
  anywhere inside the ±20° beam model; if a real box steps over the player,
  lower `search_step_deg` (10) in the config.
- Tools: `python3 -m tools.jump_bench` runs these jumps in the simulator
  (before, search, right hint, wrong hint) and prints the tables; `--csv`
  writes one row per trial, `--timeline` what each box does after a jump.
- Tests: `JumpTests` and `ExpectTests` in `tests/test_swarm.py`.

## 2026-10-01 — prototype config in the repository, phone hotspot only

- Config: `config.prototype.json` is the tracked field setup of the three-box
  prototype: sensors at x 0, 0.75 and 1.50 m on the line y 0.50 m, servo travel
  0..180 degrees, buzzer on node 1. Until now it existed only in the Git-ignored
  `config.local.json`, so a fresh clone on another computer could not run the
  prototype. `config.local.json` remains an optional personal override, used
  with `--config config.local.json`. Without `--config` the CLI still uses the
  built-in two-box defaults.
- Run command for the three-box prototype:
  `python3 -m whack --tracker swarm --config config.prototype.json`, with no
  `--nodes`. The boxes announce themselves with `WM2 HELLO` and are discovered;
  `--nodes` stays as an optional override for a network that blocks broadcast.
- README: new section "Run on another computer" (Python 3.10+ with tkinter, no
  pip packages, same hotspot, incoming UDP 4210, calibrate once per computer).
- Firmware: one network, the phone hotspot, joined as an ordinary WPA2-personal
  station with `WIFI_SSID` / `WIFI_PASSWORD`. Removed `WIFI_PROFILE` and its four
  profiles, `SCHOOL_WIFI_*`, `ONENET_*` and `TRACKER_WIFI_*`, the WPA2-Enterprise
  (PEAP) code with its certificate clock, the TrackerNet access point that node 0
  ran, and every node 0 networking special case. The reconnect attempt every
  10 s is unchanged. The boot banner prints the network name it will join, never
  the password. An empty `WIFI_SSID` still builds, reports missing credentials
  over USB and never connects. A name longer than 32 bytes fails the build.
- Private configs are not migrated automatically. An existing `config.local.h`
  or `tracker_config.h` that selected a profile must have its hotspot name and
  password moved into `WIFI_SSID` / `WIFI_PASSWORD` by hand. `settings.h`
  refuses to build while any removed name (`WIFI_PROFILE`, `SCHOOL_WIFI_*`,
  `TRACKER_WIFI_*`, `ONENET_*`) is still defined and names the fix, so an old
  config cannot silently join the network left in `WIFI_SSID`.
- Tools: `tools/prepare_tracker_firmware.py` lost `--network`, the generated
  `tracker_network.h` and `tracker_network.local.json`; its `tracker_config.h`
  template has the single Wi-Fi block. It still never overwrites an existing
  `tracker_config.h`. `tools/probe_network.py`, which existed only for the
  deferred OneNet UDP check, is deleted.
- `.gitignore` keeps its entries for `tracker_network.local.json` and the
  `onenet_*` sketch folders: nothing creates them now, but old copies on disk
  contain passwords.
- Docs: the OneNet and university-network sections, TrackerNet and the profile
  table are removed from the READMEs and guides, which now describe the one
  supported network. The earlier entries below and the bench logs keep the
  record of the removed setups.
- Checked without hardware: the four firmware environments build (flash use of
  `node_left` 745797 bytes before and 745821 after, same private config; the
  other profiles were already compiled out), a build without `config.local.h`
  succeeds, a generated `tracker_middle` sketch compiles, the native parser
  test passes, and the Python suite passes (126 tests, run with UDP 4210 free).
  Compiled with Arduino-ESP32 2.0.17 only; the 3.x code paths were not built.
- Review follow-up, same day. Docs: the controls are described as the window
  binds them (Space searches, P pauses and resumes, R stops and forgets the
  player until Space is pressed; "Space / R restarts acquisition" was wrong for
  both trackers). The live setup guide's scan steps now match the swarm tracker,
  which waits for Space after calibration. The READMEs say which sensor line
  belongs to which config: `y = 0.50` for `config.prototype.json`, `y = 0.20`
  for the built-in two-box defaults. "Run on another computer" names the branch
  to check out until the work is merged into `main`, adds Windows and macOS
  notes (written from general knowledge of those systems, not tried on either)
  and says what to check when the boxes are not found. Tests: the DHCP-change
  discovery test lost its soft-AP name and addresses. With the `settings.h`
  guard above and its host-compiler test the Python suite has 128 tests.
  `README_1.html`, the two-box explainer of 2026-09-23, keeps its run command
  as a record of that setup.
  Nothing was flashed or run on the boxes.

## 2026-09-29 — buzzer: review follow-up

- Swarm: a "Player too close to box n" report is dropped when that box is
  offline or has reported nothing for 1.5 s, and on pause. Before, only a later
  reading from the same box withdrew it, so a box that went offline left the
  alert up and the buzzer sounding for as long as the tracker ran. Resume no
  longer sounds for a player who stepped back during the pause.
- Swarm: a BUZZ that fails to send is tried again after 0.2 s, not on every
  poll.
- Firmware: `BUZZER_PIN` on GPIO1, GPIO3 (serial) or GPIO6..11 (flash) fails
  the build. Pin 25 is unaffected.
- Tools: `python3 -m tools.probe_node ... --buzz` sounds the buzzer during the
  pings, for the bench check in the buzzer section of
  `docs/live-tracker-setup.md`.
- Docs: a box that prints no `Buzzer:` line at boot runs firmware from before
  the buzzer and ignores `WM2 BUZZ`. In a two-box layout the PlatformIO
  `node_right_pair` build drives GPIO25 and the generated `tracker_right_pair`
  sketch does not.
- Checked without hardware: the four firmware environments build, the native
  parser test passes, and the Python suite passes (125 tests, run with UDP 4210
  free). Not yet checked on the boxes: the buzzer itself, and whether its sound
  changes the middle box's ranges.

## 2026-09-29 — one pin map for every box, buzzer on the middle box

- Pins: servo GPIO33, TRIG GPIO32 and ECHO GPIO34 on every box (were servo
  GPIO25 and ECHO GPIO35). The sensors are powered from 3V3 and ECHO is wired
  directly; the divider is gone. GPIO34 is input-only and has no internal pull
  resistors. Changed in the `settings.h` defaults, `config.example.h`, the
  `tracker_config.h` template of `tools/prepare_tracker_firmware.py`, the
  `bench_test` and `sensor_test` sketches, the boot banner and the wiring
  sections of the READMEs and setup guides. An existing `config.local.h` or
  `tracker_config.h` keeps its own pins until it is edited by hand.
- Firmware: optional buzzer. `BUZZER_PIN` defaults to -1 (none) and is 25 for
  node 1 in `config.example.h`. `BUZZER_TONE_HZ` 2000 is a square wave for a
  passive buzzer on LEDC channel 2 (10-bit, 50 % duty, duty 0 when silent); 0
  holds the pin HIGH for an active buzzer. A buzzer pin that is input-only or
  shared with the servo, trigger or echo fails the build.
- Protocol: `WM2 BUZZ <duration_ms>`, 0..2000, from the host port only. No
  sequence, no reply, no ownership, and no effect on aims or firing leases.
  The box sounds until receipt + duration, each BUZZ replaces the deadline, 0
  silences at once, and the box silences itself at the deadline. A box without
  a buzzer ignores it.
- Laptop: `protocol.buzz()`, `Geometry.buzzer_node` (-1 = none; not a layout
  field, so saved calibrations stay valid). The swarm tracker sends `BUZZ 400`
  every 0.2 s while the alert is "Player in the dead zone" or "Player too close
  to box n", and `BUZZ 0` once when that ends, on pause, reset, calibration
  start or close. Other alerts are silent. The paired tracker is unchanged.
- Simulators: `SimulatedTransport` records BUZZ (`.buzzes`, `.buzzing(node)`);
  `tools/simulate_nodes.py` accepts and ignores it.
- Config: `"buzzer_node": 1` in `config.example.json`.
- Checked without hardware: the four firmware environments build, the native
  parser test passes, and the Python suite passes (119 tests; `test_udp` needs
  UDP 4210 free, so close the tracker first). The new wiring and the buzzer
  have not been flashed or run on the boxes yet.

## 2026-09-23 — swarm tracker: no more prediction

- `whack/swarm.py`: the alpha-beta `Motion` filter (velocity + extrapolation) is
  replaced by `Estimate`, smoothing only. The spot is the last measured point,
  smoothed with `smoothing_tau_s` (half weight for a one-box fix) and a
  jump-reject at `max_speed_m_s`. Nothing is extrapolated: leader-follower aims
  every box at the last fused point and re-aims when it moves 0.3 m, so a
  velocity guess from noisy one-box fixes only pushed the aim off.
- Hollow spot now means "one box only" (`contributors < 2`); solid means both
  boxes agreed within 0.30 m. Confidence fades over `local_search_s`.
- `aim_lead_s` and `prediction_horizon_s` are no longer used by the swarm
  tracker (the pairs tracker still uses them).
- Live run before the change (t 670–867 s of `results/swarm-run2.csv`, walking):
  dot 85 %, two-box 39 %, one-box 55 %, node 0 timeouts 38 %, node 1 32 %.

## 2026-09-22 — first bench session with both boxes

See `docs/mvp1-bench-log-2026-09-22.md` for the measured timeline. Summary:

- Controller: lost READY re-requested; calibration tolerates 3 failed frames per step; "sensor busy" `INVALID` (ECHO still high after a no-echo cycle) retried instead of failing; search visits targets along a small-swing path and restarts near the last known position; idle start with Search / Pause / Reset; servos parked at 90° on pause, reset and close; body-radius model (`body_radius_m`) and 0.25 s smoothing; saved maps stay valid across tuning changes; CSV records the aim point.
- Firmware: servo ramp at 150°/s with READY waiting for the ramp; caps 0–180° in the local config after a 15–165° travel check.
- UI: 24 px status, five buttons on their own row, PAUSED banner, mirrored x axis, field frame with 0.25 m grid and labels.
- Tools: `tools/session_metrics.py` summarises recordings.
- Results: calibration 138 pairs in ~31 s with no aborts after the retry changes; tracking 4–5 fresh fixes/s, ±2 cm standing, 75 % dot coverage over a 228 s walking run; edges near either box remain weak.

# Engineering change log

## Left ESP32 hosts TrackerNet (15 September 2026)

- Added profile 3: the left ESP32 creates a protected access point at
  192.168.4.1; right ESP32 and laptop join using DHCP. The laptop continues
  coordinating both sensors and rendering the spot.
- AP readiness, UDP replies and broadcasts now use the AP interface; home,
  school personal Wi-Fi and optional OneNet profiles remain available.
- Added `--network tracker` preparation with a shared private password and
  preserved original credentials/servo settings. `--network configured`
  restores the existing profile. Both uploads remain manual.
- Added credential-pairing/preservation and DHCP discovery regression tests.
  Actual radio connectivity and motion tracking require the user's hardware test.

## Coordinated live tracking workflow (15 September 2026)

- Implemented WM2 concurrent servo aiming and sequential one-use ultrasonic
  firing leases, including conservative recovery after lost UDP responses.
- Added unicast discovery for fixed IPs and six-second connection freshness.
- Added dense empty-field calibration, two-pair target confirmation,
  timestamp-aware range alignment, alpha-beta velocity estimation, short
  prediction, nearby recovery and full search after loss.
- The window renders one cyan spot; predictions are hollow and expire after
  200 ms by default. Gameplay, zone warnings and bells are excluded.
- Preserved home/school network profiles and private settings; regenerated
  separate Arduino sketches for manual upload.
- Software tests cover synthetic moving targets, missing echoes, delayed/lost
  messages, acoustic scheduling and UI behavior. Firmware builds pass on Arduino
  ESP32 2.x and 3.x. These results do not establish real player accuracy or delay.

## Live tracker setup with the user's hardware

- Identified Freenove ESP32-WROOM-32E boards and HC-SR04 sensors; configured
  servo GPIO25, TRIG GPIO32 and ECHO GPIO35 through the external divider.
- Prepared separate Arduino IDE left/right sketches from the maintained node
  source, with private Wi-Fi/servo settings preserved when regenerating.
- Added Arduino ESP32 3.x PWM/UDP compatibility while retaining the pinned
  PlatformIO/core 2.x builds. Both nodes compile with both toolchains.
- Added an Arduino IDE-to-desktop setup guide and a local geometry file using
  the documented default placement, pending actual mounting measurements.
- Closed a simulated scan-coverage gap using additional paired aim directions
  (39 points for default geometry), and briefly retry the last player aim after
  missed echoes while immediately hiding invalid position data.
- Distance reliability/calibration tests are paused at the user's request;
  completed Excel/serial evidence remains saved. Live servo/player tracking
  still needs upload, mounting alignment and an empty-area background scan.

## Baseline

- Preserved the assignment, read-only study implementation, and initial graph.
- Chose one sensor/servo per ESP32 with PC-controlled alternating measurements.
- Recorded coordinate conventions, wire protocol, assumptions, and failure states.
- Validation planned: native tests, UDP simulation, both firmware builds, then
  measured bench and playing-area trials using the actual components.

## ESP32 node firmware

- Added pinned left/right firmware builds, configurable servo calibration,
  strict versioned datagrams, echo timeouts, reconnect and duplicate suppression.
- Both ESP32 targets compiled; native parser and servo-mapping tests passed.
- No physical boards were flashed. Wiring/servo model confirmation remains open.

## Tracking subsystem and dot visualizer

- Current delivery scope: hardware tracking and black-screen cyan dot only.
- Added PC-controlled alternating acquisition, circle localization, background
  calibration, configurable geometry, freshness/beam/speed filters and diagnostics.
- Review corrected missing near-corner scan coverage, stale range pairing,
  background-filter bypass and fixed-address recovery after an outage.
- Added ideal sensor simulation plus real UDP emulation and failure tests.
- Hardware accuracy, servo response, body reflection behaviour and battery runtime
  remain unmeasured; record results and revision using the acceptance procedure.
