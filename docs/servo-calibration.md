# SG90 angle-scale check

The user measured approximately 45 degrees of physical rotation for each
90-degree command change with the original 1000–2000 microsecond mapping.
This suggests twice the pulse change per degree is needed. It does not establish
safe mechanical endpoints or the calibration of the second servo.

## Current test settings on both boards

The local `tracker_config.h` files in both `firmware/arduino/tracker_left/` and
`firmware/arduino/tracker_right/` now use:

```cpp
#define SERVO_PULSE_MIN_US 500
#define SERVO_PULSE_MAX_US 2500
#define SERVO_MIN_MDEG 30000
#define SERVO_MAX_MDEG 150000
```

The first two values define the angle-to-pulse scale, extrapolated from the
observed motion. The initial 45–135 degree check kept pulses within
1000–2000 microseconds. At the user's request for a wider test, both bounds
are now 30–150 degrees, allowing approximately 833–2167 microseconds. This
extends beyond the previously tested pulse range; approach each new endpoint
gradually from the centre and stop if the servo presses against a stop or buzzes
strongly. This setting is a test range, not a measured travel result.
Startup remains 90 degrees / 1500 microseconds. The right board has the same
provisional mapping at the user's request; its physical scale still needs a
separate measurement.

Manually upload the matching updated sketch to each board, close the visualizer,
wait two seconds, and remain connected to TrackerNet. Run these commands individually:

```bash
python3 -m tools.probe_node --ip 192.168.4.1 --node 0 --angle 90 --count 1
python3 -m tools.probe_node --ip 192.168.4.1 --node 0 --angle 60 --count 1
python3 -m tools.probe_node --ip 192.168.4.1 --node 0 --angle 90 --count 1
python3 -m tools.probe_node --ip 192.168.4.1 --node 0 --angle 120 --count 1
python3 -m tools.probe_node --ip 192.168.4.1 --node 0 --angle 90 --count 1
```

For the right tracker, use `--ip 192.168.4.2 --node 1` with the same angle
sequence. Use its actual Serial Monitor IP if DHCP assigns another address.

After confirming central movement, test these angles one at a time:
`90 → 60 → 45 → 30 → 45 → 60 → 90 → 120 → 135 → 150 → 135 → 120 → 90`.
Observe the mount after every command. The limits still reject 0 and 180 degrees.

Each 30-degree change should produce approximately 30 degrees of physical
rotation if the measured scale remains linear. The mount should return to the
same forward direction at 90 degrees. Printed angles are commanded estimates;
verify the horn/sensor direction with angle marks or a protractor.

Do not start the full empty-field calibration yet: it requests bearings outside
these temporary travel bounds and will be rejected. After checking scale,
measure each servo's usable travel and mounting alignment before widening the
bounds and recalibrating the room. Do not treat 500/2500 as verified endpoints.

The ordinary firmware preparation command preserves these local settings.
To restore either board's previous setup, use 1000/2000 for the pulse endpoints
and 0/180000 for the travel bounds, then manually upload again.
