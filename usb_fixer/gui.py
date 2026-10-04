"""Entry point for the window (kept as a thin module so `from usb_fixer import gui` keeps working)."""

from PySide6 import QtGui  # noqa: F401  (re-exported for tests)
from PySide6.QtCore import Qt  # noqa: F401

from .strings import UI  # noqa: F401
from .ui.window import (  # noqa: F401
    FONT_DIR, FONT_FAMILY, ICON_PNG, PAGES, AboutDialog, ConfirmDialog, MainWindow, make_app, run_gui,
)
