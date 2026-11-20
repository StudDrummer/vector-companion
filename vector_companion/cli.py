"""Command line for Vector, handy for hooking him into any project.

  vector say "Training finished. Validation AUC 0.91"
  vector run -- python train.py          # Vector announces when a command finishes or fails
  vector eyes purple
  vector do dance
  vector look photo.jpg
  vector status
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import os
import time
from pathlib import Path

from . import config
from .wirepod import Vector


def _announce(v: Vector, text: str, color: str, flash: bool) -> None:
    if flash:
        with v.flash_eyes(color):
            v.say(text)
    else:
        v.say(text)


def hook(event: str, rc: int = 0, seconds: float = 0, cmd: str = "", cwd: str = "", detach: bool = False) -> None:
    """Called by Claude Code hooks and the zsh hook. Never raises; logs to logs/hook.log."""
    from . import notify, settings as S
    payload = notify.read_stdin_json() if event.startswith("claude") else {}
    if detach and event != "claude-start" and notify.detach():
        return  # parent: return immediately so Claude Code / the shell never waits
    try:
        notify.handle(event, rc, seconds, cmd, cwd, payload)
    except Exception as e:  # noqa: BLE001
        S.log("hook", f"{event}: ERROR {e!r}")


def main(argv=None):
    config.load_env()
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "voice":  # called by wire-pod custom intents
        from .voice import main as voice_main
        return voice_main(argv[1:])
    p = argparse.ArgumentParser(prog="vector")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("say"); s.add_argument("text", nargs="+")
    e = sub.add_parser("eyes"); e.add_argument("color")
    d = sub.add_parser("do"); d.add_argument("action")
    lk = sub.add_parser("look"); lk.add_argument("out", nargs="?", default="vector.jpg")
    sub.add_parser("status")
    sub.add_parser("listen")
    r = sub.add_parser("run", help="run a command and have Vector report the result")
    r.add_argument("command", nargs=argparse.REMAINDER)
    h = sub.add_parser("hook", help="notification hook (used by Claude Code / zsh)")
    h.add_argument("event", choices=["claude-start", "claude-stop", "claude-input", "terminal", "test"])
    h.add_argument("--rc", type=int, default=0)
    h.add_argument("--seconds", type=float, default=0)
    h.add_argument("--cmd", dest="cmdline", default="")
    h.add_argument("--cwd", default="")
    h.add_argument("--detach", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "hook":
        return hook(a.event, a.rc, a.seconds, a.cmdline, a.cwd, a.detach)

    v = Vector()
    if not v.serial:
        sys.exit("wire-pod not reachable or no robot authenticated (is WirePod running?)")

    if a.cmd == "say":
        v.say(" ".join(a.text))
    elif a.cmd == "eyes":
        v.eye_color(a.color)
    elif a.cmd == "do":
        v.intent(a.action)
    elif a.cmd == "look":
        open(a.out, "wb").write(v.snapshot())
        print(f"saved {a.out}")
    elif a.cmd == "status":
        print(json.dumps({"serial": v.serial, "battery": v.battery()}, indent=2))
    elif a.cmd == "listen":
        v.wake_word()
    elif a.cmd == "run":
        cmd = [c for c in a.command if c != "--"]
        if not cmd:
            sys.exit("usage: vector run -- <command>")
        name = shlex.join(cmd)[:60]
        t0 = time.time()
        rc = subprocess.call(cmd)
        mins = (time.time() - t0) / 60
        took = f"{mins:.0f} minutes" if mins >= 1 else "under a minute"
        if rc == 0:
            _announce(v, f"Your job finished successfully. It took {took}.", "lime", True)
            if mins > 10:  # long jobs earn a victory dance
                v.intent("dance")
        else:
            _announce(v, f"Uh oh. Your job failed with exit code {rc} after {took}.", "orange", True)
        print(f"[vector] {name} -> exit {rc}")
        sys.exit(rc)


if __name__ == "__main__":
    main()
