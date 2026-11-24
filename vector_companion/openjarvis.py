"""Bridge to OpenJarvis (Stanford, Apache-2.0): the 'deep brain' for requests that need tools,
research, memory or several steps. The fast path (name detection -> local skills -> gemma3) stays
for everyday questions; anything that needs real work goes to the OpenJarvis agent server.

  OpenJarvis:  https://github.com/open-jarvis/OpenJarvis   (jarvis serve -> OpenAI-compatible API)
  Vector is registered with it as an MCP server, so its agents can speak, show things on his face,
  look through his camera and start timers.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

from . import settings as S

DEEP = re.compile(
    r"\b(research|look (it |this |that )?up|search (the web|online|for)|find (me )?(papers?|articles?|sources?|studies)"
    r"|deep dive|dig into|compare\b|summari[sz]e (my |the )?(emails?|inbox|calendar|news|paper|article)"
    r"|(my|the) (inbox|emails?|calendar|schedule)\b|what'?s on my calendar|plan (my|out|a)\b"
    r"|draft (an?|the) (email|message)|write (me )?(a |an )?(plan|outline|summary)"
    r"|latest (news|research|papers?)|step by step|in depth)", re.I)


def prefs() -> dict:
    return S.load().get("openjarvis", {})


def url() -> str:
    return str(prefs().get("url") or "http://127.0.0.1:8000").rstrip("/")


_up = (0.0, False)


def available() -> bool:
    """Is `jarvis serve` running? (cached for 20 s)"""
    global _up
    if not prefs().get("enabled", True):
        return False
    if time.time() - _up[0] < 20:
        return _up[1]
    ok = False
    try:
        with urllib.request.urlopen(url() + "/health", timeout=1.5) as r:
            ok = r.status == 200
    except Exception:  # noqa: BLE001
        ok = False
    _up = (time.time(), ok)
    return ok


def wants_deep(text: str) -> bool:
    return bool(DEEP.search(text or "")) and available()


def stream(messages: list[dict], timeout: float = 180):
    """Yield text as the OpenJarvis agent writes it."""
    body = {"model": prefs().get("model") or "default", "messages": messages, "stream": True}
    req = urllib.request.Request(url() + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                delta = json.loads(data)["choices"][0].get("delta", {})
            except Exception:  # noqa: BLE001
                continue
            if delta.get("content"):
                yield delta["content"]


def save_report(question: str, text: str):
    """The spoken answer is short; the full one is kept for the app (Brain page) and Claude."""
    try:
        d = S.DATA_DIR / "reports"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H.%M")
        (d / f"{stamp}.md").write_text(f"# {question}\n\n{text}\n")
    except OSError:
        pass
