"""Render the window in demo mode to PNG files (used by CI to check the real Windows look)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("USB_FIXER_SETTINGS_PATH", os.path.join(os.environ.get("TEMP", "/tmp"), "usbfixer-shots.ini"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6 import QtCore  # noqa: E402

from usb_fixer import demo, gui  # noqa: E402


def pump(app, n=20):
    for _ in range(n):
        app.processEvents()
        QtCore.QThread.msleep(5)


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    app = gui.make_app([])
    win = gui.MainWindow(demo.DemoRunner(), demo=True)
    win.resize(1120, 800)
    win.show()
    for _ in range(300):
        app.processEvents()
        if win.result is not None:
            break
        QtCore.QThread.msleep(20)
    for mode in ("light", "dark"):
        win.mode = mode
        win.apply_theme()
        for page, name in ((0, "problems"), (1, "devices"), (2, "drivers"), (3, "system")):
            win.nav_buttons[page].click()
            if page == 0 and win.problem_cards:
                win.problem_cards[0].toggle_details()
            pump(app)
            win.grab().save(os.path.join(out_dir, f"{mode}-{name}.png"))
            if page == 0 and win.problem_cards:
                win.problem_cards[0].toggle_details()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
