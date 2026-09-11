# Engineering change log

## Baseline

- Preserved the assignment, read-only study implementation, and initial graph.
- Chose one sensor/servo per ESP32 with PC-controlled alternating measurements.
- Recorded coordinate conventions, wire protocol, assumptions, and failure states.
- Validation planned: native tests, UDP simulation, both firmware builds, then
  measured bench and playing-area trials using the actual components.

## ESP32 node firmware

- Added pinned left/right firmware builds, configurable servo calibration,
  strict versioned datagrams, echo timeouts, reconnect and duplicate suppression.
- Both ESP32 targets compiled; native parser and servo-mapping tests passed.
- No physical boards were flashed. Wiring/servo model confirmation remains open.

## Tracking subsystem and dot visualizer

- Current delivery scope: hardware tracking and black-screen cyan dot only.
- Added PC-controlled alternating acquisition, circle localization, background
  calibration, configurable geometry, freshness/beam/speed filters and diagnostics.
- Review corrected missing near-corner scan coverage, stale range pairing,
  background-filter bypass and fixed-address recovery after an outage.
- Added ideal sensor simulation plus real UDP emulation and failure tests.
- Hardware accuracy, servo response, body reflection behaviour and battery runtime
  remain unmeasured; record results and revision using the acceptance procedure.
