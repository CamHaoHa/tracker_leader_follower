"""Run with python -m whack --simulate, or omit --simulate for hardware."""

import argparse
import csv
import json
import math
import sys
import time

from .controller import Controller
from .lockscan import LockScanController
from .swarm import SwarmController
from .tracking import load_geometry


CSV_FIELDS = (
    "elapsed_s", "x_m", "y_m", "fix_age_s", "in_bounds", "dead_zone",
    "state", "predicted", "confidence", "update_hz", "status", "nodes", "aim_x", "aim_y", "reason", "alert", "contributors")


def _finite_age(snapshot):
    return snapshot.fix_age_s if math.isfinite(snapshot.fix_age_s) else None


def _record_row(elapsed, snapshot, aim=(None, None), reason=""):
    return (
        round(elapsed, 3), *(snapshot.position or ("", "")), _finite_age(snapshot),
        snapshot.in_bounds, snapshot.dead_zone, snapshot.state, snapshot.predicted,
        snapshot.confidence, snapshot.update_hz, snapshot.status, " | ".join(snapshot.node_status),
        *("" if v is None else round(v, 3) for v in aim),  # where the servos were last aimed
        reason,  # tracker's last accept/reject reason, for post-run diagnosis
        getattr(snapshot, "alert", ""), getattr(snapshot, "contributors", ""),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Two-node ultrasound tracking visualizer")
    parser.add_argument("--simulate", action="store_true", help="Use timed virtual sensors; mouse controls the player")
    parser.add_argument("--headless", action="store_true", help="Run diagnostics without the tracking window")
    parser.add_argument("--seconds", type=float, default=10, help="Duration of headless diagnostics")
    parser.add_argument("--config", help="Geometry JSON; see config.example.json")
    parser.add_argument("--calibration", default="calibration.local.json", help="Empty-area calibration profile")
    parser.add_argument("--calibrate", action="store_true", help="Begin empty-area calibration at startup")
    parser.add_argument("--start-mode", choices=("center", "search"), default="center",
                        help="Acquire a player at the field centre or search the whole field (default: center)")
    parser.add_argument("--nodes", nargs="+", metavar="IP", help="Optional fixed node IPv4 addresses, left to right")
    parser.add_argument("--port", type=int, default=4210, help="Local UDP port; hardware discovery uses 4210")
    parser.add_argument("--record", help="Write timestamped tracking observations to a CSV file")
    parser.add_argument("--tracker", choices=("swarm", "lock", "pairs"), default="swarm",
                        help="swarm: independent sweeps, leader-follower aiming (default); "
                             "lock: search, lock on the first echo, scan a window round it; "
                             "pairs: paired two-box scheduler")
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds <= 0 or not 1 <= args.port <= 65535:
        parser.error("Require positive finite seconds and a port from 1 to 65535")
    controller = None
    logfile = None
    try:
        trackers = {"swarm": SwarmController, "lock": LockScanController, "pairs": Controller}
        controller = trackers[args.tracker](
            load_geometry(args.config), simulate=args.simulate, calibration_path=args.calibration,
            port=args.port, node_ips=args.nodes, start_mode=args.start_mode,
            # The desktop hardware window waits for Search/Calibrate; headless and
            # simulation runs keep starting on their own.
            start_paused=not args.simulate and not args.headless and not args.calibrate,
        )
        if args.calibrate:
            controller.start_calibration()
        if args.record:
            logfile = open(args.record, "w", newline="", encoding="utf-8")
            writer = csv.writer(logfile)
            writer.writerow(CSV_FIELDS)
            original_poll = controller.poll
            start = time.monotonic()
            last_record = [-1.0]

            def recorded_poll():
                snap = original_poll()
                elapsed = time.monotonic() - start
                if elapsed - last_record[0] >= .1:
                    aim = getattr(controller, "target", None)
                    if not (isinstance(aim, tuple) and len(aim) == 2):
                        aim = (None, None)
                    reason = getattr(getattr(controller, "tracker", None), "reason", "")
                    writer.writerow(_record_row(elapsed, snap, aim, reason if isinstance(reason, str) else ""))
                    logfile.flush()
                    last_record[0] = elapsed
                return snap

            controller.poll = recorded_poll
        if args.headless:
            start = time.monotonic()
            tracked = 0
            polls = 0
            snap = None
            while snap is None or time.monotonic() - start < args.seconds:
                snap = controller.poll()
                polls += 1
                tracked += bool(snap.in_bounds and snap.position is not None)
                time.sleep(.01)
            print(json.dumps({
                "mode": "simulation" if args.simulate else "hardware", "polls": polls,
                "tracked_polls": tracked, "position": snap.position, "status": snap.status,
                "nodes": snap.node_status, "state": snap.state, "predicted": snap.predicted,
                "confidence": snap.confidence, "fix_age_s": _finite_age(snap),
                "update_hz": snap.update_hz,
            }, allow_nan=False))
            calibration_done = args.calibrate and bool(controller.background) and not controller.calibrating
            return 0 if tracked or calibration_done else 1
        try:
            import tkinter as tk
        except ImportError as exc:
            raise RuntimeError("Tk is missing; install Python with Tcl/Tk support") from exc
        from .ui import TrackerWindow
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError("Cannot open a display; use --headless or run from a desktop session") from exc
        TrackerWindow(root, controller, simulate=args.simulate)
        root.mainloop()
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"Cannot start tracker: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        if controller:
            controller.close()
        if logfile:
            logfile.close()


if __name__ == "__main__":
    raise SystemExit(main())
