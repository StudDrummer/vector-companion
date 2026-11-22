"""Quiz mode: "Hey Jarvis, quiz me on DNA replication".

He makes five short questions with the AI, asks them out loud, listens to your spoken answers (Hey Jarvis
follow-ups, no wake word needed), tells you if you're right, keeps score on his face, and remembers what
you missed so "quiz me on my mistakes" reviews them later.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from datetime import datetime

from . import face_art, settings as S

MISSES = S.DATA_DIR / "quiz_misses.json"
CYAN, WHITE, GREEN, RED, GOLD = (100, 210, 255), (240, 240, 245), (48, 215, 75), (255, 69, 58), (255, 214, 10)


def _llm(prompt: str, max_tokens: int = 600) -> str:
    from . import brain
    msgs = [{"role": "system", "content": "You write short, accurate study questions for a high school junior "
                                          "taking AP classes. Reply with JSON only."},
            {"role": "user", "content": prompt}]
    if brain.BACKEND == "ollama":
        return "".join(brain._stream_ollama(msgs, max_tokens=max_tokens))
    return "".join(brain.stream_llm(msgs))


def _words(s: str) -> set:
    stop = {"the", "a", "an", "of", "and", "or", "to", "is", "it", "in", "its", "it's", "that", "which"}
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if w not in stop}


def _load_misses() -> list:
    try:
        return json.loads(MISSES.read_text())
    except Exception:  # noqa: BLE001
        return []


class Quiz:
    def __init__(self, comp, topic: str):
        self.c, self.topic = comp, topic.strip() or "general science"
        self.qs: list[dict] = []
        self.i = 0
        self.score = 0
        self.active = False
        self.lock = threading.Lock()

    # ------------------------------------------------------------ setup
    def generate(self) -> bool:
        if re.search(r"mistake|missed|wrong", self.topic):
            past = _load_misses()[-12:]
            random.shuffle(past)
            self.qs = past[:5]
            self.topic = "your past mistakes"
            return bool(self.qs)
        raw = _llm(f'Write 5 quiz questions about "{self.topic}". Each answer must be a few words, not a sentence. '
                   'Format: [{"q": "question?", "a": "short answer"}, ...]')
        m = re.search(r"\[.*\]", raw, re.S)
        try:
            items = json.loads(m.group(0)) if m else []
        except ValueError:
            items = []
        self.qs = [{"q": str(x.get("q", "")).strip(), "a": str(x.get("a", "")).strip()}
                   for x in items if isinstance(x, dict) and x.get("q") and x.get("a")][:5]
        return len(self.qs) >= 2

    def hud(self, banner: str = "", color=CYAN):
        n = len(self.qs)
        lines = [(f"Question {min(self.i + 1, n)} of {n}", WHITE), (f"Score {self.score}", GOLD)]
        if banner:
            lines.append((banner, color))
        return face_art.card_hud(f"Quiz · {self.topic[:16]}", lines, color)

    def show(self, banner: str = "", color=CYAN, seconds: float = 30):
        try:
            with self.c.control(wait=4) as r:
                self.c.put_screen(r, self.hud(banner, color), seconds)
            self.c.ctl_last = time.time() + 20
        except Exception:  # noqa: BLE001
            pass

    def start(self):
        jarvis = S.load().get("persona", {}).get("style") == "jarvis"
        self.c.say(("Very good, sir. " if jarvis else "Okay! ") + f"Making a quiz on {self.topic}.")
        if not self.generate():
            self.c.say(f"Sorry, I couldn't make questions about {self.topic}. Try a different topic.")
            return
        self.active = True
        self.c.pause_still(900)
        self.ask(intro=f"{len(self.qs)} questions. Say skip if you don't know. ")

    def ask(self, intro: str = ""):
        self.show()
        self.c.say(f"{intro}{self.question_text()}")

    def question_text(self) -> str:
        return f"Question {self.i + 1}. {self.qs[self.i]['q']}"

    # ------------------------------------------------------------ answers
    def grade(self, answer: str) -> tuple[bool, str]:
        q = self.qs[self.i]
        want, got = _words(q["a"]), _words(answer)
        if want and (want <= got or (len(want) > 2 and len(want & got) / len(want) >= 0.6)):
            return True, ""
        if re.search(r"\b(skip|pass|don'?t know|no idea|not sure)\b", answer.lower()):
            return False, ""
        raw = _llm(f'Question: {q["q"]}\nCorrect answer: {q["a"]}\nStudent said: "{answer}"\n'
                   'Is the student essentially correct (synonyms and paraphrases count)? '
                   'Reply {"correct": true or false, "why": "one short sentence"}', max_tokens=80)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            j = json.loads(m.group(0)) if m else {}
        except ValueError:
            j = {}
        return bool(j.get("correct")), str(j.get("why", ""))[:160]

    def answer(self, text: str) -> None:
        with self.lock:
            if not self.active:
                return
            if re.search(r"\b(stop|end|quit|cancel)\b.*\b(quiz|it)\b|^(stop|quit)$", text.lower()):
                self.finish(stopped=True)
                return
            q = self.qs[self.i]
            ok, why = self.grade(text)
            if ok:
                self.score += 1
                line = random.choice(["Correct!", "That's right!", "Yes, exactly.", "Nailed it."])
                self.show("RIGHT", GREEN, 6)
            else:
                line = f"Not quite. The answer is {q['a']}." + (f" {why}" if why and len(why) < 120 else "")
                self._remember_miss(q)
                self.show("NOT QUITE", RED, 6)
            self.i += 1
            if self.i >= len(self.qs):
                self.c.say(line)
                self.finish()
            else:  # feedback and the next question in one breath, so the Mac doesn't hear him as you
                self.c.say(f"{line} {self.question_text()}")
                self.show()

    def _remember_miss(self, q: dict):
        misses = [m for m in _load_misses() if m.get("q") != q["q"]]
        misses.append({**q, "topic": self.topic, "at": datetime.now().strftime("%Y-%m-%d")})
        try:
            MISSES.write_text(json.dumps(misses[-100:], indent=1))
        except OSError:
            pass

    def finish(self, stopped: bool = False):
        self.active = False
        n = self.i if stopped else len(self.qs)
        if stopped and n == 0:
            self.c.say("Quiz stopped.")
            return
        pct = self.score / max(1, n)
        verdict = "Perfect score!" if pct == 1 else "Great job." if pct >= 0.8 else "Not bad." if pct >= 0.5 \
            else "Let's review this one again soon."
        self.show(f"{self.score} / {n}", GREEN if pct >= 0.8 else GOLD if pct >= 0.5 else RED, 8)
        self.c.say(f"You got {self.score} out of {n}. {verdict}" +
                   (" Say quiz me on my mistakes to review what you missed." if self.score < n else ""))
        try:
            trig = self.c.find_trigger("BlackJack_VictorWin" if pct >= 0.8 else "Feedback_GoodRobot")
            if trig and pct >= 0.5:
                from .companion import play_trigger
                with self.c.control() as r:
                    play_trigger(r, trig)
        except Exception:  # noqa: BLE001
            pass
