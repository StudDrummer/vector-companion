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
    r"|deep dive|dig into|compare\b|summari[sz]e (the )?(news|paper|article)"
    r"|plan (out|a)\b|write (me )?(a |an )?(plan|outline|summary)"
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
    body = {"model": prefs().get("model") or "qwen3.5:4b", "messages": messages, "stream": True}
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


# ------------------------------------------------------------------ setup
SAFE_TOOLS = ["web_search", "http_request", "think", "calculator", "get_weather",
              "vector_say", "vector_show_on_face", "vector_look", "vector_focus_timer", "vector_weather",
              "vector_status", "vector_action", "vector_desk_guard", "vector_head_angle"]


def configure() -> str:
    """Point OpenJarvis at safe tools only (web + Vector; no shell or code execution from a voice
    request) and at the tool-calling model, then restart it."""
    import os
    import subprocess
    cfg = os.path.expanduser(os.environ.get("OPENJARVIS_CONFIG", "~/.openjarvis/config.toml"))
    text = open(cfg).read() if os.path.exists(cfg) else ""
    model = prefs().get("model") or "qwen3.5:4b"
    tools_line = "enabled = [" + ", ".join(f'"{t}"' for t in SAFE_TOOLS) + "]"
    lines, section, done_tools, done_model = text.splitlines(), "", False, False
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            if section == "tools" and not done_tools:
                out.append(tools_line)
                done_tools = True
            if section == "intelligence" and not done_model:
                out.append(f'default_model = "{model}"')
                done_model = True
            section = s.strip("[]")
        elif section == "tools" and s.startswith("enabled"):
            ln, done_tools = tools_line, True
        elif section == "intelligence" and s.startswith("default_model"):
            ln, done_model = f'default_model = "{model}"', True
        out.append(ln)
    if section == "tools" and not done_tools:
        out.append(tools_line)
        done_tools = True
    if not done_tools:
        out += ["", "[tools]", tools_line]
    if not done_model:
        out += ["", "[intelligence]", f'default_model = "{model}"']
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    open(cfg, "w").write("\n".join(out) + "\n")
    try:
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.rushil.openjarvis"],
                       capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass
    global _up
    _up = (0.0, False)
    return cfg


if __name__ == "__main__":
    import sys
    if "--configure" in sys.argv:
        print("   configured", configure())
