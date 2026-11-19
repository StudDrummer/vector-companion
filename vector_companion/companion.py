"""Always-on companion: keeps a Python-SDK connection to Vector and adds behaviors wire-pod can't.

  * Hearts on his face when you pet him (plus a happy animation)
  * Greets people he recognizes; morning briefing with your to-do list
  * Focus timer drawn on his face, with check-ins
  * Face icons for Claude/terminal notifications (check, X, question)
  * Homework / text scanning: high-res photo -> vision AI -> spoken summary + full answer in the app
  * Precise head angle and lift height for the app

Local HTTP API on 127.0.0.1:47801 (used by the app, the brain, the hooks and the MCP server).
Run: python -m vector_companion.companion   (installed as a login item by upgrade.sh)
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import threading
import time
import traceback
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, face_art, settings as S, vision

config.load_env()
PORT = int(os.environ.get("COMPANION_PORT", "47801"))
WIREPOD = os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080").rstrip("/")
OWNER = os.environ.get("VECTOR_OWNER", "Rushil")

def prefs() -> dict:
    return S.load()["companion"]


def log(msg: str) -> None:
    S.log("companion", msg)


def mac_notify(title: str, body: str) -> None:
    body = body.replace('"', "'")[:220]
    try:
        subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                       capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001
        pass


class Companion:
    def __init__(self):
        self.robot = None
        self.serial = None
        self.lock = threading.RLock()
        self.error = "starting"
        self.triggers: list[str] = []
        self.last_greet: dict[str, float] = {}
        self.briefed_on = None
        self.focus = None  # {"end": ts, "total": min, "id": n}
        self.focus_id = 0
        self.last_pet = 0.0
        self.scanning = False
        threading.Thread(target=self._connect_loop, daemon=True).start()
        threading.Thread(target=self._pet_loop, daemon=True).start()

    # ------------------------------------------------------------ connection
    @property
    def connected(self) -> bool:
        return self.robot is not None

    def _connect_loop(self):
        while True:
            if self.robot is None:
                try:
                    self._connect()
                    self.error = None
                    log(f"connected to {self.serial}")
                except Exception as e:  # noqa: BLE001
                    self.error = f"{e.__class__.__name__}: {e}"
                    self._drop()
            else:
                try:
                    _ = self.robot.get_battery_state()  # heartbeat
                except Exception as e:  # noqa: BLE001
                    log(f"lost connection: {e}")
                    self.error = "lost connection"
                    self._drop()
            time.sleep(20)

    def _connect(self):
        import anki_vector
        from anki_vector.events import Events
        from .sdk_setup import ensure_config
        self.serial = ensure_config(WIREPOD)
        r = anki_vector.Robot(self.serial, behavior_control_level=None, enable_face_detection=True,
                              cache_animation_lists=False)
        r.connect(timeout=15)
        self.robot = r
        try:
            r.anim.load_animation_trigger_list()
            self.triggers = list(r.anim.anim_trigger_list)
        except Exception:  # noqa: BLE001
            self.triggers = []
        r.events.subscribe(self._on_face, Events.robot_observed_face)

    def _drop(self):
        r, self.robot = self.robot, None
        if r is not None:
            try:
                r.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def need(self):
        if self.robot is None:
            raise RuntimeError(f"Vector not connected ({self.error})")
        return self.robot

    class _Control:
        def __init__(self, outer):
            self.o = outer

        def __enter__(self):
            self.o.lock.acquire()
            r = self.o.need()
            r.conn.request_control(timeout=6)
            return r

        def __exit__(self, *exc):
            try:
                if self.o.robot is not None:
                    self.o.robot.conn.release_control(timeout=4)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self.o.lock.release()
            return False

    def control(self):
        return Companion._Control(self)

    # ------------------------------------------------------------ actions
    def show(self, img, seconds: float = 3.0, with_control=None):
        from anki_vector import screen as scr
        size = scr.dimensions() if hasattr(scr, "dimensions") else (184, 96)
        img = img.convert("RGB")
        if img.size != tuple(size):
            img = img.resize(tuple(size))
        data = scr.convert_image_to_screen_data(img)

        def _do(r):
            r.screen.set_screen_with_image_data(data, seconds, interrupt_running=True)
            time.sleep(seconds)
        if with_control is not None:
            _do(with_control)
        else:
            with self.control() as r:
                _do(r)

    def face(self, icon: str = "", text: str = "", seconds: float = 3.0):
        img = face_art.text(text) if text else face_art.ICONS.get(icon, face_art.question)()
        self.show(img, seconds)

    def announce(self, text: str, icon: str = "check"):
        img = face_art.ICONS.get(icon, face_art.check)()
        with self.control() as r:
            self.show(img, 1.4, with_control=r)
            r.behavior.say_text(text)
            self.show(img, 2.0, with_control=r)

    def say(self, text: str, r=None):
        if r is not None:
            r.behavior.say_text(text)
            return
        with self.control() as rr:
            rr.behavior.say_text(text)

    def find_trigger(self, *keywords: str) -> str | None:
        for k in keywords:
            for t in self.triggers:
                if k.lower() in t.lower():
                    return t
        return None

    def anim(self, name: str, r=None):
        trig = name if name in self.triggers else self.find_trigger(name)
        if not trig:
            raise ValueError(f"no animation matching {name!r}")
        if r is not None:
            r.anim.play_animation_trigger(trig)
            return trig
        with self.control() as rr:
            rr.anim.play_animation_trigger(trig)
        return trig

    def head(self, deg: float):
        from anki_vector.util import degrees
        with self.control() as r:
            r.behavior.set_head_angle(degrees(max(-22.0, min(45.0, float(deg)))))

    def lift(self, height: float):
        with self.control() as r:
            r.behavior.set_lift_height(max(0.0, min(1.0, float(height))))

    def capture(self) -> bytes:
        with self.lock:
            r = self.need()
            try:
                img = r.camera.capture_single_image(enable_high_resolution=True)
            except TypeError:
                img = r.camera.capture_single_image()
            buf = io.BytesIO()
            img.raw_image.convert("RGB").save(buf, "JPEG", quality=92)
            return buf.getvalue()

    # ------------------------------------------------------------ scanning
    def scan(self, mode="explain", question="", countdown=True, delay: float = 0) -> dict:
        if self.scanning:
            raise RuntimeError("already scanning")
        self.scanning = True
        try:
            if delay:
                time.sleep(min(float(delay), 10))  # let wire-pod finish speaking first
            with self.control() as r:
                from anki_vector.util import degrees
                r.behavior.set_head_angle(degrees(10))
                if countdown:
                    r.behavior.say_text("Hold it up in front of me. Three, two, one.")
                self.show(face_art.camera(), 0.8, with_control=r)
            jpeg = self.capture()
            done = threading.Event()

            def thinking():  # animated dots while the AI works
                i = 0
                while not done.is_set():
                    try:
                        with self.control() as rr:
                            self.show(face_art.thinking(i), 1.2, with_control=rr)
                    except Exception:  # noqa: BLE001
                        return
                    i += 1
            threading.Thread(target=thinking, daemon=True).start()
            try:
                res = vision.ask(jpeg, mode, question)
            finally:
                done.set()
            res = vision.save(jpeg, res)
            mac_notify("Vector scanned it", res["say"])
            try:
                with self.control() as r:
                    self.show(face_art.check(), 1.5, with_control=r)
                    r.behavior.say_text(res["say"])
            except Exception:  # noqa: BLE001
                pass
            log(f"scan {mode}: {res['say']}")
            return res
        except Exception as e:  # noqa: BLE001
            log(f"scan failed: {e}")
            try:
                self.say("Sorry, I couldn't scan that. " + (str(e)[:120] if "vision AI" in str(e) else ""))
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            self.scanning = False

    # ------------------------------------------------------------ focus timer
    def start_focus(self, minutes: int | None = None):
        minutes = int(minutes or prefs()["focus_minutes"])
        self.focus_id += 1
        fid = self.focus_id
        self.focus = {"end": time.time() + minutes * 60, "total": minutes, "id": fid}
        threading.Thread(target=self._focus_loop, args=(fid, minutes), daemon=True).start()
        return self.focus

    def stop_focus(self):
        self.focus = None
        self.focus_id += 1

    def _focus_loop(self, fid: int, total: int):
        try:
            with self.control() as r:
                self.show(face_art.timer(total, total), 3, with_control=r)
                r.behavior.say_text(f"{total} minute focus timer. Go get it.")
        except Exception as e:  # noqa: BLE001
            log(f"focus start display failed: {e}")
        shown = total
        while self.focus and self.focus["id"] == fid:
            left = self.focus["end"] - time.time()
            if left <= 0:
                break
            mins = int((left + 59) // 60)
            if prefs()["focus_checkins"] and mins % 5 == 0 and mins != shown:
                shown = mins
                try:
                    self.show(face_art.timer(mins, total), 3)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)
        if not (self.focus and self.focus["id"] == fid):
            return
        self.focus = None
        try:
            with self.control() as r:
                trig = self.find_trigger("Celebrat", "Happy", "Success", "FistBump")
                if trig:
                    r.anim.play_animation_trigger(trig)
                self.show(face_art.check(), 2, with_control=r)
                r.behavior.say_text(f"Time's up {OWNER}! {total} minute{'s' if total != 1 else ''} done. Take a five minute break.")
        except Exception as e:  # noqa: BLE001
            log(f"focus end failed: {e}")
        mac_notify("Focus timer done", f"{total} minutes. Take a break.")

    # ------------------------------------------------------------ petting
    def _pet_loop(self):
        touching_since = None
        while True:
            time.sleep(0.15)
            r = self.robot
            if r is None or not prefs()["pet_hearts"]:
                touching_since = None
                continue
            try:
                touched = r.touch.last_sensor_reading.is_being_touched
            except Exception:  # noqa: BLE001
                continue
            now = time.time()
            if not touched:
                touching_since = None
                continue
            touching_since = touching_since or now
            if now - touching_since > 1.3 and now - self.last_pet > 25 and not self.scanning and not self.focus:
                self.last_pet = now
                threading.Thread(target=self._pet_reaction, daemon=True).start()

    def _pet_reaction(self):
        try:
            with self.control() as r:
                for s in (0.8, 1.0, 1.1, 1.0):  # little heartbeat
                    self.show(face_art.heart(s), 0.35, with_control=r)
                trig = self.find_trigger("PettingBliss", "Petting", "Happy", "Love")
                if trig:
                    r.anim.play_animation_trigger(trig)
            log("pet: hearts")
        except Exception as e:  # noqa: BLE001
            log(f"pet reaction failed: {e}")

    # ------------------------------------------------------------ greetings
    def _on_face(self, robot, event_type, event, *a):
        try:
            name = (getattr(event, "name", "") or "").strip()
        except Exception:  # noqa: BLE001
            return
        if not name or not prefs()["greetings"] or self.scanning or self.focus:
            return
        now = time.time()
        if now - self.last_greet.get(name, 0) < 4 * 3600:
            return
        self.last_greet[name] = now
        threading.Thread(target=self._greet, args=(name,), daemon=True).start()

    def greeting_text(self, name: str) -> str:
        now = datetime.now()
        is_owner = name.lower() == OWNER.lower()
        if is_owner and prefs()["morning_briefing"] and 5 <= now.hour < 11 and self.briefed_on != now.date():
            self.briefed_on = now.date()
            from .brain import briefing
            return briefing()
        style = S.load().get("persona", {}).get("style", "vector")
        if is_owner and style == "jarvis":
            return f"Welcome back, sir." + (" Shall I start a focus timer?" if 17 <= now.hour < 23 else "")
        if is_owner and style == "friday":
            return "Hey boss, good to see you." + (" Want a focus timer?" if 17 <= now.hour < 23 else "")
        if 17 <= now.hour < 23:
            return f"Welcome back {name}!" + (" Want me to start a focus timer?" if is_owner else "")
        return f"Hi {name}!"

    def _greet(self, name: str):
        try:
            text = self.greeting_text(name)
            with self.control() as r:
                trig = self.find_trigger("GreetAfterLongTime", "Greet", "Happy")
                if trig and len(text) < 40:
                    r.anim.play_animation_trigger(trig)
                r.behavior.say_text(text)
            log(f"greet {name}: {text}")
        except Exception as e:  # noqa: BLE001
            log(f"greet failed: {e}")


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def upcoming_reminders(days: int = 3) -> list[str]:
    """Memory notes that mention today, tomorrow, or a weekday/date in the next few days."""
    out = []
    today = datetime.now().date()
    soon = {(today + timedelta(d)) for d in range(days + 1)}
    names = {WEEKDAYS[d.weekday()] for d in soon} | {"today", "tomorrow"}
    for m in _load(S.DATA_DIR / "memory.json", []):
        t = m.get("text", "")
        low = t.lower()
        if any(w in low for w in names) or any(d.strftime("%b %-d").lower() in low for d in soon):
            out.append(t)
    return out


COMP: Companion = None  # created in main()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return {}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/health":
                f = COMP.focus
                return self._send(200, {"connected": COMP.connected, "serial": COMP.serial, "error": COMP.error,
                                        "scanning": COMP.scanning, "triggers": len(COMP.triggers),
                                        "focus": {"left_s": int(f["end"] - time.time()), "total": f["total"]} if f else None,
                                        "prefs": prefs()})
            if u.path == "/capture":
                return self._send(200, COMP.capture(), "image/jpeg")
            if u.path == "/anims":
                return self._send(200, COMP.triggers)
            if u.path == "/scans":
                return self._send(200, vision.history())
            if u.path.startswith("/scan_image/"):
                sid = os.path.basename(u.path)
                return self._send(200, (vision.SCANS / f"{sid}.jpg").read_bytes(), "image/jpeg")
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(503, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        b = self._body()
        try:
            if u.path == "/say":
                COMP.say(str(b.get("text", ""))[:400])
            elif u.path == "/face":
                if not prefs()["face_icons"] and b.get("source") == "notify":
                    return self._send(200, {"ok": True, "skipped": True})
                COMP.face(b.get("icon", ""), b.get("text", ""), float(b.get("seconds", 3)))
            elif u.path == "/hud":
                lines = [(str(t)[:22], tuple(c)) for t, c in b.get("lines", [])][:4]
                threading.Thread(target=lambda: _safe(COMP.show, face_art.status(lines), float(b.get("seconds", 6))),
                                 daemon=True).start()
            elif u.path == "/announce":
                COMP.announce(str(b.get("text", ""))[:400], b.get("icon", "check"))
            elif u.path == "/head":
                COMP.head(b.get("deg", 10))
            elif u.path == "/lift":
                COMP.lift(b.get("height", 0))
            elif u.path == "/anim":
                return self._send(200, {"ok": True, "played": COMP.anim(str(b.get("name", "")))})
            elif u.path == "/scan":
                args = (b.get("mode", "explain"), b.get("question", ""), b.get("countdown", True), b.get("delay", 0))
                if b.get("async"):
                    threading.Thread(target=lambda: _safe(COMP.scan, *args), daemon=True).start()
                    return self._send(200, {"ok": True, "started": True})
                return self._send(200, {"ok": True, "result": COMP.scan(*args)})
            elif u.path == "/focus":
                if b.get("stop"):
                    COMP.stop_focus()
                    return self._send(200, {"ok": True})
                return self._send(200, {"ok": True, "focus": COMP.start_focus(b.get("minutes"))})
            elif u.path == "/greet_test":
                return self._send(200, {"ok": True, "text": COMP.greeting_text(OWNER)})
            else:
                return self._send(404, {"error": "not found"})
            return self._send(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            return self._send(503, {"ok": False, "error": str(e)})


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001
        log(traceback.format_exc(limit=3))


def main():
    global COMP
    log("companion starting")
    COMP = Companion()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[companion] http://127.0.0.1:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
