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


# Vector's own built-in voice commands (the same ones "Hey Vector" understands), matched on clean text.
# Order matters: specific first. (pattern, intent, drives_him)
VECTOR_COMMANDS = [
    (r"\bblack ?jack\b|play (a )?(card )?game|play cards", "intent_play_blackjack", False),
    (r"^(hit|hit me)$", "intent_blackjack_hit", False),
    (r"^(stand|i'?ll stand|stay)$", "intent_blackjack_stand", False),
    (r"\bfist ?bump", "intent_play_fistbump", False),
    (r"\bdo a trick\b|something cool", "intent_play_anytrick", False),
    (r"\bi love you\b", "intent_imperative_love", False),
    (r"^(good (robot|boy|job)|well done|awesome|nice job)$", "intent_imperative_praise", False),
    (r"^(bad robot|bad boy)$", "intent_imperative_abuse", False),
    (r"^(volume up|louder|turn (it|the volume) up)$", "intent_imperative_volumeup", False),
    (r"^(volume down|quieter|turn (it|the volume) down)$", "intent_imperative_volumedown", False),
    (r"^(shut up)$", "intent_imperative_shutup", False),
    (r"^(be quiet|quiet)$", "intent_imperative_quiet", False),
    (r"\bhow old are you\b", "intent_character_age", False),
    (r"\bwhat'?s my name\b|\bwho am i\b", "intent_names_ask", False),
    (r"\bwhat time is it\b|what'?s the time", "intent_clock_time", False),
    (r"^(go to sleep|sleep|take a nap)$", "intent_system_sleep", False),
    (r"go (to your )?(home|charger)|go charge", "intent_system_charger", False),
    (r"^(hello|hi|hey)( there| vector)?$", "intent_greeting_hello", False),
    (r"^(goodbye|bye|see you)", "intent_greeting_goodbye", False),
    (r"\bdance\b|boogie", "intent_imperative_dance", True),
    (r"\blook at me\b", "intent_imperative_lookatme", True),
    (r"\bcome (here|to me)\b", "intent_imperative_come", True),
    (r"\b(fetch|bring me) (your |the )?cube", "intent_imperative_fetchcube", True),
    (r"\bfind (your |the )?cube", "intent_imperative_findcube", True),
    (r"\broll (your |the )?cube", "intent_play_rollcube", True),
    (r"\bpick up (your |the )?cube", "intent_play_pickupcube", True),
    (r"\bwheelie\b", "intent_play_popawheelie", True),
    (r"\bkeep ?away\b", "intent_play_keepaway", True),
    (r"\bexplore\b", "intent_explore_start", True),
    (r"^(turn around)$", "intent_imperative_turnaround", True),
    (r"^(turn left|go left)$", "intent_imperative_turnleft", True),
    (r"^(turn right|go right)$", "intent_imperative_turnright", True),
    (r"^(go forward|forward|move forward)$", "intent_imperative_forward", True),
    (r"^(back up|go back|backwards?)$", "intent_imperative_backup", True),
]


def vector_command(text: str) -> tuple[str, bool] | None:
    t = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    t = re.sub(r"^(can you|could you|please|vector|let'?s)\s+", "", t).strip()
    t = re.sub(r"\s+please$", "", t)
    for pat, intent, drives in VECTOR_COMMANDS:
        if re.search(pat, t):
            return intent, drives
    return None


def run_vector_command(intent: str, drives: bool) -> str:
    """Do it exactly like "Hey Vector" would. Returns what to say ("" = he handles it himself)."""
    if drives and S.load()["safety"].get("dock_lock"):
        return "I have to stay on my charger until my new battery is in, so I can't move around yet."
    from .wirepod import Vector
    Vector().intent(intent)
    S.log("voice", f"vector command: {intent}")
    return ""


def respond(text: str, history: list[dict] | None = None) -> str:
    """Answer one thing you said: Vector's own commands (blackjack, fist bump...), then built-in skills
    (timer, list, weather, homework...), else the AI."""
    from . import brain
    cmd = vector_command(text)
    if cmd:
        try:
            return run_vector_command(*cmd)
        except Exception as e:  # noqa: BLE001
            S.log("voice", f"vector command failed: {e}")
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
