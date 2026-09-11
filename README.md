# Body Whack

A two-node, wireless full-body Whack-a-Mole prototype for the ES3 project.
Each ESP32 rotates one ultrasonic sensor with a positional servo. A Windows PC
requests alternating measurements, calculates a two-dimensional position, and
runs the game. A simulator exercises the same measurement and tracking path.

Implementation is in progress. Hardware defaults are provisional until board,
sensor, and servo models are confirmed. Physical accuracy, responsiveness,
battery runtime, and the dead-zone warning require measured validation.

## Layout

- `firmware/`: identical ESP32 firmware with separate left/right build targets
- `whack/`: desktop controller, tracking, protocol, and game
- `tests/`: geometry, protocol, transport, and game regression checks
- `docs/`: requirements, architecture, and commissioning instructions
- `example-code/`: unchanged third-party study reference; see its provenance/license
- `graphify-out/`: persistent project knowledge graph
