"""Live answers: hours, prices, scores, news... anything that changes. A real web search first, then the
local model answers only from what the pages say (one or two sentences, the answer first).

Why: asked "YMCA timings tomorrow", the local model alone made up "6 AM to 10 PM". It doesn't know today's
date, holidays, or anything after its training. Here the date (and any holiday) goes into the search and
into the prompt, so "tomorrow" on the day after Thanksgiving finds the holiday hours.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from . import settings as S

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) "
      "Version/17.5 Safari/605.1.15")

LIVE = re.compile(
    r"\b(hours|timings?|time(s)? (does|do|is)|(is|are) .{2,40} open|open(ing)? (hours|time|today|tomorrow|on|until|till)|"
    r"(when|what time) (does|do|is|are) .{2,40} (open|close)|clos(e|es|ing) (time|today|tomorrow|at)|"
    r"price of|how much (is|are|does|do) (a |an |the )?(?!time)|cost of|tickets? (for|to)|showtimes?|"
    r"score|who won|did .{2,30} win|standings|news|headlines?|stock price|release date|come out|"
    r"latest|currently|right now|who is the (current )?(ceo|president|governor|mayor|coach|prime minister)|"
    r"traffic|events? (this|tonight|tomorrow|today)|happening (this|tonight|today))\b", re.I)
NOT_LIVE = re.compile(r"\b(my (calendar|schedule|grades?|canvas|assignments?|homework)|timer|remind|what time is it)\b", re.I)

POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="web")


def wants(text: str) -> bool:
    return bool(LIVE.search(text or "")) and not NOT_LIVE.search(text or "")


def log(msg: str):
    S.log("voice", msg)


# ---------------------------------------------------------------- dates
def _nth_weekday(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y, m, wd):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def holiday(d: date) -> str | None:
    y = d.year
    thanks = _nth_weekday(y, 11, 3, 4)
    days = {date(y, 1, 1): "New Year's Day", _nth_weekday(y, 1, 0, 3): "Martin Luther King Jr. Day",
            _nth_weekday(y, 2, 0, 3): "Presidents' Day", _last_weekday(y, 5, 0): "Memorial Day",
            date(y, 6, 19): "Juneteenth", date(y, 7, 4): "Independence Day", _nth_weekday(y, 9, 0, 1): "Labor Day",
            date(y, 10, 31): "Halloween", date(y, 11, 11): "Veterans Day", thanks: "Thanksgiving",
            thanks + timedelta(days=1): "the day after Thanksgiving (Black Friday)", date(y, 12, 24): "Christmas Eve",
            date(y, 12, 25): "Christmas Day", date(y, 12, 31): "New Year's Eve"}
    return days.get(d)


def which_day(text: str) -> date:
    t = text.lower()
    today = date.today()
    if "tomorrow" in t:
        return today + timedelta(days=1)
    for i, name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
        if re.search(rf"\b{name}\b", t):
            return today + timedelta(days=(i - today.weekday()) % 7 or (7 if "next" in t else 0))
    return today


def _query(text: str) -> tuple[str, date, str | None]:
    q = re.sub(r"^(hey |ok |okay )?(jarvis|vector)[, ]*", "", text.strip(), flags=re.I)
    q = re.sub(r"[?.!]+$", "", q)
    day = which_day(q)
    hol = holiday(day)
    if re.search(r"\b(hours|timings?|open|close|closing)\b", q, re.I):
        q = re.sub(r"\btimings?\b", "hours", q, flags=re.I)
        city = (S.load().get("weather") or {}).get("city") or "Bellevue WA"
        if not re.search(r"\b(in|near|at)\s+[A-Z]", q) and city.split()[0].lower() not in q.lower():
            q += f" {city}"
        if hol:
            q += " holiday hours " + re.sub(r" \(.*\)", "", hol)
    q = re.sub(r"\b(tomorrow|today|tonight)\b", lambda m: day.strftime("%B %-d %Y") if m.group(1) != "tonight" else "tonight", q,
               flags=re.I)
    return q, day, hol


# ---------------------------------------------------------------- search
def _get(url: str, data: bytes | None = None, timeout: float = 4.0) -> str:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                                          "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1_500_000)
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, "replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _ddg(q: str) -> list[dict]:
    page = _get("https://html.duckduckgo.com/html/", urllib.parse.urlencode({"q": q, "kl": "us-en"}).encode())
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                         page, re.S):
        href, title, rest = m.groups()
        u = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query).get("uddg", [html.unescape(href)])[0]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        if "duckduckgo.com/y.js" in u:  # ads
            continue
        out.append({"url": u, "title": _clean(title), "snippet": _clean(sn.group(1)) if sn else ""})
    return out


def _bing(q: str) -> list[dict]:
    page = _get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": q, "setlang": "en-US", "cc": "US"}))
    out = []
    for block in re.findall(r'<li class="b_algo"(.*?)</li>', page, re.S):
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a:
            continue
        p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S) or re.search(r'class="b_caption"[^>]*>(.*?)</div>', block, re.S)
        out.append({"url": html.unescape(a.group(1)), "title": _clean(a.group(2)), "snippet": _clean(p.group(1)) if p else ""})
    return out


def search(q: str, n: int = 6) -> list[dict]:
    for fn in (_ddg, _bing):
        try:
            res = [r for r in fn(q) if r["url"].startswith("http")]
            if res:
                return res[:n]
        except Exception as e:  # noqa: BLE001
            log(f"web: {fn.__name__} failed: {e.__class__.__name__}")
    return []


TIMEISH = re.compile(r"\b(\d{1,2}(:\d{2})?\s?(am|pm|a\.m\.|p\.m\.)|noon|midnight|closed|open|hours|holiday|"
                     r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun|"
                     r"thanksgiving|christmas|\$\d|price|score)\b", re.I)


def _page_text(url: str, words: list[str], limit: int = 1600) -> str:
    try:
        raw = _get(url, timeout=3.0)
    except Exception:  # noqa: BLE001
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer)[^>]*>.*?</\1>", " ", raw)
    text = _clean(raw)
    # keep the parts that look like the answer: sentences with the question's words, times, days, prices
    bits = re.split(r"(?<=[.!?])\s+|\s{2,}|\s\|\s", text)
    scored = []
    for i, b in enumerate(bits):
        if len(b) < 6:
            continue
        s = len(TIMEISH.findall(b)) * 2 + sum(w in b.lower() for w in words)
        if s >= 2:
            scored.append((s, i, b[:300]))
    keep = sorted(sorted(scored, reverse=True)[:14], key=lambda t: t[1])
    out = " / ".join(b for _, _, b in keep)
    return out[:limit]


def gather(text: str) -> tuple[str, list[dict], date, str | None]:
    q, day, hol = _query(text)
    t0 = time.time()
    res = search(q)
    words = [w for w in re.findall(r"[a-z]{4,}", q.lower()) if w not in ("hours", "what", "when", "does", "open")]
    pages = list(POOL.map(lambda r: _page_text(r["url"], words), res[:3]))
    for r, p in zip(res, pages + [""] * len(res)):
        r["page"] = p
    log(f"web: '{q}' -> {len(res)} results in {time.time() - t0:.1f}s")
    return q, res, day, hol


def answer(text: str, history=None):
    """Yield the spoken answer (one or two sentences)."""
    from . import brain
    jarvis = brain._style() == "jarvis"
    q, res, day, hol = gather(text)
    if not res:
        yield ("I couldn't reach the web just now, sir." if jarvis else "I couldn't reach the web just now.")
        return
    today = date.today()
    when = day.strftime("%A, %B %-d, %Y") + (f" ({hol})" if hol else "")
    src = "\n\n".join(f"[{i + 1}] {r['title']} ({urllib.parse.urlparse(r['url']).netloc})\n{r['snippet']}\n{r.get('page', '')}"
                      for i, r in enumerate(res[:5]))
    sys_prompt = (
        f"Today is {today:%A, %B %-d, %Y} ({datetime.now():%-I:%M %p}). The question is about {when}.\n"
        "Answer ONLY from the search results below. Rules: one or two short spoken sentences; the answer first; "
        "no greeting, no filler, no offers to do anything else, no restating the question. "
        "If the day is a holiday and the results only show regular hours, say the regular hours and that holiday hours "
        "may differ. If the results don't contain the answer, say you couldn't confirm it and name the website to check. "
        "Name the source site briefly (e.g. 'per the Y's website'). "
        + ("Address him as sir at most once." if jarvis else "") + "\n\nSEARCH RESULTS:\n" + src)
    msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}]
    buf, said = "", 0
    for chunk in brain.stream_llm(msgs):
        buf += chunk
        m = re.search(r"^(.{12,}?[.!?])(\s+)", buf, re.S)
        if m:
            yield brain.speakable(m.group(1).strip())
            said += 1
            buf = buf[m.end():]
            if said >= 2:
                break
    if said < 2 and buf.strip():
        yield brain.speakable(buf.strip()[:240])
    try:
        (S.DATA_DIR / "last_web.json").write_text(json.dumps({"q": q, "results": res[:5], "at": time.time()}))
    except Exception:  # noqa: BLE001
        pass
