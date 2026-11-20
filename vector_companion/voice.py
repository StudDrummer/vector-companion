"""Reliable voice commands, run by wire-pod *before* its built-in intents.

wire-pod's "custom intents" match phrases first (and add them to the speech model's vocabulary),
then run `vector voice "<what you said>"`. We return immediately (so wire-pod moves on), then
handle the command and have Vector answer through the companion.

  install / refresh:  python -m vector_companion.voice --install
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from . import config, settings as S

config.load_env()
WIREPOD = os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080").rstrip("/")
PREFIX = "vc-"  # our custom intents are named vc-...

# phrase groups (wire-pod matches if the transcript CONTAINS a phrase). Keep phrases distinctive.
COMMANDS = {
    "focus": ["focus timer", "focus mode", "study timer", "pomodoro", "start a timer for"],
    "stop-timer": ["stop the timer", "cancel the timer", "stop my timer", "end the timer"],
    "time-left": ["time left", "time is left", "how much longer"],
    "status": ["status report", "sitrep", "system status", "give me a rundown"],
    "homework": ["check my homework", "scan my homework", "look at my homework", "help me with this problem",
                 "check my work"],
    "solve": ["solve this", "solve the problem"],
    "read": ["read this page", "read this for me", "read this"],
    "look": ["what am i holding", "what do you see", "what is this thing"],
    "briefing": ["good morning", "my briefing", "morning briefing"],
    "night": ["good night", "goodnight"],
    "claude": ["what did claude do", "claude update", "is claude done"],
    "memory-add": ["remember that"],
    "memory-read": ["what do you remember"],
    "list-add": ["to my list", "to my to do list"],
    "list-read": ["what's on my list", "what is on my list", "read my list"],
    "list-clear": ["clear my list"],
}
ACK_INTENT = "intent_imperative_affirmative"  # Vector's small "okay" reaction while we work


def _req(path: str, body=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(WIREPOD + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def install() -> int:
    """(Re)register our phrases as wire-pod custom intents. Returns how many were added."""
    exe = str(Path(sys.executable).with_name("vector"))
    existing = json.loads(_req("/api/get_custom_intents_json") or "[]") or []
    # remove our old ones, highest number first (wire-pod numbers them from 1)
    for i in sorted((i for i, c in enumerate(existing) if str(c.get("name", "")).startswith(PREFIX)), reverse=True):
        _req("/api/remove_custom_intent", {"number": i + 1})
    n = 0
    for key, phrases in COMMANDS.items():
        _req("/api/add_custom_intent", {
            "name": PREFIX + key, "description": f"vector-companion: {key}", "utterances": phrases,
            "intent": ACK_INTENT, "params": {"paramname": "", "paramvalue": ""},
            "exec": exe, "execargs": ["voice", "!speechText"], "issystem": False, "luascript": ""})
        n += 1
    return n


def _speak(text: str) -> None:
    from .companion_client import call
    try:
        call("/say", {"text": text}, timeout=60)
    except Exception:  # noqa: BLE001
        from .wirepod import Vector
        Vector().say(text)


def handle(text: str) -> None:
    from . import brain
    text = text.strip().strip('"').strip()
    S.log("voice", f"heard: {text}")
    time.sleep(1.8)  # let Vector finish his little acknowledgment
    reply = brain.local_skill(text)
    if reply is None:  # shouldn't happen for our phrases, but fall back to the AI
        msgs, _ = brain.build_messages([{"role": "user", "content": text}])
        reply = "".join(brain.stream_llm(msgs)).strip() or "Sorry, I didn't catch that."
    S.log("voice", f"reply: {reply}")
    _speak(brain.speakable(reply))


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--install":
        print(f"   registered {install()} voice command groups in wire-pod")
        return
    text = " ".join(argv)
    from .notify import detach
    if detach():
        return  # parent returns at once so wire-pod isn't kept waiting
    try:
        handle(text)
    except Exception as e:  # noqa: BLE001
        S.log("voice", f"ERROR {e!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
