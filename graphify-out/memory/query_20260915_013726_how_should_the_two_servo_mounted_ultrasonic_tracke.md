---
type: "query"
date: "2026-09-15T01:37:26.022495+00:00"
question: "How should the two servo-mounted ultrasonic trackers find and follow one player with low delay?"
contributor: "graphify"
source_nodes: ["Controller", "Geometry", "write_servo"]
---

# Q: How should the two servo-mounted ultrasonic trackers find and follow one player with low delay?

## Answer

Current controller and firmware serialize aiming and ranging with 60 ms minimum settle per node and 65 ms after each reply: 250 ms per steady pair before echoes and networking. Default 39-aim cyclic search has about 14.7 seconds of programmed waits. Proposed workflow in docs/player-tracking-workflow.md: empty reference, known centre start or bounded search, paired confirmation, concurrent servo aiming, exclusive alternating pings, timestamp-aware position and velocity estimation, bounded prediction and local reacquisition. These are design proposals, not implemented or physically verified performance. Preserve home and school operation; user uploads firmware manually.

## Source Nodes

- Controller
- Geometry
- write_servo