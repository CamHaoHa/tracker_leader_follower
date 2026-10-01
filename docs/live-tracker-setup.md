# Two servos, two sensors, one on-screen dot

This stage tracks one person and renders a cyan position dot on a black screen.
Game logic is outside the current scope. Distance accuracy/reliability testing is
paused; previous Excel results and raw evidence are retained.

## Network: one phone hotspot

The laptop and every box join **one phone hotspot** (WPA2-personal). It is the
only supported network. The firmware has no network profiles, no board acts as
an access point, and the university network is not used. The hotspot was
used for the bench session of 23 September 2026
([bench log](mvp1-bench-log-2026-09-23.md)).

Set the hotspot up once:

1. On the phone, turn on the hotspot. The ESP32 radio is **2.4 GHz only**: on an
   iPhone turn on **Maximise Compatibility** and keep the Personal Hotspot
   screen open while the boxes join.
2. Enter the hotspot's name and password as `WIFI_SSID` and `WIFI_PASSWORD` in
   each `tracker_config.h` (Arduino IDE) or in `firmware/include/config.local.h`
   (PlatformIO), then upload manually using the steps below. An iPhone's default
   name contains a typographic apostrophe (U+2019): write it as the UTF-8 bytes
   `\xE2\x80\x99` inside the C string, for example `"Sam\xE2\x80\x99s iPhone"`.
3. Join the same hotspot on the laptop and allow incoming UDP 4210 in its
   firewall.

Every box broadcasts `WM2 HELLO <node>` to UDP 4210 every two seconds. The
laptop listens on UDP 4210 and discovers the boxes from those announcements;
the boxes receive commands on UDP 4211. No IP address is entered anywhere.
Start the three-box prototype normally:

```bash
python3 -m whack --tracker swarm --config config.prototype.json
```

`--nodes` is an optional override for a network that blocks broadcast. Give the
addresses each box prints in Serial Monitor, left to right:

```bash
python3 -m whack --tracker swarm --config config.prototype.json --nodes LEFT_IP MIDDLE_IP RIGHT_IP
```

The user uploads sketches manually; preparation and laptop software never
flash a board. To run the tracker from a different laptop, see
[Run on another computer](../README.md#run-on-another-computer).

## Hardware arrangement

Use two or three independent units, each with one classic ESP32 board (Freenove
ESP32-WROOM-32E with CH340, or ELEGOO ESP-WROOM-32 with CP2102; same GPIO map),
one positional pan servo and one HC-SR04 fixed to the servo. All use these GPIO
numbers:

| Signal | ESP32 GPIO |
| --- | --- |
| Servo signal | 33 |
| HC-SR04 TRIG | 32 |
| HC-SR04 ECHO, wired directly | 34 |
| Buzzer +, middle box only | 25 |

Power each HC-SR04 from the ESP32 3V3 pin and wire ECHO straight to GPIO34:
there is no divider. GPIO34 is input-only and has no internal pull resistors.
A sensor powered from 5 V must not be wired this way, because its ECHO would
be a 5 V signal. Keep the shared grounds from the bench setup. Supply the servo
from its rated external supply. The ESP32 3.3 V pin is not a servo power supply.
A continuous-rotation servo cannot use this positional control scheme.

The field is 1.50 m wide, with its near edge 0.60 m and far edge 2.00 m from
the screen wall. Mount the sensors at the same height, aimed horizontally toward
the torso. Which sensor line applies depends on the config in use:

- **Three-box prototype** (`--config config.prototype.json`, tracked): three
  sensors at `x = 0`, `0.75` and `1.50` on the line `y = 0.50` m.
- **Built-in two-box defaults** (no `--config`): the left sensor's acoustic
  centre is `(0.00, 0.20)` m and the right sensor's is `(1.50, 0.20)` m.

Measure your actual layout and record it in a config file; positions are metres,
not centimetres. `config.local.json` is an optional personal override that Git
ignores, used with `--config config.local.json`.

The diagram shows the built-in two-box defaults:

```text
                  Screen wall (y = 0)
       Left sensor                   Right sensor
        (0, 0.20)                    (1.50, 0.20)
             \                         /
              \     playing area      /
               y = 0.60 to 2.00 metres
```

The 200 cm limit belongs to the earlier bench sketch. Tracking firmware accepts
up to 400 cm, because a diagonal path across the default field is approximately
234 cm. The desktop application filters positions to the configured play area.

## Buzzer

The middle box (node 1) carries a buzzer that warns a player who is too close
to the screen wall. No other box has one.

| Buzzer lead | Middle box |
| --- | --- |
| + | GPIO25 |
| − | GND |

A GPIO pin supplies only a small current (about 20 mA). A piezo buzzer or a
buzzer module with its own transistor can be wired as above; anything that
draws more needs a transistor between the pin and the buzzer.

**What makes it sound.** With `"buzzer_node": 1` in the config file (it is set
in `config.prototype.json`), the
default swarm tracker sounds the buzzer while the banner shows **Player in the
dead zone** or **Player too close to box n**. The sound follows the banner,
which stays up for at least 2 s after the last such reading. A box that goes
offline, or reports nothing for 1.5 s, no longer counts as reporting a player
too close, so a box that drops out cannot keep the sound going. It is silent for
*Player outside the field* and *Two players detected*, while paused and during
calibration. Leave `buzzer_node` out, or set it to `-1`, for no buzzer. The
older `--tracker pairs` never sounds it. With three boxes node 1 is the middle
box; a two-box layout has no middle box and its node 1 is the right box.

**Failsafe.** While the alert lasts the laptop sends `WM2 BUZZ 400` every 0.2 s,
then `WM2 BUZZ 0` once. Each command only moves the box's own deadline, and the
box silences itself when that deadline passes. One command can ask for at most
2 s, so a laptop that crashes or leaves the network cannot leave the buzzer
sounding.

**Passive or active buzzer.** The firmware default, `BUZZER_TONE_HZ 2000`, drives
a passive buzzer with a 2000 Hz square wave. An active buzzer has its own
oscillator: set `#define BUZZER_TONE_HZ 0` in `config.local.h` (PlatformIO) or
the middle sketch's `tracker_config.h` (Arduino IDE) and upload the middle box
again. The pin is then held HIGH while sounding.

`BUZZER_PIN 25` is set for node 1 by `config.example.h` and by a newly generated
`tracker_middle/tracker_config.h`; add `#define BUZZER_PIN 25` by hand to a
config file that already exists. At boot the middle box prints
`Buzzer: pin=25, 2000 Hz tone` and every other box prints `Buzzer: none`.

A box that prints no `Buzzer:` line at all runs firmware from before the buzzer
existed. It drops `WM2 BUZZ` without a sound. Such a build has the same pins and
tracks normally, so it may stay on the left and right boxes, but the middle box
needs the current firmware: build `node_middle` from this repository's
`firmware/` directory, with the `BUZZER_PIN` block in its `config.local.h`.

In a two-box layout node 1 is the right box, and the two build paths differ:
the PlatformIO `node_right_pair` build drives GPIO25, because `config.example.h`
sets the pin for node 1, while a generated `tracker_right_pair/tracker_config.h`
has no `BUZZER_PIN`. Add `#define BUZZER_PIN 25` to that file if a two-box right
box is to carry the buzzer. With nothing wired to GPIO25 neither is audible.

To hear it without the tracker, close the visualizer (it owns UDP 4210) and
send one second of sound from the project root, replacing `MIDDLE_BOX_IP`:

```bash
python3 -c "import socket; from whack.protocol import buzz; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('0.0.0.0', 4210)); s.sendto(buzz(1000), ('MIDDLE_BOX_IP', 4211))"
```

**Check that the sound does not disturb the sensor.** This has not been
measured yet. The buzzer is on the same box as an HC-SR04, and a 2000 Hz
square wave has harmonics near the sensor's 40 kHz. A false short range while
the buzzer sounds could keep a *too close* alert, and so the sound, alive. With
the visualizer closed and a fixed target about 1 m in front of the middle box,
probe it silent and then sounding:

```bash
python3 -m tools.probe_node --ip MIDDLE_BOX_IP --node 1 --angle 90 --count 20
python3 -m tools.probe_node --ip MIDDLE_BOX_IP --node 1 --angle 90 --count 20 --buzz
```

`--buzz` sounds the buzzer for the whole run and silences it at the end. The
two summaries should agree: the same number of valid readings, and a median
inside the range the silent run printed. Repeat with nothing in front of the box; the
sounding run must not report a range where the silent run reports `TIMEOUT`. If
the runs differ, lower `BUZZER_TONE_HZ`, or move the buzzer away from the
sensor, and check again.

## Upload the tracking sketches in Arduino IDE

From the project root, prepare the Arduino folders:

```bash
python3 -m tools.prepare_tracker_firmware
```

The generator copies the maintained firmware into independent Arduino sketch
folders named by box position: left (node 0), middle (node 1) and right (node 2),
plus right_pair (node 1) for the right box of a two-box layout. Re-running the
generator refreshes code while retaining your configuration. That also means an
existing `tracker_config.h` keeps what it was created with:

- If it still says servo 25 and ECHO 35, change its `SERVO_PIN`,
  `ULTRASONIC_TRIG_PIN` and `ULTRASONIC_ECHO_PIN` lines to 33, 32 and 34 by hand.
- If it still sets `WIFI_PROFILE`, `SCHOOL_WIFI_*`, `TRACKER_WIFI_*` or
  `ONENET_*`, the sketch stops compiling with `Network profiles were removed`.
  Move the hotspot name and password into `WIFI_SSID` and `WIFI_PASSWORD` by
  hand and delete those lines. An old `tracker_network.h` tab is no longer used.

1. Open `firmware/arduino/tracker_left/tracker_left.ino` in Arduino IDE.
2. In `tracker_config.h`, enter the phone hotspot as `WIFI_SSID` and
   `WIFI_PASSWORD` and check the servo settings. Keep the file local; the
   generated folders are ignored by Git.
3. Select **ESP32 Dev Module**, select the left board's USB port, and upload.
4. Three boxes: upload `tracker_middle` (node 1) to the middle board and
   `tracker_right` (node 2) to the right board. Two boxes: upload
   `tracker_right_pair` (node 1) to the right board. Every `tracker_config.h`
   needs the same hotspot name and password.
5. Open Serial Monitor at **115200 baud**. Each board prints
   `Wi-Fi: will join "<name>" (phone hotspot, 2.4 GHz)` at boot and, once
   connected, `Node 0 ready at ...:4211`, `Node 1 ready ...` or `Node 2 ready ...`.
   The boxes can be powered in any order.

Every sketch must be regenerated and uploaded for the WM2 AIM/FIRE workflow.
The sketches have distinct node IDs. Upload each one to the box at its
position. The old `sensor_test.ino` only prints USB distance readings; it
cannot receive aiming commands from the tracker.

Join the phone hotspot on the laptop. The host receives on UDP 4210; nodes
receive on UDP 4211. Nodes announce themselves automatically. Sessions started
with `--nodes` also use a unicast discovery query, so they can work without
broadcast delivery.

## Centre the mounts

**Current SG90 test:** both boards have a provisional corrected angle scale
with temporary 30–150 degree test limits, based on the user's half-angle
measurement. Follow [the servo calibration check](servo-calibration.md) before
another empty-field sweep. Verify each servo's movement separately; copying
the settings does not establish the right servo's actual angle scale.

The firmware commands a forward bearing of 90 degrees on startup. Initially keep
the bracket free of obstructions. At that centre position, arrange the horn so
the sensor faces straight into the play area. Both units use the same world axes:
0 degrees is right along the wall, 90 degrees forward, 180 degrees left.

Servo model, actual travel, direction and power supply still need checking. Set
`SERVO_REVERSED` for a reversed installation and trim/endpoints in each
`tracker_config.h`. Default 1000–2000 microsecond pulses are only a starting point;
they do not establish a measured 180-degree sweep. See the detailed servo setup
in `firmware/README.md`.

Once the mounts are ready, the existing probe can aim one unit at 90 degrees
(replace `LEFT_BOX_IP` with its Serial Monitor address):

```bash
python3 -m tools.probe_node --ip LEFT_BOX_IP --node 0 --angle 90 --count 3
```

Close other controllers while using the probe. If changing computers/controllers,
allow the previous controller's 30-second idle timeout before taking ownership.

## Start the screen and empty-area scan

`config.prototype.json` contains the three-box prototype's geometry. If the
sensor spacing is different, copy it to `config.local.json`, adjust that copy
before scanning and pass `--config config.local.json` instead.

```bash
python3 -m whack --tracker swarm --config config.prototype.json
```

1. Wait for every node to connect: press **D** and check that each box reads
   `Connected <IP>`.
2. Clear the entire area, then press **C** (button **Calibrate (C)**). The servos scan
   a dense set of bearings and measure the background. Stay out until scanning finishes.
   This background scan is required even while distance-accuracy tests are deferred.
   The dense sweep includes every search bearing and fills gaps to at most the
   configured calibration step (default 3 degrees), with three pairs per step.
   Existing sparse calibration profiles must be recreated for this version.
3. When calibration has finished, the status reads `Calibration saved — press
   Search to track` and the tracker waits. Press **Space** (button **Search
   (Space)**) and step into the field: the swarm tracker sweeps every box until
   one sees the player, then aims the others at that estimate. **P** pauses and
   resumes. **R** stops and forgets the player; press **Space** to search again.
   `--start-mode` applies only to the older `--tracker pairs`.
4. A cyan dot follows the position estimate. A dim hollow spot marks short
   prediction between readings or during a brief echo loss. Prediction expires
   after 0.20 seconds by default. The sensors search locally for up to 0.50
   seconds from the last fix, then resume a wider search. Missing or out-of-field
   estimates do not leave an old dot behind.
5. Press **D** for fresh measurement rate, fix age and confidence,
   **F11** for fullscreen, and **Escape** to close.

If automatic discovery fails, pass the addresses from Serial Monitor, left to
right:

```bash
python3 -m whack --tracker swarm --config config.prototype.json --nodes LEFT_IP MIDDLE_IP RIGHT_IP
```

The empty-area profile is stored as `calibration.local.json` on this computer; Git
ignores it, so another computer needs its own scan. Repeat the scan after
moving sensors or furniture. Start later runs with the same command to reuse it.
No Wi-Fi credentials are needed in the Python application.

## Expectations for the first live run

The software implements scan, foreground filtering, aiming and dot rendering;
physical player tracking has not yet been demonstrated with these mounts. Two
broad ultrasonic beams can reflect off different body parts or furniture. Start
with one person, slow movement and an uncluttered field. Initial acquisition and
reacquisition can take a full sweep. Servo alignment and pulse-to-angle mapping
are required for the geometry to make sense, even before measuring accuracy.
The configured 20-degree beam half-angle is a model assumption, not a measured
HC-SR04 characteristic. A narrower effective beam requires a narrower setting and
more scan directions; geometric coverage does not guarantee useful echoes.

### Human width and scan gaps

The player has a finite body width, as the user highlighted. A torso can overlap
a sampled beam even when its centre falls in a gap of the point-target model, so
actual human width may improve acquisition. The size of this benefit depends on
distance, orientation, clothing and which surfaces return a useful echo; it is
not a measured property of this setup yet.

The two sensors may range to different body surfaces. Their circle intersection
is therefore an approximate player-position estimate, not a directly measured
body centre. Retain deliberate scan coverage and consistency checks rather than
assuming body width always fills a gap. The current simulator uses one ideal
point reflector and does not model torso width or establish human acquisition
performance. Human width is not yet measured or used as a calibration correction.

For a screen-only preview without moving hardware:

```bash
python3 -m whack --simulate
```

Mouse movement drives that preview. It does not test the physical sensors.
