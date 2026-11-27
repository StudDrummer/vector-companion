"""Vector's face screen (184 x 96): one HUD design language for everything he shows.

Everything is drawn at 4x on near-black, given a soft glow (a blurred copy of the bright parts added
back on), then scaled down, so lines stay crisp and look lit from behind on his small screen. Colours:
cyan for Jarvis / information, green for done, amber for attention, red for problems.
Animated faces take a `phase` (0..1 or a frame counter) so the caller can step them.
"""
from __future__ import annotations

import math
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 184, 96
K = 4                    # supersampling
GREEN = (48, 225, 120)
RED = (255, 69, 58)
PINK = (255, 64, 110)
YELLOW = (255, 204, 40)
ORANGE = (255, 159, 10)
TEAL = (47, 214, 201)
CYAN = (90, 210, 255)
BLUE = (10, 132, 255)
WHITE = (236, 246, 255)
DIM = (40, 90, 120)
BG = (2, 6, 12)
CARD = (246, 246, 248)
INK = (28, 28, 32)
SUIT_RED = (225, 40, 55)


# ---------------------------------------------------------------- basics
def _font(size: int, mono: bool = False):
    names = (("/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono-Bold.ttf",
              "DejaVuSansMono.ttf") if mono else
             ("/System/Library/Fonts/SFNSRounded.ttf", "/System/Library/Fonts/SFNS.ttf",
              "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _canvas():
    """Plain 1x canvas (kept for older callers)."""
    im = Image.new("RGB", (W, H), (0, 0, 0))
    return im, ImageDraw.Draw(im)


def _hi(bg=BG):
    im = Image.new("RGB", (W * K, H * K), bg)
    return im, ImageDraw.Draw(im)


def _glow(im: Image.Image, strength: float = 1.0, radius: int = 14) -> Image.Image:
    """Add a halo around everything bright."""
    bright = im.point(lambda v: max(0, v - 40) * 1.4)
    halo = bright.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        halo = halo.point(lambda v: min(255, int(v * strength)))
    return ImageChops.add(im, halo)


def _done(im: Image.Image, glow: float = 1.0) -> Image.Image:
    if glow:
        im = _glow(im, glow)
    return im.resize((W, H), Image.LANCZOS)


def _grid(d, col=(8, 22, 32), step=48):
    """Faint tech grid + corner brackets: the HUD frame everything sits in."""
    for x in range(0, W * K, step):
        d.line([(x, 0), (x, H * K)], fill=col, width=1)
    for y in range(0, H * K, step):
        d.line([(0, y), (W * K, y)], fill=col, width=1)


def _brackets(d, col=DIM, inset=10, ln=36, w=4):
    x0, y0, x1, y1 = inset, inset, W * K - inset, H * K - inset
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(x, y), (x + dx * ln, y)], fill=col, width=w)
        d.line([(x, y), (x, y + dy * ln)], fill=col, width=w)


def _ring(d, cx, cy, r, col, w, a0=0, a1=360):
    d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=col, width=w)


def _ticks(d, cx, cy, r1, r2, n, col, w=3, every=0, long_add=0):
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r2 + (long_add if every and i % every == 0 else 0)
        d.line([(cx + r1 * math.cos(a), cy + r1 * math.sin(a)), (cx + rr * math.cos(a), cy + rr * math.sin(a))],
               fill=col, width=w)


def _reactor(d, cx, cy, r, col=CYAN, phase: float = 0.0):
    """The arc-reactor core used across Jarvis faces."""
    _ring(d, cx, cy, r, tuple(c // 4 for c in col), 6)
    a = phase * 360
    for k in range(3):  # three rotating segments
        _ring(d, cx, cy, r, col, 8, a + k * 120, a + k * 120 + 70)
    _ring(d, cx, cy, r * 0.74, tuple(c // 2 for c in col), 4)
    _ticks(d, cx, cy, r * 0.80, r * 0.88, 24, tuple(c // 2 for c in col), 3)
    for k in range(6):  # spokes
        b = math.radians(-a * 0.5 + k * 60)
        d.line([(cx + r * 0.28 * math.cos(b), cy + r * 0.28 * math.sin(b)),
                (cx + r * 0.62 * math.cos(b), cy + r * 0.62 * math.sin(b))], fill=tuple(c // 2 for c in col), width=4)
    d.ellipse([cx - r * 0.30, cy - r * 0.30, cx + r * 0.30, cy + r * 0.30], fill=tuple(int(c * 0.8) for c in col))
    d.ellipse([cx - r * 0.16, cy - r * 0.16, cx + r * 0.16, cy + r * 0.16], fill=WHITE)


def _label(d, x, y, txt, col=CYAN, size=26, anchor="la"):
    d.text((x, y), txt, fill=col, font=_font(size, mono=True), anchor=anchor)


def _fit(d, txt, max_w, size, mono=False, min_size=18):
    while size > min_size and d.textlength(txt, font=_font(size, mono)) > max_w:
        size -= 2
    return _font(size, mono), size


def _phase(phase):
    return (time.time() % 3) / 3 if phase is None else phase


# ---------------------------------------------------------------- icons
def _badge_icon(col, draw, label: str | None = None, phase=None):
    im, d = _hi()
    _grid(d)
    _brackets(d, tuple(c // 3 for c in col))
    cx, cy = W * K / 2, H * K / 2 + (14 if label else 0)
    r = 120 if not label else 100
    p = _phase(phase)
    _ring(d, cx, cy, r + 26, tuple(c // 5 for c in col), 4)
    _ring(d, cx, cy, r + 26, tuple(c // 2 for c in col), 6, p * 360, p * 360 + 50)
    _ring(d, cx, cy, r, col, 10)
    _ticks(d, cx, cy, r + 8, r + 16, 36, tuple(c // 3 for c in col), 3)
    draw(d, cx, cy, r)
    if label:
        _label(d, W * K / 2, 22, label, col, 34, "ma")
    return _done(im)


def check(label: str | None = None) -> Image.Image:
    return _badge_icon(GREEN, lambda d, cx, cy, r: d.line(
        [(cx - r * .42, cy + r * .02), (cx - r * .1, cy + r * .34), (cx + r * .46, cy - r * .3)],
        fill=GREEN, width=22, joint="curve"), label)


def cross(label: str | None = None) -> Image.Image:
    def g(d, cx, cy, r):
        for a, b in (((-1, -1), (1, 1)), ((-1, 1), (1, -1))):
            d.line([(cx + a[0] * r * .36, cy + a[1] * r * .36), (cx + b[0] * r * .36, cy + b[1] * r * .36)], fill=RED, width=22)
    return _badge_icon(RED, g, label)


def question() -> Image.Image:
    return _badge_icon(YELLOW, lambda d, cx, cy, r: d.text((cx, cy + 6), "?", fill=YELLOW, font=_font(170), anchor="mm"))


def heart(scale: float = 1.0) -> Image.Image:
    im, d = _hi()
    _grid(d)
    cx, cy = W * K / 2, H * K / 2 - 8
    for s, col, w in ((1.25, (90, 20, 40), 0), (1.0, PINK, 0)):
        pts = []
        for i in range(240):
            t = 2 * math.pi * i / 240
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((cx + x * 9.5 * scale * s, cy - y * 9.5 * scale * s))
        if s > 1:
            d.line(pts + pts[:1], fill=col, width=6)
        else:
            d.polygon(pts, fill=col)
    # a heartbeat trace across it
    pts, base = [], H * K - 40
    for x in range(20, W * K - 20, 6):
        u = (x - 20) / (W * K - 40)
        y = base - (60 * math.exp(-((u - 0.5) * 18) ** 2) * math.sin((u - 0.5) * 60)) if 0.4 < u < 0.6 else base
        pts.append((x, y))
    d.line(pts, fill=(255, 150, 175), width=4)
    return _done(im, 1.2)


def camera() -> Image.Image:
    im, d = _hi()
    _grid(d)
    cx, cy = W * K / 2, H * K / 2
    for i, r in enumerate((150, 110)):
        _ring(d, cx, cy, r, CYAN if i else DIM, 6 if i else 4)
    _ticks(d, cx, cy, 118, 136, 8, CYAN, 6)
    d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=CYAN)
    d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=WHITE)
    _brackets(d, CYAN, 20, 60, 6)
    _label(d, 30, H * K - 52, "CAPTURE", CYAN, 28)
    return _done(im)


def thinking(phase: int = 0) -> Image.Image:
    return thinking_dots(phase)


def moon() -> Image.Image:
    im, d = _hi((0, 2, 8))
    cx, cy = W * K / 2 - 120, H * K / 2
    d.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(170, 190, 235))
    d.ellipse([cx - 40, cy - 115, cx + 125, cy + 60], fill=(0, 2, 8))
    for x, y in ((420, 70), (520, 120), (600, 60), (470, 280), (640, 250), (380, 200)):
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=WHITE)
    _label(d, W * K / 2 + 20, H * K / 2 - 20, "STANDBY", (110, 140, 200), 40)
    return _done(im, 0.8)


def text(msg: str, color=WHITE) -> Image.Image:
    """Up to ~3 short lines, auto-sized, on the HUD frame."""
    im, d = _hi()
    _grid(d)
    _brackets(d, DIM)
    words, size = msg.split(), 104
    while size >= 44:
        f = _font(size)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=f) <= W * K - 60:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) * (size + 14) <= H * K - 40:
            break
        size -= 6
    f = _font(size)
    total = len(lines) * (size + 14)
    for i, ln in enumerate(lines):
        d.text((W * K / 2, (H * K - total) / 2 + i * (size + 14) + size / 2 + 6), ln, fill=color, font=f, anchor="mm")
    return _done(im, 0.7)


def timer(minutes_left: int, total: int) -> Image.Image:
    im, d = _hi()
    _grid(d)
    frac = max(0.0, min(1.0, minutes_left / max(total, 1)))
    cx, cy, r = 190, H * K / 2, 150
    _ring(d, cx, cy, r, (14, 40, 30), 22)
    _ring(d, cx, cy, r, GREEN, 22, -90, -90 + 360 * frac)
    _ticks(d, cx, cy, r + 18, r + 26, 60, (30, 90, 60), 3, 5, 8)
    d.text((cx, cy - 4), str(minutes_left), fill=WHITE, font=_font(110), anchor="mm")
    _label(d, 400, 92, "FOCUS", GREEN, 44)
    _label(d, 400, 150, "MIN LEFT", (120, 170, 140), 30)
    for i in range(10):  # progress segments
        on = i < round(frac * 10)
        d.rectangle([400 + i * 30, 230, 400 + i * 30 + 22, 262], fill=GREEN if on else (20, 50, 35))
    return _done(im)


def status(lines: list[tuple[str, tuple]]) -> Image.Image:
    """A compact HUD readout: up to 4 short coloured lines."""
    im, d = _hi()
    _grid(d)
    _brackets(d, DIM)
    for i, (txt, col) in enumerate(lines[:4]):
        y = 26 + i * 86
        d.rectangle([28, y + 16, 38, y + 52], fill=col)
        f, _ = _fit(d, txt, W * K - 90, 60, mono=True, min_size=30)
        d.text((58, y + 34), txt, fill=col, font=f, anchor="lm")
    return _done(im, 0.8)


def _badge(label: str, color, draw_glyph):
    """Label on top, glyph below (notifications from Claude / the terminal)."""
    im, d = _hi()
    _grid(d)
    _brackets(d, tuple(c // 3 for c in color))
    _label(d, W * K / 2, 18, label, color, 40, "ma")
    d.line([(60, 74), (W * K - 60, 74)], fill=tuple(c // 3 for c in color), width=3)
    draw_glyph(d)
    return _done(im)


def ai_done(label: str = "CLAUDE") -> Image.Image:
    def g(d):
        cx, cy = W * K / 2, 230
        _ring(d, cx, cy, 108, GREEN, 12)
        d.line([(cx - 50, cy + 4), (cx - 12, cy + 42), (cx + 56, cy - 40)], fill=GREEN, width=20, joint="curve")
    return _badge(label, ORANGE, g)


def ai_input(label: str = "CLAUDE") -> Image.Image:
    def g(d):
        cx, cy = W * K / 2, 220
        d.rounded_rectangle([cx - 150, cy - 90, cx + 150, cy + 70], 40, outline=YELLOW, width=12)
        d.polygon([(cx - 50, cy + 66), (cx - 96, cy + 130), (cx - 6, cy + 66)], fill=YELLOW)
        for i in (-1, 0, 1):
            d.ellipse([cx + i * 66 - 18, cy - 28, cx + i * 66 + 18, cy + 8], fill=YELLOW)
    return _badge(label, ORANGE, g)


def terminal(ok: bool = True, label: str = "TERMINAL") -> Image.Image:
    color = GREEN if ok else RED

    def g(d):
        x0, y0, x1, y1 = W * K / 2 - 180, 100, W * K / 2 + 180, 350
        d.rounded_rectangle([x0, y0, x1, y1], 28, outline=(160, 180, 200), width=8)
        d.line([(x0 + 4, y0 + 50), (x1 - 4, y0 + 50)], fill=(160, 180, 200), width=6)
        for i, c in enumerate((RED, YELLOW, GREEN)):
            d.ellipse([x0 + 28 + i * 34, y0 + 16, x0 + 48 + i * 34, y0 + 36], fill=c)
        if ok:
            d.line([(x0 + 50, y0 + 90), (x0 + 100, y0 + 130), (x0 + 50, y0 + 170)], fill=color, width=16)
            d.line([(x0 + 130, y0 + 175), (x0 + 220, y0 + 175)], fill=color, width=16)
        else:
            d.text((W * K / 2, y0 + 140), "!", fill=color, font=_font(130), anchor="mm")
    return _badge(label, color, g)


# ---------------------------------------------------------------- Jarvis
def jarvis_idle(clock: str = "", phase=None) -> Image.Image:
    """Jarvis mode's resting face: the reactor core, the time and the date, on the HUD frame."""
    im, d = _hi()
    _grid(d)
    _brackets(d)
    p = _phase(phase)
    cx, cy = 180, H * K / 2
    _reactor(d, cx, cy, 140, CYAN, p)
    if clock:
        f, _ = _fit(d, clock, W * K - 400, 124, min_size=60)
        d.text((360, 150), clock, fill=WHITE, font=f, anchor="lm")
        d.text((364, 268), time.strftime("%a %d %b").upper(), fill=(90, 170, 220), font=_font(32, True), anchor="lm")
        _label(d, 364, 40, "J.A.R.V.I.S.", (60, 140, 200), 30)
        d.line([(364, 300), (W * K - 40, 300)], fill=DIM, width=3)
        for i in range(8):  # little live bars
            h = 8 + 22 * abs(math.sin(p * 6.28 + i))
            d.rectangle([364 + i * 26, 340 - h, 380 + i * 26, 340], fill=(40, 120, 170))
    return _done(im)


def talking(phase=None, level: float = 0.7) -> Image.Image:
    """While Jarvis speaks: the core with a live voice trace through it."""
    im, d = _hi()
    _grid(d)
    p = _phase(phase)
    cx, cy = W * K / 2, H * K / 2
    _reactor(d, cx, cy, 120, CYAN, p)
    for k, (col, amp, w) in enumerate(((DIM, 1.0, 4), (CYAN, 0.75, 6), (WHITE, 0.5, 4))):
        pts = []
        for x in range(30, W * K - 30, 6):
            u = (x - 30) / (W * K - 60)
            env = math.sin(math.pi * u) ** 1.5
            y = cy + level * amp * 110 * env * math.sin(u * 38 + p * 25 + k) * (0.6 + 0.4 * math.sin(u * 9 - p * 8))
            pts.append((x, y))
        d.line(pts, fill=col, width=w, joint="curve")
    return _done(im, 1.1)


def listening(level: float = 0.6, phase=None) -> Image.Image:
    """The moment you say 'Jarvis': a scanning waveform."""
    im, d = _hi()
    _grid(d)
    _brackets(d, CYAN)
    p = _phase(phase)
    cx, cy = W * K / 2, H * K / 2
    n, bw, gap = 23, 16, 10
    x = cx - (n * bw + (n - 1) * gap) / 2
    for i in range(n):
        u = i / (n - 1)
        b = (0.35 + 0.65 * abs(math.sin(i * 0.9 + p * 6.28))) * math.sin(math.pi * u) ** 0.7
        hh = 20 + b * level * 250
        col = (int(40 + 60 * b), int(150 + 80 * b), 255)
        d.rounded_rectangle([x, cy - hh / 2, x + bw, cy + hh / 2], bw / 2, fill=col)
        x += bw + gap
    _label(d, 30, 22, "LISTENING", CYAN, 28)
    return _done(im, 1.1)


def thinking_dots(phase: int = 0) -> Image.Image:
    """Working on it: a radar sweep."""
    return hud_action("PROCESSING", "", phase=(phase % 12) / 12)


def card_hud(title: str, lines: list[tuple[str, tuple]], accent=CYAN) -> Image.Image:
    """An info panel: title bar + up to 3 lines (status, weather, quiz questions)."""
    im, d = _hi()
    _grid(d)
    d.rectangle([0, 0, W * K, 70], fill=tuple(c // 6 for c in accent))
    d.rectangle([0, 66, W * K, 72], fill=accent)
    _label(d, 24, 14, title.upper()[:22], accent, 40)
    y = 96
    for txt, col in lines[:3]:
        f, size = _fit(d, txt, W * K - 50, 74 if len(txt) < 14 else 58, min_size=34)
        d.text((24, y), txt, fill=col, font=f)
        y += size + 22
    return _done(im, 0.7)


def hud_action(title: str, sub: str = "", phase=None, accent=CYAN, pct: float | None = None) -> Image.Image:
    """Shown while he's doing something (Jarvis mode): a radar sweep, what he's doing, and progress."""
    im, d = _hi()
    _grid(d)
    _brackets(d, accent)
    p = _phase(phase)
    cx, cy, r = 170, H * K / 2, 140
    for rr in (r, r * 0.66, r * 0.33):
        _ring(d, cx, cy, rr, tuple(c // 4 for c in accent), 3)
    d.line([(cx - r, cy), (cx + r, cy)], fill=tuple(c // 5 for c in accent), width=2)
    d.line([(cx, cy - r), (cx, cy + r)], fill=tuple(c // 5 for c in accent), width=2)
    a = p * 2 * math.pi
    for k in range(18):  # the sweep and its fading tail
        b = a - k * 0.05
        col = tuple(int(c * (1 - k / 18) * 0.9) for c in accent)
        d.line([(cx, cy), (cx + r * math.cos(b), cy + r * math.sin(b))], fill=col, width=6 if k == 0 else 4)
    for k, (u, v) in enumerate(((0.4, -0.3), (-0.5, 0.2), (0.15, 0.55))):  # blips
        bx, by = cx + u * r, cy + v * r
        ang = (math.atan2(by - cy, bx - cx) - a) % (2 * math.pi)
        lum = max(0.15, 1 - ang / 2.5)
        d.ellipse([bx - 9, by - 9, bx + 9, by + 9], fill=tuple(int(c * lum) for c in accent))
    f, _ = _fit(d, title.upper(), W * K - 390, 54, mono=True, min_size=28)
    d.text((350, 120), title.upper(), fill=accent, font=f, anchor="lm")
    if sub:
        f2, _ = _fit(d, sub, W * K - 390, 34, mono=True, min_size=22)
        d.text((350, 186), sub, fill=(150, 200, 230), font=f2, anchor="lm")
    if pct is not None:
        d.rectangle([350, 250, W * K - 40, 270], outline=tuple(c // 2 for c in accent), width=3)
        d.rectangle([354, 254, 354 + (W * K - 398) * max(0, min(1, pct)), 266], fill=accent)
    else:  # indeterminate: a moving segment
        x = 350 + ((W * K - 430) * p)
        d.rectangle([350, 258, W * K - 40, 262], fill=tuple(c // 4 for c in accent))
        d.rectangle([x, 252, x + 80, 268], fill=accent)
    return _done(im)


def equalizer(phase=None, accent=CYAN) -> Image.Image:
    """Dance / music: a spectrum."""
    im, d = _hi()
    _grid(d)
    p = _phase(phase)
    n = 28
    bw = (W * K - 60) / n
    for i in range(n):
        v = 0.5 + 0.5 * math.sin(i * 0.7 + p * 12) * math.cos(i * 0.23 - p * 5)
        h = 20 + v * (H * K - 70)
        col = (int(accent[0] * (0.4 + 0.6 * v)), int(accent[1] * (0.6 + 0.4 * v)), accent[2])
        for y in range(int(H * K - 30), int(H * K - 30 - h), -18):  # segmented LED bars
            d.rectangle([30 + i * bw + 3, y - 13, 30 + (i + 1) * bw - 3, y], fill=col)
    return _done(im, 1.2)


def gesture(name: str, phase=None) -> Image.Image:
    """Jarvis mode's stand-ins for Vector's emotional animations."""
    labels = {"fist_bump": ("CONTACT", GREEN), "love": ("APPRECIATED", PINK), "praise": ("THANK YOU", GREEN),
              "scold": ("NOTED", ORANGE), "hello": ("HELLO", CYAN), "goodbye": ("GOODBYE", CYAN),
              "sleep": ("STANDBY", (110, 140, 200)), "win": ("I WIN", GREEN), "lose": ("YOU WIN", ORANGE),
              "push": ("PUSH", YELLOW), "think": ("THINKING", CYAN), "trick": ("SHOWTIME", CYAN)}
    label, col = labels.get(name, (name.upper(), CYAN))
    im, d = _hi()
    _grid(d)
    _brackets(d, col)
    p = _phase(phase)
    cx, cy = W * K / 2, H * K / 2
    for k in range(4):  # expanding rings
        rr = 40 + ((p + k / 4) % 1) * 200
        _ring(d, cx, cy, rr, tuple(int(c * (1 - rr / 240)) for c in col), 6)
    f, _ = _fit(d, label, W * K - 80, 92, min_size=40)
    d.text((cx, cy), label, fill=WHITE, font=f, anchor="mm")
    return _done(im, 1.1)


# ---------------------------------------------------------------- blackjack
def _suit(d, suit: str, cx: float, cy: float, r: float, color):
    """Draw a suit symbol centred at (cx, cy), roughly r wide."""
    if suit in "♥h":
        pts = []
        for i in range(120):
            t = 2 * math.pi * i / 120
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((cx + x * r / 34, cy - 1.5 - y * r / 34))
        d.polygon(pts, fill=color)
    elif suit in "♦d":
        d.polygon([(cx, cy - r * 0.6), (cx + r * 0.42, cy), (cx, cy + r * 0.6), (cx - r * 0.42, cy)], fill=color)
    elif suit in "♠s":
        pts = []
        for i in range(120):
            t = 2 * math.pi * i / 120
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((cx + x * r / 34, cy - 3 + y * r / 34))
        d.polygon(pts, fill=color)
        d.polygon([(cx, cy), (cx + r * 0.22, cy + r * 0.55), (cx - r * 0.22, cy + r * 0.55)], fill=color)
    else:  # clubs
        rr = r * 0.24
        for ox, oy in ((0, -r * 0.24), (-r * 0.25, r * 0.08), (r * 0.25, r * 0.08)):
            d.ellipse([cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr], fill=color)
        d.polygon([(cx, cy), (cx + r * 0.2, cy + r * 0.55), (cx - r * 0.2, cy + r * 0.55)], fill=color)


def _card(d, x: float, y: float, w: float, h: float, rank: str | None, suit: str = "s", big: bool = False):
    """One playing card: corner index (rank over a small suit), big suit if it's the top card. None = face down."""
    rad = w * 0.13
    d.rounded_rectangle([x + 4, y + 5, x + w + 4, y + h + 5], rad, fill=(0, 10, 20))  # shadow
    if rank is None:
        d.rounded_rectangle([x, y, x + w, y + h], rad, fill=(8, 36, 70), outline=CYAN, width=5)
        ins = w * 0.18
        d.rounded_rectangle([x + ins, y + ins, x + w - ins, y + h - ins], rad * 0.5, outline=(40, 120, 180), width=3)
        cx, cy = x + w / 2, y + h / 2
        _ring(d, cx, cy, w * 0.22, CYAN, 4)
        d.ellipse([cx - w * 0.07, cy - w * 0.07, cx + w * 0.07, cy + w * 0.07], fill=WHITE)
        return
    col = SUIT_RED if suit in "hd" else INK
    d.rounded_rectangle([x, y, x + w, y + h], rad, fill=CARD)
    f = _font(int(h * (0.30 if len(rank) == 1 else 0.24)))
    d.text((x + w * (0.10 if len(rank) == 1 else 0.05), y + h * 0.03), rank, fill=col, font=f)
    _suit(d, suit, x + w * 0.24, y + h * 0.50, w * 0.34, col)
    if big:
        _suit(d, suit, x + w * 0.62, y + h * 0.68, w * 0.55, col)


def _pill(d, x: float, y: float, text: str, bg, fg=(0, 0, 0), size: int = 30):
    f = _font(size)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([x, y, x + tw + 34, y + size + 18], (size + 18) / 2, fill=bg)
    d.text((x + 17, y + 6), text, fill=fg, font=f)


def blackjack(you: list, me: list, you_total: int, me_total: int | None, banner: str = "", banner_color=GREEN):
    """The table: his hand on top (one face down until reveal), yours below, totals as pills.
    Cards are (rank, suit) with suit one of h d s c; None = face down."""
    im, d = _hi((3, 14, 22))
    _grid(d, (8, 30, 40))
    d.rounded_rectangle([6, 6, W * K - 6, H * K - 6], 36, outline=(30, 110, 150), width=4)
    cw, ch = 110, 158
    step = 70

    def row(cards, y, label, total, color):
        x = 28
        for i, c in enumerate(cards):
            last = i == len(cards) - 1
            _card(d, x, y, cw, ch, None if c is None else c[0], "s" if c is None else c[1], big=last)
            x += step
        px = W * K - 190
        _label(d, px + 6, y + 6, label, (120, 180, 210), 30)
        _pill(d, px, y + 56, "?" if total is None else str(total), color, (0, 0, 0), 54)

    row(me, 22, "JARVIS" if _jarvis_style() else "VECTOR", me_total, CYAN)
    row(you, 22 + ch + 24, "YOU", you_total, YELLOW if you_total <= 21 else RED)
    if banner:
        f = _font(62)
        tw = d.textlength(banner, font=f)
        bw, bh = tw + 90, 108
        bx, by = (W * K - bw) / 2, (H * K - bh) / 2
        d.rounded_rectangle([bx + 5, by + 8, bx + bw + 5, by + bh + 8], 54, fill=(0, 0, 0))
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 54, fill=banner_color)
        d.text((bx + 45, by + 18), banner, fill=(0, 0, 0), font=f)
    return _done(im, 0.5)


def _jarvis_style() -> bool:
    try:
        from . import settings as S
        return S.load().get("persona", {}).get("style") == "jarvis"
    except Exception:  # noqa: BLE001
        return False


ICONS = {"heart": heart, "check": check, "x": cross, "question": question, "camera": camera, "thinking": thinking_dots,
         "ai_done": ai_done, "ai_input": ai_input, "terminal_ok": lambda: terminal(True),
         "terminal_fail": lambda: terminal(False), "moon": moon, "listening": listening, "talking": talking,
         "jarvis": jarvis_idle}
