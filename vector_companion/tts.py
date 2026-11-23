"""Jarvis's voice: Piper neural text-to-speech, fully offline on the Mac.

  python -m vector_companion.tts --install [voice]   install Piper and download a voice
  python -m vector_companion.tts "Good evening, sir."  say it through the Mac speakers

Voices live in ~/.vector-companion/voices. A light "assistant" polish (clean low end, a touch of
presence and a short room sheen) is applied so it sounds like a voice in the room, not a phone line.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path

from . import settings as S

VOICE_DIR = S.DATA_DIR / "voices"
STATUS = S.DATA_DIR / "tts_install.json"
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# id -> (path in the piper-voices repo, label shown in the app)
VOICES = {
    "en_GB-alan-medium": ("en/en_GB/alan/medium/", "Alan (British, calm)"),
    "en_GB-northern_english_male-medium": ("en/en_GB/northern_english_male/medium/", "Northern (British, warm)"),
    "en_GB-semaine-medium": ("en/en_GB/semaine/medium/", "Semaine (British, crisp)"),
    "en_US-ryan-high": ("en/en_US/ryan/high/", "Ryan (American)"),
}
DEFAULT_VOICE = "en_GB-alan-medium"
MALE_SPEAKERS = ("obadiah", "spike")  # for multi-speaker voices, the deeper male speakers

_loaded: dict = {}
_lock = threading.Lock()


def log(msg: str) -> None:
    S.log("companion", f"tts: {msg}")


# ------------------------------------------------------------------ install
def piper_ok() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def voice_files(vid: str) -> tuple[Path, Path]:
    return VOICE_DIR / f"{vid}.onnx", VOICE_DIR / f"{vid}.onnx.json"


def have_voice(vid: str) -> bool:
    m, c = voice_files(vid)
    return m.exists() and c.exists() and m.stat().st_size > 1_000_000


def ready(vid: str | None = None) -> bool:
    return piper_ok() and have_voice(vid or chosen_voice())


def chosen_voice() -> str:
    v = str(S.load()["voice"].get("piper_voice") or DEFAULT_VOICE)
    return v if v in VOICES else DEFAULT_VOICE


def status() -> dict:
    try:
        st = json.loads(STATUS.read_text())
    except Exception:  # noqa: BLE001
        st = {}
    st.update(piper=piper_ok(), voices={k: {"label": v[1], "installed": have_voice(k)} for k, v in VOICES.items()},
              chosen=chosen_voice())
    return st


def _status(**kw):
    try:
        S.DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps({**kw, "at": time.time()}))
    except OSError:
        pass


def install(vid: str | None = None) -> bool:
    vid = vid if vid in VOICES else DEFAULT_VOICE
    try:
        if not piper_ok():
            _status(state="installing Piper")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "piper-tts>=1.3"], check=True, timeout=900)
        if not have_voice(vid):
            VOICE_DIR.mkdir(parents=True, exist_ok=True)
            for suffix in (".onnx.json", ".onnx"):
                _status(state=f"downloading {VOICES[vid][1]}")
                dest = VOICE_DIR / f"{vid}{suffix}"
                tmp = dest.with_suffix(dest.suffix + ".part")
                urllib.request.urlretrieve(HF + VOICES[vid][0] + vid + suffix, tmp)
                tmp.rename(dest)
        _status(state="ready", voice=vid)
        return True
    except Exception as e:  # noqa: BLE001
        _status(state="error", error=str(e)[:200])
        log(f"install failed: {e}")
        return False


def install_async(vid: str | None = None):
    threading.Thread(target=install, args=(vid,), daemon=True).start()


# ------------------------------------------------------------------ synthesis
def _voice(vid: str):
    with _lock:
        if vid not in _loaded:
            from piper import PiperVoice
            m, c = voice_files(vid)
            _loaded[vid] = PiperVoice.load(str(m), config_path=str(c))
        return _loaded[vid]


def _speaker(vid: str):
    try:
        ids = json.loads(voice_files(vid)[1].read_text()).get("speaker_id_map") or {}
    except Exception:  # noqa: BLE001
        return None
    for name in MALE_SPEAKERS:
        if name in ids:
            return ids[name]
    return None


def warm():
    """Load the voice now so the first sentence isn't slow."""
    if ready():
        try:
            synth("Ready.")
        except Exception as e:  # noqa: BLE001
            log(f"warm-up failed: {e}")


def synth(text: str):
    """-> (int16 numpy array, sample rate)."""
    import numpy as np
    vid = chosen_voice()
    v = _voice(vid)
    prefs = S.load()["voice"]
    length = 1.0 / max(0.6, min(1.6, float(prefs.get("speed") or 1.0)))
    speaker = _speaker(vid)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        try:  # piper-tts 1.3+
            from piper import SynthesisConfig
            cfg = SynthesisConfig(length_scale=length, speaker_id=speaker)
            v.synthesize_wav(text, w, syn_config=cfg)
        except ImportError:  # older API
            kw = {"length_scale": length}
            if speaker is not None:
                kw["speaker_id"] = speaker
            v.synthesize(text, w, **kw)
    buf.seek(0)
    with wave.open(buf, "rb") as r:
        sr = r.getframerate()
        audio = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16)
    if prefs.get("fx", True):
        audio = polish(audio, sr)
    return audio, sr


def polish(audio, sr: int):
    """Clean, present, slightly 'in the room': high-pass, a little presence, a short soft reflection tail."""
    import numpy as np
    x = audio.astype(np.float32) / 32768.0
    # one-pole high-pass at ~90 Hz (removes rumble so small speakers stay clear)
    a = float(np.exp(-2 * np.pi * 90 / sr))
    try:
        from scipy.signal import lfilter
        y = lfilter([a, -a], [1.0, -a], x).astype(np.float32)
    except Exception:  # noqa: BLE001  (no scipy: skip the high-pass)
        y = x
    # presence: add a bit of the difference signal (brightens consonants)
    pres = np.concatenate([[0.0], np.diff(y)]) * 0.35
    y = y + pres
    # short room sheen: a few early reflections, quiet
    out = y.copy()
    for ms, g in ((11, 0.16), (23, 0.11), (37, 0.07), (53, 0.045)):
        d = int(sr * ms / 1000)
        out[d:] += y[:-d] * g
    pad = np.zeros(int(sr * 0.06), dtype=np.float32)
    out = np.concatenate([out, pad])
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * 0.89
    return (out * 32767).astype(np.int16)


def resample(audio, sr: int, to: int = 16000):
    import numpy as np
    if sr == to:
        return audio
    n = int(len(audio) * to / sr)
    xs = np.linspace(0, len(audio) - 1, n)
    return np.interp(xs, np.arange(len(audio)), audio.astype(np.float32)).astype(np.int16)


def write_wav(path: str, audio, sr: int) -> float:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio.tobytes())
    return len(audio) / float(sr)


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--install":
        ok = install(argv[1] if len(argv) > 1 else None)
        print("   Jarvis voice ready" if ok else "   couldn't install the voice: " + status().get("error", ""))
        return
    text = " ".join(argv) or "Good evening, sir. All systems are running normally."
    t0 = time.time()
    audio, sr = synth(text)
    path = "/tmp/jarvis-test.wav"
    secs = write_wav(path, audio, sr)
    print(f"   made {secs:.1f}s of speech in {time.time() - t0:.2f}s")
    subprocess.run(["afplay", path])


if __name__ == "__main__":
    main(sys.argv[1:])
