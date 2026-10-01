# Tracking subsystem architecture

Two ESP32 nodes each operate one positional pan servo and one ultrasonic sensor.
The laptop owns coordination, background calibration, localization, motion
prediction and rendering. The output is one cyan spot on a black screen.
Gameplay and installer work are outside this stage.

## Components

| Component | Responsibility |
| --- | --- |
| `firmware/src/main.cpp` | Phone-hotspot Wi-Fi connection, calibrated servo commands, bounded echo acquisition, WM2 protocol |
| `whack/protocol.py` | Strict, versioned ASCII packet formats |
| `whack/transport.py` | Nonblocking UDP discovery and a timed point-reflector simulator |
| `whack/controller.py` | Concurrent aiming, exclusive ping turns, calibration and tracking states |
| `whack/tracking.py` | Circle intersection, motion filtering, timestamp alignment and bounded prediction |
| `whack/ui.py` | One measured/predicted position spot and optional diagnostics |
| `whack/__main__.py` | Window/headless launch, start mode and CSV recording |

## Coordinates and measurement model

Coordinates are metres. `x` increases from the field's left edge and `y`
increases away from the wall. Default acoustic centres are `(0, 0.20)` and
`(1.50, 0.20)`; both share the same measured depth and torso height. The visible
rectangle is `x=0..1.50`, `y=0.60..2.00`. The screen maps the near edge to the top
and far edge to the bottom. Measure the actual geometry before calibration.

Two corrected ranges to a common point define two circle intersections. The
laptop chooses the forward one. Servo bearings gate the possible result but are
not exact echo angles. Body surfaces, clothing and furniture can violate the
common-point assumption. No body-width correction or human identification is
implemented; the reconstructed position is an approximate foreground target.

Servo bearings are counter-clockwise from +x: 0° right, 90° forward, 180° left.
Firmware applies reversal, centre trim and calibrated pulse mapping. A reported
bearing is the commanded estimate; there is no servo angle encoder.

## Calibration and acquisition

Hardware needs a version-2 empty-field background profile matching its geometry.
A three-second lead-in precedes a dense independent bearing sweep. The angular
grid also includes all bearings required by the search plan; each sweep entry
gets three left/right pairs. Typical ranges are stored by node and bearing.
Fewer than two valid echoes stores no return; `INVALID` responses, packet loss or
other acquisition failures abort calibration. A no-return result does not
establish sensor health.

Following may use exact calibrated bearings or directions between closely
spaced calibrated samples. At an intermediate direction the nearer available
background range is used conservatively; large uncalibrated gaps are rejected.
A range must be more than 0.15 m closer than a recorded background to qualify as
foreground. Simulation has an ideal target and does not require a room profile.

Search points cover paired beams over rectangular cells with an angular margin.
This covers the configured beam model, not physical human echo gaps. The dense
calibration grid and search-point list serve different purposes and may have
different sizes. Their sizes depend on measured geometry and beam assumptions.

State flow:

```text
CALIBRATION → FIND → CONFIRM → TRACK
                         ↑       ↓
                         └─ LOCAL SEARCH
                                 ↓
                                LOST → FIND
```

`--start-mode center` initially holds the centre, then allows a wider search if
acquisition has not succeeded. `--start-mode search` searches immediately. Both
require two consistent foreground pairs before displaying the target. Space
restarts acquisition, R stops and forgets the player until Space is pressed, and
C rebuilds the empty-field profile.

## Position and motion filter

The tracker rejects invalid ranges, unstable intersections, incompatible beam
angles, excessive pair skew and implausible jumps. An alpha-beta filter maintains
position and velocity. Once a recent motion estimate exists, each earlier range
is adjusted by its predicted radial movement to align the staggered measurements
to the newer observation time. This is a first-order constant-velocity model;
sudden changes and different reflecting body surfaces remain limitations.

Aiming projects the estimated target forward by the configured lead interval.
Both motors can move concurrently. Commands that retain an already-settled
bearing incur no new movement delay. There is no closed-loop servo feedback.

On a brief miss, local search tries directions around the recent prediction.
The default local-search budget is 0.50 s from the last accepted observation.
After that, tracking is lost and wider acquisition resumes. A single range is
never accepted as a complete 2D fix.

The default displayed prediction expires after 0.20 s. Prediction does not update
the last accepted measurement timestamp. These limits are software parameters,
not measured physical response times. Confidence combines consistency and age;
it is not a calibrated probability of position accuracy.

## WM2 scheduling and firing permissions

The laptop binds UDP 4210 and nodes UDP 4211. Both nodes receive an AIM for the
same frame sequence, each with its own bearing. The laptop waits for both READY
responses, then grants one FIRE at a time. Servo settling is bounded to 700 ms
and echo waiting to 25 ms. An unchanged settled servo has no extra settling wait.

Successful RANGE receipt proves that firing has finished. The host then waits
at least 65 ms before authorizing the next sensor. Each node also enforces its
local minimum spacing. These settings are conservative engineering controls;
physical crosstalk still needs testing in the actual room.

READY provides a firing lease lasting at most 1000 ms from readiness. FIRE
consumes that lease immediately; it is never queued for later execution. Cached
results allow retransmission without emitting another ping. If FIRE may have
been delivered but its response is missing, the laptop retains an acoustic guard
through the latest possible lease expiry plus echo and quiet time. Starting a
new calibration or acquisition does not cancel this uncertainty guard.

The normal host waits at most 0.95 s for readiness and 0.25 s for a firing reply.
Timeout recovery can be longer because the acoustic guard remains in effect.
No per-frame rate or network delivery guarantee follows from these timeout values.

### Strict ASCII protocol

```text
WM2 DISCOVER
WM2 HELLO <node>
WM2 AIM <seq> <angle_mdeg>
WM2 READY <node> <seq> <angle_mdeg> <lease_ms> <status>
WM2 FIRE <seq>
WM2 RANGE <node> <seq> <angle_mdeg> <distance_mm> <status> <sample_ms> <age_us>
```

- Nodes use IDs 0 and 1. Sequences are nonzero uint32 values with wrap-aware order.
- Angles are 0..180000 millidegrees; 90000 means forward.
- READY status is `OK` with a remaining lease, or `INVALID` with no lease.
- RANGE status is `OK`, `TIMEOUT` or `INVALID`. Firmware accepts 20..4000 mm;
  error responses have zero distance and are not position fixes.
- `sample_ms` is the node's local clock at the trigger. `age_us` describes elapsed
  acquisition time before completing the result; cached results retain their
  original measurement metadata.

Replies must match the pending sequence, node and source endpoint. Successful
responses must match the commanded bearing. The host bounds acquisition time
between its FIRE send time and RANGE receive time minus the reported acquisition
age, then uses the interval midpoint as its timestamp estimate. Excessively
wide or inconsistent timing is rejected. Independent node clocks are not treated
as synchronized, and raw `sample_ms` values are not compared across boards.

WM1 MEASURE remains available to legacy diagnostic tools, but the new controller
requires WM2 capability from both nodes. A node advertising WM1 is shown as
requiring the new firmware rather than being given a WM2 firing schedule.

### Discovery and node freshness

Nodes broadcast HELLO every two seconds. For explicitly supplied IP addresses,
the host can also send unicast `WM2 DISCOVER`; its HELLO reply confirms node ID
and protocol version without moving the servo, taking ownership or changing a
firing lease. Discovery replies go to the requester's source port.

Node/protocol freshness expires after six seconds without the expected evidence
of life. Configured IPs retain their endpoint mapping across outages, but do not
bypass the requirement for fresh compatible firmware identification. Duplicate
node IDs suspend the conflicting node. Only one laptop should coordinate both
units. Firmware releases control ownership after 30 seconds of inactivity, and
Wi-Fi loss revokes pending transactions and firing permissions.

## Rendering and logs

The canvas contains one cyan position spot. Fresh measured estimates are solid;
short extrapolation is dim and hollow. Missing, lost or out-of-field positions
are hidden. A 2 mm boundary tolerance accommodates millimetre range quantization;
accepted near-edge points are clamped only for rendering onto the canvas edge.
Invalid observations are never clamped into valid tracking fixes.

The UI requests a redraw every 16 ms, independently of new sensor readings.
Optional diagnostics distinguish display FPS from accepted position updates,
and show fix age, confidence and state. CSV and headless output include those
fields and a prediction flag. There are no gameplay events or warning bells.

## Network and validation boundary

There is one supported network: a phone hotspot (WPA2-personal, 2.4 GHz). The
laptop and every box join it as ordinary Wi-Fi clients and receive DHCP
addresses. The firmware has no network profiles and no board acts as an access
point. The hotspot name and password are `WIFI_SSID` and `WIFI_PASSWORD` in the
private `tracker_config.h` (Arduino IDE) or `config.local.h` (PlatformIO).

Addresses are never assumed. Each box broadcasts `WM2 HELLO <node>` to UDP 4210
every two seconds; the laptop listens on UDP 4210 and learns each box's address
from that announcement, and the boxes receive commands on UDP 4211. `--nodes`
is an optional override that supplies the addresses, left to right, for a
network that blocks broadcast.

`python3 -m tools.prepare_tracker_firmware` prepares the Arduino sketches and
never overwrites an existing `tracker_config.h`. The user manually uploads the
matching sketch to each box after a change. Generation and the desktop
controller never flash hardware.

The field layout of the three-box prototype is the tracked
`config.prototype.json`, so any computer with a clone can run it with
`python3 -m whack --tracker swarm --config config.prototype.json`. The
empty-field calibration (`calibration.local.json`) stays per computer, and
`config.local.json` is an optional personal override; Git ignores both.

Synthetic tests exercise packet handling, timing, ideal movement and loss.
Physical tests are still needed for accurate body positioning, usable speed,
servo settling, crosstalk, radio behavior and visible latency. See the
[workflow](player-tracking-workflow.md) and [live setup](live-tracker-setup.md).

## Study reference

`example-code/tracker.py` supplies the black-background visual reference for a
different board/UART setup. This tracker has its own UDP protocol and geometry.
The vendored files retain their original implementation and license.
