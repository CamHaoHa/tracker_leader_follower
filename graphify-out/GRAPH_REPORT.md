# Graph Report - /home/cam/Desktop/whack_whack_gpt  (2026-09-12)

## Corpus Check
- Corpus is ~44,337 words - fits in a single context window. You may not need a graph.

## Summary
- 73 nodes · 97 edges · 11 communities (10 shown, 1 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Reference Tracker Architecture|Reference Tracker Architecture]]
- [[_COMMUNITY_Framebuffer Rendering|Framebuffer Rendering]]
- [[_COMMUNITY_Sensor Reading and Filtering|Sensor Reading and Filtering]]
- [[_COMMUNITY_Board Pinout|Board Pinout]]
- [[_COMMUNITY_Sensor Module Photograph|Sensor Module Photograph]]
- [[_COMMUNITY_Project Hardware Constraints|Project Hardware Constraints]]
- [[_COMMUNITY_Tracking and Playing Area|Tracking and Playing Area]]
- [[_COMMUNITY_Animated Tracking Demo|Animated Tracking Demo]]
- [[_COMMUNITY_Engineering and Design Milestones|Engineering and Design Milestones]]
- [[_COMMUNITY_Final Game Delivery|Final Game Delivery]]
- [[_COMMUNITY_Wireless Sensor Power|Wireless Sensor Power]]

## God Nodes (most connected - your core abstractions)
1. `Whack-a-Mole project brief v2.1` - 15 edges
2. `Dual-sensor reference tracker` - 13 edges
3. `main()` - 9 edges
4. `FastFramebuffer` - 8 edges
5. `Pico Board Pinout Diagram` - 8 edges
6. `SmartTracker` - 7 edges
7. `Ultrasound-only person tracking` - 7 edges
8. `HC-SR04 ultrasonic sensor module` - 5 edges
9. `FastSensorReader` - 4 edges
10. `Full-body Whack-a-Mole game` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Background calibration` --semantically_similar_to--> `Ultrasound-only person tracking`  [INFERRED] [semantically similar]
  example-code/README.md → ES3 Whack-a-Mole v2.1.pdf
- `Movement noise filtering` --conceptually_related_to--> `Ultrasound-only person tracking`  [INFERRED]
  example-code/README.md → ES3 Whack-a-Mole v2.1.pdf
- `Vendored study-only reference` --references--> `Dual-sensor reference tracker`  [EXTRACTED]
  example-code/UPSTREAM.md → example-code/README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Body-controlled gameplay loop** — es3_tracking, es3_boxes, es3_game, es3_windows [EXTRACTED 1.00]
- **Sensor enclosure and placement constraints** — es3_boxes, es3_batteries, es3_area, es3_construction [EXTRACTED 1.00]

## Communities (11 total, 1 thin omitted)

### Community 0 - "Reference Tracker Architecture"
Cohesion: 0.18
Nodes (12): Double-buffered framebuffer rendering, HC-SR04 UART sensors, Luckfox Pico Mini B, pyserial, Reference tracking parameters, Weighted position smoothing, Dual-sensor reference tracker, UART ranging protocol (+4 more)

### Community 1 - "Framebuffer Rendering"
Cohesion: 0.27
Nodes (5): FastFramebuffer, main(), Clear back buffer to black, Draw box in back buffer only, Swap back buffer to front (no flicker)

### Community 2 - "Sensor Reading and Filtering"
Cohesion: 0.25
Nodes (4): FastSensorReader, Check if object is within sensor range and detectable, Apply noise filtering and movement threshold, SmartTracker

### Community 3 - "Board Pinout"
Cohesion: 0.22
Nodes (9): 3V3(OUT), GND, GPIO1_C4_d, GPIO1_C5_d, GPIO1_C6_d, GPIO1_D0_d, GPIO1_D1_d, VBUS (+1 more)

### Community 4 - "Sensor Module Photograph"
Cohesion: 0.29
Nodes (7): Four-pin sensor connector, GPIO, IIC, UART and 1-WIRE mode table, HC-SR04 ultrasonic sensor module, HC-SR04 sensor front and rear photograph, RCWL-9610A board design, Ultrasonic receiver (R), Ultrasonic transmitter (T)

### Community 5 - "Project Hardware Constraints"
Cohesion: 0.53
Nodes (6): Whack-a-Mole project brief v2.1, Project component budget, Non-destructive supplied components, ESP32 processor boards, RCWL-1601 ultrasound sensors, Approved component suppliers

### Community 6 - "Tracking and Playing Area"
Cohesion: 0.40
Nodes (5): Playing area geometry, 60 cm dead-zone warning, Ultrasound-only person tracking, Background calibration, Movement noise filtering

### Community 7 - "Animated Tracking Demo"
Cohesion: 0.67
Nodes (3): Animated Square Demo, Black Playfield, Moving Cyan Square

### Community 8 - "Engineering and Design Milestones"
Cohesion: 0.67
Nodes (3): Engineering Rigour and Change Log, Sprint 1 MVP, Sprint 2 Critical Design Review

### Community 9 - "Final Game Delivery"
Cohesion: 0.67
Nodes (3): Sprint 3 Final Product, Full-body Whack-a-Mole game, Installable Windows game package

## Knowledge Gaps
- **16 isolated node(s):** `themrleon ultrasonic-2d-position-tracker`, `Moving Cyan Square`, `Black Playfield`, `HC-SR04 sensor front and rear photograph`, `Ultrasonic transmitter (T)` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Dual-sensor reference tracker` connect `Reference Tracker Architecture` to `Framebuffer Rendering`, `Tracking and Playing Area`?**
  _High betweenness centrality (0.373) - this node is a cross-community bridge._
- **Why does `Ultrasound-only person tracking` connect `Tracking and Playing Area` to `Final Game Delivery`, `Wireless Sensor Power`, `Project Hardware Constraints`?**
  _High betweenness centrality (0.233) - this node is a cross-community bridge._
- **Why does `Whack-a-Mole project brief v2.1` connect `Project Hardware Constraints` to `Engineering and Design Milestones`, `Final Game Delivery`, `Wireless Sensor Power`, `Tracking and Playing Area`?**
  _High betweenness centrality (0.177) - this node is a cross-community bridge._
- **What connects `Clear back buffer to black`, `Draw box in back buffer only`, `Swap back buffer to front (no flicker)` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._
## Extraction limitations

Agent token usage and monetary cost are unavailable in this environment. Any zero token figures above are placeholders, not measured usage. All eight PDF pages were text-extracted; embedded figures and revision highlight colours were not visually reviewed. Remote README images were not fetched.
