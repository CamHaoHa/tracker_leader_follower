"""Laptop state machine diagrams (SwarmController) as 16:9 SVGs for PowerPoint."""
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
FONT = "Arial, Helvetica, sans-serif"
INK, MUTED, LINE = "#1f2937", "#4b5563", "#374151"
STYLE = {  # fill, stroke
    "setup": ("#f3f4f6", "#6b7280"),
    "cal": ("#fef3c7", "#d97706"),
    "find": ("#dbeafe", "#2563eb"),
    "track": ("#dcfce7", "#16a34a"),
    "pause": ("#e5e7eb", "#374151"),
    "jitter": ("#fce7f3", "#db2777"),
    "search": ("#ede9fe", "#7c3aed"),
}


def head(title, subtitle):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" font-family="{FONT}">',
            '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>',
            '<rect width="1600" height="900" fill="#ffffff"/>',
            f'<text x="60" y="62" font-size="34" font-weight="bold" fill="{INK}">{title}</text>',
            f'<text x="60" y="96" font-size="18" fill="{MUTED}">{subtitle}</text>']


def state(x, y, w, h, kind, name, lines):
    fill, stroke = STYLE[kind]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="{stroke}" stroke-width="3"/>',
           f'<text x="{x+w/2}" y="{y+34}" font-size="24" font-weight="bold" fill="{INK}" text-anchor="middle">{name}</text>']
    for i, t in enumerate(lines):
        out.append(f'<text x="{x+w/2}" y="{y+62+i*22}" font-size="16" fill="{MUTED}" text-anchor="middle">{t}</text>')
    return out


def arrow(d, dashed=False):
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    return [f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2.5" marker-end="url(#a)"{dash}/>']


def label(x, y, lines, anchor="middle", size=16, bold_first=True):
    out = []
    for i, t in enumerate(lines):
        weight = ' font-weight="bold"' if bold_first and i == 0 else ""
        out.append(f'<text x="{x}" y="{y+i*20}" font-size="{size}" fill="{INK}" text-anchor="{anchor}"{weight}>{t}</text>')
    return out


def note(x, y, w, h, lines):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fffbeb" stroke="#d97706" stroke-width="1.5" stroke-dasharray="6 4"/>']
    for i, t in enumerate(lines):
        weight = ' font-weight="bold"' if i == 0 else ""
        out.append(f'<text x="{x+16}" y="{y+28+i*22}" font-size="16" fill="{INK}"{weight}>{t}</text>')
    return out


def controller():
    s = head("Laptop state machine — tracker controller",
             "whack/swarm.py · SwarmController.poll() runs every UI frame; one ping in the air at a time")
    # start
    s += ['<circle cx="70" cy="200" r="13" fill="#1f2937"/>'] + arrow("M83,200 L118,200")
    s += state(120, 150, 300, 100, "setup", "Waiting for boxes", ["&lt; 2 boxes online", "listen UDP 4210 beacons"])
    s += state(120, 400, 300, 100, "setup", "Needs calibration", ["no empty-room map", "on disk"])
    s += state(120, 650, 300, 120, "cal", "Calibrating", ["area kept empty", "every sweep bearing × 3 pings", "median range = wall echo"])
    s += state(700, 145, 320, 120, "find", "Find", ["no player fix", "boxes sweep / search arcs", "look for a reliable echo"])
    s += state(1220, 145, 320, 120, "track", "Track", ["player (x, y) estimate", "fuse ranges, aim all boxes", "alerts + buzzer active"])
    s += state(700, 650, 320, 120, "pause", "Paused", ["no pings sent", "servos parked at 90°", "buzzer off"])

    # setup column
    s += arrow("M420,200 L698,200") + label(559, 188, ["≥ 2 online, map loaded"])
    s += arrow("M270,250 L270,398") + label(285, 320, ["≥ 2 online,", "no map"], anchor="start")
    s += arrow("M270,500 L270,648") + label(285, 570, ["Calibrate (C)", "area empty"], anchor="start")
    # calibrating -> find
    s += arrow("M420,662 L735,267") + label(600, 455, ["All bearings done", "map saved"], anchor="start")
    # calibrating <-> paused
    s += arrow("M420,688 L698,688") + label(559, 678, ["Pause → cancelled, map cleared"], bold_first=False, size=15)
    s += arrow("M698,725 L422,725") + label(559, 715, ["Calibrate (C)"], bold_first=False, size=15)
    s += arrow("M420,758 L698,758") + label(559, 788, ["Map saved, game start (idle)"], bold_first=False, size=15)
    # find <-> track
    s += arrow("M1020,185 L1218,185") + label(1120, 140, ["Reliable echo", "accepted"])
    s += arrow("M1220,240 L1022,240") + label(1120, 268, ["No fix 0.5 s", "→ search arcs"])
    # track self loop
    s += arrow("M1340,145 C1340,95 1420,95 1420,143") + label(1325, 112, ["New fix: fuse + re-aim"], anchor="end", bold_first=False)
    # find <-> paused
    s += arrow("M835,265 L835,648") + label(820, 440, ["Pause /", "Reset"], anchor="end")
    s += arrow("M885,648 L885,267") + label(900, 440, ["Search (Space)", "map present"], anchor="start")
    # track -> paused
    s += arrow("M1300,265 L1300,700 L1022,700") + label(1290, 560, ["Pause / Reset"], anchor="end")
    # notes
    s += note(1330, 330, 240, 205, ["Reliable echo =", "status OK", "≥ 10 cm, ≤ 1.7 m", "not the wall map", "same range again", "within 1.5 s",
                                     "(±16° bearing)", "and not outvoted"][:8])
    s += note(1330, 600, 240, 150, ["Alerts (not states)", "too close &lt; 10 cm", "dead zone, outside field", "two players → banner,", "buzzer while near wall"])
    s += note(120, 800, 560, 70, ["Any running state → Waiting for boxes", "when &lt; 2 boxes online: all pings cancelled"])
    s.append("</svg>")
    return "\n".join(s)


def box_modes():
    s = head("Laptop state machine — per-box servo mode",
             "whack/swarm.py · each box runs this independently; the laptop picks its next bearing every poll")
    s += ['<circle cx="70" cy="300" r="13" fill="#1f2937"/>'] + arrow("M83,300 L118,300")
    s += state(120, 230, 320, 140, "find", "Sweep", ["5° steps across own arc", "bounce at arc ends", "1 ping per bearing", "candidate → repeat once"])
    s += state(640, 230, 320, 140, "track", "Aimed", ["point at shared estimate", "(any box's fix)", "re-aim every ping", "lead 80 ms"])
    s += state(1180, 230, 320, 140, "jitter", "Jitter", ["dither 0, +8°, −8°", "round aimed bearing", "for up to 1.0 s"])
    s += state(640, 620, 320, 140, "search", "Search", ["after full loss (0.5 s)", "start at game's expect()", "15° steps, middle first", "out to both arc ends"])

    # sweep <-> aimed
    s += arrow("M440,275 L638,275") + label(539, 230, ["Fix accepted", "(this or other box)"])
    s += arrow("M640,330 L442,330") + label(539, 360, ["Estimate stale", "&gt; 0.5 s"])
    # aimed <-> jitter
    s += arrow("M960,275 L1178,275") + label(1069, 255, ["Aimed ping missed"])
    s += arrow("M1180,330 L962,330") + label(1069, 360, ["Fix accepted"])
    # aimed self
    s += arrow("M760,230 C760,170 840,170 840,228") + label(860, 190, ["Hit: re-aim at new fix"], anchor="start", bold_first=False)
    # jitter -> sweep (over the top)
    s += arrow("M1340,230 L1340,150 L280,150 L280,228") + label(810, 138, ["1.0 s with no hit → back to Sweep, 2 s cooldown before re-aim (unless estimate moved ≥ 0.3 m)"], bold_first=False)
    # loss -> search
    s += arrow("M280,370 L280,690 L638,690") + label(295, 520, ["Player lost", "no fix 0.5 s", "(all boxes)"], anchor="start")
    s += arrow("M1340,370 L1340,690 L962,690") + label(1355, 520, ["Player lost", "no fix 0.5 s"], anchor="start")
    s += arrow("M800,370 L800,618", dashed=True) + label(785, 500, ["Player lost"], anchor="end", bold_first=False)
    # search -> sweep / aimed
    s += arrow("M640,740 L200,740 L200,372") + label(420, 770, ["Both arc ends done → Sweep"], bold_first=False)
    s += arrow("M880,618 L880,372") + label(895, 450, ["Fix accepted"], anchor="start")
    s += note(1060, 790, 500, 80, ["Calibrating overrides all modes:", "fixed plan, every bearing × 3 pings"])
    s.append("</svg>")
    return "\n".join(s)


OUT.mkdir(parents=True, exist_ok=True)
(OUT / "laptop-controller-states.svg").write_text(controller())
(OUT / "laptop-box-modes.svg").write_text(box_modes())
