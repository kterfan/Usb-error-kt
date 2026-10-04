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
    # wait for the online BIOS check (fake in demo mode)
    for _ in range(200):
        app.processEvents()
        if win.result is not None and win.result.bios is not None:
            break
        QtCore.QThread.msleep(20)
    # run the live test once (demo: a broken device "arrives" after a couple of polls)
    win.live_duration, win.live_interval = 10, 0.05
    win.start_live()
    for _ in range(500):
        app.processEvents()
        if not win.live_running:
            break
        QtCore.QThread.msleep(20)
    for mode in ("light", "dark"):
        win.mode = mode
        win.apply_theme()
        for name in gui.PAGES:
            win.go(name)
            if name == "problems" and win.problem_cards:
                win.problem_cards[0].toggle_details()
            pump(app)
            win.grab().save(os.path.join(out_dir, f"{mode}-{name}.png"))
            if name == "problems" and win.problem_cards:
                win.problem_cards[0].toggle_details()
    # the confirmation dialog and the about box
    for mode in ("light", "dark"):
        win.mode = mode
        win.apply_theme()
        for name, dlg in (("confirm", win.make_confirm_dialog()), ("about", gui.AboutDialog(win))):
            if dlg is None:
                continue
            dlg.resize(760, 720)
            dlg.show()
            pump(app)
            dlg.grab().save(os.path.join(out_dir, f"{mode}-{name}.png"))
            dlg.close()

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
