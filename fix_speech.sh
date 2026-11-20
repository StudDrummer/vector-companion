#!/usr/bin/env bash
# Swap WirePod's small English speech model for the larger, more accurate one (~130 MB download).
# The small model mishears a lot ("start a focus timer" -> "the focus time around").
# Safe to re-run; keeps a backup of the old model. Undo: ./fix_speech.sh --undo
set -euo pipefail
MODELS="$HOME/Library/Application Support/wire-pod/vosk/models/en-US"
URL="https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip"

if [[ ! -d "$MODELS/model" ]]; then
  echo "Couldn't find WirePod's speech model at: $MODELS/model"
  echo "Open WirePod once (and finish its setup), then run this again."
  exit 1
fi

restart_wirepod() {
  osascript -e 'quit app "WirePod"' 2>/dev/null || true
  sleep 3
  open -a WirePod
  echo "WirePod restarted. Give it ~20 seconds to load the model, then talk to Vector."
}

if [[ "${1:-}" == "--undo" ]]; then
  [[ -d "$MODELS/model.small-backup" ]] || { echo "No backup to restore."; exit 1; }
  rm -rf "$MODELS/model" && mv "$MODELS/model.small-backup" "$MODELS/model"
  echo "Restored the original small model."; restart_wirepod; exit 0
fi

if [[ -f "$MODELS/model/.vector-lgraph" ]]; then
  echo "The larger speech model is already installed."; exit 0
fi

TMP=$(mktemp -d)
echo "Downloading the larger English model (about 130 MB)..."
curl -fL --progress-bar -o "$TMP/m.zip" "$URL"
unzip -q "$TMP/m.zip" -d "$TMP"
NEW=$(find "$TMP" -maxdepth 1 -type d -name "vosk-model-*" | head -1)
[[ -n "$NEW" ]] || { echo "Download looked wrong; nothing changed."; exit 1; }
touch "$NEW/.vector-lgraph"
rm -rf "$MODELS/model.small-backup"
mv "$MODELS/model" "$MODELS/model.small-backup"
mv "$NEW" "$MODELS/model"
rm -rf "$TMP"
echo "Installed. (Old model kept as model.small-backup; undo with ./fix_speech.sh --undo)"
restart_wirepod
