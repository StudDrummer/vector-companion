"""Announcements for Claude Code and the terminal: what happened, where, and a face badge.

Claude Code passes JSON on stdin to its hooks (session, transcript_path, cwd, message...).
For "Stop" we read Claude's last reply from the transcript and turn it into one spoken
sentence ("Claude finished in vector companion. It fixed the head slider and added tests.").
"""
from __future__ import annotations

import json
import os
import re
import select
import sys
import threading
import time
from pathlib import Path

from . import settings as S

STAMP = S.DATA_DIR / "claude_started"
LAST = S.DATA_DIR / "last_events.json"


# ------------------------------------------------------------------ persona
def persona() -> str:
    return S.load().get("persona", {}).get("style", "vector")


def address() -> str:
    """How announcements address you, by personality style."""
    owner = os.environ.get("VECTOR_OWNER", "Rushil")
    return {"jarvis": "Sir, ", "friday": "Hey boss, "}.get(persona(), f"{owner}, " if persona() == "vector_named" else "")


# ------------------------------------------------------------------ helpers
def dur(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} second{'s' if sec != 1 else ''}"
    m = round(sec / 60)
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''}"
    h, m = divmod(m, 60)
    return f"{h} hour{'s' if h != 1 else ''}" + (f" {m} minutes" if m else "")


def place(cwd: str) -> str:
    name = Path(cwd).name if cwd else ""
    if not name or name in (os.path.basename(str(Path.home())), "/"):
        return ""
    return " in " + re.sub(r"[-_]+", " ", name)


def read_stdin_json(timeout: float = 0.6) -> dict:
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return {}
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        return {}


def last_assistant_text(payload: dict) -> str:
    for k in ("last_assistant_message", "assistant_message"):
        if isinstance(payload.get(k), str) and payload[k].strip():
            return payload[k]
    tp = payload.get("transcript_path")
    if not tp or not Path(tp).exists():
        return ""
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        content = (obj.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            if text.strip():
                return text
    return ""


_CODEBLOCK = re.compile(r"```.*?```", re.S)
_MD = re.compile(r"`([^`]*)`|\*\*|__|#+ |\[([^\]]+)\]\([^)]+\)|https?://\S+|[*_>|]")
_FILLER = re.compile(r"^(done|all set|great|perfect|okay|ok|got it|sure|alright|all done)[.!,:]?\s+", re.I)


def plain(text: str) -> str:
    text = _CODEBLOCK.sub(" ", text)
    text = _MD.sub(lambda m: m.group(1) or m.group(2) or " ", text)
    return re.sub(r"\s+", " ", text).strip()


def third_person(s: str) -> str:
    """'I fixed X' -> 'It fixed X' so Vector reports about Claude."""
    s = _FILLER.sub("", s.strip())
    for a, b in (("I've ", "It has "), ("I have ", "It has "), ("I'm ", "It's "), ("I'll ", "It will "),
                 ("I ", "It "), ("We ", "It "), ("I've", "It has")):
        if s.startswith(a):
            return b + s[len(a):]
    return s


def with_addr(text: str) -> str:
    a = address()
    return (a + text[0].lower() + text[1:]) if a and text else text


def first_sentences(text: str, max_words: int = 24) -> str:
    t = third_person(plain(text))
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = ""
    for p in parts:
        if len((out + " " + p).split()) > max_words:
            break
        out = (out + " " + p).strip()
    if not out:
        out = " ".join(t.split()[:max_words])
    return out


def summarize(text: str) -> str:
    """One short spoken sentence about what Claude did. Uses Vector's brain if it answers fast, else trims."""
    if not text.strip():
        return ""
    fallback = first_sentences(text)
    result: list[str] = []

    def run():
        try:
            from . import brain
            msgs = [{"role": "system", "content": "You turn an AI coding assistant's final message into ONE short spoken "
                     "sentence (under 16 words, past tense, starting with 'It') saying what it did or found. "
                     "No markdown, no file paths, no code."},
                    {"role": "user", "content": plain(text)[:3000]}]
            result.append("".join(brain.stream_llm(msgs)).strip())
        except Exception:  # noqa: BLE001
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(20)
    s = third_person(plain(result[0])) if result else ""
    if not s or len(s.split()) > 30:
        return fallback
    return s


def remember(kind: str, data: dict) -> None:
    try:
        d = json.loads(LAST.read_text()) if LAST.exists() else {}
    except ValueError:
        d = {}
    d[kind] = {**data, "at": time.time()}
    LAST.write_text(json.dumps(d, indent=2))


def recent(kind: str) -> dict | None:
    try:
        return json.loads(LAST.read_text()).get(kind)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ main entry
def detach() -> bool:
    """Fork so Claude Code / the shell never waits on Vector. Returns True in the parent."""
    try:
        if os.fork() > 0:
            return True
        os.setsid()
        fd = os.open(os.devnull, os.O_RDWR)
        for n in (0, 1, 2):
            os.dup2(fd, n)
        return False
    except (AttributeError, OSError):
        return False


def handle(event: str, rc: int = 0, seconds: float = 0, cmd: str = "", cwd: str = "", payload: dict | None = None):
    from .wirepod import Vector
    payload = payload or {}
    S.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if event == "claude-start":
        STAMP.write_text(str(time.time()))
        return
    prefs = S.load()
    n = prefs["notify"]
    cwd = cwd or payload.get("cwd", "")
    where = place(cwd)
    text = color = icon = None
    if event == "claude-stop":
        started = float(STAMP.read_text()) if STAMP.exists() else 0
        elapsed = time.time() - started if started else 0
        summary = summarize(last_assistant_text(payload))
        remember("claude", {"project": where.replace(" in ", "", 1), "summary": summary, "seconds": elapsed})
        if not n["claude_done"] or (started and elapsed < n["claude_min_seconds"]):
            S.log("hook", f"claude-stop: quiet ({elapsed:.0f}s)")
            return
        text = with_addr(f"Claude finished{where}.") + (f" {summary}" if summary else "")
        if elapsed >= 120:
            text += f" That took {dur(elapsed)}."
        color, icon = "lime", "ai_done"
    elif event == "claude-input":
        if not n["claude_input"]:
            return
        msg = plain(payload.get("message", ""))
        if re.search(r"waiting for your input|idle", msg, re.I):
            text = with_addr(f"Claude is waiting for you{where}.")
        elif msg:
            text = with_addr(f"{msg.rstrip('.')}{where}.")
        else:
            text = with_addr(f"Claude needs your input{where}.")
        color, icon = "yellow", "ai_input"
    elif event == "terminal":
        name = (cmd.split() or ["command"])[0].split("/")[-1]
        remember("terminal", {"command": name, "rc": rc, "seconds": seconds, "project": where.replace(" in ", "", 1)})
        if not n["terminal"] or seconds < n["terminal_min_seconds"] or (rc == 0 and n["terminal_failures_only"]):
            S.log("hook", f"terminal {name} rc={rc} {seconds:.0f}s: below threshold/off")
            return
        if rc == 0:
            text, color, icon = with_addr(f"Your {name} command finished{where} after {dur(seconds)}."), "lime", "terminal_ok"
        else:
            text, color, icon = with_addr(f"Heads up. {name} failed{where} after {dur(seconds)}."), "orange", "terminal_fail"
    elif event == "test":
        text, color, icon = with_addr("Notifications are working. I'll let you know when things finish."), "lime", "check"
    if not text:
        return
    if S.in_quiet_hours(prefs):
        S.log("hook", f"{event}: skipped (quiet hours): {text}")
        return
    v = Vector(timeout=8)
    if not v.serial:
        S.log("hook", f"{event}: wire-pod unreachable or no robot")
        return
    # Preferred: the companion shows the badge and speaks under one behavior-control session.
    try:
        from .companion_client import call
        if prefs.get("companion", {}).get("face_icons", True):
            call("/announce", {"text": text, "icon": icon}, timeout=60)
            S.log("hook", f"{event}: said '{text}' (+{icon})")
            return
    except Exception as e:  # noqa: BLE001
        S.log("hook", f"{event}: companion unavailable ({e}); using wire-pod")
    if n["eye_flash"]:
        with v.flash_eyes(color):
            v.say(text)
    else:
        v.say(text)
    S.log("hook", f"{event}: said '{text}'")
