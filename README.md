# vector-companion

Bring a 2019 Anki Vector back to life as a local AI companion that's wired into your projects.

```
 "Hey Vector, ..."                                     Claude Desktop / Claude Code
      |                                                       |
  [Vector] <--wifi--> [WirePod app on your Mac :8080] <--- [vector MCP server]
                               |  Knowledge Graph (Custom)          ^
                               v                                    |
                      [vector-brain :11500/v1] -----> Ollama (local) or Claude API
                       persona + memory + to-do        `vector` CLI / your scripts
```

## Why WirePod (and not the official cloud)

Anki went bankrupt in 2019; Digital Dream Labs (DDL) bought the robots, but its cloud has been unreliable
since 2023 and, as of July 2026, DDL's digital assets are under a court-appointed receiver. Voice through
the official route also needs a paid subscription. **wire-pod** is a free, open-source (MIT) replacement
server that runs on your own computer, supports Vector 1.0 and 2.0, keeps every voice command working,
and adds an LLM "knowledge graph", custom commands, and a full HTTP/Python API. Everything here builds on it.

## 1. Install (about 10 minutes, one command)

```bash
cd vector-companion
./setup.sh --autostart
```

This downloads the WirePod macOS app into /Applications, creates `.venv` with this package and the
Python SDK (`wirepod_vector_sdk`), pulls a small local model with Ollama (`llama3.2:3b`), copies
`.env.example` to `.env`, and starts Vector's brain at login.

## 2. Connect Vector to WirePod (hands-on, ~15 minutes)

1. Open **WirePod** from Applications. If macOS says the developer is unidentified:
   System Settings > Privacy & Security > **Open Anyway**. Follow its prompts, then **Open browser**.
2. Make sure Vector and your Mac are on the same Wi-Fi. (School/enterprise Wi-Fi with client isolation
   won't work; use home Wi-Fi or a phone hotspot.)
3. Charge Vector. A robot stored since 2020 may have a deeply drained battery: leave him on the charger
   for an hour first. If he won't wake at all, see Troubleshooting.
4. Put him on the charger and **hold the back button ~15 seconds** until the lights return (recovery mode;
   this doesn't wipe his memories). His screen will show `anki.com/v` or `ddl.io/v`.
5. In **Chrome** (needs Web Bluetooth), open <https://wpsetup.keriganc.com>. Pair over Bluetooth, let it
   install the special `ep` firmware, connect him to Wi-Fi, then click **Activate**. If Chrome errors,
   enable `chrome://flags` > *Experimental Web Platform features* and retry. If Activate fails, wait 20 s and retry.
6. Done when it says setup is complete. Say "Hey Vector, what time is it?" to check.

## 3. Give him a brain

In wire-pod (<http://localhost:8080>) > **Server Settings** > **Knowledge Graph**:

| Field | Value |
|---|---|
| Provider | Custom (OpenAI-compatible) |
| Endpoint | `http://127.0.0.1:11500/v1` |
| API key | `local` |
| Model | `vector-brain` |

Also turn on, if your version offers them: **forward unrecognized speech to the LLM** (intent graph),
**remember chat**, and **let the LLM perform actions/animations**. Then "Hey Vector... I have a question...
what should I study tonight?" goes to your brain.

Choose the model in `.env`:
- `BRAIN_BACKEND=ollama` (default): free, private, runs on your Mac.
- `BRAIN_BACKEND=anthropic` + `ANTHROPIC_API_KEY=...`: Claude answers (`claude-haiku-5-5` by default; fast and cheap).

Restart the brain after editing: `launchctl kickstart -k gui/$(id -u)/com.rushil.vector-brain`
(or just run `.venv/bin/vector-brain` in a terminal).

### What the brain adds on top of wire-pod
- A persona: study buddy / lab companion who knows who you are and keeps answers speakable.
- Live context in every answer: the time, your to-do list, and things you asked him to remember
  (set `PROJECTS_DIR=~/GitHub` in `.env` if you also want him to know your recent commits).
- Local skills, no LLM needed:
  - "I have a question. Remember that my AP Bio test is Friday." / "What do you remember?" / "Forget everything."
  - "Add finish the physics lab report to my list." / "What's on my list?" / "Clear my list."
  - "Start a 25 minute study timer." He announces when it's done (Pomodoro).

Data lives in `~/.vector-companion/` (memory.json, todo.json, brain.log).

## 4. Let Claude control Vector (MCP)

Claude Code:
```bash
claude mcp add vector -- "$PWD/.venv/bin/python" -m vector_companion.mcp_server
```
Claude Desktop: Settings > Developer > Edit Config, add under `mcpServers`:
```json
"vector": { "command": "/ABSOLUTE/PATH/vector-companion/.venv/bin/python",
            "args": ["-m", "vector_companion.mcp_server"] }
```
Tools: `vector_say`, `vector_look` (camera photo Claude can see), `vector_drive`, `vector_head`,
`vector_lift`, `vector_eyes`, `vector_action` (dance, explore, fetch_cube, go_to_charger...),
`vector_listen`, `vector_status`, `vector_faces`, `vector_learn_face`.

Try: *"When the tests pass, have Vector say so and dance."* or *"Look through Vector's camera: is my
lab notebook on the desk?"*

## 5. Hook him into your projects (CLI)

```bash
.venv/bin/vector say "NeuroVision fold 3 finished"
.venv/bin/vector run -- python train.py     # announces success/failure + duration; dances after long jobs
.venv/bin/vector eyes purple
.venv/bin/vector do explore
.venv/bin/vector look desk.jpg
.venv/bin/vector status
```
Add `.venv/bin` to your PATH (or alias `vector=...`) to use it anywhere: in a git `post-push` hook, at the
or at the end of a Jupyter notebook (`!vector say "done"`).

From Python anywhere:
```python
from vector_companion import Vector
Vector().say("Validation AUC is 0.91")
```

## 6. Automatic announcements (Claude Code + terminal)

```bash
./install_notifications.sh      # once; then open a new terminal tab
```
- Claude Code: "Claude is done. That took 3 minutes." when a task ran 20+ seconds (quick replies stay
  silent), and "Claude needs your input." when it is waiting on you. Eyes go lime / yellow.
- Terminal: any command that runs 30+ seconds gets "Your python command finished after 4 minutes."
  or "Heads up. Your npm command failed..." Editors, ssh, claude, REPLs and Ctrl-C are ignored.
- Adds a safe `vector` shortcut (an alias, so it never shadows your conda Python).
- Tune: `VECTOR_MIN_SECONDS=60` / `VECTOR_TERMINAL_ANNOUNCE=0` (in ~/.zshrc, before the source line),
  `VECTOR_CLAUDE_MIN_SECONDS=20` (in `.env`). Undo: delete the `# Vector robot` line in ~/.zshrc and the
  `hook claude-` entries in ~/.claude/settings.json (backups end in `.bak-vector`).

## 7. The Vector app

```bash
./install_app.sh        # builds /Applications/Vector.app and opens it
```
A native Mac window in the style of System Settings:
- **Overview**: battery, charger, network, quick actions, service status.
- **Drive & Camera**: live camera, on-screen joystick (or WASD/arrows), head and lift, speed, mirror camera to his face.
  He stops automatically if the app loses contact.
- **Actions**: dance, explore, fetch/roll cube, wheelie, blackjack, photo, go home, sleep, listen.
- **Voice & Sound**: say anything, quick phrases, volume, play any audio file.
- **Eyes**: preset colors or any custom hue.
- **People / Photos**: rename or forget faces, teach new ones; browse and delete his photos.
- **Brain & Memory**: local model or Claude, your name, what he remembers, your to-do list.
- **Notifications**: Claude Code and terminal announcements, thresholds, eye flash, quiet hours, test button, activity log.
- **Robot Settings / Diagnostics**: wake word, units, clock, location, time zone, language; lifetime stats and logs.

## 8. Companion: personality, focus timer, homework scanning

`./upgrade.sh` installs an always-on companion service that holds a Python-SDK connection to Vector
(set up automatically from wire-pod, no prompts) and adds:

- **Hearts when you pet him**: hold a finger on his back for a second.
- **Greetings** for people he recognizes, and a **morning briefing** (time, your to-do list, reminders
  for today/tomorrow from his memory) the first time he sees you before 11 AM.
- **Focus timer on his face**: "I have a question... start a 25 minute focus timer", "how much time is left",
  "stop the timer". Check-ins on his screen every 5 minutes, a celebration at the end.
- **Scan & Ask**: "I have a question... check my homework" / "solve this" / "read this page" /
  "what am I holding". He takes a high-resolution photo, an AI reads it, he speaks a short summary, and
  the full worked explanation appears in the app (Scan & Ask) plus a Mac notification. Uses your Claude,
  ChatGPT or Gemini key (Brain & Memory), or a local vision model (`ollama pull qwen2.5vl:7b`).
  "Explain" mode teaches and checks your work; "Solve" gives full worked solutions.
- **Face icons** for Claude/terminal announcements (check, X, question).
- **Precise head and lift** sliders in Drive (R/F and T/G keys).
- **Animations**: browse and play any of his built-in animations (Personality page).

### Voice commands (say "Hey Vector", wait for his lights, then "I have a question..." + one of these)
| Say | He does |
|---|---|
| status report | battery, focus timer, your list, what Claude and your last long command did, upcoming reminders; plus a heads-up display on his face |
| good morning / give me my briefing | time, your list, reminders for the next few days |
| good night | tomorrow's reminders, then goes to sleep |
| what did Claude do | the one-line summary of Claude's last finished task |
| check my homework / solve this / read this page / what am I holding | Scan & Ask |
| start a 25 minute focus timer / how much time is left / stop the timer | focus timer on his face |
| remember that ... / what do you remember / add ... to my list / what's on my list | memory and to-do list |
| anything else | answered by the AI you picked, in the personality you picked |

### Personality styles
Brain & Memory > Personality: **Vector** (playful) or **JARVIS** (calm, quick British butler who calls
you sir and offers the obvious next step). It changes his answers, greetings, briefings and announcements.
His own wake word stays "Hey Vector" (it's built into his firmware), so "Hey Jarvis" runs on the Mac (below).

## 9. Hey Jarvis (your Mac's microphone)
`Vector Ears.app` (installed and started by `./upgrade.sh`, runs in the background at login) listens for
**"Hey Jarvis"** with [openWakeWord](https://github.com/dscripka/openWakeWord) and transcribes with
Whisper, all offline on the Mac. Say it in one breath: "Hey Jarvis, what's the weather tomorrow?",
then keep talking for follow-ups without the wake word; "that's all" ends it. This avoids the two weak
spots of "Hey Vector": his small microphones and his Wi-Fi link to WirePod.
Settings (wake word: Hey Jarvis / Hey Mycroft / Alexa, sensitivity, follow-ups, chime) are on the
**Hey Jarvis** page. If it doesn't respond, click Restart Ears and allow the microphone.

**JARVIS voice:** with the JARVIS personality (or Voice set to JARVIS), he speaks with a Mac voice
(Daniel, British, by default) streamed through his own speaker. Falls back to his robot voice automatically.

## 10. Desk guard, cube button, weather
- **Desk guard**: "Hey Jarvis, guard my desk" (or the Desk Guard page). He watches from the charger, saves a
  photo and notifies the Mac when something moves, and when he recognizes you he turns it off and tells
  you what happened.
- **Cube button** (needs a fresh N / E90 battery in the cube): tap once to start or stop a focus timer
  (cube lights go green, yellow, red), tap twice for a status report.
- **Weather**: in the morning briefing and "what's the weather", from Open-Meteo (free, no key).
  Set the place on the Personality page.
- **Hearing & Wi-Fi** (Diagnostics): how often he dropped off Wi-Fi and how often he heard "Hey Vector".

The local model is **gemma3:4b**: it answers in about half a second and also reads homework photos
(about 4 seconds). If you pick a "thinking" model like qwen3-vl, he still talks with a fast one, because
thinking models spend their answer budget thinking and return nothing.

### Smarter announcements
When Claude Code finishes, Vector reads Claude's final message and says what it did, where:
"Claude finished in vector companion. It fixed the head slider bug and added 3 tests." with a CLAUDE badge
on his face. When Claude needs you: "Claude needs your permission to use Bash in vigil." Terminal jobs get a
terminal badge and say which folder they ran in.

### Your AI apps get a body
The MCP server (tools: say, look (HD camera), show on face, head angle, lift height, animations,
focus timer, desk guard, weather, drive, eyes, actions, faces) is added to Claude Code, Claude Desktop and Gemini CLI by
`upgrade.sh`. Ask any of them things like "look through Vector's camera and tell me what's on my desk",
"put a heart on Vector's face", or "when the tests pass, make Vector celebrate".
ChatGPT's desktop app can't load local MCP servers, so use ChatGPT as Vector's *brain* instead
(Brain & Memory > ChatGPT).

### SSH?
Regular (production) Vectors can't be SSH'd into: that needs an OSKR unlock from DDL, which isn't
available. The SDK used here covers the camera, screen, motors, sensors, animations and speech.

## 9. Examples
- `examples/sdk_tour.py`: full SDK: animations, drawing on his face screen, camera frames, face detection.

## Troubleshooting
- **Won't power on after years in storage:** charge 1-2 hours; clean the charger contacts and the
  contacts under him. Lithium cells that sat empty for years can be dead; a replacement battery
  (iFixit has guides) is the fix.
- **Setup site can't find him:** use Chrome, keep Bluetooth on, keep him on the charger, put him back
  in recovery mode (hold button 15 s), close other tabs using Bluetooth.
- **Voice commands time out / he can't find the server:** only one machine on your network may be named
  `escapepod`; check <http://escapepod.local:8080> works from another device; allow WirePod through the
  macOS firewall; restart Vector and WirePod. More: <https://github.com/kercre123/wire-pod/wiki/Troubleshooting>.
- **Brain not answering:** `curl http://127.0.0.1:11500/health`, check `~/.vector-companion/brain.log`,
  make sure the Ollama app is running (`ollama list`).
- Community help: r/AnkiVector and the wire-pod GitHub issues/Discord.

## Credits
wire-pod and WirePod by kercre123 (MIT). Vector SDK originally by Anki, maintained for wire-pod.


## Deep brain: OpenJarvis (Stanford)

Everyday questions stay on the fast voice path. Requests that need real work ("Jarvis, research...",
"look up...", "compare...", "the latest research on...") go to
[OpenJarvis](https://github.com/open-jarvis/OpenJarvis), Stanford's local-first agent framework,
running on this Mac. Jarvis says "On it, sir.", speaks a short summary when it's done, and saves the
full write-up under Brain & Memory > Reports.

    ./setup_openjarvis.sh      # installs OpenJarvis (local only, no analytics), a tool-calling model,
                               # registers Vector as an MCP tool server, and starts it at login

Vector is exposed to any agent framework that speaks MCP (OpenJarvis, Hermes Agent, OpenClaw,
nanobot, Claude) through `python -m vector_companion.mcp_server`; `skills/vector-desk-robot/SKILL.md`
teaches them how to use him.

## Turn-taking

Ears uses Pipecat's open Smart Turn v3 model (8 MB, ~35 ms per check) to hear when you've finished
a sentence from your intonation, so he answers after ~0.25 s of quiet when you're done and waits
when you're only pausing.


## Jarvis on the Mac

Say his name and what you want, in one breath:

| Say | What happens |
|---|---|
| "open Canvas / Instagram / Notes / NeuroVision" | Opens the app, site, or your project on GitHub (unknown names try name.com) |
| "close Instagram" | Closes those browser tabs, or quits the app |
| "check my calendar", "what's on my calendar tomorrow" | Reads the Mac Calendar app (every account added in System Settings) |
| "what's due tomorrow", "what are my grades" | Canvas (token or calendar feed on Brain & Memory > Connections) |
| "remind me to email Mr. K in 20 minutes", "set a timer for 10 minutes" | Spoken reminder + Mac notification; survives restarts |
| "take a note: ...", "read my note about chem" | Apple Notes |
| "play music", "pause", "next song", "what song is this" | Spotify desktop app (or Apple Music) |
| "what did I push today", "check GitHub", "my pull requests" | GitHub (token on Connections, or `gh auth login`) |
| "ask Claude what to do next" | Opens Claude with the question and what's due / on your calendar |
| "what should I do next" | Jarvis plans from your real Canvas, calendar and GitHub |
| "what can you do" | The short list |

At 7:30 PM he gives a one-line heads-up about Canvas work due tomorrow (Personality page to turn off).
