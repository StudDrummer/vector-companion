"""Launch the Vector app: local server + native macOS window (falls back to the browser)."""
import socket
import sys
import time
import webbrowser
from pathlib import Path

PORT = 47800
ICON = Path(__file__).resolve().parent / "static" / "icon.png"


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _mac_branding():
    """Show 'Vector' and our icon in the Dock/menu bar instead of 'Python'."""
    try:
        from Foundation import NSBundle  # pyobjc, installed with pywebview
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Vector"
        info["CFBundleDisplayName"] = "Vector"
        from AppKit import NSApplication, NSImage
        img = NSImage.alloc().initWithContentsOfFile_(str(ICON))
        if img:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:  # noqa: BLE001
        pass


def main():
    robot = None
    if _port_in_use(PORT):  # another copy already runs the server
        url = f"http://127.0.0.1:{PORT}/"
    else:
        from .server import ROBOT, serve
        robot = ROBOT
        _, port = serve(PORT)
        url = f"http://127.0.0.1:{port}/"
    try:
        import webview  # pywebview -> native WKWebView window
    except ImportError:
        webbrowser.open(url)
        print(f"Vector app running at {url}. Ctrl-C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            sys.exit(0)
    _mac_branding()
    webview.create_window("Vector", url, width=1120, height=780, min_size=(940, 640),
                          background_color="#1c1c1e", text_select=False)
    webview.start()
    if robot is not None:  # window closed: make sure he isn't left driving
        try:
            robot.stop()
            robot.release()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
