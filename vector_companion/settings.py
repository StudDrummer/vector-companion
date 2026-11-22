"""User preferences shared by the app, the brain and the notification hooks.

Stored in ~/.vector-companion/settings.json. Brain/LLM settings that are needed
at process start live in the project's .env (see config.py); helpers here read
and update both.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, time as dtime
from pathlib import Path

from .config import ROOT

DATA_DIR = Path(os.path.expanduser(os.environ.get("VECTOR_DATA_DIR", "~/.vector-companion")))
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_DIR = ROOT / "logs"
ENV_FILE = ROOT / ".env"

# built-in behaviors that drive him off the charger (blocked while the dock lock is on)
DOCK_BLOCKED = {"dance", "explore", "come_here", "fetch_cube", "roll_cube", "pop_a_wheelie", "look_at_me"}

DEFAULTS: dict = {
    "notify": {
        "claude_done": True,
        "claude_input": True,
        "claude_min_seconds": 20,
        "terminal": True,
        "terminal_min_seconds": 30,
        "terminal_failures_only": False,
        "eye_flash": True,
    },
    "quiet_hours": {"enabled": False, "start": "22:30", "end": "07:00"},
    "persona": {"style": "vector"},
    "safety": {"dock_lock": True, "keep_still": True},
    "companion": {"pet_hearts": True, "greetings": True, "morning_briefing": True,
                  "face_icons": True, "focus_minutes": 25, "focus_checkins": True,
                  "cube_button": True},
    # how he sounds: his own robot voice, or a Mac voice played through his speaker
    "voice": {"engine": "auto", "mac_voice": "Daniel", "rate": 190, "volume": 80},
    # "Hey Jarvis" through the Mac's microphone (Vector Ears)
    "ears": {"enabled": True, "wake_word": "hey_jarvis", "sensitivity": 0.5, "follow_up": True, "chime": True},
    "guard": {"notify": True, "save_photos": True},
    "weather": {"enabled": True, "place": "Bellevue, WA", "units": "fahrenheit"},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(SETTINGS_FILE.read_text()))
    except Exception:  # noqa: BLE001
        return json.loads(json.dumps(DEFAULTS))


def save(new: dict) -> dict:
    merged = _merge(load(), new)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2))
    return merged


def in_quiet_hours(s: dict | None = None, now: datetime | None = None) -> bool:
    q = (s or load())["quiet_hours"]
    if not q.get("enabled"):
        return False
    try:
        start = dtime.fromisoformat(q["start"])
        end = dtime.fromisoformat(q["end"])
    except (ValueError, KeyError):
        return False
    t = (now or datetime.now()).time()
    return start <= t < end if start < end else (t >= start or t < end)


def log(name: str, msg: str) -> None:
    """Append one line to logs/<name>.log (kept small)."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        p = LOG_DIR / f"{name}.log"
        if p.exists() and p.stat().st_size > 200_000:
            p.write_text("\n".join(p.read_text().splitlines()[-500:]) + "\n")
        with p.open("a") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def tail(name: str, n: int = 40) -> list[str]:
    p = LOG_DIR / f"{name}.log"
    if not p.exists():
        return []
    return p.read_text(errors="replace").splitlines()[-n:]


# ---------------------------------------------------------------- .env helpers
def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    done = set()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            done.add(m.group(1))
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
