"""Jarvis's hands on the Mac: open apps and sites, check the calendar, take and read notes, hand a
question to Claude, look things up. Runs on the Mac (Ears / the app), so `open` and AppleScript work.

  "Jarvis, open Canvas"            "Jarvis, open Instagram"          "Jarvis, open Notes"
  "Jarvis, check my calendar"      "what's on my calendar tomorrow"  "what's due on Canvas"
  "Jarvis, take a note: ..."       "read my note about chem"         "what are my grades"
  "Jarvis, ask Claude what to do next"   "search YouTube for mitosis"  "google OCT angiography"
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

from . import settings as S

SITES = {
    "canvas": None,  # filled from canvas.base()
    "instagram": "https://www.instagram.com", "insta": "https://www.instagram.com",
    "youtube": "https://www.youtube.com", "gmail": "https://mail.google.com",
    "outlook": "https://outlook.office.com/mail", "school email": "https://outlook.office.com/mail",
    "email": "https://outlook.office.com/mail", "onedrive": "https://www.office.com/launch/onedrive",
    "office": "https://www.office.com", "teams": "https://teams.microsoft.com",
    "veracross": "https://portals.veracross.com/overlake", "flint": "https://app.flintk12.com",
    "github": "https://github.com", "google docs": "https://docs.google.com", "docs": "https://docs.google.com",
    "google drive": "https://drive.google.com", "drive": "https://drive.google.com",
    "claude": "https://claude.ai", "chatgpt": "https://chatgpt.com", "khan academy": "https://www.khanacademy.org",
    "college board": "https://mysat.collegeboard.org", "noodletools": "https://my.noodletools.com",
    "spotify": "https://open.spotify.com", "netflix": "https://www.netflix.com", "maps": "https://maps.apple.com",
    "pubmed": "https://pubmed.ncbi.nlm.nih.gov", "google scholar": "https://scholar.google.com",
    "scholar": "https://scholar.google.com", "linkedin": "https://www.linkedin.com", "reddit": "https://www.reddit.com",
    "x": "https://x.com", "twitter": "https://x.com", "whatsapp": "https://web.whatsapp.com",
    "amazon": "https://www.amazon.com", "ebay": "https://www.ebay.com", "target": "https://www.target.com",
    "costco": "https://www.costco.com", "best buy": "https://www.bestbuy.com", "walmart": "https://www.walmart.com",
    "google": "https://www.google.com", "google maps": "https://maps.google.com", "google calendar": "https://calendar.google.com",
    "wikipedia": "https://www.wikipedia.org", "quizlet": "https://quizlet.com", "desmos": "https://www.desmos.com/calculator",
    "wolfram alpha": "https://www.wolframalpha.com", "wolfram": "https://www.wolframalpha.com", "duolingo": "https://www.duolingo.com",
    "discord": "https://discord.com/app", "tiktok": "https://www.tiktok.com", "snapchat": "https://web.snapchat.com",
    "facebook": "https://www.facebook.com", "pinterest": "https://www.pinterest.com", "twitch": "https://www.twitch.tv",
    "hulu": "https://www.hulu.com", "disney plus": "https://www.disneyplus.com", "prime video": "https://www.primevideo.com",
    "apple music": "https://music.apple.com", "soundcloud": "https://soundcloud.com", "weather": "https://weather.com",
    "kaggle": "https://www.kaggle.com", "hugging face": "https://huggingface.co", "arxiv": "https://arxiv.org",
    "common app": "https://apply.commonapp.org", "stanford": "https://www.stanford.edu", "overlake": "https://www.overlake.org",
    "notion": "https://www.notion.so", "canva": "https://www.canva.com", "figma": "https://www.figma.com",
    "zoom": "https://zoom.us", "uber": "https://m.uber.com", "doordash": "https://www.doordash.com",
}
# spoken name -> app name, when they differ
APP_ALIASES = {"notes": "Notes", "calendar": "Calendar", "messages": "Messages", "imessage": "Messages",
               "music": "Music", "safari": "Safari", "chrome": "Google Chrome", "google chrome": "Google Chrome",
               "settings": "System Settings", "system settings": "System Settings", "finder": "Finder",
               "terminal": "Terminal", "vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
               "code": "Visual Studio Code", "word": "Microsoft Word", "excel": "Microsoft Excel",
               "powerpoint": "Microsoft PowerPoint", "reminders": "Reminders", "photos": "Photos",
               "facetime": "FaceTime", "mail": "Mail", "xcode": "Xcode", "claude app": "Claude",
               "vector": "Vector", "vector app": "Vector", "app store": "App Store", "preview": "Preview",
               "calculator": "Calculator", "clock": "Clock", "weather": "Weather"}
APP_DIRS = ["/Applications", "/System/Applications", "/System/Applications/Utilities", str(Path.home() / "Applications")]


def _style_sir() -> str:
    return ", sir" if S.load().get("persona", {}).get("style") == "jarvis" else ""


def _osascript(script: str, timeout: float = 25) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ------------------------------------------------------------------ open
def _apps() -> dict[str, str]:
    out = {}
    for d in APP_DIRS:
        try:
            for n in os.listdir(d):
                if n.endswith(".app"):
                    out[n[:-4].lower()] = os.path.join(d, n)
        except OSError:
            pass
    return out


def open_thing(name: str) -> str:
    n = re.sub(r"^(the|my|up)\s+", "", name.strip().lower()).strip(" .!?")
    n = re.sub(r"\s+(app|website|site|page)$", "", n)
    sir = _style_sir()
    if n in ("canvas", "my canvas", "school canvas"):
        from . import canvas
        subprocess.Popen(["open", canvas.base()])
        return f"Opening Canvas{sir}."
    apps = _apps()
    app = APP_ALIASES.get(n)
    if (app and app.lower() in apps) or n in apps:
        target = apps.get((app or n).lower())
        subprocess.Popen(["open", target])
        return f"Opening {os.path.basename(target)[:-4]}{sir}."
    if n in SITES and SITES[n]:
        subprocess.Popen(["open", SITES[n]])
        return f"Opening {name.strip().title()}{sir}."
    close = [a for a in apps if n and (a.startswith(n) or n in a)]
    if close:
        subprocess.Popen(["open", apps[close[0]]])
        return f"Opening {os.path.basename(apps[close[0]])[:-4]}{sir}."
    if re.match(r"^[\w-]+\.(com|org|net|edu|io|ai|gov|co|tv|us)$", n):
        subprocess.Popen(["open", "https://" + n])
        return f"Opening {n}{sir}."
    # one of your projects? open it on GitHub
    try:
        from . import github
        r = github.find_repo(n)
        if r:
            subprocess.Popen(["open", r["url"]])
            return f"Opening {r['name']} on GitHub{sir}."
    except Exception:  # noqa: BLE001
        pass
    # not an app or a known site: try <name>.com (amazon -> amazon.com) if that domain exists
    slug = re.sub(r"[^a-z0-9]", "", n)
    if 2 < len(slug) < 30:
        import socket
        socket.setdefaulttimeout(2)
        for dom in (f"www.{slug}.com", f"{slug}.com"):
            try:
                socket.gethostbyname(dom)
                subprocess.Popen(["open", "https://" + dom])
                return f"Opening {name.strip().title()}{sir}."
            except OSError:
                continue
    return f"I don't see an app or site called {name.strip()}{sir}."


BROWSERS = (("Google Chrome", "chrome"), ("Safari", "safari"), ("Arc", "chrome"), ("Microsoft Edge", "chrome"),
            ("Brave Browser", "chrome"))


def _running(app: str) -> bool:
    try:
        return _osascript(f'return application {_q(app)} is running', timeout=5) == "true"
    except Exception:  # noqa: BLE001
        return False


def close_thing(name: str) -> str:
    """Quit an app, or close the browser tabs for a site ("close Instagram")."""
    n = re.sub(r"^(the|my)\s+", "", name.strip().lower()).strip(" .!?")
    n = re.sub(r"\s+(app|website|site|page|tab|tabs)$", "", n)
    sir = _style_sir()
    apps = _apps()
    app = APP_ALIASES.get(n) or next((os.path.basename(v)[:-4] for k, v in apps.items() if k == n), None)
    site = SITES.get(n) or (f"{n}.com" if " " not in n else None)
    if n == "canvas":
        from . import canvas
        site = canvas.base()
    closed = 0
    if site:
        host = re.sub(r"^https?://(www\.)?", "", site).split("/")[0]
        for browser, kind in BROWSERS:
            if not _running(browser):
                continue
            if kind == "safari":
                script = (f'tell application "Safari" to repeat with w in windows\n'
                          f'repeat with t in (tabs of w whose URL contains {_q(host)})\nclose t\nend repeat\nend repeat')
            else:
                script = (f'set n to 0\ntell application {_q(browser)} to repeat with w in windows\n'
                          f'repeat with t in (tabs of w whose URL contains {_q(host)})\nclose t\nset n to n + 1\n'
                          'end repeat\nend repeat\nreturn n')
            try:
                out = _osascript(script)
                closed += int(out) if out.isdigit() else 1
            except Exception:  # noqa: BLE001
                pass
        if closed:
            return f"Closed {name.strip().title()}{sir}."
    if app and _running(app):
        _osascript(f'tell application {_q(app)} to quit')
        return f"{app} closed{sir}."
    return f"{name.strip().title()} isn't open{sir}."


def search(where: str, query: str) -> str:
    q = urllib.parse.quote_plus(query.strip())
    urls = {"youtube": f"https://www.youtube.com/results?search_query={q}",
            "scholar": f"https://scholar.google.com/scholar?q={q}", "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/?term={q}",
            "google": f"https://www.google.com/search?q={q}"}
    subprocess.Popen(["open", urls.get(where, urls["google"])])
    return f"Searching {where.title() if where in urls else 'Google'} for {query.strip()}{_style_sir()}."


# ------------------------------------------------------------------ calendar
def events(start: dt.date, days: int = 1) -> list[dict]:
    """Events from the Mac's Calendar app (every account added in System Settings > Internet Accounts)."""
    script = f'''
set d1 to current date
set year of d1 to {start.year}
set month of d1 to {start.month}
set day of d1 to {start.day}
set time of d1 to 0
set d2 to d1 + ({days} * days)
set out to ""
tell application "Calendar"
  repeat with c in calendars
    try
      set evs to (every event of c whose start date is greater than or equal to d1 and start date is less than d2)
      repeat with e in evs
        set out to out & ((start date of e) as «class isot» as string) & "|" & (summary of e) & "|" & (allday event of e as string) & linefeed
      end repeat
    end try
  end repeat
end tell
return out'''
    out = []
    for line in _osascript(script, timeout=40).splitlines():
        try:
            when, title, allday = line.split("|", 2)
            out.append({"start": dt.datetime.fromisoformat(when), "title": title.strip(), "allday": allday.strip() == "true"})
        except ValueError:
            continue
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: e["start"]):
        k = (e["start"], e["title"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def calendar_sentence(text: str) -> str:
    t = text.lower()
    today = dt.date.today()
    if "tomorrow" in t:
        day, label, n = today + dt.timedelta(days=1), "tomorrow", 1
    elif "week" in t:
        day, label, n = today, "this week", 7
    else:
        day, label, n = today, "today", 1
    try:
        evs = events(day, n)
    except Exception as e:  # noqa: BLE001
        S.log("voice", f"calendar read failed: {e}")
        if "not allowed" in str(e).lower() or "-1743" in str(e):
            return "I need permission to read your calendar. Allow Vector Ears to control Calendar in System Settings, Privacy and Security, Automation."
        return "I couldn't read your calendar just now."
    if label == "today":
        now = dt.datetime.now()
        evs = [e for e in evs if e["allday"] or e["start"] >= now - dt.timedelta(minutes=30)]
    if not evs:
        return f"Your calendar is clear {label}{_style_sir()}."

    def fmt(e):
        if e["allday"]:
            return f"{e['title']} all day"
        when = e["start"].strftime("%-I:%M %p").replace(":00", "")
        return f"{e['title']} at {when}" if n == 1 else f"{e['title']} {e['start'].strftime('%A')} at {when}"
    lines = [fmt(e) for e in evs[:5]]
    more = f", and {len(evs) - 5} more" if len(evs) > 5 else ""
    return f"{label.capitalize()}: " + "; ".join(lines) + more + "."


def calendar_context() -> str:
    try:
        evs = events(dt.date.today(), 2)
    except Exception:  # noqa: BLE001
        return ""
    if not evs:
        return "Calendar: nothing today or tomorrow."
    return "Calendar:\n" + "\n".join(f"- {e['start'].strftime('%a %-I:%M %p')}: {e['title']}" for e in evs[:10])


# ------------------------------------------------------------------ notes
def add_note(body: str) -> str:
    body = body.strip().strip(".")
    title = (body[:40] + "...") if len(body) > 40 else body
    html = "<div><b>" + _esc(title) + "</b></div><div>" + _esc(body) + "</div>"
    _osascript(f'tell application "Notes" to make new note with properties {{name:{_q(title)}, body:{_q(html)}}}')
    return f"Noted{_style_sir()}."


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_note(topic: str) -> str:
    topic = topic.strip().strip(".?")
    if topic:
        script = (f'tell application "Notes" to set ns to (notes whose name contains {_q(topic)})\n'
                  'if (count of ns) = 0 then return ""\n'
                  'tell application "Notes" to return (name of item 1 of ns) & "|" & (plaintext of item 1 of ns)')
    else:
        script = ('tell application "Notes" to set n to note 1\n'
                  'tell application "Notes" to return (name of n) & "|" & (plaintext of n)')
    out = _osascript(script)
    if not out:
        return f"I couldn't find a note about {topic}{_style_sir()}."
    name, _, body = out.partition("|")
    body = re.sub(r"\s+", " ", body).strip()
    if body.lower().startswith(name.lower()):
        body = body[len(name):].strip()
    return f"Your note {name}: {body[:400]}"


# ------------------------------------------------------------------ Claude
def ask_claude(question: str) -> str:
    """Opens Claude with the question ready to send (and what's due / on the calendar when it's about
    planning), on your own Claude account."""
    q = question.strip().strip("?.") + "?"
    if re.search(r"\b(what (should|do) i do next|what next|plan|priorit|what to (do|work on)|focus on)\b", q, re.I):
        from . import canvas
        from . import github
        ctx = "\n\n".join(x for x in (canvas.context(), calendar_context(), github.context()) if x)
        if ctx:
            q = f"{q}\n\nHere's what I have going on:\n{ctx}"
    subprocess.Popen(["open", "https://claude.ai/new?q=" + urllib.parse.quote(q)])
    return f"I've put that to Claude{_style_sir()}. It's on your screen."


# ------------------------------------------------------------------ music (Spotify app, or Apple Music)
def _player() -> str:
    apps = _apps()
    return "Spotify" if "spotify" in apps else "Music"


def music(cmd: str, query: str = "") -> str:
    import time as _t
    app, sir = _player(), _style_sir()
    if cmd == "play":
        if query:
            if app == "Spotify":
                subprocess.Popen(["open", "spotify:search:" + urllib.parse.quote(query)])
                return f"I've pulled up {query} in Spotify{sir}. Press play on the one you want."
            _osascript(f'tell application "Music" to play (first track of library playlist 1 whose name contains {_q(query)} or artist contains {_q(query)})')
            return f"Playing {query}{sir}."
        if not _running(app) and app == "Spotify":
            subprocess.Popen(["open", "-a", "Spotify"])
            _t.sleep(3)
        _osascript(f'tell application "{app}" to play')
        return now_playing(prefix="Playing")
    if cmd == "pause":
        if not _running(app):
            return f"Nothing is playing{sir}."
        _osascript(f'tell application "{app}" to pause')
        return f"Paused{sir}."
    if cmd == "next":
        _osascript(f'tell application "{app}" to next track')
        return now_playing(prefix="Now playing")
    if cmd == "previous":
        _osascript(f'tell application "{app}" to previous track')
        return now_playing(prefix="Now playing")
    return now_playing()


def now_playing(prefix: str = "This is") -> str:
    import time as _t
    app = _player()
    if not _running(app):
        return f"{app} isn't open{_style_sir()}. Say open {app} and pick something to play."
    _t.sleep(0.5)
    try:
        out = _osascript(f'tell application "{app}" to if player state is playing then return (name of current track) & " by " & (artist of current track)')
    except Exception:  # noqa: BLE001
        out = ""
    if not out:
        return f"Nothing is playing in {app} yet{_style_sir()}. Open it and pick something, and I can handle it from there."
    return f"{prefix} {out}{_style_sir()}."


# ------------------------------------------------------------------ reminders and timers
NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
       "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty five": 45, "forty-five": 45,
       "half an": 0.5, "a half": 0.5}


def parse_when(t: str) -> dt.datetime | None:
    """'in 20 minutes', 'in an hour', 'at 5', 'at 5:30 pm', 'tomorrow at 7 am'."""
    now = dt.datetime.now()
    m = re.search(r"\b(?:in|for) (\d+(?:\.\d+)?|" + "|".join(sorted(NUM, key=len, reverse=True)) + r") (seconds?|minutes?|mins?|hours?|hrs?)\b", t)
    if m:
        n = float(m.group(1)) if m.group(1)[0].isdigit() else NUM[m.group(1)]
        unit = m.group(2)
        secs = n * (1 if unit.startswith("sec") else 3600 if unit.startswith("h") else 60)
        return now + dt.timedelta(seconds=secs)
    if re.search(r"\bin half an hour\b", t):
        return now + dt.timedelta(minutes=30)
    m = re.search(r"\bat (\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and h < 8:
            h += 12  # "at 5" means 5 pm
        when = now.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if "tomorrow" in t or when <= now:
            when += dt.timedelta(days=1)
        return when
    return None


def remind(t: str) -> str:
    from .companion_client import call
    sir = _style_sir()
    timer = re.search(r"\b(set )?(a )?timer\b", t, re.I)
    when = parse_when(t.lower())
    if not when:
        return f"When should I remind you{sir}? Say something like in 20 minutes, or at 5 PM."
    if timer:
        what = "Timer's done"
    else:
        m = re.search(r"remind me (?:to |about |that )?(.+?)(?:\s+(?:in|at|tomorrow)\b.*)?$", t, re.I) or \
            re.search(r"remind me (?:in|at) .+? (?:to|about|that) (.+)$", t, re.I)
        what = (m.group(1) if m else "").strip() or "your reminder"
        if re.match(r"(in|at) ", what):
            m2 = re.search(r"\b(?:to|about|that) (.+)$", t, re.I)
            what = m2.group(1) if m2 else "your reminder"
    call("/remind", {"text": what, "at": when.timestamp()}, timeout=5)
    mins = round((when - dt.datetime.now()).total_seconds() / 60)
    if timer:
        return f"Timer set for {mins} minute{'s' if mins != 1 else ''}{sir}." if mins < 120 else f"Timer set{sir}."
    if mins < 90:
        return f"I'll remind you in {max(1, mins)} minute{'s' if mins != 1 else ''}{sir}."
    return f"I'll remind you at {when.strftime('%-I:%M %p')}{' tomorrow' if when.date() > dt.date.today() else ''}{sir}."


def list_reminders() -> str:
    from .companion_client import call
    r = call("/reminders", timeout=5).get("reminders", [])
    if not r:
        return f"No reminders set{_style_sir()}."
    parts = [f"{x['text']} at {dt.datetime.fromtimestamp(x['at']).strftime('%-I:%M %p')}" for x in r[:4]]
    return "Reminders: " + "; ".join(parts) + "."


HELP = ("I can open apps and sites, check your calendar and Canvas, take notes, play and pause music, set "
        "reminders and timers, start a study session, quiz you, research things, check GitHub, ask Claude, "
        "read your homework through my camera, guard your desk, and play blackjack.")


# ------------------------------------------------------------------ router
PATTERNS = [
    (r"^what can you do|^what are you able to do|^help$|^what can i (say|ask)", "help"),
    (r"\bremind me\b|\bset (?:a |an )?(?:timer|alarm|reminder)\b|\btimer for\b", "remind"),
    (r"\b(what are )?my reminders\b|\bwhat reminders\b", "list_reminders"),
    (r"^(?:can you |please )?(?:close|quit|exit|shut) (?:down )?(.+)$", "close"),
    (r"\bcanvas\b(?!.*\b(open|close)\b)|\bwhat (homework|assignments?) do i have\b|\bwhat do i have due\b|\bany (homework|assignments)\b", "canvas_any"),
    (r"^(?:play|resume|start|put on)(?: some| my)? (?:music|songs?|spotify|tunes)$|^(?:resume|unpause)(?: the)?(?: music| song| spotify)?$", "music_play"),
    (r"^(?:pause|stop)(?: the| my)? (?:music|song|spotify|track)$|^pause$", "music_pause"),
    (r"^(?:next|skip)(?: this)?(?: song| track)?$|^skip it$", "music_next"),
    (r"^(?:previous|last|go back)(?: a)? (?:song|track)$", "music_prev"),
    (r"^what(?:'s| is) (?:this song|playing|this track)$|^what song is (?:this|playing)$", "music_now"),
    (r"^(?:play|put on) (.+?)(?: on spotify| on apple music)?$", "music_query"),
    (r"^(?:can you |please )?(?:ask|tell) claude (?:to |about )?(.+)$", "claude"),
    (r"^(?:can you |please )?(?:search|look up) (youtube|google scholar|scholar|pubmed|google) for (.+)$", "search"),
    (r"^(?:can you |please )?google (.+)$", "google"),
    (r"^(?:can you |please )?(?:open|launch|pull up|bring up|go to) (.+)$", "open"),
    (r"\b(what'?s|what is|anything) (on|in) my (calendar|schedule)\b|\bcheck my (calendar|schedule)\b|\bmy (calendar|schedule) (today|tomorrow|this week)\b|\bdo i have anything (today|tomorrow|this week)\b", "calendar"),
    (r"\bwhat'?s due\b|\bdue (today|tomorrow|this week|soon)\b|\b(my )?(canvas|homework|assignments)( due)?\b.*\b(today|tomorrow|this week|due|left)\b|\bwhat (homework|assignments) do i have\b", "due"),
    (r"\b(my )?grades?\b.*\b(canvas|classes|now|right now)?\b|\bwhat'?s my grade\b", "grades"),
    (r"^(?:take|make|add|write) (?:a )?note(?: that| saying| to)?[:,]?\s*(.+)$|^note (?:that |to self )?(.+)$|^remember in (?:my )?notes (?:that )?(.+)$", "note"),
    (r"^(?:read|what'?s in|find) (?:me )?(?:my )?(?:latest |last )?note(?:s)?(?: about| on| for| called)?\s*(.*)$", "read_note"),
]


def skill(text: str) -> str | None:
    """Handle a Mac request, or None if this isn't one."""
    t = text.strip().rstrip(".!?")
    # two things at once: "open Spotify and play music"
    parts = re.split(r",?\s+and (?:then )?(?=(?:open|close|play|pause|search|google|check|take|remind|set)\b)", t, flags=re.I)
    if len(parts) > 1:
        replies = []
        for i, p in enumerate(parts):
            r = skill(p)
            if r is None:
                return None if i == 0 else " ".join(replies) or None
            replies.append(r)
            if i == 0 and re.match(r"open ", p, re.I):
                import time as _t
                _t.sleep(2.5)  # let the app open before the next step
        return " ".join(replies)
    from . import github
    gh = github.skill(t)
    if gh is not None:
        return gh
    for pat, kind in PATTERNS:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        g = next((x for x in m.groups() if x), "") if m.groups() else ""
        try:
            if kind == "help":
                return HELP
            if kind == "remind":
                if re.search(r"\b(focus|study|pomodoro)\b", t, re.I):
                    continue  # the study timer has its own handler
                return remind(t)
            if kind == "list_reminders":
                return list_reminders()
            if kind == "canvas_any":
                if re.match(r"^(open|close|go to|pull up)\b", t, re.I):
                    continue
                from . import canvas
                if re.search(r"\bgrades?\b|\bscores?\b", t, re.I):
                    return canvas.grades_sentence()
                low = t.lower()
                only = "today" if "today" in low or "tonight" in low else "tomorrow" if "tomorrow" in low else ""
                return canvas.due_sentence(7, only)
            if kind == "close":
                if re.search(r"\b(the )?(game|blackjack|timer|session)\b", g, re.I):
                    return None
                return close_thing(g)
            if kind.startswith("music"):
                cmd = {"music_play": "play", "music_pause": "pause", "music_next": "next", "music_prev": "previous",
                       "music_now": "now", "music_query": "play"}[kind]
                return music(cmd, g if kind == "music_query" else "")
            if kind == "claude":
                if re.fullmatch(r"(what )?(should i |i should )?(to )?do next|next|what'?s next", g.strip(), re.I):
                    g = "what should I do next"
                return ask_claude(g)
            if kind == "search":
                return search(m.group(1).lower().replace("google scholar", "scholar"), m.group(2))
            if kind == "google":
                return search("google", g)
            if kind == "open":
                if re.search(r"\b(the )?(door|window|pod bay)\b", g, re.I) or \
                        re.fullmatch(r"(to )?(sleep|bed|the charger|charger|home|your charger)", g.strip(), re.I):
                    return None
                return open_thing(g)
            if kind == "calendar":
                return calendar_sentence(t)
            if kind == "due":
                from . import canvas
                low = t.lower()
                only = "today" if "today" in low or "tonight" in low else "tomorrow" if "tomorrow" in low else ""
                return canvas.due_sentence(7, only)
            if kind == "grades":
                if not re.search(r"\bgrades?\b", t, re.I):
                    continue
                from . import canvas
                return canvas.grades_sentence()
            if kind == "note":
                return add_note(g)
            if kind == "read_note":
                return read_note(g)
        except Exception as e:  # noqa: BLE001
            S.log("voice", f"mac skill {kind} failed: {e}")
            return "That didn't work just now" + _style_sir() + "."
    return None


PLANNING = re.compile(r"\bwhat (should|do) i (do|work on|study) (next|now|tonight|today)\b|\bwhat'?s next\b|\bhelp me (plan|prioriti[sz]e)\b|\bplan my (day|evening|night|week)\b", re.I)


def plan_context(text: str) -> str:
    """For 'what should I do next?': what's due and what's on the calendar, so the answer is real."""
    if not PLANNING.search(text or ""):
        return ""
    from . import canvas, github
    return "\n\n".join(x for x in (canvas.context(), calendar_context(), github.context()) if x)
