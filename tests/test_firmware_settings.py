"""Compile-time checks in firmware/include/settings.h, exercised with the host compiler."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / "firmware" / "include" / "settings.h"
COMPILER = shutil.which("g++")
REMOVED = ("WIFI_PROFILE", "SCHOOL_WIFI_SSID", "SCHOOL_WIFI_PASSWORD", "TRACKER_WIFI_SSID",
           "TRACKER_WIFI_PASSWORD", "TRACKER_WIFI_CHANNEL", "ONENET_SSID", "ONENET_USERNAME",
           "ONENET_PASSWORD", "ONENET_SERVER_DOMAIN", "ONENET_BUILD_TIMEZONE")


@unittest.skipUnless(COMPILER, "needs a host g++")
class RemovedNetworkProfileGuardTests(unittest.TestCase):
    def compile(self, *defines):
        # A copy in an empty folder: the private config.local.h must not take part.
        with tempfile.TemporaryDirectory() as tmp:
            header = Path(tmp) / "settings.h"
            header.write_text(SETTINGS.read_text())
            return subprocess.run(
                [COMPILER, "-std=c++17", "-fsyntax-only", "-x", "c++", "-DNODE_ID=0", *defines, str(header)],
                capture_output=True, text=True, timeout=60)

    def test_hotspot_only_config_compiles(self):
        for defines in ((), ('-DWIFI_SSID="hotspot"', '-DWIFI_PASSWORD="secret"')):
            result = self.compile(*defines)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_removed_profile_setting_stops_the_build_and_names_the_fix(self):
        for name in REMOVED:
            result = self.compile('-DWIFI_SSID="old-home"', f"-D{name}=1")
            self.assertNotEqual(result.returncode, 0, name)
            self.assertIn("Network profiles were removed", result.stderr, name)
            self.assertIn("WIFI_SSID / WIFI_PASSWORD", result.stderr, name)


if __name__ == "__main__":
    unittest.main()
