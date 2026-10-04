"""Light / dark themes. One palette dict per theme; the stylesheet is generated from it."""

from __future__ import annotations

LIGHT = {
    "bg": "#f2f4f8", "surface": "#ffffff", "surface2": "#f6f8fb", "border": "#e2e6ee",
    "text": "#18202d", "sub": "#5a6577", "primary": "#2563eb", "primary_hover": "#1d4ed8",
    "on_primary": "#ffffff", "error": "#dc2626", "warn": "#d97706", "info": "#2563eb", "ok": "#16a34a",
    "chip_bg": "#eef2f8", "link": "#1d4ed8", "hero_ok": "#e8f7ee", "hero_warn": "#fdf3e1",
    "hero_error": "#fdecec", "hero_busy": "#e9effc", "disabled": "#aab3c2", "hover": "#eef2f9",
}

DARK = {
    "bg": "#0e131a", "surface": "#161d27", "surface2": "#1b2431", "border": "#2a3443",
    "text": "#e7ecf3", "sub": "#9aa7ba", "primary": "#3b82f6", "primary_hover": "#60a5fa",
    "on_primary": "#ffffff", "error": "#f87171", "warn": "#fbbf24", "info": "#60a5fa", "ok": "#4ade80",
    "chip_bg": "#222c3b", "link": "#8ab9ff", "hero_ok": "#14281d", "hero_warn": "#2d2412",
    "hero_error": "#2e1818", "hero_busy": "#17233b", "disabled": "#4b576a", "hover": "#202a39",
}

THEMES = {"light": LIGHT, "dark": DARK}
CURRENT = {"name": "light", "p": LIGHT}


def set_theme(name: str) -> dict:
    CURRENT["name"] = name
    CURRENT["p"] = THEMES[name]
    return CURRENT["p"]


def color(key: str) -> str:
    return CURRENT["p"][key]


def stylesheet(p: dict) -> str:
    return f"""
* {{ font-family: "Vazirmatn", "Segoe UI", "Tahoma"; font-size: 10.5pt; color: {p['text']}; }}
QMainWindow, QWidget#root, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p['bg']}; }}
QScrollArea {{ border: none; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 4px 8px; }}

QFrame#card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 14px; }}
QFrame#card[sev="error"] {{ border-right: 4px solid {p['error']}; }}
QFrame#card[sev="warn"] {{ border-right: 4px solid {p['warn']}; }}
QFrame#card[sev="info"] {{ border-right: 4px solid {p['info']}; }}
QFrame#card[sev="ok"] {{ border-right: 4px solid {p['ok']}; }}
QFrame#card QLabel {{ background: transparent; }}

QFrame#hero {{ border-radius: 18px; border: 1px solid {p['border']}; }}
QFrame#hero[state="ok"] {{ background: {p['hero_ok']}; }}
QFrame#hero[state="warn"] {{ background: {p['hero_warn']}; }}
QFrame#hero[state="error"] {{ background: {p['hero_error']}; }}
QFrame#hero[state="busy"] {{ background: {p['hero_busy']}; }}
QLabel#headline {{ font-size: 19pt; font-weight: bold; }}
QLabel#sub {{ color: {p['sub']}; }}
QLabel#cardTitle {{ font-weight: bold; font-size: 11.5pt; }}
QLabel#mono {{ font-family: Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace; font-size: 10pt; }}
QLabel#appname {{ font-weight: bold; font-size: 12pt; }}
QLabel#sectionTitle {{ font-weight: bold; font-size: 12pt; }}

QLabel#chip {{ background: {p['chip_bg']}; color: {p['sub']}; border-radius: 9px; padding: 2px 10px; font-size: 9pt; }}
QLabel#chip[kind="fix"] {{ background: {p['ok']}; color: #ffffff; }}
QLabel#chip[kind="manual"] {{ background: {p['chip_bg']}; color: {p['warn']}; }}
QLabel#chip[kind="error"] {{ color: {p['error']}; }}

QPushButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 7px 16px; }}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton:disabled {{ color: {p['disabled']}; }}
QPushButton#primary {{ background: {p['primary']}; color: {p['on_primary']}; border: none; font-weight: bold; padding: 11px 26px; font-size: 11.5pt; border-radius: 12px; }}
QPushButton#primary:hover {{ background: {p['primary_hover']}; }}
QPushButton#primary:disabled {{ background: {p['border']}; color: {p['disabled']}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {p['border']}; }}
QPushButton#link {{ background: transparent; border: none; color: {p['link']}; padding: 4px 6px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#nav {{ background: transparent; border: none; border-radius: 10px; padding: 8px 18px; color: {p['sub']}; }}
QPushButton#nav:hover {{ background: {p['hover']}; }}
QPushButton#nav:checked {{ background: {p['surface']}; color: {p['text']}; font-weight: bold; border: 1px solid {p['border']}; }}
QPushButton#icon {{ padding: 6px 12px; }}

QCheckBox {{ spacing: 8px; background: transparent; }}

QProgressBar {{ background: transparent; border: none; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {p['primary']}; border-radius: 2px; }}

QTreeWidget {{ background: {p['surface']}; border: none; alternate-background-color: {p['surface2']}; outline: none; }}
QTreeWidget::item {{ padding: 7px 4px; }}
QTreeWidget::item:selected {{ background: {p['hover']}; color: {p['text']}; }}
QHeaderView::section {{ background: {p['surface2']}; color: {p['sub']}; border: none; border-bottom: 1px solid {p['border']}; padding: 7px 8px; font-weight: bold; }}

QPlainTextEdit {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 8px; font-family: Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace; font-size: 9.5pt; }}
QDialog {{ background: {p['bg']}; }}
QMessageBox {{ background: {p['bg']}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['disabled']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""
