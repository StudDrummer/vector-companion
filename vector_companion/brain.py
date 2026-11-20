"""Vector's brain: an OpenAI-compatible chat server that wire-pod talks to.

Point wire-pod's Knowledge Graph at this server ("Custom" provider,
endpoint http://localhost:11500/v1). Every question you ask Vector then
comes here, gets your persona + memory + live context (time, your git
activity if enabled, your to-do list), and is answered by:

  * a local model through Ollama (default, free, private), or
  * Claude through the Anthropic API (set ANTHROPIC_API_KEY), or
  * any other OpenAI-compatible server.

Some requests are handled locally without the LLM at all:
  "remember that ...", "what do you remember", "forget everything",
  "add ... to my list", "what's on my list", "clear my list",
  "start a 25 minute study timer" / "pomodoro".

Run:  python -m vector_companion.brain
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, settings as S

config.load_env()

HOST = os.environ.get("BRAIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("BRAIN_PORT", "11500"))
BACKEND = os.environ.get("BRAIN_BACKEND", "ollama").lower()  # ollama | anthropic | openai
MODEL = os.environ.get("BRAIN_MODEL", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1")
OPENAI_URL = os.environ.get("OPENAI_COMPAT_URL", "")
OPENAI_KEY = os.environ.get("OPENAI_COMPAT_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OWNER = os.environ.get("VECTOR_OWNER", "Rushil")
_pd = os.environ.get("PROJECTS_DIR", "").strip()  # blank = off
PROJECTS_DIR = Path(os.path.expanduser(_pd)) if _pd else None
DATA_DIR = Path(os.path.expanduser(os.environ.get("VECTOR_DATA_DIR", "~/.vector-companion")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"
TODO_FILE = DATA_DIR / "todo.json"

DEFAULT_MODELS = {
    "ollama": "llama3.2:3b",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-5.5",
}

STYLES = {
    "vector": "",
    "jarvis": ("Personality: you are a JARVIS-style AI: a calm, impeccably polite British butler with a dry, "
               "understated wit, who is also quick, practical and upbeat. Address the user as 'sir'. "
               "Lead with the answer, keep it brief, and when it helps, proactively offer the obvious next step "
               "(a focus timer, a reminder, checking his homework). Never claim to be a movie character."),
}


def style_prompt() -> str:
    try:
        from . import settings as _S
        return STYLES.get(_S.load().get("persona", {}).get("style", "vector"), "")
    except Exception:  # noqa: BLE001
        return ""


PERSONA = f"""You are Vector, a small, curious, slightly mischievous desk robot who lives with {OWNER}.
{OWNER} is a high school student in Bellevue, WA who builds AI and health-tech projects and does biomedical research.
You are his study buddy and lab companion: encouraging, funny, honest, and brief.
Rules for speaking out loud:
- Your words are spoken by a robot voice. Answer in 1-3 short sentences unless asked for more.
- No markdown, lists, emojis, code, or URLs. Spell out symbols ("percent", "degrees").
- If you do not know something current, say so instead of guessing.
"""

_state_lock = threading.Lock()


# ------------------------------------------------------------------ storage
def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2))


# ------------------------------------------------------------------ context
def git_activity(max_repos: int = 4) -> str:
    if PROJECTS_DIR is None or not PROJECTS_DIR.is_dir():
        return ""
    lines = []
    repos = [p for p in PROJECTS_DIR.iterdir() if (p / ".git").exists()]
    repos.sort(key=lambda p: (p / ".git").stat().st_mtime, reverse=True)
    for repo in repos[:max_repos]:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), "log", "-1", "--format=%cr: %s"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if out:
                lines.append(f"{repo.name} (last commit {out})")
        except Exception:  # noqa: BLE001
            continue
    return "; ".join(lines)


def live_context() -> str:
    now = datetime.now()
    parts = [f"Current local time: {now:%A, %B %d %Y, %I:%M %p}."]
    mem = _load(MEMORY_FILE, [])
    if mem:
        parts.append("Things " + OWNER + " asked you to remember: " + " | ".join(m["text"] for m in mem[-25:]))
    todo = _load(TODO_FILE, [])
    if todo:
        parts.append(f"{OWNER}'s to-do list: " + "; ".join(todo))
    ga = git_activity()
    if ga:
        parts.append("Recent project activity: " + ga)
    return "\n".join(parts)


# ------------------------------------------------------------------ local skills
_timers: list[threading.Timer] = []


def _speak_later(text: str, delay_s: float) -> None:
    def fire():
        try:
            from .wirepod import Vector
            v = Vector()
            with v.flash_eyes("lime"):
                v.say(text)
        except Exception as e:  # noqa: BLE001
            print(f"[brain] timer speak failed: {e}")
    t = threading.Timer(delay_s, fire)
    t.daemon = True
    t.start()
    _timers.append(t)


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20,
              "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60}


def _minutes(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:minute|min)", text)
    if m:
        return int(m.group(1))
    for w, n in sorted(_NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{w}\s*minute", text):
            return n
    return None


def local_skill(utterance: str) -> str | None:
    orig = utterance.strip().rstrip(".?!")
    t = orig.lower()
    with _state_lock:
        m = re.match(r"^(?:please )?remember (?:that )?(.+)$", t)
        if m:
            mem = _load(MEMORY_FILE, [])
            mem.append({"text": orig[m.start(1):], "at": datetime.now().isoformat(timespec="minutes")})
            _save(MEMORY_FILE, mem)
            return "Got it. I'll remember that."
        if re.search(r"what do you remember|what have i told you", t):
            mem = _load(MEMORY_FILE, [])
            if not mem:
                return "Nothing yet. Tell me to remember something."
            return "You told me: " + ". ".join(x["text"] for x in mem[-5:]) + "."
        if re.search(r"forget everything", t):
            _save(MEMORY_FILE, [])
            return "Okay. My memory is wiped clean."
        if re.search(r"\bweather\b|temperature outside|\bumbrella\b|need a jacket|is it (going to )?(rain|snow|cold)", t):
            try:
                from . import weather
                return weather.sentence("tomorrow" if "tomorrow" in t else "today")
            except Exception as e:  # noqa: BLE001
                print(f"[brain] weather failed: {e}")
                return "I couldn't reach the weather service just now."
        m = re.search(r"\badd (.+?) to (?:my )?(?:to do |todo |to-do )?list$", t)
        if m:
            todo = _load(TODO_FILE, [])
            item = orig[m.start(1):m.end(1)]
            todo.append(item)
            _save(TODO_FILE, todo)
            n = len(todo)
            return f"Added {item}. You have {n} thing{'s' if n != 1 else ''} on your list."
        if re.search(r"what'?s on my (?:to do |todo )?list|read my list", t):
            todo = _load(TODO_FILE, [])
            return ("Your list: " + ". ".join(todo) + ".") if todo else "Your list is empty. Nice."
        if re.search(r"clear my (?:to do |todo )?list", t):
            _save(TODO_FILE, [])
            return "List cleared."
        if re.search(r"status report|sitrep|system status|how are we doing|give me a (status|rundown)", t):
            return status_report()
        if re.search(r"what did claude (do|say|finish)|is claude (done|finished)|claude update", t):
            c = _recent("claude")
            if not c:
                return "I haven't heard from Claude yet today."
            ago = _ago(c["at"])
            where = f" in {c['project']}" if c.get("project") else ""
            return f"{_addr()}Claude finished{where} {ago}. {c.get('summary') or ''}".strip()
        if re.fullmatch(r"(good ?night|goodnight|i'?m going to (bed|sleep)).*", t):
            soon = _reminders(1)
            msg = f"Good night{', sir' if _style() == 'jarvis' else ''}."
            if soon:
                msg += " Tomorrow: " + "; ".join(soon[:2]) + "."
            threading.Timer(6, lambda: _wp_intent("intent_system_sleep")).start()
            return msg + " Sleep well."
        if re.fullmatch(r"(good )?morning.*", t) or "briefing" in t:
            return briefing()
        if re.search(r"(guard|watch) (my |the )?desk|guard mode|i'?m (leaving|heading out|going out)|keep watch", t) \
                and not re.search(r"\b(stop|end|off|cancel)\b", t):
            from .companion_client import call
            try:
                call("/guard", {"on": True}, timeout=30)
                return ""  # he announces it himself
            except Exception:  # noqa: BLE001
                return "I can't reach my camera helper right now, so I can't guard the desk."
        if re.search(r"(stop|end|cancel|turn off) (the )?(desk )?guard|guard (mode )?off|i'?m back", t):
            from .companion_client import call
            try:
                n = len(call("/guard", {"on": False}, timeout=10).get("events") or [])
                return "Guard off. " + ("Nothing happened while you were gone." if n == 0 else
                                        f"I saw movement {n} time{'s' if n != 1 else ''}. The photos are in the app.")
            except Exception:  # noqa: BLE001
                return "Guard off."
        scan_mode = _scan_mode(t)
        if scan_mode:
            from .companion_client import call
            try:
                call("/scan", {"mode": scan_mode, "async": True, "countdown": False, "delay": 4})
            except Exception as e:  # noqa: BLE001
                return "My camera helper isn't running right now, so I can't scan. Open the Vector app to check."
            return {"explain": "Okay! Hold your homework up in front of my face. Taking the picture in three seconds.",
                    "solve": "On it. Hold the problem up in front of my face. Picture in three seconds.",
                    "read": "Sure. Hold the page up in front of me. Reading in three seconds.",
                    "describe": "Let me take a look."}[scan_mode]
        if re.search(r"(stop|cancel|end) (the |my )?(focus |study )?timer", t):
            try:
                from .companion_client import call
                call("/focus", {"stop": True})
            except Exception:  # noqa: BLE001
                pass
            return "Timer stopped."
        if re.search(r"how (much|long).*(left|remaining)|time (is )?left|how much longer", t):
            try:
                from .companion_client import call
                f = call("/health").get("focus")
                if f:
                    m = max(1, round(f["left_s"] / 60))
                    return f"About {m} minute{'s' if m != 1 else ''} left. Keep going."
            except Exception:  # noqa: BLE001
                pass
            return "There's no timer running."
        if re.search(r"pomodoro|study timer|focus timer|timer for|focus mode", t):
            mins = _minutes(t) or 25
            try:
                from .companion_client import call
                call("/focus", {"minutes": mins})
                return "Focus mode on."
            except Exception:  # noqa: BLE001
                _speak_later(f"Time's up {OWNER}! {mins} minutes done. Take a five minute break.", mins * 60)
                return f"Starting a {mins} minute focus timer. I'll tell you when it's done. Go get it."
    return None


def _style() -> str:
    try:
        from . import settings as _S
        return _S.load().get("persona", {}).get("style", "vector")
    except Exception:  # noqa: BLE001
        return "vector"


def _addr() -> str:
    return {"jarvis": "Sir, "}.get(_style(), "")


def _recent(kind: str):
    try:
        from .notify import recent
        return recent(kind)
    except Exception:  # noqa: BLE001
        return None


def _ago(ts: float) -> str:
    m = int((time.time() - ts) // 60)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''} ago"
    h = m // 60
    return f"{h} hour{'s' if h != 1 else ''} ago"


def _reminders(days: int = 3) -> list[str]:
    try:
        from .companion import upcoming_reminders
        return upcoming_reminders(days)
    except Exception:  # noqa: BLE001
        return []


def _wp_intent(intent: str) -> None:
    try:
        from .wirepod import Vector
        Vector().intent(intent)
    except Exception:  # noqa: BLE001
        pass


def _battery_word() -> str | None:
    try:
        from .wirepod import Vector
        b = Vector(timeout=4).battery()
        lvl = b.get("battery_level")
        word = {3: "full", 2: "good", 1: "low", 0: "very low"}.get(lvl)
        if b.get("is_on_charger_platform"):
            word = (word or "unknown") + ", on the charger"
        return word
    except Exception:  # noqa: BLE001
        return None


def briefing() -> str:
    now = datetime.now()
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
    who = "sir" if _style() == "jarvis" else OWNER
    out = [f"Good {part}, {who}. It's {now:%-I:%M} on {now:%A}."]
    if S.load()["weather"].get("enabled", True):
        try:
            from . import weather
            out.append(weather.sentence())
        except Exception as e:  # noqa: BLE001
            print(f"[brain] weather skipped: {e}")
    todo = _load(TODO_FILE, [])
    if todo:
        out.append(f"You have {len(todo)} thing{'s' if len(todo) != 1 else ''} on your list, starting with {todo[0]}.")
    soon = _reminders(3)
    if soon:
        out.append("Coming up: " + "; ".join(soon[:3]) + ".")
    return " ".join(out)


def status_report() -> str:
    from .companion_client import call
    lines, hud = [], []
    b = _battery_word()
    if b:
        lines.append(f"Battery {b}.")
        hud.append((f"BATTERY {b.split(',')[0].upper()}", (48, 215, 75)))
    try:
        f = call("/health", timeout=2).get("focus")
        if f:
            m = max(1, round(f["left_s"] / 60))
            lines.append(f"Focus timer: {m} minute{'s' if m != 1 else ''} left.")
            hud.append((f"FOCUS {m} MIN", (47, 214, 201)))
    except Exception:  # noqa: BLE001
        pass
    todo = _load(TODO_FILE, [])
    lines.append(f"{len(todo)} thing{'s' if len(todo) != 1 else ''} on your list." if todo else "Your list is clear.")
    hud.append((f"LIST {len(todo)}", (240, 240, 245)))
    c = _recent("claude")
    if c and time.time() - c["at"] < 6 * 3600:
        lines.append(f"Claude last finished {_ago(c['at'])}" + (f" in {c['project']}" if c.get("project") else "") + ".")
        hud.append(("CLAUDE " + _ago(c["at"]).replace(" ago", "").upper(), (255, 159, 10)))
    tr = _recent("terminal")
    if tr and time.time() - tr["at"] < 6 * 3600 and tr.get("seconds", 0) >= 30:
        lines.append(f"Your last long command, {tr['command']}, {'succeeded' if tr['rc'] == 0 else 'failed'}.")
    soon = _reminders(2)
    if soon:
        lines.append("Coming up: " + "; ".join(soon[:2]) + ".")
    try:
        call("/hud", {"lines": hud, "seconds": 8}, timeout=3)
    except Exception:  # noqa: BLE001
        pass
    return (_addr() + "here's your status. " if _addr() else "Status report. ") + " ".join(lines)


def _scan_mode(t: str) -> str | None:
    if re.search(r"(solve|answer) (this|my|the)", t):
        return "solve"
    if re.search(r"(scan|check|look at|help me with) (my |this |the )?(homework|worksheet|problem|work|notes|answer)", t):
        return "explain"
    if re.search(r"\bread (this|that|my|the|it)\b", t):
        return "read"
    if re.search(r"what do you see|what am i holding|what is this|what's this|look at this", t):
        return "describe"
    return None


# ------------------------------------------------------------------ LLM backends
def _model() -> str:
    m = MODEL or DEFAULT_MODELS.get(BACKEND, "llama3.2:3b")
    return chat_model(m) if BACKEND == "ollama" else m


# Models that "think" before answering. Fine for homework photos, far too slow (and often empty) for talking.
THINKERS = re.compile(r"qwen3|deepseek-r1|qwq|gpt-oss|magistral|phi4-reasoning|cogito", re.I)
FAST_TALKERS = ("llama3.2:3b", "llama3.2", "gemma3:4b", "llama3.1:8b", "qwen2.5:7b", "qwen2.5:3b", "mistral", "gemma3")
_chat_cache: dict = {}


def installed_ollama() -> list[str]:
    try:
        with urllib.request.urlopen(_ollama_base() + "/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def chat_model(preferred: str) -> str:
    """Use the chosen model for talking unless it's a thinking model; then pick a fast one that's installed."""
    if not THINKERS.search(preferred or ""):
        return preferred
    if preferred in _chat_cache and time.time() - _chat_cache[preferred][1] < 300:
        return _chat_cache[preferred][0]
    names = installed_ollama()
    pick = next((n for want in FAST_TALKERS for n in names if n == want or n.startswith(want + ":")
                 or (":" not in want and n.split(":")[0] == want)), None)
    pick = pick or next((n for n in names if not THINKERS.search(n) and "uncensored" not in n), preferred)
    _chat_cache[preferred] = (pick, time.time())
    return pick


def stream_llm(messages: list[dict]):
    """Yield text chunks from the configured backend."""
    if BACKEND == "anthropic":
        yield from _stream_anthropic(messages)
    elif BACKEND == "ollama":
        got = False
        for c in _stream_ollama(messages):
            got = got or bool(c.strip())
            yield c
        if not got:  # the model spent its whole budget "thinking": answer with a fast model instead
            alt = next((n for n in installed_ollama() if not THINKERS.search(n) and "uncensored" not in n), None)
            if alt and alt != _model():
                print(f"[brain] {_model()} gave no answer; retrying with {alt}")
                yield from _stream_ollama(messages, model=alt)
    else:
        yield from _stream_openai(OPENAI_URL, OPENAI_KEY, messages)


def _ollama_base() -> str:
    b = OLLAMA_URL.rstrip("/")
    return b[:-3] if b.endswith("/v1") else b


KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "2h")  # keep the model in memory between questions


def _stream_ollama(messages, think: bool = False, max_tokens: int = 350, model: str | None = None):
    """Ollama's native chat API: lets us switch 'thinking' off (fast, and the whole budget goes to the answer)."""
    body = {"model": model or _model(), "messages": messages, "stream": True, "keep_alive": KEEP_ALIVE,
            "think": think, "options": {"num_predict": max_tokens, "temperature": 0.7}}
    url = _ollama_base() + "/api/chat"
    for attempt in (1, 2):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                in_think = False
                for raw in resp:
                    try:
                        ev = json.loads(raw)
                    except ValueError:
                        continue
                    text = (ev.get("message") or {}).get("content") or ""
                    out = ""
                    while text:  # drop any inline <think>...</think>, even across chunks
                        if in_think:
                            end = text.find("</think>")
                            if end == -1:
                                text = ""
                            else:
                                in_think, text = False, text[end + len("</think>"):]
                        else:
                            start = text.find("<think>")
                            if start == -1:
                                out, text = out + text, ""
                            else:
                                out, in_think, text = out + text[:start], True, text[start + len("<think>"):]
                    if out:
                        yield out
                    if ev.get("done"):
                        return
            return
        except urllib.error.HTTPError as e:
            if attempt == 1 and e.code == 400:  # model doesn't accept the think flag: retry without it
                body.pop("think", None)
                continue
            raise


def warm_up():
    """Load the local model into memory at startup so the first question isn't slow."""
    if BACKEND != "ollama":
        return
    try:
        req = urllib.request.Request(_ollama_base() + "/api/chat", data=json.dumps(
            {"model": _model(), "messages": [{"role": "user", "content": "hi"}], "stream": False,
             "keep_alive": KEEP_ALIVE, "think": False, "options": {"num_predict": 1}}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=180).read()
        print(f"[brain] {_model()} loaded and warm")
    except Exception as e:  # noqa: BLE001
        print(f"[brain] warm-up failed: {e}")


def _sse_lines(resp):
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("data:"):
            yield line[5:].strip()


def _stream_openai(base: str, key: str, messages):
    req_body = {"model": _model(), "messages": messages, "stream": True}
    if "api.openai.com" in base:  # newer OpenAI models: max_completion_tokens, default temperature
        req_body["max_completion_tokens"] = 1200
    else:
        req_body.update({"max_tokens": 400, "temperature": 0.8})
    body = json.dumps(req_body).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        for data in _sse_lines(resp):
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                yield delta


def _stream_anthropic(messages):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    convo = [{"role": m["role"], "content": m["content"]} for m in messages
             if m["role"] in ("user", "assistant") and m.get("content")]
    while convo and convo[0]["role"] != "user":
        convo.pop(0)
    body = json.dumps({"model": _model(), "max_tokens": 400, "system": system,
                       "messages": convo, "stream": True}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        for data in _sse_lines(resp):
            try:
                ev = json.loads(data)
            except ValueError:
                continue
            if ev.get("type") == "content_block_delta":
                txt = ev.get("delta", {}).get("text")
                if txt:
                    yield txt


_MD = re.compile(r"[*#`_>]|https?://\S+")


def speakable(chunk: str) -> str:
    # keep wire-pod action tags like {{playAnimation||...}} intact; strip markdown noise
    return _MD.sub("", chunk)


def build_messages(incoming: list[dict]) -> tuple[list[dict], str]:
    sys_parts = [m.get("content", "") for m in incoming if m.get("role") == "system"]
    rest = [m for m in incoming if m.get("role") != "system" and m.get("content")]
    user_text = next((m["content"] for m in reversed(rest) if m["role"] == "user"), "")
    about = ""
    try:
        about = (DATA_DIR / "about_me.txt").read_text().strip()
    except OSError:
        pass
    system = PERSONA + style_prompt() + ("\nAbout " + OWNER + ": " + about + "\n" if about else "") + "\n" + live_context()
    system += ("\nYou can see through your camera: if asked to look at, read, or check something, tell them to say "
               "'check my homework' or 'what do you see' and you'll take a picture.")
    if sys_parts:  # wire-pod's prompt carries the robot action instructions; keep it
        system += "\n\nInstructions from the robot's voice server:\n" + "\n".join(sys_parts)
    return [{"role": "system", "content": system}] + rest, user_text


# ------------------------------------------------------------------ HTTP server
class Handler(BaseHTTPRequestHandler):
    server_version = "VectorBrain/1.0"

    def log_message(self, fmt, *args):  # quieter logs (skip the constant health checks)
        msg = fmt % args
        if "/health" not in msg:
            print("[brain]", msg)

    def _json(self, code: int, obj) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "vector-brain", "object": "model"}]})
        elif self.path in ("/", "/health"):
            self._json(200, {"ok": True, "backend": BACKEND, "model": _model(), "chosen": MODEL or None})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        messages, user_text = build_messages(req.get("messages", []))
        print(f"[brain] heard: {user_text!r}")
        stream = bool(req.get("stream"))
        canned = local_skill(user_text)
        chunks = iter([canned]) if canned else self._safe_stream(messages)

        cid, created = f"chatcmpl-{uuid.uuid4().hex[:12]}", int(time.time())
        if not stream:
            text = "".join(speakable(c) for c in chunks)
            return self._json(200, {
                "id": cid, "object": "chat.completion", "created": created, "model": "vector-brain",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}]})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(delta, finish=None):
            payload = {"id": cid, "object": "chat.completion.chunk", "created": created,
                       "model": "vector-brain",
                       "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        try:
            emit({"role": "assistant", "content": ""})
            for c in chunks:
                c = speakable(c)
                if c:
                    emit({"content": c})
            emit({}, "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _safe_stream(messages):
        got = False
        try:
            for c in stream_llm(messages):
                if c.strip():
                    got = True
                yield c
            if not got:  # never hand wire-pod an empty answer
                yield "Hmm, I lost my train of thought. Could you ask me that again?"
        except Exception as e:  # noqa: BLE001
            print(f"[brain] backend error: {e}")
            yield "Hmm, my brain server is not answering right now. Check that the model is running."


def main():
    threading.Thread(target=warm_up, daemon=True).start()
    print(f"[brain] Vector brain on http://{HOST}:{PORT}/v1  backend={BACKEND} model={_model()}")
    print(f"[brain] data dir: {DATA_DIR}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
