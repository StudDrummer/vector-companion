"""Tiny client for the companion's local API (safe to import anywhere)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PORT = int(os.environ.get("COMPANION_PORT", "47801"))


def call(path: str, body: dict | None = None, timeout: float = 5):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", str(e))
        except Exception:  # noqa: BLE001
            msg = str(e)
        raise RuntimeError(msg) from None
    return json.loads(raw) if ctype.startswith("application/json") else raw


def available() -> bool:
    try:
        return bool(call("/health", timeout=1.5).get("connected"))
    except Exception:  # noqa: BLE001
        return False
