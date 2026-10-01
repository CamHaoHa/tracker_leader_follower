# ESP32 sensor nodes

Each ESP32 controls **one positional servo carrying one trigger/echo ultrasonic
sensor**. Manually upload the build named after each box's position: `node_left`
(node 0), `node_middle` (node 1) and `node_right` (node 2) for three boxes, or
`node_left` and `node_right_pair` (node 1) for two. The laptop aims all motors concurrently, then
coordinates ultrasound transmissions in separate turns using **WM2 AIM/FIRE**.
A board never ranges on its own. The desktop displays one tracked spot and has
no gameplay logic.

The user's hardware is a Freenove ESP32-WROOM-32E board and HC-SR04 sensor per unit. PlatformIO uses its classic ESP32 DevKit target; Arduino IDE uses ESP32 Dev Module. ESP32-C3/S3 boards, continuous-rotation servos, and UART/I2C ultrasonic sensors need different configuration or drivers. Firmware builds and parser tests can be checked without hardware; actual tracking, servo travel, and electrical timing still need hardware verification.

## Connect each unit

| Signal | ESP32 connection |
| --- | --- |
| Servo control | GPIO33 |
| Ultrasonic TRIG | GPIO32 |
| Ultrasonic ECHO | GPIO34, **wired directly** (sensor powered from 3V3) |
| Ultrasonic ground | ESP32 ground |
| Servo ground | ESP32 ground and external supply ground |
| Servo power | Separate regulated supply rated for the servo voltage and stall current |
| HC-SR04 supply | ESP32 3V3 |
| Buzzer, **middle box only** | Buzzer + to GPIO25, buzzer − to ESP32 ground |

Keep a common ground within each unit. Do not power a servo from ESP32 3V3 or GPIO pins. A suitable external servo supply avoids regulator overload and Wi-Fi brownouts. During USB programming, avoid connecting another source to the board's 5 V input unless the exact board supports that arrangement; the separately powered servo still needs a shared ground.

The sensor is powered from the ESP32's 3V3 pin, so its ECHO output is a 3.3 V signal and goes to GPIO34 directly: there is no divider. **Do not move the sensor supply to 5 V while ECHO is wired directly.** A 5 V ECHO needs a divider or level shifter again, for example 2.2 kΩ from ECHO to the GPIO and 3.3 kΩ from the GPIO to ground (approximately 3.0 V). The ESP32 uses 3.3 V logic; see [Espressif's electrical specifications](https://documentation.espressif.com/esp32_datasheet_en.pdf). The classic HC-SR04 is specified for 5 V and only the 3–5.5 V revisions range reliably on 3V3, so check every sensor with `arduino/bench_test` before mounting it.

On classic ESP32 boards, GPIO32 and GPIO33 support output (trigger and servo signal). GPIO34 is input-only and has no internal pull-up or pull-down resistor, which suits ECHO: the sensor drives that line both ways. GPIO32/33/34 have no boot strapping restriction in [Espressif's GPIO table](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html). Check the silkscreen's **GPIO numbers**, not header positions.

These are the firmware defaults (`include/settings.h`). A local `config.local.h` or a generated `tracker_config.h` overrides them and is never rewritten by the tools: a file written for the old map (servo GPIO25, ECHO GPIO35) must have its three pin lines changed by hand.

## Configure and flash

For Arduino IDE, run `python3 -m tools.prepare_tracker_firmware` from the project
root. Open the sketch named after each box's position (`tracker_left`,
`tracker_middle`, `tracker_right`, or `tracker_right_pair` for a two-box right
box). In that sketch's `tracker_config.h`, enter the phone hotspot as
`WIFI_SSID` and `WIFI_PASSWORD` and check the per-servo calibration. Select
**ESP32 Dev Module** and upload to the matching board. The folders are generated
from the maintained firmware, and regeneration preserves each local config file.
The preparation command only writes sketch files; it does not flash a board.
Every unit must receive the current WM2 tracking firmware. The prior WM1 tracker
and the USB sensor sketch do not implement this workflow.
See [live setup](../docs/live-tracker-setup.md) for the complete sequence.

### Wi-Fi: the phone hotspot

The firmware joins exactly one network as an ordinary WPA2-personal station:
the phone hotspot named by `WIFI_SSID` and `WIFI_PASSWORD` in `tracker_config.h`
(Arduino) or `config.local.h` (PlatformIO). The laptop joins the same hotspot.
There are no network profiles and no board acts as an access point.

- The ESP32 radio is **2.4 GHz only**. On an iPhone turn on **Maximise
  Compatibility** and keep the Personal Hotspot screen open while the boxes join.
- An iPhone's default hotspot name contains a typographic apostrophe (U+2019).
  Write it as the UTF-8 bytes `\xE2\x80\x99` inside the C string, for example
  `"Sam\xE2\x80\x99s iPhone"`. A name longer than 32 bytes fails the build.
- At boot each board prints `Wi-Fi: will join "<name>" (phone hotspot, 2.4 GHz)`.
  The password is never printed.
- While it is not connected, the board prints `Joining Wi-Fi "<name>"` and tries
  again every 10 s. A lost connection cancels pending commands.
- Once connected it prints `Node n ready at <IP>:4211 (WM2 AIM/FIRE)` and
  broadcasts `WM2 HELLO n` to UDP 4210 every two seconds. That is how the laptop
  finds the boxes; no IP address is configured on either side.

A private config written before 2026-10-01 may still set `WIFI_PROFILE`,
`SCHOOL_WIFI_*`, `ONENET_*` or `TRACKER_WIFI_*`. The build then stops with
`Network profiles were removed: ...` instead of joining the wrong network: move
the hotspot name and password into `WIFI_SSID` and `WIFI_PASSWORD` by hand and
delete those lines. A `tracker_network.h` tab left in an older generated sketch
folder is no longer used and can be deleted.

Run the three-box prototype with normal discovery:

```bash
python3 -m whack --tracker swarm --config config.prototype.json
```

`--nodes` is an optional override for a network that blocks broadcast. Give the
addresses from Serial Monitor, left to right:

```bash
python3 -m whack --tracker swarm --config config.prototype.json --nodes LEFT_IP MIDDLE_IP RIGHT_IP
```

### PlatformIO alternative

The following are manual commands; this workflow does not automatically upload
firmware:

Install PlatformIO Core or its VS Code extension, then run from this directory:

```bash
cp include/config.example.h include/config.local.h
# Edit config.local.h: the phone hotspot's name and password, and per-node calibration.
pio run
pio run -e node_left   -t upload --upload-port /dev/ttyUSB0   # node 0
pio run -e node_middle -t upload --upload-port /dev/ttyUSB1   # node 1
pio run -e node_right  -t upload --upload-port /dev/ttyUSB2   # node 2
# two boxes: node_left + node_right_pair (node 1)
pio device monitor --port /dev/ttyUSB0 --baud 115200
```

Choose the actual ports on your machine. `config.local.h` is gitignored. Builds also work without that file, but the firmware then reports missing credentials over USB and does not connect. Credentials are stored in the flashed image; this is intended for the project's phone hotspot.

PlatformIO remains pinned to `espressif32@7.0.1`, whose [official release lists Arduino 2.0.17](https://github.com/platformio/platform-espressif32/releases/tag/v7.0.1). The firmware selects the appropriate servo PWM API for Arduino ESP32 2.x or 3.x. Arduino 3 uses [LEDC channel attachment and writes](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html); no external servo library is needed.

## Calibrate before scanning

1. With the sensor mount clear of obstacles, start at a requested bearing of 90° (`90000` millidegrees). Both sensors must face **forward into the play area**, along its positive y axis. The servo moves to this centre on startup and holds position when commands stop.
2. Set `SERVO_REVERSED` if increasing bearings turn the mount the wrong way. World bearings are 0° right (+x), 90° forward (+y), and 180° left (-x), for **both** nodes.
3. Adjust `SERVO_CENTER_TRIM_MDEG` until the mount's centre faces forward. The firmware applies reversal first, then trim; responses continue to report the world bearing.
4. Calibrate `SERVO_PULSE_MIN_US` and `SERVO_PULSE_MAX_US` against measured angles using the servo's specification. The default 1000–2000 µs pulse range is a conservative starting point, **not evidence that your servo travels 180°**. The linear mapping needs to match actual movement for valid geometry.
5. Set `SERVO_MIN_MDEG` and `SERVO_MAX_MDEG` to avoid mount collisions and servo end stops. These bounds apply to the internal servo coordinate **after reversal and trim**. Unreachable requests return `INVALID`; they are never silently clamped.
6. Test a flat target at several known distances, then a stationary person, before moving-person tests. Tune settle time for the loaded mount. A changed bearing uses a default settling allowance of 60 ms + 3 ms per degree moved, capped at 700 ms. An unchanged, settled bearing adds no new wait. There is no angle encoder; `actual_angle_mdeg` is the calibrated commanded estimate.

The HC-SR04 reference specifies a 10 µs trigger and more than 60 ms between measurement cycles. Firmware uses 10 µs triggers, at least 65 ms between local pings, a 25 ms echo timeout, and accepts 20–4000 mm distances. See the [module datasheet](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf). The PC must also leave a quiet interval **between different nodes**, since local spacing alone cannot prevent cross-talk.

## Laptop calibration and following

After checking each mount and sensor, run the laptop visualizer, clear the field
and press **C**. The dense bearing sweep includes the search bearings and samples
each direction three times. Background profiles are versioned and tied to the
geometry; old sparse profiles need recalibration. The background filter rejects
unprofiled gaps rather than treating them as free space.

The laptop starts at the centre by default or scans with `--start-mode search`.
Two consistent foreground pairs confirm a player. It calculates the forward
circle intersection, estimates velocity, predicts aiming directions, and uses
bounded local recovery after missed echoes. **Space** restarts acquisition,
**R** stops and forgets the player until **Space** is pressed, and
**D** shows measurement age, update rate and confidence. The single spot is solid
for measured estimates and hollow/dim for short prediction, then disappears when
lost or outside the field. There are no game zones. The only sound is the
middle box's buzzer, which the default swarm tracker sounds during a near-wall
alert (see [Buzzer](#buzzer)).

See [the full workflow](../docs/player-tracking-workflow.md). Servo directions,
human echoes and actual delay must still be tested with the two physical units.

## WM2 UDP protocol

Packets are bounded ASCII with integer fields. Nodes listen on **UDP 4211**;
movement/ranging commands must come from the laptop's **UDP 4210**. Nodes
broadcast every two seconds:

```text
WM2 HELLO 0
```

With explicit node IPs, the laptop also requests a unicast capability reply:

```text
WM2 DISCOVER
```

DISCOVER returns HELLO to the request's source port. It does not move the servo,
claim control ownership, change sequence ordering or alter firing permissions.
The laptop requires a fresh compatible node identity; protocol freshness expires
after six seconds. Knowing a configured IP does not establish that the board is
online or still running WM2 firmware.

### Buzzer

A box built with `BUZZER_PIN` sounds its buzzer on request. Only the middle box
(node 1) has one, on GPIO25; `BUZZER_PIN` defaults to `-1`, no buzzer.

```text
WM2 BUZZ 400
```

The single field is a duration of 0..2000 ms. The buzzer sounds until that long
after receipt. Every new BUZZ replaces the deadline, and `WM2 BUZZ 0` silences
at once. The board silences itself when the deadline passes: the laptop repeats
the command while the sound should continue, so a laptop that stops or leaves
the network cannot leave the buzzer on for more than 2 s.

BUZZ must come from the laptop's UDP 4210. It has no sequence number and no
reply. Like DISCOVER it claims no control ownership and leaves aims, firing
leases and ping spacing alone. A box without a buzzer ignores it.

`BUZZER_TONE_HZ` (default 2000) is the square wave for a passive buzzer: LEDC
channel 2, 10-bit, 50 % duty while sounding and duty 0 when silent. The servo
keeps channel 0 and its own 50 Hz timer. Set `BUZZER_TONE_HZ 0` for an active
buzzer; the pin is then held HIGH while sounding. With `#if NODE_ID == 1` the
`node_right_pair` build (node 1 of a two-box layout) drives GPIO25 as well.
The generated Arduino sketches differ there: only `tracker_middle` is created
with `BUZZER_PIN`, and `tracker_right_pair` has none unless it is added to its
`tracker_config.h`. `BUZZER_PIN` may not be GPIO1 or GPIO3 (serial), GPIO6..11
(flash), GPIO34..39 (input-only) or a pin the servo or sensor uses; the build
fails if it is.

### Aim both, fire one at a time

The laptop sends an AIM to each node, using one frame sequence and the bearing
appropriate to that node. The following exchange is an example for node 0:

```text
WM2 AIM 12345 90000
WM2 READY 0 12345 90000 1000 OK
WM2 FIRE 12345
WM2 RANGE 0 12345 90000 1524 OK 42400 8910
```

AIM moves the servo without producing ultrasound. READY is emitted after the
configured settling allowance. Both nodes can aim at once; the host waits for
both to be ready before sending FIRE to only one. The other sensor receives its
turn after the first result and an acoustic quiet interval.

READY fields are `node sequence bearing_mdeg lease_ms status`. `OK` grants a
single-use firing lease lasting at most **1000 ms** from readiness; retransmitted
READY reports the remaining lease and never extends it. A rejected aim reports
`INVALID` and zero lease.

FIRE must reference that aim sequence and arrive after readiness, before lease
expiry, and after the local ping interval. It executes immediately or is rejected;
it is never queued to fire later. Early, expired or repeated requests cannot
produce an additional ping. An existing completed result can be replayed from
the 16-entry transaction cache without operating the sensor again.

RANGE fields are:

```text
node sequence bearing_mdeg distance_mm status sample_ms age_us
```

`sample_ms` is the node's local millisecond clock at trigger time. `age_us` is the
microsecond elapsed acquisition time recorded when completing the result. Cached
replies retain that original metadata. The laptop combines command/response timing
with this age to bound the measurement time in its own clock; the two ESP32 clocks
are not synchronized or directly compared.

Statuses:

| Status | Meaning |
| --- | --- |
| `OK` | Valid firmware range in 20..4000 mm |
| `TIMEOUT` | No complete echo within the bounded acquisition wait |
| `INVALID` | Invalid firing permission, unreachable aim, stuck-high ECHO, or out-of-range result |

Error ranges are zero and cannot be used as a position. Bearings describe the
calibrated command estimate, not an encoder reading or measured echo direction.

### Timing, retries and control ownership

Sequence IDs are nonzero uint32 integers and use wrap-aware ordering. Newer AIM
commands may replace an unfired transaction and revoke older firing permissions.
Retries with the same sequence cannot restart servo motion or extend a lease.
Conflicting sequence payloads are rejected. Only one laptop should coordinate
the units; ownership expires after 30 seconds without accepted command activity.

Servo settling is serviced without blocking the network loop. Only the echo
measurement blocks, for at most 25 ms. Nodes enforce at least 65 ms between their
own triggers. The laptop also waits at least 65 ms after a completed result before
authorizing the other node. If FIRE may have been delivered but its reply is lost,
the laptop retains the guard through possible lease expiry, echo completion and
quiet time. Retry/cancellation cannot shorten that guard.

Malformed fields, overflows, wrong movement-command source ports, embedded NULs
and extra tokens are rejected. Wi-Fi loss cancels pending transactions and
revokes leases; fresh discovery and commands are required after reconnecting.
Physical room crosstalk and radio timing still require measurement.

### Legacy diagnostics

WM1 `MEASURE` and its shorter `RANGE` reply remain for existing single-node probe
tools. They combine aiming and ranging and do not participate in the WM2
coordinated tracker. The laptop visualizer requires both nodes to advertise WM2;
it will not silently use the old sequential workflow. Run only one probe or
controller at a time.

## Checks without hardware

Build both boards with `pio run`. For the native parser and calibration regression checks, run from the repository root:

```bash
g++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include firmware/test/protocol_test.cpp -o /tmp/whack-firmware-protocol-test
/tmp/whack-firmware-protocol-test
```

Native tests cover malformed/overflowed inputs, discovery, buzzer durations and
the buzzer deadline, sequence wraparound, lease consumption/expiry, reversed
mounting, trim and travel-limit rejection.
Python simulation and loopback tests cover coordination and synthetic tracking.
These checks do not exercise actual servo motion, radio transport or human
ultrasonic reflections. No measured tracking rate or latency is claimed.
