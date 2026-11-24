"""Canvas (Overlake: overlake.instructure.com): what's due, grades, upcoming events.

Two ways to connect, both set on the Vector app's Connections page (stored in .env, never in git):
  - Canvas access token (Account > Settings > + New Access Token): assignments, to-dos and grades.
  - Calendar feed link (Calendar > Calendar Feed): due dates only, works even if tokens are turned off.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request

from . import settings as S

DEFAULT_BASE = "https://overlake.instructure.com"


def _local_tz():
    """The Mac's own time zone (background services can start without TZ set and fall back to UTC,
    which made 'tomorrow' come out as 'Tuesday')."""
    import os
    from zoneinfo import ZoneInfo
    try:
        link = os.readlink("/etc/localtime")
        return ZoneInfo(link.split("zoneinfo/")[-1])
    except Exception:  # noqa: BLE001
        try:
            tzname = (S.load().get("robot") or {}).get("timezone") or "America/Los_Angeles"
            return ZoneInfo(tzname)
        except Exception:  # noqa: BLE001
            return None


LOCAL = _local_tz()


def now() -> dt.datetime:
    return dt.datetime.now(LOCAL) if LOCAL else dt.datetime.now().astimezone()
_cache: dict = {}


def base() -> str:
    return (S.read_env().get("CANVAS_URL") or DEFAULT_BASE).rstrip("/")


def token() -> str:
    return S.read_env().get("CANVAS_TOKEN", "").strip()


def feed() -> str:
    return S.read_env().get("CANVAS_ICS", "").strip()


def connected() -> bool:
    return bool(token() or feed())


def _get(path: str, params: dict | None = None):
    url = base() + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token()}"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _when(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(LOCAL)
    except ValueError:
        return None


# ------------------------------------------------------------------ assignments
def upcoming(days: int = 7) -> list[dict]:
    """[{title, course, due (datetime), url, done}] soonest first."""
    return _cached(f"up{days}", 300, lambda: _upcoming(days))


def _upcoming(days: int) -> list[dict]:
    now_ = now()
    end = now_ + dt.timedelta(days=days)
    items: list[dict] = []
    if token():
        courses = {c["id"]: c.get("name", "") for c in _get("/api/v1/courses", {"enrollment_state": "active", "per_page": 50})}
        for a in _get("/api/v1/users/self/upcoming_events", {"per_page": 50}):
            asg = a.get("assignment") or {}
            due = _when(asg.get("due_at") or a.get("start_at"))
            if due and now_ - dt.timedelta(hours=2) <= due <= end:
                items.append({"title": asg.get("name") or a.get("title", ""), "due": due,
                              "course": courses.get(asg.get("course_id"), a.get("context_name", "")),
                              "url": asg.get("html_url") or a.get("html_url", ""),
                              "done": bool(asg.get("has_submitted_submissions"))})
        try:
            for t in _get("/api/v1/users/self/todo", {"per_page": 50}):
                asg = t.get("assignment") or {}
                due = _when(asg.get("due_at"))
                if asg and due and due <= end and not any(i["title"] == asg.get("name") for i in items):
                    items.append({"title": asg.get("name", ""), "due": due, "course": t.get("context_name", ""),
                                  "url": asg.get("html_url", ""), "done": False})
        except Exception:  # noqa: BLE001
            pass
    elif feed():
        items = [i for i in _ics(feed()) if now_ - dt.timedelta(hours=2) <= i["due"] <= end]
    return sorted(items, key=lambda i: i["due"])


def _ics(url: str) -> list[dict]:
    with urllib.request.urlopen(url.replace("webcal://", "https://"), timeout=12) as r:
        text = r.read().decode("utf-8", "ignore")
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold lines
    out = []
    for ev in text.split("BEGIN:VEVENT")[1:]:
        f = dict(re.findall(r"^([A-Z-]+)(?:;[^:\n]*)?:(.*)$", ev, re.M))
        raw = f.get("DTSTART", "")
        try:
            if len(raw) == 8:
                due = dt.datetime.strptime(raw, "%Y%m%d").replace(hour=23, minute=59, tzinfo=LOCAL)
            else:
                due = dt.datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S")
                due = due.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL) if raw.endswith("Z") else due.replace(tzinfo=LOCAL)
        except ValueError:
            continue
        summary = f.get("SUMMARY", "").replace("\\,", ",").replace("\\;", ";")
        m = re.match(r"(.*)\s\[(.*)\]$", summary)
        out.append({"title": m.group(1) if m else summary, "course": m.group(2) if m else "",
                    "due": due, "url": f.get("URL", ""), "done": False})
    return out


def grades() -> list[dict]:
    """[{course, score}] for active courses (needs a token)."""
    if not token():
        return []

    def fetch():
        out = []
        for c in _get("/api/v1/courses", {"enrollment_state": "active", "include[]": ["total_scores"], "per_page": 50}):
            for e in c.get("enrollments") or []:
                score = e.get("computed_current_score")
                if score is not None:
                    out.append({"course": c.get("name", ""), "score": score, "grade": e.get("computed_current_grade")})
        return out
    return _cached("grades", 600, fetch)


# ------------------------------------------------------------------ spoken
def _short_course(name: str) -> str:
    name = re.sub(r"\s*[\(\[].*?[\)\]]", "", name or "")
    name = re.sub(r"\s+\d{2}-\d{2}$", "", name)  # school year suffix "26-27"
    name = re.sub(r"\s+[A-Z][a-z]+'s Class$", "", name)  # "Brian's Class"
    name = re.sub(r"^Honors (Physics) of Our Universe", r"Honors \1", name)
    name = re.sub(r"\bLang\.?(?=\s|$)", "Language", name)
    return re.sub(r"\b(Section|Sec|Period)\s*\w+\b|\bP\d+\b", "", name).strip(" -:.")


def _day(d: dt.datetime) -> str:
    today = now().date()
    d = d.astimezone(LOCAL) if LOCAL else d
    if d.date() == today:
        return "today" + (f" at {d.strftime('%-I:%M %p')}" if d.hour < 23 else "")
    if d.date() == today + dt.timedelta(days=1):
        return "tomorrow"
    if d.date() < today + dt.timedelta(days=7):
        return d.strftime("%A")
    return d.strftime("%A %B %-d")


def due_sentence(days: int = 7, only: str = "") -> str:
    """only='today' / 'tomorrow' keeps just that day; otherwise the next `days` days."""
    if not connected():
        return "Canvas isn't connected yet. Add your Canvas token or calendar feed on the Connections page of the Vector app."
    items = [i for i in upcoming(max(days, 2)) if not i["done"]]
    today = now().date()
    if only == "today":
        items = [i for i in items if i["due"].date() == today]
    elif only == "tomorrow":
        items = [i for i in items if i["due"].date() == today + dt.timedelta(days=1)]
    items = [i for i in items if not re.search(r"\b(thanksgiving|break|no school|holiday)\b", i["title"], re.I)
             or i.get("url", "").find("assignments") >= 0]
    if not items:
        return f"Nothing due on Canvas {only}." if only else f"Nothing due on Canvas in the next {days} days."
    when = (lambda i: "") if only else (lambda i: f", due {_day(i['due'])}")
    parts = [f"{_clean_title(i['title'])} for {_short_course(i['course'])}{when(i)}" if i["course"]
             else f"{_clean_title(i['title'])}{when(i)}" for i in items[:4]]
    more = f" Plus {len(items) - 4} more." if len(items) > 4 else ""
    head = f"Due {only}: " if only else f"{len(items)} thing{'s' if len(items) != 1 else ''} due: "
    return head + "; ".join(parts) + "." + more


def _clean_title(t: str) -> str:
    """'Unit 2: Summative Assessment--NoodleTool Source Checkpoint' -> 'NoodleTool Source Checkpoint'."""
    t = re.sub(r"\s*\[[A-Z]{1,4}\]\s*", " ", t)
    t = re.sub(r"^\((minor|major)\)\s*", "", t, flags=re.I)
    if re.search(r"\s*(--|—|–| - )\s*", t):
        tail = re.split(r"\s*(?:--|—|–| - )\s*", t)[-1]
        if len(tail) > 6:
            t = tail
    return t.strip()


def grades_sentence() -> str:
    g = grades()
    if not g:
        return ("Grades need a Canvas access token. Add one on the Connections page." if not token()
                else "Canvas didn't return any grades.")
    g = [x for x in g if not re.search(r"\b(\d{2})-\d{2}\b", x["course"]) or _current_year(x["course"])]
    return "; ".join(f"{_short_course(x['course'])} {round(x['score'])} percent" for x in g[:7]) + "."


def _current_year(course: str) -> bool:
    """Skip old courses ('Computer Science Foundations 23-24')."""
    m = re.search(r"\b(\d{2})-(\d{2})\b", course)
    if not m:
        return True
    d = now()
    start = d.year % 100 if d.month >= 7 else (d.year - 1) % 100
    return int(m.group(1)) == start


def context(days: int = 5) -> str:
    """Plain text for the brain / Claude: what's due."""
    if not connected():
        return ""
    try:
        items = [i for i in upcoming(days) if not i["done"]]
    except Exception:  # noqa: BLE001
        return ""
    if not items:
        return "Canvas: nothing due in the next few days."
    return "Canvas, due soon:\n" + "\n".join(
        f"- {i['title']} ({_short_course(i['course'])}) due {i['due'].strftime('%a %b %-d %-I:%M %p')}" for i in items[:10])
