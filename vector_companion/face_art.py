"""Little images for Vector's face screen (184 x 96 on Vector 1.0)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

W, H = 184, 96
GREEN = (48, 215, 75)
RED = (255, 69, 58)
PINK = (255, 55, 95)
YELLOW = (255, 214, 10)
TEAL = (47, 214, 201)
WHITE = (240, 240, 245)


def _font(size: int):
    for name in ("/System/Library/Fonts/SFNSRounded.ttf", "/System/Library/Fonts/SFNS.ttf",
                 "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _canvas():
    im = Image.new("RGB", (W, H), (0, 0, 0))
    return im, ImageDraw.Draw(im)


def heart(scale: float = 1.0) -> Image.Image:
    im, d = _canvas()
    pts = []
    for i in range(200):
        t = 2 * math.pi * i / 200
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((W / 2 + x * 2.6 * scale, H / 2 - 4 - y * 2.6 * scale))
    d.polygon(pts, fill=PINK)
    return im


def check() -> Image.Image:
    im, d = _canvas()
    d.ellipse([W / 2 - 38, H / 2 - 38, W / 2 + 38, H / 2 + 38], outline=GREEN, width=6)
    d.line([(W / 2 - 18, H / 2 + 2), (W / 2 - 4, H / 2 + 16), (W / 2 + 20, H / 2 - 14)], fill=GREEN, width=8, joint="curve")
    return im


def cross() -> Image.Image:
    im, d = _canvas()
    d.ellipse([W / 2 - 38, H / 2 - 38, W / 2 + 38, H / 2 + 38], outline=RED, width=6)
    for a, b in (((-16, -16), (16, 16)), ((-16, 16), (16, -16))):
        d.line([(W / 2 + a[0], H / 2 + a[1]), (W / 2 + b[0], H / 2 + b[1])], fill=RED, width=8)
    return im


def question() -> Image.Image:
    im, d = _canvas()
    d.ellipse([W / 2 - 38, H / 2 - 38, W / 2 + 38, H / 2 + 38], outline=YELLOW, width=6)
    f = _font(52)
    d.text((W / 2, H / 2 + 2), "?", fill=YELLOW, font=f, anchor="mm")
    return im


def thinking(phase: int = 0) -> Image.Image:
    im, d = _canvas()
    for i in range(3):
        r = 9 if i == phase % 3 else 6
        x = W / 2 + (i - 1) * 32
        d.ellipse([x - r, H / 2 - r, x + r, H / 2 + r], fill=TEAL)
    return im


def camera() -> Image.Image:
    im, d = _canvas()
    d.rounded_rectangle([W / 2 - 44, H / 2 - 26, W / 2 + 44, H / 2 + 30], 10, outline=WHITE, width=5)
    d.rectangle([W / 2 - 16, H / 2 - 36, W / 2 + 16, H / 2 - 26], fill=WHITE)
    d.ellipse([W / 2 - 16, H / 2 - 14, W / 2 + 16, H / 2 + 18], outline=WHITE, width=5)
    return im


def timer(minutes_left: int, total: int) -> Image.Image:
    im, d = _canvas()
    frac = max(0.0, min(1.0, minutes_left / max(total, 1)))
    d.arc([8, 8, 88, 88], 0, 360, fill=(40, 40, 44), width=8)
    d.arc([8, 8, 88, 88], -90, -90 + 360 * frac, fill=GREEN, width=8)
    d.text((48, 50), str(minutes_left), fill=WHITE, font=_font(30), anchor="mm")
    d.text((136, 38), "FOCUS", fill=GREEN, font=_font(16), anchor="mm")
    d.text((136, 60), "min left", fill=(150, 150, 155), font=_font(13), anchor="mm")
    return im


def text(msg: str, color=WHITE) -> Image.Image:
    """Up to ~3 short lines, auto-sized."""
    im, d = _canvas()
    words, lines, size = msg.split(), [], 26
    while size >= 12:
        f = _font(size)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=f) <= W - 12:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) * (size + 4) <= H - 8:
            break
        size -= 2
    f = _font(size)
    total = len(lines) * (size + 4)
    for i, ln in enumerate(lines):
        d.text((W / 2, (H - total) / 2 + i * (size + 4) + size / 2 + 2), ln, fill=color, font=f, anchor="mm")
    return im


ICONS = {"heart": heart, "check": check, "x": cross, "question": question, "camera": camera, "thinking": thinking}


ORANGE = (255, 159, 10)


def _badge(label: str, color, draw_glyph):
    """Label on top, glyph in the middle: used for 'who finished' notifications."""
    im, d = _canvas()
    d.text((W / 2, 13), label, fill=color, font=_font(15), anchor="mm")
    draw_glyph(d)
    return im


def ai_done(label: str = "CLAUDE") -> Image.Image:
    def g(d):
        cx, cy = W / 2, 58
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=GREEN, width=5)
        d.line([(cx - 14, cy + 1), (cx - 3, cy + 12), (cx + 16, cy - 11)], fill=GREEN, width=7, joint="curve")
    return _badge(label, ORANGE, g)


def ai_input(label: str = "CLAUDE") -> Image.Image:
    def g(d):
        cx, cy = W / 2, 56
        d.rounded_rectangle([cx - 40, cy - 26, cx + 40, cy + 20], 12, outline=YELLOW, width=5)
        d.polygon([(cx - 14, cy + 18), (cx - 26, cy + 34), (cx - 2, cy + 18)], fill=YELLOW)
        for i in (-1, 0, 1):
            d.ellipse([cx + i * 18 - 5, cy - 8, cx + i * 18 + 5, cy + 2], fill=YELLOW)
    return _badge(label, ORANGE, g)


def terminal(ok: bool = True, label: str = "TERMINAL") -> Image.Image:
    color = GREEN if ok else RED

    def g(d):
        x0, y0, x1, y1 = W / 2 - 48, 28, W / 2 + 48, 88
        d.rounded_rectangle([x0, y0, x1, y1], 9, outline=WHITE, width=4)
        d.line([(x0 + 2, y0 + 15), (x1 - 2, y0 + 15)], fill=WHITE, width=3)
        for i, c in enumerate((RED, YELLOW, GREEN)):
            d.ellipse([x0 + 9 + i * 10, y0 + 5, x0 + 15 + i * 10, y0 + 11], fill=c)
        if ok:
            d.line([(x0 + 16, y0 + 25), (x0 + 30, y0 + 35), (x0 + 16, y0 + 45)], fill=color, width=5)
            d.line([(x0 + 38, y0 + 47), (x0 + 60, y0 + 47)], fill=color, width=5)
        else:
            d.text((W / 2, y0 + 36), "!", fill=color, font=_font(34), anchor="mm")
    return _badge(label, color, g)


def moon() -> Image.Image:
    im, d = _canvas()
    d.ellipse([W / 2 - 30, H / 2 - 30, W / 2 + 30, H / 2 + 30], fill=(200, 200, 230))
    d.ellipse([W / 2 - 14, H / 2 - 38, W / 2 + 40, H / 2 + 22], fill=(0, 0, 0))
    for x, y in ((40, 22), (140, 30), (150, 70), (30, 72)):
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=WHITE)
    return im


def status(lines: list[tuple[str, tuple]]) -> Image.Image:
    """A compact HUD: up to 4 short colored lines."""
    im, d = _canvas()
    f = _font(15)
    for i, (txt, col) in enumerate(lines[:4]):
        d.text((8, 8 + i * 21), txt, fill=col, font=f)
    return im


ICONS.update({"ai_done": ai_done, "ai_input": ai_input, "terminal_ok": lambda: terminal(True),
              "terminal_fail": lambda: terminal(False), "moon": moon})
