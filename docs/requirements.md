# Requirements and validation

This implementation targets **two ESP32 boards, two pan servos, and two ultrasonic sensors**: one of each in each wireless box. The servos aim the sensors; body motion controls the Windows game. This is a prototype architecture. Its room coverage, body tracking accuracy, battery runtime, and warning response need the physical tests below.

## Requirements traced to the brief

Source: [ES3 Whack-a-Mole v2.1.pdf](../ES3%20Whack-a-Mole%20v2.1.pdf), pages 4–6. These are paraphrases of the supplied project requirements, not measured results.

| ID | Required behaviour or constraint | Source | Evidence to collect |
| --- | --- | --- | --- |
| R1 | Body movement controls the cursor using ultrasound alone. A randomly appearing mole gives one point if reached before expiry. | p. 4 | Live demonstration with real sensor input; simulator is only a software check. |
| R2 | Track over a 1.5 m wide × 1.4 m deep playing area, beginning 0.60 m from the screen wall. | p. 4 | Marked floor grid, tracking logs, errors and dropout rates. |
| R3 | Every component stays within 0.50 m of the wall; nothing occupies the playing area. | p. 4 | Measurements and photographs including servo sweep and wiring. |
| R4 | Entering the 0.60 m dead zone produces an audible alarm and an effective visible warning. | pp. 4–5 | Boundary crossing tests, speaker check, warning latency recording. |
| R5 | Each sensor box communicates wirelessly with the game PC. | pp. 4–5 | Both boxes operating without USB or signal cables to the PC. |
| R6 | Each box fits within 100 × 100 × 150 mm. The performance checklist says less than those dimensions, so design with clearance. | pp. 4–5 | External dimension measurements including moving parts. |
| R7 | Each box runs on its own four AA NiMH cells for at least one hour; the performance checklist asks for more than one hour. USB charging is optional. | pp. 4–5 | More than 60 minutes of battery-only operation with current/voltage logs. |
| R8 | Integrate sensor data into calibrated spatial positions, with accuracy and response sufficient for play. | p. 5 | Calibration record and the acceptance tests below. |
| R9 | Include increasing difficulty levels and downloadable, installable Windows software. | pp. 4–5 | Clean Windows installation and game progression test. |
| R10 | Use sound construction; return supplied components working without solder, adhesive, paint, or similar material applied to them. | p. 5 | Removable headers/clamps and final inspection. |
| R11 | Total component budget is $100 including supplied parts. The supplied inventory includes two ESP32s and four RCWL-1601 sensors. | p. 6 | Bill of materials including the two added servos and power electronics. |

The user's two-sensor design uses a subset of the supplied four sensors. The brief permits multiple sensors and does not require all four. Servos and their mounts are additional components and count toward the budget. No particular servo model or ESP32 board variant has been identified; pin availability, supply input and mechanical limits must be checked against the actual hardware.

## Geometry and the two-sensor design

Use metres throughout. Put the origin on the screen wall at the left edge of the playing area. Positive `x` is right; positive `y` is away from the wall. The playing rectangle is:

```text
 0.00 <= x <=  1.50
 0.60 <= y <=  2.00
```

Mount the two acoustic centres at a common height, separated horizontally. The default layout is left `(0.00, 0.20)` and right `(1.50, 0.20)`, but record the measured positions in configuration. The whole enclosure and its swept volume must remain within 0.50 m of the wall. Mount both sensors horizontally at a height that intersects the player's torso; floor and ceiling returns can invalidate a two-dimensional model.

Let the baseline be `b`, common sensor depth be `ys`, and calibrated ranges be `rL` and `rR`. With the left anchor at `x=0`, the forward circle intersection is:

```text
x = (rL*rL - rR*rR + b*b) / (2*b)
h2 = rL*rL - x*x
y = ys + sqrt(h2)
```

Reject impossible intersections (`h2 < 0` beyond numerical tolerance), physically implausible jumps and old range pairs. The positive root selects the front of the sensor baseline. It cannot represent a player behind that baseline. The warning region between the wall and the sensors therefore needs explicit testing; moving the boxes closer to the wall reduces this blind region.

For a predicted point `(x,y)` and sensor `(sx,sy)`, the aim angle measured counter-clockwise from the positive x axis is `atan2(y-sy, x-sx)`: 90° points straight away from the wall. Translate that geometric angle through each servo's measured centre offset, direction and allowed travel. A servo command is an aiming direction, not an independently measured target bearing.

Two circle ranges determine a point only if both returns correspond to that point. A person is an extended, moving reflector: the boxes may see different parts of the torso, an arm, a wall or furniture. This creates bias even when both individual ranges are accurate. Restrict the first demonstration to one player, calibrate an empty room, acquire the target with a sweep, and keep the servos near the predicted target while tracking. Reacquire after loss; do not preserve a scoring cursor indefinitely from the last good point.

The RCWL-1601 product specification lists a typical detection angle of ±15° (±20° maximum) and a typical measurement cycle of 50 ms. Fixed forward beams cannot cover this whole near-field rectangle from both wall-side anchors; pan servos add coverage but introduce movement and acquisition delay. The vendor recommends 10–250 cm for best results, although the listed maximum range is longer. These specifications describe the component, not demonstrated human-tracking accuracy. [Adafruit RCWL-1601 technical details](https://www.adafruit.com/product/4007)

Sequence pings so the two modules do not transmit concurrently. The controller leaves at least 65 ms between a measurement response and the next request, with only one active measurement. Firmware also waits after servo motion before triggering; measure the required settle time on the actual loaded servo. Wider sweeps trade acquisition time for coverage. Reduce timing only after cross-talk, settling and dropped-echo measurements demonstrate that it is reliable.

## Hardware and firmware API assumptions

- The intended sensor interface is separate GPIO trigger/echo. The RCWL-1601 is available in other interface variants, so check the actual module. Adafruit describes the GPIO version as HC-SR04 software compatible, powered at 3–5.5 V, with logic level following supply. Run a verified RCWL-1601 at 3.3 V for direct ESP32 logic. A generic 5 V HC-SR04 needs a suitable echo level shifter or divider. [RCWL-1601 product specification](https://www.adafruit.com/product/4007)
- A compatible trigger is a 10 µs high pulse. Convert the measured round trip to distance using `distance_m = echo_seconds * sound_speed_m_s / 2`. Always bound the wait for an echo. Adafruit's reference driver uses a 10 µs trigger and timed waits for both rising and falling echo edges. [Adafruit HC-SR04 driver source](https://github.com/adafruit/Adafruit_CircuitPython_HCSR04/blob/main/adafruit_hcsr04.py)
- ESP32 GPIO is not a servo supply. Provide the servo's specified supply through a regulator sized for its start/stall current, and connect signal grounds. Size the ESP32 regulator for Wi-Fi load transients. Do not connect the four-cell pack directly to a 3.3 V pin. Verify the actual development board's power-input circuit. The ESP32 chip datasheet specifies a 3.3 V supply design and electrical limits; development-board input limits are board-specific. [Espressif ESP32 datasheet, electrical characteristics](https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf)
- The build pins PlatformIO Espressif32 7.0.1, which supplies Arduino-ESP32 2.0.17. That core uses channel-based `ledcSetup`/`ledcAttachPin`. For Arduino-ESP32 3.x, the official API is `ledcAttach(pin, frequency, resolution)` followed by `ledcWrite(pin, duty)`: the older setup functions were removed. Check setup success and use an explicit version guard when supporting both. A servo commonly starts at 50 Hz, with pulse endpoints configured for its actual model. [PlatformIO 7.0.1 manifest](https://github.com/platformio/platform-espressif32/blob/v7.0.1/platform.json), [LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html), [2.x to 3.0 migration](https://docs.espressif.com/projects/arduino-esp32/en/latest/migration_guides/2.x_to_3.0.html)
- Current `WiFiUDP` is an alias for `NetworkUDP`. Its receive/send interfaces include `begin`, `parsePacket`, `read`, `remoteIP`, `remotePort`, `beginPacket`, `write`, and `endPacket`. UDP needs application-level sequence matching, packet validation, timeouts and recovery because packets can be lost or reordered. Avoid relying on `flush()` to discard input; the current API has `clear()`. [Espressif WiFiUDP header](https://github.com/espressif/arduino-esp32/blob/master/libraries/WiFi/src/WiFiUdp.h), [NetworkUDP header](https://github.com/espressif/arduino-esp32/blob/master/libraries/Network/src/NetworkUdp.h)

## Physical acceptance procedure

The brief gives qualitative accuracy and responsiveness requirements. The numerical targets below are proposed engineering gates, not university-specified limits or claimed results. Record actual measurements and revise target sizes or tracking parameters from evidence.

1. **Inspect and bring up one box.** Record board, sensor and servo models, battery capacity, regulator ratings, wiring, firmware revision and measured rail voltages. Centre the unloaded servo first, then fit the bracket and verify sweep clearance. Measure echo voltage before connecting it to the ESP32. Compare ranging to a flat board at 0.25, 0.50, 1.00, 1.50 and 2.00 m; log 30 samples at each position and all timeout counts. Repeat for the other box.
2. **Calibrate geometry and room.** Measure acoustic centre positions, baseline and sensor height. Align and record servo zero offsets/directions using a marked centre line. Sweep the empty room and store or record static background returns. Verify target acquisition with one player standing at centre. Repeat after moving either box or furniture. Range correction based on a flat board does not remove human-body reflection bias.
3. **Check coverage and stationary accuracy.** Mark `x = 0.05, 0.40, 0.75, 1.10, 1.45 m` and `y = 0.65, 1.00, 1.35, 1.70, 1.95 m` (25 points). At each point stand for 10 seconds facing the screen, then repeat side-on and with different clothing. Log estimated position, ground truth marker, age of each range, tracking state and invalid counts. Initial gate: at least 95% valid updates after acquisition and 95th-percentile position error no more than 0.15 m at every point. Report worst points separately; an average alone can hide uncovered corners.
4. **Check motion and latency.** Walk lateral, front-to-back and diagonal paths, including each edge; repeat 10 times. Record synchronized video of floor marks and the on-screen cursor, plus timestamped telemetry. Initial gate: 95th-percentile motion-to-visible-cursor latency below 250 ms while locked, with no unsupported jumps. Measure initial acquisition and reacquisition separately (initial target: within 3 seconds); these are not the same as locked tracking latency. Tune mole radius/dwell time only after measuring real tracking error and latency.
5. **Check interference and recovery.** Run both boxes in normal alternating operation, then observe operation with walls/furniture near the beam edges. Interrupt one box's power, block a transducer, disconnect Wi-Fi, inject malformed or delayed packets in the software tests, and restart either endpoint. Scoring must stop on stale/invalid tracking. Recovery must not require restarting the PC game. A stale warning or missing data must not silently look like a fresh valid position.
6. **Check the dead zone.** At several lateral positions, walk slowly across the 0.60 m line and back, including near both outer edges; use a spotter and start with generous screen clearance. Record audible and visible onset and release. Initial gate: both warnings within 250 ms of a detected crossing, with no scoring while warning. Repeat after momentary loss of one range and while the servos reacquire. Check approaches to the region behind the sensor baseline. If any approach is invisible, this hardware/layout has not satisfied R4; software cannot turn a missing echo into a verified person position. Document the failure and change placement/coverage before active play.
7. **Check battery and construction.** Run both boxes independently on their four NiMH cells for more than 60 minutes with the real game, frequent servo movements and Wi-Fi traffic. Record start/end cell/pack voltage, average current, peak behaviour, temperature, brownouts and resets. Capacity divided by nominal current is an estimate; use the timed run as evidence. Measure the final enclosures and inspect removable connections and sweep clearance.
8. **Check Windows delivery.** On a clean Windows machine, install the packaged application, connect to the sensor network and permit the documented local UDP port. Calibrate, acquire, score exactly once per mole, miss a mole, progress through levels, trigger both warnings, lose/recover a sensor and restart. Simulator play and automated unit tests are separate evidence; neither substitutes for this hardware run.

Keep the test date, commit hash, configuration, raw readings and failures with each result. Firmware compilation validates syntax and linkage. Only physical measurements establish that the two-sensor design meets the project brief.
