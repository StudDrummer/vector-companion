#!/usr/bin/env bash
# Builds /Applications/Vector.app (a native window onto the local Vector control app). Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"
APP="/Applications/Vector.app"

echo "==> Updating Python packages (adds the native window library)"
"$ROOT/.venv/bin/pip" install -q -e "$ROOT" pywebview

echo "==> Building app icon"
TMP=$(mktemp -d)
ICONSET="$TMP/AppIcon.iconset"; mkdir -p "$ICONSET"
SRC="$ROOT/vector_companion/app/static/icon.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$TMP/AppIcon.icns"

echo "==> Creating $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$TMP/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Vector</string>
  <key>CFBundleDisplayName</key><string>Vector</string>
  <key>CFBundleIdentifier</key><string>com.studdrummer.vector</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Vector</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict></plist>
EOF
cat > "$APP/Contents/MacOS/Vector" <<EOF
#!/bin/bash
cd "$ROOT"
exec "$PY" -m vector_companion.app >> "$ROOT/logs/app.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/Vector"
mkdir -p "$ROOT/logs"

echo "==> Creating /Applications/Vector Ears.app (the 'Hey Jarvis' listener, runs in the background)"
EARS="/Applications/Vector Ears.app"
rm -rf "$EARS"
mkdir -p "$EARS/Contents/MacOS" "$EARS/Contents/Resources"
cp "$TMP/AppIcon.icns" "$EARS/Contents/Resources/AppIcon.icns"
cat > "$EARS/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Vector Ears</string>
  <key>CFBundleDisplayName</key><string>Vector Ears</string>
  <key>CFBundleIdentifier</key><string>com.studdrummer.vector-ears</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>VectorEars</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Vector listens for "Hey Jarvis" so you can talk to your robot. Audio stays on this Mac.</string>
</dict></plist>
EOF
cat > "$EARS/Contents/MacOS/VectorEars" <<EOF
#!/bin/bash
cd "$ROOT"
pgrep -f "vector_companion.ears" >/dev/null && exit 0   # only one copy
exec "$PY" -m vector_companion.ears >> "$ROOT/logs/ears.out" 2>&1
EOF
chmod +x "$EARS/Contents/MacOS/VectorEars"
codesign --force --deep --sign - "$EARS" >/dev/null 2>&1 || true
rm -rf "$TMP"
touch "$APP"  # refresh Finder/Dock icon cache

echo
echo "Done. Open Vector from Applications or Spotlight (Cmd+Space, type Vector)."
echo "Tip: drag it to your Dock to keep it there."
[[ -n "${NO_OPEN:-}" ]] || open "$APP" || true
