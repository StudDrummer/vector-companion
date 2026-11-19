#!/usr/bin/env bash
# Sets up: Vector announcements for long terminal commands, Claude Code finish/input
# announcements, and Claude Code control of Vector (MCP). Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VEC="$ROOT/.venv/bin/vector"
PY="$ROOT/.venv/bin/python"
ZSHRC="$HOME/.zshrc"

echo "==> Terminal announcements (zsh)"
touch "$ZSHRC"
cp "$ZSHRC" "$ZSHRC.bak-vector"
# remove the PATH line suggested earlier (it would shadow your conda python)
grep -v 'vector-companion/.venv/bin:\$PATH' "$ZSHRC.bak-vector" > "$ZSHRC" || true
LINE="source \"$ROOT/shell/vector.zsh\""
grep -qF "$LINE" "$ZSHRC" || printf '\n# Vector robot\n%s\n' "$LINE" >> "$ZSHRC"
echo "   added to ~/.zshrc (backup: ~/.zshrc.bak-vector)"

echo "==> Claude Code hooks"
"$PY" - "$VEC" <<'PYEOF'
import json, sys, shutil
from pathlib import Path
vec = sys.argv[1]
p = Path.home() / ".claude" / "settings.json"
p.parent.mkdir(exist_ok=True)
data = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}
if p.exists():
    shutil.copy(p, p.with_suffix(".json.bak-vector"))
hooks = data.setdefault("hooks", {})
want = {
    "UserPromptSubmit": f'"{vec}" hook claude-start',
    "Stop": f'"{vec}" hook claude-stop --detach',
    "Notification": f'"{vec}" hook claude-input --detach',
}
for event, cmd in want.items():
    groups = hooks.setdefault(event, [])
    # drop any older vector hooks, then add ours
    for g in groups:
        g["hooks"] = [h for h in g.get("hooks", []) if "hook claude-" not in h.get("command", "")]
    groups[:] = [g for g in groups if g.get("hooks")]
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
p.write_text(json.dumps(data, indent=2))
print(f"   hooks written to {p}")
PYEOF

echo "==> Claude Code can control Vector (MCP)"
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user vector >/dev/null 2>&1 || true
  claude mcp add --scope user vector -- "$PY" -m vector_companion.mcp_server && echo "   added"
else
  echo "   claude CLI not found; skip. Later run:"
  echo "   claude mcp add --scope user vector -- \"$PY\" -m vector_companion.mcp_server"
fi

echo "==> Restarting Vector's brain"
launchctl kickstart -k "gui/$(id -u)/com.rushil.vector-brain" 2>/dev/null && echo "   restarted" || echo "   (brain not set to autostart; skip)"

echo
echo "Done. Open a NEW terminal tab (or run: source ~/.zshrc), then test:"
echo "   sleep 31        # Vector should announce it when it finishes"
