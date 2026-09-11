# ESP32 sensor nodes

Each ESP32 controls **one positional servo carrying one trigger/echo ultrasonic sensor**. Flash `node_left` to the left unit (node 0) and `node_right` to the right unit (node 1). A PC on the same 2.4 GHz Wi-Fi network commands all pings in sequence, so the two ultrasonic transmitters do not fire together. The ESP32s never start a range measurement independently.

The provisional hardware target is a classic DOIT ESP32 DevKit V1 and an HC-SR04-compatible sensor. ESP32-C3/S3 boards, continuous-rotation servos, and UART/I2C ultrasonic sensors need different configuration or drivers. Firmware builds and parser tests can be checked without hardware; actual tracking, servo travel, and electrical timing still need bench verification.

## Connect each unit

| Signal | ESP32 connection |
| --- | --- |
| Servo control | GPIO18 |
| Ultrasonic TRIG | GPIO23 |
| Ultrasonic ECHO | GPIO19, **through a 5 V to 3.3 V level shifter/divider** |
| Ultrasonic ground | ESP32 ground |
| Servo ground | ESP32 ground and external supply ground |
| Servo power | Separate regulated supply rated for the servo voltage and stall current |
| HC-SR04 supply | Regulated 5 V, according to the sensor's specification |

Keep a common ground within each unit. Do not power a servo from ESP32 3V3 or GPIO pins. A suitable external servo supply avoids regulator overload and Wi-Fi brownouts. During USB programming, avoid connecting another source to the board's 5 V input unless the exact board supports that arrangement; the separately powered servo still needs a shared ground.

Treat ECHO as 5 V unless your exact sensor explicitly provides a 3.3 V-safe output. For a nominal 5 V ECHO, a divider can use **2.2 kΩ from ECHO to GPIO19 and 3.3 kΩ from GPIO19 to ground**, producing approximately 3.0 V. Confirm its output against your sensor and supply voltage. The ESP32 uses 3.3 V logic; see [Espressif's electrical specifications](https://documentation.espressif.com/esp32_datasheet_en.pdf). If the sensor does not accept a 3.3 V TRIG input, add a suitable level shifter in that direction too.

GPIO23 was chosen for trigger because GPIO5 is a boot strapping pin on classic ESP32; the selected GPIO18/19/23 have no such restriction in [Espressif's GPIO table](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html). Check the silkscreen's **GPIO numbers**, not header positions.

## Configure and flash

Install PlatformIO Core or its VS Code extension, then run from this directory:

```bash
cp include/config.example.h include/config.local.h
# Edit config.local.h: Wi-Fi credentials and per-node calibration.
pio run
pio run -e node_left -t upload --upload-port /dev/ttyUSB0
pio run -e node_right -t upload --upload-port /dev/ttyUSB1
pio device monitor --port /dev/ttyUSB0 --baud 115200
```

Choose the actual ports on your machine. `config.local.h` is gitignored. Builds also work without that file, but the firmware then reports missing credentials over USB and does not connect. Credentials are stored in the flashed image; this is intended for a local project network.

The platform is pinned to `espressif32@7.0.1`, whose [official release lists Arduino 2.0.17](https://github.com/platformio/platform-espressif32/releases/tag/v7.0.1). This code uses the [Arduino 2.0.17 LEDC channel API](https://github.com/espressif/arduino-esp32/blob/2.0.17/cores/esp32/esp32-hal-ledc.h). Arduino 3 removed `ledcSetup` and `ledcAttachPin`; do not silently switch cores without adapting the code.

## Calibrate before scanning

1. With the sensor mount clear of obstacles, start at a requested bearing of 90° (`90000` millidegrees). Both sensors must face **forward into the play area**, along its positive y axis. The servo moves to this centre on startup and holds position when commands stop.
2. Set `SERVO_REVERSED` if increasing bearings turn the mount the wrong way. World bearings are 0° right (+x), 90° forward (+y), and 180° left (-x), for **both** nodes.
3. Adjust `SERVO_CENTER_TRIM_MDEG` until the mount's centre faces forward. The firmware applies reversal first, then trim; responses continue to report the world bearing.
4. Calibrate `SERVO_PULSE_MIN_US` and `SERVO_PULSE_MAX_US` against measured angles using the servo's specification. The default 1000–2000 µs pulse range is a conservative starting point, **not evidence that your servo travels 180°**. The linear mapping needs to match actual movement for valid geometry.
5. Set `SERVO_MIN_MDEG` and `SERVO_MAX_MDEG` to avoid mount collisions and servo end stops. These bounds apply to the internal servo coordinate **after reversal and trim**. Unreachable requests return `INVALID`; they are never silently clamped.
6. Test a flat target at several known distances, then a stationary person, before moving-person tests. Tune settle time for the loaded mount. Default delay is 60 ms + 3 ms per degree moved, capped at 700 ms. There is no angle encoder; `actual_angle_mdeg` is the calibrated commanded estimate.

The HC-SR04 reference specifies a 10 µs trigger and more than 60 ms between measurement cycles. Firmware uses 10 µs triggers, at least 65 ms between local pings, a 25 ms echo timeout, and accepts 20–4000 mm distances. See the [module datasheet](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf). The PC must also leave a quiet interval **between different nodes**, since local spacing alone cannot prevent cross-talk.

## UDP protocol

All messages are ASCII, use integer units, and contain no JSON. Nodes listen on UDP4211. The PC binds UDP4210. Nodes broadcast to the local subnet every two seconds:

```text
WM1 HELLO 0
```

The PC sends a unicast command to the chosen node from UDP4210:

```text
WM1 MEASURE 12345 90000
```

The node settles, emits one ping, and replies to that PC's UDP4210:

```text
WM1 RANGE 0 12345 90000 1524 OK
WM1 RANGE 0 12346 90000 0 TIMEOUT
WM1 RANGE 0 12347 90000 0 INVALID
```

Fields are `node sequence actual_angle_mdeg distance_mm status`. `TIMEOUT` means no complete echo before the deadline; `INVALID` means an unreachable servo request, a stuck-high echo, or a distance outside 20–4000 mm. Both error statuses have zero distance and must not be used as position fixes. `actual_angle_mdeg` is the previous bearing if a requested move was rejected.

Sequence IDs are nonzero uint32 integers. Start a PC session with Unix milliseconds modulo 2³² (use 1 if zero), then increment, skipping zero on wrap. Only one pending command is allowed. Identical pending retries are ignored, and the last 16 completed results are replayed without triggering again. Older sequences are rejected using wrap-aware ordering. Reusing a sequence with a different angle is ignored. A session becomes available to a new controller after 30 seconds without an accepted new command; this also clears ordering state to tolerate clock changes and long downtime. Wait for each result or the full command timeout before commanding the other node.

Packets with malformed fields, zero/overflowing sequence IDs, noninteger/negative/out-of-range bearings, embedded NULs, extra tokens, or the wrong source port are ignored without operating the hardware. A terminal CR/LF is optional. Wi-Fi loss cancels the pending acquisition; reconnecting resumes discovery, and only a fresh accepted command can trigger a ping.

## Checks without hardware

Build both boards with `pio run`. For the native parser and calibration regression checks, run from the repository root:

```bash
g++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include firmware/test/protocol_test.cpp -o /tmp/whack-firmware-protocol-test
/tmp/whack-firmware-protocol-test
```

These tests cover malformed/overflowed network inputs, sequence wraparound, reversed mounting, trim, and travel-limit rejection. They do not exercise actual servo motion, Wi-Fi transport, or ultrasonic reflections.
