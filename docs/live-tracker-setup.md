# Two servos, two sensors, one on-screen dot

This stage tracks one person and renders a cyan position dot on a black screen.
Game logic is outside the current scope. Distance accuracy/reliability testing is
paused; previous Excel results and raw evidence are retained.

## TrackerNet at home or school

Profile 3 lets the two trackers provide their own local Wi-Fi. The left ESP32
creates the WPA2-protected **TrackerNet** access point at `192.168.4.1` on the
`192.168.4.0/24` network. The right ESP32 and laptop join it and receive addresses
automatically. Internet access is not needed.

Prepare both matching sketches with:

```bash
python3 -m tools.prepare_tracker_firmware --network tracker
```

The generator creates the shared random private password in the generated
`tracker_network.h` file, visible as a tab in Arduino IDE. Use that password
when joining TrackerNet on the laptop. Preparation only writes files; manually
upload both boards using the steps below.

After uploading, boot the left board first. The right board joins automatically.
Select **TrackerNet** in the laptop's Wi-Fi settings and stay connected when the
operating system reports no internet. Start the visualizer normally:

```bash
python3 -m whack --config config.local.json
```

Discovery finds the boards automatically. The right board's DHCP address is not
fixed at `192.168.4.2`; check its Serial Monitor if needed. For manual discovery,
replace `ACTUAL_RIGHT_IP` with that address:

```bash
python3 -m whack --config config.local.json --nodes 192.168.4.1 ACTUAL_RIGHT_IP
```

This network mode is implemented for testing; connection stability and physical
tracking still need verification with both boards.

## Retained home and school networks

The user works at both home and Macquarie University. Preserve support for both
environments and retain the home connection when adding school support. The
tracker retains selectable home (`WIFI_PROFILE=0`), school personal Wi-Fi/hotspot
(`1`), optional OneNet PEAP with certificate verification (`2`), and TrackerNet
(`3`) profiles. Home and school credentials remain in `tracker_config.h` when
the generated `tracker_network.h` override selects TrackerNet. A normal generator
run preserves the selection. To remove that override and use the profile from
the existing `tracker_config.h` files, run
`python3 -m tools.prepare_tracker_firmware --network configured`, then manually
upload both sketches. Fill the desired home/school values before those uploads.
The optional OneNet branch requires Arduino-ESP32 3.3+; OneNet troubleshooting
remains deferred. The user uploads sketches manually; preparation and laptop
software never automatically flash either board.

On 15 September 2026, the left ESP32's Serial Monitor showed a stable Macquarie
OneNet connection at `10.126.113.137`. A laptop ping test received 4/4 replies,
with 0% packet loss and a mean round trip of 55.101 ms. This verifies basic IP
reachability; it does not verify tracker commands, UDP discovery, or readings.
The address may change after reconnection.

The deferred standalone OneNet communication check uses
`firmware/arduino/onenet_udp_test/onenet_udp_test.ino`, then wait for `UDP READY`
in Serial Monitor at 115200 baud. Use the displayed IP with:

```bash
python3 -m tools.probe_network --ip 10.126.113.137
```

This exchanges five challenge/reply messages on the tracker ports (laptop UDP
4210, ESP32 UDP 4211). It does not move the servo or trigger the sensor. The
locally configured OneNet sketch folders are ignored by Git because they contain
credentials. The first UDP sketch uploads failed before obtaining an IP address:
the user's Serial Monitor screenshots showed reason 23 (`802_1X_AUTH_FAILED`),
then reasons 3 (`AUTH_LEAVE`) and 2 (`AUTH_EXPIRE`) after a restart. UDP replies
have not been tested on hardware. Diagnostic version `ONENET UDP TEST v2` waits
for station startup, reads the driver MAC, selects the strongest scanned
enterprise access point, and prints the certificate-check clock. It preserves
certificate verification; the cause of the failed login remains unconfirmed.

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

Power each HC-SR04 from the ESP32 3V3 pin and wire ECHO straight to GPIO34:
there is no divider. GPIO34 is input-only and has no internal pull resistors.
A sensor powered from 5 V must not be wired this way, because its ECHO would
be a 5 V signal. Keep the shared grounds from the bench setup. Supply the servo
from its rated external supply. The ESP32 3.3 V pin is not a servo power supply.
A continuous-rotation servo cannot use this positional control scheme.

The default field is 1.50 m wide, with its near edge 0.60 m and far edge 2.00 m
from the screen wall. The left sensor's acoustic centre is `(0.00, 0.20)` m and
the right sensor's centre is `(1.50, 0.20)` m. Mount at the same height, aimed
horizontally toward the torso. Measure your actual layout and set
`config.local.json`; positions are metres, not centimetres.

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

## Upload both tracking sketches in Arduino IDE

From the project root, prepare the Arduino folders:

```bash
python3 -m tools.prepare_tracker_firmware --network tracker
```

The generator copies the maintained firmware into three independent Arduino sketch
folders named by box position: left (node 0), middle (node 1) and right (node 2),
plus right_pair (node 1) for the right box of a two-box layout, and preconfigures them for the same TrackerNet access point. Re-running
the generator without a network argument refreshes code while retaining your
configuration and selected network mode. That also means an existing
`tracker_config.h` keeps the pins it was created with: if it still says servo 25
and ECHO 35, change its `SERVO_PIN`, `ULTRASONIC_TRIG_PIN` and
`ULTRASONIC_ECHO_PIN` lines to 33, 32 and 34 by hand.

1. Open `firmware/arduino/tracker_left/tracker_left.ino` in Arduino IDE.
2. Check the servo settings in `tracker_config.h`. The `tracker_network.h` tab
   contains the generated TrackerNet password used by both boards and the laptop.
   Keep it local; the generated folders are ignored by Git.
3. Select **ESP32 Dev Module**, select the left board's USB port, and upload.
4. Three boxes: upload `tracker_middle` (node 1) to the middle board and
   `tracker_right` (node 2) to the right board. Two boxes: upload
   `tracker_right_pair` (node 1) to the right board. Each generated network tab
   already matches the left board.
5. Open Serial Monitor at **115200 baud**. Each board should print
   `Node 0 ready at ...:4211`, `Node 1 ready ...` or `Node 2 ready ...`. Boot left
   first and note each other board's assigned IP address. Pass the addresses to
   `--nodes` in left-to-right order.

Every sketch must be regenerated and uploaded for the WM2 AIM/FIRE workflow.
The sketches have distinct node IDs. Upload each one to the box at its
position. The old `sensor_test.ino` only prints USB distance readings; it
cannot receive aiming commands from the tracker.

Join **TrackerNet** on the laptop using the generated password. The PC and both
boards must share a local network that permits communication
between clients. The host receives on UDP 4210; nodes receive on UDP 4211. Nodes
announce themselves automatically. Fixed-IP sessions also use a unicast discovery
query so they can work without broadcast delivery. A phone hotspot or guest network may isolate
clients; use a network where the devices can reach each other.

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
(replace the example address with its Serial Monitor address):

```bash
python3 -m tools.probe_node --ip 192.168.1.101 --node 0 --angle 90 --count 3
```

Close other controllers while using the probe. If changing computers/controllers,
allow the previous controller's 30-second idle timeout before taking ownership.

## Start the screen and empty-area scan

`config.local.json` contains the local geometry. The supplied defaults are the
positions above; adjust them before scanning if the sensor spacing is different.

```bash
python3 -m whack --config config.local.json
```

1. Wait for both nodes to connect.
2. Clear the entire area, then click **Calibrate empty area (C)**. The servos scan
   a dense set of bearings and measure the background. Stay out until scanning finishes.
   This background scan is required even while distance-accuracy tests are deferred.
   The dense sweep includes every search bearing and fills gaps to at most the
   configured calibration step (default 3 degrees), with three pairs per step.
   Existing sparse calibration profiles must be recreated for this version.
3. Stand briefly in the centre. Two consistent foreground range pairs confirm
   the player before the first spot appears. **Space / R** restarts acquisition;
   `--start-mode search` starts with a full-field search.
4. A cyan dot follows the position estimate. A dim hollow spot marks short
   prediction between readings or during a brief echo loss. Prediction expires
   after 0.20 seconds by default. The sensors search locally for up to 0.50
   seconds from the last fix, then resume a wider search. Missing or out-of-field
   estimates do not leave an old dot behind.
5. Press **D** for fresh measurement rate, fix age and confidence,
   **F11** for fullscreen, and **Escape** to close.

If automatic discovery fails on TrackerNet, replace `ACTUAL_RIGHT_IP` below with
the right board's address from Serial Monitor. On a home or school network, use
both addresses from Serial Monitor instead:

```bash
python3 -m whack --config config.local.json --nodes 192.168.4.1 ACTUAL_RIGHT_IP
```

The empty-area profile is stored as `calibration.local.json`. Repeat the scan after
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
