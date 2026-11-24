"""Always-on companion: keeps a Python-SDK connection to Vector and does what wire-pod can't.

Reliability first:
  * every robot call has a time limit; a call that hangs (Wi-Fi drop) marks the link dead,
    the companion reconnects within seconds, and the caller gets a clear error instead of a freeze
  * one lock with a timeout around behavior control, so nothing can block everything else
  * dock lock (default on): no driving, no leave-the-charger actions, and if he rolls off he's
    sent straight back
  * safe driving: wheels stop on a cliff (desk edge) or an obstacle closer than ~6 cm ahead

Features: hearts when petted, greetings + morning briefing, focus timer on his face, face badges
for notifications, homework/text scanning, precise head/lift, animations, live sensors, desk map.

Local HTTP API on 127.0.0.1:47801. Run: python -m vector_companion.companion
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import wave
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, face_art, settings as S, vision

config.load_env()
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "0")
import logging  # noqa: E402
logging.basicConfig(level=logging.WARNING)
for _name in ("anki_vector", "connection", "connection.Connection", "util", "util.AudioComponent", "grpc"):
    logging.getLogger(_name).setLevel(logging.WARNING)
PORT = int(os.environ.get("COMPANION_PORT", "47801"))
WIREPOD = os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080").rstrip("/")
OWNER = os.environ.get("VECTOR_OWNER", "Rushil")

# per-call time limits (seconds); anything slower means the link is gone
# An action that hangs (e.g. an animation waiting for something that never happens) blocks every later
# action in his queue. After one of these times out, we hand control back, which clears his queue.
QUEUED_ACTIONS = {"play_animation_trigger", "play_animation", "set_lift_height", "set_head_angle", "say_text",
                  "drive_straight", "turn_in_place", "drive_on_charger"}
TIMEOUTS = {"say_text": 45, "play_animation_trigger": 20, "drive_on_charger": 45, "drive_off_charger": 30,
            "capture_single_image": 12, "request_control": 8, "release_control": 5,
            "set_screen_with_image_data": 6, "get_battery_state": 6, "connect": 20, "drive_straight": 20,
            "turn_in_place": 20}
DEFAULT_TIMEOUT = 10
SAFE_STOP_MM = 60  # stop driving forward when something is closer than this


def play_trigger(r, name: str):
    """Play an animation trigger by name without the SDK first downloading his whole animation list
    (that download times out over Wi-Fi, which made animations fail)."""
    try:
        from anki_vector.messaging import protocol
        trig = protocol.AnimationTrigger(name=name)
    except Exception:  # noqa: BLE001  (older SDKs: fall back to the name)
        trig = name
    # He stays docked (dock lock), so never let an animation spin his wheels on the charger.
    try:
        return r.anim.play_animation_trigger(trig, ignore_body_track=True)
    except TypeError:
        return r.anim.play_animation_trigger(trig)


class VectorOffline(RuntimeError):
    pass


def prefs() -> dict:
    return S.load()["companion"]


def safety() -> dict:
    return S.load()["safety"]


def log(msg: str) -> None:
    S.log("companion", msg)


def mac_notify(title: str, body: str) -> None:
    body = body.replace('"', "'")[:220]
    try:
        subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                       capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001
        pass


class _Guard:
    """Wraps the SDK robot so every method call runs with a time limit."""

    def __init__(self, target, comp: "Companion"):
        object.__setattr__(self, "_t", target)
        object.__setattr__(self, "_c", comp)

    def __getattr__(self, name):
        attr = getattr(self._t, name)
        if callable(attr):
            def call(*a, **k):
                return self._c.call(lambda: attr(*a, **k), TIMEOUTS.get(name, DEFAULT_TIMEOUT), name)
            return call
        mod = type(attr).__module__ or ""
        if mod.startswith("anki_vector") and not isinstance(attr, (int, float, str, bool)):
            return _Guard(attr, self._c)  # nested component (behavior, anim, screen, ...)
        return attr


class Companion:
    def __init__(self):
        self._robot = None
        self.serial = None
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="vector-call")
        self.error = "starting"
        self.triggers: list[str] = []
        self.last_greet: dict[str, float] = {}
        self.briefed_on = None
        self.focus = None  # {"end": ts, "total": min, "id": n}
        self.focus_id = 0
        self.last_pet = 0.0
        self.scanning = False
        self.drive_cmd = {"lw": 0.0, "rw": 0.0, "at": 0.0}
        self.safety_event = None
        self.returning = False
        self._wake = threading.Event()
        self.speaking_until = 0.0
        self.audio_broken_until = 0.0
        self.ctl_held = False
        self.ctl_last = 0.0
        self.hb_misses = 0
        self.unstick = False
        self.move_target: dict = {}
        self.move_busy: dict = {}
        self.cube_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vector-cube")
        self.stats = {"since": time.time(), "drops": [], "wake_words": [], "intents": [], "taps": 0}
        self.guard = None  # {"since": ts, "events": [...]} while desk guard is on
        self.deaths: list[float] = []
        self.reserve = None  # second connection holding RESERVE_CONTROL: no idle wandering while docked
        self.still_paused_until = 0.0  # built-in behaviors (actions, learn face) need the hold released
        from .actions import Actions
        self.actions = Actions(self)
        self.quiz = None
        self.presence = {"since": 0.0, "last": 0.0, "reminded": 0.0}
        self.mirror_on = False
        self.mirror_thread = None
        self.mirror_stop = threading.Event()
        self.cube_connected = False
        self._taps: list[float] = []
        for fn in (self._connect_loop, self._pet_loop, self._watch_loop, self._drive_loop, self._release_loop):
            threading.Thread(target=fn, daemon=True).start()

    # ------------------------------------------------------------ connection
    @property
    def connected(self) -> bool:
        return self._robot is not None

    @property
    def robot(self):
        if self._robot is None:
            raise VectorOffline(f"Vector isn't connected ({self.error or 'reconnecting'})")
        return _Guard(self._robot, self)

    @property
    def raw(self):
        return self._robot

    def call(self, fn, timeout: float, name: str = "call", kill_link: bool = False):
        """Run one robot call with a time limit. A slow call only fails itself; deciding that the whole
        link is dead is the heartbeat's job (tearing everything down on one slow call caused reconnect storms)."""
        fut = self.pool.submit(fn)
        try:
            return fut.result(timeout=timeout)
        except FutTimeout:
            if kill_link:
                self.mark_dead(f"{name} got no answer in {timeout:.0f}s")
                raise VectorOffline("Vector didn't answer. He may have dropped off Wi-Fi; reconnecting now.") from None
            log(f"slow: {name} took over {timeout:.0f}s")
            if name in QUEUED_ACTIONS:
                self.unstick = True
            self._wake.set()  # check the link now instead of in 10 s
            raise VectorOffline(f"Vector was slow to answer ({name}). Try again in a moment.") from None

    def mark_dead(self, why: str):
        if self._robot is not None:
            log(f"link lost: {why}")
            self.stats["drops"] = [t for t in self.stats["drops"] if time.time() - t < 86400] + [time.time()]
        self.cube_connected = False
        self.ctl_held = False
        self.error = why
        self.deaths = [t for t in self.deaths if time.time() - t < 120] + [time.time()]
        # hung calls keep their worker threads busy; start a fresh pool so new commands aren't stuck behind them
        old, self.pool = self.pool, ThreadPoolExecutor(max_workers=12, thread_name_prefix="vector-call")
        old.shutdown(wait=False, cancel_futures=True)
        self._drop_reserve()
        r, self._robot = self._robot, None
        if r is not None:
            threading.Thread(target=self._safe_disconnect, args=(r,), daemon=True).start()
        self._wake.set()

    @staticmethod
    def _safe_disconnect(r):
        try:
            r.disconnect()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _fd_check():
        """Safety net: if connections ever leak, restart cleanly (launchd brings us back) instead of dying slowly."""
        try:
            n = len(os.listdir("/dev/fd"))
        except OSError:
            return
        if n > 700:
            log(f"too many open connections ({n}); restarting the companion cleanly")
            os._exit(3)

    def _connect_loop(self):
        while True:
            self._fd_check()
            if self._robot is None:
                if len([t for t in self.deaths if time.time() - t < 120]) >= 4:
                    self.error = "connection keeps dropping; waiting 30 s before trying again"
                    self._wake.wait(30)
                    self._wake.clear()
                    self.deaths = []
                try:
                    self._connect()
                    self.error = None
                    log(f"connected to {self.serial}")
                    threading.Thread(target=self._connect_cube, daemon=True).start()
                except Exception as e:  # noqa: BLE001
                    self.error = f"{e.__class__.__name__}: {e}"[:200]
                    if "Too many open files" in str(e):
                        log("out of file handles; restarting the companion cleanly")
                        os._exit(3)
                    self._wake.wait(5)
                    self._wake.clear()
                    continue
            # heartbeat
            try:
                r = self._robot
                self.call(lambda: r.get_battery_state(), 6, "heartbeat")
                self.hb_misses = 0
            except Exception as e:  # noqa: BLE001
                self.hb_misses += 1
                if self.hb_misses >= 2:  # two misses in a row: the link really is gone
                    self.hb_misses = 0
                    self.mark_dead(f"heartbeat failed twice: {str(e)[:80]}")
                    continue
                self._wake.wait(2)
                self._wake.clear()
                continue
            self._sync_reserve()
            self._wake.wait(10)
            self._wake.clear()

    # ------------------------------------------------------------ keep him still while docked
    def _sync_reserve(self):
        want = (bool(safety().get("dock_lock")) and safety().get("keep_still", True) and self.connected
                and time.time() >= self.still_paused_until)
        if want and self.reserve is None:
            def hold():
                from anki_vector.behavior import ReserveBehaviorControl
                rc = ReserveBehaviorControl(self.serial, behavior_activation_timeout=8)
                rc.__enter__()
                return rc
            try:
                self.reserve = self.call(hold, 15, "reserve_control", kill_link=False)
                log("holding him still on the dock (no idle wandering)")
                threading.Thread(target=self._look_up, daemon=True).start()
            except Exception as e:  # noqa: BLE001
                log(f"couldn't reserve control: {e.__class__.__name__}")
        elif not want and self.reserve is not None:
            self._drop_reserve()
            log("released: idle behaviors back on")

    # ------------------------------------------------------------ camera on his face
    def start_mirror(self, seconds: float = 120) -> None:
        """Show what his camera sees on his face. Needs control the whole time, so the companion holds it."""
        self.stop_mirror()
        self.mirror_stop = threading.Event()
        self.mirror_thread = threading.Thread(target=self._mirror_loop, args=(min(float(seconds), 600),), daemon=True)
        self.mirror_thread.start()

    def stop_mirror(self) -> None:
        self.mirror_stop.set()
        t = self.mirror_thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=8)

    def _mirror_loop(self, seconds: float):
        try:
            with self.control(wait=8) as r:
                self.mirror_on = True
                r.vision.enable_display_camera_feed_on_face(True)
                log("camera on his face")
                end = time.time() + seconds
                while time.time() < end and not self.mirror_stop.is_set() and self.connected:
                    time.sleep(0.3)
                try:
                    r.vision.enable_display_camera_feed_on_face(False)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            log(f"camera on face failed: {e}")
        finally:
            self.mirror_on = False

    def pause_still(self, seconds: float) -> None:
        """Release the hold so a built-in behavior can run; it comes back by itself afterwards."""
        self.still_paused_until = max(self.still_paused_until, time.time() + max(5.0, min(float(seconds), 900)))
        self.release_now()  # his own behavior (learning a face, a game) needs his body too
        if self.reserve is not None:
            rc, self.reserve = self.reserve, None
            try:
                self.call(lambda: rc.__exit__(None, None, None), 4, "release_reserve", kill_link=False)
            except Exception:  # noqa: BLE001
                pass
            log(f"released the hold for {seconds:.0f} s so he can run a built-in behavior")
        threading.Timer(self.still_paused_until - time.time() + 0.5, self._sync_reserve).start()

    def _look_up(self):
        """While he sits still, tilt his head up so he can see (and recognize) you."""
        try:
            from anki_vector.util import degrees
            with self.control(wait=5) as r:
                r.behavior.set_head_angle(degrees(float(prefs().get("dock_head_angle", 25))))
        except Exception:  # noqa: BLE001
            pass

    def _drop_reserve(self):
        rc, self.reserve = self.reserve, None
        if rc is not None:
            threading.Thread(target=lambda: _quiet(rc.__exit__, None, None, None), daemon=True).start()

    def _connect(self):
        import anki_vector
        from anki_vector.events import Events
        from .sdk_setup import ensure_config
        self.serial = ensure_config(WIREPOD)
        r = anki_vector.Robot(self.serial, behavior_control_level=None, enable_face_detection=True,
                              enable_nav_map_feed=True, cache_animation_lists=False)
        fut = self.pool.submit(lambda: r.connect(timeout=15))
        try:
            fut.result(timeout=20)
        except FutTimeout:
            raise VectorOffline("connect timed out") from None
        try:
            fut2 = self.pool.submit(r.anim.load_animation_trigger_list)
            fut2.result(timeout=15)
            self.triggers = list(r.anim.anim_trigger_list)
        except Exception:  # noqa: BLE001
            self.triggers = self.triggers or []
        r.events.subscribe(self._on_face, Events.robot_observed_face)
        for ev, fn in (("wake_word", self._on_wake_word), ("user_intent", self._on_intent),
                       ("object_tapped", self._on_cube_tap)):
            if hasattr(Events, ev):
                r.events.subscribe(fn, getattr(Events, ev))
        self._robot = r

    # ------------------------------------------------------------ control
    class _Control:
        def __init__(self, outer: "Companion", wait: float):
            self.o, self.wait = outer, wait

        def __enter__(self):
            if self.o.mirror_on and threading.current_thread() is not self.o.mirror_thread:
                self.o.mirror_stop.set()  # anything else he needs to do ends the camera-on-face mode
            if not self.o.lock.acquire(timeout=self.wait):
                raise RuntimeError("Vector is busy with something else; try again in a moment.")
            try:
                r = self.o.robot
                if not self.o.has_control():  # asking for control takes ~1 s; keep it between commands
                    r.conn.request_control(timeout=6)
                    self.o.ctl_held = True
                self.o.ctl_last = time.time()
                return r
            except Exception:
                self.o.lock.release()
                raise

        def __exit__(self, *exc):
            self.o.ctl_last = time.time()  # released by _release_loop after a quiet moment, not right away
            try:
                if self.o.unstick:
                    self.o._clear_queue()
            finally:
                self.o.lock.release()
            return False

    CONTROL_IDLE = 15.0  # seconds of quiet before handing his body back to him

    def has_control(self) -> bool:
        if not self.ctl_held or self._robot is None:
            return False
        try:
            return bool(self._robot.conn._control_events.has_control)
        except Exception:  # noqa: BLE001
            return self.ctl_held

    def _clear_queue(self):
        """Something got stuck. Cancel what we sent and hand control back once, which makes him drop
        the stuck action, so the next command runs at once instead of waiting behind it."""
        self.unstick = False
        r = self._robot
        if r is None:
            return
        try:
            r.conn._cancel_active()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.call(lambda: r.conn.release_control(timeout=4), 6, "release_control")
        except Exception:  # noqa: BLE001
            pass
        self.ctl_held = False
        log("cleared a stuck action")

    def release_now(self):
        """Hand his body back immediately instead of after the idle timeout."""
        if not self.ctl_held or not self.lock.acquire(timeout=2):
            return
        try:
            if self.connected:
                self.robot.conn.release_control(timeout=4)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.ctl_held = False
            self.lock.release()

    def _release_loop(self):
        while True:
            time.sleep(1)
            if not self.ctl_held or time.time() - self.ctl_last < self.CONTROL_IDLE or self.mirror_on:
                continue
            if self.actions.bj and self.actions.bj.active and time.time() - self.ctl_last < 180:
                continue  # keep the cards on his face while you think
            if not self.lock.acquire(blocking=False):
                continue
            try:
                if self.connected and time.time() - self.ctl_last >= self.CONTROL_IDLE:
                    self.robot.conn.release_control(timeout=4)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self.ctl_held = False
                self.lock.release()

    def control(self, wait: float = 12):
        return Companion._Control(self, wait)

    # ------------------------------------------------------------ basic actions
    def show(self, img, seconds: float = 3.0, with_control=None):
        from anki_vector import screen as scr
        size = tuple(scr.dimensions()) if hasattr(scr, "dimensions") else (184, 96)
        img = img.convert("RGB")
        if img.size != size:
            img = img.resize(size)
        data = scr.convert_image_to_screen_data(img)

        def _do(r):
            r.screen.set_screen_with_image_data(data, seconds, interrupt_running=True)
            time.sleep(seconds)
        if with_control is not None:
            _do(with_control)
        else:
            with self.control() as r:
                _do(r)

    def put_screen(self, r, img, seconds: float):
        """Put an image on his face without waiting (caller holds control)."""
        from anki_vector import screen as scr
        size = tuple(scr.dimensions()) if hasattr(scr, "dimensions") else (184, 96)
        img = img.convert("RGB")
        if img.size != size:
            img = img.resize(size)
        r.screen.set_screen_with_image_data(scr.convert_image_to_screen_data(img), seconds, interrupt_running=True)

    def face(self, icon: str = "", text: str = "", seconds: float = 3.0):
        """Put an icon or words on his face and return right away (doesn't hold him up)."""
        img = face_art.text(text) if text else face_art.ICONS.get(icon, face_art.question)()
        with self.control(wait=4) as r:
            self.put_screen(r, img, seconds)
        self.ctl_last = time.time() + seconds  # keep control while it's showing

    def say(self, text: str):
        if self.voice_output() == "mac" and self.voice_engine() != "robot":
            self.speak(None, text)  # the Mac speaks: no need to wait for (or even reach) the robot
            return
        with self.control() as r:
            self.speak(r, text)

    # ------------------------------------------------------------ voice
    def voice_engine(self) -> str:
        """'piper' (neural Jarvis voice), 'mac' (a built-in Mac voice) or 'robot' (his own voice)."""
        from . import tts
        v = S.load()["voice"]
        eng = v.get("engine", "auto")
        if eng == "auto":
            jarvis = S.load().get("persona", {}).get("style") == "jarvis"
            eng = ("piper" if tts.ready() else "mac") if jarvis else "robot"
        if eng == "piper" and not tts.ready():
            eng = "mac"
        if eng == "mac" and not shutil.which("say"):
            eng = "robot"
        if eng != "robot" and self.voice_output() != "mac" and time.time() < self.audio_broken_until:
            eng = "robot"
        return eng

    def voice_output(self) -> str:
        """Where the voice comes out: 'mac' (Mac speakers, best sound), 'vector' (his speaker) or 'both'."""
        out = str(S.load()["voice"].get("output") or "mac")
        out = out if out in ("mac", "vector", "both") else "mac"
        if out != "vector" and not shutil.which("afplay"):
            out = "vector"  # no Mac audio player here
        return out

    def play_wav(self, path: str):
        """Play a sound file through his speaker (16 kHz mono WAV)."""
        with wave.open(path, "rb") as w:
            secs = w.getnframes() / float(w.getframerate())
        vol = max(0, min(100, int(S.load()["voice"].get("volume") or 80)))
        with self.control() as r:
            raw = self.raw
            self.speaking_until = time.time() + secs + 1
            self.call(lambda: raw.audio.stream_wav_file(path, vol), secs + 15, "play_sound")

    def _render(self, text: str, engine: str):
        """Text -> (int16 audio, sample rate) in the chosen voice."""
        import numpy as np
        if engine == "piper":
            from . import tts
            return tts.synth(text)
        v = S.load()["voice"]
        path = os.path.join(tempfile.gettempdir(), f"vector-say-{threading.get_ident()}.wav")
        subprocess.run(["say", "-v", str(v.get("mac_voice") or "Daniel"), "-r", str(int(v.get("rate") or 190)),
                        "-o", path, "--file-format=WAVE", "--data-format=LEI16@22050", text],
                       capture_output=True, timeout=30, check=True)
        with wave.open(path, "rb") as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()

    def _mac_wav(self, text: str) -> tuple[str, float]:
        """16 kHz WAV for his speaker (kept for callers that stream a file themselves)."""
        from . import tts
        audio, sr = self._render(text, "piper" if self.voice_engine() == "piper" else "mac")
        path = os.path.join(tempfile.gettempdir(), f"vector-say16-{threading.get_ident()}.wav")
        return path, tts.write_wav(path, tts.resample(audio, sr, 16000), 16000)

    def speak(self, r, text: str):
        """Say something in the chosen voice and place. Pass the robot from `with control()` when he should
        speak through his own speaker; with Mac output r may be None."""
        from . import tts
        text = (text or "").strip()
        if not text:
            return
        self.speaking_until = time.time() + 2 + len(text) / 12
        try:
            eng, out = self.voice_engine(), self.voice_output()
            if eng == "robot":
                if r is None:
                    with self.control() as r2:
                        r2.behavior.say_text(text)
                else:
                    r.behavior.say_text(text)
                return
            t0 = time.time()
            audio, sr = self._render(text, eng)
            t_synth = time.time() - t0
            secs = len(audio) / float(sr)
            self.speaking_until = time.time() + secs + 1
            player = None
            mac_done = False
            if out in ("mac", "both"):
                vol = max(0.0, min(2.0, float(S.load()["voice"].get("mac_volume") or 1.0)))
                if out == "mac" and self.connected and not self._face_busy():
                    threading.Thread(target=lambda: _safe(self.face, "talking", "", secs + 0.3), daemon=True).start()
                if out == "mac" and tts.play_on_mac(audio, sr, vol):
                    mac_done = True  # played in-process, device kept warm between sentences
                else:
                    hi = os.path.join(tempfile.gettempdir(), f"jarvis-{threading.get_ident()}.wav")
                    tts.write_wav(hi, audio, sr)
                    player = subprocess.Popen(["afplay", "-v", f"{vol:.2f}", hi],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not mac_done and out in ("vector", "both") and (r is not None or self.connected):
                try:
                    lo = os.path.join(tempfile.gettempdir(), f"vector-say16-{threading.get_ident()}.wav")
                    tts.write_wav(lo, tts.resample(audio, sr, 16000), 16000)
                    vol = max(0, min(100, int(S.load()["voice"].get("volume") or 80)))
                    raw = self.raw
                    self.call(lambda: raw.audio.stream_wav_file(lo, vol), secs + 15, "stream_wav_file")
                except VectorOffline:
                    if player is None:
                        raise
                except Exception as e:  # noqa: BLE001
                    if player is None:
                        self.audio_broken_until = time.time() + 600
                        log(f"voice through his speaker failed, using his own voice for 10 min: {e!r}"[:300])
                        (r or self.robot).behavior.say_text(text)
            if player is not None:
                try:
                    player.wait(timeout=secs + 10)
                except subprocess.TimeoutExpired:
                    player.kill()
            log(f"speech timing: voice {t_synth:.2f}s, total {time.time() - t0:.1f}s for {secs:.1f}s of audio ({eng} -> {out})")
        finally:
            self.speaking_until = time.time() + 0.6

    def _face_busy(self) -> bool:
        """Don't cover the cards, the camera view or a quiz with the talking face."""
        bj = self.actions.bj if getattr(self, "actions", None) else None
        return bool(self.mirror_on or (bj and bj.active) or (self.quiz and self.quiz.active))

    def announce(self, text: str, icon: str = "check"):
        img = face_art.ICONS.get(icon, face_art.check)()
        with self.control() as r:
            self.show(img, 1.4, with_control=r)
            self.speak(r, text)
            self.show(img, 2.0, with_control=r)

    STUCK_FILE = S.DATA_DIR / "stuck_animations.json"

    def find_trigger(self, *keywords: str) -> str | None:
        """First trigger that exists, skipping any that have hung on him before."""
        stuck = self.stuck_anims()
        for k in keywords:
            if k in self.triggers and k not in stuck:
                return k
        for k in keywords:
            for t in self.triggers:
                if k.lower() in t.lower() and t not in stuck:
                    return t
        return None

    def stuck_anims(self) -> set:
        if not hasattr(self, "_stuck"):
            self._stuck = set(_load(self.STUCK_FILE, []))
        return self._stuck

    def note_stuck(self, trig: str):
        self.stuck_anims().add(trig)
        log(f"animation {trig} hung on him; won't use it again")
        try:
            self.STUCK_FILE.write_text(json.dumps(sorted(self._stuck)))
        except OSError:
            pass

    def anim(self, name: str):
        trig = name if name in self.triggers else self.find_trigger(name)
        if not trig:
            raise ValueError(f"no animation matching {name!r}")
        if safety()["dock_lock"] and any(w in trig for w in DRIVING_ANIMS):
            raise PermissionError(f"{trig} drives him around; it's blocked while the dock lock is on.")
        with self.control() as r:
            play_trigger(r, trig)
        return trig

    def head(self, deg: float, wait: bool = True):
        if not wait:
            return self._move_later("head", max(-22.0, min(45.0, float(deg))))
        from anki_vector.util import degrees
        with self.control() as r:
            r.behavior.set_head_angle(degrees(max(-22.0, min(45.0, float(deg)))))

    def lift(self, height: float, wait: bool = True):
        if not wait:
            return self._move_later("lift", max(0.0, min(1.0, float(height))))
        with self.control() as r:
            r.behavior.set_lift_height(max(0.0, min(1.0, float(height))), duration=0.6)

    def _move_later(self, part: str, value: float):
        """Slider moves from the app: answer at once, and if you drag fast only the latest position is used."""
        self.move_target[part] = value
        if not self.move_busy.get(part):
            self.move_busy[part] = True
            threading.Thread(target=self._move_worker, args=(part,), daemon=True).start()

    def _move_worker(self, part: str):
        try:
            while part in self.move_target:
                v = self.move_target.pop(part)
                try:
                    (self.head if part == "head" else self.lift)(v)
                except Exception as e:  # noqa: BLE001
                    log(f"{part} move failed: {e}")
        finally:
            self.move_busy[part] = False

    def capture(self) -> bytes:
        r = self.robot
        try:
            img = r.camera.capture_single_image(enable_high_resolution=True)
        except TypeError:
            img = r.camera.capture_single_image()
        buf = io.BytesIO()
        img.raw_image.convert("RGB").save(buf, "JPEG", quality=92)
        return buf.getvalue()

    # ------------------------------------------------------------ sensors & map
    def sensors(self) -> dict:
        r = self.raw
        if r is None:
            raise VectorOffline(f"Vector isn't connected ({self.error})")
        out = {}
        try:
            st = r.status
            out.update(on_charger=bool(st.is_on_charger), cliff=bool(st.is_cliff_detected),
                       picked_up=bool(st.is_picked_up), held=bool(getattr(st, "is_being_held", False)))
        except Exception:  # noqa: BLE001
            pass
        try:
            p = r.proximity.last_sensor_reading
            out["distance_mm"] = round(p.distance.distance_mm) if p.found_object else None
        except Exception:  # noqa: BLE001
            out["distance_mm"] = None
        try:
            pose = r.pose
            out["pose"] = {"x": round(pose.position.x), "y": round(pose.position.y),
                           "deg": round(pose.rotation.angle_z.degrees)}
        except Exception:  # noqa: BLE001
            pass
        out["safety_event"] = self.safety_event
        return out

    def map_png(self, px: int = 360) -> bytes:
        """Top-down drawing of Vector's own navigation map: clear floor, obstacles, cliffs, him."""
        from PIL import Image, ImageDraw
        r = self.raw
        if r is None:
            raise VectorOffline("Vector isn't connected")
        grid = r.nav_map.latest_nav_map
        size, cx, cy = grid.size, grid.center.x, grid.center.y
        im = Image.new("RGB", (px, px), (18, 18, 20))
        d = ImageDraw.Draw(im)
        scale = px / size

        def to_px(x, y):
            return (px / 2 + (x - cx) * scale, px / 2 - (y - cy) * scale)

        colors = {"NAV_NODE_CLEAR_OF_CLIFF": (44, 60, 48), "NAV_NODE_CLEAR_OF_OBSTACLE": (34, 44, 40),
                  "NAV_NODE_CLIFF": (255, 69, 58), "NAV_NODE_OBSTACLE_PROXIMITY": (255, 159, 10),
                  "NAV_NODE_OBSTACLE_PROXIMITY_EXPLORED": (255, 159, 10),
                  "NAV_NODE_OBSTACLE_UNRECOGNIZED": (255, 159, 10), "NAV_NODE_OBSTACLE_CUBE": (100, 210, 255),
                  "NAV_NODE_INTERESTING_EDGE": (255, 214, 10)}
        try:
            from anki_vector.messaging import protocol
            namer = protocol.NavNodeContentType.Name
        except Exception:  # noqa: BLE001
            namer = str

        def walk(node):
            kids = getattr(node, "children", None)
            if kids:
                for k in kids:
                    walk(k)
                return
            try:
                name = namer(node.content)
            except Exception:  # noqa: BLE001
                name = str(node.content)
            col = colors.get(name)
            if col:
                x0, y0 = to_px(node.center.x - node.size / 2, node.center.y + node.size / 2)
                x1, y1 = to_px(node.center.x + node.size / 2, node.center.y - node.size / 2)
                d.rectangle([x0, y0, x1, y1], fill=col)
        walk(grid.root_node)
        try:  # Vector: dot + heading
            pose = r.pose
            x, y = to_px(pose.position.x, pose.position.y)
            a = pose.rotation.angle_z.radians
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(47, 214, 201))
            d.line([x, y, x + 18 * math.cos(a), y - 18 * math.sin(a)], fill=(47, 214, 201), width=3)
        except Exception:  # noqa: BLE001
            pass
        # 10 cm scale bar
        bar = 100 * scale
        d.line([10, px - 14, 10 + bar, px - 14], fill=(200, 200, 205), width=2)
        d.text((14 + bar, px - 22), "10 cm", fill=(200, 200, 205))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()

    # ------------------------------------------------------------ driving (safe)
    def drive(self, lw: float, rw: float):
        if safety()["dock_lock"] and (lw or rw):
            raise PermissionError("The dock lock is on: driving is off until his new battery is in.")
        self.drive_cmd = {"lw": max(-220.0, min(220.0, float(lw))), "rw": max(-220.0, min(220.0, float(rw))),
                          "at": time.time()}

    def _drive_loop(self):
        """Applies wheel commands at 10 Hz; stops on watchdog, cliffs and obstacles ahead."""
        applied = (0.0, 0.0)
        holding = False
        while True:
            time.sleep(0.1)
            r = self._robot
            cmd = self.drive_cmd
            want = (cmd["lw"], cmd["rw"]) if time.time() - cmd["at"] < 0.6 else (0.0, 0.0)
            if r is None:
                applied, holding = (0.0, 0.0), False
                continue
            if want != (0.0, 0.0):
                forward = want[0] + want[1] > 0
                try:
                    st = r.status
                    if st.is_cliff_detected and forward:
                        self.safety_event = {"at": time.time(), "why": "edge ahead"}
                        want = (0.0, 0.0)
                    elif forward:
                        p = r.proximity.last_sensor_reading
                        if p.found_object and p.distance.distance_mm < SAFE_STOP_MM:
                            self.safety_event = {"at": time.time(), "why": f"obstacle {p.distance.distance_mm:.0f} mm ahead"}
                            want = (0.0, 0.0)
                except Exception:  # noqa: BLE001
                    pass
            try:
                if want != (0.0, 0.0) and not holding:
                    if self.lock.acquire(timeout=2):
                        try:
                            self.robot.conn.request_control(timeout=6)
                            holding = True
                        except Exception:  # noqa: BLE001
                            self.lock.release()
                if want != applied and holding:
                    self.robot.motors.set_wheel_motors(want[0], want[1])
                    applied = want
                if holding and want == (0.0, 0.0) and time.time() - cmd["at"] > 3:
                    self.robot.conn.release_control(timeout=4)
                    holding = False
                    self.lock.release()
            except Exception:  # noqa: BLE001
                if holding:
                    holding = False
                    try:
                        self.lock.release()
                    except RuntimeError:
                        pass
                applied = (0.0, 0.0)

    def _watch_loop(self):
        """Dock lock: if he leaves the charger by himself, send him straight back."""
        off_since = None
        while True:
            time.sleep(0.5)
            r = self._robot
            if r is None or not safety()["dock_lock"] or self.returning:
                off_since = None
                continue
            try:
                st = r.status
                if st.is_on_charger or st.is_picked_up or getattr(st, "is_being_held", False):
                    off_since = None
                    continue
            except Exception:  # noqa: BLE001
                continue
            off_since = off_since or time.time()
            if time.time() - off_since > 1.0:
                threading.Thread(target=self._return_home, daemon=True).start()
                off_since = None

    def _return_home(self):
        self.returning = True
        try:
            log("dock lock: he left the charger, sending him back")
            with self.control(wait=5) as r:
                r.behavior.drive_on_charger()
        except Exception as e:  # noqa: BLE001
            log(f"dock lock: couldn't drive back ({e})")
        finally:
            self.returning = False

    # ------------------------------------------------------------ scanning
    def scan(self, mode="explain", question="", countdown=True, delay: float = 0) -> dict:
        if self.scanning:
            raise RuntimeError("Already scanning; give it a moment.")
        self.scanning = True
        try:
            if delay:
                time.sleep(min(float(delay), 10))
            with self.control() as r:
                from anki_vector.util import degrees
                r.behavior.set_head_angle(degrees(10))
                if countdown:
                    self.speak(r, "Hold it up in front of me. Three, two, one.")
                self.show(face_art.camera(), 0.8, with_control=r)
            jpeg = self.capture()
            try:
                with self.control(wait=4) as r:
                    t = self.find_trigger("KnowledgeGraphSearchingGetIn")
                    if t:
                        play_trigger(r, t)
            except Exception:  # noqa: BLE001
                pass
            # No control held while the AI thinks: Vector stays fully usable.
            res = vision.ask(jpeg, mode, question)
            res = vision.save(jpeg, res)
            mac_notify("Vector scanned it", res["say"])
            try:
                with self.control() as r:
                    t = self.find_trigger("KnowledgeGraphSearchingGetOutSuccess")
                    if t:
                        play_trigger(r, t)
                    self.show(face_art.check(), 1.2, with_control=r)
                    self.speak(r, res["say"])
            except Exception:  # noqa: BLE001
                pass
            log(f"scan {mode}: {res['say']}")
            return res
        except Exception as e:  # noqa: BLE001
            log(f"scan failed: {e}")
            try:
                t = self.find_trigger("KnowledgeGraphSearchingFail")
                if t:
                    self.anim(t)
                self.say("Sorry, I couldn't scan that." + (" " + str(e)[:120] if "vision AI" in str(e) else ""))
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            self.scanning = False

    # ------------------------------------------------------------ focus timer
    def start_focus(self, minutes: int | None = None, goal: str = ""):
        minutes = max(1, int(minutes or prefs()["focus_minutes"]))
        self.focus_id += 1
        fid = self.focus_id
        self.focus = {"end": time.time() + minutes * 60, "total": minutes, "id": fid, "goal": goal.strip(),
                      "start": time.time()}
        threading.Thread(target=self._focus_loop, args=(fid, minutes), daemon=True).start()
        self._save_focus()
        return {k: v for k, v in self.focus.items() if k != "id"}

    FOCUS_FILE = S.DATA_DIR / "focus.json"

    def _save_focus(self):
        try:
            f = self.focus
            self.FOCUS_FILE.write_text(json.dumps({k: v for k, v in f.items() if k != "id"} if f else {}))
        except OSError:
            pass

    def resume_focus(self):
        """A restart (update, crash, Mac sleep) shouldn't lose a study session that's still running."""
        f = _load(self.FOCUS_FILE, {})
        left = f.get("end", 0) - time.time()
        if left > 30:
            self.focus_id += 1
            fid = self.focus_id
            self.focus = {**f, "id": fid, "resumed": True}
            threading.Thread(target=self._focus_loop, args=(fid, int(f.get("total", 25))), daemon=True).start()
            log(f"resumed a focus timer with {int(left // 60)} min left")

    def stop_focus(self):
        f = self.focus
        if f:
            done = (time.time() - f["start"]) / 60
            if done >= 5:
                log_study(int(done), f.get("goal", ""), finished=False)
        self.focus = None
        self.focus_id += 1
        self._save_focus()

    def _focus_loop(self, fid: int, total: int):
        goal = (self.focus or {}).get("goal", "")
        jarvis = S.load().get("persona", {}).get("style") == "jarvis"
        try:
            if (self.focus or {}).get("resumed"):
                raise StopIteration  # picked up after a restart: no new announcement
            with self.control() as r:
                self.show(face_art.timer(total, total), 3, with_control=r)
                self.speak(r, f"{total} minutes on {goal}. Go get it." if goal else f"{total} minute focus timer. Go get it.")
        except StopIteration:
            pass
        except Exception as e:  # noqa: BLE001
            log(f"focus start display failed: {e}")
        shown = total
        halfway_said = total < 10
        while self.focus and self.focus["id"] == fid:
            left = self.focus["end"] - time.time()
            if left <= 0:
                break
            mins = int((left + 59) // 60)
            frac = left / (total * 60)
            color = "green" if frac > 0.5 else "yellow" if frac > 0.2 else "red"
            if self.cube_connected and color != getattr(self, "_cube_shown", None):
                self._cube_shown = color
                self.cube_color(color)
            if not halfway_said and left <= total * 30:
                halfway_said = True
                line = (f"Halfway there{', sir' if jarvis else ''}. " +
                        (f"How's {goal} going? " if goal else "") + "Keep it up.")
                threading.Thread(target=lambda: _quiet(self.say, line), daemon=True).start()
            if prefs()["focus_checkins"] and mins % 5 == 0 and mins != shown:
                shown = mins
                try:
                    self.show(face_art.timer(mins, total), 3)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)
        self._cube_shown = None
        if not (self.focus and self.focus["id"] == fid):
            return
        self.focus = None
        self._save_focus()
        if self.cube_connected:
            threading.Thread(target=self._cube_celebrate, daemon=True).start()
        for attempt in range(3):  # Wi-Fi blips shouldn't eat the end of a timer
            try:
                with self.control() as r:
                    for name in ("TimerRing", "BlackJack_VictorWin"):
                        trig = self.find_trigger(name)
                        if trig:
                            play_trigger(r, trig)
                    self.show(face_art.check(), 2, with_control=r)
                    today = log_study(total, goal, finished=True)
                    self.speak(r, f"Time's up{', sir' if jarvis else ' ' + OWNER}! {total} minute{'s' if total != 1 else ''} "
                                  + (f"on {goal} " if goal else "") + f"done. That's {today} minute{'s' if today != 1 else ''} today. "
                                  + ("Did you finish it? " if goal else "") + "Take a five minute break.")
                break
            except Exception as e:  # noqa: BLE001
                log(f"focus end attempt {attempt + 1} failed: {e}")
                time.sleep(6)
        mac_notify("Focus timer done", f"{total} minutes. Take a break.")

    def _cube_celebrate(self):
        for _ in range(4):
            self.cube_color("white")
            time.sleep(0.4)
            self.cube_color(None)
            time.sleep(0.3)

    # ------------------------------------------------------------ petting
    def _pet_loop(self):
        touching_since = None
        while True:
            time.sleep(0.15)
            r = self._robot
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
            with self.control(wait=3) as r:
                for s in (0.8, 1.0, 1.1, 1.0):
                    self.show(face_art.heart(s), 0.35, with_control=r)
                trig = self.find_trigger("PettingLevel4", "PettingLevel3", "Feedback_GoodRobot")
                if trig:
                    play_trigger(r, trig)
            log("pet: hearts")
        except Exception as e:  # noqa: BLE001
            log(f"pet reaction skipped: {e}")

    # ------------------------------------------------------------ hearing + network stats
    def _on_wake_word(self, robot, event_type, event, *a):
        try:
            if getattr(event, "WhichOneof", None) and event.WhichOneof("wake_word_type") == "wake_word_end":
                return
        except Exception:  # noqa: BLE001
            pass
        self.stats["wake_words"] = [t for t in self.stats["wake_words"] if time.time() - t < 86400] + [time.time()]

    def _on_intent(self, robot, event_type, event, *a):
        name = str(getattr(event, "intent_id", "") or getattr(event, "intent", "") or "")
        self.stats["intents"] = (self.stats["intents"] + [(time.time(), name)])[-50:]

    def stats_summary(self) -> dict:
        now = time.time()
        drops = [t for t in self.stats["drops"] if now - t < 86400]
        wakes = [t for t in self.stats["wake_words"] if now - t < 86400]
        hour = [t for t in drops if now - t < 3600]
        verdict = ("Connection looks steady." if not hour else
                   f"He dropped off Wi-Fi {len(hour)} time{'s' if len(hour) != 1 else ''} in the last hour. "
                   "Move his charger closer to the router, or run WirePod on a wired computer.")
        return {"connected": self.connected, "drops_24h": len(drops), "drops_1h": len(hour),
                "last_drops": [datetime.fromtimestamp(t).strftime("%-I:%M %p") for t in drops[-6:]],
                "wake_words_24h": len(wakes),
                "last_wake": datetime.fromtimestamp(wakes[-1]).strftime("%-I:%M:%S %p") if wakes else None,
                "cube": self.cube_connected, "cube_taps": self.stats["taps"],
                "voice": self.voice_engine(), "verdict": verdict,
                "uptime_min": int((now - self.stats["since"]) / 60)}

    # ------------------------------------------------------------ cube as a desk button
    def _connect_cube(self):
        if not prefs().get("cube_button", True) or self.cube_connected:
            return
        if time.time() < getattr(self, "cube_retry_at", 0):
            return  # a failed Bluetooth search also slows his Wi-Fi, so don't retry on every reconnect
        time.sleep(8)
        try:
            raw = self.raw
            with self.control(wait=6):
                pass  # just make sure we hold control; don't block every other command during the search
            self.cube_pool.submit(raw.world.connect_cube).result(timeout=25)
            cube = raw.world.connected_light_cube
            self.cube_connected = bool(cube and cube.is_connected)
            if self.cube_connected:
                log("cube connected: tap = focus timer, double tap = status report")
                self.cube_color("blue", 2)
        except Exception as e:  # noqa: BLE001
            self.cube_retry_at = time.time() + 600
            log(f"cube not connected ({e.__class__.__name__}); will try again in 10 min (or tap Connect on the Desk Guard & Cube page)")

    def cube_color(self, color: str | None, seconds: float = 0):
        """Light the cube: green/yellow/red/blue/white, or None for off."""
        try:
            from anki_vector import lights
            cube = self.raw.world.connected_light_cube if self.raw else None
            if not cube or not cube.is_connected:
                return
            if color is None:
                self.cube_pool.submit(cube.set_lights_off).result(timeout=8)
            else:
                light = getattr(lights, f"{color}_light", lights.white_light)
                self.cube_pool.submit(cube.set_lights, light).result(timeout=8)
                if seconds:
                    threading.Timer(seconds, lambda: self.cube_color(None) if not self.focus else None).start()
        except Exception:  # noqa: BLE001
            pass

    def _on_cube_tap(self, robot, event_type, event, *a):
        now = time.time()
        if self._taps and now - self._taps[-1] < 0.25:
            return  # one physical tap often reports twice
        self._taps.append(now)
        self.stats["taps"] += 1
        if len(self._taps) == 1:
            threading.Thread(target=self._resolve_taps, daemon=True).start()

    def _resolve_taps(self):
        time.sleep(0.8)
        taps, self._taps = len(self._taps), []
        try:
            if self.actions.bj and self.actions.bj.active:  # in a game: tap = hit, double tap = stand
                self.actions.run("bj_stand" if taps >= 2 else "bj_hit")
                return
            if taps >= 2:
                from .brain import status_report
                self.say(status_report())
            elif self.focus:
                left = int((self.focus["end"] - time.time() + 59) // 60)
                self.stop_focus()
                self.cube_color(None)
                self.say(f"Focus timer stopped with {left} minute{'s' if left != 1 else ''} left.")
            else:
                self.start_focus()
        except Exception as e:  # noqa: BLE001
            log(f"cube tap action failed: {e}")

    # ------------------------------------------------------------ desk guard
    def start_guard(self) -> dict:
        if self.guard:
            return self.guard_info()
        self.guard = {"since": time.time(), "events": [], "id": int(time.time())}
        threading.Thread(target=self._guard_loop, args=(self.guard["id"],), daemon=True).start()
        try:
            from anki_vector.util import degrees
            jarvis = S.load().get("persona", {}).get("style") == "jarvis"
            with self.control(wait=5) as r:
                r.behavior.set_head_angle(degrees(8))
                self.show(face_art.text("GUARD ON"), 1.5, with_control=r)
                self.speak(r, "Desk guard on. I'll keep watch, sir." if jarvis else "Guard mode on. I'll watch your desk.")
        except Exception as e:  # noqa: BLE001
            log(f"guard start announce skipped: {e}")
        log("desk guard on")
        return self.guard_info()

    def stop_guard(self, report: bool = False) -> dict:
        g, self.guard = self.guard, None
        if not g:
            return {"on": False}
        n = len(g["events"])
        log(f"desk guard off ({n} events)")
        if report:
            jarvis = S.load().get("persona", {}).get("style") == "jarvis"
            if n == 0:
                msg = "Welcome back, sir. All quiet while you were away." if jarvis else f"Welcome back {OWNER}! All quiet while you were gone."
            else:
                first = datetime.fromtimestamp(g["events"][0]["at"]).strftime("%-I:%M")
                msg = (f"Welcome back{', sir' if jarvis else ' ' + OWNER}. I saw movement at your desk {n} "
                       f"time{'s' if n != 1 else ''}, first at {first}. The photos are in the app.")
            try:
                self.say(msg)
            except Exception:  # noqa: BLE001
                pass
        return {"on": False, "events": g["events"]}

    def guard_info(self) -> dict:
        g = self.guard
        return {"on": bool(g), "since": g["since"] if g else None, "events": g["events"][-20:] if g else []}

    GUARD_DIR = S.DATA_DIR / "guard"

    def _guard_loop(self, gid: int):
        from PIL import Image, ImageChops, ImageStat
        prev, last_alert, fails = None, 0.0, 0
        while self.guard and self.guard["id"] == gid:
            time.sleep(1.5)
            g = self.guard
            if not g or g["id"] != gid:
                return
            if time.time() - g["since"] > 12 * 3600:
                log("desk guard: 12 hours up, turning it off")
                self.stop_guard()
                return
            if fails >= 3:
                log("desk guard paused: his camera isn't answering (he may be asleep)")
                mac_notify("Vector desk guard", "Paused: his camera stopped answering. Turn it on again from the app.")
                self.stop_guard()
                return
            if not self.connected or time.time() < self.speaking_until:
                prev = None
                continue
            raw = self.raw
            try:
                st = raw.status
                if getattr(st, "are_motors_moving", False) or getattr(st, "is_animating", False):
                    prev = None  # he's moving his own head: not an intruder
                    continue
                img = self.call(lambda: raw.camera.capture_single_image().raw_image, 8, "guard_capture",
                                kill_link=False)
                fails = 0
            except VectorOffline:
                fails += 1
                prev = None
                continue
            except Exception:  # noqa: BLE001
                prev = None
                continue
            small = img.convert("L").resize((64, 36))
            if prev is not None:
                diff = ImageStat.Stat(ImageChops.difference(small, prev)).mean[0]
                if diff > 10 and time.time() - last_alert > 20:
                    last_alert = time.time()
                    ev = {"at": time.time(), "kind": "motion", "score": round(diff, 1), "photo": None}
                    if S.load()["guard"].get("save_photos", True):
                        self.GUARD_DIR.mkdir(parents=True, exist_ok=True)
                        name = datetime.now().strftime("%Y%m%d-%H%M%S") + ".jpg"
                        img.convert("RGB").save(self.GUARD_DIR / name, quality=85)
                        ev["photo"] = name
                    if self.guard and self.guard["id"] == gid:
                        self.guard["events"].append(ev)
                    log(f"guard: movement (score {diff:.0f})")
                    if S.load()["guard"].get("notify", True):
                        mac_notify("Vector desk guard", f"Movement at your desk at {datetime.now():%-I:%M %p}")
            prev = small

    # ------------------------------------------------------------ greetings
    def _on_face(self, robot, event_type, event, *a):
        try:
            name = (getattr(event, "name", "") or "").strip()
        except Exception:  # noqa: BLE001
            return
        if time.time() < self.still_paused_until and not (self.actions.bj and self.actions.bj.active) \
                and not (self.quiz and self.quiz.active):
            return  # one of his own behaviors is running (e.g. learning a face): don't talk over it
        self._presence()
        if self.guard and name.lower() == OWNER.lower():
            self.last_greet[name] = time.time()
            threading.Thread(target=self.stop_guard, args=(True,), daemon=True).start()
            return
        if not name or not prefs()["greetings"] or self.scanning or self.focus:
            return
        now = time.time()
        if now - self.last_greet.get(name, 0) < 4 * 3600:
            return
        self.last_greet[name] = now
        threading.Thread(target=self._greet, args=(name,), daemon=True).start()

    def _presence(self):
        """Seeing a face at the desk = you're there. Long stretches get a stand-up reminder; late nights a nudge."""
        now = time.time()
        p = self.presence
        if now - p["last"] > 600:  # away 10+ minutes: a new sitting starts
            p["since"] = now
        p["last"] = now
        c = prefs()
        busy = (self.focus or (self.quiz and self.quiz.active) or (self.actions.bj and self.actions.bj.active)
                or now < self.speaking_until or self.guard or S.in_quiet_hours())
        if busy:
            return
        jarvis = S.load().get("persona", {}).get("style") == "jarvis"
        mins = int(c.get("stretch_minutes", 50))
        if c.get("stretch_reminders", True) and now - p["since"] > mins * 60 and now - p["reminded"] > mins * 60:
            p["reminded"] = now
            msg = (f"You've been at your desk for {mins} minutes{', sir' if jarvis else ''}. "
                   "Stand up, stretch, and grab some water.")
            threading.Thread(target=lambda: _quiet(self.say, msg), daemon=True).start()
            log("stretch reminder")
            return
        hour = datetime.now().hour
        if c.get("bedtime_nudge", True) and (hour >= 23 or hour < 4) and p.get("nudged") != datetime.now().date():
            p["nudged"] = datetime.now().date()
            msg = ("It's getting late, sir. Shall we wrap up for tonight?" if jarvis
                   else "It's getting late. Maybe wrap up soon so you're fresh tomorrow?")
            threading.Thread(target=lambda: _quiet(self.say, msg), daemon=True).start()

    def greeting_text(self, name: str) -> str:
        now = datetime.now()
        is_owner = name.lower() == OWNER.lower()
        if is_owner and prefs()["morning_briefing"] and 5 <= now.hour < 11 and self.briefed_on != now.date():
            self.briefed_on = now.date()
            from .brain import briefing
            return briefing()
        style = S.load().get("persona", {}).get("style", "vector")
        if is_owner and style == "jarvis":
            return "Welcome back, sir." + (" Shall I start a focus timer?" if 17 <= now.hour < 23 else "")
        if 17 <= now.hour < 23:
            return f"Welcome back {name}!" + (" Want me to start a focus timer?" if is_owner else "")
        return f"Hi {name}!"

    def _greet(self, name: str):
        try:
            text = self.greeting_text(name)
            with self.control(wait=4) as r:
                trig = self.find_trigger("GreetAfterLongTime", "OnboardingReactToFaceHappy", "ReactToGreeting")
                if trig and len(text) < 40:
                    play_trigger(r, trig)
                self.speak(r, text)
            log(f"greet {name}: {text}")
        except Exception as e:  # noqa: BLE001
            log(f"greet skipped: {e}")


# animations that drive him off the charger (blocked while the dock lock is on)
DRIVING_ANIMS = ("Drive", "Explore", "Pounce", "Wheelie", "FetchCube", "RollBlock", "PickupCube",
                 "ComeHere", "PlaceCube", "DanceBeat", "BumpObject")


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


REMINDERS_FILE = S.DATA_DIR / "reminders.json"


class Reminders:
    """Spoken reminders and timers ('remind me to email Mr. K in 20 minutes', 'set a timer for 10 minutes').
    Saved to disk so a restart doesn't lose them. Also gives a heads-up in the evening about Canvas work due
    tomorrow (once a day, off in quiet hours)."""

    def __init__(self, comp: "Companion"):
        self.c = comp
        self.items = _load(REMINDERS_FILE, [])
        self.lock = threading.Lock()
        self.nudged_on = None
        threading.Thread(target=self._loop, daemon=True).start()

    def _save(self):
        try:
            REMINDERS_FILE.write_text(json.dumps(self.items))
        except OSError:
            pass

    def add(self, text: str, at: float) -> dict:
        r = {"id": int(time.time() * 1000), "text": text.strip()[:200], "at": float(at)}
        with self.lock:
            self.items = sorted(self.items + [r], key=lambda x: x["at"])
            self._save()
        log(f"reminder set for {datetime.fromtimestamp(at):%a %-I:%M %p}: {r['text']}")
        return r

    def clear(self):
        with self.lock:
            self.items = []
            self._save()

    def _loop(self):
        while True:
            time.sleep(5)
            now = time.time()
            with self.lock:
                due = [r for r in self.items if r["at"] <= now]
                if due:
                    self.items = [r for r in self.items if r["at"] > now]
                    self._save()
            for r in due:
                self._fire(r)
            try:
                self._evening_heads_up()
            except Exception as e:  # noqa: BLE001
                log(f"heads-up skipped: {e}")

    def _fire(self, r: dict):
        jarvis = S.load().get("persona", {}).get("style") == "jarvis"
        text = r["text"]
        msg = (f"{text}, sir." if text.lower().startswith("timer") else f"Reminder{', sir' if jarvis else ''}: {text}.")
        mac_notify("Jarvis" if jarvis else "Vector", msg)
        late = time.time() - r["at"] > 600  # Mac was asleep: say it happened, don't pretend it's on time
        try:
            self.c.announce(("Earlier: " if late else "") + msg, "check")
        except Exception:  # noqa: BLE001
            _quiet(self.c.say, msg)

    def _evening_heads_up(self):
        c = prefs()
        if not c.get("due_heads_up", True) or S.in_quiet_hours():
            return
        now = datetime.now()
        at = str(c.get("due_heads_up_at", "19:30"))
        hh, mm = (int(x) for x in at.split(":"))
        if self.nudged_on == now.date() or (now.hour, now.minute) < (hh, mm) or now.hour >= 22:
            return
        self.nudged_on = now.date()
        from . import canvas
        if not canvas.connected():
            return
        tomorrow = canvas.now().date() + timedelta(days=1)
        items = [i for i in canvas.upcoming(2) if not i["done"] and not i.get("overdue") and i["due"].date() == tomorrow]
        if not items:
            return
        jarvis = S.load().get("persona", {}).get("style") == "jarvis"
        names = "; ".join(canvas._clean_title(i["title"]) for i in items[:3])
        msg = (f"A heads-up{', sir' if jarvis else ''}: due tomorrow on Canvas, {names}."
               + (f" Plus {len(items) - 3} more." if len(items) > 3 else ""))
        log("evening Canvas heads-up")
        mac_notify("Due tomorrow", names)
        _quiet(self.c.say, msg)


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
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:47800")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return {}

    def _err(self, e: Exception):
        code = 423 if isinstance(e, PermissionError) else 503
        return self._send(code, {"ok": False, "error": str(e), "offline": isinstance(e, VectorOffline)})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/health":
                f = COMP.focus
                return self._send(200, {"connected": COMP.connected, "serial": COMP.serial, "error": COMP.error,
                                        "scanning": COMP.scanning, "triggers": len(COMP.triggers),
                                        "focus": {"left_s": int(f["end"] - time.time()), "total": f["total"], "goal": f.get("goal", "")} if f else None,
                                        "mirror": COMP.mirror_on, "holding_still": COMP.reserve is not None,
                                        "quiz": bool(COMP.quiz and COMP.quiz.active),
                                        "quiz_state": ({"q": COMP.quiz.i + 1, "of": len(COMP.quiz.qs), "score": COMP.quiz.score,
                                                        "topic": COMP.quiz.topic} if COMP.quiz and COMP.quiz.active else None),
                                        "blackjack": bool(COMP.actions.bj and COMP.actions.bj.active),
                                        "game": COMP.actions.bj.state() if COMP.actions.bj else None,
                                        "prefs": prefs(), "safety": safety(), "guard": bool(COMP.guard),
                                        "speaking": time.time() < COMP.speaking_until, "voice": COMP.voice_engine(),
                                        "cube": COMP.cube_connected})
            if u.path == "/reminders":
                return self._send(200, {"reminders": COMP.reminders.items})
            if u.path == "/stats":
                return self._send(200, COMP.stats_summary())
            if u.path == "/guard":
                return self._send(200, COMP.guard_info())
            if u.path.startswith("/guard_photo/"):
                return self._send(200, (Companion.GUARD_DIR / os.path.basename(u.path)).read_bytes(), "image/jpeg")
            if u.path == "/sensors":
                return self._send(200, COMP.sensors())
            if u.path == "/map.png":
                png = None
                if time.time() - getattr(COMP, "map_failed_at", 0) > 120:  # don't ask him every 3 s when there's no map
                    try:
                        png = COMP.call(COMP.map_png, 4, "map")
                    except Exception:  # noqa: BLE001  (no map until he drives around)
                        COMP.map_failed_at = time.time()
                png = png or _no_map_png()
                return self._send(200, png, "image/png")
            if u.path == "/capture":
                return self._send(200, COMP.capture(), "image/jpeg")
            if u.path == "/anims":
                lock = safety()["dock_lock"]
                return self._send(200, [t for t in COMP.triggers if not (lock and any(w in t for w in DRIVING_ANIMS))])
            if u.path == "/scans":
                return self._send(200, vision.history())
            if u.path.startswith("/scan_image/"):
                sid = os.path.basename(u.path)
                return self._send(200, (vision.SCANS / f"{sid}.jpg").read_bytes(), "image/jpeg")
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._err(e)

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
                COMP.head(b.get("deg", 10), wait=bool(b.get("wait", False)))
            elif u.path == "/lift":
                COMP.lift(b.get("height", 0), wait=bool(b.get("wait", False)))
            elif u.path == "/drive":
                COMP.drive(b.get("lw", 0), b.get("rw", 0))
            elif u.path == "/stop":
                COMP.drive_cmd = {"lw": 0.0, "rw": 0.0, "at": time.time()}
            elif u.path == "/dock":
                with COMP.control() as r:
                    r.behavior.drive_on_charger()
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
                return self._send(200, {"ok": True, "focus": COMP.start_focus(b.get("minutes"), str(b.get("goal", "")))})
            elif u.path == "/greet_test":
                return self._send(200, {"ok": True, "text": COMP.greeting_text(OWNER)})
            elif u.path == "/guard":
                info = COMP.start_guard() if b.get("on", True) else COMP.stop_guard(bool(b.get("report")))
                return self._send(200, {"ok": True, **info})
            elif u.path == "/cube":
                if b.get("connect"):
                    COMP.cube_connected = False
                    COMP.cube_retry_at = 0
                    threading.Thread(target=COMP._connect_cube, daemon=True).start()
                else:
                    COMP.cube_color(b.get("color"), float(b.get("seconds", 3)))
            elif u.path == "/play":
                path = str(b.get("path", ""))
                threading.Thread(target=lambda: _safe(COMP.play_wav, path), daemon=True).start()
            elif u.path == "/quiz":
                from .quiz import Quiz
                COMP.quiz = Quiz(COMP, str(b.get("topic", "")))
                threading.Thread(target=lambda: _safe(COMP.quiz.start), daemon=True).start()
            elif u.path == "/quiz_answer":
                q = COMP.quiz
                if not (q and q.active):
                    return self._send(200, {"ok": True, "active": False})
                threading.Thread(target=lambda: _safe(q.answer, str(b.get("text", ""))), daemon=True).start()
            elif u.path == "/do":
                return self._send(200, {"ok": True, **COMP.actions.run(str(b.get("action", "")))})
            elif u.path == "/mirror":
                if b.get("on", True):
                    COMP.start_mirror(float(b.get("seconds", 120)))
                else:
                    COMP.stop_mirror()
            elif u.path == "/still":
                COMP.pause_still(float(b.get("pause", 45)))
            elif u.path == "/remind":
                if b.get("clear"):
                    COMP.reminders.clear()
                    return self._send(200, {"ok": True})
                return self._send(200, {"ok": True, **COMP.reminders.add(str(b.get("text", "")), float(b["at"]))})
            elif u.path == "/relaunch_app":
                pid, app = int(b.get("pid", 0)), str(b.get("app", "/Applications/Vector.app"))
                if not app.endswith(".app"):
                    return self._send(400, {"error": "bad app"})

                def relaunch():
                    for _ in range(100):  # up to 20 s for the old window to close
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            break
                        time.sleep(0.2)
                    time.sleep(0.8)
                    for attempt in range(3):
                        r = subprocess.run(["open", app], capture_output=True, text=True, timeout=20)
                        log(f"reopened the app (try {attempt + 1}): rc={r.returncode} {r.stderr.strip()[:120]}")
                        if r.returncode == 0:
                            break
                        time.sleep(2)
                threading.Thread(target=relaunch, daemon=True).start()
            elif u.path == "/reconnect":
                COMP.mark_dead("manual reconnect")
            else:
                return self._send(404, {"error": "not found"})
            return self._send(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            return self._err(e)


STUDY_LOG = S.DATA_DIR / "study_log.json"


def log_study(minutes: int, goal: str = "", finished: bool = True) -> int:
    """Add a study session; returns today's total minutes."""
    data = _load(STUDY_LOG, {})
    day = datetime.now().strftime("%Y-%m-%d")
    d = data.setdefault(day, {"minutes": 0, "sessions": []})
    d["minutes"] += int(minutes)
    d["sessions"].append({"at": datetime.now().strftime("%H:%M"), "minutes": int(minutes), "goal": goal,
                          "finished": finished})
    try:
        STUDY_LOG.write_text(json.dumps(data, indent=1))
    except OSError:
        pass
    return d["minutes"]


def study_today() -> int:
    return int(_load(STUDY_LOG, {}).get(datetime.now().strftime("%Y-%m-%d"), {}).get("minutes", 0))


_NO_MAP = None


def _no_map_png() -> bytes:
    global _NO_MAP
    if _NO_MAP is None:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (360, 360), (28, 28, 30))
        d = ImageDraw.Draw(im)
        f = face_art._font(17)
        for i, line in enumerate(("No map yet", "He maps your desk as he drives.", "Driving is off until his new battery.")):
            w = d.textlength(line, font=f)
            d.text(((360 - w) / 2, 150 + i * 26), line, fill=(235, 235, 240) if i == 0 else (150, 150, 158), font=f)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        _NO_MAP = buf.getvalue()
    return _NO_MAP


def _quiet(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001
        pass


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001
        log(traceback.format_exc(limit=3))


def _quiet_sdk_logs():
    """The SDK adds its own INFO handlers (every sound it plays); keep only warnings, and keep the
    launch agent's .out files from growing forever (one had reached 1.8 GB)."""
    for name in list(logging.root.manager.loggerDict):
        if not name.startswith("vector_companion"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.WARNING)
            for h in lg.handlers:
                h.setLevel(logging.WARNING)
    for f in (S.ROOT / "logs").glob("*.out"):
        try:
            if f.stat().st_size > 20_000_000:
                with open(f, "rb") as fh:
                    fh.seek(-500_000, 2)
                    tail = fh.read()
                with open(f, "r+b") as fh:
                    fh.truncate(0)
                    fh.write(b"[trimmed]\n" + tail)
        except OSError:
            pass


def main():
    global COMP
    log("companion starting")
    COMP = Companion()
    COMP.reminders = Reminders(COMP)
    _quiet_sdk_logs()
    threading.Timer(20, _quiet_sdk_logs).start()  # again once the SDK has connected and added its loggers
    COMP.resume_focus()
    from . import tts
    threading.Thread(target=tts.warm, daemon=True).start()  # first sentence shouldn't wait for the voice to load
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[companion] http://127.0.0.1:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
