#!/usr/bin/env bash
# One-shot macOS setup for vector-companion.
#   ./setup.sh               install WirePod app + Python env + local model
#   ./setup.sh --autostart   also start Vector's brain automatically at login
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
say_step() { printf "\n\033[1;32m==> %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$1"; }

[[ "$(uname)" == "Darwin" ]] || { echo "This script is for macOS."; exit 1; }

# ---------------------------------------------------------------- 1. WirePod app
say_step "WirePod (the server that replaces Anki/DDL's cloud)"
if [[ -d /Applications/WirePod.app ]]; then
  echo "WirePod already installed."
else
  API=https://api.github.com/repos/kercre123/WirePod/releases
  DMG_URL=$(curl -fsSL "$API/latest" | grep -o '"browser_download_url": *"[^"]*\.dmg"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/' || true)
  if [[ -z "${DMG_URL}" ]]; then  # latest release may not carry a dmg; search recent ones
    DMG_URL=$(curl -fsSL "$API?per_page=15" | grep -o '"browser_download_url": *"[^"]*\.dmg"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/' || true)
  fi
  if [[ -z "${DMG_URL}" ]]; then
    warn "Couldn't find the WirePod .dmg automatically. Download it from https://github.com/kercre123/WirePod/releases"
  else
    echo "Downloading $DMG_URL"
    TMP=$(mktemp -d)
    curl -fL --progress-bar -o "$TMP/WirePod.dmg" "$DMG_URL"
    MNT=$(hdiutil attach -nobrowse -readonly "$TMP/WirePod.dmg" | grep -o '/Volumes/.*' | head -1)
    APP=$(find "$MNT" -maxdepth 1 -name "*.app" | head -1)
    cp -R "$APP" /Applications/
    hdiutil detach "$MNT" -quiet || true
    rm -rf "$TMP"
    echo "Installed $(basename "$APP") to /Applications."
  fi
fi

# ---------------------------------------------------------------- 2. Python env
say_step "Python environment"
PY=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[[ -n "$PY" ]] || { warn "No python3 found. Install with: brew install python@3.12"; exit 1; }
echo "Using $($PY --version)"
"$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .
if .venv/bin/pip install -q wirepod_vector_sdk; then
  echo "Full Python SDK (anki_vector) installed."
else
  warn "wirepod_vector_sdk failed to install on this Python. Everything else still works;"
  warn "for the SDK examples try: brew install python@3.11 && rm -rf .venv && PY=python3.11 ./setup.sh"
fi
[[ -f .env ]] || cp .env.example .env

# ---------------------------------------------------------------- 3. Local model
say_step "Local AI model (Ollama)"
BREW=$(command -v brew || ls /opt/homebrew/bin/brew 2>/dev/null || true)
if ! command -v ollama >/dev/null 2>&1 && [[ -n "$BREW" ]]; then
  echo "Installing Ollama with Homebrew..."
  "$BREW" install ollama && "$BREW" services start ollama && sleep 5
  export PATH="$(dirname "$BREW"):$PATH"
fi
if command -v ollama >/dev/null 2>&1; then
  ollama pull gemma3:4b || warn "ollama pull failed. Is the Ollama app running?"
else
  warn "Ollama not found. Install from https://ollama.com, then run: ollama pull gemma3:4b"
  warn "(or set BRAIN_BACKEND=anthropic and ANTHROPIC_API_KEY in .env to use Claude)"
fi

# ---------------------------------------------------------------- 4. Autostart brain
if [[ "${1:-}" == "--autostart" ]]; then
  say_step "Starting Vector's brain at login"
  PLIST="$HOME/Library/LaunchAgents/com.rushil.vector-brain.plist"
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.vector-companion"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.rushil.vector-brain</string>
  <key>ProgramArguments</key><array>
    <string>$ROOT/.venv/bin/python</string><string>-m</string><string>vector_companion.brain</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.vector-companion/brain.log</string>
  <key>StandardErrorPath</key><string>$HOME/.vector-companion/brain.log</string>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Brain running at http://127.0.0.1:11500/v1 (log: ~/.vector-companion/brain.log)"
fi

# ---------------------------------------------------------------- Next steps
say_step "Done. Next steps"
cat <<EOF
1. Open WirePod from Applications. If macOS blocks it: System Settings > Privacy & Security > "Open Anyway".
   Follow its prompts, then "Open browser" (http://localhost:8080).
2. Put Vector on his charger, hold his back button ~15 s until the lights come back (recovery mode).
3. In Chrome, go to https://wpsetup.keriganc.com and follow it (Bluetooth pairing, firmware, Activate).
4. Start the brain:     .venv/bin/vector-brain     (or rerun ./setup.sh --autostart)
5. In wire-pod (localhost:8080) > Server Settings > Knowledge Graph:
     Provider: Custom   Endpoint: http://127.0.0.1:11500/v1   Key: local   Model: vector-brain
     Enable "intent graph"/"forward unknown commands to the LLM", "remember chat", and "LLM actions" if offered.
6. Test:  .venv/bin/vector say "I'm back"
7. Claude MCP config (Claude Desktop: Settings > Developer > Edit Config):
   "vector": {"command": "$ROOT/.venv/bin/python", "args": ["-m", "vector_companion.mcp_server"], "cwd": "$ROOT"}
   Claude Code:  claude mcp add vector -- $ROOT/.venv/bin/python -m vector_companion.mcp_server
EOF
