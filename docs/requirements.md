# Tracking subsystem requirements and validation

The current scope is **two ESP32 boards, two pan servos, two ultrasonic sensors, and a black-screen visualizer showing the tracked person as a dot**. Each wireless box contains one board, one servo, and one sensor. The servos aim the sensors. This is a tracking prototype; room coverage, body-position accuracy, response time and battery runtime remain unverified on physical hardware.

## Active subsystem checklist

The user's latest instruction narrows this stage to tracking and a dot display. Hardware and geometry constraints below come from [ES3 Whack-a-Mole v2.1.pdf](../ES3%20Whack-a-Mole%20v2.1.pdf), pages 4–6. They are paraphrases of the supplied requirements, not measured results.

| ID | Required behaviour or constraint | Source | Evidence to collect |
| --- | --- | --- | --- |
| R1 | Track a person's position using ultrasound alone and display it as a dot on a black screen. | User scope; p. 4 tracking requirement | Live dot display driven by real sensor input; simulator is only a software check. |
| R2 | Track over a 1.5 m wide × 1.4 m deep playing area, beginning 0.60 m from the screen wall. | p. 4 | Marked floor grid, tracking logs, errors and dropout rates. |
| R3 | Every component stays within 0.50 m of the wall; nothing occupies the playing area. | p. 4 | Measurements and photographs including servo sweep and wiring. |
| R4 | Detect valid tracked positions inside the 0.60 m dead zone and expose tracking loss separately. | pp. 4–5, tracking portion of the warning requirement | Boundary crossing and missing-data tests; record classification and detection latency. |
| R5 | Each sensor box communicates wirelessly with the tracking PC. | pp. 4–5 | Both boxes operating without USB or signal cables to the PC. |
| R6 | Each box fits within 100 × 100 × 150 mm. The performance checklist says less than those dimensions, so design with clearance. | pp. 4–5 | External dimension measurements including moving parts. |
| R7 | Each box runs on its own four AA NiMH cells for at least one hour; the performance checklist asks for more than one hour. USB charging is optional. | pp. 4–5 | More than 60 minutes of battery-only operation with current/voltage logs. |
| R8 | Integrate sensor data into calibrated spatial positions and measure tracking accuracy and response. | p. 5 tracking benchmark | Calibration record and the acceptance tests below. |
| R9 | Run a minimal visualizer that shows the current dot and makes unavailable tracking apparent. | User scope | Launch the visualizer, acquire a person, move the dot, lose and recover tracking. |
| R10 | Use sound construction; return supplied components working without solder, adhesive, paint, or similar material applied to them. | p. 5 | Removable headers/clamps and final inspection. |
| R11 | Total component budget is $100 including supplied parts. The supplied inventory includes two ESP32s and four RCWL-1601 sensors. | p. 6 | Bill of materials including the two added servos and power electronics. |

The user's two-sensor design uses a subset of the supplied four sensors. The brief permits multiple sensors and does not require all four. Servos and their mounts are additional components and count toward the budget. The user has identified Freenove ESP32-WROOM-32E boards and HC-SR04 sensors. Servo model, rated supply and mechanical limits still need confirmation.

The full brief also requires gameplay, scoring, difficulty levels, a downloadable Windows installer, and an audible/visual dead-zone alarm. Those product features are deferred by the user's scope change. Their mention in the brief does not make them acceptance criteria for this tracking-only stage. The retained dead-zone state is diagnostic tracking output; it does not establish compliance with the finished product's alarm requirement.

## Geometry and the two-sensor design

Use metres throughout. Put the origin on the screen wall at the left edge of the playing area. Positive `x` is right; positive `y` is away from the wall. The playing rectangle is:

```text
 0.00 <= x <=  1.50
 0.60 <= y <=  2.00
```

Mount the two acoustic centres at a common height, separated horizontally. The default layout is left `(0.00, 0.20)` and right `(1.50, 0.20)`, but record the measured positions in configuration. The whole enclosure and its swept volume must remain within 0.50 m of the wall. Mount both sensors horizontally at a height that intersects the person's torso; floor and ceiling returns can invalidate a two-dimensional model.

Let the baseline be `b`, common sensor depth be `ys`, and calibrated ranges be `rL` and `rR`. With the left anchor at `x=0`, the forward circle intersection is:

```text
x = (rL*rL - rR*rR + b*b) / (2*b)
h2 = rL*rL - x*x
y = ys + sqrt(h2)
```

Reject impossible intersections (`h2 < 0` beyond numerical tolerance), physically implausible jumps and old range pairs. The positive root selects the front of the sensor baseline. It cannot represent a person behind that baseline. The region between the wall and the sensors therefore needs explicit testing; moving the boxes closer to the wall reduces this blind region.

For a predicted point `(x,y)` and sensor `(sx,sy)`, the aim angle measured counter-clockwise from the positive x axis is `atan2(y-sy, x-sx)`: 90° points straight away from the wall. Translate that geometric angle through each servo's measured centre offset, direction and allowed travel. A servo command is an aiming direction, not an independently measured target bearing.

Two circle ranges determine a point only if both returns correspond to that point. A person is an extended, moving reflector: the boxes may see different parts of the torso, an arm, a wall or furniture. This creates bias even when both individual ranges are accurate. Restrict the first demonstration to one person, calibrate an empty room, acquire the target with a sweep, and keep the servos near the predicted target while tracking. Reacquire after loss; the display must not present an indefinitely held last position as current tracking.

The host's default `max_pair_skew_s` is **0.15 seconds**, measured between
estimated acquisition times on the host clock. Each estimate is bounded by FIRE
send time and RANGE receipt time minus the node's reported acquisition duration.
The two ESP32 clocks are not directly compared. Excessively uncertain or skewed
pairs are rejected. A velocity estimate aligns the earlier range to the later
sample; this is a first-order approximation, not an accuracy guarantee.

Acquisition visits the original field-boundary and near-wall candidate positions plus additional directions chosen to cover gaps under the configured beam-angle model. A complete sweep can take many seconds because each box must move, settle and measure, and pairs may need repeating. Initial acquisition, reacquisition and locked tracking latency are different measurements; there is no demonstrated sub-three-second acquisition guarantee.

Empty-room calibration uses a dense bearing sweep containing every search
bearing. Tracking can use intermediate directions only between nearby calibrated
bearings; the nearer background value is used conservatively. Bearings outside
the profile or across a large gap cannot bypass rejection. Recalibrate after
changes to placement, geometry, servo alignment or surrounding furniture.
A no-echo background entry is not proof of reliable empty-volume coverage.

The RCWL-1601 product specification lists a typical detection angle of ±15° (±20° maximum) and a typical measurement cycle of 50 ms. Fixed forward beams cannot cover this whole near-field rectangle from both wall-side anchors; pan servos add coverage but introduce movement and acquisition delay. The vendor recommends 10–250 cm for best results, although the listed maximum range is longer. These specifications describe the component, not demonstrated human-tracking accuracy. [Adafruit RCWL-1601 technical details](https://www.adafruit.com/product/4007)

Sequence pings so the two modules do not transmit concurrently. The controller leaves at least 65 ms between a measurement response and the next FIRE grant, with only one active measurement. Both servos can aim concurrently; only one FIRE may be outstanding. After a
lost reply the host waits out the firing lease plus the echo and quiet interval.
Firmware also waits after servo motion before triggering; measure the required settle time on the actual loaded servo. Wider sweeps trade acquisition time for coverage. Reduce timing only after cross-talk, settling and dropped-echo measurements demonstrate that it is reliable.

## Hardware and firmware API assumptions

- The intended sensor interface is separate GPIO trigger/echo. The RCWL-1601 is available in other interface variants, so check the actual module. Adafruit describes the GPIO version as HC-SR04 software compatible, powered at 3–5.5 V, with logic level following supply. Run a verified RCWL-1601 at 3.3 V for direct ESP32 logic. A generic 5 V HC-SR04 needs a suitable echo level shifter or divider. [RCWL-1601 product specification](https://www.adafruit.com/product/4007)
- A compatible trigger is a 10 µs high pulse. Convert the measured round trip to distance using `distance_m = echo_seconds * sound_speed_m_s / 2`. Always bound the wait for an echo. Adafruit's reference driver uses a 10 µs trigger and timed waits for both rising and falling echo edges. [Adafruit HC-SR04 driver source](https://github.com/adafruit/Adafruit_CircuitPython_HCSR04/blob/main/adafruit_hcsr04.py)
- ESP32 GPIO is not a servo supply. Provide the servo's specified supply through a regulator sized for its start/stall current, and connect signal grounds. Size the ESP32 regulator for Wi-Fi load transients. Do not connect the four-cell pack directly to a 3.3 V pin. Verify the actual development board's power-input circuit. The ESP32 chip datasheet specifies a 3.3 V supply design and electrical limits; development-board input limits are board-specific. [Espressif ESP32 datasheet, electrical characteristics](https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf)
- The build pins PlatformIO Espressif32 7.0.1, which supplies Arduino-ESP32 2.0.17. That core uses channel-based `ledcSetup`/`ledcAttachPin`. For Arduino-ESP32 3.x, the official API is `ledcAttach(pin, frequency, resolution)` followed by `ledcWrite(pin, duty)`: the older setup functions were removed. Check setup success and use an explicit version guard when supporting both. A servo commonly starts at 50 Hz, with pulse endpoints configured for its actual model. [PlatformIO 7.0.1 manifest](https://github.com/platformio/platform-espressif32/blob/v7.0.1/platform.json), [LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html), [2.x to 3.0 migration](https://docs.espressif.com/projects/arduino-esp32/en/latest/migration_guides/2.x_to_3.0.html)
- Current `WiFiUDP` is an alias for `NetworkUDP`. Its receive/send interfaces include `begin`, `parsePacket`, `read`, `remoteIP`, `remotePort`, `beginPacket`, `write`, and `endPacket`. UDP needs application-level sequence matching, packet validation, timeouts and recovery because packets can be lost or reordered. Avoid relying on `flush()` to discard input; the current API has `clear()`. [Espressif WiFiUDP header](https://github.com/espressif/arduino-esp32/blob/master/libraries/WiFi/src/WiFiUdp.h), [NetworkUDP header](https://github.com/espressif/arduino-esp32/blob/master/libraries/Network/src/NetworkUdp.h)

## Physical acceptance procedure

The brief gives qualitative accuracy and responsiveness requirements. The numerical targets below are proposed engineering gates, not university-specified limits or claimed results. Record actual measurements and revise tracking parameters from evidence. Passing simulation or software tests does not demonstrate physical performance.

1. **Inspect and bring up one box.** Record board, sensor and servo models, battery capacity, regulator ratings, wiring, firmware revision and measured rail voltages. Centre the unloaded servo first, then fit the bracket and verify sweep clearance. Measure echo voltage before connecting it to the ESP32. Compare ranging to a flat board at 0.25, 0.50, 1.00, 1.50 and 2.00 m; log 30 samples at each position and all timeout counts. Repeat for the other box.
2. **Calibrate geometry and room.** Measure acoustic centre positions, baseline and sensor height. Align and record servo zero offsets/directions using a marked centre line. Sweep the empty room and save static background returns for all commanded bearings. Verify that foreground filtering uses the dense calibrated bearing profile and that a changed geometry requires recalibration. Verify acquisition with one person standing at centre. Repeat after moving either box or furniture. Range correction based on a flat board does not remove human-body reflection bias.
3. **Check coverage and stationary accuracy.** Mark `x = 0.05, 0.40, 0.75, 1.10, 1.45 m` and `y = 0.65, 1.00, 1.35, 1.70, 1.95 m` (25 interior points). Also test all four exact field corners and points along each boundary. At each point stand for 10 seconds after acquisition, then repeat side-on and with different clothing. Log estimated position, ground truth marker, age and estimated acquisition-time skew of each range pair, tracking state and invalid counts. Initial gate: at least 95% valid updates after acquisition and 95th-percentile position error no more than 0.15 m at every point. Report worst points and points that never acquire separately; an average alone can hide uncovered corners.
4. **Check motion and latency.** Walk lateral, front-to-back and diagonal paths, including each edge; repeat 10 times. Record synchronized video of floor marks and the on-screen dot, plus timestamped telemetry. Initial gate: 95th-percentile motion-to-visible-dot latency below 250 ms while locked, with no unsupported jumps. Separately record initial acquisition and reacquisition duration at every test position, including a full configured sweep. Expect that sweeps may take many seconds; measure rather than claim an acquisition bound. Confirm that range pairs more than 0.15 seconds apart are rejected with the default configuration. That limit is a rejection rule, not a measured display-latency guarantee.
5. **Check interference and recovery.** Run both boxes in normal alternating operation, then observe operation with walls/furniture near the beam edges. Interrupt one box's power, block a transducer, disconnect Wi-Fi, inject malformed or delayed packets in the software tests, and restart either endpoint. The dot must disappear or clearly indicate unavailable tracking when data becomes stale or invalid. Recovery must not require restarting the PC visualizer. Test automatic discovery and configured IP addresses after a prolonged outage. Missing data must not silently look like a fresh valid position.
6. **Check the dead-zone state.** At several lateral positions, walk slowly across the 0.60 m line and back, including near both outer edges; use a spotter and start with generous screen clearance. Record the raw position, dead-zone state, onset and release. The diagnostic flag reflects accepted raw positions with a 2 mm quantization tolerance; the current display has no warning or alarm logic. Initial gate: classify a detected crossing within 250 ms while tracking. Repeat after momentary loss of one range and while the servos reacquire. Check approaches to the region behind the sensor baseline. If any approach is invisible, record that coverage failure: software cannot turn a missing echo into a verified person position. This test validates diagnostic state, not the deferred finished-product alarm.
7. **Check battery and construction.** Run both boxes independently on their four NiMH cells for more than 60 minutes with the real tracking loop, frequent servo movements and Wi-Fi traffic. Record start/end cell/pack voltage, average current, peak behaviour, temperature, brownouts and resets. Capacity divided by nominal current is an estimate; use the timed run as evidence. Measure the final enclosures and inspect removable connections and sweep clearance.
8. **Check the dot visualizer.** Launch the documented application on the intended PC, join the phone hotspot the boxes use (the one supported network) and permit incoming UDP 4210 in the firewall. Calibrate, acquire a person, move left/right and toward/away from the screen, and verify the corresponding dot movement on the black background. Resize the window, lose/recover a sensor and restart. Repeat with simulator input as a separate software check. An installer and the full game are outside this stage.

Keep the test date, commit hash, configuration, raw readings and failures with each result. Firmware compilation validates syntax and linkage. Only physical measurements establish whether this tracking subsystem meets its applicable hardware and tracking requirements; completing it does not establish delivery of the full project brief.
