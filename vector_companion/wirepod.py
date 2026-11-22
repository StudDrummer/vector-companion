"""Tiny, dependency-free client for wire-pod's HTTP API (port 8080 by default).

wire-pod exposes a REST bridge to Vector at /api-sdk/<action>?serial=<ESN>&...
This wraps the routes so the brain, the MCP server and your own scripts
can all drive Vector the same way.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager

DEFAULT_URL = os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080")

# wire-pod eye color presets (same order as the Vector app)
EYE_COLORS = {
    "teal": 0, "orange": 1, "yellow": 2, "lime": 3,
    "blue": 4, "purple": 5, "green": 6,
}

# Cloud intents wire-pod can fire on the robot (subset that is fun/useful)
INTENTS = {
    "dance": "intent_imperative_dance",
    "sleep": "intent_system_sleep",
    "go_to_charger": "intent_system_charger",
    "fetch_cube": "intent_imperative_fetchcube",
    "explore": "explore_start",
    "come_here": "intent_imperative_come",
    "look_at_me": "intent_imperative_lookatme",
    "take_photo": "intent_photo_take_extend",
    "roll_cube": "intent_play_rollcube",
    "blackjack": "intent_play_blackjack",
    "pop_a_wheelie": "intent_play_popawheelie",
    "be_quiet": "intent_imperative_shutup",
}  # any raw intent_* string also passes straight through


class WirePodError(RuntimeError):
    pass


class Vector:
    def __init__(self, serial: str | None = None, url: str = DEFAULT_URL, timeout: float = 15):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.serial = serial or os.environ.get("VECTOR_SERIAL") or self.discover_serial()

    # ---------- plumbing ----------
    # built-in behaviors that can't run while the companion keeps him still on the dock
    NEEDS_BEHAVIORS = {"cloud_intent": 45, "add_face": 60, "trigger_wake_word": 20}

    def _req(self, action: str, method: str = "POST", **params) -> str:
        if action in self.NEEDS_BEHAVIORS:
            try:  # let go of the "keep still" hold for a bit so the behavior can run
                from .companion_client import call
                call("/still", {"pause": self.NEEDS_BEHAVIORS[action]}, timeout=6)
            except Exception:  # noqa: BLE001  (companion not running: nothing to release)
                pass
        q = {"serial": self.serial or "", **{k: str(v) for k, v in params.items()}}
        full = f"{self.url}/api-sdk/{action}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(full, method=method, data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            raise WirePodError(f"{action} failed: {e}") from e

    def discover_serial(self) -> str | None:
        """Ask wire-pod which robots it knows and return the first ESN."""
        try:
            with urllib.request.urlopen(f"{self.url}/api-sdk/get_sdk_info", timeout=5) as r:
                body = r.read().decode()
        except Exception:  # noqa: BLE001
            return None
        try:
            data = json.loads(body)
        except ValueError:
            data = body
        found = _find_esns(data)
        return found[0] if found else None

    # ---------- control ----------
    @contextmanager
    def control(self, priority: str = "high"):
        self._req("assume_behavior_control", priority=priority)
        try:
            yield self
        finally:
            try:
                self._req("release_behavior_control")
            except WirePodError:
                pass

    # ---------- speech & sound ----------
    def say(self, text: str, take_control: bool = True) -> None:
        text = text.strip()
        if not text:
            return
        if take_control:
            with self.control():
                self._req("say_text", text=text)
        else:
            self._req("say_text", text=text)

    def volume(self, level: int) -> None:
        self._req("volume", volume=max(0, min(5, int(level))))

    # ---------- movement ----------
    def drive(self, left: float, right: float, seconds: float) -> None:
        """Wheel speeds in mm/s (-200..200); stops after `seconds`."""
        left, right = _clamp(left, -200, 200), _clamp(right, -200, 200)
        with self.control():
            self._req("move_wheels", lw=int(left), rw=int(right))
            time.sleep(max(0.0, min(seconds, 10)))
            self._req("move_wheels", lw=0, rw=0)

    def head(self, speed: float, seconds: float = 0.6) -> None:
        with self.control():
            self._req("move_head", speed=_clamp(speed, -2, 2))
            time.sleep(seconds)
            self._req("move_head", speed=0)

    def lift(self, speed: float, seconds: float = 0.6) -> None:
        with self.control():
            self._req("move_lift", speed=_clamp(speed, -2, 2))
            time.sleep(seconds)
            self._req("move_lift", speed=0)

    # ---------- looks & behaviors ----------
    def eye_color(self, name_or_index) -> None:
        idx = EYE_COLORS.get(str(name_or_index).lower(), name_or_index)
        self._req("eye_color", color=int(idx))

    def custom_eye_color(self, hue: float, saturation: float) -> None:
        """hue and saturation are 0.0-1.0"""
        self._req("custom_eye_color", hue=_clamp(hue, 0, 1), sat=_clamp(saturation, 0, 1))

    def intent(self, name: str) -> None:
        self._req("cloud_intent", intent=INTENTS.get(name, name))

    def wake_word(self) -> None:
        """Make Vector start listening as if you said 'Hey Vector'."""
        self._req("trigger_wake_word")

    def robot_settings(self) -> dict:
        """Vector's own settings doc (volume, eye color, locale, units, ...)."""
        return _find_settings(_json_or_text(self._req("get_sdk_settings", method="GET")))

    def flash_eyes(self, name: str):
        """Context manager: show a color while speaking, then restore the user's choice."""
        bot = self

        class _Flash:
            def __enter__(self_inner):
                self_inner.prev = None
                try:
                    s = bot.robot_settings()
                    if (s.get("custom_eye_color") or {}).get("enabled"):
                        return self_inner  # don't fight a custom color
                    self_inner.prev = s.get("eye_color")
                    bot.eye_color(name)
                except Exception:  # noqa: BLE001
                    pass
                return self_inner

            def __exit__(self_inner, *exc):
                if self_inner.prev is not None:
                    try:
                        time.sleep(1.5)
                        bot.eye_color(int(self_inner.prev))
                    except Exception:  # noqa: BLE001
                        pass
                return False

        return _Flash()

    # ---------- sensing ----------
    def battery(self) -> dict:
        return _json_or_text(self._req("get_battery", method="GET"))

    def stats(self) -> dict:
        return _json_or_text(self._req("get_robot_stats", method="GET"))

    def faces(self):
        return _json_or_text(self._req("get_faces", method="GET"))

    def add_face(self, name: str) -> None:
        """Vector enrolls the face he is currently looking at."""
        self._req("add_face", name=name)

    def snapshot(self, timeout: float = 8.0) -> bytes:
        """Grab one JPEG frame from Vector's camera via wire-pod's MJPEG stream."""
        try:
            self._req("begin_cam_stream")
        except WirePodError:
            pass
        url = f"{self.url}/cam-stream?serial={urllib.parse.quote(self.serial or '')}"
        buf = b""
        deadline = time.time() + timeout
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                while time.time() < deadline:
                    chunk = r.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2) if start != -1 else -1
                    if start != -1 and end != -1:
                        return buf[start:end + 2]
        finally:
            try:
                self._req("stop_cam_stream")
            except WirePodError:
                pass
        raise WirePodError("no camera frame received")


def _clamp(v, lo, hi):
    return max(lo, min(hi, float(v)))


def _json_or_text(body: str):
    try:
        return json.loads(body)
    except ValueError:
        return {"raw": body}


def _find_settings(data) -> dict:
    """Locate the robot-settings dict inside wire-pod's jdoc response (may be nested JSON strings)."""
    if isinstance(data, str):
        try:
            return _find_settings(json.loads(data))
        except ValueError:
            return {}
    if isinstance(data, dict):
        if "master_volume" in data or "eye_color" in data:
            return data
        for v in data.values():
            found = _find_settings(v)
            if found:
                return found
    if isinstance(data, list):
        for v in data:
            found = _find_settings(v)
            if found:
                return found
    return {}


_ESN_RE =re.compile(r"\b(00[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")


def _find_esns(data) -> list[str]:
    out: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in ("esn", "serial") and isinstance(v, str):
                out.append(v)
            else:
                out += _find_esns(v)
    elif isinstance(data, list):
        for v in data:
            out += _find_esns(v)
    elif isinstance(data, str):
        out += _ESN_RE.findall(data)
    return out
