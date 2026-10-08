# Sensor test evidence

Upload `firmware/arduino/sensor_test/sensor_test.ino` in Arduino IDE first.
Use TRIG GPIO32 and ECHO GPIO35 through the divider, shared ground, one sensor
active, and the servo unpowered. Fix a flat target at the measured gap from the
front of the transducers. Close Arduino Serial Monitor and Serial Plotter.

From the project root, capture 30 consecutive attempts at 25 cm:

```bash
python3 -m tools.record_sensor_test --sensor A --distance-cm 25 --samples 30
```

The recorder selects the port only when it finds exactly one USB serial device.
To select a port explicitly:

```bash
python3 -m tools.record_sensor_test --list-ports
python3 -m tools.record_sensor_test --sensor A --distance-cm 25 --port /dev/ttyUSB0
```

Use the listed port on your machine. Add `--notes "flat board, sensor fixed"`
to document conditions. Change `--distance-cm` for each measured position and
`--sensor B` for the second sensor. Each command creates a separate timestamped
folder; it never replaces a previous run or the manually prepared results workbook.

Each folder contains `results.xlsx` (summary, all attempts, chart), `readings.csv`,
`serial.log` (original received bytes), and `run.json` (metadata and statistics).
The log starts after a two-second startup period; the final received chunk may
contain extra lines beyond the requested sample count. Excel contains only the
requested consecutive recognized attempts. Startup messages are not attempts;
NO ECHO, ECHO HIGH, OUT OF RANGE and malformed Distance lines all count as attempts.
Unknown serial lines remain in the raw log. The uploaded sketch controls any range
limit; the recorder never clamps or silently removes numeric readings.

Timeout (default 60 s), Ctrl+C during capture, or serial disconnection saves the
partial run and marks it incomplete. No port means no measurement run is created.
Completion means the requested number of attempts was captured, not a sensor pass.
Errors are included in the return-rate denominator. Distance statistics use
READING rows only; review all error counts, especially near the 200 cm cutoff.
No calibration correction or automatic pass/fail threshold is applied.

The recorder requires pyserial and openpyxl. They are available on this workstation.
On a different machine, install `tools/requirements-sensor-test.txt` in a Python
virtual environment. API references: [pySerial](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)
and [openpyxl](https://openpyxl.readthedocs.io/en/stable/tutorial.html).

The first physical batch is recorded in `week8/`: sensor A at 25 cm, 30 attempts. An earlier empty timeout run is preserved separately. Software test fixtures are kept in temporary directories, not this evidence folder.
