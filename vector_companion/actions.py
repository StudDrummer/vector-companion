"""Things Vector does on request, run by the companion itself.

Why: on a regular (non-developer) Vector, built-in games and tricks only start when he hears them through
his own microphones. A remote "play blackjack" command is not recognized (he just reacts happily). So the
companion does them directly with his real animations, his voice and his face screen. They work the same
from the app, from "Hey Jarvis", from Claude and from the cube.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import datetime
from pathlib import Path

from . import face_art, settings as S

GREEN, RED, GOLD, WHITE, BLUE = (48, 215, 75), (255, 69, 58), (255, 214, 10), (240, 240, 245), (100, 210, 255)

# safe on the dock: no wheels. First trigger name that exists wins (exact, then substring).
ANIMS = {
    "fist_bump": ("FistBumpRequestOnce", "FistBumpSuccess", "FistBump"),
    "love": ("Feedback_ILoveYou", "ILoveYou"),
    "praise": ("Feedback_GoodRobot", "GoodRobot"),
    "scold": ("Feedback_BadRobot", "BadRobot", "MeanWords"),
    "hello": ("GreetAfterLongTime", "OnboardingReactToFaceHappy", "ReactToGreeting"),
    "goodbye": ("Feedback_Goodbye", "Goodbye", "GoToSleepGetIn"),
    "sleep": ("GoToSleepGetIn", "GoToSleep", "Sleeping"),
    "win": ("BlackJack_VictorWin", "VictorWin", "CelebrateSuccess"),
    "lose": ("BlackJack_VictorLose", "VictorLose", "FrustratedByFailure"),
    "push": ("BlackJack_VictorPush", "Shrug"),
    "think": ("KnowledgeGraphSearchingGetIn", "Thinking"),
}
TRICKS = ("Sneeze", "Feedback_ILoveYou", "FistBumpSuccess", "BlackJack_VictorWin", "OnboardingReactToFaceHappy",
          "PettingLevel4", "GreetAfterLongTime", "KnowledgeGraphSearchingGetOutSuccess", "Hiccup", "Feedback_GoodRobot")

# what each app/voice action does; "drives" ones are refused while the dock lock is on
CATALOG = {
    "blackjack": "Play blackjack", "bj_hit": "Hit", "bj_stand": "Stand", "fist_bump": "Fist bump",
    "trick": "Do a trick", "love": "I love you", "praise": "Good robot", "scold": "Bad robot",
    "hello": "Say hi", "goodbye": "Goodbye", "time": "What time is it", "age": "How old are you",
    "name": "What's my name", "sleep": "Go to sleep", "go_to_charger": "Go home", "take_photo": "Take a photo",
    "volume_up": "Louder", "volume_down": "Quieter", "be_quiet": "Be quiet",
}
DRIVES = {"dance", "explore", "come_here", "look_at_me", "fetch_cube", "roll_cube", "pop_a_wheelie"}


def _jarvis() -> bool:
    return S.load().get("persona", {}).get("style") == "jarvis"


class Actions:
    def __init__(self, comp):
        self.c = comp
        self.bj: "Blackjack | None" = None

    def anim(self, key: str) -> str | None:
        from .companion import play_trigger  # noqa: F811
        trig = self.c.find_trigger(*ANIMS.get(key, (key,)))
        if trig:
            with self.c.control() as r:
                play_trigger(r, trig)
        return trig

    def say(self, text: str):
        self.c.say(text)

    def run(self, action: str) -> dict:
        a = action.strip().lower()
        from .companion import OWNER as owner
        if a in DRIVES:
            if S.load()["safety"].get("dock_lock"):
                raise PermissionError("He has to stay on the charger until his new battery is in (dock lock).")
            from .wirepod import INTENTS, Vector  # best effort: these are his own driving behaviors
            Vector().intent(INTENTS.get(a, a))
            return {"sent": a}
        if a == "blackjack":
            self.bj = Blackjack(self)
            threading.Thread(target=self.bj.deal, daemon=True).start()
            return {"started": "blackjack"}
        if a == "bj_status":
            self.say(self.bj.describe() if self.bj else "We're not in a game. Say play blackjack to start one.")
            return {}
        if a in ("bj_hit", "bj_stand"):
            if not (self.bj and self.bj.active):
                self.say("We're not playing right now. Say play blackjack to start a game.")
                return {"playing": False}
            threading.Thread(target=self.bj.hit if a == "bj_hit" else self.bj.stand, daemon=True).start()
            return {"playing": True}
        if a == "trick":
            pool = [t for t in TRICKS if t in self.c.triggers] or [t for t in self.c.triggers if "Feedback" in t]
            trig = random.choice(pool)
            from .companion import play_trigger
            with self.c.control() as r:
                play_trigger(r, trig)
            return {"played": trig}
        if a in ("fist_bump", "love", "praise", "scold"):
            trig = self.anim(a)
            if not trig:
                self.say({"fist_bump": "Fist bump!", "love": "I love you too!", "praise": "Thank you!",
                          "scold": "Sorry. I'll do better."}[a])
            return {"played": trig}
        if a == "hello":
            self.anim("hello")
            self.say("Good day, sir." if _jarvis() else f"Hi {owner}!")
            return {}
        if a == "goodbye":
            self.say("Goodbye, sir." if _jarvis() else f"Bye {owner}! See you soon.")
            return {}
        if a == "time":
            now = datetime.now()
            self.say(f"It's {now:%-I:%M} {'in the morning' if now.hour < 12 else 'in the afternoon' if now.hour < 17 else 'in the evening'}.")
            return {}
        if a == "age":
            self.say("I came online in 2018, and I've been your robot since 2019.")
            return {}
        if a == "name":
            self.say(f"You're {owner}" + (", sir." if _jarvis() else "!"))
            return {}
        if a == "sleep":
            self.say("Good night, sir." if _jarvis() else "Okay, nap time.")
            self.anim("sleep")
            return {}
        if a == "go_to_charger":
            with self.c.control() as r:
                r.behavior.drive_on_charger()
            return {}
        if a == "take_photo":
            return self.photo()
        if a in ("volume_up", "volume_down"):
            from .wirepod import Vector
            v = Vector()
            try:
                cur = int((v.robot_settings() or {}).get("master_volume", 3))
            except Exception:  # noqa: BLE001
                cur = 3
            new = max(0, min(5, cur + (1 if a == "volume_up" else -1)))
            v.volume(new)
            self.say("Louder." if new > cur else "Quieter." if new < cur else "That's as far as it goes.")
            return {"volume": new}
        if a == "be_quiet":
            return {}
        raise ValueError(f"unknown action {action!r}")

    def photo(self) -> dict:
        folder = Path.home() / "Pictures" / "Vector"
        folder.mkdir(parents=True, exist_ok=True)
        with self.c.control() as r:
            self.c.show(face_art.camera(), 1.0, with_control=r)
            self.c.speak(r, "Say cheese!")
        data = self.c.capture()
        path = folder / datetime.now().strftime("Vector %Y-%m-%d at %H.%M.%S.jpg")
        path.write_bytes(data)
        from .companion import mac_notify
        mac_notify("Vector took a photo", f"Saved to Pictures/Vector/{path.name}")
        return {"saved": str(path)}


RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
NAMES = {"A": "an ace", "J": "a jack", "Q": "a queen", "K": "a king", "8": "an 8"}


SUITS = "hdsc"


def value(hand: list) -> int:
    total, aces = 0, 0
    for c in (x[0] for x in hand):
        total += 11 if c == "A" else 10 if c in ("J", "Q", "K") else int(c)
        aces += c == "A"
    while total > 21 and aces:
        total, aces = total - 10, aces - 1
    return total


def spoken(card) -> str:
    r = card[0]
    return NAMES.get(r, f"a {r}")


class Blackjack:
    """You against Vector. Cards on his face, he talks you through it.
    Hit / stand: say it ("Hey Jarvis, hit"), tap the cube (once = hit, twice = stand), or use the app."""

    def __init__(self, actions: Actions):
        self.a, self.c = actions, actions.c
        self.deck = [(r, s) for r in RANKS for s in SUITS]
        random.shuffle(self.deck)
        self.you: list = []
        self.me: list = []
        self.active = False
        self.lock = threading.Lock()
        self.current = None
        self.show_until = 0.0
        self.refresher = None

    def table(self, reveal: bool = False, banner: str = "", color=GREEN):
        me = self.me if reveal else [self.me[0], None]
        return face_art.blackjack(self.you, me, value(self.you), value(self.me) if reveal else None, banner, color)

    def present(self, text: str, reveal: bool = False, linger: float = 3.0, banner: str = "", color=GREEN):
        """Cards on his face while he talks (kept there by _keep_table), then a few seconds more."""
        self.current = self.table(reveal, banner, color)
        self.show_until = time.time() + 600 if self.active else time.time() + 8
        if not self.refresher:
            self.refresher = threading.Thread(target=self._keep_table, daemon=True)
            self.refresher.start()
        with self.c.control() as r:
            self.c.put_screen(r, self.current, 5)
            self.c.speak(r, text)
        self.c.ctl_last = time.time() + linger

    def _keep_table(self):
        """His voice and idle face can paint over the screen, so keep re-sending the table while we play."""
        raw_call = self.c.call
        while time.time() < self.show_until and self.c.actions.bj is self:
            try:
                if self.c.has_control() and self.current is not None:
                    from anki_vector import screen as scr
                    data = scr.convert_image_to_screen_data(self.current.convert("RGB"))
                    raw = self.c.raw
                    raw_call(lambda: raw.screen.set_screen_with_image_data(data, 2.5, interrupt_running=True), 4,
                             "keep_table", kill_link=False)
                    self.c.ctl_last = time.time()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.8)  # faster than his eye animation can take the screen back
        self.refresher = None

    def describe(self) -> str:
        """For "what's my card?" mid-game."""
        if not self.active:
            return "We're not in a game. Say play blackjack to start one."
        cards = ", ".join(spoken(c) for c in self.you)
        return f"You have {cards}, that's {value(self.you)}. I'm showing {spoken(self.me[0])}. Hit or stand?"

    def deal(self):
        with self.lock:
            self.you = [self.deck.pop(), self.deck.pop()]
            self.me = [self.deck.pop(), self.deck.pop()]
            self.active = True
            self.c.pause_still(600)  # keep him free for the game
            if self.c.cube_connected:
                self.c.cube_color("blue")
            y = value(self.you)
            self.present(f"Let's play. You have {spoken(self.you[0])} and {spoken(self.you[1])}, that's {y}. "
                         f"I'm showing {spoken(self.me[0])}." + ("" if y == 21 else " Hit or stand?"))
            if y == 21:
                self._finish("Blackjack! You win.", "lose")

    def hit(self):
        with self.lock:
            if not self.active:
                return
            card = self.deck.pop()
            self.you.append(card)
            y = value(self.you)
            if y > 21:
                self._finish(f"{spoken(card).capitalize()}. That's {y}, you bust. I win!", "win")
            elif y == 21:
                self.present(f"{spoken(card).capitalize()}. Twenty one!", linger=0.5)
                self._dealer()
            else:
                self.present(f"{spoken(card).capitalize()}. You're at {y}. Hit or stand?")

    def stand(self):
        with self.lock:
            if self.active:
                self._dealer()

    def _dealer(self):
        y = value(self.you)
        line = [f"You stand on {y}. I flip {spoken(self.me[1])}, that's {value(self.me)}."]
        while value(self.me) < 17:
            card = self.deck.pop()
            self.me.append(card)
            line.append(f"I draw {spoken(card)}, {value(self.me)}.")
        m = value(self.me)
        if m > 21:
            self._finish(" ".join(line) + " I bust. You win!", "lose")
        elif m > y:
            self._finish(" ".join(line) + f" {m} beats {y}. I win!", "win")
        elif m < y:
            self._finish(" ".join(line) + f" {y} beats {m}. You win!", "lose")
        else:
            self._finish(" ".join(line) + " It's a tie.", "push")

    def _finish(self, text: str, outcome: str):
        self.active = False
        if self.c.cube_connected:
            self.c.cube_color({"win": "red", "lose": "green"}.get(outcome, "yellow"), 5)
        banner, color = {"win": ("VECTOR WINS", RED), "lose": ("YOU WIN!", GREEN)}.get(outcome, ("PUSH", GOLD))
        self.present(text, reveal=True, linger=3.5, banner=banner, color=color)
        try:
            self.a.anim(outcome)
        except Exception:  # noqa: BLE001
            pass
