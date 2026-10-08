# HC-SR04 bench test record

Started: 2026-09-14 (Australia/Sydney)

## Equipment and configuration

- Sensor: HC-SR04, confirmed by user. Label the two physical sensors A and B.
- Board: Freenove ESP32 board with ESP32-WROOM-32E, identified from the user's product image.
- Sensor test pins: TRIG GPIO32; ECHO GPIO35.
- Intended ECHO divider: 10 kΩ from ECHO to GPIO35 junction; two 10 kΩ resistors in series from that junction to ESP32 ground.
- Sensor and ESP32 share ground. Servo power disconnected for the initial bench test.
- Test sketch: `firmware/arduino/sensor_test/sensor_test.ino`; USB serial at 115200 baud, approximately two readings per second.
- The user also received a shortened sketch with the same pins and measurement calculation. Confirm the uploaded version when collecting measurements.
- Supply voltage and divider output have not been measured/reported.
- Compile checks passed for the standalone bench sketch and both project node builds. These are software checks, not physical accuracy results.

## Troubleshooting observations

| Test | Evidence | Result / interpretation |
| --- | --- | --- |
| Upload using Arduino Snap | User screenshot: Python shared library load failure; exit status 255 | Build-tool failure; no sensor conclusion |
| Subsequent uploaded sensor test | User screenshots: repeated `ECHO already HIGH` | Sketch runs; GPIO35 reads HIGH before triggering |
| Disconnect sensor ECHO jumper from A10, retain divider and ground | User confirmed same HIGH message and supplied screenshot | HIGH persisted with sensor output disconnected; breadboard/ground/pin path needs isolation |
| Remove breadboard connection from GPIO35 and connect GPIO35 directly to ESP32 GND | User replied "it works now" | Exact output from the direct-ground diagnostic was not supplied |
| Reconnect sensor for distance measurement | User explicitly confirmed "Distance readings with sensor reconnected" | Basic ranging reported working; numerical output and accuracy still pending |

Basic ranging is confirmed by the user's report and the first 30-reading batch at 25 cm. No sensor reliability pass has been established. The exact wiring change that resolved the persistent HIGH reading has not been recorded.

## Setup for distance testing

1. Confirm GPIO35 reads LOW with the direct-ground diagnostic. `NO ECHO` is the expected diagnostic output, not a successful distance measurement.
2. Disconnect USB and external power. Remove the temporary GPIO35-to-GND jumper, restore the resistor divider and sensor connections, and verify common ground.
3. Power only one sensor setup for this stage. Keep the servo unpowered and the second sensor inactive.
4. Fix the sensor in place. Use a large, rigid, flat target facing it squarely. Record target dimensions and keep the same target throughout.
5. Measure the true gap from the front faces of the sensor's metal transducers to the target with a tape/ruler. Keep other objects out of the beam.
6. Start at 25 cm. After the target is stationary, collect 30 consecutive measurement lines, including every error line. Do not discard poor readings or select only good ones.
7. Repeat at 50, 100, 150 and 200 cm. Reposition the target and repeat the full series three times for each sensor if time permits; record each run separately.
8. Keep target size, mounting, power supply and firmware consistent between sensors. Record changes, room temperature if available, and any resets.

## Results awaiting measurements

Rows marked Pending are planned tests, not completed results. Completed rows link to stored evidence below; add rows for repeated runs.

| Sensor | Run | True distance (cm) | Attempts collected | Distance readings | NO ECHO | ECHO HIGH | Mean (cm) | Bias (cm) | SD (cm) | Min–max (cm) | Mean absolute error (cm) | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 1 | 25 | 30 | 30 | 0 | 0 | 25.3633 | +0.3633 | 0.4056 | 24.5–26.3 | 0.4300 | Recorded |
| A | 1 | 50 | 30 | 30 | 0 | 0 | 54.6267 | +4.6267 | 7.0197 | 48.0–68.0 | 5.3733 | Recorded; repeat needed |
| A | 1 | 100 | — | — | — | — | — | — | — | — | — | Pending |
| A | 1 | 150 | — | — | — | — | — | — | — | — | — | Pending |
| A | 1 | 200 | — | — | — | — | — | — | — | — | — | Pending |
| B | 1 | 25 | — | — | — | — | — | — | — | — | — | Pending |
| B | 1 | 50 | — | — | — | — | — | — | — | — | — | Pending |
| B | 1 | 100 | — | — | — | — | — | — | — | — | — | Pending |
| B | 1 | 150 | — | — | — | — | — | — | — | — | — | Pending |
| B | 1 | 200 | — | — | — | — | — | — | — | — | — | Pending |

## Analysis rules

- Preserve raw serial lines with sensor ID, run, true distance, and conditions before calculating summaries.
- Bias = mean measured distance minus true distance; report its sign.
- Mean absolute error = mean of the absolute error of each numerical distance reading.
- Repeatability = sample standard deviation of numerical distance readings (at least two required), plus minimum and maximum.
- Report distance-return rate and each error count separately. A numerical return can still be inaccurate; do not call all numerical readings accurate or valid.
- If no numerical readings occur, leave distance statistics unavailable rather than substituting zero.
- No standalone sensor pass/fail threshold has been agreed. Establish application-specific criteria before claiming a pass.
- Flat-target measurements do not establish accuracy on a person or reliability with moving servos, two sensors, Wi-Fi, or battery power. Follow the broader acceptance procedure in `requirements.md` after this stage.

## Raw readings

First batch: [sensor A at 25 cm](../evidence/week8/results.xlsx), 30 consecutive numerical returns. Raw CSV and serial log are retained beside the Excel report. Next batch: sensor A at a measured 50 cm.

## Requested bench-test range limit

- The Arduino bench sketch now accepts computed distances from 2 to 200 cm inclusive. Other completed echoes print `OUT OF RANGE` with no accepted numerical distance. Missing echoes still print `NO ECHO`.
- This is software filtering; the sensor still emits its normal pulse and can receive echoes from farther objects. The finite echo wait is retained.
- The full project node firmware is unchanged by this bench limit. The default playing rectangle reaches y=2.00 m from the wall, with sensor centres at y=0.20 m separated by 1.50 m. The opposite far corner is sqrt(1.50^2 + 1.80^2) = 2.343 m from either opposite sensor; a 2 m radial limit cannot cover the whole rectangle.
- Range limiting is not calibration. Calibration coefficients remain unset pending actual known-distance measurements. Filtering can hide positive error near 200 cm: record all out-of-range results, and use an uncapped diagnostic run if necessary to measure calibration bias at the boundary.
- Excel now includes an OUT OF RANGE count and a Calibration notes sheet. The first known-distance batch at 25 cm has now been recorded; no correction has been applied.

## First batch review — 2026-09-14

- Capture at 21:52:39 timed out after 60 seconds with zero recognized attempts; this is an incomplete capture, not 30 failed sensor measurements. Its evidence is preserved.
- Capture at 21:55:43 completed with 30/30 numerical returns and no recorded error statuses. Mean 25.3633 cm, bias +0.3633 cm, sample SD 0.4056 cm, range 24.5–26.3 cm, MAE 0.4300 cm.
- Statistics were independently recomputed from the raw CSV and checked against run.json. The consolidated Excel workbook now contains these 30 readings.
- Do not apply a fixed calibration offset from this single distance. Next, collect sensor A at 50 cm with the same flat target and setup.

## Sensor A at 50 cm — first capture

- Evidence: [Excel report](../evidence/week7/results.xlsx), with raw CSV and serial log alongside.
- 30/30 numerical returns; no error statuses. Mean 54.6267 cm, bias +4.6267 cm, sample SD 7.0197 cm, range 48.0–68.0 cm, MAE 5.3733 cm. Recomputed mean from CSV agrees with run.json.
- First five readings were 67.2–68.0 cm, then readings declined progressively toward 50 cm and ended around 49 cm. Movement or changing reflection is a possible explanation; cause is unconfirmed. Do not infer a fixed +4.63 cm calibration offset from this run.
- Keep the complete run as evidence. Repeat at a physically measured 50 cm with sensor and target secured and motionless before starting the command. Do not retrospectively select only the last readings.

## Test programme paused

The user deferred further distance reliability/calibration tests to work on live two-servo player tracking and dot rendering. All completed measurements and the requested repeat at 50 cm remain recorded above; no additional measurements or calibration coefficients are inferred. Live setup is documented in `live-tracker-setup.md`. The empty-area background scan and servo mounting alignment are setup steps for tracking, separate from these deferred accuracy tests.
