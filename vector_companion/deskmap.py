"""Desk map: where it's safe for Vector to drive, kept in a frame fixed to his charger so it survives
restarts and his own idea of "where am I" resetting.

How it's built (Motion "desk_scan"): from the dock he drives slow, short hops out along a fan of
straight lines. Before every hop he checks his distance sensor; each line ends at the desk edge (his
edge sensors fire and he backs off), at an obstacle (he stops 7 cm short, so nothing gets pushed), or
when he's stuck. The floor between neighbouring lines is filled in, and he repeats the fan from new
spots until the reachable desk is covered. It keeps improving afterwards: whenever he drives, the floor
under him, every edge and every obstacle he sees are added.

Frame: origin = where his centre sits when docked, +x = the way he faces when he drives off. mm.
Layers, one cell = 2 cm:
  floor  0 unknown, 1 floor (driven over, or inside a scanned fan), 2 edge (his cliff sensors fired)
  obst   how sure we are there's an obstacle: +3 per sighting, -1 per clear look; 2 or more counts
  zones  rectangles you draw in the app: "keep out", or "sometimes there" (the laptop) with an on/off

Roaming only ever plans through known floor, at least 8 cm from any edge, obstacle, zone or unknown
area, so he can't drive somewhere nobody has checked.
"""
from __future__ import annotations

import base64
import heapq
import json
import math
import random
import threading
import time
from collections import deque

from . import settings as S

CELL = 20
HALF = 100              # cells each side of the dock: a 4 m square
N = 2 * HALF
FILE = S.DATA_DIR / "desk_map.json"
UNKNOWN, FLOOR, EDGE = 0, 1, 2
FRONT = 45              # mm from his centre to his front edge (edge sensors, distance sensor)
PROX_MAX = 400          # trust the distance sensor this far
DOCK_ZONE = (-110, -50, 35, 50)   # the charger itself: never somewhere to roam
ROAM_CLEAR = 80         # mm he keeps from edges, obstacles, zones and the unknown
OBST = 2


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Lost(Exception):
    """He was picked up or moved, so his position on the map is unknown until he's back on the dock."""


class Map:
    def __init__(self):
        self.lock = threading.RLock()
        self.zones: list[dict] = []
        self.anchor = None            # (origin_id, x, y, th): his odometry pose while docked
        self.charger_offset = None    # docked pose relative to the charger he sees: re-anchor by sight
        self.scanned_at = 0.0
        self.drift_mm = None
        self.progress = None          # live scan / roam status for the app
        self.dirty = False
        self.clear_layers()
        self.load()

    # ------------------------------------------------------------ storage
    def clear_layers(self):
        self.floor = bytearray(N * N)
        self.obst = bytearray(N * N)

    def load(self):
        try:
            d = json.loads(FILE.read_text())
            if d.get("cell") != CELL or d.get("n") != N:
                return
            self.floor = bytearray(base64.b64decode(d["floor"]))
            self.obst = bytearray(base64.b64decode(d["obst"]))
            self.zones = d.get("zones", [])
            self.scanned_at = d.get("scanned_at", 0)
            self.drift_mm = d.get("drift_mm")
            self.charger_offset = d.get("charger_offset")
        except Exception:  # noqa: BLE001  (no map yet)
            pass

    def save(self):
        with self.lock:
            d = {"cell": CELL, "n": N, "floor": base64.b64encode(bytes(self.floor)).decode(),
                 "obst": base64.b64encode(bytes(self.obst)).decode(), "zones": self.zones,
                 "scanned_at": self.scanned_at, "drift_mm": self.drift_mm, "charger_offset": self.charger_offset}
            FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(FILE)
            self.dirty = False

    @property
    def scanned(self) -> bool:
        return self.scanned_at > 0

    # ------------------------------------------------------------ frames
    @staticmethod
    def odom(r) -> tuple:
        p = r.pose
        return (p.origin_id, p.position.x, p.position.y, p.rotation.angle_z.radians)

    def set_anchor(self, od: tuple):
        self.anchor = tuple(od)

    def anchored(self, r) -> bool:
        try:
            return bool(self.anchor) and r.pose.origin_id == self.anchor[0]
        except Exception:  # noqa: BLE001
            return False

    def to_desk(self, od: tuple):
        """His odometry pose -> (x, y, heading) on the desk map, or None when the frames don't match."""
        a = self.anchor
        if not a or od[0] != a[0]:
            return None
        dx, dy = od[1] - a[1], od[2] - a[2]
        c, s = math.cos(-a[3]), math.sin(-a[3])
        return (c * dx - s * dy, s * dx + c * dy, wrap(od[3] - a[3]))

    def to_odom(self, x: float, y: float, th: float = 0.0):
        a = self.anchor
        c, s = math.cos(a[3]), math.sin(a[3])
        return (a[1] + c * x - s * y, a[2] + s * x + c * y, wrap(th + a[3]))

    def where(self, r):
        try:
            return self.to_desk(self.odom(r))
        except Exception:  # noqa: BLE001
            return None

    def remember_charger(self, r):
        """While docked: where he sits relative to the charger he can see, to re-anchor by sight later."""
        try:
            ch = r.world.charger
            if ch is None or ch.pose.origin_id != r.pose.origin_id:
                return
            cx, cy, cth = ch.pose.position.x, ch.pose.position.y, ch.pose.rotation.angle_z.radians
            _, x, y, th = self.odom(r)
            c, s = math.cos(-cth), math.sin(-cth)
            self.charger_offset = [c * (x - cx) - s * (y - cy), s * (x - cx) + c * (y - cy), wrap(th - cth)]
        except Exception:  # noqa: BLE001
            pass

    def anchor_from_charger(self, r) -> bool:
        """He was moved, but he can see his charger: work out where the dock is from that."""
        try:
            ch, off = r.world.charger, self.charger_offset
            if ch is None or not off or ch.pose.origin_id != r.pose.origin_id:
                return False
            if time.time() - (ch.last_observed_time or 0) > 3:
                return False
            cx, cy, cth = ch.pose.position.x, ch.pose.position.y, ch.pose.rotation.angle_z.radians
            c, s = math.cos(cth), math.sin(cth)
            self.anchor = (r.pose.origin_id, cx + c * off[0] - s * off[1], cy + s * off[0] + c * off[1],
                           wrap(cth + off[2]))
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------ cells
    @staticmethod
    def cell(x: float, y: float):
        i, j = int(math.floor(x / CELL)) + HALF, int(math.floor(y / CELL)) + HALF
        return (i, j) if 0 <= i < N and 0 <= j < N else None

    @staticmethod
    def centre(i: int, j: int):
        return ((i - HALF + 0.5) * CELL, (j - HALF + 0.5) * CELL)

    def _set_floor(self, x, y, v, force=False):
        c = self.cell(x, y)
        if c:
            k = c[1] * N + c[0]
            if force or self.floor[k] != EDGE or v == EDGE:
                if self.floor[k] != v:
                    self.floor[k] = v
                    self.dirty = True

    def _obst(self, k, delta):
        v = max(0, min(12, self.obst[k] + delta))
        if v != self.obst[k]:
            self.obst[k] = v
            self.dirty = True

    def mark_floor(self, x, y, rad=24):
        with self.lock:
            for dx in range(-rad, rad + 1, CELL // 2):
                for dy in range(-rad, rad + 1, CELL // 2):
                    if dx * dx + dy * dy <= rad * rad:
                        self._set_floor(x + dx, y + dy, FLOOR, force=(dx == 0 and dy == 0))
            c = self.cell(x, y)
            if c:  # he's sitting on it: nothing solid there
                self._obst(c[1] * N + c[0], -12)

    def mark_path(self, x0, y0, x1, y1):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / (CELL / 2)))
        for t in range(n + 1):
            self.mark_floor(x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n)

    def _ahead(self, x, y, th, d0, d1, half_w):
        c, s = math.cos(th), math.sin(th)
        out = set()
        for d in range(int(d0), int(d1) + 1, CELL // 2):
            for w in range(-half_w, half_w + 1, CELL // 2):
                cc = self.cell(x + c * d - s * w, y + s * d + c * w)
                if cc:
                    out.add(cc)
        return out

    def mark_edge(self, x, y, th):
        """His edge sensors fired: the desk ends just past his front."""
        with self.lock:
            for i, j in self._ahead(x, y, th, FRONT + 5, FRONT + 45, 40):
                self._set_floor(*self.centre(i, j), EDGE)

    def mark_prox(self, x, y, th, found: bool, dist: float):
        with self.lock:
            reach = min(dist if found else PROX_MAX, PROX_MAX)
            hit = self._ahead(x, y, th, FRONT + reach, FRONT + reach + 30, 20) if found and dist <= PROX_MAX else set()
            for i, j in self._ahead(x, y, th, FRONT + 10, FRONT + reach - 25, 0) - hit:
                self._obst(j * N + i, -1)
            for i, j in hit:
                self._obst(j * N + i, +3)

    def mark_block(self, x, y, th):
        """He pushed and didn't move: something low (a cable, the mat's edge with his lift down...)."""
        with self.lock:
            for i, j in self._ahead(x, y, th, FRONT + 5, FRONT + 35, 30):
                self._obst(j * N + i, +6)

    def fill_triangle(self, a, b, c):
        with self.lock:
            xs, ys = (a[0], b[0], c[0]), (a[1], b[1], c[1])
            lo, hi = self.cell(min(xs), min(ys)), self.cell(max(xs), max(ys))
            if not lo or not hi:
                return

            def side(p, q, r):
                return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
            for i in range(lo[0], hi[0] + 1):
                for j in range(lo[1], hi[1] + 1):
                    p = self.centre(i, j)
                    d1, d2, d3 = side(a, b, p), side(b, c, p), side(c, a, p)
                    if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
                        k = j * N + i
                        if self.floor[k] == UNKNOWN:
                            self.floor[k] = FLOOR
                            self.dirty = True

    def close_holes(self):
        """Single unknown cells surrounded by floor (gaps between driven lines) are floor."""
        with self.lock:
            i0, j0, i1, j1 = self._bbox(pad=1)
            fill = []
            for j in range(max(1, j0), min(N - 1, j1)):
                for i in range(max(1, i0), min(N - 1, i1)):
                    if self.floor[j * N + i] != UNKNOWN:
                        continue
                    n = sum(self.floor[(j + dj) * N + i + di] == FLOOR for di in (-1, 0, 1) for dj in (-1, 0, 1))
                    if n >= 6:
                        fill.append(j * N + i)
            for k in fill:
                self.floor[k] = FLOOR
            if fill:
                self.dirty = True

    # ------------------------------------------------------------ zones
    def zone_cells(self):
        out = set()
        rects = [DOCK_ZONE] + [(z["x0"], z["y0"], z["x1"], z["y1"]) for z in self.zones
                               if z.get("kind") == "keepout" or (z.get("kind") == "sometimes" and z.get("present", True))]
        for x0, y0, x1, y1 in rects:
            lo, hi = self.cell(min(x0, x1), min(y0, y1)), self.cell(max(x0, x1), max(y0, y1))
            if lo and hi:
                for i in range(lo[0], hi[0] + 1):
                    for j in range(lo[1], hi[1] + 1):
                        out.add((i, j))
        return out

    def add_zone(self, z: dict) -> dict:
        with self.lock:
            z = {"id": z.get("id") or f"z{int(time.time() * 1000) % 10**9}", "name": str(z.get("name", "Zone"))[:40],
                 "kind": "sometimes" if z.get("kind") == "sometimes" else "keepout", "present": bool(z.get("present", True)),
                 **{k: float(z[k]) for k in ("x0", "y0", "x1", "y1")}}
            self.zones = [o for o in self.zones if o["id"] != z["id"]] + [z]
            self.save()
            return z

    def remove_zone(self, zid: str):
        with self.lock:
            self.zones = [o for o in self.zones if o["id"] != zid]
            self.save()

    def set_present(self, word: str, present: bool) -> int:
        n = 0
        with self.lock:
            for z in self.zones:
                if z.get("kind") == "sometimes" and word.lower() in z.get("name", "").lower():
                    z["present"] = present
                    n += 1
            self.save()
        return n

    # ------------------------------------------------------------ planning
    def _bbox(self, pad=8):
        idx = [k for k in range(N * N) if self.floor[k] or self.obst[k] >= OBST]
        if not idx:
            return (HALF - pad, HALF - pad, HALF + pad, HALF + pad)
        ii = [k % N for k in idx]
        jj = [k // N for k in idx]
        return (max(0, min(ii) - pad), max(0, min(jj) - pad), min(N - 1, max(ii) + pad), min(N - 1, max(jj) + pad))

    def clearance(self, unknown_bad=True, box=None):
        """mm from each cell to the nearest edge / obstacle / zone (/ unknown), inside box."""
        i0, j0, i1, j1 = box or self._bbox()
        zc = self.zone_cells()
        W, H = i1 - i0 + 1, j1 - j0 + 1
        dist = [None] * (W * H)
        q = deque()
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                k = j * N + i
                f = self.floor[k]
                bad = (f == EDGE or self.obst[k] >= OBST or (i, j) in zc or (unknown_bad and f == UNKNOWN)
                       or i in (i0, i1) or j in (j0, j1))
                if bad:
                    dist[(j - j0) * W + (i - i0)] = 0
                    q.append((i, j))
        while q:
            i, j = q.popleft()
            d = dist[(j - j0) * W + (i - i0)]
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if i0 <= a <= i1 and j0 <= b <= j1 and dist[(b - j0) * W + (a - i0)] is None:
                        dist[(b - j0) * W + (a - i0)] = d + 1
                        q.append((a, b))
        box = (i0, j0, i1, j1)
        return lambda i, j: (dist[(j - j0) * W + (i - i0)] * CELL if i0 <= i <= i1 and j0 <= j <= j1 else 0), box

    def plan(self, start, goal, clear=ROAM_CLEAR, unknown_bad=True):
        """Waypoints (mm) from start to goal through cells at least `clear` mm from anything bad."""
        with self.lock:
            cl, box = self.clearance(unknown_bad)
            s, g = self.cell(*start[:2]), self.cell(*goal[:2])
            if not s or not g:
                return None
            sx, sy = self.centre(*s)

            def ok(c):  # near where he is, a bit less room is fine (he has to get out of a tight spot)
                near = math.hypot(self.centre(*c)[0] - sx, self.centre(*c)[1] - sy) < 120
                return cl(*c) >= (min(clear, 40) if near else clear)
            if not ok(g):
                return None
            openq = [(0.0, s)]
            came, cost = {s: None}, {s: 0.0}
            while openq:
                _, c = heapq.heappop(openq)
                if c == g:
                    break
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        if not (di or dj):
                            continue
                        nb = (c[0] + di, c[1] + dj)
                        if not (box[0] <= nb[0] <= box[2] and box[1] <= nb[1] <= box[3]) or not ok(nb):
                            continue
                        # prefer the middle of open space, not hugging the limit
                        step = (1.414 if di and dj else 1.0) + max(0.0, (clear + 60 - cl(*nb)) / 120)
                        nc = cost[c] + step
                        if nc < cost.get(nb, 1e18):
                            cost[nb], came[nb] = nc, c
                            heapq.heappush(openq, (nc + math.hypot(g[0] - nb[0], g[1] - nb[1]), nb))
            if g not in came:
                return None
            cells = []
            c = g
            while c:
                cells.append(c)
                c = came[c]
            cells.reverse()
            # keep only the corners: straight lines between points that can see each other
            pts, k = [cells[0]], 0
            while k < len(cells) - 1:
                far = k + 1
                for m in range(len(cells) - 1, k, -1):
                    if self._visible(cells[k], cells[m], ok):
                        far = m
                        break
                pts.append(cells[far])
                k = far
            way = [self.centre(*c) for c in pts[1:]]
            if way:
                way[-1] = tuple(goal[:2])
            return way

    @staticmethod
    def _visible(a, b, ok):
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2
        for t in range(n + 1):
            c = (round(a[0] + (b[0] - a[0]) * t / max(n, 1)), round(a[1] + (b[1] - a[1]) * t / max(n, 1)))
            if not ok(c):
                return False
        return True

    def reachable(self, start, clear=ROAM_CLEAR):
        with self.lock:
            cl, box = self.clearance(True)
            s = self.cell(*start[:2])
            if not s:
                return [], cl
            sx, sy = self.centre(*s)
            seen, q = {s}, deque([s])
            while q:
                i, j = q.popleft()
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        nb = (i + di, j + dj)
                        if nb in seen or not (box[0] <= nb[0] <= box[2] and box[1] <= nb[1] <= box[3]):
                            continue
                        x, y = self.centre(*nb)
                        if cl(*nb) >= (min(clear, 40) if math.hypot(x - sx, y - sy) < 120 else clear):
                            seen.add(nb)
                            q.append(nb)
            return [c for c in seen if cl(*c) >= clear], cl

    def random_goal(self, start, rng=random, clear=ROAM_CLEAR + 20, min_dist=200):
        cells, cl = self.reachable(start)
        cand = [c for c in cells if cl(*c) >= clear
                and math.hypot(self.centre(*c)[0] - start[0], self.centre(*c)[1] - start[1]) >= min_dist]
        return self.centre(*rng.choice(cand)) if cand else None

    def frontier(self, clear=70):
        """Unknown cells next to floor, not near an edge or obstacle: where the map can still grow."""
        with self.lock:
            cl, box = self.clearance(False)
            zc = self.zone_cells()
            out = []
            for j in range(box[1] + 1, box[3]):
                for i in range(box[0] + 1, box[2]):
                    if self.floor[j * N + i] != UNKNOWN or (i, j) in zc or cl(i, j) < clear:
                        continue
                    if any(self.floor[(j + dj) * N + i + di] == FLOOR for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                        out.append((i, j))
            return out

    @staticmethod
    def clusters(cells):
        left, out = set(cells), []
        while left:
            s = left.pop()
            grp, q = [s], deque([s])
            while q:
                i, j = q.popleft()
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        nb = (i + di, j + dj)
                        if nb in left:
                            left.remove(nb)
                            grp.append(nb)
                            q.append(nb)
            out.append(grp)
        return sorted(out, key=len, reverse=True)

    # ------------------------------------------------------------ live safety
    def danger(self, x, y, th, look=110):
        """Is there an edge, a keep-out zone or something that's always there just ahead of him? (Things
        seen only a few times, like his cube, don't count: he's allowed to play with those.)"""
        zc = self.zone_cells() - self.zone_cells_dock()
        for i, j in self._ahead(x, y, th, FRONT, FRONT + look, 30):
            k = j * N + i
            if self.floor[k] == EDGE:
                return "edge"
            if self.obst[k] >= 8:
                return "obstacle"
            if (i, j) in zc:
                return "zone"
        return None

    def ahead_marked(self, x, y, th, look):
        """Anything known in the strip his body will sweep: marked areas, edges, obstacles seen before
        (the distance sensor only looks straight ahead, so this is what stops side-swipes)."""
        zc = self.zone_cells() - self.zone_cells_dock()
        for i, j in self._ahead(x, y, th, FRONT - 10, FRONT + look, 38):
            k = j * N + i
            if (i, j) in zc or self.floor[k] == EDGE or self.obst[k] >= OBST:
                return True
        return False

    def zone_cells_dock(self):
        x0, y0, x1, y1 = DOCK_ZONE
        lo, hi = self.cell(x0, y0), self.cell(x1, y1)
        return {(i, j) for i in range(lo[0], hi[0] + 1) for j in range(lo[1], hi[1] + 1)}

    def blocks(self, kind: str, limit=30):
        """The map as boxes (desk mm), for telling his own planner where things are."""
        out = []
        with self.lock:
            buckets: dict = {}
            for k in range(N * N):
                hit = self.floor[k] == EDGE if kind == "edge" else self.obst[k] >= 4
                if hit:
                    i, j = k % N, k // N
                    buckets.setdefault((i // 8, j // 8), []).append((i, j))
            for cells in buckets.values():
                if len(cells) < 2:
                    continue
                ii, jj = [c[0] for c in cells], [c[1] for c in cells]
                x0, y0 = self.centre(min(ii), min(jj))
                x1, y1 = self.centre(max(ii), max(jj))
                out.append((x0 - CELL / 2, y0 - CELL / 2, x1 + CELL / 2, y1 + CELL / 2))
        return out[:limit]

    # ------------------------------------------------------------ for the app
    def summary(self) -> dict:
        with self.lock:
            floor = sum(1 for v in self.floor if v == FLOOR)
            obst = [(k % N, k // N) for k in range(N * N) if self.obst[k] >= OBST]
            edges = sum(1 for v in self.floor if v == EDGE)
            return {"area_m2": round(floor * CELL * CELL / 1e6, 2), "obstacles": len([c for c in self.clusters(obst) if len(c) >= 2]),
                    "edge_cm": round(edges * CELL / 10 / 2), "scanned_at": self.scanned_at, "drift_mm": self.drift_mm}

    def view(self, r=None) -> dict:
        with self.lock:
            i0, j0, i1, j1 = self._bbox(pad=6)
            W, H = i1 - i0 + 1, j1 - j0 + 1
            cells = bytearray(W * H)
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    k = j * N + i
                    cells[(j - j0) * W + (i - i0)] = 3 if self.obst[k] >= OBST and self.floor[k] != EDGE else self.floor[k]
            pose = self.where(r) if r is not None else None
            return {"cell": CELL, "x0": (i0 - HALF) * CELL, "y0": (j0 - HALF) * CELL, "w": W, "h": H,
                    "cells": base64.b64encode(bytes(cells)).decode(), "zones": self.zones, "dock": DOCK_ZONE,
                    "pose": [round(pose[0]), round(pose[1]), round(math.degrees(pose[2]))] if pose else None,
                    "anchored": bool(pose), "progress": self.progress, **self.summary()}


# ---------------------------------------------------------------- driving on the map
class Driver:
    """Slow, checked driving: distance sensor before every hop, edges and bumps go on the map.

    His own reflexes (the edge reaction, the 'bumped into something' reaction) outrank us: they take over,
    back him up fast and blind, and that's what made him speed up and hit things. So: approach slowly (so
    they rarely fire), notice when one has fired, wait it out, take control back and mark the spot, and
    never add a blind reverse of our own on top. Low lips (the desk mat) get a real climbing attempt.
    """

    def __init__(self, m: Map, r, call, cancel: threading.Event, log=print, control_ok=None, regain=None):
        self.m, self.r, self.call, self.cancel, self.log = m, r, call, cancel, log
        self.control_ok, self.regain = control_ok, regain
        self.reach = None

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("stopped")
        st = self.r.status
        if st.is_picked_up or getattr(st, "is_being_held", False):
            raise Lost("picked up")

    def pose(self):
        self.check()
        p = self.m.where(self.r)
        if p is None:
            raise Lost("lost track of where the dock is")
        return p

    def look(self, samples: int = 1):
        """Distance sensor: the nearest of a few readings (one stale reading once let him drive into things)."""
        found, dist = False, PROX_MAX + 1.0
        got = False
        for i in range(samples):
            if i:
                time.sleep(0.08)
            try:
                p = self.r.proximity.last_sensor_reading
                if p is None or getattr(p, "is_lift_in_fov", False):
                    continue
                got = True
                if p.found_object and p.distance.distance_mm < dist:
                    found, dist = True, float(p.distance.distance_mm)
            except Exception:  # noqa: BLE001
                continue
        if not got:
            return None
        x, y, th = self.pose()
        self.m.mark_prox(x, y, th, found, dist if found else PROX_MAX)
        return found, (dist if found else PROX_MAX)

    def act(self, fn, timeout: float, name: str, done=None) -> bool:
        """Run one command; if its reply is slow (his Wi-Fi), check whether it actually happened instead of
        giving up ('that took too long' while his arms were already up)."""
        try:
            self.call(fn, timeout, name)
            return True
        except Exception as e:  # noqa: BLE001
            if done is None:
                raise
            t0 = time.time()
            while time.time() - t0 < timeout:
                try:
                    if done():
                        self.log(f"deskmap: {name} replied late but it happened")
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.2)
            self.log(f"deskmap: {name} didn't happen ({e.__class__.__name__})")
            return False

    def lift(self, h: float) -> bool:
        target = 32 + 60 * h  # mm, roughly: 0 = down, 1 = fully up
        return self.act(lambda: self.r.behavior.set_lift_height(h), 8, "set_lift_height",
                        lambda: abs(self.r.lift_height_mm - target) < 10)

    def stop(self):
        for _ in range(2):
            try:
                self.call(lambda: self.r.motors.set_wheel_motors(0, 0), 3, "set_wheel_motors")
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.2)

    def leg(self, mm: float, speed: float) -> str:
        """Drive forward continuously, watching the sensors at 20 Hz on this side, the way a robot vacuum
        does (one start + one stop command instead of a round trip per few centimetres). Ends: ok / edge /
        blocked / stuck / reflex."""
        r = self.r
        x0, y0, _ = self.pose()
        try:
            self.call(lambda: r.motors.set_wheel_motors(speed, speed), 4, "set_wheel_motors")
        except Exception:  # noqa: BLE001
            self.stop()
            return "stuck"
        t0 = last_move = time.time()
        lastp, out = (x0, y0), "ok"
        try:
            while True:
                time.sleep(0.05)
                if self.cancel.is_set():
                    out = "cancel"
                    break
                st = r.status
                if st.is_picked_up or getattr(st, "is_being_held", False):
                    out = "lifted"
                    break
                if st.is_cliff_detected:
                    out = "edge"
                    break
                if self.control_ok is not None and not self.control_ok():
                    out = "reflex"
                    break
                try:
                    p = r.proximity.last_sensor_reading
                    if p is not None and not p.is_lift_in_fov and p.found_object and p.distance.distance_mm < 95:
                        out = "blocked"
                        break
                except Exception:  # noqa: BLE001
                    pass
                w = self.m.where(r)
                if w is None:
                    out = "lifted"
                    break
                x, y = w[0], w[1]
                if math.hypot(x - x0, y - y0) >= mm - 4:
                    break
                now = time.time()
                if math.hypot(x - lastp[0], y - lastp[1]) > 3:
                    lastp, last_move = (x, y), now
                elif now - last_move > 1.2 and now - t0 > 1.2:
                    out = "stuck"
                    break
                if now - t0 > 2 + 2.5 * mm / speed:
                    out = "stuck"
                    break
        finally:
            self.stop()
        if out == "cancel":
            raise InterruptedError("stopped")
        if out == "lifted":
            raise Lost("picked up")
        return out

    def reflex(self) -> bool:
        """Did one of his own reactions just take control? If so, let it finish and take control back."""
        if self.control_ok is None or self.control_ok():
            return False
        self.log("deskmap: his own reflex took over (edge or bump reaction); waiting it out")
        time.sleep(2.5)
        try:
            if self.regain:
                self.regain()
        except Exception as e:  # noqa: BLE001
            self.log(f"deskmap: couldn't take control back ({e.__class__.__name__})")
        return True

    def room_around(self, rad=56) -> bool:
        """Is there room to turn in place? (His corners sweep about 5 cm out.)"""
        x, y, _ = self.pose()
        with self.m.lock:
            for dx in range(-rad, rad + 1, CELL // 2):
                for dy in range(-rad, rad + 1, CELL // 2):
                    if dx * dx + dy * dy > rad * rad:
                        continue
                    c = self.m.cell(x + dx, y + dy)
                    if not c or dx * dx + dy * dy <= 30 * 30:  # not the cell he's on
                        continue
                    k = c[1] * N + c[0]
                    # things get hit by his corners (6 cm out); an edge only matters closer (overhang is fine)
                    if self.m.obst[k] >= OBST + 2 or (self.m.floor[k] == EDGE and dx * dx + dy * dy < 42 * 42):
                        return False
        return True

    def turn_to(self, heading) -> bool:
        from anki_vector.util import degrees
        _, _, th = self.pose()
        d = wrap(heading - th)
        if abs(d) > math.radians(4):
            if abs(d) > math.radians(35) and not self.room_around():
                self.back(50)
                if not self.room_around():
                    self.log("deskmap: too cramped to turn here")
                    return False
            def turned():
                w = self.m.where(self.r)
                return w is not None and abs(wrap(heading - w[2])) < math.radians(8)
            self.act(lambda: self.r.behavior.turn_in_place(degrees(math.degrees(d)), speed=degrees(70)), 12,
                     "turn_in_place", turned)
            if self.reflex():
                return False
            if not turned():
                return False
        time.sleep(0.3)  # fresh distance readings for the new direction
        return True

    def hop(self, mm: float, speed: float = 45) -> str:
        """One short forward move. Returns ok / edge / blocked / stuck."""
        from anki_vector.util import distance_mm, speed_mmps
        x0, y0, th = self.pose()
        seen = self.look(samples=3)
        if seen is None:  # the distance sensor is blocked (lift sagging into its view): never drive blind
            self.lift(1.0)
            time.sleep(0.3)
            seen = self.look(samples=3)
            if seen is None:
                self.log("deskmap: distance sensor unusable, not moving")
                return "blocked"
        if seen[0] and seen[1] < mm + 90:
            return "blocked"
        if self.m.ahead_marked(x0, y0, th, mm + 50):  # a keep-out area you marked, or a known edge
            return "blocked"
        if self.r.status.is_cliff_detected:
            self.m.mark_edge(x0, y0, th)
            return "edge"
        res = self.leg(mm, speed)
        x1, y1, _ = self.pose()
        self.reach = (x1, y1)
        self.m.mark_path(x0, y0, x1, y1)
        if res == "reflex" or self.reflex():  # his edge/bump reaction already backed him off: no reverse of ours
            self.reflex()
            self.m.mark_edge(x1, y1, th)
            return "edge"
        if res == "edge" or self.r.status.is_cliff_detected:
            self.m.mark_edge(x1, y1, th)
            self.back(40)
            return "edge"
        if res == "blocked":
            self.look()
            return "blocked"
        if res == "stuck" or math.hypot(x1 - x0, y1 - y0) < 0.35 * mm:
            # pushing and not moving, with nothing in front for the sensor: a low lip (the mat's edge, a cable)
            if not (seen[0] and seen[1] < 200) and self.climb():
                return "ok"
            self.m.mark_block(*self.pose())
            self.back(25)
            return "stuck"
        self.look()
        return "ok"

    def climb(self) -> bool:
        """Get over a low lip: arms up and a firmer push; then push down with the arms to lift his front."""
        from anki_vector.util import distance_mm, speed_mmps
        r = self.r
        for attempt in (1, 2):
            x0, y0, _ = self.pose()
            try:
                self.lift(1.0)
                if attempt == 1:
                    self.leg(50, 75)
                else:  # arms down against the desk: tilts his front up onto the lip while the treads push
                    self.back(15)
                    self.call(lambda: r.motors.set_lift_motor(-4), 3, "set_lift_motor")
                    self.call(lambda: r.motors.set_wheel_motors(55, 55), 3, "set_wheel_motors")
                    time.sleep(1.2)
                    self.call(lambda: r.motors.set_wheel_motors(0, 0), 3, "set_wheel_motors")
                    self.call(lambda: r.motors.set_lift_motor(0), 3, "set_lift_motor")
                    self.lift(1.0)
            except (Lost, InterruptedError):
                raise
            except Exception as e:  # noqa: BLE001
                self.log(f"deskmap: climb attempt {attempt} interrupted ({e.__class__.__name__})")
            if self.reflex() or self.r.status.is_cliff_detected:
                return False
            x1, y1, _ = self.pose()
            if math.hypot(x1 - x0, y1 - y0) > 30:
                self.log(f"deskmap: climbed over a low edge (attempt {attempt})")
                self.m.mark_path(x0, y0, x1, y1)
                return True
        self.log("deskmap: couldn't get over a low edge")
        return False

    def back(self, mm: float) -> float:
        """Reverse only over floor he has just driven (no sensor at the back), and never far."""
        from anki_vector.util import distance_mm, speed_mmps
        x0, y0, th = self.pose()
        ok_mm = 0
        for d in range(10, int(min(mm, 50)) + 1, 10):
            cells = self.m._ahead(x0, y0, th + math.pi, FRONT - 5 + d - 10, FRONT - 5 + d, 10)
            if any(self.m.floor[j * N + i] != FLOOR or self.m.obst[j * N + i] >= OBST for i, j in cells):
                break
            ok_mm = d
        if ok_mm < 10:
            return 0.0
        try:
            self.call(lambda: self.r.behavior.drive_straight(distance_mm(-ok_mm), speed_mmps(40), should_play_anim=False),
                      10 + 2 * ok_mm / 40, "drive_straight")
        except Exception:  # noqa: BLE001
            pass
        self.reflex()
        x1, y1, _ = self.pose()
        self.m.mark_path(x0, y0, x1, y1)
        return ok_mm

    def follow(self, way, hop=90) -> bool:
        for wx, wy in way:
            while True:
                x, y, _ = self.pose()
                d = math.hypot(wx - x, wy - y)
                if d < 25:
                    break
                if not self.turn_to(math.atan2(wy - y, wx - x)):
                    return False
                if self.hop(min(d, hop), speed=60) != "ok":
                    return False
        return True


def _bearings(m: Map, centre, step_deg=22.5, dock_avoid=40):
    """Directions from centre that point into unknown desk (and not back at the dock)."""
    out = []
    for k in range(int(360 / step_deg)):
        b = math.radians(k * step_deg)
        to_dock = math.atan2(-centre[1], -centre[0])
        if math.hypot(*centre) < 400 and abs(wrap(b - to_dock)) < math.radians(dock_avoid):
            continue
        unknown = 0
        for d in (120, 220, 320):
            c = m.cell(centre[0] + math.cos(b) * d, centre[1] + math.sin(b) * d)
            if c and m.floor[c[1] * N + c[0]] == UNKNOWN:
                unknown += 1
        if unknown >= 2:
            out.append(b)
    return out


def fan(m: Map, d: Driver, centre, bearings, deadline, max_ray=1500):
    """Drive out along each bearing until something stops him, come back, fill between the lines."""
    rays = []
    fails = 0
    for b in sorted(bearings, key=lambda b: wrap(b)):
        if time.time() > deadline or fails >= 3:
            break
        try:
            if not d.turn_to(b):
                continue
            start = d.pose()[:2]
            d.reach, why = start, "max"
            while math.hypot(d.reach[0] - start[0], d.reach[1] - start[1]) < max_ray:
                seen = d.look()
                far = not seen or not seen[0] or seen[1] > 250
                why = d.hop(70 if far else 40, speed=50 if far else 35)
                if why != "ok":
                    break
            reach = d.reach
            rays.append((wrap(b), reach, why))
            x, y, _ = d.pose()
            if math.hypot(x - start[0], y - start[1]) > 25:
                d.follow([start])  # turn round and drive back forward, sensor first (no long blind reverse)
            fails = 0
        except (Lost, InterruptedError):
            raise
        except Exception as e:  # noqa: BLE001  (a slow reply on his Wi-Fi: skip this line, don't end the scan)
            fails += 1
            d.log(f"deskmap: a line was cut short ({e.__class__.__name__}); carrying on")
            d.stop()
            time.sleep(1.0)
    rays.sort(key=lambda t: t[0])
    for (b1, p1, w1), (b2, p2, w2) in zip(rays, rays[1:] + rays[:1]):
        gap = wrap(b2 - b1) % (2 * math.pi)
        if gap > math.radians(30):
            continue
        l1, l2 = math.hypot(p1[0] - centre[0], p1[1] - centre[1]), math.hypot(p2[0] - centre[0], p2[1] - centre[1])
        if min(l1, l2) < 60:
            continue
        # when a line stopped at an obstacle, don't assume the floor beyond it on the other line
        if w1 in ("blocked", "stuck") and l2 > l1:
            p2 = (centre[0] + (p2[0] - centre[0]) * l1 / l2, centre[1] + (p2[1] - centre[1]) * l1 / l2)
        elif w2 in ("blocked", "stuck") and l1 > l2:
            p1 = (centre[0] + (p1[0] - centre[0]) * l2 / l1, centre[1] + (p1[1] - centre[1]) * l2 / l1)
        m.fill_triangle(centre, p1, p2)
    m.close_holes()
    return rays


def prep_dock(r, call, log=print):
    """He can't back onto the charger holding the cube or with his arms up: put it down, arms down,
    head level (he finds the charger by its marker)."""
    from anki_vector.util import degrees
    try:
        if getattr(r.status, "is_carrying_block", False):
            log("deskmap: putting the cube down before docking")
            call(lambda: r.behavior.place_object_on_ground_here(num_retries=1), 30, "place_object_on_ground_here")
    except Exception as e:  # noqa: BLE001
        log(f"deskmap: couldn't put the cube down ({e.__class__.__name__})")
    for fn, name in ((lambda: r.behavior.set_lift_height(0.0), "set_lift_height"),
                     (lambda: r.behavior.set_head_angle(degrees(0)), "set_head_angle")):
        try:
            call(fn, 8, name)
        except Exception:  # noqa: BLE001
            pass


def go_home(m: Map, d: Driver, r, call, log=print) -> bool:
    """Back to a spot in front of the dock, facing it, then let him reverse on. Re-anchors the map."""
    try:
        x, y, _ = d.pose()
        m.close_holes()
        way = m.plan((x, y), (170, 0), clear=60) or m.plan((x, y), (170, 0), clear=40)
        if way:
            d.follow(way)
        d.turn_to(math.pi)
    except (Lost, InterruptedError):
        raise
    except Exception as e:  # noqa: BLE001
        log(f"deskmap: couldn't line up with the dock ({e})")
    before = m.where(r)
    prep_dock(r, call, log)
    if not d.act(lambda: r.behavior.drive_on_charger(), 120, "drive_on_charger", lambda: r.status.is_on_charger):
        log("deskmap: docking failed")
    time.sleep(1.0)
    if r.status.is_on_charger:
        now = m.where(r)
        if now is not None:
            m.drift_mm = round(math.hypot(now[0], now[1]))
            log(f"deskmap: back on the dock; odometry drift {m.drift_mm} mm (from {before})")
        m.set_anchor(Map.odom(r))
        m.remember_charger(r)
        return True
    return False


def scan(m: Map, r, call, cancel, say=print, log=print, minutes: float = 10, control=(None, None)) -> dict:
    """The full desk scan. He starts and ends on the dock."""
    from anki_vector.util import degrees
    deadline = time.time() + minutes * 60
    if not r.status.is_on_charger:
        call(lambda: r.behavior.drive_on_charger(), 120, "drive_on_charger")
        time.sleep(1.0)
        if not r.status.is_on_charger:
            raise RuntimeError("Put me on my charger first, so the map starts from there.")
    with m.lock:
        m.clear_layers()
        m.set_anchor(Map.odom(r))
        m.remember_charger(r)
    d = Driver(m, r, call, cancel, log, *control)
    m.progress = {"what": "scanning", "step": "leaving the dock", "started": time.time()}
    # lift fully up: it clears the mat's edge and stays out of the distance sensor's view
    d.lift(1.0)
    d.act(lambda: r.behavior.set_head_angle(degrees(-5)), 8, "set_head_angle", lambda: True)
    if not d.act(lambda: r.behavior.drive_off_charger(), 30, "drive_off_charger", lambda: not r.status.is_on_charger):
        raise RuntimeError("couldn't get off the charger")
    x, y, _ = d.pose()
    m.mark_path(0, 0, x, y)
    centres = [(x, y)]
    m.progress["step"] = "first fan"
    fan(m, d, (x, y), _bearings(m, (x, y)), deadline)
    tried = set()
    while time.time() < deadline - 45 and len(centres) < 9:
        groups = [g for g in m.clusters(m.frontier(clear=50)) if len(g) >= 6 and g[0] not in tried]
        if not groups:
            break
        g = groups[0]
        tried.add(g[0])
        gx = sum(m.centre(*c)[0] for c in g) / len(g)
        gy = sum(m.centre(*c)[1] for c in g) / len(g)
        cur = d.pose()
        cells, cl = m.reachable(cur, clear=80)
        far_from_old = [c for c in cells if all(math.hypot(m.centre(*c)[0] - a, m.centre(*c)[1] - b) > 120 for a, b in centres)]
        if not far_from_old:
            continue
        best = min(far_from_old, key=lambda c: math.hypot(m.centre(*c)[0] - gx, m.centre(*c)[1] - gy))
        spot = m.centre(*best)
        way = m.plan(cur, spot, clear=80)
        m.progress["step"] = f"spot {len(centres) + 1}"
        try:
            if not way or not d.follow(way):
                continue
        except (Lost, InterruptedError):
            raise
        except Exception as e:  # noqa: BLE001
            d.log(f"deskmap: moving to the next spot was cut short ({e.__class__.__name__})")
            d.stop()
            continue
        here = d.pose()[:2]
        centres.append(here)
        fan(m, d, here, _bearings(m, here), deadline)
        m.save()
    m.progress["step"] = "going home"
    docked = go_home(m, d, r, call, log)
    m.scanned_at = time.time()
    m.progress = None
    m.save()
    out = {**m.summary(), "docked": docked, "spots": len(centres)}
    log(f"deskmap: scan done {out}")
    return out


def roam(m: Map, r, call, cancel, log=print, minutes: float = 3, pause=None, control=(None, None)) -> dict:
    """Wander the mapped desk: random safe spots, planned paths, back to the dock at the end."""
    from anki_vector.util import degrees
    if not m.scanned:
        raise RuntimeError("I haven't mapped the desk yet. Say: scan the desk.")
    if r.status.is_on_charger:
        m.set_anchor(Map.odom(r))
        m.remember_charger(r)
    elif not m.anchored(r) and not m.anchor_from_charger(r):
        raise RuntimeError("I don't know where I am on the desk. Put me on my charger and ask again.")
    d = Driver(m, r, call, cancel, log, *control)
    deadline = time.time() + minutes * 60
    m.progress = {"what": "roaming", "step": "leaving the dock", "started": time.time()}
    d.lift(1.0)
    d.act(lambda: r.behavior.set_head_angle(degrees(5)), 8, "set_head_angle", lambda: True)
    if r.status.is_on_charger:
        if not d.act(lambda: r.behavior.drive_off_charger(), 30, "drive_off_charger", lambda: not r.status.is_on_charger):
            raise RuntimeError("couldn't get off the charger")
        x, y, _ = d.pose()
        m.mark_path(0, 0, x, y)
    visits, fails = 0, 0
    try:
        while time.time() < deadline and fails < 6:
            cur = d.pose()
            goal = m.random_goal(cur)
            way = goal and m.plan(cur, goal)
            if not way:
                fails += 1
                continue
            m.progress["step"] = f"spot {visits + 1}"
            try:
                ok = d.follow(way)
            except (Lost, InterruptedError):
                raise
            except Exception as e:  # noqa: BLE001
                d.log(f"deskmap: a move was cut short ({e.__class__.__name__})")
                d.stop()
                ok = False
            if ok:
                visits += 1
                fails = 0
                if pause:
                    pause()
            else:
                fails += 1
    finally:
        m.progress = {"what": "roaming", "step": "going home", "started": time.time()}
        try:
            docked = go_home(m, d, r, call, log)
        finally:
            m.progress = None
            m.save()
    return {"visits": visits, "docked": docked}


_MAP = None


def get() -> Map:
    global _MAP
    if _MAP is None:
        _MAP = Map()
    return _MAP
