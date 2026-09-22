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
