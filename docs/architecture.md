# Architecture and decisions

## Geometry

Coordinates are metres: x increases from the left edge (0) to the right edge
(1.5), y increases away from the screen wall. Both sensor acoustic centres must
be at the same measured y coordinate, default 0.20 m. Their default x coordinates
are 0 and 1.5 m. The playable rectangle is x=0..1.5, y=0.60..2.00. Sensor boxes
and all other hardware must remain within 0.50 m of the wall.

Two ranges to a common reflecting target define two circle intersections. The
controller chooses the intersection in front of the sensors. This model assumes
both echoes belong to the same player; ultrasonic beams often return different
body surfaces or walls. Range geometry alone cannot prove target identity.
Bearing gates, timeout rejection, acquisition sweeps, smoothing, and speed checks
reduce bad fixes but do not replace physical validation.

A servo carries each sensor; it does not strike the player or a mechanical mole.
When tracked, both sensors point toward the last estimated position. When lost,
they scan the same sequence of candidate positions in the playing area. Angles
are measured counter-clockwise from +x (90 degrees faces away from the wall).
Physical centre offsets and reverse mounting are set in firmware.

## Scheduling and protocol

PC binds UDP 4210. Nodes bind UDP 4211 and broadcast a discovery message every
2 seconds. Both nodes and PC join the same local Wi-Fi network; client isolation
must be off. Only one measurement command is outstanding. Node 0 is measured,
then node 1, with at least 65 ms between responses and subsequent requests.
Each node waits for its servo to settle before its bounded ultrasonic pulse.
This deliberately prioritises distinct echoes over a promised frame rate.

ASCII datagrams, no trailing fields, protocol version WM1:

```
WM1 HELLO <node>
WM1 MEASURE <seq> <angle_mdeg>
WM1 RANGE <node> <seq> <actual_angle_mdeg> <distance_mm> <status>
```

`node`: 0 or 1. `seq`: 1..4294967295. `angle_mdeg`: 0..180000.
`distance_mm`: integer 0..4500; 0 on errors. `status`: OK, TIMEOUT, INVALID.
A successful range is >=20 mm. A reply must match the outstanding node,
sequence, sender address and commanded angle. Replies never trigger another
ping themselves. Repeated command sequences return a cached result or wait
for the active result, never a second physical measurement.

This is an isolated-lab protocol, with no authentication or encryption. It is
not intended for hostile networks. Use a dedicated local Wi-Fi network.

## Failure behaviour

Missing nodes, invalid measurements, impossible intersections, stale pairs,
and out-of-bounds positions suspend scoring. The dead-zone decision uses the
raw position before display smoothing. Tracking loss also visibly suspends play.
An ultrasonic blind spot can prevent both localization and a dead-zone warning;
the software warning is not a safety-rated collision prevention system.

## Reference

The supplied study code uses a different board/UART sensor arrangement and a
framebuffer display. Its separation of acquisition, noise filtering, and rendering
in `example-code/tracker.py` informed the module boundaries. The new implementation
uses an independent UDP protocol and two-circle geometry.
