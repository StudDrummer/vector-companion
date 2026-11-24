"""GitHub for Jarvis: open repos, recent pushes, notifications, open PRs and issues.

Sign-in, whichever is there first:
  - GITHUB_TOKEN in .env (set on the Vector app's Connections section; a read-only fine-grained token is enough)
  - the GitHub CLI, if you've run `gh auth login`
Without either, "open <repo> on GitHub" still works for repos cloned in ~/GitHub.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from . import settings as S

API = "https://api.github.com"
_cache: dict = {}


def token() -> str:
    t = S.read_env().get("GITHUB_TOKEN", "").strip()
    if t:
        return t
    gh = shutil.which("gh") or next((p for p in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh") if os.path.exists(p)), None)
    if gh:
        try:
            r = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""


def connected() -> bool:
    return bool(token())


def _get(path: str):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token()}",
                                                      "Accept": "application/vnd.github+json",
                                                      "User-Agent": "vector-companion"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = fn()
    _cache[key] = (time.time(), v)
    return v


def login() -> str:
    if connected():
        try:
            return _cached("login", 3600, lambda: _get("/user")["login"])
        except Exception:  # noqa: BLE001
            pass
    return S.read_env().get("GITHUB_USER", "StudDrummer")


def repos() -> list[dict]:
    """[{name, url}] newest first: from GitHub when signed in, plus anything cloned locally."""
    out: dict[str, dict] = {}
    if connected():
        try:
            for r in _cached("repos", 600, lambda: _get("/user/repos?sort=pushed&per_page=50&affiliation=owner,collaborator")):
                out[r["name"].lower()] = {"name": r["name"], "url": r["html_url"]}
        except Exception:  # noqa: BLE001
            pass
    for d in (Path.home() / "GitHub", Path(os.path.expanduser(os.environ.get("PROJECTS_DIR", "") or "~/GitHub"))):
        if d.is_dir():
            for p in d.iterdir():
                if (p / ".git").exists() and p.name.lower() not in out:
                    url = _remote_url(p)
                    if url:
                        out[p.name.lower()] = {"name": p.name, "url": url}
    return list(out.values())


def _remote_url(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=3)
        u = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"github\.com[:/](.+?)(\.git)?$", u)
    return f"https://github.com/{m.group(1)}" if m else ""


def find_repo(name: str) -> dict | None:
    rs = repos()
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    by = {re.sub(r"[^a-z0-9]", "", r["name"].lower()): r for r in rs}
    if key in by:
        return by[key]
    for k, r in by.items():
        if key and (key in k or k in key):
            return r
    m = difflib.get_close_matches(key, list(by), n=1, cutoff=0.6)
    return by[m[0]] if m else None


# ------------------------------------------------------------------ spoken
def _sir() -> str:
    return ", sir" if S.load().get("persona", {}).get("style") == "jarvis" else ""


def _ago(iso: str) -> str:
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = (dt.datetime.now(dt.timezone.utc) - t).total_seconds()
    if s < 3600:
        return f"{max(1, int(s // 60))} minutes ago"
    if s < 86400:
        h = int(s // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = int(s // 86400)
    return "yesterday" if d == 1 else f"{d} days ago"


def open_repo(name: str = "") -> str:
    if not name or re.fullmatch(r"(my )?(github|profile|account)", name.strip(), re.I):
        subprocess.Popen(["open", f"https://github.com/{login()}"])
        return f"Opening your GitHub{_sir()}."
    r = find_repo(name)
    if not r:
        return f"I couldn't find a repository called {name}{_sir()}."
    subprocess.Popen(["open", r["url"]])
    return f"Opening {r['name']} on GitHub{_sir()}."


def activity_sentence() -> str:
    if not connected():
        return _local_activity()
    ev = _cached("events", 300, lambda: _get(f"/users/{login()}/events?per_page=40"))
    pushes: dict[str, dict] = {}
    for e in ev:
        if e.get("type") != "PushEvent":
            continue
        repo = e["repo"]["name"].split("/")[-1]
        p = pushes.setdefault(repo, {"n": 0, "at": e["created_at"], "msg": ""})
        commits = e.get("payload", {}).get("commits") or []
        p["n"] += len(commits) or 1
        if not p["msg"] and commits:
            p["msg"] = commits[-1].get("message", "").splitlines()[0]
    if not pushes:
        return f"No pushes to GitHub recently{_sir()}."
    parts = []
    for repo, p in list(pushes.items())[:3]:
        parts.append(f"{p['n']} commit{'s' if p['n'] != 1 else ''} to {repo}, last {_ago(p['at'])}"
                     + (f": {p['msg'][:70]}" if p["msg"] else ""))
    return "On GitHub: " + "; ".join(parts) + "."


def _local_activity() -> str:
    lines = []
    base = Path.home() / "GitHub"
    for p in sorted((x for x in base.iterdir() if (x / ".git").exists()), key=lambda x: (x / ".git").stat().st_mtime,
                    reverse=True)[:3] if base.is_dir() else []:
        try:
            out = subprocess.run(["git", "-C", str(p), "log", "-1", "--format=%cr: %s"], capture_output=True,
                                 text=True, timeout=3).stdout.strip()
            if out:
                lines.append(f"{p.name}, {out}")
        except (OSError, subprocess.SubprocessError):
            pass
    return ("Latest commits: " + "; ".join(lines) + ".") if lines else "I can't see any repositories yet."


def notifications_sentence() -> str:
    if not connected():
        return "GitHub isn't connected. Add a token on the Connections section of the Brain page, or run gh auth login."
    n = _get("/notifications?per_page=20")
    if not n:
        return f"No GitHub notifications{_sir()}."
    titles = [f"{x['subject']['title'][:60]} in {x['repository']['name']}" for x in n[:3]]
    return f"{len(n)} GitHub notification{'s' if len(n) != 1 else ''}: " + "; ".join(titles) + "."


def prs_sentence(kind: str = "pr") -> str:
    if not connected():
        return "GitHub isn't connected. Add a token on the Connections section of the Brain page, or run gh auth login."
    q = f"involves:{login()} state:open " + ("is:pr" if kind == "pr" else "is:issue")
    res = _get("/search/issues?per_page=10&q=" + urllib.request.quote(q))
    items = res.get("items", [])
    label = "pull requests" if kind == "pr" else "issues"
    if not items:
        return f"No open {label}{_sir()}."
    names = [f"{i['title'][:60]} in {i['repository_url'].split('/')[-1]}" for i in items[:3]]
    n = res.get("total_count", len(items))
    return f"{n} open {label if n != 1 else label[:-1]}: " + "; ".join(names) + "."


def context() -> str:
    """For planning answers and Claude."""
    try:
        return "GitHub: " + activity_sentence()
    except Exception:  # noqa: BLE001
        return ""


PATTERNS = [
    (r"^(?:open|pull up|show me|go to) (?:my )?github$", "open_profile"),
    (r"^(?:open|pull up|show me|go to) (?:the |my )?(.+?) (?:repo|repository)(?: on github)?$", "open_repo"),
    (r"^(?:open|pull up|show me|go to) (?:the |my )?(.+?) on github$", "open_repo"),
    (r"\bgithub notifications?\b|\bcheck (my )?github\b|\banything (new )?on github\b", "notifications"),
    (r"\b(open |my )?(pull requests|prs)\b", "prs"),
    (r"\bmy (open )?(github )?issues\b|\bopen issues\b", "issues"),
    (r"\bwhat did i (push|commit|work on)\b|\bmy (recent|latest|last) (commits?|pushes)\b|\b(recent|latest) github activity\b", "activity"),
]


def skill(text: str) -> str | None:
    t = text.strip().rstrip(".!?")
    for pat, kind in PATTERNS:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        try:
            if kind == "open_profile":
                return open_repo("")
            if kind == "open_repo":
                return open_repo(m.group(1))
            if kind == "notifications":
                return notifications_sentence()
            if kind == "prs":
                return prs_sentence("pr")
            if kind == "issues":
                return prs_sentence("issue")
            if kind == "activity":
                return activity_sentence()
        except Exception as e:  # noqa: BLE001
            S.log("voice", f"github {kind} failed: {e}")
            return f"GitHub didn't answer just now{_sir()}."
    return None
