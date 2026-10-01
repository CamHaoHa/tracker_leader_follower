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

The title and the built-in defaults describe the original two-box layout. The
**three-box prototype** adds a middle box (left, middle, right are nodes 0, 1,
2) and is run with the default swarm tracker and the tracked
`config.prototype.json`; see [Run on another computer](#run-on-another-computer).

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
| **Space** | Search: start or restart finding the player |
| **P** | Pause / resume |
| **R** | Reset: stop and forget the player (press **Space** to search again) |
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

## Prepare and upload the ESP32s

The user uploads firmware manually. Preparing the Arduino folders or starting
the Python application does not flash a board.

1. Wire each ESP32, servo and HC-SR04 using [firmware setup](firmware/README.md).
2. Run `python3 -m tools.prepare_tracker_firmware` from the project root, then
   open the generated sketches in Arduino IDE. With three boxes use
   `tracker_left`, `tracker_middle` and `tracker_right` (nodes 0, 1, 2). With two
   boxes use `tracker_left` and `tracker_right_pair` (nodes 0, 1).
3. In each sketch's `tracker_config.h`, enter the phone hotspot's name and
   password as `WIFI_SSID` and `WIFI_PASSWORD` and check the servo calibration.
   Select **ESP32 Dev Module**, then manually upload each sketch to the box at
   its position. Existing local config files are preserved when regenerating
   the folders.
4. Every board must run the current **WM2 AIM/FIRE** firmware. The previous WM1
   tracker and the standalone USB sensor sketches do not provide this workflow.
5. Open Serial Monitor at **115200 baud**. Each board prints the hotspot name it
   will join and, once connected, `Node n ready at <IP>:4211`.

See the [live tracker setup guide](docs/live-tracker-setup.md) for the detailed
upload and mounting sequence. PlatformIO remains available as an alternative;
`pio run` compiles without uploading.

### Network: one phone hotspot

The laptop and every box join **one phone hotspot** (WPA2-personal). It is the
only supported network: the home, university and TrackerNet setups were removed
on 2026-10-01, and the firmware has no network profiles any more.

- The ESP32 radio is **2.4 GHz only**. On an iPhone turn on **Maximise
  Compatibility** and keep the Personal Hotspot screen open while the boxes join.
- An iPhone's default hotspot name contains a typographic apostrophe (U+2019).
  In the firmware config write it as the UTF-8 bytes `\xE2\x80\x99`, for example
  `"Sam\xE2\x80\x99s iPhone"`.
- No IP address is entered anywhere. Every box broadcasts `WM2 HELLO <node>` to
  UDP 4210 every two seconds; the laptop listens there and finds the boxes. The
  boxes receive their commands on UDP 4211.

Start the three-box prototype once the laptop is on the hotspot:

```bash
python3 -m whack --tracker swarm --config config.prototype.json
```

`--nodes` is an optional override for a network that blocks broadcast. Give the
addresses from Serial Monitor, left to right:

```bash
python3 -m whack --tracker swarm --config config.prototype.json --nodes LEFT_IP MIDDLE_IP RIGHT_IP
```

## Run on another computer

The boxes keep their firmware; only the laptop changes. The field setup of the
three-box prototype travels with the repository in `config.prototype.json`.

1. Clone this repository and check out the branch that holds
   `config.prototype.json`. Until that work is merged into `main`, run
   `git checkout leader-follower-tracking-2` after cloning.
2. Install **Python 3.10 or newer with tkinter**. The tracker needs no pip
   packages.
   - Debian/Ubuntu: `sudo apt install python3-tk`.
   - Windows: the python.org installer includes tkinter. Start Python as `py`
     (or `python`) instead of `python3`.
   - macOS: the python.org installer includes tkinter. A Homebrew Python needs
     `brew install python-tk`.
3. Join the **same phone hotspot** as the boxes.
4. Allow **incoming UDP 4210** in the firewall. The boxes announce themselves
   on that port.
   - Linux with ufw: `sudo ufw allow 4210/udp`.
   - Windows: on the first run, accept the Windows Defender Firewall prompt
     for Python and tick the network type the hotspot is listed as (tick both
     private and public if unsure).
   - macOS: if the firewall is on, allow incoming connections for Python when
     the system asks.
5. From the project root, run (`py -m whack ...` on Windows):

   ```bash
   python3 -m whack --tracker swarm --config config.prototype.json
   ```

6. Press **D**. Within a few seconds every box should read `Connected <IP>`.
7. Press **C** once with the field empty. The empty-field calibration is stored
   per computer in `calibration.local.json`, which Git ignores, so a new
   computer has none. Then press **Space** to start tracking.

If a box stays `offline` under **D**, or the status stays at `Waiting for
sensors: n of 3 online` after **Space**, its announcements are not reaching the
laptop. Check that the laptop is on the hotspot and that the firewall lets UDP
4210 in, or pass `--nodes` as shown in
[Network: one phone hotspot](#network-one-phone-hotspot).

`config.local.json` is an optional personal override that Git ignores. Use it
for a different layout with `--config config.local.json`; start it as a copy of
`config.prototype.json` or `config.example.json`.

## Start a real tracking session

1. Mount the sensors at the same torso height and depth with horizontal beams.
   The three-box prototype mounts all three on the line `y = 0.50` metres, at
   `x = 0`, `0.75` and `1.50`, as in the tracked `config.prototype.json`. The
   acoustic centres `(0, 0.20)` and `(1.50, 0.20)` are the built-in two-box
   defaults, used only when no `--config` is given. In both, the field runs
   from `x=0` to `1.50` and `y=0.60` to `2.00`, with the wall at `y=0`.
2. For a different layout, copy `config.example.json` to `config.local.json`
   (ignored by Git), enter the actual geometry, range corrections and tracking
   limits, and pass `--config config.local.json` instead of
   `--config config.prototype.json`.
3. Join the phone hotspot on the laptop. The laptop receives on UDP 4210 and the
   boards on UDP 4211.
4. Start the visualizer:

```bash
python3 -m whack --tracker swarm --config config.prototype.json
```

5. Clear the whole field and press **C**. Stay out during the lead-in and dense
   background sweep. Each calibrated direction is sampled repeatedly; the
   status reports progress. When it has finished, press **Space** to search.
6. Step into the field. The swarm tracker sweeps every box until one sees the
   player, then aims the others at that estimate. Press **Space** to search
   again when needed.
7. Move slowly first. Watch the spot and use **D** to inspect measurement age,
   confidence and accepted update rate.

The older paired two-box tracker confirms a player at the field centre first.
It can begin with a search across the field instead (`--start-mode` has no
effect on the swarm tracker):

```bash
python3 -m whack --tracker pairs --config config.local.json --start-mode search
```

Full-field acquisition can take longer than tracking an established target. The
search covers the configured beam model; actual human echoes need physical tests.

If broadcast discovery is unavailable, add `--nodes` with the IPs from Serial
Monitor, left to right:

```bash
python3 -m whack --tracker swarm --config config.prototype.json --nodes LEFT_IP MIDDLE_IP RIGHT_IP
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