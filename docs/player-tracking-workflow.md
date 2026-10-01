# Two ESP32s, one tracked position

Status: implemented workflow for software validation, 15 September 2026.
Physical moving-player tracking, accuracy and latency remain unverified.
Gameplay is outside this stage; the output is one cyan spot on a black screen.
The laptop and the boxes share one phone hotspot, and firmware uploads are
performed manually by the user.

## Hardware and coordinates

Each ESP32 controls one positional pan servo carrying one HC-SR04. Both sensors
must have overlapping coverage at the same torso height, with horizontal beams.
Default sensor positions are `(0, 0.20)` and `(1.50, 0.20)` metres. The visible
field is 1.50 m wide, from `y=0.60` to `2.00`; the screen wall is `y=0`.
Configure the actual acoustic centres, servo bearings and distance corrections.

There is one foreground participant. Ultrasound measures reflecting surfaces;
it cannot recognize a human or distinguish identities. Spectators, furniture,
clothing and body orientation can change the returning echo. The two units may
measure different parts of the same person, so the reconstructed point is an
approximate body position rather than a measured body centre.

The default beam half-angle is a software model assumption. Measure effective
coverage and loaded servo settling time before relying on the scan geometry.
A simulator using an ideal point reflector cannot establish human coverage.

## Running the workflow

```bash
python3 -m whack --simulate
python3 -m whack --config config.local.json
python3 -m whack --config config.local.json --start-mode search
```

`config.local.json` is a personal layout file that Git ignores. The three-box
prototype has a tracked one and is started with
`python3 -m whack --tracker swarm --config config.prototype.json`; see
[Run on another computer](../README.md#run-on-another-computer).

In simulation, wait for centre acquisition before moving the mouse. Hardware
requires both nodes on WM2 AIM/FIRE firmware and a current background profile.
The default start mode is `center`; `search` scans the field for initial lock.

- **C:** start empty-field calibration in hardware mode.
- **Space / R:** find the player again using the selected start mode.
- **D:** inspect state, sensor status, confidence, measured update rate and age.
- **F11:** fullscreen; **Escape:** close.

The stage sequence is:

```text
Calibrate empty field → Find → Confirm → Track
                              ↑           ↓
                              └──── Local search
                                        ↓
                                       Lost → Find
```

A centre start means standing briefly at the physical field centre. The screen
shows only the tracked position; it does not draw an extra starting target.

## 1. Build a dense empty-field reference

Clear the whole field, then press **C**. After the lead-in, both motors sweep
the useful bearings while ultrasound measurements remain sequential. Calibration
uses a dense angular grid together with the required search bearings, sampling
each direction three times. The median valid ranges form the background profile;
repeated missing echoes record no background return at that bearing.

The grid supports nearby steering corrections during following. Only a
sufficiently close calibrated bearing can be used for foreground comparison;
an unprofiled direction must not bypass the background filter. A return must be
closer than its reference by the configured implementation margin to qualify as
foreground. A stationary player can therefore remain a candidate.

The profile is saved locally and reused with matching geometry. Recalibrate
when either sensor or surrounding furniture moves, and when an old profile is
incompatible with the current workflow/settings. Calibration has no claim to
identify a person, and a missing echo does not demonstrate that a sensor works.

## 2. Find and confirm a candidate

In `center` mode, both sensors first aim into the centre of the field. The player
stands there briefly. In `search` mode, the controller advances through shared
candidate points whose paired beams cover the field under the configured model.
Both motors may move at the same time; only the acoustic transmissions take turns.

A candidate needs two valid foreground ranges that are recent, inside the aimed
beams and consistent with a possible forward circle intersection. **Two
consistent pairs** are required before entering tracking. A lone range does not
establish a 2D position. If confirmation fails, acquisition continues rather
than displaying an unconfirmed target as a lock.

The full search is a geometric coverage scheme, not a guarantee that a person
returns detectable echoes everywhere. Its duration is separate from the update
interval once following is established.

## 3. Calculate a position from two ranges

This uses two-distance circle intersection, often called trilateration. The
servo supplies an estimated beam direction rather than an exact echo bearing,
so angle-only triangulation is not the measurement model.

Let the sensor baseline be `b = right_x - left_x`, the shared sensor depth be
`sensor_y`, and the corrected ranges be `rL` and `rR`:

```text
x_relative = (rL² - rR² + b²) / (2b)
x = left_x + x_relative
y = sensor_y + sqrt(rL² - x_relative²)
```

Choose the intersection in front of the sensors. For `b=1.50 m`, both ranges
`1.25 m`, and `sensor_y=0.20 m`, the result is `(0.75, 1.20) m`.

Reject invalid ranges, nonintersecting circles, incompatible beam directions,
implausible motion and observations too far apart in time. A point outside the
configured visible field is not drawn. Real echo mismatch can still produce a
plausible but biased result; these checks do not prove body-centre accuracy.

### Account for staggered measurements

Left and right ultrasound measurements occur at different times. WM2 responses
include timing information, and the host derives bounded acquisition-time
estimates in its own clock domain. The host does not subtract raw timestamps
from the two independently running ESP32 clocks. Replies with excessive or
inconsistent timing are rejected.

Once a recent velocity estimate exists, the tracker estimates each sensor's
radial speed: the component of the player's velocity along that sensor's range
direction. It adjusts the earlier range by `radial_speed × time_difference`
before intersecting the circles at the newer observation time. Initial lock
uses zero velocity. This first-order correction helps steady movement; uncertain
network timing and sudden acceleration still limit accuracy.

## 4. Predict, aim, measure and correct

The tracker maintains filtered position `(x, y)`, velocity `(vx, vy)`, the last
accepted measurement time and a consistency score. The alpha-beta filter makes
a position prediction, then uses each new position residual to correct both
position and velocity. Speed is bounded by the configured movement limit.

For a future interval `dt`:

```text
predicted_x = x + vx × dt
predicted_y = y + vy × dt
```

For example, at `(0.85, 1.20) m` moving right at `0.50 m/s`, a `0.15 s` prediction
is `(0.925, 1.20) m`. This example explains the motion model; it is not a measured
command or hardware delay.

The controller aims both sensors around the expected position at the next
measurement. An unchanged, already-settled bearing avoids an extra movement
wait; a changed bearing still needs settling. Prediction stays within configured horizons;
a new range pair corrects the model rather than extending the old measurement's
age. Constant velocity cannot anticipate a sudden reversal.

### Concurrent servo movement, exclusive ping turns

The WM2 exchange separates aiming from ranging:

```text
Laptop → left and right: AIM(sequence, bearing)
Left and right → laptop: READY after settling
Laptop → left: FIRE(sequence)
Left → laptop: RANGE with timing information
Quiet interval
Laptop → right: FIRE(sequence)
Right → laptop: RANGE with timing information
```

A settled servo commanded to its current bearing has no extra movement wait.
Real moves still use the configured settling allowance. Firmware handles aim
settling without blocking the network loop and bounds the echo wait.

Each READY gives a short-lived, single-use firing permission. FIRE cannot be
queued to execute after settling; expired or repeated commands cannot produce
an extra measurement. If a reply is missing, the host waits out the possible
firing window before authorizing the other sensor. Sequence and address checks
reject unrelated packets. This behavior intentionally allows a network fault
to slow acquisition instead of accumulating old commands.

The scheduler includes a conservative acoustic quiet interval between nodes,
and each node also enforces its local minimum ping spacing. Actual room
crosstalk still needs measurement. Motor travel, network round trips and lost
responses all affect the achieved pair rate.

## 5. Recover without leaving a stale spot

Briefly missing a usable pair enters local search around the recent predicted
position. The controller tries nearby directions for a bounded period, keeping
the motion model only while it remains recent. A suitable pair restores
tracking; otherwise the state becomes lost and wider acquisition resumes.

Defaults include a **0.20 s display prediction horizon** and a **0.50 s local
search budget**. These are software limits, not measured response times. A dot
can disappear while the controller is still trying to recover. A single sensor
return never becomes a standalone 2D fix.

The display has one spot:

- Solid cyan: measured position estimate.
- Dim hollow cyan: short extrapolation between measurements or during recovery.
- No spot: no confirmed estimate, expired prediction, loss or out-of-field position.

The screen redraws independently of new measurements, at a requested 16 ms
interval. A faster redraw does not produce more measured observations. The
status reports acquisition/recovery state; there are no gameplay rules, hit
zones or warning sounds.

## Diagnostics and validation

Press **D** for fresh accepted position updates in Hz, observed display FPS,
last measured fix age and confidence. Confidence is a heuristic consistency
score, not an experimentally calibrated accuracy probability.

```bash
python3 -m whack --simulate --headless --seconds 5
python3 -m whack --config config.local.json --record tracking.csv
```

CSV and headless diagnostics preserve the distinction between measured and
predicted positions. An extrapolation never resets the measured fix timestamp.
Software and simulated tests exercise acquisition, sequence handling, moving
ideal targets, stale/reordered responses, loss and recovery. They do not establish
physical player-tracking performance.

Before reporting latency or accuracy, test both real units together:

1. Verify servo directions, commanded angles and loaded settling times.
2. Check fixed-target distances and stationary-person position scatter.
3. Compare one-sensor and alternating two-sensor echoes for crosstalk.
4. Record slow lateral movement, depth changes and reversals with independent
   position/time evidence.
5. Measure position error, accepted update rate, visible delay, acquisition time,
   recovery time and loss frequency separately.

No hardware tracking rate or latency is claimed. A person moving at `2 m/s`
travels `0.40 m` in `0.20 s`; a smooth display alone cannot remove that uncertainty.

## Network

The laptop and every box join one phone hotspot (WPA2-personal, 2.4 GHz). It is
the only supported network: the firmware has no network profiles and no board
acts as an access point. The hotspot name and password are `WIFI_SSID` and
`WIFI_PASSWORD` in the local firmware configuration. Every box broadcasts
`WM2 HELLO` to UDP 4210 every two seconds, the laptop discovers the boxes from
those announcements, and the boxes receive commands on UDP 4211. The laptop
remains the tracking controller.

The user prepares settings and manually uploads the matching sketch to each box.
The workflow never automatically flashes boards. See the
[live setup guide](live-tracker-setup.md) and [firmware setup](../firmware/README.md).

## References and implementation

- [HC-SR04 datasheet](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf):
  trigger/echo operation and nominal module characteristics.
- [Manufacturer discussion of multi-sensor crosstalk](https://maxbotix.com/blogs/blog/using-multiple-ultrasonic-sensors):
  the general interference problem; its model-specific wiring is not HC-SR04 wiring.
- [Controller](../whack/controller.py), [position filter](../whack/tracking.py),
  [protocol](../whack/protocol.py), [node firmware](../firmware/src/main.cpp),
  [visualizer](../whack/ui.py).
