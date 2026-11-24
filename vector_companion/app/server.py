"""Local backend for the Vector app: serves the UI and bridges it to wire-pod, the brain and settings.

Listens on 127.0.0.1 only. The UI talks to /api/*; this server talks to wire-pod's
/api-sdk/* on the same Mac. Driving uses a watchdog so the robot always stops if the
UI goes away mid-drive.
"""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import config, settings as S
from .. import companion_client as cc
from ..wirepod import EYE_COLORS, INTENTS, Vector, WirePodError, _find_esns, _json_or_text

config.load_env()
STATIC = Path(__file__).parent / "static"
WIREPOD = os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080").rstrip("/")
BRAIN_PORT = int(os.environ.get("BRAIN_PORT", "11500"))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1").rstrip("/")
if OLLAMA.endswith("/v1"):
    OLLAMA = OLLAMA[:-3]
MEMORY_FILE = S.DATA_DIR / "memory.json"
TODO_FILE = S.DATA_DIR / "todo.json"

DOCK_BLOCKED = S.DOCK_BLOCKED

# actions the UI may call directly on wire-pod (with their allowed params)
WP_ALLOWED = {
    "volume": ["volume"], "eye_color": ["color"], "custom_eye_color": ["hue", "sat"],
    "locale": ["locale"], "location": ["location"], "timezone": ["timezone"],
    "time_format_12": [], "time_format_24": [], "temp_c": [], "temp_f": [],
    "button_hey_vector": [], "button_alexa": [], "mirror_mode": ["enable"],
    "cloud_intent": ["intent"], "trigger_wake_word": [], "rename_face": ["id", "oldname", "newname"],
    "delete_face": ["id"], "add_face": ["name"], "delete_image": ["id"],
}


def _get(url: str, timeout: float = 4) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


class Robot:
    """Thin stateful wrapper: serial discovery, behavior control, drive watchdog."""

    def __init__(self):
        self.lock = threading.Lock()
        self._v: Vector | None = None
        self.motion = {"lw": 0.0, "rw": 0.0, "head": 0.0, "lift": 0.0}
        self.last_cmd = 0.0
        self.controlling = False
        threading.Thread(target=self._watchdog, daemon=True).start()

    @property
    def v(self) -> Vector:
        if self._v is None or not self._v.serial:
            self._v = Vector(url=WIREPOD, timeout=6)
        if not self._v.serial:
            raise WirePodError("no robot set up in wire-pod")
        return self._v

    def wp(self, action: str, **params) -> str:
        return self.v._req(action, **params)

    def take_control(self):
        if not self.controlling:
            self.wp("assume_behavior_control", priority="high")
            self.controlling = True

    def release(self):
        if self.controlling:
            try:
                self.wp("release_behavior_control")
            finally:
                self.controlling = False

    def move(self, **kw):
        with self.lock:
            self.take_control()
            changed = {k: v for k, v in kw.items() if v is not None and self.motion.get(k) != v}
            self.motion.update(changed)
            if "lw" in changed or "rw" in changed:  # both wheels in one command
                self.wp("move_wheels", lw=int(self.motion["lw"]), rw=int(self.motion["rw"]))
            if "head" in changed:
                self.wp("move_head", speed=changed["head"])
            if "lift" in changed:
                self.wp("move_lift", speed=changed["lift"])
            self.last_cmd = time.time()

    def stop(self):
        with self.lock:
            try:
                if self.motion["lw"] or self.motion["rw"]:
                    self.wp("move_wheels", lw=0, rw=0)
                if self.motion["head"]:
                    self.wp("move_head", speed=0)
                if self.motion["lift"]:
                    self.wp("move_lift", speed=0)
            finally:
                self.motion = {"lw": 0.0, "rw": 0.0, "head": 0.0, "lift": 0.0}

    def _watchdog(self):
        while True:
            time.sleep(0.15)
            idle = time.time() - self.last_cmd
            try:
                if any(self.motion.values()) and idle > 0.6:
                    self.stop()  # UI stopped sending: halt
                if self.controlling and not any(self.motion.values()) and idle > 4:
                    with self.lock:
                        self.release()  # give Vector his personality back
            except Exception:  # noqa: BLE001
                self.motion = {"lw": 0.0, "rw": 0.0, "head": 0.0, "lift": 0.0}


ROBOT = Robot()


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def _ping(url: str) -> bool:
    try:
        _get(url, timeout=1.5)
        return True
    except Exception:  # noqa: BLE001
        return False


def _relaunch():
    """Quit and reopen the app with the latest code. (exec'ing in place from a background thread can take
    the window down with it, so ask macOS to start a fresh copy a moment after this one exits.)"""
    app = "/Applications/Vector.app"
    if sys.platform == "darwin" and os.path.exists(app):
        # wait until this process has fully gone, then reopen (launchd keeps the helper alive after we exit)
        script = f'while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done; sleep 0.5; open "{app}"'
        subprocess.Popen(["/usr/bin/nohup", "/bin/sh", "-c", script], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        time.sleep(0.3)
        os._exit(0)
    os.execv(sys.executable, [sys.executable, "-m", "vector_companion.app"])


def status() -> dict:
    try:
        comp = cc.call("/health", timeout=1.5)
    except Exception:  # noqa: BLE001
        comp = None
    out: dict = {"companion": comp, "wirepod": False, "brain": _ping(f"http://127.0.0.1:{BRAIN_PORT}/health"),
                 "ollama": _ping(OLLAMA + "/api/tags"), "robot": None}
    try:
        info = json.loads(_get(WIREPOD + "/api-sdk/get_sdk_info", 2))
        out["wirepod"] = True
        bots = info.get("robots") or []
        if bots:
            out["robot"] = bots[0]
    except Exception:  # noqa: BLE001
        pass
    if out["robot"]:
        try:
            out["battery"] = _json_or_text(ROBOT.wp("get_battery"))
        except Exception as e:  # noqa: BLE001
            out["battery_error"] = str(e)
    return out


PROVIDER_URLS = {"chatgpt": "https://api.openai.com/v1",
                 "gemini": "https://generativelanguage.googleapis.com/v1beta/openai"}


def _hint(k: str) -> str:
    return ("..." + k[-4:]) if len(k) > 8 else ""


def brain_settings() -> dict:
    env = S.read_env()
    backend = env.get("BRAIN_BACKEND", "ollama")
    url = env.get("OPENAI_COMPAT_URL", "")
    provider = backend
    if backend == "openai":
        provider = "gemini" if "generativelanguage" in url else "chatgpt"
    return {
        "provider": provider, "backend": backend,
        "model": env.get("BRAIN_MODEL", ""),
        "owner": env.get("VECTOR_OWNER", "Rushil"),
        "keys": {"anthropic": _hint(env.get("ANTHROPIC_API_KEY", "")),
                 "chatgpt": _hint(env.get("OPENAI_API_KEY_SAVED", "")),
                 "gemini": _hint(env.get("GEMINI_API_KEY_SAVED", ""))},
        "projects_dir": env.get("PROJECTS_DIR", ""),
        "about_me": _about_me(),
    }


ABOUT_FILE = S.DATA_DIR / "about_me.txt"


def _about_me() -> str:
    try:
        return ABOUT_FILE.read_text()
    except OSError:
        return ""


def provider_models(provider: str) -> list[str]:
    env = S.read_env()
    if provider == "ollama":
        return ollama_models()
    if provider == "anthropic":
        return ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
    key = env.get("OPENAI_API_KEY_SAVED" if provider == "chatgpt" else "GEMINI_API_KEY_SAVED", "")
    if not key:
        return []
    req = urllib.request.Request(PROVIDER_URLS[provider] + "/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            ids = [m.get("id", "") for m in json.loads(r.read()).get("data", [])]
    except Exception:  # noqa: BLE001
        return []
    ids = [i.replace("models/", "") for i in ids]
    if provider == "chatgpt":
        ids = [i for i in ids if i.startswith(("gpt-", "o")) and not any(x in i for x in ("audio", "realtime", "tts", "transcribe", "image", "search", "embedding", "moderation"))]
    else:
        ids = [i for i in ids if i.startswith("gemini") and not any(x in i for x in ("embedding", "tts", "image", "live", "audio"))]
    return sorted(set(ids), reverse=True)


def save_brain(body: dict) -> dict:
    up = {}
    keys = body.get("keys") or {}
    if keys.get("anthropic"):
        up["ANTHROPIC_API_KEY"] = keys["anthropic"].strip()
    if keys.get("chatgpt"):
        up["OPENAI_API_KEY_SAVED"] = keys["chatgpt"].strip()
    if keys.get("gemini"):
        up["GEMINI_API_KEY_SAVED"] = keys["gemini"].strip()
    S.write_env(up) if up else None
    env = S.read_env()
    prov = body.get("provider")
    if prov in ("ollama", "anthropic"):
        up["BRAIN_BACKEND"] = prov
    elif prov in ("chatgpt", "gemini"):
        up["BRAIN_BACKEND"] = "openai"
        up["OPENAI_COMPAT_URL"] = PROVIDER_URLS[prov]
        up["OPENAI_COMPAT_KEY"] = env.get("OPENAI_API_KEY_SAVED" if prov == "chatgpt" else "GEMINI_API_KEY_SAVED", "")
    if "model" in body:
        up["BRAIN_MODEL"] = str(body["model"]).strip()
    if "owner" in body and str(body["owner"]).strip():
        up["VECTOR_OWNER"] = str(body["owner"]).strip()
    if "projects_dir" in body:
        up["PROJECTS_DIR"] = str(body["projects_dir"]).strip()
    if "about_me" in body:
        S.DATA_DIR.mkdir(parents=True, exist_ok=True)
        ABOUT_FILE.write_text(str(body["about_me"]).strip() + "\n")
    if up:
        S.write_env(up)
    restart_brain()
    return brain_settings()


def restart_brain(service: str = "brain") -> bool:
    try:
        uid = os.getuid()
        r = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/com.rushil.vector-{service}"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


PHOTO_DIRS = (Path.home() / "Pictures" / "Vector", S.DATA_DIR / "guard")


def mac_photos() -> list[dict]:
    out = []
    for d in PHOTO_DIRS:
        if d.exists():
            for f in d.glob("*.jpg"):
                out.append({"name": f"{d.name}/{f.name}", "at": f.stat().st_mtime,
                            "kind": "guard" if d.name == "guard" else "photo"})
    return sorted(out, key=lambda x: -x["at"])[:120]


def _mac_photo_path(name: str) -> Path:
    folder, _, fname = name.partition("/")
    for d in PHOTO_DIRS:
        if d.name == folder and fname and "/" not in fname and not fname.startswith("."):
            f = d / fname
            if f.exists():
                return f
    raise FileNotFoundError(name)


_weather_cache: dict = {}


def today() -> dict:
    from ..brain import TODO_FILE, _reminders
    from ..companion import study_today
    out = {"study": study_today(), "todo": _load_json(TODO_FILE, []), "next": [], "weather": None, "focus": None}
    try:
        out["next"] = _reminders(3)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["focus"] = cc.call("/health", timeout=2).get("focus")
    except Exception:  # noqa: BLE001
        pass
    if S.load()["weather"].get("enabled", True):
        hit = _weather_cache.get("w")
        if hit and time.time() - hit[0] < 1200:
            out["weather"] = hit[1]
        else:
            try:
                from .. import weather
                d = weather.forecast()
                cur, dl = d["current"], d["daily"]
                w = {"now": f"{round(cur['temperature_2m'])}° {weather.CODES.get(cur['weather_code'], '')}".strip(),
                     "range": f"High {round(dl['temperature_2m_max'][0])}° · Low {round(dl['temperature_2m_min'][0])}°"}
                _weather_cache["w"] = (time.time(), w)
                out["weather"] = w
            except Exception:  # noqa: BLE001
                pass
    return out


def ears_status() -> dict:
    try:
        st = json.loads((S.DATA_DIR / "ears.json").read_text())
    except Exception:  # noqa: BLE001
        st = {}
    try:
        st["running"] = subprocess.run(["pgrep", "-f", "vector_companion.ears"], capture_output=True,
                                       timeout=3).returncode == 0
    except Exception:  # noqa: BLE001
        st["running"] = False
    return st


def restart_ears() -> bool:
    subprocess.run(["pkill", "-f", "vector_companion.ears"], capture_output=True, timeout=5)
    time.sleep(0.8)
    app = "/Applications/Vector Ears.app"
    if os.path.exists(app):
        return subprocess.run(["open", "-g", "-a", app], capture_output=True, timeout=10).returncode == 0
    subprocess.Popen([str(config.ROOT / ".venv/bin/python"), "-m", "vector_companion.ears"], cwd=str(config.ROOT),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True


_voices: list[str] = []


def mac_voices() -> list[str]:
    """English voices from `say -v ?`, British ones first (JARVIS)."""
    global _voices
    if not _voices:
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=8).stdout
        except Exception:  # noqa: BLE001
            out = ""
        rows = []
        for line in out.splitlines():
            parts = line.split("#")[0].split()
            if len(parts) >= 2 and parts[-1].startswith("en_"):
                rows.append((" ".join(parts[:-1]), parts[-1]))
        rows.sort(key=lambda r: (r[1] != "en_GB", r[0]))
        _voices = [n for n, _ in rows]
    return _voices


def ollama_models() -> list[str]:
    try:
        return [m["name"] for m in json.loads(_get(OLLAMA + "/api/tags", 3)).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def convert_sound(raw: bytes, suffix: str) -> bytes:
    """Vector plays 8 kHz mono 16-bit WAV. Uses macOS afconvert (or ffmpeg) to convert."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / f"in{suffix}", Path(d) / "out.wav"
        src.write_bytes(raw)
        if shutil.which("afconvert"):
            cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(dst)]
        elif shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "16000", "-ac", "1",
                   "-sample_fmt", "s16", str(dst)]
        else:
            raise RuntimeError("no audio converter found")
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        return dst.read_bytes()


def play_sound(wav: bytes) -> None:
    boundary = "----vectorapp" + str(int(time.time() * 1000))
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"sound\"; filename=\"s.wav\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + wav + f"\r\n--{boundary}--\r\n".encode()
    url = f"{WIREPOD}/api-sdk/play_sound?serial={ROBOT.v.serial}"
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()


class Handler(BaseHTTPRequestHandler):
    server_version = "VectorApp/1.0"

    def log_message(self, fmt, *args):
        pass

    # ---------- helpers ----------
    def _send(self, code: int, body: bytes, ctype: str = "application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode())

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw)
        except ValueError:
            return {"_raw": raw}

    def _err(self, e: Exception, code: int = 502):
        self._json({"ok": False, "error": str(e)}, code)

    # ---------- routes ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path
        try:
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/status":
                return self._json(status())
            if path == "/api/robot_settings":
                return self._json(ROBOT.v.robot_settings())
            if path == "/api/stats":
                return self._json(_json_or_text(ROBOT.wp("get_robot_stats", method="GET")))
            if path == "/api/faces":
                return self._json(_json_or_text(ROBOT.wp("get_faces", method="GET")))
            if path == "/api/photos":
                try:
                    robot = _json_or_text(ROBOT.wp("get_image_ids", method="GET")) or []
                except Exception:  # noqa: BLE001
                    robot = []
                return self._json({"mac": mac_photos(), "robot": robot if isinstance(robot, list) else []})
            if path.startswith("/api/mac_photo/"):
                f = _mac_photo_path(urllib.parse.unquote(path[len("/api/mac_photo/"):]))
                return self._send(200, f.read_bytes(), "image/jpeg")
            if path == "/api/today":
                return self._json(today())
            if path == "/api/photo":
                action = "get_image_thumb" if q.get("thumb") else "get_image"
                url = f"{WIREPOD}/api-sdk/{action}?serial={ROBOT.v.serial}&id={urllib.parse.quote(q.get('id', ''))}"
                data = _get(url, 15)
                return self._send(200, data, "image/jpeg")
            if path == "/api/camera_url":
                return self._json({"url": "/api/cam?x=1"})
            if path == "/api/cam":
                return self._proxy_cam()
            if path == "/api/settings":
                return self._json({"app": S.load(), "brain": brain_settings(),
                                   "ollama_models": ollama_models(),
                                   "eye_colors": list(EYE_COLORS), "actions": list(INTENTS)})
            if path == "/api/memory":
                return self._json({"memory": _load_json(MEMORY_FILE, []), "todo": _load_json(TODO_FILE, [])})
            if path == "/api/models":
                return self._json(provider_models(q.get("provider", "ollama")))
            if path == "/api/companion/health":
                try:
                    return self._json(cc.call("/health", timeout=2))
                except Exception as e:  # noqa: BLE001
                    return self._json({"connected": False, "running": False, "error": str(e)})
            if path in ("/api/companion/stats", "/api/companion/guard"):
                return self._json(cc.call(path[len("/api/companion"):], timeout=4))
            if path.startswith("/api/guard_photo/"):
                return self._send(200, cc.call("/guard_photo/" + os.path.basename(path), timeout=6), "image/jpeg")
            if path == "/api/study":
                from ..companion import study_today
                return self._json({"today": study_today()})
            if path == "/api/ears":
                return self._json(ears_status())
            if path == "/api/reports":
                from .. import openjarvis as OJ
                out = []
                d = S.DATA_DIR / "reports"
                for f in sorted(d.glob("*.md"), reverse=True)[:12] if d.exists() else []:
                    t = f.read_text(errors="ignore")
                    out.append({"title": t.splitlines()[0].lstrip("# ")[:120] if t else f.stem, "when": f.stem,
                                "text": "\n".join(t.splitlines()[2:])[:20000]})
                return self._json({"reports": out, "openjarvis": OJ.available()})
            if path == "/api/tts":
                from .. import tts
                return self._json(tts.status())
            if path == "/api/voices":
                return self._json(mac_voices())
            if path == "/api/sensors":
                return self._json(cc.call("/sensors", timeout=3))
            if path == "/api/map.png":
                return self._send(200, cc.call("/map.png", timeout=8), "image/png")
            if path == "/api/companion_anims":
                return self._json(cc.call("/anims", timeout=5))
            if path == "/api/scans":
                return self._json(vision_history())
            if path.startswith("/api/scan_image/"):
                sid = os.path.basename(path)
                return self._send(200, (S.DATA_DIR / "scans" / f"{sid}.jpg").read_bytes(), "image/jpeg")
            if path == "/api/logs":
                return self._json({"hook": S.tail("hook", 60), "companion": S.tail("companion", 40),
                                   "brain": _tail_file(S.DATA_DIR / "brain.log", 60)})
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        b = self._body()
        try:
            if path.startswith("/api/wp/"):
                action = path[len("/api/wp/"):]
                if action not in WP_ALLOWED:
                    return self._json({"error": "not allowed"}, 403)
                params = {k: b[k] for k in WP_ALLOWED[action] if k in b}
                if action == "mirror_mode":  # needs control held the whole time: the companion does it
                    on = str(params.get("enable", "true")).lower() == "true"
                    return self._json(cc.call("/mirror", {"on": on, "seconds": 300}, timeout=15))
                if action == "cloud_intent":
                    name = params.get("intent", "")
                    if S.load()["safety"]["dock_lock"] and name in DOCK_BLOCKED:
                        return self._json({"ok": False, "error": "That makes him leave the charger. "
                                           "It's blocked while the dock lock is on (Robot Settings)."}, 423)
                    params["intent"] = INTENTS.get(name, name)
                return self._json({"ok": True, "result": ROBOT.wp(action, **params)})
            if path == "/api/say":
                text = str(b.get("text", "")).strip()[:400]
                try:  # one channel: the companion owns behavior control
                    cc.call("/say", {"text": text}, timeout=60)
                except Exception:  # noqa: BLE001
                    with ROBOT.lock:
                        ROBOT.take_control()
                        ROBOT.wp("say_text", text=text)
                        ROBOT.last_cmd = time.time()
                return self._json({"ok": True})
            if path == "/api/move":
                lw, rw = _f(b, "lw", -220, 220) or 0, _f(b, "rw", -220, 220) or 0
                if S.load()["safety"]["dock_lock"] and (lw or rw):
                    return self._json({"ok": False, "error": "Dock lock is on: driving is off until his new battery is in."}, 423)
                try:  # companion drives with cliff + obstacle protection
                    cc.call("/drive", {"lw": lw, "rw": rw}, timeout=3)
                except Exception:  # noqa: BLE001
                    ROBOT.move(lw=lw, rw=rw)
                return self._json({"ok": True})
            if path == "/api/stop":
                try:
                    cc.call("/stop", {}, timeout=3)
                except Exception:  # noqa: BLE001
                    pass
                ROBOT.stop()
                return self._json({"ok": True})
            if path == "/api/release":
                ROBOT.stop()
                with ROBOT.lock:
                    ROBOT.release()
                return self._json({"ok": True})
            if path.startswith("/api/companion/"):
                sub = path[len("/api/companion"):]
                if sub not in ("/face", "/head", "/lift", "/anim", "/scan", "/focus", "/greet_test", "/say",
                               "/dock", "/reconnect", "/stop", "/guard", "/cube"):
                    return self._json({"error": "not allowed"}, 403)
                r = cc.call(sub, b, timeout=180 if sub == "/scan" else 60)
                return self._json(r, 200 if (not isinstance(r, dict) or r.get("ok", True)) else 503)
            if path == "/api/settings":
                return self._json({"app": S.save(b.get("app", {})),
                                   "brain": save_brain(b["brain"]) if "brain" in b else brain_settings()})
            if path == "/api/openjarvis/diag":  # what OpenJarvis is configured with, and one raw agent answer
                from .. import openjarvis as OJ
                cfg = os.path.expanduser("~/.openjarvis/config.toml")
                out = {"config": open(cfg).read()[-4000:] if os.path.exists(cfg) else None}
                try:
                    req = urllib.request.Request(OJ.url() + "/v1/chat/completions", data=json.dumps(
                        {"model": "default", "stream": False, "messages": [{"role": "user", "content": str(b.get("text") or "Search the web: what is today's top science headline? Give the link.")}]}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        out["raw"] = json.loads(r.read())
                except Exception as e:  # noqa: BLE001
                    out["error"] = str(e)
                return self._json(out)
            if path == "/api/ask":  # type to Jarvis: same brain as voice (fast path or OpenJarvis)
                from .. import voice
                text = str(b.get("text", "")).strip()[:1000]
                parts, t0 = [], time.time()
                for part in voice.respond_stream(text, []):
                    if part and part.strip():
                        parts.append(part)
                        if b.get("speak"):
                            try:
                                cc.call("/say", {"text": part}, timeout=90)
                            except Exception:  # noqa: BLE001
                                pass
                return self._json({"parts": parts, "seconds": round(time.time() - t0, 1)})
            if path == "/api/tts/install":
                from .. import tts
                tts.install_async(str(b.get("voice", "")) or None)
                return self._json({"ok": True})
            if path == "/api/ears/restart":
                return self._json({"ok": restart_ears()})
            if path == "/api/quiz":
                return self._json(cc.call("/quiz", {"topic": str(b.get("topic", ""))}, timeout=10))
            if path == "/api/do":
                return self._json(cc.call("/do", {"action": str(b.get("action", ""))}, timeout=90))
            if path == "/api/app_restart":  # reload this app with the latest code
                threading.Timer(0.5, _relaunch).start()
                return self._json({"ok": True})
            if path == "/api/companion_restart":
                return self._json({"ok": restart_brain("companion")})
            if path == "/api/brain/restart":
                return self._json({"ok": restart_brain()})
            if path == "/api/test_notify":
                from ..cli import hook
                threading.Thread(target=hook, args=("test",), daemon=True).start()
                return self._json({"ok": True})
            if path == "/api/memory":
                MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                if "memory" in b:
                    MEMORY_FILE.write_text(json.dumps(b["memory"], indent=2))
                if "todo" in b:
                    TODO_FILE.write_text(json.dumps(b["todo"], indent=2))
                return self._json({"ok": True})
            if path == "/api/sound":
                data = b.get("_raw", b"")
                name = self.headers.get("X-Filename", "sound.wav")
                wav = convert_sound(data, Path(name).suffix or ".wav")
                tmp = Path(tempfile.gettempdir()) / f"vector-sound-{int(time.time())}.wav"
                tmp.write_bytes(wav)
                try:  # the companion owns his speaker; WirePod's player fights it for control
                    cc.call("/play", {"path": str(tmp)}, timeout=5)
                except Exception:  # noqa: BLE001
                    threading.Thread(target=play_sound, args=(wav,), daemon=True).start()
                return self._json({"ok": True})
            if path == "/api/mac_photo_delete":
                _mac_photo_path(str(b.get("name", ""))).unlink()
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def _proxy_cam(self):
        """Relay wire-pod's MJPEG camera stream (the browser can't load it cross-origin)."""
        up = urllib.request.urlopen(f"{WIREPOD}/cam-stream?serial={ROBOT.v.serial}", timeout=10)
        try:
            self.send_response(200)
            self.send_header("Content-Type", up.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=--boundary"))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while True:
                chunk = up.read(16384)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # viewer left: closing upstream stops wire-pod's stream
        finally:
            up.close()

    def _static(self, rel: str):
        p = (STATIC / rel).resolve()
        if STATIC.resolve() not in p.parents and p != STATIC.resolve() or not p.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        self._send(200, p.read_bytes(), ctype)


def vision_history(n: int = 40) -> list:
    d = S.DATA_DIR / "scans"
    out = []
    for p in sorted(d.glob("*.json"), reverse=True)[:n] if d.exists() else []:
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            pass
    return out


def _f(b: dict, k: str, lo: float, hi: float):
    if k not in b or b[k] is None:
        return None
    return max(lo, min(hi, float(b[k])))


def _tail_file(p: Path, n: int) -> list[str]:
    try:
        return p.read_text(errors="replace").splitlines()[-n:]
    except Exception:  # noqa: BLE001
        return []


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]
