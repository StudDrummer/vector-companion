"""Reliable voice commands, run by wire-pod *before* its built-in intents.

wire-pod's "custom intents" match phrases first (and add them to the speech model's vocabulary),
then run `vector voice "<what you said>"`. We return immediately (so wire-pod moves on), then
handle the command and have Vector answer through the companion.

  install / refresh:  python -m vector_companion.voice --install
"""
from __future__ import annotations

import json
import re
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
    "weather": ["the weather", "weather like", "need an umbrella", "need a jacket", "weather tomorrow"],
    "guard": ["guard my desk", "guard mode", "watch my desk", "keep watch"],
    "guard-off": ["stop guarding", "guard off", "i'm back"],
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


def speak(text: str) -> None:
    """Vector says it (in the chosen voice) through the companion; falls back to wire-pod."""
    if not (text or "").strip():
        return
    from .companion_client import call
    try:
        call("/say", {"text": text}, timeout=90)
    except Exception:  # noqa: BLE001
        from .wirepod import Vector
        Vector().say(text)


_speak = speak


# Vector's own voice commands (the same things "Hey Vector" does), matched on clean text and carried out
# by the companion (remote commands for these are ignored by a regular Vector). (pattern, action)
VECTOR_COMMANDS = [
    (r"\bblack ?jack\b|play (a )?(card )?game|play cards|deal me in", "blackjack"),
    (r"^(hit|hit me|another( card)?|one more( card)?)$", "bj_hit"),
    (r"^(stand|i'?ll stand|stay|i'?m good|hold)$", "bj_stand"),
    (r"\bfist ?bump", "fist_bump"),
    (r"\bdo a trick\b|something cool|show me a trick", "trick"),
    (r"\bi love you\b", "love"),
    (r"^(good (robot|boy|job)|well done|awesome|nice job|nice work)$", "praise"),
    (r"^(bad robot|bad boy)$", "scold"),
    (r"^(volume up|louder|turn (it|the volume) up|speak up)$", "volume_up"),
    (r"^(volume down|quieter|turn (it|the volume) down)$", "volume_down"),
    (r"\bhow old are you\b", "age"),
    (r"\bwhat'?s my name\b|\bwho am i\b", "name"),
    (r"\bwhat time is it\b|what'?s the time", "time"),
    (r"^(go to sleep|sleep|take a nap)$", "sleep"),
    (r"go (to your )?(home|charger)|go charge", "go_to_charger"),
    (r"\btake (a |my )?(photo|picture|selfie)", "take_photo"),
    (r"^(hello|hi|hey)( there| vector)?$", "hello"),
    (r"^(goodbye|bye|see you)", "goodbye"),
    (r"\bdance\b|boogie", "dance"),
    (r"\blook at me\b", "look_at_me"),
    (r"\bcome (here|to me)\b", "come_here"),
    (r"\b(fetch|bring me) (your |the )?cube", "fetch_cube"),
    (r"\broll (your |the )?cube", "roll_cube"),
    (r"\bwheelie\b", "pop_a_wheelie"),
    (r"\bexplore\b", "explore"),
]


def vector_command(text: str) -> str | None:
    t = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    t = re.sub(r"^(can you|could you|please|vector|jarvis|let'?s)\s+", "", t).strip()
    t = re.sub(r"\s+please$", "", t)
    for pat, action in VECTOR_COMMANDS:
        if re.search(pat, t):
            return action
    return None


def run_vector_command(action: str) -> str:
    """Carry it out through the companion. Returns what to say ("" = he handles it himself)."""
    from .companion_client import call
    try:
        call("/do", {"action": action}, timeout=90)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        S.log("voice", f"action {action} failed: {msg}")
        if "dock lock" in msg or "charger" in msg:
            return "I have to stay on my charger until my new battery is in, so I can't move around yet."
        return "I couldn't do that right now. Is the companion running?"
    S.log("voice", f"action: {action}")
    return ""


def respond(text: str, history: list[dict] | None = None) -> str:
    """Answer one thing you said: Vector's own commands (blackjack, fist bump...), then built-in skills
    (timer, list, weather, homework...), else the AI."""
    from . import brain
    action = vector_command(text)
    if action:
        return run_vector_command(action)
    reply = brain.local_skill(text)
    if reply is None:
        msgs, _ = brain.build_messages((history or [])[-8:] + [{"role": "user", "content": text}])
        reply = "".join(brain.stream_llm(msgs)).strip() or "Sorry, I didn't catch that."
    return brain.speakable(reply)


def handle(text: str) -> None:
    text = text.strip().strip('"').strip()
    S.log("voice", f"heard: {text}")
    time.sleep(1.8)  # let Vector finish his little acknowledgment
    reply = respond(text)
    S.log("voice", f"reply: {reply}")
    speak(reply)


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
