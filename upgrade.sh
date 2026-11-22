#!/usr/bin/env bash
# One command to install/refresh everything:
#   companion service (petting, greetings, focus timer, face icons, homework scanning),
#   Python packages, the Vector app, and Vector control for Claude Desktop / Gemini CLI.
# Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"
DATA="$HOME/.vector-companion"
mkdir -p "$DATA" "$ROOT/logs" "$HOME/Library/LaunchAgents"
step() { printf "\n\033[1;32m==> %s\033[0m\n" "$1"; }

step "Python packages"
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q -e "$ROOT" pywebview wirepod_vector_sdk

step "Connecting the Python SDK to Vector (via wire-pod)"
if "$PY" -m vector_companion.sdk_setup; then echo "   SDK ready"; else
  echo "   Couldn't reach Vector right now. That's fine: the companion keeps retrying in the background."
  echo "   (Vector must be on, on your Wi-Fi, and WirePod must be open.)"; fi

step "About you (used to pitch explanations at your level)"
if [[ ! -s "$DATA/about_me.txt" ]]; then
  cat > "$DATA/about_me.txt" <<'EOF'
Rushil is a junior at The Overlake School in Bellevue, Washington, aiming for Stanford (CS or biomedical engineering).
Classes: AP Biology (visual learner; explain the idea so it clicks instead of memorizing, especially DNA, RNA and gene expression), AP English Language (rhetorical analysis), Honors Physics preparing for AP Physics 1, Honors US History. Also SAT prep.
Interests: AI and machine learning, medicine and biomedical research (ISEF projects), drums (11 years, Led Zeppelin fan), cars, Fortnite, Rocket League and Forza.
EOF
  echo "   wrote $DATA/about_me.txt (edit it any time in the app: Brain & Memory)"
else echo "   keeping your existing about_me.txt"; fi

step "Companion service (always on)"
PLIST="$HOME/Library/LaunchAgents/com.rushil.vector-companion.plist"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.rushil.vector-companion</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>-m</string><string>vector_companion.companion</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/logs/companion.out</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/companion.out</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
for f in "$ROOT/logs/companion.out" "$ROOT/logs/ears.out" "$ROOT/logs/app.log"; do  # keep logs small
  [[ -f "$f" && $(stat -f%z "$f" 2>/dev/null || echo 0) -gt 20000000 ]] && tail -c 2000000 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
launchctl load "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.rushil.vector-brain" 2>/dev/null || true
echo "   companion running on http://127.0.0.1:47801 (brain restarted too)"

step "Claude Code + terminal announcements"
bash "$ROOT/install_notifications.sh" | sed 's/^/   /'

echo "-> voice commands (registered in WirePod so they run before its built-ins)"
"$PY" -m vector_companion.voice --install || echo "   WirePod isn't running; open it and re-run ./upgrade.sh"

step "Vector control for your AI apps (MCP)"
"$PY" - "$PY" <<'PYEOF'
import json, shutil, sys
from pathlib import Path
py = sys.argv[1]
entry = {"command": py, "args": ["-m", "vector_companion.mcp_server"]}
targets = [
    ("Claude Desktop", Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"),
    ("Gemini CLI", Path.home() / ".gemini/settings.json"),
]
for name, p in targets:
    if not p.parent.exists():
        print(f"   {name}: not installed, skipped")
        continue
    data = {}
    if p.exists() and p.read_text().strip():
        shutil.copy(p, p.with_name(p.name + ".bak-vector"))
        data = json.loads(p.read_text())
    data.setdefault("mcpServers", {})["vector"] = entry
    p.write_text(json.dumps(data, indent=2))
    print(f"   {name}: added (restart {name} to load it)")
PYEOF
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user vector >/dev/null 2>&1 || true
  claude mcp add --scope user vector -- "$PY" -m vector_companion.mcp_server >/dev/null && echo "   Claude Code: updated"
fi

step "Local AI model (talks and sees)"
if command -v ollama >/dev/null 2>&1; then
  if ollama list 2>/dev/null | grep -q "^gemma3:4b"; then echo "   gemma3:4b ready (answers in under a second, reads homework photos)"
  else ollama pull gemma3:4b && echo "   gemma3:4b installed"; fi
fi

step "Vector app"
NO_OPEN=1 bash "$ROOT/install_app.sh" >/dev/null && echo "   /Applications/Vector.app and Vector Ears.app rebuilt"

step "Hey Jarvis (your Mac's microphone)"
if "$ROOT/.venv/bin/pip" install -q "openwakeword>=0.6" sounddevice faster-whisper onnxruntime scipy; then
  "$PY" -m vector_companion.ears --setup || echo "   model download failed; it will retry the first time Ears starts"
  EPLIST="$HOME/Library/LaunchAgents/com.rushil.vector-ears.plist"
  cat > "$EPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.rushil.vector-ears</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/open</string><string>-g</string><string>-j</string><string>-a</string><string>/Applications/Vector Ears.app</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
EOF
  pkill -f "vector_companion.ears" 2>/dev/null || true
  sleep 1
  launchctl unload "$EPLIST" 2>/dev/null || true
  launchctl load "$EPLIST"
  echo "   Vector Ears started. If macOS asks to let \"Vector Ears\" use the microphone, click Allow."
else
  echo "   couldn't install the speech packages; Hey Jarvis is off (everything else works)"
fi

step "Done"
cat <<EOF
Say "Hey Jarvis" near your Mac (no waiting), e.g. "Hey Jarvis, what's the weather?"
Then just keep talking for a follow-up. Also: "guard my desk", "check my homework".
Or say "Hey Vector", wait for his lights, then "I have a question..." and:
  "status report"                       "good morning"         "what did Claude do"
  "check my homework" (hold the page up)  "what am I holding"
  "start a 25 minute focus timer"       "good night"
Pet his back for a second -> hearts.   Open a NEW Terminal tab, run: sleep 35
In the Vector app: Brain & Memory > Personality > JARVIS.
EOF
open /Applications/Vector.app || true
