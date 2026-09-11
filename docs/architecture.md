# Tracking subsystem architecture

The current scope is ultrasound body tracking and a black-screen dot visualizer.
The full assignment's gameplay and installer work are deferred.

## Layout and coordinates

Each ESP32 controls one positional servo carrying one ultrasonic sensor. The
PC coordinates measurements and performs localization. Coordinates are metres:
`x` increases from the left edge (0) to the right edge (1.5), `y` increases away
from the screen wall. Both acoustic centres have the same measured `y`, default
0.20 m, and default `x` coordinates 0 and 1.5 m. The tracking rectangle is
`x=0..1.5`, `y=0.60..2.00`. The screen maps near depth to top and far depth to
bottom. All hardware must remain within 0.50 m of the wall.

Two ranges to a common reflecting target define two circle intersections. The
PC selects the forward intersection. Both echoes must belong to the same
person; walls, arms, clothing and different torso surfaces violate this model.
Servo aim is not a measured target bearing. Bearing gates, background rejection,
range-pair timing and a speed gate reject some errors, but cannot prove target
identity. See `docs/requirements.md` for physical validation.

The servo command is the angle counter-clockwise from +x: 90 degrees faces away
from the wall. Firmware maps this to pulse width using each mount's reversal,
centre trim and travel limits. Position is open-loop; there is no servo encoder.

## Acquisition, calibration and filtering

An empty-area profile samples 20 candidate positions, three pairs per position.
The sweep includes both near corners, the far region and a row in the warning
zone. Calibration has a three-second lead-in. The median of successful echoes
is stored for each bearing; fewer than two successes records no background echo.
An invalid servo response or a lost packet fails calibration. A missing echo
alone cannot distinguish clear space from a disconnected sensor, so validate
sensors against a board first.

During tracking, each commanded angle snaps to a bearing in that node's profile.
A foreground echo must be at least 0.15 m closer than the stored room background,
or the profile must have no return there. Unprofiled angles cannot bypass the
filter. Simulation uses an ideal single reflector and does not require a profile.

Accepted ranges must be within 250 ms of each other by default. A long second
servo movement causes a repeat at the same aim point after settling. The
scheduler then resumes normal acquisition. Circle geometry, beam consistency,
speed and range checks precede a time-based display filter. The raw estimate
controls the warning so display smoothing cannot postpone it. Warning release
requires 3 cm beyond the near boundary. Calibration geometry changes invalidate
old profiles.

## Scheduling and wire protocol

PC binds UDP 4210. Nodes bind UDP 4211 and broadcast discovery every 2 seconds.
All devices join the same local Wi-Fi network. Only one command is outstanding:
node 0, then node 1, with at least 65ms after a response before the next command.
Node servo settling is bounded to 700 ms and echo waiting to 25 ms. A command times
out after 1 s, followed by a 100 ms guard; late replies are ignored. No node pings
without a request. Tracking-loss sweeps trade reacquisition speed for coverage.

Strict ASCII datagrams:

```
WM1 HELLO <node>
WM1 MEASURE <seq> <angle_mdeg>
WM1 RANGE <node> <seq> <actual_angle_mdeg> <distance_mm> <status>
```

- `node`: 0 or 1; `seq`: 1..4294967295, seeded from host time and incremented.
- `angle_mdeg`: 0..180000; 90,000 means forward.
- `distance_mm`: 20..4000 for the firmware; 0 on errors.
- `status`: OK, TIMEOUT or INVALID.

Replies must match the pending node, sequence and source address. Successful
replies must also match the requested angle; an INVALID response may report the
unchanged bearing if travel limits reject movement. Angles describe calibrated
commands, not independently observed servo positions. Cached command sequences
never re-ping. Nodes release host ownership after 30 seconds of inactivity.

Discovered nodes expire after 6 seconds without evidence of life. Duplicate IDs
suspend that node. Explicitly configured IP addresses remain usable across
outages. Only one PC should coordinate the nodes. There is no protocol
authentication; use a dedicated trusted local network.

## Failure behaviour and limits

The dot disappears immediately after an invalid pair, or after 1 second without
a new accepted fix. Missing sensors, impossible intersections and out-of-bounds
positions are shown in diagnostics. A detected near-wall position activates a
visual warning and throttled system bell. Behind the sensor baseline, the
forward-intersection model has no coverage. Loss of an echo must be shown as
loss of tracking, not inferred to be a safe person position.

Firmware runs independently on each ESP32, while the PC owns global sequencing.
Simulations validate timing and message handling; only actual body tests establish
accuracy, usable speed, acquisition delay, interference and battery runtime.

## Study reference

`example-code/tracker.py` separates acquisition, filtering and rendering on a
different board/UART configuration. Its black-background position display is the
visual reference. The new tracker uses its own UDP protocol and circle geometry;
the vendored files remain unchanged.
