# Reading the tracker code

The laptop decides where to look, combines the readings and draws one spot.
Each ESP32 turns its own servo and measures one ultrasonic distance when asked.
The ESP32s do not calculate the player's position. There is no gameplay logic.

## 1. Read these functions in order

| Function | What it contributes |
| --- | --- |
| [Controller.poll()](../whack/controller.py) | Advances acquisition, coordinates both nodes and produces the display snapshot |
| [Controller._aim_angles()](../whack/controller.py) | Chooses a search point or predicts the next aiming point |
| [handle_command(), settle_if_ready(), acquire()](../firmware/src/main.cpp) | Move the servo, report readiness and take one distance reading |
| [Controller._receive(), _complete_pair()](../whack/controller.py) | Check replies, estimate measurement times and confirm/update a target |
| [locate(), Tracker.update(), Tracker.predict()](../whack/tracking.py) | Calculate position, estimate velocity and predict short-term movement |
| [TrackerWindow._tick(), _screen(), _draw()](../whack/ui.py) | Map metres to pixels and draw one current spot |

A normal cycle follows this path:

```text
Predicted point → both AIM commands → both READY replies
→ left FIRE/RANGE → quiet interval → right FIRE/RANGE
→ position and velocity correction → next prediction + screen spot
```

Both servos may move together. Ultrasound transmissions take separate turns so
one sensor is less likely to hear the other's pulse. In firmware, `write_servo()`
sets the PWM pulse; `acquire()` converts echo duration to distance. An unchanged,
settled bearing avoids a new movement wait. Real changed bearings need settling.

## 2. Find one foreground target

[Controller.start_calibration()](../whack/controller.py) begins an empty-field
scan. [Geometry.calibration_aims()](../whack/tracking.py) supplies dense bearings;
three readings per node/bearing build the background reference. The foreground
check accepts a valid echo nearer than that reference, or an echo where the
reference had no return. It rejects gaps without adequate background coverage.

This identifies a new reflecting object under a **single-person assumption**.
It cannot recognize a human or distinguish identities. A chair or another person
can also return an echo; the two sensors may see different shoulders or arms.

State changes are handled by `_complete_pair()`, `_miss()` and `poll()`:

```text
calibration → find → confirm → track
                        ↑       ↓
                        └─ local_search
                                ↓
                               lost → find
```

Default `center` mode tries the centre first, then expands the search if needed.
`search` mode starts searching immediately. The first accepted pair initializes
position with **zero velocity**. The controller requires **two consistent pairs**
before displaying a confirmed track; the next pair begins informing velocity.
Space restarts acquisition. R stops and forgets the player until Space is
pressed. C starts hardware background calibration.

## 3. Calculate the first position

[locate()](../whack/tracking.py) intersects two distance circles. This is often
called trilateration; it is not exact angle-based triangulation. The servos tell
us approximate beam directions, not the exact angles of the returning echoes.

For sensors sharing one depth, with corrected distances `rL`, `rR`:

```text
b = right_x - left_x
x_relative = (rL*rL - rR*rR + b*b) / (2*b)
x = left_x + x_relative
y = sensor_y + sqrt(rL*rL - x_relative*x_relative)
```

The positive square root selects the point in front of the sensors. For the
nominal 1.50 m baseline, `rL = rR = 1.25 m` gives `(x, y) = (0.75, 1.20) m`
when `sensor_y = 0.20 m`. This arithmetic assumes both echoes refer to one point.
Impossible intersections, beam mismatches and implausible jumps are rejected.
A geometrically plausible answer can still be biased by different body surfaces.

## 4. Put staggered readings on a common timeline

The left and right measurements happen at different times. In
[Controller._receive()](../whack/controller.py), the laptop bounds each trigger
time using its FIRE send time and RANGE receipt time minus the reported
acquisition age. It uses the midpoint of that interval and rejects excessive
uncertainty. The two ESP32 `sample_ms` clocks are independent; the code does not
subtract one board's raw clock from the other's.

Once velocity is known, [Tracker.update()](../whack/tracking.py) estimates how
quickly distance is changing along each sensor's beam. It advances the older
range by `radial_speed × time_difference` before calculating the newer position.
For the first fix, there is no velocity correction. Sudden acceleration still
causes error; this is a constant-velocity approximation.

## 5. Estimate movement and predict the next point

`Tracker.update()` uses an **alpha-beta filter**: prediction plus correction.
For one coordinate, `p` is position, `v` velocity and `dt` time since the last fix:

```text
expected = p + v * dt
error = observed_position - expected
new_position = expected + alpha * error
new_velocity = v + beta * error / dt
```

Alpha controls how much a reading corrects position. Beta controls how much it
changes estimated velocity. The implementation chooses alpha from the time gap
and smoothing setting, uses `beta = 0.5 * alpha²`, and limits the resulting speed.

[Tracker.predict()](../whack/tracking.py) then projects using `p + v * dt`, within
a bounded horizon. Example: at `x=0.75 m` with `vx=0.30 m/s`, looking `0.10 s`
ahead gives `x=0.78 m`—a 3 cm move. This explains the calculation; it is not a
measured player result or a guarantee of the next position. Reversals cannot be
predicted in advance; the next accepted pair corrects the model.

[Geometry.angle()](../whack/tracking.py) converts the predicted point into a
bearing for each sensor using `atan2(y - sensor_y, x - sensor_x)`. World bearings
are 0° right, **90° forward**, 180° left. Firmware applies each mount's reversal,
trim and pulse mapping. Reported bearing is a commanded estimate, not an encoder.

## 6. Understand a hollow or missing spot

The default display prediction lasts at most **0.20 s** after the last accepted
fix. Local search may continue for **0.50 s** from that fix before loss and wider
search. A missing echo never refreshes the last measurement time; one range
cannot produce a full 2D fix. Lost or out-of-field estimates are hidden.

The UI requests a redraw every 16 ms. Recent estimates appear solid; older short
predictions appear dim and hollow. **Display FPS is not measurement Hz.** Press
D to see both rates, fix age and confidence. Confidence is a consistency/age
score, not a measured probability that the spot is accurate.

## 7. Current settings and physical limits

[Geometry](../whack/tracking.py) contains defaults, but a supplied JSON config
overrides them. For example, default `max_pair_skew_s` is **0.15 s**, while the
current local configuration uses **0.25 s**. Check the file passed with `--config`
when interpreting behavior; source defaults alone do not describe every run.

Both mounts currently have **30–150° test limits**. The original near-field sweep
requests bearings outside that travel, so it remains unavailable until usable
travel and alignment are verified and the limits/coverage are reconciled. Do
not interpret successful compilation or simulation as a completed physical scan.
See [servo calibration](servo-calibration.md) and [live setup](live-tracker-setup.md).

Moving-body accuracy, crosstalk and end-to-end delay still need physical testing.
Software tests validate the programmed workflow and ideal-reflector simulation;
they do not establish reliable live tracking of a person.
