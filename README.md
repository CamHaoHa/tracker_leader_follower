# Two-node body tracker

Track one person with **two ESP32s, two positional servos and two ultrasonic
sensors**. Each servo aims one sensor. The laptop coordinates the two units,
estimates position and velocity, and displays **one cyan spot on a black screen**.
There is no gameplay logic.

The tracking workflow is implemented for software testing: empty-field
calibration, centre acquisition or full-field search, confirmation, predictive
following, local recovery and loss handling. **Physical moving-player tracking
and end-to-end delay have not yet been validated.** The simulator uses an ideal
point reflector and cannot establish how accurately ultrasound follows a body.

The current hardware is two Freenove ESP32-WROOM-32E boards with an HC-SR04 and
positional servo on each. Every box uses the same pins:

| Signal | ESP32 GPIO |
| --- | --- |
| Servo signal | 33 |
| HC-SR04 TRIG | 32 |
| HC-SR04 ECHO, wired directly (sensor powered from 3V3, no divider) | 34 |
| Buzzer +, **middle box only** (buzzer − to GND) | 25 |

The buzzer sounds while a player is in the dead zone or too close to a box; see
[the buzzer section of the live setup](docs/live-tracker-setup.md#buzzer).

Measure the mounting geometry and calibrate the servo direction, travel and
loaded settling time before running a sweep.

For the current 30–150° servo limits, follow the [first live test guide](docs/first-live-test.md)
using the dedicated farther-back test field.

## Try the single-spot display

Python 3.10+ with Tk is required. Linux may need `python3-tk`; no third-party
Python runtime libraries are required.

```bash
python3 -m whack --simulate
```

Wait for the simulated centre target to lock, then move the mouse within the
window. The simulator models servo settling, alternating pings and beam
visibility. A solid spot represents a measured estimate; a dim hollow spot
represents a short prediction. Missing, expired or out-of-field estimates are
hidden. There are no extra target dots, collision alarms or game zones.

| Control | Action |
| --- | --- |
| **C** | Calibrate the empty field in hardware mode |
| **Space / R** | Restart player acquisition using the selected start mode |
| **D** | Show sensor status, fix age, confidence and fresh measurement rate |
| **F11** | Toggle fullscreen |
| **Escape** | Close |

The screen polls at a 16 ms interval. Diagnostics report the observed display
refresh rate separately from fresh position updates; screen refresh is not
sensor measurement rate.

For diagnostics without a window:

```bash
python3 -m whack --simulate --headless --seconds 5
```

### Run the lock-scan sketch on the boxes (`--tracker sketch`)

The SEARCH/TRACK sketch runs **on each box, unchanged**, as the `lock_left`,
`lock_middle` and `lock_right` builds (`firmware/src/lockscan_main.cpp`: the
sketch plus Wi-Fi join and one UDP report line per ping and per pass). Each
box searches 0–180° in 3° steps at its own pace (40 ms settle + echo, about
15 pings/s), locks on the first echo nearer than 100 cm, scans ±15° round
the lock, and gives up after 4 empty passes. Boxes never wait for each other
and the laptop never commands them: it listens on UDP 4210 and draws the
fusion of every locked box.

```bash
~/.platformio/penv/bin/pio run -d firmware -e lock_left -t upload    # then lock_middle, lock_right
python3 -m whack --config config.local.json --tracker sketch --nodes IP0 IP1 IP2
python3 -m whack --config config.local.json --simulate --tracker sketch
```

`--nodes` makes the laptop HELLO each box so it learns where to report; a
box also broadcasts HELLO every 2 s until the laptop answers. There is no
calibration or background map in this mode: a wall or the next box nearer
than 100 cm locks a box exactly as the sketch would. The simulation runs a
line-for-line Python twin of the sketch per box (`whack/sketch.py`).

### Try the laptop-driven lock-scan tracker

`--tracker lock` runs the search → lock → window-scan algorithm from the
single-box Arduino sketch (`whack/lockscan.py`), one state machine per box, on
the same spot display:

```bash
python3 -m whack --simulate --tracker lock
python3 -m whack --config config.local.json --tracker lock --nodes IP0 IP1 IP2
```

Each box sweeps its arc in 3° steps until an echo inside `reliable_range_m`
locks it, then scans ±15° around the lock in 3° steps, one direction then the
other. Echoes within 0.25 m of the locked range are hits; a pass ends with the
lock at the mean hit bearing and a smoothed range. Four empty passes in a row
send the box back to searching from the lock. The spot fuses every locked box
(hollow when only one is locked). Press **D** to see each box's beam, its
window × range acceptance band and its locked point. Tune with
`lock_step_deg`, `lock_window_deg`, `lock_max_jump_m` and `lock_lost_limit`
in the config; the empty-room calibration is shared with the swarm tracker.

## Prepare and upload both ESP32s

The user uploads firmware manually. Preparing the Arduino folders or starting
the Python application does not flash a board.

1. Wire each ESP32, servo and HC-SR04 using [firmware setup](firmware/README.md).
2. Run `python3 -m tools.prepare_tracker_firmware --network tracker` from the
   project root to prepare both boards for their own **TrackerNet** Wi-Fi.
   Open the generated sketches in Arduino IDE. With three boxes use
   `tracker_left`, `tracker_middle` and `tracker_right` (nodes 0, 1, 2). With two
   boxes use `tracker_left` and `tracker_right_pair` (nodes 0, 1).
3. Check each servo's calibration in `tracker_config.h`. The generated
   `tracker_network.h` tab contains the shared TrackerNet password. Select
   **ESP32 Dev Module**, then manually upload the
   each sketch to the box at its position. Existing local config
   files are preserved when regenerating the folders.
4. Both boards must run the new **WM2 AIM/FIRE** firmware. The previous WM1
   tracker and standalone USB/OneNet tests do not provide this workflow.
5. Open Serial Monitor at **115200 baud** and note each node's IP address.

See the [live tracker setup guide](docs/live-tracker-setup.md) for the detailed
upload and mounting sequence. PlatformIO remains available as an alternative;
`pio run` compiles without uploading.

### Connect to TrackerNet

Boot the left ESP32 first: it creates a password-protected **TrackerNet** access
point at `192.168.4.1`. The right ESP32 joins automatically. On the laptop,
select **TrackerNet** in Wi-Fi settings and enter the password from the generated
`tracker_network.h` tab. Stay connected if the laptop reports no internet.

The laptop and right board receive their addresses automatically. The right
board's address is **not guaranteed to be `192.168.4.2`**; read its Serial Monitor
if an address is needed. This network can be used at home or school without
changing either environment's saved credentials.

Start the regular visualizer after joining; both nodes should be discovered:

```bash
python3 -m whack --config config.local.json
```

If discovery fails, replace `ACTUAL_RIGHT_IP` with the right board's serial IP:

```bash
python3 -m whack --config config.local.json --nodes 192.168.4.1 ACTUAL_RIGHT_IP
```

### Retained home and school profiles

Keep both environments configured in the local firmware settings:

| `WIFI_PROFILE` | Network |
| --- | --- |
| `0` | Home network: `WIFI_SSID` and `WIFI_PASSWORD` |
| `1` | School local network/hotspot: `SCHOOL_WIFI_SSID` and `SCHOOL_WIFI_PASSWORD` |
| `2` | Optional Macquarie OneNet PEAP credentials |
| `3` | TrackerNet: left ESP32 creates Wi-Fi; right ESP32 and laptop join |

`--network tracker` generates a shared random private password and selects
profile 3 through `tracker_network.h`; it preserves both `tracker_config.h`
files. Running the generator without `--network` preserves the selection. To
return to the profile selected in each existing `tracker_config.h`, run:

```bash
python3 -m tools.prepare_tracker_firmware --network configured
```

This removes the generated network override. Manually upload both matching
sketches after changing network mode. Preparing files does not connect to,
restart or upload either board.

For development at school, use a reachable 2.4 GHz local network shared by the
laptop and both ESP32s. Internet access is not required. OneNet troubleshooting
is deferred; its earlier successful ping does not establish tracker UDP support.
The optional enterprise profile requires Arduino-ESP32 3.3+ with certificate
and server-name verification support; the older PlatformIO core cannot use it.

## Start a real tracking session

1. Mount both sensors at the same torso height and depth with horizontal beams.
   Default acoustic centres are `(0, 0.20)` and `(1.50, 0.20)` metres. The default
   field runs from `x=0` to `1.50` and `y=0.60` to `2.00`, with the wall at `y=0`.
2. Copy `config.example.json` to `config.local.json` and enter actual geometry,
   range corrections and tracking limits.
3. Join **TrackerNet** on the laptop, or use the selected home/school network
   that allows communication between clients. The laptop receives on UDP 4210
   and the boards on UDP 4211.
4. Start the visualizer:

```bash
python3 -m whack --config config.local.json
```

5. Clear the whole field and press **C**. Stay out during the lead-in and dense
   background sweep. Each calibrated direction is sampled repeatedly; the
   status reports progress.
6. Stand briefly at the field centre. The default `center` mode confirms two
   consistent foreground pairs before showing a tracked position. Press
   **Space / R** to restart acquisition when needed.
7. Move slowly first. Watch the spot and use **D** to inspect measurement age,
   confidence and accepted update rate.

To begin with a search across the field:

```bash
python3 -m whack --config config.local.json --start-mode search
```

Full-field acquisition can take longer than tracking an established target. The
search covers the configured beam model; actual human echoes need physical tests.

If broadcast discovery is unavailable, use the IPs from Serial Monitor:

```bash
python3 -m whack --config config.local.json --nodes 192.168.1.101 192.168.1.102
```

Background profiles are stored in `calibration.local.json`. Recalibrate after
moving either sensor, changing the scene or changing geometry/settings that
invalidate the profile. Old profiles from the earlier sparse workflow must be
recreated. A timeout echo means no return, not proof of a healthy sensor; test
each unit against a flat target before calibration.

Use `--record tracking.csv` to log position, state, prediction flag, fix age,
confidence and update rate. Only run one controller or hardware probe at a time.
A node probe moves a real servo; see the setup guide before using it.

## How the workflow works

```text
Empty-field calibration → Find → Confirm → Track
                                   ↑        ↓
                                   └── Local search
                                            ↓
                                           Lost → Find
```

The laptop sends **AIM** to both nodes so their motors can move concurrently.
Once the servos report **READY**, it authorizes **FIRE** on one sensor at a time,
with a quiet interval between ultrasound transmissions. A short-lived firing
permission and sequence checks prevent a delayed/repeated command from becoming
an extra queued measurement. An unchanged settled bearing has no new movement
wait. Network loss or uncertain firing completion can lengthen a cycle.

Two corrected ranges define the forward intersection of two circles. Beam,
background, timing and movement checks reject inconsistent pairs. An alpha-beta
filter estimates position and velocity; it aligns staggered ranges using the
motion estimate and predicts the next aiming point. Brief misses trigger a
bounded nearby search. The spot's extrapolation expires before a prolonged loss
can leave a stale marker visible; wider acquisition then resumes.

See [the workflow and position equations](docs/player-tracking-workflow.md).
For a function-by-function explanation, read the [tracker code guide](docs/tracker-code-guide.md).
Two broad beams can return from different body surfaces or furniture. This is an
approximate single-player position estimate, not human recognition or a measured
body centre. Confidence is a software consistency score, not a calibrated
probability of accuracy.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 -m whack --simulate --headless --seconds 5
```

Firmware compilation and native protocol checks are described in
[firmware setup](firmware/README.md). The Python suite includes a loopback UDP
test requiring local socket access. These checks cover software behavior and
synthetic movement; they do not validate wiring, real servo travel, radio delay,
ultrasonic crosstalk or reflections from a moving person.

Before reporting live-tracking performance, measure accepted update rate,
position error, acquisition/recovery times, loss frequency and visible latency
with both physical units. No measured tracking rate or latency is claimed here.

The supplied `example-code/` retains its upstream license; see
`example-code/UPSTREAM.md`. Tracker code is in `whack/`.



mkdir -p results
python3 -m whack --config config.test-field.json --calibration calibration.test-field.local.json --record results/first-live-test.csv