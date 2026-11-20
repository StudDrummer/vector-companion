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
WAKE_WORDS = {"hey_jarvis": "Hey Jarvis", "hey_mycroft": "Hey Mycroft", "alexa": "Alexa"}
STOP_WORDS = re.compile(r"^(never ?mind|stop|cancel|nothing|that'?s all|thanks?,? (that'?s all|jarvis)|thank you,? jarvis)\W*$", re.I)


def log(msg: str) -> None:
    S.log("ears", msg)


class Ears:
    def __init__(self, robot: bool = True):
        self.robot = robot
        self.q: queue.Queue = queue.Queue(maxsize=400)
        self.state = {"state": "starting", "heard": 0, "last_text": "", "last_reply": "", "error": "",
                      "at": time.time(), "wake_score": 0.0}
        self.history: list[dict] = []
        self.history_at = 0.0
        self.vector_busy_until = 0.0
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
        utils.download_models(model_names=list(WAKE_WORDS))
        print(f"   downloading the Whisper '{WHISPER}' speech model (about 470 MB, once)...")
        from faster_whisper import WhisperModel
        WhisperModel(WHISPER, device="cpu", compute_type="int8")
        print("   ears ready", openwakeword.__version__ if hasattr(openwakeword, "__version__") else "")

    @staticmethod
    def wake_word() -> str:
        w = str(S.load()["ears"].get("wake_word") or "hey_jarvis")  # noqa
        return w if w in WAKE_WORDS else "hey_jarvis"

    @staticmethod
    def _wake_model():
        from openwakeword.model import Model  # needs openwakeword 0.6+ (0.4 scores everything as 0)
        return Model(wakeword_models=[Ears.wake_word()], inference_framework="onnx")

    def load(self):
        try:
            self.wake = self._wake_model()
        except Exception:  # noqa: BLE001  (first run: models not downloaded yet)
            self.setup()
            self.wake = self._wake_model()
        from faster_whisper import WhisperModel
        self.stt = WhisperModel(WHISPER, device="cpu", compute_type="int8")

    # ------------------------------------------------------------ audio
    def _callback(self, indata, frames, t, status):
        try:
            self.q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def frame(self, timeout: float = 1.0):
        return self.q.get(timeout=timeout)

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

    def record(self, wait_for_speech: float, first=None) -> "list | None":
        """Collect frames until ~0.8 s of quiet after speech. None if nobody spoke within wait_for_speech."""
        frames = list(first or [])
        talk = max(self.noise * 2.2, 350.0)
        started, quiet, t0 = bool(first), 0, time.time()
        while True:
            try:
                f = self.frame()
            except queue.Empty:
                continue
            loud = self.rms(f) > talk
            if not started:
                if loud:
                    started = True
                    frames.append(f)
                elif time.time() - t0 > wait_for_speech:
                    return None
                else:
                    frames = (frames + [f])[-4:]  # keep a little lead-in
                continue
            frames.append(f)
            quiet = 0 if loud else quiet + 1
            if quiet >= 10 or len(frames) * FRAME / SR > 12:
                return frames

    def transcribe(self, frames) -> str:
        import numpy as np
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        segs, _ = self.stt.transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                      initial_prompt="Hey Jarvis, Vector, homework, focus timer, Claude.")
        text = " ".join(s.text for s in segs).strip()
        text = re.sub(r"^(hey,?\s+)?(jarvis|mycroft|alexa)[,.!]?\s*", "", text, flags=re.I).strip()
        return text

    # ------------------------------------------------------------ robot side
    def _busy_watch(self):
        """Don't wake on Vector's own voice: mute while he's talking."""
        from .companion_client import call
        while True:
            try:
                if call("/health", timeout=2).get("speaking"):
                    self.vector_busy_until = time.time() + 0.8
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)

    def cue(self):
        if self.prefs()["ears"].get("chime", True):
            subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        if self.robot:
            def show():
                from .companion_client import call
                try:
                    call("/face", {"text": "LISTENING", "seconds": 2.5}, timeout=6)
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=show, daemon=True).start()

    def answer(self, text: str) -> None:
        from .voice import respond, speak
        if time.time() - self.history_at > 180:
            self.history = []
        self.set(state="thinking", last_text=text)
        reply = respond(text, self.history)
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        self.history_at = time.time()
        self.set(state="speaking", last_reply=reply)
        log(f"heard: {text!r} -> {reply[:120]!r}")
        if self.robot:
            speak(reply)
            self.vector_busy_until = time.time() + 0.8
        else:
            print("   reply:", reply)

    # ------------------------------------------------------------ main loop
    def run(self):
        import numpy as np
        import sounddevice as sd
        self.set(state="loading models")
        self.load()
        if self.robot:
            threading.Thread(target=self._busy_watch, daemon=True).start()
        while True:  # keep going through mic unplugs, sleep/wake, etc.
            try:
                with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME,
                                    callback=self._callback):
                    self.set(state=f"listening for '{WAKE_WORDS[self.wake_word()]}'", error="")
                    log(f"listening for '{WAKE_WORDS[self.wake_word()]}'")
                    self._loop(np)
            except Exception as e:  # noqa: BLE001
                self.set(state="error", error=f"{e.__class__.__name__}: {e}"[:200])
                log(f"mic error, retrying in 5 s: {e}")
                time.sleep(5)

    def _loop(self, np):
        levels: list[float] = []
        loaded = self.wake_word()
        while True:
            p = self.prefs()["ears"]
            if p.get("wake_word", "hey_jarvis") != loaded and p.get("wake_word") in WAKE_WORDS:
                loaded = p["wake_word"]
                self.wake = self._wake_model()
                self.set(state=f"listening for '{WAKE_WORDS[loaded]}'")
            if not p.get("enabled", True):
                self.set(state="off (turn on in the Vector app)")
                time.sleep(2)
                self.drain()
                continue
            try:
                f = self.frame()
            except queue.Empty:
                continue
            if time.time() < self.vector_busy_until:
                self.wake.reset()
                continue
            levels = (levels + [self.rms(f)])[-60:]
            self.noise = float(np.median(levels))
            scores = self.wake.predict(f)
            score = max(scores.values(), default=0.0)
            sens = float(p.get("sensitivity", 0.5))
            if score < 0.85 - 0.6 * sens:
                continue
            self.set(wake_score=round(float(score), 2), heard=self.state["heard"] + 1, state="hearing you")
            self.cue()
            frames = self.record(wait_for_speech=4.0)
            self.conversation(frames)
            self.wake.reset()
            self.drain()
            self.set(state=f"listening for '{WAKE_WORDS[self.wake_word()]}'")

    def conversation(self, frames):
        turns = 0
        while frames is not None and turns < 6:
            text = self.transcribe(frames) if frames else ""
            if not text or len(text) < 2:
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
            # follow-up without the wake word: wait until he's done talking, then listen a few seconds
            while time.time() < self.vector_busy_until:
                time.sleep(0.1)
            self.drain()
            self.set(state="listening for a follow-up")
            frames = self.record(wait_for_speech=5.0)


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
