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
    if re.match(r"^[\w-]+\.(com|org|net|edu|io|ai|gov)$", n):
        subprocess.Popen(["open", "https://" + n])
        return f"Opening {n}{sir}."
    return f"I don't see an app or site called {name.strip()}{sir}."


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
        ctx = "\n\n".join(x for x in (canvas.context(), calendar_context()) if x)
        if ctx:
            q = f"{q}\n\nHere's what I have going on:\n{ctx}"
    subprocess.Popen(["open", "https://claude.ai/new?q=" + urllib.parse.quote(q)])
    return f"I've put that to Claude{_style_sir()}. It's on your screen."


# ------------------------------------------------------------------ router
PATTERNS = [
    (r"^(?:can you |please )?(?:ask|tell) claude (?:to |about )?(.+)$", "claude"),
    (r"^(?:can you |please )?(?:search|look up) (youtube|google scholar|scholar|pubmed|google) for (.+)$", "search"),
    (r"^(?:can you |please )?google (.+)$", "google"),
    (r"^(?:can you |please )?(?:open|launch|pull up|bring up|start|go to) (.+)$", "open"),
    (r"\b(what'?s|what is|anything) (on|in) my (calendar|schedule)\b|\bcheck my (calendar|schedule)\b|\bmy (calendar|schedule) (today|tomorrow|this week)\b|\bdo i have anything (today|tomorrow|this week)\b", "calendar"),
    (r"\bwhat'?s due\b|\bdue (today|tomorrow|this week|soon)\b|\b(my )?(canvas|homework|assignments)( due)?\b.*\b(today|tomorrow|this week|due|left)\b|\bwhat (homework|assignments) do i have\b", "due"),
    (r"\b(my )?grades?\b.*\b(canvas|classes|now|right now)?\b|\bwhat'?s my grade\b", "grades"),
    (r"^(?:take|make|add|write) (?:a )?note(?: that| saying| to)?[:,]?\s*(.+)$|^note (?:that |to self )?(.+)$|^remember in (?:my )?notes (?:that )?(.+)$", "note"),
    (r"^(?:read|what'?s in|find) (?:me )?(?:my )?(?:latest |last )?note(?:s)?(?: about| on| for| called)?\s*(.*)$", "read_note"),
]


def skill(text: str) -> str | None:
    """Handle a Mac request, or None if this isn't one."""
    t = text.strip().rstrip(".!?")
    for pat, kind in PATTERNS:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        g = next((x for x in m.groups() if x), "") if m.groups() else ""
        try:
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
                days = 1 if "today" in t.lower() else 2 if "tomorrow" in t.lower() else 7
                return canvas.due_sentence(days)
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
    from . import canvas
    return "\n\n".join(x for x in (canvas.context(), calendar_context()) if x)
