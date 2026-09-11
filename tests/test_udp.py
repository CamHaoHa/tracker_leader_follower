"""Integration against independent virtual ESP32 processes over real UDP sockets."""

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from whack.controller import Controller
from whack.tracking import Geometry

ROOT = Path(__file__).resolve().parents[1]


class UdpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        geometry = Geometry()
        profile = Path(self.temp.name) / "calibration.json"
        profile.write_text(json.dumps({
            "version": 1,
            "geometry": asdict(geometry),
            "background": {f"{node}:{geometry.angle(node, point)}": None
                           for point in geometry.scan_targets() for node in (0, 1)},
        }))
        # Fixed ports deliberately exercise the actual firmware protocol. Bind
        # errors are test failures, rather than silently skipping networking.
        self.controller = Controller(geometry, calibration_path=profile)
        self.addCleanup(self.controller.close)
        self.process = None
        self.output = ""
        self.addCleanup(self.stop_nodes)

    def start_nodes(self, *args):
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "simulate_nodes.py"), "--seconds", "30", *args],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def stop_nodes(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.output, _ = self.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.output, _ = self.process.communicate(timeout=3)
                raise AssertionError("UDP simulator did not stop promptly")
            finally:
                self.process = None

    def until(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        snapshot = None
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                output, _ = self.process.communicate()
                self.fail(f"UDP simulator exited unexpectedly: {output}")
            snapshot = self.controller.poll()
            if predicate(snapshot):
                return snapshot
            time.sleep(0.005)
        self.fail(f"Condition not met within {timeout}s: {snapshot}")

    def summary(self):
        records = [json.loads(line) for line in self.output.splitlines()]
        return next(record for record in records if record["event"] == "summary")

    def test_discovery_localization_and_offline_timeout(self):
        self.start_nodes("--x", "0.75", "--y", "1.3")
        snapshot = self.until(lambda snap: snap.in_bounds)
        self.assertEqual(self.controller.transport.address(0), ("127.0.0.2", 4211))
        self.assertEqual(self.controller.transport.address(1), ("127.0.0.3", 4211))
        self.assertAlmostEqual(snapshot.position[0], 0.75, delta=0.002)
        self.assertAlmostEqual(snapshot.position[1], 1.3, delta=0.002)
        self.stop_nodes()
        stats = self.summary()
        self.assertGreaterEqual(min(stats["pings"]), 1)
        self.assertEqual(stats["overlapping_commands"], 0)
        self.assertGreaterEqual(stats["min_ping_gap_ms"], 65)
        snapshot = self.until(lambda snap: snap.position is None, timeout=2)
        self.assertFalse(snapshot.in_bounds)
        snapshot = self.until(
            lambda snap: all(self.controller.transport.address(node) is None for node in (0, 1)),
            timeout=7,
        )
        self.assertIsNone(snapshot.position)
        self.assertTrue(all("Offline" in status for status in snapshot.node_status))

    def test_empty_scene_returns_timeout_without_a_position(self):
        self.start_nodes("--empty")
        snapshot = self.until(lambda snap: snap.node_status == ("timeout", "timeout"))
        self.assertIsNone(snapshot.position)
        self.assertFalse(snapshot.in_bounds)
        self.stop_nodes()
        self.assertEqual(self.summary()["overlapping_commands"], 0)

    def test_absent_second_node_prevents_any_ping(self):
        self.start_nodes("--drop-node", "1")
        snapshot = self.until(lambda snap: self.controller.transport.address(0) is not None)
        self.assertIsNone(self.controller.transport.address(1))
        self.assertIsNone(snapshot.position)
        self.assertIsNone(self.controller.pending)
        self.stop_nodes()
        self.assertEqual(self.summary()["pings"], [0, 0])


if __name__ == "__main__":
    unittest.main()
