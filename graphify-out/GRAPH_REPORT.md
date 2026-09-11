# Graph Report - /home/cam/Desktop/whack_whack_gpt  (2026-09-12)

## Corpus Check
- 33 files · ~56,963 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 305 nodes · 575 edges · 19 communities (16 shown, 3 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 35 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Tracking Subsystem Design|Tracking Subsystem Design]]
- [[_COMMUNITY_Acquisition and Calibration|Acquisition and Calibration]]
- [[_COMMUNITY_Assignment and Study Reference|Assignment and Study Reference]]
- [[_COMMUNITY_UDP Protocol and Transport|UDP Protocol and Transport]]
- [[_COMMUNITY_Position Estimation and Validation|Position Estimation and Validation]]
- [[_COMMUNITY_ESP32 Servo and Ranging|ESP32 Servo and Ranging]]
- [[_COMMUNITY_Vendored Framebuffer Tracker|Vendored Framebuffer Tracker]]
- [[_COMMUNITY_Black-Screen Dot Visualizer|Black-Screen Dot Visualizer]]
- [[_COMMUNITY_UDP Sensor Emulator|UDP Sensor Emulator]]
- [[_COMMUNITY_Tracking Geometry Configuration|Tracking Geometry Configuration]]
- [[_COMMUNITY_Reference Board Pinout|Reference Board Pinout]]
- [[_COMMUNITY_UDP Integration Tests|UDP Integration Tests]]
- [[_COMMUNITY_Reference Sensor Photograph|Reference Sensor Photograph]]
- [[_COMMUNITY_Reference Animation|Reference Animation]]
- [[_COMMUNITY_Firmware Command Parser|Firmware Command Parser]]
- [[_COMMUNITY_Tracker Python Package|Tracker Python Package]]

## God Nodes (most connected - your core abstractions)
1. `Geometry` - 32 edges
2. `Controller` - 30 edges
3. `SimulatedTransport` - 21 edges
4. `Range` - 20 edges
5. `UdpTransport` - 17 edges
6. `Two-node body tracker` - 17 edges
7. `Tracker` - 16 edges
8. `Clock` - 15 edges
9. `TrackerWindow` - 15 edges
10. `Whack-a-Mole project brief v2.1` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Background calibration` --semantically_similar_to--> `Ultrasound-only person tracking`  [INFERRED] [semantically similar]
  /home/cam/Desktop/whack_whack_gpt/example-code/README.md → /home/cam/Desktop/whack_whack_gpt/ES3 Whack-a-Mole v2.1.pdf
- `Clock` --uses--> `Range`  [INFERRED]
  tests/test_controller.py → whack/protocol.py
- `Clock` --uses--> `Geometry`  [INFERRED]
  tests/test_controller.py → whack/tracking.py
- `InjectedTransport` --uses--> `Range`  [INFERRED]
  tests/test_controller.py → whack/protocol.py
- `InjectedTransport` --uses--> `Geometry`  [INFERRED]
  tests/test_controller.py → whack/tracking.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Body-controlled gameplay loop** — es3_tracking, es3_boxes, es3_game, es3_windows [EXTRACTED 1.00]
- **Sensor enclosure and placement constraints** — es3_boxes, es3_batteries, es3_area, es3_construction [EXTRACTED 1.00]
- **Wireless body position pipeline** — tracking_pc_coordinator, tracking_ping_schedule, tracking_circle_localization, tracking_consistency_filters, tracking_dot_display [EXTRACTED 1.00]
- **Self-contained servo sensor box** — tracking_esp32_boards, tracking_positional_servo, tracking_rcwl1601, tracking_power_design, tracking_enclosure, tracking_battery_runtime [EXTRACTED 1.00]

## Communities (19 total, 3 thin omitted)

### Community 0 - "Tracking Subsystem Design"
Cohesion: 0.07
Nodes (54): Interior and boundary accuracy trials, Twenty-position acquisition sweep, Four-AA NiMH battery runtime, Bounded trigger/echo acquisition, ES3 Whack-a-Mole v2.1 project brief, Calibrated bearing selection, Persistent calibration.local.json profile, Forward two-circle localization (+46 more)

### Community 1 - "Acquisition and Calibration"
Cohesion: 0.14
Nodes (8): Clock, ControllerTests, InjectedTransport, run(), Controller, Snapshot, Ideal single reflector with beam gates and servo delay; not a hardware model., SimulatedTransport

### Community 2 - "Assignment and Study Reference"
Cohesion: 0.09
Nodes (31): Playing area geometry, Four-AA NiMH battery power, Standalone wireless sensor boxes, Whack-a-Mole project brief v2.1, Project component budget, Engineering Rigour and Change Log, Non-destructive supplied components, 60 cm dead-zone warning (+23 more)

### Community 3 - "UDP Protocol and Transport"
Cohesion: 0.15
Nodes (12): ProtocolTests, TransportTests, main(), Bench one sensor/servo: python -m tools.probe_node --help., Single-flight acquisition scheduler; all network work runs without blocking Tk., Hello, measure(), parse() (+4 more)

### Community 4 - "Position Estimation and Validation"
Cohesion: 0.15
Nodes (11): samples(), TrackingTests, Integration against independent virtual ESP32 processes over real UDP sockets., main(), Run with python -m whack --simulate, or omit --simulate for hardware., Geometry, load_geometry(), locate() (+3 more)

### Community 5 - "ESP32 Servo and Ranging"
Cohesion: 0.16
Nodes (24): Command, IPAddress, finish(), handle_command(), loop(), measure_if_ready(), network_tick(), Pending (+16 more)

### Community 6 - "Vendored Framebuffer Tracker"
Cohesion: 0.15
Nodes (9): FastFramebuffer, FastSensorReader, main(), Check if object is within sensor range and detectable, Apply noise filtering and movement threshold, Clear back buffer to black, Draw box in back buffer only, Swap back buffer to front (no flicker) (+1 more)

### Community 7 - "Black-Screen Dot Visualizer"
Cohesion: 0.18
Nodes (4): Tk, Black-screen visualizer for current dual-ultrasonic position estimates., Display one current position; acquisition is owned by the controller.      Coord, TrackerWindow

### Community 8 - "UDP Sensor Emulator"
Cohesion: 0.23
Nodes (6): main(), Node, parse_command(), Pending, Match the firmware's integer-only, bounded command syntax., Simulator

### Community 9 - "Tracking Geometry Configuration"
Cohesion: 0.15
Nodes (12): beam_half_angle_deg, far_y, left_offset_m, left_x, max_pair_skew_s, max_speed_m_s, near_y, right_offset_m (+4 more)

### Community 10 - "Reference Board Pinout"
Cohesion: 0.22
Nodes (9): 3V3(OUT), GND, GPIO1_C4_d, GPIO1_C5_d, GPIO1_C6_d, GPIO1_D0_d, GPIO1_D1_d, VBUS (+1 more)

### Community 12 - "Reference Sensor Photograph"
Cohesion: 0.29
Nodes (7): Four-pin sensor connector, GPIO, IIC, UART and 1-WIRE mode table, HC-SR04 ultrasonic sensor module, HC-SR04 sensor front and rear photograph, RCWL-9610A board design, Ultrasonic receiver (R), Ultrasonic transmitter (T)

### Community 13 - "Reference Animation"
Cohesion: 0.67
Nodes (3): Animated Square Demo, Black Playfield, Moving Cyan Square

## Knowledge Gaps
- **38 isolated node(s):** `width`, `near_y`, `far_y`, `left_x`, `right_x` (+33 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Acquisition and Calibration` to `UDP Protocol and Transport`, `UDP Integration Tests`, `Position Estimation and Validation`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `TrackerWindow` connect `Black-Screen Dot Visualizer` to `Position Estimation and Validation`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `Geometry` connect `Position Estimation and Validation` to `UDP Protocol and Transport`, `Acquisition and Calibration`, `UDP Integration Tests`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Geometry` (e.g. with `Clock` and `ControllerTests`) actually correct?**
  _`Geometry` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Controller` (e.g. with `Clock` and `ControllerTests`) actually correct?**
  _`Controller` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `SimulatedTransport` (e.g. with `Clock` and `ControllerTests`) actually correct?**
  _`SimulatedTransport` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `Range` (e.g. with `Clock` and `ControllerTests`) actually correct?**
  _`Range` has 7 INFERRED edges - model-reasoned connections that need verification._
## Scope and extraction limitations

Current implementation scope is the hardware tracking subsystem and black-screen dot visualizer. Gameplay concepts in the graph belong to the assignment and are deferred, not implemented. Agent token usage and monetary cost are unavailable; zero token fields above are placeholders, not measured usage. The original eight-page PDF was text-extracted; embedded figures and revision colours were not visually reviewed. Remote README images were not fetched. Physical hardware performance is unverified.
