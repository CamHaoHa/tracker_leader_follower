from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest

from tools.prepare_tracker_firmware import FIRMWARE, NETWORK_SETTINGS, config_template, main, prepare


class PrepareTrackerFirmwareTests(unittest.TestCase):
    def test_independent_sketches_use_canonical_firmware_and_distinct_node_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            prepare(output)
            canonical = (FIRMWARE / "src" / "main.cpp").read_text()
            for side, node_id in (("left", 0), ("right", 1), ("middle", 2)):
                folder = output / f"tracker_{side}"
                self.assertTrue((folder / f"tracker_{side}.ino").is_file())
                self.assertTrue((folder / "tracker_node.cpp").read_text().endswith(canonical))
                self.assertIn(f"#define NODE_ID {node_id}", (folder / "tracker_config.h").read_text())
                self.assertFalse((folder / "config.local.h").exists())

    def test_refresh_preserves_credentials_and_mounting_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            prepare(output)
            config = output / "tracker_left" / "tracker_config.h"
            private_settings = ('#define NODE_ID 0\n#define WIFI_PASSWORD "test-only"\n'
                                '#define SERVO_REVERSED 1\n#define WIFI_PROFILE 1\n'
                                '#define SCHOOL_WIFI_PASSWORD "school-test-only"\n')
            config.write_text(private_settings)
            source = output / "tracker_left" / "tracker_node.cpp"
            source.write_text("stale generated code")
            self.assertIn(source, prepare(output))
            self.assertEqual(config.read_text(), private_settings)
            self.assertEqual(prepare(output, check=True), [])

    def test_template_preserves_two_personal_profiles_and_optional_enterprise(self):
        template = config_template("left", 0)
        for name in ("WIFI_SSID", "WIFI_PASSWORD", "SCHOOL_WIFI_SSID", "SCHOOL_WIFI_PASSWORD",
                     "ONENET_USERNAME", "ONENET_PASSWORD"):
            self.assertIn(f'#define {name} ""', template)
        self.assertIn("#define WIFI_PROFILE 0", template)
        self.assertIn("Arduino-ESP32 3.3+", template)

    def test_check_reports_missing_and_stale_sources_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "absent"
            self.assertTrue(prepare(output, check=True))
            self.assertFalse(output.exists())
            prepare(output)
            header = output / "tracker_right" / "settings.h"
            header.write_text("outdated")
            self.assertEqual(prepare(output, check=True), [header])
            self.assertEqual(header.read_text(), "outdated")

    def test_tracker_network_pairs_credentials_without_replacing_private_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            prepare(output)
            configs = {}
            for side in ("left", "right"):
                path = output / f"tracker_{side}" / "tracker_config.h"
                configs[path] = path.read_text().replace('#define WIFI_PASSWORD ""',
                                                       '#define WIFI_PASSWORD "home-test-only"')
                path.write_text(configs[path])
            prepare(output, network="tracker")
            shared = json.loads((output / NETWORK_SETTINGS).read_text())
            self.assertEqual(shared["ssid"], "TrackerNet")
            self.assertGreaterEqual(len(shared["password"]), 8)
            self.assertEqual((output / NETWORK_SETTINGS).stat().st_mode & 0o777, 0o600)
            headers = [(output / f"tracker_{side}" / "tracker_network.h").read_text()
                       for side in ("left", "right")]
            self.assertEqual(headers[0], headers[1])
            self.assertIn('#define WIFI_PROFILE 3', headers[0])
            self.assertIn(json.dumps(shared["password"]), headers[0])
            self.assertEqual(prepare(output, network="tracker", check=True), [])
            self.assertEqual(prepare(output), [])
            self.assertEqual(prepare(output, network="tracker"), [])
            for path, content in configs.items():
                self.assertEqual(path.read_text(), content)
            # Switching back preserves credentials for both existing profiles
            # and the newly-created tracker network.
            prepare(output, network="configured")
            self.assertEqual(json.loads((output / NETWORK_SETTINGS).read_text()), shared)
            for path, content in configs.items():
                self.assertEqual(path.read_text(), content)
                self.assertNotIn('#define WIFI_PROFILE', (path.parent / "tracker_network.h").read_text())
            prepare(output, network="tracker")
            self.assertEqual((output / "tracker_left" / "tracker_network.h").read_text(), headers[0])

    def test_tracker_check_never_creates_credentials_or_changes_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "absent"
            paths = prepare(output, network="tracker", check=True)
            self.assertIn(output / NETWORK_SETTINGS, paths)
            self.assertFalse(output.exists())
            prepare(output)
            original = (output / "tracker_left" / "tracker_network.h").read_text()
            self.assertTrue(prepare(output, network="tracker", check=True))
            self.assertFalse((output / NETWORK_SETTINGS).exists())
            self.assertEqual((output / "tracker_left" / "tracker_network.h").read_text(), original)

    def test_invalid_shared_credentials_fail_without_rewriting_sketches(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); prepare(output, network="tracker")
            header = output / "tracker_left" / "tracker_network.h"
            original = header.read_text()
            shared = json.loads((output / NETWORK_SETTINGS).read_text())
            for bad in (dict(shared, password="short"), dict(shared, ssid="bad\nSSID"),
                        dict(shared, channel=True), dict(shared, channel=99)):
                (output / NETWORK_SETTINGS).write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    prepare(output, network="tracker")
                self.assertEqual(header.read_text(), original)

    def test_cli_prepares_ready_to_upload_pair_without_printing_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--output-dir", tmp, "--network", "tracker"]), 0)
            secret = json.loads((Path(tmp) / NETWORK_SETTINGS).read_text())["password"]
            self.assertNotIn(secret, output.getvalue())
            self.assertIn("192.168.4.1", output.getvalue())
            cpp = (Path(tmp) / "tracker_left" / "tracker_node.cpp").read_text()
            self.assertLess(cpp.index('#include "tracker_config.h"'), cpp.index('#include "tracker_network.h"'))
            self.assertLess(cpp.index('#include "tracker_network.h"'), cpp.index('#include "settings.h"'))


if __name__ == "__main__":
    unittest.main()
