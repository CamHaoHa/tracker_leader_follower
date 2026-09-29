"""Prepare self-contained Arduino IDE sketches from the canonical node firmware.

Run ``python3 -m tools.prepare_tracker_firmware`` from the project directory.
Generated sources can be refreshed safely: tracker_config.h is never overwritten.
No boards are contacted or flashed by this command.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
DEFAULT_OUTPUT = FIRMWARE / "arduino"
HEADERS = ("settings.h", "wm_protocol.h")
# Node IDs follow box position left to right. With three boxes the right box is
# node 2; a two-box layout uses right_pair (node 1) for its right box.
NODES = (("left", 0), ("middle", 1), ("right", 2), ("right_pair", 1))
NETWORK_SETTINGS = "tracker_network.local.json"
CONFIGURED_NETWORK = '''#pragma once
// Use WIFI_PROFILE and credentials from tracker_config.h.
// Select the private tracker network with:
// python3 -m tools.prepare_tracker_firmware --network tracker
'''


def network_settings(output: Path, *, check: bool) -> dict | None:
    """Keep one private network identity shared by both generated sketches."""
    path = output / NETWORK_SETTINGS
    if not path.exists():
        if check:
            return None
        output.mkdir(parents=True, exist_ok=True)
        settings = {"version": 1, "ssid": "TrackerNet", "password": secrets.token_urlsafe(12), "channel": 6}
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # Another preparation has created the shared identity.
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(settings, stream, indent=2)
                stream.write("\n")
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(settings, dict) or settings.get("version") != 1
                or not isinstance(settings.get("ssid"), str)
                or not 1 <= len(settings["ssid"]) <= 32
                or not isinstance(settings.get("password"), str)
                or not 8 <= len(settings["password"]) <= 63
                or not all(32 <= ord(c) <= 126 for c in settings["ssid"]+settings["password"])
                or type(settings.get("channel")) is not int or not 1 <= settings["channel"] <= 11):
            raise ValueError("Invalid network settings")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {path.name}; require printable ASCII SSID (1–32), password (8–63), channel (1–11), version 1") from exc
    return settings


def tracker_network_header(settings: dict) -> str:
    return '''#pragma once
// Shared private Wi-Fi: LEFT creates it, the other boards join it; laptop joins manually.
// Generated from ../tracker_network.local.json; keep both files private.
// To change the SSID/password, edit that JSON then rerun preparation with --network tracker.
// Home, school and servo settings remain in tracker_config.h.
// To use them again: python3 -m tools.prepare_tracker_firmware --network configured
#ifdef WIFI_PROFILE
#undef WIFI_PROFILE
#endif
#define WIFI_PROFILE 3
''' + "".join(f"#ifdef {name}\n#undef {name}\n#endif\n#define {name} {json.dumps(value)}\n"
               for name, value in (("TRACKER_WIFI_SSID", settings["ssid"]),
                                   ("TRACKER_WIFI_PASSWORD", settings["password"]),
                                   ("TRACKER_WIFI_CHANNEL", settings["channel"])))


def config_template(side: str, node_id: int) -> str:
    return f'''#pragma once

// Settings for the {side.upper()} ESP32 only. Keep this file private.
// The preparation command preserves this file when refreshing firmware sources.
#define NODE_ID {node_id}

// All boards and the computer must use the same reachable Wi-Fi network.
// ESP32-WROOM-32E uses 2.4 GHz Wi-Fi. Enter your network details here.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Select 0=home, 1=school personal/hotspot, 2=OneNet PEAP, 3=left-hosted Wi-Fi.
// Switching profiles preserves both sets of credentials.
// tracker_network.h can override the selection with a shared private network.
#define WIFI_PROFILE 0
#define SCHOOL_WIFI_SSID ""
#define SCHOOL_WIFI_PASSWORD ""

// Optional OneNet: Arduino-ESP32 3.3+ only; no certificate checks are disabled.
// Recompile before use (certificate clock is seeded from the build timestamp).
#define ONENET_USERNAME ""
#define ONENET_PASSWORD ""
#define ONENET_SERVER_DOMAIN "radius.mq.edu.au"
#define ONENET_BUILD_TIMEZONE "AEST-10AEDT,M10.1.0,M4.1.0/3"

#define SERVO_PIN 25
#define ULTRASONIC_TRIG_PIN 32
#define ULTRASONIC_ECHO_PIN 35

// World bearings: 0 = right, 90 = into the field, 180 = left.
// Check your servo's mounting and specifications before scanning.
// Uploading/restarting centers the servo at a requested bearing of 90 degrees.
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0

// Conservative initial pulse endpoints; calibrate for your actual servo.
// These endpoints map to servo coordinates 0 and 180 degrees.
#define SERVO_PULSE_MIN_US 1000
#define SERVO_PULSE_MAX_US 2000
#define SERVO_MIN_MDEG 0
#define SERVO_MAX_MDEG 180000
'''


def sketch_sources(side: str, node_id: int) -> dict[str, str]:
    """Return generated files; deliberately exclude private/local configuration."""
    name = f"tracker_{side}"
    source = (FIRMWARE / "src" / "main.cpp").read_text(encoding="utf-8")
    files = {
        f"{name}.ino": (
            "// Open this sketch in Arduino IDE; select ESP32 Dev Module.\n"
            "// Edit the tracker_config.h tab, then upload to this node only.\n"
            "// tracker_node.cpp contains setup()/loop(); it is generated from\n"
            "// firmware/src/main.cpp to avoid Arduino's automatic prototypes.\n"
            "// Refresh with: python3 -m tools.prepare_tracker_firmware\n"
            "#include <Arduino.h>\n"
        ),
        "tracker_node.cpp": (
            "// Generated by tools.prepare_tracker_firmware; edit firmware/src/main.cpp.\n"
            '#include "tracker_config.h"\n'
            '#include "tracker_network.h"\n'
            f'static_assert(NODE_ID == {node_id}, "This is the {side} node sketch");\n\n'
            + source
        ),
    }
    for header in HEADERS:
        files[header] = (FIRMWARE / "include" / header).read_text(encoding="utf-8")
    return files


def prepare(output: Path = DEFAULT_OUTPUT, *, check: bool = False, network: str | None = None) -> list[Path]:
    """Write sketches, or return missing/stale paths without changes in check mode."""
    changed = []
    if network not in (None, "tracker", "configured"):
        raise ValueError("Network must be tracker or configured")
    selected_header = CONFIGURED_NETWORK if network == "configured" else None
    if network == "tracker":
        shared = network_settings(output, check=check)
        if shared is None:
            changed.append(output / NETWORK_SETTINGS)
            selected_header = ""  # Check-only: credentials do not exist yet.
        else:
            selected_header = tracker_network_header(shared)
    for side, node_id in NODES:
        folder = output / f"tracker_{side}"
        for name, content in sketch_sources(side, node_id).items():
            path = folder / name
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                changed.append(path)
                if not check:
                    folder.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")

        config = folder / "tracker_config.h"
        if not config.exists():
            changed.append(config)
            if not check:
                # Exclusive creation also protects settings if two preparations overlap.
                with config.open("x", encoding="utf-8") as stream:
                    stream.write(config_template(side, node_id))
        # Ordinary refresh preserves the selected network, as well as user settings.
        override = folder / "tracker_network.h"
        wanted = selected_header if selected_header is not None else CONFIGURED_NETWORK
        if not override.exists() or (selected_header is not None and override.read_text(encoding="utf-8") != wanted):
            changed.append(override)
            if not check:
                override.write_text(wanted, encoding="utf-8")
                override.chmod(0o600)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="Parent directory for tracker_left, tracker_middle, tracker_right and tracker_right_pair")
    parser.add_argument("--check", action="store_true",
                        help="Check generated sources are current; do not write files")
    parser.add_argument("--network", choices=("tracker", "configured"),
                        help="Select left-hosted private Wi-Fi, or return to tracker_config.h profiles; omitted preserves selection")
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    try:
        changed = prepare(output, check=args.check, network=args.network)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot prepare sketches: {exc}\n")
    if args.check:
        if changed:
            print("Missing or stale generated files:")
            for path in changed:
                print(f"  {path}")
            print("Run python3 -m tools.prepare_tracker_firmware to refresh sources.")
            return 1
        print("All Arduino sketches are current. User settings were not changed.")
        return 0

    print("Arduino sketches prepared. Existing tracker_config.h settings were preserved.")
    for side, _ in NODES:
        name = f"tracker_{side}"
        print(f"  {side.capitalize()}: {output / name / (name + '.ino')}")
    print("Select ESP32 Dev Module and manually upload each sketch to its matching board.")
    if args.network == "tracker":
        print("Left creates the private Wi-Fi at 192.168.4.1; right and middle join automatically by DHCP.")
        print("Connect the laptop using TRACKER_WIFI_SSID / TRACKER_WIFI_PASSWORD in either")
        print("tracker_network.h tab. No internet connection is needed.")
    else:
        print("Network selection is in tracker_network.h; original profiles/servo settings")
        print("are preserved in tracker_config.h. Use --network tracker for left-hosted Wi-Fi,")
        print("or --network configured to use the selected home/school/OneNet profile.")
    print("Each board centers its servo when it starts. No hardware was accessed here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
