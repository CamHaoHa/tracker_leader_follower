# First live test: two trackers and one spot

This test uses a **farther-back field** so the planned bearings fit the current
30–150° test limits on both mounts, with normal direction and zero trim. It does
not establish the servos' physical travel or prove that body tracking works.
Keep the original near-field configuration for later; its full background sweep
still exceeds these temporary limits.

## 1. Upload the matching firmware manually

1. Open `firmware/arduino/tracker_left/tracker_left.ino` in Arduino IDE.
2. Select **ESP32 Dev Module** and the left board's port; upload.
3. Open `firmware/arduino/tracker_right_pair/tracker_right_pair.ino` (node 1 in a two-box layout), select the right
   board's port and upload that sketch to it.
4. Open Serial Monitor at **115200 baud**. Each board prints the phone hotspot
   it will join and, once connected, `Node n ready at <IP>:4211`.
5. Note both boards' IPs for the probe commands below. The hotspot assigns them
   by DHCP, so they can change between sessions.
6. On the laptop, join the same phone hotspot.

Each sketch takes the hotspot name and password from `WIFI_SSID` and
`WIFI_PASSWORD` in its `tracker_config.h`; see the
[network section of the live setup](live-tracker-setup.md#network-one-phone-hotspot).
Preparation and the laptop application do not upload firmware automatically.

## 2. Check each servo's scale and forward direction

Close the visualizer before using a probe. Run one command at a time and watch
what the mount actually does. For the left unit, replace `ACTUAL_LEFT_IP` with
its Serial Monitor address:

```bash
python3 -m tools.probe_node --ip ACTUAL_LEFT_IP --node 0 --angle 90 --count 1
python3 -m tools.probe_node --ip ACTUAL_LEFT_IP --node 0 --angle 60 --count 1
python3 -m tools.probe_node --ip ACTUAL_LEFT_IP --node 0 --angle 90 --count 1
python3 -m tools.probe_node --ip ACTUAL_LEFT_IP --node 0 --angle 120 --count 1
python3 -m tools.probe_node --ip ACTUAL_LEFT_IP --node 0 --angle 90 --count 1
```

Repeat **90 → 60 → 90 → 120 → 90** on the right unit, replacing the IP with its
Serial Monitor address and using `--node 1`. For example, replace
`ACTUAL_RIGHT_IP` before running:

```bash
python3 -m tools.probe_node --ip ACTUAL_RIGHT_IP --node 1 --angle 90 --count 1
```

Both mounts use the same world directions: **90° forward into the field**, 0°
right along the wall, 180° left. At 90°, the sensors should face parallel and
straight forward. Each 30° command change should produce about 30° of physical
rotation and return to the same centre. Check with angle marks or a protractor;
the printed angle does not measure actual servo movement.

After central movement is correct, approach the endpoints gradually, observing
every step: **90 → 60 → 45 → 30 → 45 → 60 → 90 → 120 → 135 → 150 → 135 → 120 → 90**.
Stop if a mount binds, pushes against a stop or buzzes strongly. Do not continue
to the scan if travel or scale is wrong. See [servo calibration](servo-calibration.md).

Check each sensor against a flat target at a known distance, then a stationary
person. `TIMEOUT` means no usable echo, not a zero-distance measurement.

## 3. Place the units and mark this test field

Measure from the wall and each sensor's acoustic centre:

| Item | Position |
| --- | --- |
| Left sensor | `(x=0.00, y=0.20)` metres |
| Right sensor | `(x=1.50, y=0.20)` metres |
| Field width | `x=0.00..1.50` metres |
| Near and far field edges | `y=2.10..3.00` metres from the wall |
| Starting point | `(x=0.75, y=2.55)` metres |

The field is **1.90–2.80 m forward of the sensors**. Mount both at the same torso
height with horizontal beams. Keep brackets clear and place spectators outside
the beams. Each unit needs its sensor powered from 3V3 with ECHO wired directly
to GPIO34 (servo signal GPIO33, TRIG GPIO32), suitable servo power and shared
ground. The dedicated file is [config.test-field.json](../config.test-field.json).

This arrangement's planned sweep stays approximately within 32–148° under its
configured geometry. Verify the physical angles first; software coverage is not
proof that every position produces a usable body echo.

## 4. Start the screen and calibrate the empty field

From the project root:

```bash
mkdir -p results
python3 -m whack --config config.test-field.json --calibration calibration.test-field.local.json --record results/first-live-test.csv
```

If discovery fails, close the application and add the two IPs, replacing both
placeholders:

```bash
python3 -m whack --config config.test-field.json --calibration calibration.test-field.local.json --record results/first-live-test.csv --nodes ACTUAL_LEFT_IP ACTUAL_RIGHT_IP
```

Press **D** to show diagnostics. Wait for both sensors, clear the whole field,
then press **C**. Keep the field empty through the three-second lead-in and all
calibration steps. Wait for calibration to finish before walking in. An
`INVALID` or interrupted calibration needs its cause resolved before proceeding.
The separate calibration file keeps this layout apart from the original field.

## 5. Acquire, move slowly and record what happens

Stand briefly on the centre mark `(0.75, 2.55)`. Two consistent pairs are needed
before the spot appears. Press **Space/R** to restart finding if necessary. First
stand still, then walk slowly left/right and forward/back inside the marks.

A solid cyan spot is a recent estimate; a dim hollow spot is short prediction.
The spot should disappear when the estimate expires or leaves the field. Watch
**fresh position updates in Hz**, fix age and confidence; display FPS is a
separate redraw rate. Note dropouts, jitter and whether the spot follows the
correct direction. The CSV records the session; each launch overwrites that
filename, so rename it before another run if retaining both.

Send the diagnostics and CSV with your observations. Actual update rate,
position accuracy and visible delay remain physical test results to establish.
