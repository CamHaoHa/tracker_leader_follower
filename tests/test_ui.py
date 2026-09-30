"""Display behavior and CLI diagnostics without opening a desktop or network socket."""

from collections import deque
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from whack.__main__ import main
from whack.tracking import Geometry
from whack.ui import TrackerWindow


def snapshot(**changes):
    fields = dict(
        position=(.75, 1.2), status="Tracking", node_status=("ready", "ready"),
        dead_zone=False, in_bounds=True, state="track", predicted=False,
        confidence=.9, fix_age_s=.05, update_hz=6.2,
    )
    fields.update(changes)
    return SimpleNamespace(**fields)


class Canvas:
    def __init__(self):
        self.ovals = []
        self.texts = []
        self.arcs = []

    def delete(self, tag):
        self.ovals.clear()
        self.texts.clear()
        self.arcs.clear()

    def winfo_width(self): return 900
    def winfo_height(self): return 600
    def create_oval(self, *args, **kwargs): self.ovals.append((args, kwargs))
    def create_text(self, *args, **kwargs): self.texts.append((args, kwargs))
    def create_line(self, *args, **kwargs): pass
    def create_rectangle(self, *args, **kwargs): pass
    def create_arc(self, *args, **kwargs): self.arcs.append((args, kwargs))

    @property
    def overlay_texts(self):
        return [t for t in self.texts if t[1].get("tags") != "grid"]


class DisplayTests(unittest.TestCase):
    def window(self, *snapshots):
        window = TrackerWindow.__new__(TrackerWindow)
        window.root = Mock()
        window.controller = Mock()
        window.controller.poll.side_effect = snapshots
        window.geometry = Geometry()
        window.canvas = Canvas()
        window.status_text = Mock()
        window.status_label = Mock()
        window.simulate = False
        window._closed = False
        window._diagnostics = False
        window._frame_times = deque(maxlen=120)
        window._position = None
        window.snapshot = None
        return window

    def test_one_spot_switches_to_prediction_and_disappears_on_loss(self):
        window = self.window(
            snapshot(), snapshot(predicted=True, state="local_search"),
            # Even an inconsistent stale coordinate cannot draw a lost target.
            snapshot(state="lost"),
        )
        window._tick()
        self.assertEqual(len(window.canvas.ovals), 1)
        self.assertEqual(window.canvas.ovals[0][1]["fill"], window.DOT)
        window._tick()
        self.assertEqual(len(window.canvas.ovals), 1)
        self.assertEqual(window.canvas.ovals[0][1]["fill"], "")
        self.assertEqual(window.canvas.ovals[0][1]["outline"], window.PREDICTED_DOT)
        window._tick()
        self.assertEqual(window.canvas.ovals, [])
        self.assertEqual(window.canvas.overlay_texts, [])
        self.assertEqual(window.controller.poll.call_count, 3)
        self.assertTrue(all(call.args[0] == 16 for call in window.root.after.call_args_list))
        window.root.bell.assert_not_called()

    def test_outside_missing_and_nonfinite_positions_never_leave_old_spot(self):
        for changes in (
            {"position": None}, {"position": (float("nan"), 1.2)},
            {"position": (.75, float("inf"))}, {"position": (10, 1.2)},
            {"position": (.75, .2)}, {"in_bounds": False}, {"dead_zone": True},
        ):
            with self.subTest(changes=changes):
                window = self.window(snapshot(), snapshot(**changes))
                window._tick()
                self.assertEqual(len(window.canvas.ovals), 1)
                window._tick()
                self.assertIsNone(window._position)
                self.assertEqual(window.canvas.ovals, [])
                self.assertEqual(window.canvas.overlay_texts, [])
                window.root.bell.assert_not_called()

    def test_field_boundary_is_visible_and_near_edge_maps_to_top(self):
        window = self.window(snapshot(position=(-.001, .599)))
        window._tick()
        self.assertEqual(window._position, (0, .6))
        # Mirrored: field x = 0 (the box on the player's right) draws at the right edge.
        self.assertEqual(window._screen(window._position), (900, 0))
        self.assertEqual(window._screen((1.5, window.geometry.far_y)), (0, 600))

    def test_diagnostics_distinguish_measurements_from_display_refresh(self):
        window = self.window(snapshot(), snapshot(predicted=True, fix_age_s=.22))
        window._diagnostics = True
        with patch("whack.ui.time.monotonic", side_effect=(1.0, 1.016)):
            window._tick()
            window._tick()
        text = window.canvas.overlay_texts[0][1]["text"]
        self.assertIn("Fresh position updates: 6.2 Hz", text)
        self.assertIn("Display refresh: 62 FPS", text)
        self.assertIn("220 ms", text)
        self.assertIn("90%", text)
        self.assertEqual(len(window.canvas.ovals), 1)

    def test_diagnostics_overlay_draws_each_box_window_and_lock(self):
        boxes = (
            {"node": 0, "mode": "track", "bearing_deg": 60.0, "window_deg": (45.0, 75.0), "lock": (60.0, 1.1)},
            {"node": 1, "mode": "search", "bearing_deg": 120.0},
            {"node": "bad", "mode": "track", "bearing_deg": 1.0},
        )
        window = self.window(snapshot(boxes=boxes), snapshot(boxes=boxes))
        window._tick()
        self.assertEqual(len(window.canvas.ovals), 1)          # the spot only, overlay is off
        window._diagnostics = True
        window._tick()
        rings = [o for o in window.canvas.ovals if o[1].get("tags") == "lock"]
        self.assertEqual(len(rings), 1)
        self.assertEqual(len(window.canvas.arcs), 2)           # outer band and its inner cut-out
        outer = window.canvas.arcs[0][1]
        self.assertEqual((outer["start"], outer["extent"]), (225.0, 30.0))
        self.assertIn("Overlay:", window.canvas.overlay_texts[0][1]["text"])

    def test_pause_toggles_and_reset_delegates(self):
        window = self.window()
        window.controller.paused = False
        window._pause()
        window.controller.pause.assert_called_once_with()
        window.controller.paused = True
        window._pause()
        window.controller.resume.assert_called_once_with()
        window._reset()
        window.controller.reset.assert_called_once_with()

    def test_controls_delegate_acquisition_and_calibration(self):
        window = self.window()
        window._acquire()
        window._calibrate()
        window.controller.start_acquisition.assert_called_once_with()
        window.controller.start_calibration.assert_called_once_with()


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class HeadlessTests(unittest.TestCase):
    def run_cli(self, args, snapshots, *, background=None, calibrating=False):
        clock = Clock()
        controller = Mock(background=background or {}, calibrating=calibrating)
        values = iter(snapshots)
        last = snapshots[-1]
        controller.poll.side_effect = lambda: next(values, last)
        output = io.StringIO()
        with patch("whack.__main__.Controller", return_value=controller), \
                patch("whack.__main__.SwarmController", return_value=controller) as constructor, \
                patch("whack.__main__.time.monotonic", clock), \
                patch("whack.__main__.time.sleep", clock.sleep), \
                contextlib.redirect_stdout(output):
            result = main(["--headless", "--seconds", "0.25", *args])
        return result, json.loads(output.getvalue()), controller, constructor

    def test_headless_records_measured_and_predicted_fixes_with_age(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "observations.csv"
            result, report, controller, constructor = self.run_cli(
                ["--simulate", "--start-mode", "search", "--record", str(filename)],
                [snapshot(), snapshot(predicted=True, fix_age_s=.2, confidence=.6)],
            )
            self.assertEqual(result, 0)
            self.assertTrue(report["predicted"])
            self.assertEqual(report["update_hz"], 6.2)
            self.assertEqual(report["confidence"], .6)
            self.assertEqual(constructor.call_args.kwargs["start_mode"], "search")
            controller.close.assert_called_once()
            with filename.open() as file:
                rows = list(csv.DictReader(file))
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[0]["predicted"], "False")
            self.assertEqual(rows[-1]["predicted"], "True")
            self.assertEqual(rows[-1]["fix_age_s"], "0.2")
            self.assertEqual(rows[-1]["update_hz"], "6.2")

    def test_no_fix_has_json_null_age_and_failure_exit(self):
        result, report, controller, _ = self.run_cli(
            ["--simulate"],
            [snapshot(position=None, in_bounds=False, state="lost", fix_age_s=math.inf,
                      confidence=0, update_hz=0)],
        )
        self.assertEqual(result, 1)
        self.assertEqual(report["tracked_polls"], 0)
        self.assertIsNone(report["fix_age_s"])
        self.assertIsNone(report["position"])
        controller.close.assert_called_once()

    def test_calibration_success_requires_completion(self):
        no_fix = snapshot(position=None, in_bounds=False, state="calibration", fix_age_s=math.inf)
        for in_progress, expected in ((True, 1), (False, 0)):
            with self.subTest(in_progress=in_progress):
                result, _, controller, _ = self.run_cli(
                    ["--calibrate"], [no_fix], background={"0:90000": None},
                    calibrating=in_progress,
                )
                self.assertEqual(result, expected)
                controller.start_calibration.assert_called_once()


if __name__ == "__main__":
    unittest.main()
