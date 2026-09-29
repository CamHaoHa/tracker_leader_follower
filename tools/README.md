# Sensor tools

## Prepare the left-hosted tracker network

```bash
python3 -m tools.prepare_tracker_firmware --network tracker
```

This prepares matching left/right Arduino sketches for **TrackerNet**. It saves
one shared random password in the ignored `firmware/arduino/tracker_network.local.json`
and copies the network selection into each sketch's `tracker_network.h` tab.
That tab shows the password to enter on the laptop. To change SSID, password or
channel, edit the JSON and run the same preparation command again.

Your original `tracker_config.h` credentials and servo settings are preserved.
A normal preparation without `--network` preserves the network selection;
`--network configured` restores the profile selected in `tracker_config.h`.
Upload both sketches manually after any change. The generator never connects
to or flashes either board. Use `--check --network tracker` to check files without
creating credentials or changing settings.

See [live setup](../docs/live-tracker-setup.md) for joining the Wi-Fi and running
the spot display.

## Record a real sensor test to Excel

Upload the Arduino `firmware/arduino/sensor_test/sensor_test.ino` sketch, then close
Serial Monitor and Serial Plotter. From the project root:

```bash
python3 -m tools.record_sensor_test --sensor A --distance-cm 25 --samples 30
```

This records USB serial measurements and saves a new timestamped folder under
`evidence/`, with an Excel report, CSV, original serial log, and metadata. The
distance argument is the measured true target gap, not a sensor command. See
[evidence instructions](../evidence/README.md) for port selection and partial runs.

## UDP sensor emulator

`simulate_nodes.py` runs two independent UDP endpoints with the same messages as the ESP32 firmware. Use it to exercise discovery, network acquisition, tracking, and disconnection without physical sensors:

```bash
python3 tools/simulate_nodes.py --x 0.75 --y 1.3 --seconds 60
```

The nodes bind `127.0.0.2:4211` and `127.0.0.3:4211`, and announce themselves to `127.0.0.1:4210`. Use the desktop application's normal hardware mode on the same computer; `--simulate` uses its separate in-process model and bypasses UDP. Run only one host and one copy of this emulator at a time.

The model uses sensors at `(0, 0.2)` and `(1.5, 0.2)` metres, 20° beam half angles, 60 ms + 3 ms/degree servo settling (maximum 700 ms), and bounded echo delay. It represents one ideal reflector and cannot establish real hardware accuracy or reliable detection of a moving person.

Options include `--empty` to return echo timeouts and `--drop-node 0` or `--drop-node 1` to suppress a node entirely. Ctrl+C stops the emulator. Its final JSON summary reports ping counts, the shortest interval between pings, and any overlapping acquisition commands.

The hardware path requires a background calibration. To exercise that workflow, start the emulator with `--empty --seconds 120`; in another terminal run:

```bash
python3 -m whack --headless --calibrate --seconds 90 --calibration /tmp/whack-udp-calibration.json
```

Stop the empty emulator, restart it with a reflector using the first command, then launch the visualizer with the same temporary profile:

```bash
python3 -m whack --calibration /tmp/whack-udp-calibration.json
```

Keep the simulator's profile separate from calibration captured with physical hardware. The temporary path above is suitable on Linux/macOS; choose a writable temporary path on Windows.

For an automated test, run:

```bash
python3 -m unittest discover -s tests -p 'test_udp.py' -v
```

The integration tests create their own temporary empty-scene profile, start the emulator as a subprocess, and verify discovery, position recovery, empty echoes, missing nodes, and expiration after disconnection. They use real loopback sockets; run outside a network-restricted sandbox if socket creation is denied.
