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
| Servo control | GPIO25 |
| Ultrasonic TRIG | GPIO32 |
| Ultrasonic ECHO | GPIO35, **through a 5 V to 3.3 V level shifter/divider** |
| Ultrasonic ground | ESP32 ground |
| Servo ground | ESP32 ground and external supply ground |
| Servo power | Separate regulated supply rated for the servo voltage and stall current |
| HC-SR04 supply | Regulated 5 V, according to the sensor's specification |

Keep a common ground within each unit. Do not power a servo from ESP32 3V3 or GPIO pins. A suitable external servo supply avoids regulator overload and Wi-Fi brownouts. During USB programming, avoid connecting another source to the board's 5 V input unless the exact board supports that arrangement; the separately powered servo still needs a shared ground.

Treat ECHO as 5 V unless your exact sensor explicitly provides a 3.3 V-safe output. For a nominal 5 V ECHO, a divider can use **2.2 kΩ from ECHO to GPIO35 and 3.3 kΩ from GPIO35 to ground**, producing approximately 3.0 V. Confirm its output against your sensor and supply voltage. The ESP32 uses 3.3 V logic; see [Espressif's electrical specifications](https://documentation.espressif.com/esp32_datasheet_en.pdf). If the sensor does not accept a 3.3 V TRIG input, add a suitable level shifter in that direction too.

On classic ESP32 boards, GPIO32 supports the trigger output and GPIO35 is input-only, suitable for ECHO. GPIO25/32/35 have no boot strapping restriction in [Espressif's GPIO table](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html). Check the silkscreen's **GPIO numbers**, not header positions.

## Configure and flash

For Arduino IDE, run
`python3 -m tools.prepare_tracker_firmware --network tracker` from the project
root to prepare both boards for TrackerNet. Open
the sketch named after each box's position (`tracker_left`, `tracker_middle`,
`tracker_right`, or `tracker_right_pair` for a two-box right box), check that sketch's
`tracker_config.h` for per-servo calibration, select **ESP32
Dev Module**, and upload to the matching board. The folders are generated from
the maintained firmware, and regeneration preserves each local config file.
The preparation command only writes sketch files; it does not flash a board.
Both units must receive the updated WM2 tracking firmware. The prior WM1 tracker,
USB sensor sketch and standalone OneNet tests do not implement this workflow.
See [live setup](../docs/live-tracker-setup.md) for the complete sequence.

### TrackerNet: Wi-Fi provided by the left board

Profile **3** makes node 0 a Wi-Fi access point (SoftAP). It creates the
WPA2-protected **TrackerNet** network at `192.168.4.1` with subnet mask
`255.255.255.0`. Node 1 joins automatically using the same generated credentials.
The laptop joins through its normal Wi-Fi settings.

The preparation command creates a shared random private password in
`tracker_network.h` in each generated sketch folder. Open that tab in Arduino
IDE to read the password for the laptop. Both matching sketches must be manually
uploaded before using this mode. Keep the network header local; it is not a
published example password.

Boot the left board first, then the right. On the laptop select **TrackerNet**,
enter the generated password and stay connected if warned that the network has
no internet. The laptop and right board use DHCP; the right board is not assigned
a guaranteed `192.168.4.2`. Read its actual address in Serial Monitor at 115200
baud if needed.

Run the visualizer with normal discovery:

```bash
python3 -m whack --config config.local.json
```

If discovery fails, replace `ACTUAL_RIGHT_IP` with the right board's serial IP:

```bash
python3 -m whack --config config.local.json --nodes 192.168.4.1 ACTUAL_RIGHT_IP
```

The local network supplies tracker communication without internet. Its stability
with both physical boards still needs testing. Servo and tracking behavior are
the same across network profiles.

### Retained home and school profiles

Keep credentials local in `tracker_config.h` (Arduino) or `config.local.h`
(PlatformIO). Select one profile without deleting the others:

| Setting | Use |
| --- | --- |
| `WIFI_PROFILE 0` | Home: `WIFI_SSID`, `WIFI_PASSWORD` |
| `WIFI_PROFILE 1` | School local network/hotspot: `SCHOOL_WIFI_SSID`, `SCHOOL_WIFI_PASSWORD` |
| `WIFI_PROFILE 2` | Optional OneNet PEAP: `ONENET_USERNAME`, `ONENET_PASSWORD` |
| `WIFI_PROFILE 3` | Left-board TrackerNet access point; right board and laptop join |

The laptop and both boards need a network allowing local UDP communication.
Internet access is unnecessary. Change the selected profile and manually upload
again when switching networks. The generated `tracker_network.h` selects profile
3 without altering the home/school settings in `tracker_config.h`. Regeneration
without `--network` preserves that selection. To remove the generated override
and use each existing config's selected profile:

```bash
python3 -m tools.prepare_tracker_firmware --network configured
```

Manually upload both sketches after changing mode. Older local config files are
preserved; add missing profile fields from the example when upgrading them.

The OneNet path uses certificate validation and the configured server domain
(`radius.mq.edu.au` by default). It requires Arduino-ESP32 **3.3+** with its CA
bundle and EAP domain-check APIs. Certificate time is seeded from the build
stamp using `ONENET_BUILD_TIMEZONE`; rebuild before testing or provide a trusted
clock. The older PlatformIO core below rejects this profile at compile time.
OneNet login reliability and tracker UDP access remain unverified and deferred.
Profiles 0, 1 and 3 support the current local tracking workflow.

### PlatformIO alternative

The following are manual commands; this workflow does not automatically upload
firmware:

Install PlatformIO Core or its VS Code extension, then run from this directory:

```bash
cp include/config.example.h include/config.local.h
# Edit config.local.h: Wi-Fi credentials and per-node calibration.
pio run
pio run -e node_left   -t upload --upload-port /dev/ttyUSB0   # node 0
pio run -e node_middle -t upload --upload-port /dev/ttyUSB1   # node 1
pio run -e node_right  -t upload --upload-port /dev/ttyUSB2   # node 2
# two boxes: node_left + node_right_pair (node 1)
pio device monitor --port /dev/ttyUSB0 --baud 115200
```

Choose the actual ports on your machine. `config.local.h` is gitignored. Builds also work without that file, but the firmware then reports missing credentials over USB and does not connect. Credentials are stored in the flashed image; this is intended for a local project network.

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
bounded local recovery after missed echoes. **Space/R** restarts acquisition;
**D** shows measurement age, update rate and confidence. The single spot is solid
for measured estimates and hollow/dim for short prediction, then disappears when
lost or outside the field. There are no game zones or warning sounds.

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

Native tests cover malformed/overflowed inputs, discovery, sequence wraparound,
lease consumption/expiry, reversed mounting, trim and travel-limit rejection.
Python simulation and loopback tests cover coordination and synthetic tracking.
These checks do not exercise actual servo motion, radio transport or human
ultrasonic reflections. No measured tracking rate or latency is claimed.
