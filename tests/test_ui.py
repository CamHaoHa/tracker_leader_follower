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

from whack.__main__ import _record_row, CSV_FIELDS, main
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
        self.lines = []

    def delete(self, tag):
        self.ovals.clear()
        self.texts.clear()
        self.lines.clear()

    def winfo_width(self): return 900
    def winfo_height(self): return 600
    def create_oval(self, *args, **kwargs): self.ovals.append((args, kwargs))
    def create_text(self, *args, **kwargs): self.texts.append((args, kwargs))
    def create_line(self, *args, **kwargs): self.lines.append((args, kwargs))
    def create_rectangle(self, *args, **kwargs): pass

    @property
    def overlay_texts(self):
        return [t for t in self.texts if t[1].get("tags") != "grid"]


class DisplayTests(unittest.TestCase):
    def window(self, *snapshots, geometry=None):
        window = TrackerWindow.__new__(TrackerWindow)
        window.root = Mock()
        window.controller = Mock()
        window.controller.poll.side_effect = snapshots
        window.geometry = geometry or Geometry()
        window.canvas = Canvas()
        window.status_text = Mock()
        window.status_label = Mock()
        window.simulate = False
        window._closed = False
        window._diagnostics = False
        window._frame_times = deque(maxlen=120)
        window._position = None
        window._positions = []
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


PVP = Geometry(extra_sensor_x=(0.75, 0.85), zones=((0, 0.75, (0, 1)), (0.75, 1.5, (2, 3))))


def two_players(**changes):
    """A swarm snapshot with two zones: player 1 solid, player 2 one box only."""
    return snapshot(zones=(snapshot(position=(.35, 1.3)),
                           snapshot(position=(1.15, 1.2), predicted=True)), **changes)


class ZoneDisplayTests(DisplayTests):
    """Player versus player: one spot per zone, the dividing line, the mouse per half."""

    def test_two_zones_draw_two_spots_in_their_own_colours_and_the_dividing_line(self):
        window = self.window(two_players(), geometry=PVP)
        window._tick()
        self.assertEqual(window._position, (.35, 1.3))            # zone 0 is still "the" position
        self.assertEqual(window._positions, [(.35, 1.3), (1.15, 1.2)])
        (first, first_kw), (second, second_kw) = window.canvas.ovals
        self.assertEqual(first_kw["fill"], TrackerWindow.DOTS[0])
        self.assertGreater(first[0], 450)                          # player 1's half is the right of the screen
        self.assertEqual(second_kw["fill"], "")                    # one box: hollow, in player 2's colour
        self.assertEqual(second_kw["outline"], TrackerWindow.PREDICTED_DOTS[1])
        self.assertLess(second[0], 450)
        divider = [args for args, kw in window.canvas.lines if kw.get("dash")]
        self.assertEqual(divider, [(450, 0, 450, 600)])
        labels = [t[1]["text"] for t in window.canvas.texts if t[1]["text"].startswith("Player")]
        self.assertEqual(labels, ["Player 1", "Player 2"])

    def test_a_missing_player_hides_only_that_spot(self):
        window = self.window(snapshot(zones=(snapshot(position=None, state="find", in_bounds=False),
                                             snapshot(position=(1.15, 1.2)))), geometry=PVP)
        window._tick()
        self.assertEqual(window._positions, [None, (1.15, 1.2)])
        self.assertIsNone(window._position)
        self.assertEqual(len(window.canvas.ovals), 1)
        self.assertEqual(window.canvas.ovals[0][1]["fill"], TrackerWindow.DOTS[1])

    def test_one_zone_draws_no_divider(self):
        window = self.window(snapshot())
        window._tick()
        self.assertEqual([args for args, kw in window.canvas.lines if kw.get("dash")], [])
        self.assertEqual(len(window.canvas.ovals), 1)

    def test_diagnostics_list_both_players(self):
        window = self.window(two_players(), geometry=PVP)
        window._diagnostics = True
        window._tick()
        text = window.canvas.overlay_texts[0][1]["text"]
        self.assertIn("Player 1: x = 0.350 m    y = 1.300 m", text)
        self.assertIn("Player 2: x = 1.150 m    y = 1.200 m", text)
        self.assertIn("State: P1 track, P2 track", text)

    def test_the_mouse_moves_the_player_of_the_half_it_is_in(self):
        window = self.window(two_players(), geometry=PVP)
        window._mouse(SimpleNamespace(x=100, y=300))             # screen left = field x 1.33: player 2
        (x, y, player), _ = window.controller.set_simulated_position.call_args
        self.assertAlmostEqual(x, 1.3333, places=3)
        self.assertAlmostEqual(y, 1.3)
        self.assertEqual(player, 1)
        window._mouse(SimpleNamespace(x=800, y=0))               # screen right = field x 0.17: player 1
        self.assertEqual(window.controller.set_simulated_position.call_args[0][2], 0)
        single = self.window(snapshot())
        single._mouse(SimpleNamespace(x=100, y=300))
        self.assertEqual(len(single.controller.set_simulated_position.call_args[0]), 2)


class ZoneRecordTests(unittest.TestCase):
    def test_the_csv_row_carries_both_players_only_for_two_zones(self):
        row = _record_row(1.0, two_players())
        self.assertEqual(len(row), len(CSV_FIELDS))
        zones = json.loads(row[-1])
        self.assertEqual([z["x"] for z in zones], [.35, 1.15])
        self.assertEqual([z["contributors"] for z in zones], [0, 0])
        self.assertEqual(zones[1]["predicted"], True)
        self.assertEqual(_record_row(1.0, snapshot())[-1], "")

    def test_headless_json_lists_the_zones(self):
        result, report, controller, _ = HeadlessTests().run_cli(["--simulate"], [two_players()])
        self.assertEqual(result, 0)
        self.assertEqual([z["state"] for z in report["zones"]], ["track", "track"])
        self.assertEqual(report["zones"][1]["y"], 1.2)
        _, report, _, _ = HeadlessTests().run_cli(["--simulate"], [snapshot()])
        self.assertEqual(report["zones"], [])


if __name__ == "__main__":
    unittest.main()
