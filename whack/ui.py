"""Black-screen visualizer for current dual-ultrasonic position estimates."""

from __future__ import annotations

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
    TEXT = "#D4D4D4"
    MUTED = "#8D8D8D"
    WARNING = "#FF6666"

    def __init__(self, root: tk.Tk, controller, simulate: bool = False) -> None:
        self.root = root
        self.controller = controller
        self.simulate = simulate
        self.geometry = controller.geometry
        self.snapshot = None
        self._closed = False
        self._after_id = None
        self._last_beep = -math.inf
        self._diagnostics = False
        self._fullscreen = False
        self._position = None

        root.title("Dual ultrasonic tracker")
        root.geometry("1000x700")
        root.minsize(600, 400)
        root.configure(bg=self.BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.close())
        root.bind("<F11>", self._toggle_fullscreen)
        root.bind("<KeyPress-d>", self._toggle_diagnostics)
        root.bind("<KeyPress-D>", self._toggle_diagnostics)
        root.bind("<KeyPress-c>", self._calibrate)
        root.bind("<KeyPress-C>", self._calibrate)

        toolbar = tk.Frame(root, bg=self.BACKGROUND, padx=12, pady=6)
        toolbar.pack(fill="x")
        self.status_text = tk.StringVar(value="Waiting for position")
        self.status_label = tk.Label(
            toolbar, textvariable=self.status_text, anchor="w", justify="left",
            bg=self.BACKGROUND, fg=self.TEXT, font=("TkDefaultFont", -13),
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self.diagnostics_button = self._button(toolbar, "Diagnostics (D)", self._toggle_diagnostics)
        if not simulate:
            self._button(toolbar, "Calibrate empty area (C)", self._calibrate)

        self.canvas = tk.Canvas(root, bg=self.BACKGROUND, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._resize)
        if simulate:
            self.canvas.bind("<Motion>", self._mouse)
        footer = "Mouse simulation" if simulate else "Live sensors"
        tk.Label(
            root, text=f"{footer}    D: diagnostics    F11: fullscreen    Esc: close",
            bg=self.BACKGROUND, fg=self.MUTED, font=("TkDefaultFont", -11), pady=5,
        ).pack(fill="x")
        self._tick()

    def _button(self, parent, label, command):
        button = tk.Button(
            parent, text=label, command=command, bg="#202020", fg=self.TEXT,
            activebackground="#333333", activeforeground="#FFFFFF",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=self.BACKGROUND, highlightcolor=self.DOT,
            padx=9, pady=5, font=("TkDefaultFont", -12), cursor="hand2",
        )
        button.pack(side="right", padx=(8, 0))
        return button

    def _resize(self, event=None) -> None:
        # Let status wrap rather than push controls beyond the window edge.
        self.status_label.configure(wraplength=max(140, self.root.winfo_width() - 400))
        self._draw()

    def _calibrate(self, event=None):
        if not self.simulate:
            self.controller.start_calibration()
        return "break"

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
        x = event.x / width * self.geometry.width
        y = self.geometry.near_y + event.y / height * (self.geometry.far_y - self.geometry.near_y)
        self.controller.set_simulated_position(x, y)

    def _screen(self, position) -> tuple[float, float]:
        x, y = position
        return (
            x / self.geometry.width * self.canvas.winfo_width(),
            (y - self.geometry.near_y) / (self.geometry.far_y - self.geometry.near_y)
            * self.canvas.winfo_height(),
        )

    def _tick(self) -> None:
        if self._closed:
            return
        self.snapshot = self.controller.poll()
        snapshot = self.snapshot
        position = snapshot.position
        valid = (
            position is not None
            and len(position) == 2
            and all(math.isfinite(value) for value in position)
            and snapshot.in_bounds
            and not snapshot.dead_zone
        )
        if valid:
            x, y = position
            # Match the tracker's millimetre quantization tolerance. Keep an
            # accepted boundary point on the visible canvas edge.
            valid = (
                -0.002 <= x <= self.geometry.width + 0.002
                and self.geometry.near_y - 1e-6 <= y <= self.geometry.far_y + 0.002
            )
            if valid:
                position = (
                    min(max(x, 0.0), self.geometry.width),
                    min(max(y, self.geometry.near_y), self.geometry.far_y),
                )
        # Never retain a previous point when the current estimate is missing.
        self._position = position if valid else None
        self.status_text.set(snapshot.status)
        self.status_label.configure(fg=self.WARNING if snapshot.dead_zone else self.TEXT)
        now = time.monotonic()
        if snapshot.dead_zone and now - self._last_beep >= 1.0:
            self.root.bell()
            self._last_beep = now
        self._draw()
        self._after_id = self.root.after(16, self._tick)

    def _draw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        if self._position is not None:
            x, y = self._screen(self._position)
            radius = 10
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill=self.DOT, outline="", tags="position")
        snapshot = self.snapshot
        if snapshot and snapshot.dead_zone:
            canvas.create_text(
                canvas.winfo_width() / 2, 36, text="Step back from the sensors",
                fill=self.WARNING, font=("TkDefaultFont", -22, "bold"), tags="warning",
            )
        if self._diagnostics:
            position = "No current position" if self._position is None else (
                f"x = {self._position[0]:.3f} m    y = {self._position[1]:.3f} m"
            )
            lines = [
                position,
                f"Left sensor: {snapshot.node_status[0]}" if snapshot else "Left sensor: waiting",
                f"Right sensor: {snapshot.node_status[1]}" if snapshot else "Right sensor: waiting",
                f"Width: {self.geometry.width:g} m",
                f"Top: {self.geometry.near_y:g} m    Bottom: {self.geometry.far_y:g} m",
            ]
            if not self.simulate:
                lines.append("Clear the tracking area before pressing C to calibrate.")
            canvas.create_text(14, 76 if snapshot and snapshot.dead_zone else 14,
                               text="\n".join(lines), anchor="nw", justify="left",
                               fill=self.MUTED, font=("TkDefaultFont", -13), tags="diagnostics")

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
