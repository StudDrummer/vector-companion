#!/bin/bash
# Gives Jarvis a "deep brain": Stanford's OpenJarvis agent framework (Apache-2.0), fully local.
#   - installs OpenJarvis into ~/.openjarvis (its own venv; no analytics; local models only)
#   - pulls a tool-calling model (qwen3.5:4b, ~3 GB)
#   - registers Vector as an MCP server so its agents can talk through Jarvis, use his face and camera
#   - runs `jarvis serve` on 127.0.0.1:8000 at login (Vector's brain sends big requests there)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"
MODEL="${OJ_MODEL:-qwen3.5:4b}"
export PATH="$HOME/.local/bin:$PATH"

echo "1/4 OpenJarvis"
if ! command -v jarvis >/dev/null 2>&1; then
  curl -fsSL https://open-jarvis.github.io/OpenJarvis/install.sh | bash -s -- --minimal --no-analytics --no-bg-orchestrator
fi
JARVIS="$(command -v jarvis || echo "$HOME/.local/bin/jarvis")"
echo "   $JARVIS"
if [ -d "$HOME/.openjarvis/src" ]; then
  (cd "$HOME/.openjarvis/src" && uv pip install --python "$HOME/.openjarvis/.venv/bin/python" -q -e ".[server]" 2>/dev/null) || true
fi

echo "2/4 Model: $MODEL"
ollama list 2>/dev/null | grep -q "^${MODEL}" || ollama pull "$MODEL"

echo "3/4 Vector as an MCP tool server"
CFG="${OPENJARVIS_CONFIG:-$HOME/.openjarvis/config.toml}"
mkdir -p "$(dirname "$CFG")"; touch "$CFG"
if ! grep -q '^\[tools\.mcp\]' "$CFG"; then
  cat >> "$CFG" <<TOML

[tools.mcp]
enabled = true
servers = '[{"name": "vector", "command": "$PY", "args": ["-m", "vector_companion.mcp_server"]}]'
TOML
  echo "   added"
else
  echo "   [tools.mcp] already in $CFG (add Vector there by hand if it's missing)"
fi

"$PY" -m vector_companion.openjarvis --configure || true   # safe tools only: web + Vector (no shell/code)
echo "4/4 Start at login (jarvis serve on 127.0.0.1:8000)"
PLIST="$HOME/Library/LaunchAgents/com.rushil.openjarvis.plist"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.rushil.openjarvis</string>
  <key>ProgramArguments</key><array>
    <string>$JARVIS</string><string>serve</string><string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string><string>--engine</string><string>ollama</string>
    <string>--model</string><string>$MODEL</string><string>--agent</string><string>orchestrator</string>
  </array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/logs/openjarvis.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/openjarvis.log</string>
</dict></plist>
XML
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
for i in $(seq 1 30); do
  curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1 && { echo "   OpenJarvis is running. Try: \"Jarvis, research the latest on retinal imaging for Alzheimer's.\""; exit 0; }
  sleep 2
done
echo "   started, but not answering yet. Check $ROOT/logs/openjarvis.log"
