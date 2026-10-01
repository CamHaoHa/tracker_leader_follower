from pathlib import Path
import contextlib
import io
import tempfile
import unittest

from tools.prepare_tracker_firmware import FIRMWARE, config_template, main, prepare


class PrepareTrackerFirmwareTests(unittest.TestCase):
    def test_independent_sketches_use_canonical_firmware_and_distinct_node_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            prepare(output)
            canonical = (FIRMWARE / "src" / "main.cpp").read_text()
            for side, node_id in (("left", 0), ("middle", 1), ("right", 2), ("right_pair", 1)):
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
            private_settings = ('#define NODE_ID 0\n#define WIFI_SSID "hotspot-test-only"\n'
                                '#define WIFI_PASSWORD "test-only"\n#define SERVO_REVERSED 1\n')
            config.write_text(private_settings)
            source = output / "tracker_left" / "tracker_node.cpp"
            source.write_text("stale generated code")
            self.assertIn(source, prepare(output))
            self.assertEqual(config.read_text(), private_settings)
            self.assertEqual(prepare(output, check=True), [])

    def test_template_has_one_wifi_block_for_the_phone_hotspot(self):
        for side, node_id in (("left", 0), ("middle", 1), ("right", 2), ("right_pair", 1)):
            template = config_template(side, node_id)
            wifi = [line for line in template.splitlines()
                    if line.startswith("#define") and ("WIFI" in line or "ONENET" in line)]
            self.assertEqual(wifi, ['#define WIFI_SSID ""', '#define WIFI_PASSWORD ""'], side)
            self.assertIn("phone hotspot", template)
            self.assertIn("Maximise Compatibility", template)
            self.assertIn("\\xE2\\x80\\x99", template)   # the iPhone apostrophe, as C escapes

    def test_template_uses_the_shared_pin_map_and_only_the_middle_box_has_a_buzzer(self):
        for side, node_id in (("left", 0), ("middle", 1), ("right", 2), ("right_pair", 1)):
            template = config_template(side, node_id)
            for line in ("#define SERVO_PIN 33", "#define ULTRASONIC_TRIG_PIN 32",
                         "#define ULTRASONIC_ECHO_PIN 34"):
                self.assertIn(line, template.splitlines())
            self.assertEqual("#define BUZZER_PIN 25" in template.splitlines(), side == "middle", side)

    def test_firmware_defaults_match_the_template_pin_map(self):
        settings = (FIRMWARE / "include" / "settings.h").read_text()
        example = (FIRMWARE / "include" / "config.example.h").read_text()
        for line in ("#define SERVO_PIN 33", "#define ULTRASONIC_TRIG_PIN 32",
                     "#define ULTRASONIC_ECHO_PIN 34"):
            self.assertIn(line, settings.splitlines())
            self.assertIn(line, example.splitlines())
        self.assertIn("#define BUZZER_PIN -1", settings.splitlines())   # no buzzer unless configured
        self.assertIn("#if NODE_ID == 1\n#define BUZZER_PIN 25\n#endif\n", example)

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

    def test_only_the_private_config_selects_the_network(self):
        # No generated network override: settings.h takes Wi-Fi from tracker_config.h alone.
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            prepare(output)
            for side in ("left", "middle", "right", "right_pair"):
                folder = output / f"tracker_{side}"
                self.assertEqual(sorted(path.name for path in folder.iterdir()),
                                 sorted(["settings.h", "tracker_config.h", "tracker_node.cpp",
                                         f"tracker_{side}.ino", "wm_protocol.h"]))
                cpp = (folder / "tracker_node.cpp").read_text()
                self.assertNotIn("tracker_network", cpp)
                self.assertLess(cpp.index('#include "tracker_config.h"'), cpp.index('#include "settings.h"'))
            self.assertEqual(sorted(path.name for path in output.iterdir()),
                             ["tracker_left", "tracker_middle", "tracker_right", "tracker_right_pair"])

    def test_cli_prepares_sketches_and_points_at_the_hotspot_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--output-dir", tmp]), 0)
                self.assertEqual(main(["--output-dir", tmp, "--check"]), 0)
            self.assertIn("WIFI_SSID / WIFI_PASSWORD", output.getvalue())
            self.assertIn("hotspot", output.getvalue())
            self.assertTrue((Path(tmp) / "tracker_middle" / "tracker_middle.ino").is_file())

    def test_cli_no_longer_accepts_a_network_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main(["--output-dir", tmp, "--network", "tracker"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
