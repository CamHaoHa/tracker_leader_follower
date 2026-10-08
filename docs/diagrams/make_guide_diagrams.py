"""Slides for the Tracker Algorithm Guide (16:9 SVGs, 1600x900) for PowerPoint.

Run: python3 make_guide_diagrams.py <out_dir>; render PNGs with headless Chromium.
"""
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
FONT = "Arial, Helvetica, sans-serif"
MONO = "Consolas, 'Courier New', monospace"
INK, MUTED, LINE, RULE = "#16202a", "#5b6a74", "#374151", "#d3dbe1"
TEAL, TEAL_SOFT, TEAL_LINE = "#0891b2", "#dcf0f3", "#0e8a9b"
ORANGE, ORANGE_SOFT = "#c2410c", "#f8e7dc"
GREEN, GREEN_SOFT = "#2d7a3e", "#e1f0e4"
GREY_SOFT, AMBER_SOFT, AMBER = "#eef1f4", "#fef3c7", "#d97706"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=16, weight="normal", fill=INK, anchor="start", family=FONT):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" font-family="{family}">{esc(s)}</text>')


def head(title, subtitle):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" font-family="{FONT}">',
            '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>',
            '<rect width="1600" height="900" fill="#ffffff"/>',
            t(60, 62, title, 34, "bold"), t(60, 96, subtitle, 18, fill=MUTED)]


def rect(x, y, w, h, fill, stroke, rx=14, sw=2.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def arrow(d, dashed=False, color=LINE):
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#a)"{dash}/>'


def card(x, y, w, h, fill, stroke, title, lines, kicker=None, size=16, center=True, title_size=21):
    out = [rect(x, y, w, h, fill, stroke)]
    cx, anchor = (x + w/2, "middle") if center else (x + 18, "start")
    yy = y + 30
    if kicker:
        out.append(t(cx, yy, kicker, 14, "bold", TEAL_LINE, anchor, MONO)); yy += 28
    out.append(t(cx, yy, title, title_size, "bold", INK, anchor)); yy += 28
    for line in lines:
        out.append(t(cx, yy, line, size, fill=MUTED, anchor=anchor)); yy += size + 6
    return out


def note(x, y, w, h, title, lines, size=16):
    out = [rect(x, y, w, h, "#fffbeb", AMBER, rx=8, sw=1.5, dash="6 4"), t(x+16, y+28, title, size, "bold")]
    for i, line in enumerate(lines):
        out.append(t(x+16, y+52+i*(size+6), line, size))
    return out


def save(name, parts):
    (OUT / f"{name}.svg").write_text("\n".join(parts + ["</svg>"]))


# 1 ---------------------------------------------------------------- pipeline
def pipeline():
    s = head("Tracker pipeline — one loop of the swarm tracker",
             "whack/swarm.py · runs on the laptop every poll; each box gets a new bearing as soon as its last ping is done")
    steps = [
        ("1 · AIM", "Choose bearing", ["hold · aimed · jitter", "sweep 5° · search 15°", "per box, own arc"]),
        ("2 · PING", "One box at a time", ["AIM → READY →", "FIRE → RANGE", "65 ms acoustic guard"]),
        ("3 · CLASSIFY", "Is it the player?", ["range 0.10–1.7 m", "not the room map", "confirm ping"]),
        ("4 · FUSE", "Combine boxes", ["Gauss-Newton on", "range circles", "residual ≤ 0.30 m"]),
        ("5 · FILTER", "Gate + smooth", ["jump ≤ 3 m/s·dt + 0.3 m", "exponential, τ 0.12 s", "no velocity term"]),
        ("6 · ACT", "Steer and warn", ["other boxes aim", "at the fix", "alerts + buzzer"]),
    ]
    w, gap, x0, y = 220, 36, 50, 190
    for i, (k, title, lines) in enumerate(steps):
        x = x0 + i*(w + gap)
        fill, stroke = (GREEN_SOFT, GREEN) if i == 5 else (TEAL_SOFT, TEAL_LINE)
        s += card(x, y, w, 175, fill, stroke, title, lines, kicker=k)
        if i < 5:
            s.append(arrow(f"M{x+w+2},{y+88} L{x+w+gap-2},{y+88}"))
    last = x0 + 5*(w + gap) + w/2
    first = x0 + w/2
    s.append(arrow(f"M{last},{y+175} L{last},{y+250} L{first},{y+250} L{first},{y+177}"))
    s.append(t((first+last)/2, y+240, "next poll: every box that finished its ping gets a new bearing", 17, anchor="middle"))
    # constants strip
    consts = [("5° / 15°", "sweep / search step"), ("0.30 s", "per bearing, 3 boxes"), ("1.7 m", "reliable range"),
              ("0.30 m", "fusion residual"), ("0.12 s", "smoothing τ"), ("0.5 s", "no fix → lost")]
    s.append(t(60, 560, "Key constants", 22, "bold"))
    for i, (v, l) in enumerate(consts):
        x = 50 + i*256
        s.append(rect(x, 580, 220, 120, "#ffffff", RULE, rx=10, sw=1.5))
        s.append(t(x+110, 635, v, 34, "bold", INK, "middle"))
        s.append(t(x+110, 670, l, 16, fill=MUTED, anchor="middle"))
    s += note(50, 740, 1500, 110, "Laptop owns every decision",
              ["Boxes only move the servo and ping when told (firmware has no tracking logic).",
               "Cleaning happens on the laptop, where readings from all boxes can be compared."])
    save("guide-1-pipeline", s)


# 2 ---------------------------------------------------------------- protocol
def protocol():
    s = head("Ping protocol and the acoustic slot",
             "whack/protocol.py · firmware/src/main.cpp · UDP over a phone hotspot, WM2 messages")
    lx, bx = 200, 690
    for x, name, sub in ((lx, "Laptop", "UDP 4210"), (bx, "Box (ESP32)", "UDP 4211")):
        s.append(rect(x-110, 130, 220, 62, GREY_SOFT, LINE, rx=10))
        s.append(t(x, 160, name, 20, "bold", anchor="middle"))
        s.append(t(x, 182, sub, 14, fill=MUTED, anchor="middle"))
        s.append(f'<line x1="{x}" y1="192" x2="{x}" y2="640" stroke="{LINE}" stroke-width="1.5" stroke-dasharray="5 5"/>')
    msgs = [(245, "→", "AIM  seq, bearing"), (395, "←", "READY  seq, lease 1000 ms"),
            (470, "→", "FIRE  seq"), (600, "←", "RANGE  mm, OK / TIMEOUT / INVALID, age")]
    for y, d, label in msgs:
        a, b = (lx+2, bx-2) if d == "→" else (bx-2, lx+2)
        s.append(arrow(f"M{a},{y} L{b},{y}"))
        s.append(t((lx+bx)/2, y-10, label, 17, "bold", anchor="middle", family=MONO))
    # box activity bars and notes
    s.append(rect(bx-8, 250, 16, 140, AMBER_SOFT, AMBER, rx=3, sw=1.5))
    s.append(rect(bx-8, 475, 16, 120, TEAL_SOFT, TEAL_LINE, rx=3, sw=1.5))
    for i, line in enumerate(["servo ramp ≥ 150 °/s", "settle 60 ms + ramp", "at most 700 ms",
                              "bearing outside travel", "→ refused at once"]):
        s.append(t(bx+22, 285+i*21, line, 15, fill=MUTED))
    for i, line in enumerate(["TRIG 10 µs", "pulseIn ≤ 25 ms (≈ 4.3 m)", "d = t·343 / 2",
                              "20–4000 mm else INVALID"]):
        s.append(t(bx+22, 505+i*21, line, 15, fill=MUTED))
    s += note(60, 672, 840, 190, "Every retry is safe over lossy UDP",
              ["AIM resent every 0.3 s until READY arrives",
               "duplicate FIRE → cached RANGE replayed, never a second ping",
               "FIRE outside the lease or < 65 ms after the last ping → INVALID",
               "32-bit sequence numbers, only newer accepted (wrap-safe)",
               "before retries: calibration aborted 3 times in 20 steps"])
    # slot schedule
    X0, W = 1040, 500       # 0.30 s across 500 px
    px = W/0.30
    s.append(t(960, 160, "One acoustic slot at a time", 22, "bold"))
    s.append(t(960, 186, "servos move together, pings never overlap", 16, fill=MUTED))
    for i in range(3):
        y = 230 + i*62
        s.append(t(960, y+26, f"box {i}", 17, "bold", family=MONO))
        s.append(rect(X0, y, W, 38, GREY_SOFT, "none", rx=4, sw=0))
        start = X0 + i*0.10*px
        s.append(rect(start, y, 0.025*px, 38, TEAL, "none", rx=4, sw=0))
        s.append(rect(start+0.025*px+2, y, 0.065*px-2, 38, "#b8c4cc", "none", rx=4, sw=0))
    for k in range(4):
        x = X0 + k*0.10*px
        s.append(f'<line x1="{x}" y1="414" x2="{x}" y2="424" stroke="{MUTED}" stroke-width="1.5"/>')
        s.append(t(x, 444, f"{k*0.1:.1f} s", 15, fill=MUTED, anchor="middle"))
    s.append(f'<line x1="{X0}" y1="414" x2="{X0+W}" y2="414" stroke="{MUTED}" stroke-width="1.5"/>')
    s.append(rect(960, 470, 22, 16, TEAL, "none", rx=3, sw=0)); s.append(t(992, 484, "ping + echo ≤ 25 ms", 16))
    s.append(rect(1200, 470, 22, 16, "#b8c4cc", "none", rx=3, sw=0)); s.append(t(1232, 484, "65 ms guard (+10 ms poll)", 16))
    s.append(rect(960, 515, 590, 120, "#e9eef2", "none", rx=8, sw=0))
    s.append(t(980, 552, "T_slot = 25 + 65 + 10 ms ≈ 0.10 s", 19, family=MONO))
    s.append(t(980, 584, "T_step = 3 boxes × 0.10 s = 0.30 s", 19, family=MONO))
    s.append(t(980, 614, "lost reply: wait lease + 25 ms + 65 ms", 16, fill=MUTED, family=MONO))
    s += note(960, 672, 590, 190, "Why one slot",
              ["Two HC-SR04s pinging together hear each",
               "other's echoes and report a false range.",
               "Cost: step rate is set by the schedule, not",
               "the servo, so faster recovery needs bigger",
               "search steps, not faster servos."])
    save("guide-2-protocol", s)


# 3 ---------------------------------------------------------------- classify
def classify():
    s = head("Classifying a reading — is it the player?",
             "whack/swarm.py:504-528 · checks run in this order on every RANGE reply")
    s += card(40, 245, 160, 100, GREY_SOFT, LINE, "RANGE", ["reply from", "one box"], size=15)
    checks = ["Status OK?", "d ≥ 0.10 m?", "Unlike the room map?", "d ≤ 1.7 m?", "Repeats last echo?"]
    subs = ["not timeout / invalid", "player not on the box", "±10°, ±0.15 m band", "reliable range", "16°, 0.10 m, 1.5 s"]
    outs = [("Miss", ["no echo / invalid", "last echo kept"], GREY_SOFT, LINE),
            ("Too close", ["alert input", "0.3 s → banner, buzzer"], AMBER_SOFT, AMBER),
            ("Miss: the room", ["wall, table, floor", "from calibration"], GREY_SOFT, LINE),
            ("Hint only", ["too far to trust", "treated as a miss"], GREY_SOFT, LINE),
            ("RELIABLE", ["used for a fix", "→ fusion"], GREEN_SOFT, GREEN)]
    w, gap, x0 = 215, 45, 245
    for i, (c, sub) in enumerate(zip(checks, subs)):
        x = x0 + i*(w + gap)
        s.append(rect(x, 245, w, 100, TEAL_SOFT, TEAL_LINE))
        s.append(t(x+w/2, 285, c, 19, "bold", anchor="middle"))
        s.append(t(x+w/2, 312, sub, 15, fill=MUTED, anchor="middle"))
        prev = 200 if i == 0 else x - gap
        s.append(arrow(f"M{prev+2},{305} L{x-2},{305}"))
        if i:
            s.append(t(x - gap/2, 278, "yes", 15, "bold", GREEN, "middle"))
        title, lines, fill, stroke = outs[i]
        s.append(arrow(f"M{x+w/2},347 L{x+w/2},448"))
        s.append(t(x+w/2+10, 405, "yes" if i == 4 else "no", 15, "bold", GREEN if i == 4 else ORANGE))
        s += card(x, 450, w, 120, fill, stroke, title, lines, size=15)
    # candidate path
    x5 = x0 + 4*(w + gap)
    s.append(arrow(f"M{x5+w+2},300 L{x5+w+60},300 L{x5+w+60},700 L{x5+w+2},700"))
    s.append(t(x5+w+48, 520, "no", 15, "bold", ORANGE, "end"))
    s += card(x5, 640, w, 120, AMBER_SOFT, AMBER, "Candidate", ["ping the same", "bearing once more"], size=15)
    s.append(arrow(f"M{x5-2},700 L120,700 L120,347"))
    s.append(t(640, 690, "repeat at the same bearing: costs one ping (0.30 s)", 17, anchor="middle"))
    s += note(40, 785, 1520, 85, "Why the confirm ping",
              ["A single echo can be a reflection or noise; asking for the same range twice removes most one-off ghosts. "
               "Match widened 5° → 16° (aee8ef0) so jitter steps no longer break it."], size=15)
    save("guide-3-classify", s)


# 4 ---------------------------------------------------------------- fusion + filter
def fusion():
    s = head("Fusion and filtering — from readings to one spot",
             "whack/swarm.py:118-185, 570-622 · least squares over range circles, then a jump gate and smoothing")
    boxes = [("Fresh readings", ["latest reliable per box", "≤ 0.6 s old"]),
             ("Gauss-Newton", ["min Σ (|P − Sᵢ| − rᵢ)²", "converges in 2–3 steps"]),
             ("Agree?", ["worst residual ≤ 0.30 m", "inside every beam"]),
             ("Jump gate", ["≤ 3 m/s · dt + 0.30 m", "else “Position jumped”"]),
             ("Smooth → spot", ["α weight on the new fix", "boxes re-aim at it"])]
    w, gap, x0 = 264, 45, 50
    for i, (title, lines) in enumerate(boxes):
        x = x0 + i*(w + gap)
        fill, stroke = (GREEN_SOFT, GREEN) if i == 4 else (TEAL_SOFT, TEAL_LINE)
        s += card(x, 130, w, 120, fill, stroke, title, lines, size=15)
        if i < 4:
            s.append(arrow(f"M{x+w+2},195 L{x+w+gap-2},195"))
    s.append(t(x0 + 2*(w+gap) + w + gap/2, 175, "yes", 15, "bold", GREEN, "middle"))
    # panel A: Gauss-Newton
    s.append(rect(50, 310, 520, 560, "#ffffff", RULE, rx=10, sw=1.5))
    s.append(t(70, 345, "Gauss-Newton step", 21, "bold"))
    for i, line in enumerate(["residual  eᵢ = |P − Sᵢ| − rᵢ", "Jacobian  Jᵢ = (P − Sᵢ) / |P − Sᵢ|",
                              "solve     (JᵀJ) Δ = Jᵀe   (2×2)", "update    P ← P − Δ",
                              "stop      |Δx|+|Δy| < 0.1 mm, ≤ 6 its"]):
        s.append(t(70, 382 + i*27, line, 16, family=MONO))
    s.append(t(70, 545, "Worked example: truth (0.50, 1.30) m, noise +2/−1/+3 cm", 15, "bold"))
    rows = [("", "x (m)", "y (m)", "|Δ|"), ("start", "0.5045", "1.3256", "—"), ("iter 1", "0.4935", "1.3121", "0.0244"),
            ("iter 2", "0.4939", "1.3120", "0.0004"), ("iter 3", "0.4939", "1.3120", "stop")]
    for r, row in enumerate(rows):
        y = 580 + r*32
        if r:
            s.append(f'<line x1="70" y1="{y-22}" x2="550" y2="{y-22}" stroke="{RULE}"/>')
        for c, val in enumerate(row):
            s.append(t(70 + c*125, y, val, 16, "bold" if r == 0 else "normal", MUTED if r == 0 else INK,
                       family=FONT if c == 0 or r == 0 else MONO))
    s.append(t(70, 760, "Final error 1.4 cm; worst residual 0.023 m,", 16))
    s.append(t(70, 784, "far inside the 0.30 m agreement limit.", 16))
    s.append(t(70, 820, "One box only: no solve, polar point", 16, fill=MUTED))
    s.append(t(70, 844, "along the bearing at d + 0.18 m body radius.", 16, fill=MUTED))
    # panel B: disagreement
    s.append(arrow(f"M{x0+2*(w+gap)+w/2},252 L{x0+2*(w+gap)+w/2},308"))
    s.append(t(x0+2*(w+gap)+w/2+12, 284, "no", 15, "bold", ORANGE))
    s.append(rect(600, 310, 440, 560, ORANGE_SOFT, ORANGE, rx=10, sw=1.5))
    s.append(t(620, 345, "When boxes disagree", 21, "bold"))
    items = [("1  Largest agreeing group", ["keep the newest reading with", "the most others that agree"]),
             ("2  Outvote", ["nobody agrees, but two boxes", "still holding the player agree", "→ newest reading = a miss"]),
             ("3  Two players alert", ["readings ≥ 0.6 m apart keep", "disagreeing for 1 s"])]
    y = 390
    for title, lines in items:
        s.append(t(620, y, title, 18, "bold")); y += 26
        for line in lines:
            s.append(t(646, y, line, 16, fill=MUTED)); y += 22
        y += 22
    s.append(t(620, 760, "Why: two circles always cross somewhere;", 16, "bold"))
    s.append(t(620, 784, "a crossing no beam faces is a ghost.", 16))
    s.append(t(620, 808, "Outvoting stops one wall echo dragging", 16))
    s.append(t(620, 832, "a well-held spot away.", 16))
    # panel C: alpha chart
    s.append(rect(1070, 310, 480, 560, "#ffffff", RULE, rx=10, sw=1.5))
    s.append(t(1090, 345, "Smoothing weight α", 21, "bold"))
    s.append(t(1090, 372, "α = clamp(1 − e^(−dt/0.12 s), 0.35, 0.90)", 15, family=MONO))
    L, R, T, B = 1135, 1520, 410, 740
    X = lambda dt: L + dt/0.5*(R-L)
    Y = lambda a: B - a*(B-T)
    for a in (0, .25, .5, .75, 1):
        s.append(f'<line x1="{L}" y1="{Y(a)}" x2="{R}" y2="{Y(a)}" stroke="{RULE}" stroke-width="1"/>')
        s.append(t(L-10, Y(a)+5, f"{a:.2f}", 14, fill=MUTED, anchor="end"))
    for dt in (0, .1, .2, .3, .4, .5):
        s.append(t(X(dt), B+22, f"{dt:.1f}", 14, fill=MUTED, anchor="middle"))
    s.append(t((L+R)/2, B+46, "time since last fix, dt (s)", 15, fill=MUTED, anchor="middle"))
    raw = lambda dt: 1 - math.exp(-dt/0.12)
    clamp = lambda dt: min(.9, max(.35, raw(dt)))
    def path(f):
        return " ".join(f"{'M' if i == 0 else 'L'}{X(.5*i/200):.1f},{Y(f(.5*i/200)):.1f}" for i in range(201))
    s.append(f'<path d="{path(raw)}" fill="none" stroke="#9aa5ad" stroke-width="2" stroke-dasharray="3 5"/>')
    s.append(f'<path d="{path(clamp)}" fill="none" stroke="{TEAL}" stroke-width="3"/>')
    s.append(f'<path d="{path(lambda d: clamp(d)/2)}" fill="none" stroke="{ORANGE}" stroke-width="3" stroke-dasharray="9 5"/>')
    for v, c in ((clamp(.15), TEAL), (clamp(.15)/2, ORANGE)):
        s.append(f'<circle cx="{X(.15)}" cy="{Y(v)}" r="6" fill="{c}" stroke="#ffffff" stroke-width="2"/>')
    s.append(t(X(.15)+12, Y(clamp(.15))+22, "0.15 s → 0.71", 15, "bold"))
    s.append(t(X(.15)+12, Y(clamp(.15)/2)+22, "0.15 s → 0.36", 15, "bold"))
    s.append(t(X(.36), Y(.9)+26, "2+ boxes", 15, "bold"))
    s.append(t(X(.36), Y(.45)-10, "1 box (half)", 15, "bold"))
    s.append(t(X(.05)+6, Y(.95)+4, "unclamped", 14, fill=MUTED))
    s.append(t(1090, 830, "No velocity term: removing prediction raised", 15, fill=MUTED))
    s.append(t(1090, 852, "two-box fixes from 39 % to 68 %.", 15, fill=MUTED))
    save("guide-4-fusion", s)


# 5 ---------------------------------------------------------------- timeline
def timeline():
    s = head("How we got here — every change driven by a measurement",
             "12 Sep → 5 Oct 2026 · teal = kept in main · orange = tried and rejected")
    events = [
        ("12–15 Sep", "Baseline design", ["1 servo + 1 HC-SR04", "per ESP32, laptop", "decides; WM2 protocol"], False),
        ("22 Sep · 2df7385", "V1 works on bench", ["calibration 0/3 →", "111/111 pairs", "dot 75 %, 4.9 Hz"], False),
        ("23 Sep · 1c9836b", "V1 fails, swarm in", ["1.5 m field: dot 14 %,", "17.6 losses/min", "swarm same day: 92 %"], False),
        ("23 Sep · 84fc859", "Prediction removed", ["two-box fixes", "39 % → 68 %", "jitter 7.3 → 2.1 cm"], False),
        ("29 Sep · 835964b", "Third box, middle", ["far corners 1.86 m", "> 1.7 m range; aims", "clamped (9–15 % refused)"], False),
        ("30 Sep · branch", "Lock-scan on laptop", ["4–5× slower over", "Wi-Fi: ~300 ms vs", "65 ms per ping"], True),
        ("2 Oct · 7d7c9d1", "Search + mole hint", ["jump recovery", "3.4–9.1 → 1.3–1.5 s", "field 0.51 → 0.21 s"], False),
        ("5 Oct · aee8ef0", "Ghost-echo hold", ["standing player", "12.4 → 1.2 losses/min", "on hole 87 → 99 %"], False),
        ("5 Oct · branch", "Consensus fusion", ["same result, more", "code; deadband 0.62", "→ 1.15 s column move"], True),
    ]
    ax_y, x_first, x_last = 470, 170, 1430
    step = (x_last - x_first) / (len(events) - 1)
    s.append(f'<line x1="{x_first-80}" y1="{ax_y}" x2="{x_last+90}" y2="{ax_y}" stroke="{LINE}" stroke-width="3"/>')
    w, h = 270, 150
    for i, (date, title, lines, rejected) in enumerate(events):
        cx = x_first + i*step
        above = i % 2 == 0
        y = 170 if above else 620
        fill, stroke = (ORANGE_SOFT, ORANGE) if rejected else (TEAL_SOFT, TEAL_LINE)
        s.append(f'<line x1="{cx}" y1="{y+h if above else y}" x2="{cx}" y2="{ax_y}" stroke="{stroke}" stroke-width="2"/>')
        s.append(f'<circle cx="{cx}" cy="{ax_y}" r="10" fill="#ffffff" stroke="{stroke}" stroke-width="4"/>')
        s.append(rect(cx - w/2, y, w, h, fill, stroke, rx=10, sw=2))
        s.append(t(cx - w/2 + 14, y + 26, date, 14, "bold", ORANGE if rejected else TEAL_LINE, family=MONO))
        s.append(t(cx - w/2 + 14, y + 52, title + (" ✗" if rejected else ""), 18, "bold"))
        for k, line in enumerate(lines):
            s.append(t(cx - w/2 + 14, y + 78 + k*22, line, 16, fill=INK))
    s.append(t(60, 870, "Results from 2 Oct on are simulator results, except the 3 Oct field reacquire comparison (p = 0.016).",
               15, fill=MUTED))
    save("guide-5-timeline", s)


# 6 ---------------------------------------------------------------- results
def results():
    s = head("Each change, measured — before vs after",
             "each panel has its own scale · orange = before, teal = after")
    panels = [("V1 → swarm", "dot shown (%)", 14, 92, "%", "↑ better", "field, 23 Sep", ("V1 pairs", "swarm")),
              ("Prediction removed", "two-box fixes (%)", 39, 68, "%", "↑ better", "field, 23 Sep", ("with", "without")),
              ("Search after loss", "jump recovery (s)", 3.64, 1.44, " s", "↓ better", "simulator, 2 Oct", ("sweep", "search")),
              ("Search + mole hint", "median reacquire (s)", 0.51, 0.21, " s", "↓ better", "field, p = 0.016", ("V1", "V2")),
              ("Ghost-echo hold", "losses per minute", 12.4, 1.2, "", "↓ better", "simulator, 5 Oct", ("before", "after"))]
    pw, gap, x0 = 280, 25, 50
    base, top = 720, 300
    for i, (title, metric, before, after, unit, better, src, names) in enumerate(panels):
        x = x0 + i*(pw + gap)
        s.append(rect(x, 140, pw, 740, "#ffffff", RULE, rx=10, sw=1.5))
        s.append(t(x+pw/2, 180, title, 20, "bold", anchor="middle"))
        s.append(t(x+pw/2, 206, metric, 16, fill=MUTED, anchor="middle"))
        s.append(t(x+pw/2, 232, better, 15, "bold", GREEN, "middle"))
        vmax = max(before, after) * 1.15
        for j, (v, c, name) in enumerate(((before, ORANGE, names[0]), (after, TEAL, names[1]))):
            bx = x + 50 + j*100
            hgt = (v / vmax) * (base - top)
            yb = base - hgt
            s.append(f'<path d="M{bx},{base} L{bx},{yb+4} Q{bx},{yb} {bx+4},{yb} L{bx+76},{yb} '
                     f'Q{bx+80},{yb} {bx+80},{yb+4} L{bx+80},{base} Z" fill="{c}"/>')
            label = f"{v:g}{unit}"
            s.append(t(bx+40, yb-10, label, 22, "bold", INK, "middle"))
            s.append(t(bx+40, base+26, name, 16, fill=INK, anchor="middle"))
        s.append(f'<line x1="{x+30}" y1="{base}" x2="{x+pw-30}" y2="{base}" stroke="{MUTED}" stroke-width="1.5"/>')
        s.append(t(x+pw/2, 800, src, 15, fill=MUTED, anchor="middle"))
        ratio = before/after
        s.append(t(x+pw/2, 845, f"{ratio:.1f}× {'higher' if after > before else 'lower'}" if after < before
                   else f"{after/before:.1f}× higher", 19, "bold", anchor="middle"))
    save("guide-6-results", s)


# 7 ---------------------------------------------------------------- noise layers
def noise():
    s = head("Noise reduction, layer by layer",
             "nothing averages pings on the box; each layer removes a different kind of error")
    layers = [
        ("Firmware", True, "no trigger while ECHO high · 25 ms timeout, 20–4000 mm · lease 1000 ms, 65 ms gap · ramp 150 °/s, settle ≤ 700 ms",
         "overlapping pings, impossible values, stale or doubled pings, pinging mid-swing"),
        ("Schedule", False, "one ping in the air + 65 ms acoustic guard", "cross-talk between boxes"),
        ("Timing", False, "reject a reading whose timing window is too wide (−3 ms … 0.12 s)", "delayed packets"),
        ("Calibration", False, "empty-room map: median of 3 pings per bearing, ≥ 2 valid", "walls, tables, floor"),
        ("Classify", False, "static-echo band ±0.15 m, ±10° · range gates 0.10 / 1.7 m · body radius 0.18 m · confirm ping",
         "room echoes, unreliable far echoes, surface-vs-centre bias, one-off reflections"),
        ("Fusion", False, "residual ≤ 0.30 m + beam check 20° + 10° · largest agreeing group, outvote · fresh ≤ 0.6 s",
         "ghost intersections, one box with a bad echo, stale positions"),
        ("Filter", False, "jump gate 3 m/s · dt + 0.3 m · exponential smoothing τ 0.12 s, half weight for one box",
         "physically impossible moves, range jitter"),
        ("Alerts", False, "debounce 0.3 / 0.5 / 1.0 s, then a 2 s latch", "flickering warnings"),
    ]
    y, h, gap = 130, 82, 9
    for i, (name, on_box, what, removes) in enumerate(layers):
        yy = y + i*(h + gap)
        fill, stroke = (AMBER_SOFT, AMBER) if on_box else (TEAL_SOFT, TEAL_LINE)
        s.append(rect(150, yy, 1400, h, "#ffffff", RULE, rx=8, sw=1.5))
        s.append(rect(150, yy, 200, h, fill, stroke, rx=8, sw=2))
        s.append(t(250, yy+h/2+7, name, 20, "bold", anchor="middle"))
        s.append(t(375, yy+34, what, 17))
        s.append(t(375, yy+62, "removes: " + removes, 16, fill=MUTED))
    # side brackets
    s.append(t(110, y+h/2+6, "box", 17, "bold", AMBER, "middle"))
    ly0, ly1 = y + (h+gap), y + 8*(h+gap) - gap
    s.append(f'<path d="M130,{ly0+4} L118,{ly0+4} L118,{ly1-4} L130,{ly1-4}" fill="none" stroke="{TEAL_LINE}" stroke-width="2.5"/>')
    s.append(f'<text x="100" y="{(ly0+ly1)/2}" font-size="17" font-weight="bold" fill="{TEAL_LINE}" text-anchor="middle" '
             f'transform="rotate(-90 100 {(ly0+ly1)/2})">laptop</text>')
    s.append(arrow(f"M75,{y+10} L75,{ly1-10}"))
    s.append(t(60, 875, "raw ping at the top → clean spot on screen at the bottom", 15, fill=MUTED))
    save("guide-7-noise", s)


OUT.mkdir(parents=True, exist_ok=True)
for fn in (pipeline, protocol, classify, fusion, timeline, results, noise):
    fn()
