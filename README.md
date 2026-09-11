# Two-node body tracker

Track one person with **two ESP32s, two positional servos and two ultrasonic
sensors**. Each servo aims one sensor. The PC coordinates wireless measurements,
calculates the position and displays a **cyan dot on a black screen**.

This project currently covers the hardware tracking subsystem and visualizer.
Gameplay is deferred. Board, sensor and servo models still need confirmation;
the defaults target classic ESP32 DevKit boards and trigger/echo ultrasonic
sensors such as the assignment's RCWL-1601.

## Try the visualizer

Python 3.10+ with Tk is required (included in the standard Windows Python
installer; Linux may need its `python3-tk` package). No third-party runtime
Python libraries are required.

```bash
python -m whack --simulate
```

Move the mouse across the window to move an ideal virtual reflector. The
simulation includes servo delays, alternating pings and beam visibility; it
cannot validate reflections from a human, wiring, mechanics or radio behaviour.
Press **C** to calibrate an empty area in hardware mode, **D** for diagnostics,
**F11** for fullscreen, and **Escape** to close.

A diagnostic run without a display:

```bash
python -m whack --simulate --headless --seconds 5
```

## Connect the hardware

1. Build two boxes, each with an ESP32, a positional pan servo and a sensor.
   Follow [wiring and firmware setup](firmware/README.md). Set Wi-Fi credentials
   in the ignored `firmware/include/config.local.h`.
2. From `firmware/`, use PlatformIO to upload `node_left` to the left ESP32 and
   `node_right` to the right ESP32. Do not flash both with the same node ID.
3. Place sensors at the same height and depth, aimed horizontally at torso
   height. Default acoustic centres are `(0, 0.20)` and `(1.50, 0.20)` metres;
   the wall is `y=0`. Measure and configure the actual geometry.
4. Copy `config.example.json` to `config.local.json`. Set measured positions,
   range corrections and tracking limits. Calibrate servo direction, centre
   and pulse endpoints in the firmware before fitting the loaded bracket.
5. Connect the PC and both ESP32s to the same 2.4 GHz local network, disable
   wireless client isolation and allow local inbound UDP4210 on the PC.
6. Run the visualizer, clear the area, then press **C**. Calibration has a
   three-second lead-in and measures20 aim points three times. Keep the whole
   area empty until it finishes. Walk into the area and watch the dot.

```bash
python -m whack --config config.local.json
```

If broadcast discovery is blocked, specify the addresses printed on USB serial:

```bash
python -m whack --config config.local.json --nodes 192.168.1.101 192.168.1.102
```

Profiles are saved as `calibration.local.json`; repeat calibration after moving
sensors or furniture. A changed geometry invalidates the old profile. Recording
can be enabled with `--record tracking.csv`. For headless room calibration use
`--headless --calibrate --seconds 120`, with both sensors online and nobody in
view. A timeout echo is treated as no background return; it does not prove that
the sensor is healthy. Confirm each sensor against a flat target first.

To centre and bench-test one sensor before calibration, close the visualizer
and run this from the project root (replace the address with its USB-serial IP):

```bash
python -m tools.probe_node --ip 192.168.1.101 --node 0 --angle 90 --count 10
```

This moves the servo to the requested bearing and prints repeated ranges.
Use small changes around 90 degrees to check direction before testing wider
travel. Run only one controller/probe at a time.

## How tracking works

The PC sends one measurement request at a time, with at least65 ms of quiet time
before the next request. Each node waits for its servo, pings and returns a
sequence-tagged range. Two ranges define a forward circle intersection; accepted
pairs must be no more than250 ms apart. Large servo moves may require a second
pair once both sensors are settled. While tracking, bearings snap to measured
background directions. When tracking is lost, both sensors scan candidate points.

The dot disappears on invalid or stale data. A detected position within0.60 m
of the screen triggers a warning and a system bell; sensor blind spots can still
prevent detection. This is a prototype, not a verified collision-warning system.
Initial acquisition and reacquisition can take a complete sweep and should be
measured separately from tracking latency.

Two broad ultrasonic beams may hit different body parts or furniture. The
triangulation model assumes a common reflector, so a build that compiles is not
proof of accurate body tracking. See [physical acceptance tests](docs/requirements.md)
and [architecture](docs/architecture.md) before claiming performance.

## Validation

```bash
python -m unittest discover -s tests -v
cd firmware
pio run
```

The suite includes a real loopback UDP test; it needs permission to open local
sockets. A standalone two-node emulator is in `tools/simulate_nodes.py`.

The supplied `example-code/` remains unchanged and licensed by its upstream
author; see `example-code/UPSTREAM.md`. The tracker implementation is in `whack/`.
