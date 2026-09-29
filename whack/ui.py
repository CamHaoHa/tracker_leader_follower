"""Black-screen visualizer for current dual-ultrasonic position estimates."""

from __future__ import annotations

from collections import deque
import math
import time
import tkinter as tk


class TrackerWindow:
    """Display one current position; acquisition is owned by the controller.

    Coordinates are metres from the tracking area's left edge along x and
    away from the wall along y. The near edge maps to the canvas top.
    """

    BACKGROUND = "#000000"
    DOT = "#00E5FF"
    PREDICTED_DOT = "#007C89"
    TEXT = "#D4D4D4"
    MUTED = "#8D8D8D"
    # Negative Tk sizes are pixels; large enough to read from the field.
    FONT_STATUS = ("TkDefaultFont", -24, "bold")
    FONT_BUTTON = ("TkDefaultFont", -17)
    FONT_DIAGNOSTICS = ("TkDefaultFont", -21)
    FONT_FOOTER = ("TkDefaultFont", -14)
    FONT_BANNER = ("TkDefaultFont", -64, "bold")
    WARN = "#E08A52"
    GRID = "#1C262A"
    GRID_MAJOR = "#2E3E44"
    FRAME = "#55686F"
    GRID_STEP_M = 0.25

    def __init__(self, root: tk.Tk, controller, simulate: bool = False) -> None:
        self.root = root
        self.controller = controller
        self.simulate = simulate
        self.geometry = controller.geometry
        self.snapshot = None
        self._closed = False
        self._after_id = None
        self._diagnostics = False
        self._fullscreen = False
        self._position = None
        self._frame_times = deque(maxlen=120)

        root.title("Dual ultrasonic tracker")
        root.geometry("1280x800")
        root.minsize(600, 400)
        root.configure(bg=self.BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.close())
        root.bind("<F11>", self._toggle_fullscreen)
        root.bind("<KeyPress-d>", self._toggle_diagnostics)
        root.bind("<KeyPress-D>", self._toggle_diagnostics)
        root.bind("<KeyPress-c>", self._calibrate)
        root.bind("<KeyPress-C>", self._calibrate)
        root.bind("<space>", self._acquire)
        root.bind("<KeyPress-p>", self._pause)
        root.bind("<KeyPress-P>", self._pause)
        root.bind("<KeyPress-r>", self._reset)
        root.bind("<KeyPress-R>", self._reset)

        toolbar = tk.Frame(root, bg=self.BACKGROUND, padx=14, pady=10)
        toolbar.pack(fill="x")
        self.status_text = tk.StringVar(value="Waiting for position")
        self.status_label = tk.Label(
            toolbar, textvariable=self.status_text, anchor="w", justify="left",
            bg=self.BACKGROUND, fg=self.TEXT, font=self.FONT_STATUS,
        )
        self.status_label.pack(side="top", fill="x")
        controls = tk.Frame(toolbar, bg=self.BACKGROUND)
        controls.pack(side="top", fill="x", pady=(8, 0))
        # Buttons pack right-to-left: the first created sits at the far right.
        self.diagnostics_button = self._button(controls, "Diagnostics (D)", self._toggle_diagnostics)
        if not simulate:
            self._button(controls, "Calibrate (C)", self._calibrate)
        self.reset_button = self._button(controls, "Reset (R)", self._reset)
        self.pause_button = self._button(controls, "Pause (P)", self._pause)
        self.search_button = self._button(controls, "Search (Space)", self._acquire)

        self.canvas = tk.Canvas(root, bg=self.BACKGROUND, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._resize)
        if simulate:
            self.canvas.bind("<Motion>", self._mouse)
        footer = "Mouse simulation" if simulate else "Live sensors"
        tk.Label(
            root, text=f"{footer}    Space: search    P: pause/resume    R: reset (stop and forget player)    "
                       f"{'' if simulate else 'C: calibrate    '}D: diagnostics    F11: fullscreen    Esc: close",
            bg=self.BACKGROUND, fg=self.MUTED, font=self.FONT_FOOTER, pady=6,
        ).pack(fill="x")
        self._tick()

    def _button(self, parent, label, command):
        button = tk.Button(
            parent, text=label, command=command, bg="#202020", fg=self.TEXT,
            activebackground="#333333", activeforeground="#FFFFFF",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=self.BACKGROUND, highlightcolor=self.DOT,
            padx=14, pady=8, font=self.FONT_BUTTON, cursor="hand2",
        )
        button.pack(side="right", padx=(10, 0))
        return button

    def _resize(self, event=None) -> None:
        # Let status wrap rather than push controls beyond the window edge.
        self.status_label.configure(wraplength=max(160, self.root.winfo_width() - 40))
        self._draw()

    def _calibrate(self, event=None):
        if not self.simulate:
            self.controller.start_calibration()
        return "break"

    def _acquire(self, event=None):
        self.controller.start_acquisition()
        return "break"

    def _pause(self, event=None):
        if getattr(self.controller, "paused", False):
            self.controller.resume()
        else:
            self.controller.pause()
        self._update_pause_button()
        return "break"

    def _reset(self, event=None):
        self.controller.reset()
        self._update_pause_button()
        return "break"

    def _update_pause_button(self) -> None:
        button = getattr(self, "pause_button", None)
        if button is not None:
            button.configure(text="Resume (P)" if self.controller.paused else "Pause (P)")

    def _toggle_diagnostics(self, event=None):
        self._diagnostics = not self._diagnostics
        self.diagnostics_button.configure(
            text="Hide diagnostics (D)" if self._diagnostics else "Diagnostics (D)"
        )
        self._draw()
        return "break"

    def _toggle_fullscreen(self, event=None):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)
        return "break"

    def _mouse(self, event) -> None:
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        # Mirrored like the display: canvas left is the player's left.
        x = (1 - event.x / width) * self.geometry.width
        y = self.geometry.near_y + event.y / height * (self.geometry.far_y - self.geometry.near_y)
        self.controller.set_simulated_position(x, y)

    def _screen(self, position) -> tuple[float, float]:
        # Convert metres to pixels independently on each axis. The field's near
        # edge is the top of the screen, its far edge the bottom. This stretches
        # to the window size; it is a position display, not a camera image.
        # Field x runs from the LEFT box as seen from the screen, which is the
        # player's RIGHT. The player faces the screen, so mirror x: a step to
        # the player's right moves the spot right on the screen they look at.
        x, y = position
        return (
            (1 - x / self.geometry.width) * self.canvas.winfo_width(),
            (y - self.geometry.near_y) / (self.geometry.far_y - self.geometry.near_y)
            * self.canvas.winfo_height(),
        )

    def _tick(self) -> None:
        if self._closed:
            return
        # One quick poll advances networking/search and asks for the current
        # estimate. It does not necessarily produce a fresh ultrasonic fix.
        self.snapshot = self.controller.poll()
        snapshot = self.snapshot
        position = snapshot.position
        valid = (
            position is not None
            and len(position) == 2
            and all(math.isfinite(value) for value in position)
            and snapshot.in_bounds
            and not snapshot.dead_zone
            and snapshot.state != "lost"
        )
        if valid:
            x, y = position
            # Match the tracker's millimetre quantization tolerance. Keep an
            # accepted boundary point on the visible canvas edge.
            valid = (
                -0.002 <= x <= self.geometry.width + 0.002
                and self.geometry.near_y - 0.002 <= y <= self.geometry.far_y + 0.002
            )
            if valid:
                position = (
                    min(max(x, 0.0), self.geometry.width),
                    min(max(y, self.geometry.near_y), self.geometry.far_y),
                )
        # Never retain a previous point when the current estimate is missing.
        self._position = position if valid else None
        self.status_text.set(snapshot.status)
        self._update_pause_button()
        self._frame_times.append(time.monotonic())
        self._draw()
        # ~60 display opportunities/second keep the controls responsive.
        # The hardware updates more slowly; the diagnostics report both rates.
        self._after_id = self.root.after(16, self._tick)

    def _draw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        # Replace the previous frame rather than leaving a trail or a stale dot.
        canvas.delete("all")
        self._draw_grid(canvas)
        if self._position is not None:
            x, y = self._screen(self._position)
            radius = 10
            predicted = self.snapshot and self.snapshot.predicted
            # Swarm: hollow = one box only. Pairs: hollow = extrapolated estimate.
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill="" if predicted else self.DOT,
                               outline=self.PREDICTED_DOT if predicted else "",
                               width=2, tags="position")
        snapshot = self.snapshot
        if getattr(self.controller, "paused", False) is True:
            canvas.create_text(canvas.winfo_width() / 2, canvas.winfo_height() / 2,
                               text="PAUSED", fill=self.MUTED, font=self.FONT_BANNER, tags="paused")
        alert = getattr(snapshot, "alert", "") if snapshot else ""
        if isinstance(alert, str) and alert:
            canvas.create_text(canvas.winfo_width() / 2, canvas.winfo_height() * 0.18,
                               text=alert.upper(), fill=self.WARN, font=self.FONT_BANNER, tags="alert")
        if self._diagnostics:
            position = "No current position" if self._position is None else (
                f"x = {self._position[0]:.3f} m    y = {self._position[1]:.3f} m"
            )
            lines = [
                position,
                f"State: {snapshot.state.replace('_', ' ')}" if snapshot else "State: waiting",
                *([f"Box {i}: {status}" for i, status in enumerate(snapshot.node_status)] if snapshot
                  else ["Boxes: waiting"]),
                f"Width: {self.geometry.width:g} m",
                f"Top: {self.geometry.near_y:g} m    Bottom: {self.geometry.far_y:g} m",
            ]
            if snapshot:
                age = f"{snapshot.fix_age_s * 1000:.0f} ms" if math.isfinite(snapshot.fix_age_s) else "no fix"
                elapsed = self._frame_times[-1] - self._frame_times[0] if len(self._frame_times) > 1 else 0
                refresh = (len(self._frame_times) - 1) / elapsed if elapsed > 0 else 0
                lines.extend([
                    f"Fresh position updates: {snapshot.update_hz:.1f} Hz",
                    f"Display refresh: {refresh:.0f} FPS",
                    f"Last measured fix: {age}    Confidence: {snapshot.confidence:.0%}",
                    "Hollow spot: one box only (pairs mode: extrapolated); solid spot: both boxes agree.",
                ])
            if not self.simulate:
                lines.append("Clear the tracking area before pressing C to calibrate.")
            canvas.create_text(14, 14,
                               text="\n".join(lines), anchor="nw", justify="left",
                               fill=self.MUTED, font=self.FONT_DIAGNOSTICS, tags="diagnostics")

    def _draw_grid(self, canvas) -> None:
        """Field frame, 0.25 m grid, metre labels and a centre cross.

        Labels follow the mirrored display: x counts from the player's left edge
        of the screen, y is the distance from the screen wall (near edge at top).
        """
        line = getattr(canvas, "create_line", None)
        rect = getattr(canvas, "create_rectangle", None)
        if line is None or rect is None:
            return
        g = self.geometry
        w, h = canvas.winfo_width(), canvas.winfo_height()
        step = self.GRID_STEP_M
        i = 0
        while i * step <= g.width + 1e-9:
            x_m = i * step
            px, _ = self._screen((x_m, g.near_y))
            major = abs(x_m / 0.5 - round(x_m / 0.5)) < 1e-6
            line(px, 0, px, h, fill=self.GRID_MAJOR if major else self.GRID, tags="grid")
            if 0 < x_m < g.width:
                canvas.create_text(px + 5, h - 6, text=f"{g.width - x_m:.2f} m", anchor="sw",
                                   fill=self.MUTED, font=self.FONT_FOOTER, tags="grid")
            i += 1
        j = 0
        while g.near_y + j * step <= g.far_y + 1e-9:
            y_m = g.near_y + j * step
            _, py = self._screen((0, y_m))
            major = abs(y_m / 0.5 - round(y_m / 0.5)) < 1e-6
            line(0, py, w, py, fill=self.GRID_MAJOR if major else self.GRID, tags="grid")
            canvas.create_text(6, py + 3, text=f"{y_m:.2f} m from wall", anchor="nw",
                               fill=self.MUTED, font=self.FONT_FOOTER, tags="grid")
            j += 1
        canvas.create_text(w - 8, 6, text="boxes above this edge  |  node 0 = your right \u25ba", anchor="ne",
                           fill=self.MUTED, font=self.FONT_FOOTER, tags="grid")
        canvas.create_text(w / 2, 6, text="\u25c4 your left            your right \u25ba", anchor="n",
                           fill=self.MUTED, font=self.FONT_FOOTER, tags="grid")
        rect(1, 1, w - 2, h - 2, outline=self.FRAME, width=2, tags="grid")
        cx, cy = self._screen((g.width / 2, (g.near_y + g.far_y) / 2))
        line(cx - 12, cy, cx + 12, cy, fill=self.FRAME, width=2, tags="grid")
        line(cx, cy - 12, cx, cy + 12, fill=self.FRAME, width=2, tags="grid")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        try:
            self.controller.close()
        finally:
            self.root.destroy()
