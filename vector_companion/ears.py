"""Vector Ears: say "Hey Jarvis" and your Mac's microphone does the listening.

Why: Vector's own wake word is fixed to "Hey Vector" (firmware) and his voice audio has to cross
Wi-Fi to WirePod, so it fails when his connection hiccups. This runs on the Mac instead:

  "Hey Jarvis"  ->  openWakeWord (free, offline)  ->  record until you stop talking
  ->  Whisper speech-to-text (offline)  ->  skills / AI brain  ->  Vector answers out loud
  ->  stays listening ~5 s for a follow-up, no wake word needed (like a real conversation)

Runs inside "Vector Ears.app" (so macOS asks once for the microphone). Status: ~/.vector-companion/ears.json
  python -m vector_companion.ears           run it
  python -m vector_companion.ears --setup   download the wake word + speech models
  python -m vector_companion.ears --test    say "Hey Jarvis" and print what it heard (no robot)
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

from . import config, settings as S

config.load_env()
SR = 16000
FRAME = 1280  # 80 ms, what openWakeWord expects
STATUS = S.DATA_DIR / "ears.json"
WHISPER = os.environ.get("EARS_WHISPER_MODEL", "small.en")
QUICK = os.environ.get("EARS_QUICK_MODEL", "tiny.en")  # tiny model that only checks "did he say Jarvis?"
WAKE_WORDS = {"jarvis": "Jarvis", "hey_jarvis": "Hey Jarvis", "hey_mycroft": "Hey Mycroft", "alexa": "Alexa"}
# how Whisper tends to spell "Jarvis" when it's said fast
NAME = re.compile(r"\b(jarvis|jarvas|jarvi|jervis|javis|jarviss|jaarvis|garvis|charvis|j\.a\.r\.v\.i\.s)\b", re.I)
END_QUIET = 7  # 80 ms frames of quiet that end a sentence (0.56 s)
MIC_OFF = re.compile(r"\b(stop listening|mic off|turn off (the |your )?(mic|microphone|listening)|mute (the |your )?(mic|microphone))\b", re.I)
STOP_WORDS = re.compile(r"^(never ?mind|stop|cancel|nothing|that'?s all|thanks?,? (that'?s all|jarvis)|thank you,? jarvis)\W*$", re.I)


def log(msg: str) -> None:
    S.log("ears", msg)


def strip_name(text: str) -> str:
    """'Hey Jarvis, what's the time?' / 'What's the time, Jarvis?' -> "What's the time?" """
    text = re.sub(r"^\W*((hey|ok|okay|hi|yo)[,.]?\s+)?" + NAME.pattern[2:-2].join(["(", ")"]) + r"\b[,.!?]?\s*", "", text, flags=re.I)
    text = re.sub(r"^\W*(hey,?\s+)?(mycroft|alexa)[,.!]?\s*", "", text, flags=re.I)
    text = re.sub(r"[,]?\s*" + NAME.pattern[2:-2].join(["(", ")"]) + r"\W*$", "", text, flags=re.I)
    return text.strip()


class Ears:
    def __init__(self, robot: bool = True):
        self.robot = robot
        self.q: queue.Queue = queue.Queue(maxsize=400)
        self.state = {"state": "starting", "heard": 0, "last_text": "", "last_reply": "", "error": "",
                      "at": time.time(), "wake_score": 0.0}
        self.history: list[dict] = []
        self.history_at = 0.0
        self.vector_busy_until = 0.0
        self.spans: list[tuple[float, float]] = []  # when he was talking (his voice in the mic)
        self.last_spoke = 0.0
        self.game = False
        self.handed_off = False
        self.noise = 200.0

    _prefs = (0.0, {})

    def prefs(self) -> dict:
        """Settings, re-read at most once a second (the loop runs 12x a second)."""
        if time.time() - self._prefs[0] > 1:
            self._prefs = (time.time(), S.load())
        return self._prefs[1]

    # ------------------------------------------------------------ status
    def set(self, **kw):
        self.state.update(kw, at=time.time())
        try:
            S.DATA_DIR.mkdir(parents=True, exist_ok=True)
            STATUS.write_text(json.dumps(self.state))
        except OSError:
            pass

    # ------------------------------------------------------------ models
    @staticmethod
    def setup() -> None:
        import openwakeword
        from openwakeword import utils
        print("   downloading the wake word models...")
        utils.download_models(model_names=[w for w in WAKE_WORDS if w != "jarvis"])
        print(f"   downloading the Whisper '{WHISPER}' speech model (about 470 MB, once)...")
        from faster_whisper import WhisperModel
        WhisperModel(WHISPER, device="cpu", compute_type="int8")
        WhisperModel(QUICK, device="cpu", compute_type="int8")
        print("   ears ready", openwakeword.__version__ if hasattr(openwakeword, "__version__") else "")

    @staticmethod
    def wake_word() -> str:
        w = str(S.load()["ears"].get("wake_word") or "jarvis")  # noqa
        return w if w in WAKE_WORDS else "jarvis"

    @staticmethod
    def _wake_model():
        from openwakeword.model import Model  # needs openwakeword 0.6+ (0.4 scores everything as 0)
        w = Ears.wake_word()
        return Model(wakeword_models=["hey_jarvis" if w == "jarvis" else w], inference_framework="onnx")

    def load(self):
        try:
            self.wake = self._wake_model()
        except Exception:  # noqa: BLE001  (first run: models not downloaded yet)
            self.setup()
            self.wake = self._wake_model()
        self.stt = None
        self.quick = None
        self._stt()  # load now so the first "Jarvis" isn't slow
        self._quick()
        import numpy as np
        self._stt().transcribe(np.zeros(SR, dtype=np.float32), language="en", beam_size=1)  # warm up

    def _stt(self):
        if self.stt is None:
            from faster_whisper import WhisperModel
            self.stt = WhisperModel(WHISPER, device="cpu", compute_type="int8", cpu_threads=4)
        return self.stt

    def _quick(self):
        if self.quick is None:
            try:
                from faster_whisper import WhisperModel
                self.quick = WhisperModel(QUICK, device="cpu", compute_type="int8", cpu_threads=2)
            except Exception as e:  # noqa: BLE001
                log(f"quick model unavailable ({e}); using the main one")
                self.quick = self._stt()
        return self.quick

    def heard_name(self, frames) -> bool:
        """Fast check on the first ~3 s of a sentence: was Jarvis said? (~0.1 s)"""
        import numpy as np
        audio = np.concatenate(frames[: int(3.2 * SR / FRAME)]).astype(np.float32) / 32768.0
        model = self._stt() if len(frames) * FRAME / SR < 1.6 else self._quick()  # a lone "Jarvis" needs the better ear
        segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                           condition_on_previous_text=False, without_timestamps=True)
        return bool(NAME.search(" ".join(x.text for x in segs)))

    # ------------------------------------------------------------ audio
    def _callback(self, indata, frames, t, status):
        try:
            self.q.put_nowait((time.time(), indata[:, 0].copy()))
        except queue.Full:
            pass

    def frame(self, timeout: float = 1.0):
        t, f = self.q.get(timeout=timeout)
        self.frame_t = t
        return f

    def busy(self) -> bool:
        """Was this audio captured while Jarvis was talking? (judged by when it was recorded, not when we
        got round to it, so a backlog of his own voice is never mistaken for you)"""
        t = getattr(self, "frame_t", time.time())
        return any(a <= t <= b for a, b in self.spans)

    def mark_busy(self, seconds: float):
        now = time.time()
        self.vector_busy_until = max(self.vector_busy_until, now + seconds)
        self.spans = (self.spans + [(now - 0.1, now + seconds)])[-20:]

    def drain(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    def rms(f) -> float:
        import numpy as np
        return float(np.sqrt(np.mean(f.astype(np.float32) ** 2)) + 1e-6)

    def record(self, wait_for_speech: float, first=None, force: bool = False) -> "list | None":
        """Collect frames until ~0.8 s of quiet after speech. None if nobody spoke within wait_for_speech."""
        frames = list(first or [])
        talk = max(self.noise * 2.0, 18.0)  # relative to this room's background noise (quiet mics are fine)
        started, quiet, t0 = bool(first), 0, time.time()
        while True:
            try:
                f = self.frame()
            except queue.Empty:
                continue
            if self.robot and self.busy():
                # that's Vector talking, not you: throw it away and give you the full window afterwards
                frames, started, quiet, t0 = [], False, 0, time.time()
                continue
            loud = self.rms(f) > talk
            if not started:
                if loud:
                    started = True
                    frames.append(f)
                elif time.time() - t0 > wait_for_speech:
                    return frames if force else None
                else:
                    frames = frames + [f] if force else (frames + [f])[-4:]  # keep a lead-in
                continue
            frames.append(f)
            quiet = 0 if loud else quiet + 1
            if quiet >= END_QUIET or len(frames) * FRAME / SR > 15:
                return frames

    def transcribe(self, frames, raw: bool = False) -> str:
        import numpy as np
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        segs, _ = self._stt().transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                         condition_on_previous_text=False, without_timestamps=True,
                                         initial_prompt="Jarvis, Vector, homework, study session, blackjack, AP Bio.")
        text = " ".join(s.text for s in segs).strip()
        if raw:
            return text
        text = strip_name(text)
        if re.fullmatch(r"(thank you|thanks for watching|you|bye|\.+|\W*)[.!]?", text, flags=re.I):
            return ""  # what Whisper "hears" in silence
        return text

    # ------------------------------------------------------------ robot side
    def _busy_watch(self):
        """Don't wake on Vector's own voice: mute while he's talking."""
        from .companion_client import call
        while True:
            try:
                h = call("/health", timeout=2)
                self.game = bool(h.get("quiz") or h.get("blackjack"))
                if h.get("speaking"):
                    now = time.time()
                    self.vector_busy_until = now + 0.8
                    self.last_spoke = now
                    if self.spans and self.spans[-1][1] >= now - 0.4:
                        self.spans[-1] = (self.spans[-1][0], now + 0.8)
                    else:
                        self.spans = (self.spans + [(now - 0.35, now + 0.8)])[-20:]
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)

    def cue(self):
        if self.prefs()["ears"].get("chime", True):
            subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        if self.robot:
            self.face("listening", 6)

    def face(self, icon: str, seconds: float):
        if not self.robot:
            return

        def show():
            from .companion_client import call
            try:
                call("/face", {"icon": icon, "seconds": seconds}, timeout=8)
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=show, daemon=True).start()

    can_trigger: "bool | None" = None  # can WirePod start his listening directly? (developer robots only)

    def hand_to_vector(self) -> bool:
        """Best case, same as "Hey Vector": he lights up and listens with his own microphones. That needs a
        developer-unlocked robot; on a regular Vector this returns False and the Mac listens instead,
        then sends him the same built-in commands "Hey Vector" would (blackjack, fist bump, sleep...)."""
        if self.can_trigger is False:
            return False
        from .wirepod import Vector
        try:
            v = Vector()
            v.timeout = 4
            out = v._req("trigger_wake_word")
            if "success" not in out.lower():
                raise RuntimeError(out[:80])
            self.can_trigger = True
            log("Hey Jarvis -> Vector is listening himself")
            self.set(state="Vector is listening", last_text="(handed to Vector)")
            self.mark_busy(12)
            return True
        except Exception as e:  # noqa: BLE001
            self.can_trigger = False
            log(f"this Vector can't be woken remotely ({str(e)[:80]}); the Mac will listen instead")
            return False

    def answer(self, text: str) -> None:
        """Think and talk at the same time: he starts on the first sentence while the rest is written."""
        from .voice import respond_stream, speak
        if time.time() - self.history_at > 180:
            self.history = []
        self.set(state="thinking", last_text=text)
        t0 = time.time()
        q: queue.Queue = queue.Queue()

        def produce():
            try:
                for part in respond_stream(text, self.history):
                    q.put(part)
            except Exception as e:  # noqa: BLE001
                log(f"answer failed: {e}")
                q.put("Sorry, something went wrong on my end.")
            q.put(None)
        threading.Thread(target=produce, daemon=True).start()
        parts, first_at = [], None
        while True:
            part = q.get()
            if part is None:
                break
            parts.append(part)
            if part.strip():
                first_at = first_at or time.time()
                self.set(state="speaking", last_reply=" ".join(parts))
                if self.robot:
                    speak(part)
                else:
                    print("   reply:", part)
        reply = " ".join(p for p in parts if p).strip()
        self.handed_off = not reply  # an action/game/quiz will talk by itself in a moment
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply or "(done)"}]
        self.history_at = time.time()
        self.mark_busy(0.8)
        log(f"heard: {text!r} -> {reply[:120]!r} (first words after {((first_at or time.time()) - t0):.1f}s, "
            f"done in {time.time() - t0:.1f}s)")

    # ------------------------------------------------------------ main loop
    def run(self):
        import numpy as np
        import sounddevice as sd
        self.set(state="loading models")
        self.load()
        if self.robot:
            threading.Thread(target=self._busy_watch, daemon=True).start()
        while True:  # keep going through mic unplugs, sleep/wake, etc.
            if not self.prefs()["ears"].get("enabled", True):
                # Mic off: the input stream is fully closed, so macOS shows no microphone indicator.
                self.set(state="mic off", level=0.0, peak=0.0, mic_silent=False, error="")
                time.sleep(1)
                continue
            try:
                with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME,
                                    callback=self._callback):
                    self.set(state=self.idle_state(), error="")
                    log(self.idle_state())
                    self._loop(np)
            except Exception as e:  # noqa: BLE001
                self.set(state="error", error=f"{e.__class__.__name__}: {e}"[:200])
                log(f"mic error, retrying in 5 s: {e}")
                time.sleep(5)
                try:  # the input device changed (AirPods, sleep/wake): start the audio system fresh
                    sd._terminate()
                    sd._initialize()
                except Exception:  # noqa: BLE001
                    pass

    def _loop(self, np):
        """Listen all the time (locally). Two ways in:
        - name mode ("Jarvis"): every sentence you say is checked by a tiny local model for the name, so
          "Jarvis, what's the time?" works in one breath, no "hey" and no pause;
        - wake-word mode ("Hey Jarvis" etc.): openWakeWord, then the chime, then you talk."""
        from collections import deque
        levels: list[float] = []
        loaded = self.wake_word()
        peak_score, peak_level, last_report, silent_since = 0.0, 0.0, time.time(), time.time()
        lead: deque = deque(maxlen=5)  # 0.4 s before you start, so the first syllable isn't clipped
        seg: list = []
        quiet, oww_hit, cued = 0, False, False
        prev, prev_end = [], 0.0  # the sentence before, in case you put the name at the end after a pause
        while True:
            if time.time() - last_report > 1.0:  # live meter for the app + silent-mic detection
                lvl = float(np.median(levels)) if levels else 0.0
                if peak_level > 3:
                    silent_since = time.time()
                silent = time.time() - silent_since > 8
                self.set(level=round(lvl, 1), peak=round(peak_level, 1), best_score=round(peak_score, 3),
                         mic_silent=silent,
                         error=("The microphone is sending silence. Open System Settings > Privacy & Security > "
                                "Microphone and turn on Vector Ears (or Terminal), then click Restart Ears.") if silent else "")
                peak_score, peak_level, last_report = 0.0, 0.0, time.time()
            p = self.prefs()["ears"]
            if p.get("wake_word", "jarvis") != loaded and p.get("wake_word") in WAKE_WORDS:
                loaded = p["wake_word"]
                self.wake = self._wake_model()
                self.set(state=self.idle_state())
            if not p.get("enabled", True):
                log("mic off")
                self.drain()
                return  # run() closes the stream and waits until it's switched back on
            try:
                f = self.frame()
            except queue.Empty:
                continue
            if self.busy():  # that's him talking
                self.wake.reset()
                seg, quiet, oww_hit, cued = [], 0, False, False
                lead.clear()
                continue
            r = self.rms(f)
            if not seg:
                levels = (levels + [r])[-60:]
                self.noise = float(np.median(levels))
            peak_level = max(peak_level, r)
            score = float(max(self.wake.predict(f).values(), default=0.0))
            peak_score = max(peak_score, score)
            sens = float(p.get("sensitivity", 0.5))
            fired = score >= 0.85 - 0.6 * sens
            name_mode = loaded == "jarvis"

            if not name_mode:
                if not fired:
                    continue
                self.set(wake_score=round(score, 2), heard=self.state["heard"] + 1, state="hearing you")
                self.cue()
                frames = self.record(wait_for_speech=4.0, force=True)
                self.conversation(frames, first=True)
                self.after_conversation(lead)
                continue

            # ---- name mode: cut the audio into sentences, check each one for "Jarvis"
            loud = r > max(self.noise * 2.2, 20.0)
            if fired and not oww_hit:
                oww_hit = True
                if not cued:  # "Hey Jarvis" recognised mid-sentence: let you know straight away
                    cued = True
                    self.cue()
            if not seg:
                lead.append(f)
                if loud:
                    seg, quiet = list(lead), 0
                continue
            seg.append(f)
            quiet = 0 if loud else quiet + 1
            dur = len(seg) * FRAME / SR
            if quiet < END_QUIET and dur < 15:
                continue
            frames, hit, was_cued = seg, oww_hit, cued
            seg, quiet, oww_hit, cued = [], 0, False, False
            lead.clear()
            if dur - END_QUIET * FRAME / SR < 0.3:
                continue  # a click or a cough
            t0 = time.time()
            if not hit and not self.heard_name(frames):
                prev, prev_end = frames, time.time()
                continue
            recent = prev if prev and time.time() - prev_end < dur + 1.5 else []
            prev = []
            if not was_cued:
                self.cue()
            check = time.time() - t0
            text = self.transcribe(frames, raw=True)
            if not hit and not NAME.search(text):
                log(f"false alarm (quick check heard the name, full pass heard {text[:60]!r})")
                continue
            if recent and not re.match(r"^\W*((hey|ok|okay|hi|yo)\W+)?" + NAME.pattern, text, re.I) \
                    and len(strip_name(text).split()) < 4:
                # "What's the weather ... tomorrow, Jarvis?": the request started in the sentence before
                text = self.transcribe(recent + frames, raw=True)
            command = strip_name(text)
            if re.fullmatch(r"(thank you|thanks for watching|you|bye|\.+|\W*)[.!]?", command, flags=re.I):
                command = ""
            self.set(wake_score=round(score, 2), heard=self.state["heard"] + 1, state="hearing you")
            log(f"name check {check:.2f}s, full text {time.time() - t0 - check:.2f}s: {text!r}")
            if command:
                self.conversation(None, first=True, text=command)
            else:  # just "Jarvis": answer like he's paying attention, then take the request
                from .voice import speak
                if self.robot:
                    speak("Sir?" if self.prefs()["persona"].get("style") == "jarvis" else "Yes?")
                self.conversation(self.record(wait_for_speech=5.0), first=True)
            self.after_conversation(lead)

    def idle_state(self) -> str:
        return f"listening for '{WAKE_WORDS[self.wake_word()]}'"

    def after_conversation(self, lead):
        self.wake.reset()
        lead.clear()
        self.set(state=self.idle_state())

    def conversation(self, frames, first: bool = False, text: str | None = None):
        turns = 0
        while (frames is not None or text) and turns < 12:
            t0 = time.time()
            if text is None:
                if frames:
                    self.face("thinking", 4)
                text = self.transcribe(frames) if frames else ""
                if text:
                    log(f"speech-to-text took {time.time() - t0:.1f}s for {len(frames) * FRAME / SR:.1f}s of audio")
            else:
                self.face("thinking", 4)
            if not text or len(text) < 2:
                if first and turns == 0:
                    log("woke up but didn't catch any words")
                    self.set(last_text="(didn't catch that)")
                    if self.robot:
                        from .voice import speak
                        speak("Sorry sir, I didn't catch that." if self.prefs()["persona"].get("style") == "jarvis"
                              else "Sorry, I didn't catch that.")
                break
            if MIC_OFF.search(text):
                S.save({"ears": {"enabled": False}})
                self._prefs = (0.0, {})
                if self.robot:
                    from .voice import speak
                    speak("Microphone off. Turn me back on from the menu bar." if self.prefs()["persona"].get("style") != "jarvis"
                          else "Microphone off, sir. Switch me back on from the menu bar when you need me.")
                break
            if STOP_WORDS.match(text):
                if self.robot:
                    from .voice import speak
                    speak("Very good, sir." if S.load()["persona"].get("style") == "jarvis" else "Okay!")
                break
            self.answer(text)
            turns += 1
            if not self.prefs()["ears"].get("follow_up", True):
                break
            # follow-up without the wake word. Actions (dealing cards, the next quiz question) start talking a few
            # seconds later, so wait for him to start, then to finish, then listen.
            asked = time.time()
            while self.robot and self.handed_off and time.time() - asked < 8 and self.last_spoke < asked:
                time.sleep(0.1)
            self.set(state="listening for a follow-up")
            window = 30.0 if self.game else 6.0  # in a quiz or a game you get longer to answer
            frames, text = self.record(wait_for_speech=window), None
            log("follow-up: " + ("heard something" if frames else f"nothing in {window:.0f}s, back to 'Hey Jarvis'"))


def main(argv: list[str]) -> None:
    if "--setup" in argv:
        Ears.setup()
        return
    ears = Ears(robot="--test" not in argv)
    try:
        ears.run()
    except KeyboardInterrupt:
        ears.set(state="stopped")


if __name__ == "__main__":
    main(sys.argv[1:])
