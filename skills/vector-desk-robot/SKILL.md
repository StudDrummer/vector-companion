---
name: vector-desk-robot
description: Control Rushil's Anki Vector desk robot (speak in Jarvis's voice, show icons or text on his face, look through his camera, move head/lift, start study timers, desk guard). Use when a task should end with something said or shown on the desk, or needs a look at the desk.
---

# Vector desk robot

Vector is the physical body of Jarvis: a small robot on the desk with a face screen, a camera,
a head and a lift. He stays on his charger (dock lock), so never ask him to drive.

Tools come from the `vector` MCP server (`python -m vector_companion.mcp_server`):

| Tool | Use it to |
|---|---|
| `vector_say(text)` | Say something out loud in Jarvis's voice. One or two short sentences, no markdown. |
| `vector_show_on_face(text, icon, seconds)` | Put a short word/number or an icon (heart, check, x, question, thinking, talking) on his face. |
| `vector_look()` | Get a photo from his camera (homework held up, what's on the desk). |
| `vector_focus_timer(minutes, stop)` | Start or stop a study timer with check-ins. |
| `vector_desk_guard(on)` | Watch the desk and log anything that moves. |
| `vector_weather(day)` | Weather sentence for Bellevue. |
| `vector_head_angle(degrees)` / `vector_lift_height(height)` | Small physical gestures. |
| `vector_action(action)` | Built-ins: fist_bump, love, praise, trick, blackjack, take_photo, status. |
| `vector_status()` | Battery, charger, connection. |

## Good habits
- Finish long-running work with a one-line `vector_say` summary ("Your report is ready, sir.").
- Put the result's single key number on his face with `vector_show_on_face` (e.g. "92%").
- Use `vector_look` before answering anything about "this", "what I'm holding" or the desk.
- Keep spoken text under ~30 words; put details in the written answer instead.
