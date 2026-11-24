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
  <key>NSAppleEventsUsageDescription</key><string>Jarvis reads your Calendar and Notes when you ask him to.</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict></plist>
EOF
cat > "$APP/Contents/MacOS/Vector" <<EOF
#!/bin/bash
cd "$ROOT"
if [ "\$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
  exec /usr/bin/arch -arm64 "$PY" -m vector_companion.app >> "$ROOT/logs/app.log" 2>&1
fi
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
  <key>LSArchitecturePriority</key><array><string>arm64</string><string>x86_64</string></array>
  <key>NSMicrophoneUsageDescription</key><string>Vector listens for "Hey Jarvis" so you can talk to your robot. Audio stays on this Mac.</string>
  <key>NSAppleEventsUsageDescription</key><string>Jarvis reads your Calendar and Notes and opens apps when you ask him to.</string>
</dict></plist>
EOF
# A tiny native launcher: macOS only grants the microphone to a real app binary (not a shell script).
# It asks for the microphone (you get the "Allow" prompt), then runs the Python listener as its child,
# which inherits the permission.
cat > "$TMP/main.swift" <<EOF
// Vector Ears: menu bar microphone switch + the launcher that gives the listener microphone permission.
import AppKit
import AVFoundation
import Carbon

let root = "$ROOT"
let py = "$PY"
let dataDir = NSHomeDirectory() + "/.vector-companion"
let settingsPath = dataDir + "/settings.json"

func readSettings() -> [String: Any] {
    guard let d = FileManager.default.contents(atPath: settingsPath),
          let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
    return o
}

func micEnabled() -> Bool {
    let ears = readSettings()["ears"] as? [String: Any]
    return (ears?["enabled"] as? Bool) ?? true
}

func setMic(_ on: Bool) {
    var s = readSettings()
    var ears = (s["ears"] as? [String: Any]) ?? [:]
    ears["enabled"] = on
    s["ears"] = ears
    try? FileManager.default.createDirectory(atPath: dataDir, withIntermediateDirectories: true)
    if let d = try? JSONSerialization.data(withJSONObject: s, options: [.prettyPrinted]) {
        try? d.write(to: URL(fileURLWithPath: settingsPath), options: .atomic)
    }
}

func earsRunning() -> Bool {
    let check = Process()
    check.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
    check.arguments = ["-f", "vector_companion.ears"]
    check.standardOutput = FileHandle.nullDevice
    try? check.run(); check.waitUntilExit()
    return check.terminationStatus == 0
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var toggleItem: NSMenuItem!
    var stateItem: NSMenuItem!
    var quitting = false
    var lastStart = Date.distantPast
    var permissionAsked = false
    var hotKey: EventHotKeyRef?

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        let menu = NSMenu()
        stateItem = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        stateItem.isEnabled = false
        menu.addItem(stateItem)
        toggleItem = NSMenuItem(title: "", action: #selector(toggle), keyEquivalent: "")
        toggleItem.target = self
        menu.addItem(toggleItem)
        let hint = NSMenuItem(title: "Shortcut: Control-Option-J", action: nil, keyEquivalent: "")
        hint.isEnabled = false
        menu.addItem(hint)
        menu.addItem(.separator())
        let open = NSMenuItem(title: "Open Vector", action: #selector(openApp), keyEquivalent: "")
        open.target = self
        menu.addItem(open)
        let quit = NSMenuItem(title: "Quit Vector Ears", action: #selector(quitAll), keyEquivalent: "")
        quit.target = self
        menu.addItem(quit)
        item.menu = menu
        refresh()
        registerHotKey()
        AVCaptureDevice.requestAccess(for: .audio) { _ in
            DispatchQueue.main.async { self.permissionAsked = true; self.keepEarsAlive() }
        }
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            self.refresh()
            self.keepEarsAlive()
        }
    }

    func refresh() {
        let on = micEnabled()
        if let b = item.button {
            b.image = NSImage(systemSymbolName: on ? "mic.fill" : "mic.slash",
                              accessibilityDescription: on ? "Vector is listening" : "Vector's microphone is off")
            b.image?.isTemplate = true
            b.toolTip = on ? "Vector is listening for Hey Jarvis" : "Vector's microphone is off"
        }
        stateItem.title = on ? "Listening for Hey Jarvis" : "Microphone off"
        toggleItem.title = on ? "Turn Microphone Off" : "Turn Microphone On"
    }

    @objc func toggle() {
        let on = !micEnabled()
        setMic(on)
        NSSound(named: on ? "Tink" : "Pop")?.play()
        refresh()
    }

    func keepEarsAlive() {
        if quitting || !permissionAsked || Date().timeIntervalSince(lastStart) < 8 || earsRunning() { return }
        lastStart = Date()
        let logPath = root + "/logs/ears.out"
        if !FileManager.default.fileExists(atPath: logPath) { FileManager.default.createFile(atPath: logPath, contents: nil) }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = ["-m", "vector_companion.ears"]
        p.currentDirectoryURL = URL(fileURLWithPath: root)
        if let log = FileHandle(forWritingAtPath: logPath) {
            log.seekToEndOfFile()
            p.standardOutput = log
            p.standardError = log
        }
        try? p.run()
    }

    @objc func openApp() {
        NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications/Vector.app"))
    }

    @objc func quitAll() {
        quitting = true
        let k = Process()
        k.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        k.arguments = ["-f", "vector_companion.ears"]
        try? k.run(); k.waitUntilExit()
        NSApp.terminate(nil)
    }

    func registerHotKey() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async { (NSApp.delegate as? AppDelegate)?.toggle() }
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: OSType(0x56454152), id: 1)
        RegisterEventHotKey(UInt32(kVK_ANSI_J), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &hotKey)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
EOF
if xcrun swiftc -O -o "$EARS/Contents/MacOS/VectorEars" "$TMP/main.swift" >/dev/null 2>"$TMP/swift.err"; then
  echo "   built the native microphone launcher"
else
  echo "   couldn't compile the launcher (install Xcode command line tools: xcode-select --install):"
  sed 's/^/     /' "$TMP/swift.err" | head -5
  cat > "$EARS/Contents/MacOS/VectorEars" <<EOF
#!/bin/bash
cd "$ROOT"
pgrep -f "vector_companion.ears" >/dev/null && exit 0
exec "$PY" -m vector_companion.ears >> "$ROOT/logs/ears.out" 2>&1
EOF
fi
chmod +x "$EARS/Contents/MacOS/VectorEars"
codesign --force --deep --sign - "$EARS" >/dev/null 2>&1 || true
rm -rf "$TMP"
# swap in the new Ears (menu bar mic switch) right away
pkill -x VectorEars 2>/dev/null || true
pkill -f "vector_companion.ears" 2>/dev/null || true
sleep 1
open -g "$EARS" 2>/dev/null && echo "   Vector Ears is in your menu bar (mic icon). Control-Option-J turns the mic on/off." || true
touch "$APP"  # refresh Finder/Dock icon cache

echo
echo "Done. Open Vector from Applications or Spotlight (Cmd+Space, type Vector)."
echo "Tip: drag it to your Dock to keep it there."
[[ -n "${NO_OPEN:-}" ]] || open "$APP" || true
