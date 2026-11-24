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
    (r"^(stop|quit|end|i'?m done|no more)( the| this)?( game| playing| blackjack)?$|stop playing|quit the game", "bj_quit"),
    (r"what'?s my (card|cards|hand|score|total)|what (do|did) i (have|get)|what are my cards", "bj_status"),
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
    try:
        q = quiz_route(text)
    except Exception:  # noqa: BLE001
        q = None
    if q is not None:
        return q
    action = vector_command(text)
    if action:
        return run_vector_command(action)
    reply = brain.local_skill(text)
    if reply is None:
        msgs, _ = brain.build_messages((history or [])[-8:] + [{"role": "user", "content": text}])
        reply = "".join(brain.stream_llm(msgs)).strip() or "Sorry, I didn't catch that."
    return brain.speakable(reply)


QUIZ_START = re.compile(r"\bquiz me\b(?:\s+(?:on|about|in)\s+(.+))?|\b(?:give me|start) a quiz(?:\s+(?:on|about)\s+(.+))?", re.I)


def game_state() -> dict:
    from .companion_client import call
    try:
        return call("/health", timeout=2)
    except Exception:  # noqa: BLE001
        return {}


def quiz_route(text: str) -> str | None:
    """Starts a quiz, or hands an answer to the one that's running. None = not quiz related."""
    from .companion_client import call
    m = QUIZ_START.search(text)
    if m:
        topic = (m.group(1) or m.group(2) or "").strip(" .?!")
        if not topic:
            from .quiz import _load_misses
            topic = "my mistakes" if _load_misses() else "AP Biology"
        call("/quiz", {"topic": topic}, timeout=10)
        return ""
    if game_state().get("quiz"):
        call("/quiz_answer", {"text": text}, timeout=10)
        return ""
    return None


def respond_stream(text: str, history: list[dict] | None = None):
    """Like respond(), but AI answers come out sentence by sentence so he can start talking right away:
    the first sentence as soon as it's written, then the rest together."""
    from . import brain
    try:
        q = quiz_route(text)
    except Exception:  # noqa: BLE001
        q = None
    if q is not None:
        yield q
        return
    action = vector_command(text)
    if action:
        yield run_vector_command(action)
        return
    reply = brain.local_skill(text)
    if reply is not None:
        yield brain.speakable(reply)
        return
    from . import openjarvis as OJ
    if OJ.wants_deep(text):
        done = yield from _deep(text, history, brain, OJ)
        if done:
            return
    msgs, _ = brain.build_messages((history or [])[-8:] + [{"role": "user", "content": text}])
    msgs[0]["content"] += ("\nYou are speaking out loud right now: answer in at most two short sentences. "
                           "Never make up what " + brain.OWNER + " is doing or has been doing.")
    buf, first_done = "", False
    for chunk in brain.stream_llm(msgs):
        buf += chunk
        m = re.search(r"^(.{12,}?[.!?])(\s+)", buf, re.S)
        if m:
            yield brain.speakable(m.group(1).strip())
            if first_done:
                return  # two sentences is plenty out loud; don't wait for the rest
            buf, first_done = buf[m.end():], True
    rest = re.findall(r"[^.!?]+[.!?]+", buf.strip()) or ([buf.strip()] if buf.strip() else [])
    rest = " ".join(x.strip() for x in rest[:1 if first_done else 2])  # two sentences out loud, max
    if rest:
        yield brain.speakable(rest)
    elif not first_done:
        yield "Sorry, I didn't catch that."


def _deep(text: str, history, brain, OJ):
    """Hand real work (research, email, calendar, planning) to the OpenJarvis agent. Says it's on it,
    then speaks the first few sentences of the result; the full answer is saved as a report."""
    jarvis = brain._style() == "jarvis"
    yield "On it, sir." if jarvis else "On it."
    sys_prompt = (brain.persona() + "\nYou have tools: use them. Your answer will be read aloud first, so start "
                  "with a two or three sentence plain-English summary, then give the details below it.")
    msgs = [{"role": "system", "content": sys_prompt}] + list((history or [])[-6:]) + [{"role": "user", "content": text}]
    full, buf, said = "", "", 0
    try:
        for chunk in OJ.stream(msgs):
            full += chunk
            buf += chunk
            while said < 3:
                m = re.search(r"^(.{12,}?[.!?])(\s+)", buf, re.S)
                if not m:
                    break
                yield brain.speakable(m.group(1).strip())
                buf, said = buf[m.end():], said + 1
    except Exception as e:  # noqa: BLE001
        S.log("voice", f"OpenJarvis failed: {e}")
        if not full:
            return False  # fall back to the quick brain
    if said < 3 and buf.strip():
        yield brain.speakable(buf.strip()[:300])
    OJ.save_report(text, full)
    if len(full) > 400:
        yield "The full write-up is in the Vector app, sir." if jarvis else "The full answer is in the Vector app."
    return True


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
