"""MCP server that lets Claude (Desktop or Code) drive Vector.

Add to Claude's MCP config (see README):
  command: <project>/.venv/bin/python
  args:    ["-m", "vector_companion.mcp_server"]

Then you can say things like "have Vector announce that my tests passed",
"look through Vector's camera and tell me what's on my desk", or
"make Vector dance when the build finishes".
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from . import config
from .wirepod import EYE_COLORS, INTENTS, Vector

config.load_env()
mcp = FastMCP("vector")
_bot: Vector | None = None


def bot() -> Vector:
    global _bot
    if _bot is None or not _bot.serial:
        _bot = Vector()
        if not _bot.serial:
            raise RuntimeError("wire-pod has no authenticated robot yet (is WirePod running?)")
    return _bot


@mcp.tool()
def vector_say(text: str) -> str:
    """Make Vector speak the text out loud (keep it short and plain; no markdown)."""
    bot().say(text)
    return "spoken"


@mcp.tool()
def vector_look() -> Image:
    """Take a photo with Vector's camera and return it so you can see what he sees.
    Uses the high-resolution camera mode when the companion service is running (good for reading
    homework, notes or labels held about 20-30 cm in front of his face)."""
    try:
        from .companion_client import call
        data = call("/capture", timeout=15)
        if isinstance(data, (bytes, bytearray)) and data[:2] == b"\xff\xd8":
            return Image(data=bytes(data), format="jpeg")
    except Exception:  # noqa: BLE001
        pass
    return Image(data=bot().snapshot(), format="jpeg")


def _c(path, body, timeout=20):
    from .companion_client import call
    r = call(path, body, timeout=timeout)
    if isinstance(r, dict) and r.get("ok") is False:
        raise RuntimeError(r.get("error"))
    return r


@mcp.tool()
def vector_show_on_face(text: str = "", icon: str = "", seconds: float = 4) -> str:
    """Show something on Vector's face screen for a few seconds: short text (a few words)
    or an icon: heart, check, x, question, camera, thinking."""
    _c("/face", {"text": text, "icon": icon, "seconds": seconds})
    return "shown"


@mcp.tool()
def vector_head_angle(degrees: float) -> str:
    """Point Vector's head: -22 (looking down at the desk) to 45 (looking up at a person)."""
    _c("/head", {"deg": degrees})
    return "done"


@mcp.tool()
def vector_lift_height(height: float) -> str:
    """Move Vector's forklift arms: 0 = down, 1 = fully up."""
    _c("/lift", {"height": height})
    return "done"


@mcp.tool()
def vector_animation(name: str) -> str:
    """Play one of Vector's built-in animations by (partial) trigger name, e.g. 'Celebrat', 'Happy',
    'Sad', 'Surprise', 'Greet', 'FistBump', 'Dance'. Use vector_animation_list to see all names."""
    return _c("/anim", {"name": name}).get("played", "played")


@mcp.tool()
def vector_animation_list() -> list:
    """List Vector's built-in animation trigger names."""
    from .companion_client import call
    return call("/anims")


@mcp.tool()
def vector_focus_timer(minutes: int = 25, stop: bool = False) -> str:
    """Start (or stop) a focus timer that Vector shows on his face and announces when done."""
    _c("/focus", {"stop": True} if stop else {"minutes": minutes})
    return "stopped" if stop else f"{minutes} minute timer started"


@mcp.tool()
def vector_desk_guard(on: bool = True) -> str:
    """Turn desk guard on or off. While on, Vector watches the desk from his charger, saves a photo and
    notifies the Mac when something moves, and turns it off himself when he recognizes his owner."""
    r = _c("/guard", {"on": on, "report": False})
    n = len((r or {}).get("events") or [])
    return "guard on" if on else f"guard off ({n} movement events)"


@mcp.tool()
def vector_weather(day: str = "today") -> str:
    """Today's or tomorrow's weather where the user lives (day: today or tomorrow), as one spoken sentence."""
    from . import weather
    return weather.sentence("tomorrow" if day.lower().startswith("tom") else "today")


@mcp.tool()
def vector_drive(left_mm_s: float, right_mm_s: float, seconds: float) -> str:
    """Drive the wheels. Speeds -200..200 mm/s; equal = straight, opposite = spin. Max 10 s.
    Be careful near table edges."""
    from . import settings as S
    if S.load()["safety"]["dock_lock"]:
        return "Refused: the dock lock is on (his battery is dead), so he must stay on the charger."
    bot().drive(left_mm_s, right_mm_s, seconds)
    return "done"


@mcp.tool()
def vector_eyes(color: str) -> str:
    """Set eye color. One of: teal, orange, yellow, lime, blue, purple, green."""
    if color.lower() not in EYE_COLORS:
        return f"unknown color; use one of {', '.join(EYE_COLORS)}"
    bot().eye_color(color)
    return f"eyes {color}"


@mcp.tool()
def vector_action(action: str) -> str:
    """Make Vector do something. Known: blackjack (then bj_hit / bj_stand), fist_bump, trick, love,
    praise, scold, hello, goodbye, time, age, name, sleep, go_to_charger, take_photo, volume_up,
    volume_down. Driving ones (dance, explore, come_here, look_at_me, fetch_cube, roll_cube,
    pop_a_wheelie) are refused while the dock lock is on."""
    try:
        r = _c("/do", {"action": action}, timeout=90)
    except Exception as e:  # noqa: BLE001
        return f"Couldn't: {e}"
    return f"done: {action} {r if isinstance(r, dict) else ''}".strip()


@mcp.tool()
def vector_listen() -> str:
    """Make Vector start listening as if someone said 'Hey Vector' (only works on developer-unlocked robots)."""
    try:
        bot().wake_word()
        return "listening"
    except Exception as e:  # noqa: BLE001
        return f"This Vector can't be woken remotely ({e}). Ask the user to say 'Hey Vector' or 'Hey Jarvis'."


@mcp.tool()
def vector_status() -> dict:
    """Battery level/charging state plus robot stats."""
    v = bot()
    return {"serial": v.serial, "battery": v.battery(), "stats": v.stats()}


@mcp.tool()
def vector_faces() -> object:
    """List the faces Vector has learned."""
    return bot().faces()


@mcp.tool()
def vector_learn_face(name: str) -> str:
    """Have Vector learn the face currently in front of him under this name."""
    bot().add_face(name)
    return f"learning {name}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
