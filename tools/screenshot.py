"""Render the window in demo mode to PNG files (used by CI to check the real Windows look)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6 import QtCore  # noqa: E402

from usb_fixer import demo, gui  # noqa: E402


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    app = gui.make_app([])
    win = gui.MainWindow(demo.DemoRunner(), demo=True)
    win.show()
    for _ in range(300):
        app.processEvents()
        if win.result is not None:
            break
        QtCore.QThread.msleep(20)
    for _ in range(20):
        app.processEvents()
    win.grab().save(os.path.join(out_dir, "findings.png"))
    win.tabs.setCurrentIndex(2)
    win.guide_tree.setCurrentItem(win.guide_tree.topLevelItem(1))
    for _ in range(20):
        app.processEvents()
    win.grab().save(os.path.join(out_dir, "guide.png"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
