"""Run with python -m whack --simulate, or omit --simulate for hardware."""

import argparse
import csv
import json
import math
import sys
import time

from .controller import Controller
from .tracking import load_geometry


def main():
    parser = argparse.ArgumentParser(description="Two-node ultrasound tracking visualizer")
    parser.add_argument("--simulate", action="store_true", help="Use two timed virtual sensors; mouse controls player")
    parser.add_argument("--headless", action="store_true", help="Run diagnostic acquisition without the tracking window")
    parser.add_argument("--seconds", type=float, default=10, help="Duration of headless diagnostics")
    parser.add_argument("--config", help="Geometry JSON; see config.example.json")
    parser.add_argument("--calibration", default="calibration.local.json", help="Empty-area calibration profile")
    parser.add_argument("--calibrate", action="store_true", help="Begin empty-area calibration at startup")
    parser.add_argument("--nodes", nargs=2, metavar=("LEFT_IP", "RIGHT_IP"), help="Optional fixed node IPv4 addresses")
    parser.add_argument("--port", type=int, default=4210, help="Local UDP port; hardware discovery uses4210")
    parser.add_argument("--record", help="Write timestamped tracking observations to a CSV file")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0 or not 1 <= args.port <= 65535:
        parser.error("Require positive finite seconds and a port from1 to65535")
    controller = None
    logfile = None
    try:
        controller = Controller(load_geometry(args.config),simulate=args.simulate,
                                calibration_path=args.calibration,port=args.port,node_ips=args.nodes)
        if args.calibrate:
            controller.start_calibration()
        if args.record:
            logfile = open(args.record,"w",newline="",encoding="utf-8")
            writer = csv.writer(logfile)
            writer.writerow(["elapsed_s","x_m","y_m","fix_age_s","in_bounds","dead_zone","status","left","right"])
            original_poll = controller.poll
            start = time.monotonic()
            last_record = [-1.0]
            def recorded_poll():
                snap = original_poll()
                elapsed = time.monotonic()-start
                if elapsed-last_record[0] >= .1:
                    writer.writerow([round(elapsed,3),*(snap.position or ("","")),
                                     time.monotonic()-controller.tracker.last_good,snap.in_bounds,
                                     snap.dead_zone,snap.status,*snap.node_status])
                    logfile.flush()
                    last_record[0] = elapsed
                return snap
            controller.poll = recorded_poll
        if args.headless:
            start = time.monotonic(); tracked = 0; polls = 0; snap = None
            while time.monotonic()-start < args.seconds:
                snap = controller.poll(); polls += 1; tracked += snap.in_bounds
                time.sleep(.01)
            print(json.dumps({"mode":"simulation" if args.simulate else "hardware","polls":polls,
                              "tracked_polls":tracked,"position":snap.position,"status":snap.status,
                              "nodes":snap.node_status}))
            return 0 if tracked or (args.calibrate and controller.background) else 1
        try:
            import tkinter as tk
        except ImportError as exc:
            raise RuntimeError("Tk is missing; install Python with Tcl/Tk support") from exc
        from .ui import TrackerWindow
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError("Cannot open a display; use --headless or run from a desktop session") from exc
        TrackerWindow(root,controller,simulate=args.simulate)
        root.mainloop()
        return 0
    except (OSError,ValueError,TypeError,RuntimeError) as exc:
        print(f"Cannot start tracker: {exc}",file=sys.stderr)
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
