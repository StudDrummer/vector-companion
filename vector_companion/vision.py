"""Send a picture from Vector's camera to a vision-capable AI (Claude, ChatGPT, Gemini or local)."""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config, settings as S

config.load_env()

SCANS = S.DATA_DIR / "scans"

MODES = {
    "explain": ("Explain & check",
                "This is a photo of the student's homework or notes, taken by a small desk robot. "
                "1) Transcribe each problem exactly (use LaTeX between $ $ for math). "
                "2) For each problem, name the concept, explain the idea clearly with an intuitive picture or analogy, "
                "and give the first step of the approach. "
                "3) If a handwritten answer is visible, check it carefully and point out exactly where any mistake is. "
                "Don't hand over every final answer unless the work is already done and you're checking it."),
    "solve": ("Full solution",
              "This is a photo of homework taken by a small desk robot. Transcribe each problem exactly "
              "(LaTeX between $ $ for math), then give a clear, numbered, step-by-step worked solution, "
              "explaining why each step is done, and box the final answer."),
    "read": ("Read text",
             "Transcribe all text in this photo exactly, keeping structure (headings, lists, tables as Markdown, "
             "math as LaTeX between $ $). Mark anything unreadable as [unclear]."),
    "describe": ("What do you see",
                 "Describe what is in this photo from a small desk robot's camera: the main objects, any text, "
                 "and anything notable. Be concrete and brief."),
}

FORMAT = ("\n\nStart your reply with one line beginning 'SAY:' holding one or two short, friendly spoken sentences "
          "summarizing the result (no markdown, no symbols, under 35 words). Then a blank line, then the full answer in Markdown. "
          "If the image is blurry, too dark or the page is cut off, say so in the SAY line and suggest how to hold it.")


def about_me() -> str:
    p = S.DATA_DIR / "about_me.txt"
    return p.read_text().strip() if p.exists() else ""


def _vision_ollama_model() -> str | None:
    base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    base = base[:-3] if base.endswith("/v1") else base
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return None
    for n in names:
        if re.search(r"vl|vision|llava|gemma3|minicpm-v|moondream|granite3\.2-vision", n, re.I):
            return n
    return None


def _first_model(url: str, key: str, want: str) -> str | None:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            ids = sorted((m.get("id", "").replace("models/", "") for m in json.loads(r.read()).get("data", [])), reverse=True)
        for i in ids:
            if want in i and not any(x in i for x in ("lite", "tts", "image", "audio", "live", "embedding", "realtime")):
                return i
    except Exception:  # noqa: BLE001
        pass
    return None


def pick_backend() -> tuple[str, str, str, str]:
    """(backend, model, url, key). Uses whichever AI keys you've saved, then any local vision model."""
    env = S.read_env()
    brain_model = env.get("BRAIN_MODEL", "")
    url_now = env.get("OPENAI_COMPAT_URL", "")
    if env.get("ANTHROPIC_API_KEY"):
        m = env.get("VISION_MODEL") or "claude-sonnet-5-5"
        return "anthropic", m, "https://api.anthropic.com/v1", env["ANTHROPIC_API_KEY"]
    for prov, url, keyname, want, fallback in (
            ("chatgpt", "https://api.openai.com/v1", "OPENAI_API_KEY_SAVED", "gpt-5", "gpt-5.5"),
            ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY_SAVED", "flash", None)):
        key = env.get(keyname)
        if key:
            model = env.get("VISION_MODEL") or (brain_model if url_now.startswith(url) and brain_model else None) \
                or _first_model(url, key, want) or fallback
            if model:
                return "openai", model, url, key
    m = _vision_ollama_model()
    if m:
        return "ollama", m, "", ""
    raise RuntimeError("No vision AI available. Add a Claude, ChatGPT or Gemini key in the Vector app (Brain), "
                       "or run: ollama pull qwen2.5vl:7b")


def _post(url: str, body: dict, headers: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask(jpeg: bytes, mode: str = "explain", question: str = "") -> dict:
    title, prompt = MODES.get(mode, MODES["describe"])
    me = about_me()
    if me:
        prompt = f"About the person: {me}\n\n{prompt}"
    if question:
        prompt += f"\n\nTheir question: {question}"
    prompt += FORMAT
    b64 = base64.b64encode(jpeg).decode()
    backend, model, url, key = pick_backend()
    t0 = time.time()
    if backend == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages", {
            "model": model, "max_tokens": 2500,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": prompt}]}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"})
        out = "".join(c.get("text", "") for c in r.get("content", []))
    elif backend == "openai":
        tok = "max_completion_tokens" if "openai.com" in url else "max_tokens"
        r = _post(url.rstrip("/") + "/chat/completions", {
            "model": model, tok: 2500,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]},
            {"Authorization": f"Bearer {key}"})
        out = r["choices"][0]["message"]["content"]
    else:
        base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base
        body = {"model": model, "stream": False, "keep_alive": "2h", "think": mode == "solve",
                "options": {"num_predict": 3000 if mode == "solve" else 1500},
                "messages": [{"role": "user", "content": prompt, "images": [b64]}]}
        try:
            r = _post(base + "/api/chat", body, {}, 300)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            body.pop("think")  # model without a thinking switch
            r = _post(base + "/api/chat", body, {}, 300)
        out = re.sub(r"<think>.*?</think>", "", r["message"]["content"], flags=re.S).strip()
        if not out and r.get("done_reason") == "length":  # it thought the whole time: give it room to answer
            body["options"]["num_predict"] = 6000
            r = _post(base + "/api/chat", body, {}, 420)
            out = re.sub(r"<think>.*?</think>", "", r["message"]["content"], flags=re.S).strip()
        if not out:
            out = "SAY: I looked, but my vision model didn't give me an answer. Try again, or add a ChatGPT or Gemini key.\n\nNo answer came back."
    say, body = split_say(out)
    return {"mode": mode, "title": title, "say": say, "text": body, "backend": backend, "model": model,
            "seconds": round(time.time() - t0, 1)}


def split_say(out: str) -> tuple[str, str]:
    m = re.match(r"\s*SAY:\s*(.+?)(?:\n\s*\n|\n|$)(.*)", out, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    first = re.split(r"(?<=[.!?])\s", out.strip(), maxsplit=1)[0]
    return first[:200], out.strip()


def save(jpeg: bytes, result: dict) -> dict:
    SCANS.mkdir(parents=True, exist_ok=True)
    sid = datetime.now().strftime("%Y%m%d-%H%M%S")
    (SCANS / f"{sid}.jpg").write_bytes(jpeg)
    result = {**result, "id": sid, "at": datetime.now().isoformat(timespec="seconds")}
    (SCANS / f"{sid}.json").write_text(json.dumps(result, indent=2))
    return result


def history(n: int = 30) -> list[dict]:
    if not SCANS.exists():
        return []
    items = []
    for p in sorted(SCANS.glob("*.json"), reverse=True)[:n]:
        try:
            items.append(json.loads(p.read_text()))
        except ValueError:
            pass
    return items
