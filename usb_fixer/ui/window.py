"""The main window: a card dashboard with automatic light/dark theme (Qt / PySide6)."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal

from .. import backup, fixes, guide, report, strings
from ..diagnostics import scan
from ..system import is_admin, relaunch_as_admin
from . import theme, widgets
from .widgets import Card, CheckBox, IconBadge, InfoCard, ProblemCard, DriverCard, card_layout, label

UI = strings.UI
FONT_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"
FONT_FAMILY = "Vazirmatn"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MODES = ("auto", "light", "dark")
MODE_LABEL = {"auto": "تم: خودکار", "light": "تم: روشن", "dark": "تم: تاریک"}


def fa(n: int) -> str:
    return str(n).translate(FA_DIGITS)


def make_settings() -> QtCore.QSettings:
    path = os.environ.get("USB_FIXER_SETTINGS_PATH")
    if path:
        return QtCore.QSettings(path, QtCore.QSettings.IniFormat)
    return QtCore.QSettings("UsbFixer", "UsbFixer")


class Bridge(QtCore.QObject):
    """Carries results from worker threads back to the GUI thread."""

    log = Signal(str)
    finished = Signal(object, object, object)  # done callback, value, error


class ConfirmDialog(QtWidgets.QDialog):
    def __init__(self, parent, title: str, intro: str, lines: list):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconBadge("warn", 40), 0, Qt.AlignTop)
        head.addWidget(label(intro, "cardTitle"), 1)
        lay.addLayout(head)
        box = QtWidgets.QPlainTextEdit("\n".join(lines))
        box.setReadOnly(True)
        box.setLayoutDirection(Qt.LeftToRight)
        box.setMinimumHeight(180)
        lay.addWidget(box)
        lay.addWidget(label(UI["confirm_question"], "sub"))
        btns = QtWidgets.QHBoxLayout()
        yes = QtWidgets.QPushButton(UI["btn_yes"])
        yes.setObjectName("primary")
        no = QtWidgets.QPushButton(UI["btn_cancel"])
        no.setObjectName("ghost")
        yes.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        btns.addWidget(yes)
        btns.addWidget(no)
        btns.addStretch(1)
        lay.addLayout(btns)
        yes.setDefault(True)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, runner, demo: bool = False):
        super().__init__()
        self.runner = runner
        self.demo = demo
        self.admin = demo or is_admin()
        self.settings = make_settings()
        self.mode = self.settings.value("theme", "auto")
        if self.mode not in MODES:
            self.mode = "auto"
        self.result = None
        self.findings: list = []
        self.problem_cards: list = []
        self.driver_cards: list = []
        self.cards: list = []
        self.busy = False
        self.notice = ""
        self.bridge = Bridge()
        self.bridge.log.connect(self.log)
        self.bridge.finished.connect(self._on_finished)

        self.setWindowTitle(UI["app_title"] + (" (دمو)" if demo else ""))
        self.resize(1120, 800)
        self.setMinimumSize(900, 640)
        self._build()
        hints = QtWidgets.QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.apply_theme())
        self.apply_theme()
        self.start_scan()

    # ---------- theme ----------
    def effective_theme(self) -> str:
        if self.mode in ("light", "dark"):
            return self.mode
        hints = QtWidgets.QApplication.instance().styleHints()
        try:
            return "dark" if hints.colorScheme() == Qt.ColorScheme.Dark else "light"
        except AttributeError:
            return "light"

    def apply_theme(self) -> None:
        palette = theme.set_theme(self.effective_theme())
        QtWidgets.QApplication.instance().setStyleSheet(theme.stylesheet(palette))
        self.theme_btn.setText(MODE_LABEL[self.mode])
        if self.result is not None:
            self.render()
        self.update_hero()
        for w in self.findChildren(IconBadge) + self.findChildren(CheckBox):
            w.update()

    def cycle_theme(self) -> None:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self.settings.setValue("theme", self.mode)
        self.apply_theme()

    # ---------- layout ----------
    def _build(self) -> None:
        root = QtWidgets.QWidget(objectName="root")
        self.setCentralWidget(root)
        v = QtWidgets.QVBoxLayout(root)
        v.setContentsMargins(24, 18, 24, 14)
        v.setSpacing(14)

        if not self.admin:
            banner = Card("warn")
            bl = QtWidgets.QHBoxLayout(banner)
            bl.setContentsMargins(16, 10, 16, 10)
            bl.addWidget(IconBadge("warn", 30))
            bl.addWidget(label(UI["admin_banner"]), 1)
            b = QtWidgets.QPushButton(UI["admin_button"])
            b.clicked.connect(self.on_admin)
            bl.addWidget(b)
            v.addWidget(banner)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(label("USB Fixer", "appname", wrap=False))
        top.addStretch(1)
        self.theme_btn = QtWidgets.QPushButton("")
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.cycle_theme)
        top.addWidget(self.theme_btn)
        v.addLayout(top)

        # hero
        self.hero = QtWidgets.QFrame(objectName="hero")
        self.hero.setAttribute(Qt.WA_StyledBackground, True)
        hv = QtWidgets.QVBoxLayout(self.hero)
        hv.setContentsMargins(26, 22, 26, 14)
        hv.setSpacing(10)
        hrow = QtWidgets.QHBoxLayout()
        hrow.setSpacing(18)
        self.hero_icon = IconBadge("busy", 68)
        hrow.addWidget(self.hero_icon, 0, Qt.AlignTop)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(4)
        self.headline = label("", "headline")
        self.stats = label("", "sub")
        self.sysline = label("", "sub")
        self.notice_label = label("", "sub")
        for w in (self.headline, self.stats, self.sysline, self.notice_label):
            text.addWidget(w)
        self.notice_label.hide()
        text.addStretch(1)
        hrow.addLayout(text, 1)
        actions = QtWidgets.QVBoxLayout()
        actions.setSpacing(8)
        self.btn_fix = QtWidgets.QPushButton(UI["fix"])
        self.btn_fix.setObjectName("primary")
        self.btn_fix.setCursor(Qt.PointingHandCursor)
        self.btn_fix.clicked.connect(self.on_fix)
        actions.addWidget(self.btn_fix)
        small = QtWidgets.QHBoxLayout()
        small.setSpacing(6)
        self.btn_scan = QtWidgets.QPushButton(UI["scan"])
        self.btn_undo = QtWidgets.QPushButton("برگرداندن تغییرات")
        self.btn_save = QtWidgets.QPushButton(UI["save_report"])
        for b, fn in ((self.btn_scan, self.on_rescan), (self.btn_undo, self.on_undo), (self.btn_save, self.on_save)):
            b.setObjectName("ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            small.addWidget(b)
        actions.addLayout(small)
        hrow.addLayout(actions)
        hv.addLayout(hrow)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        hv.addWidget(self.progress)
        self.progress.hide()
        v.addWidget(self.hero)

        # navigation
        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(6)
        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_buttons = []
        self.stack = QtWidgets.QStackedWidget()
        self.page_layouts = []
        names = (UI["tab_findings"], UI["tab_devices"], UI["tab_guide"], UI["tab_system"])
        for i, name in enumerate(names):
            b = QtWidgets.QPushButton(name)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            nav.addWidget(b)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            body = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(body)
            lay.setContentsMargins(0, 4, 6, 4)
            lay.setSpacing(10)
            scroll.setWidget(body)
            self.stack.addWidget(scroll)
            self.page_layouts.append(lay)
        nav.addStretch(1)
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)
        self.nav_buttons[0].setChecked(True)
        v.addLayout(nav)
        v.addWidget(self.stack, 1)

        # log
        self.log_toggle = QtWidgets.QPushButton(UI["log_header"] + " ▾")
        self.log_toggle.setObjectName("link")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        v.addWidget(self.log_toggle, 0, Qt.AlignRight)
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(130)
        v.addWidget(self.log_box)
        self.log_box.hide()

    # ---------- helpers ----------
    def toggle_log(self) -> None:
        show = not self.log_box.isVisible()
        self.log_box.setVisible(show)
        self.log_toggle.setText(UI["log_header"] + (" ▴" if show else " ▾"))

    def log(self, message: str) -> None:
        self.log_box.appendPlainText(message)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.progress.setVisible(busy)
        for b in (self.btn_scan, self.btn_undo):
            b.setEnabled(not busy)
        self.update_hero()

    def _ask(self, title: str, intro: str, lines: list) -> bool:
        return ConfirmDialog(self, title, intro, lines).exec() == QtWidgets.QDialog.Accepted

    def _info(self, text: str, warn: bool = False) -> None:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning if warn else QtWidgets.QMessageBox.Information)
        box.setWindowTitle(UI["app_title"])
        box.setText(text)
        box.addButton(UI["btn_ok"], QtWidgets.QMessageBox.AcceptRole)
        box.exec()

    def _run_bg(self, work, done) -> None:
        def target():
            try:
                self.bridge.finished.emit(done, work(), None)
            except Exception as exc:  # shown to the user, not swallowed
                self.bridge.finished.emit(done, None, exc)

        self._set_busy(True)
        threading.Thread(target=target, daemon=True).start()

    def _on_finished(self, done, value, error) -> None:
        self._set_busy(False)
        done(value, error)

    def _log_cb(self):
        return lambda m: self.bridge.log.emit(m)

    # ---------- scan / render ----------
    def on_rescan(self) -> None:
        self.notice = ""
        self.start_scan()

    def start_scan(self) -> None:
        self._run_bg(lambda: scan(self.runner), self.on_scan_done)

    def on_scan_done(self, result, error) -> None:
        if error:
            msg = f"{UI['scan_failed']} {error}"
            self.log(msg)
            self.notice = msg
            self.update_hero()
            self._info(msg, warn=True)
            return
        self.result = result
        self.findings = result.findings
        self.cards = guide.build_cards(result.snapshot.system)
        self.render()
        self.update_hero()
        for w in result.snapshot.warnings:
            self.log("⚠ " + w)

    def _clear(self, layout: QtWidgets.QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def render(self) -> None:
        snap = self.result.snapshot
        old = {c.finding.key + str(c.finding.targets): c.check.isChecked() for c in self.problem_cards}

        # problems
        lay = self.page_layouts[0]
        self._clear(lay)
        self.problem_cards = []
        if not self.findings:
            ok = Card("ok")
            row = QtWidgets.QHBoxLayout(ok)
            row.setContentsMargins(18, 16, 18, 16)
            row.addWidget(IconBadge("ok", 40))
            row.addWidget(label(UI["no_findings"]), 1)
            lay.addWidget(ok)
        for f in self.findings:
            key = f.key + str(f.targets)
            checked = old.get(key, bool(f.fix_id) and fixes.DEFAULT_CHECKED.get(f.fix_id, False))
            card = ProblemCard(f, checked)
            card.toggled.connect(self.update_hero)
            lay.addWidget(card)
            self.problem_cards.append(card)
        lay.addStretch(1)

        # devices
        lay = self.page_layouts[1]
        self._clear(lay)
        card = Card()
        cl = card_layout(card)
        cl.setContentsMargins(6, 6, 6, 6)
        self.device_tree = QtWidgets.QTreeWidget()
        self.device_tree.setHeaderLabels([UI["col_name"], UI["col_status"], UI["col_id"]])
        self.device_tree.setRootIsDecorated(False)
        self.device_tree.setAlternatingRowColors(True)
        self.device_tree.setColumnWidth(0, 470)
        self.device_tree.setColumnWidth(1, 100)
        self.device_tree.setMinimumHeight(360)
        for d in snap.devices:
            status = f"خطا {d.error_code}" if d.has_error else ("غایب" if d.is_ghost else d.status)
            it = QtWidgets.QTreeWidgetItem([d.name, status, d.instance_id])
            if d.has_error:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(theme.color("error"))))
            elif d.is_ghost:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(theme.color("sub"))))
            self.device_tree.addTopLevelItem(it)
        cl.addWidget(self.device_tree)
        lay.addWidget(card)
        lay.addStretch(1)

        # drivers guide
        lay = self.page_layouts[2]
        self._clear(lay)
        lay.addWidget(label(UI["guide_intro"] + " " + UI["guide_tip"], "sub"))
        self.driver_cards = []
        for c in self.cards:
            dc = DriverCard(c)
            dc.copied.connect(self.on_copy)
            lay.addWidget(dc)
            self.driver_cards.append(dc)
        lay.addStretch(1)

        # system
        lay = self.page_layouts[3]
        self._clear(lay)
        s = snap.system
        lay.addWidget(InfoCard("مادربرد و BIOS", [
            (UI["sys_board"], f"{s.board_manufacturer} {s.board_product} {s.board_version}".strip()),
            ("BIOS", f"{s.bios_vendor} {s.bios_version}".strip()),
            ("تاریخ BIOS", s.bios_date.isoformat() if s.bios_date else ""),
        ]))
        lay.addWidget(InfoCard("دستگاه و ویندوز", [
            (UI["sys_model"], f"{s.system_manufacturer} {s.system_model}".strip() + (" (لپ‌تاپ)" if s.is_laptop else "")),
            (UI["sys_cpu"], s.cpu),
            (UI["sys_os"], f"{s.os_caption} (build {s.os_build})"),
        ]))
        lay.addWidget(InfoCard(UI["sys_controllers"], [
            (c.vendor, f"{c.name} — {c.driver_provider} {c.driver_version}".strip(" —")) for c in s.controllers
        ] or [("—", "")]))
        lay.addStretch(1)

    def update_hero(self) -> None:
        if self.busy and self.result is None:
            state, kind, head = "busy", "busy", "در حال بررسی سیستم…"
            stats = "چند ثانیه صبر کن."
        elif self.busy:
            state, kind, head = "busy", "busy", "در حال انجام کار…"
            stats = "لطفاً پنجره رو نبند."
        elif self.result is None:
            state, kind, head, stats = "busy", "busy", "آماده برای اسکن", ""
        else:
            counts = {k: sum(1 for f in self.findings if f.severity == k) for k in ("error", "warn", "info")}
            if counts["error"]:
                state, kind, head = "error", "error", f"{fa(counts['error'])} مشکل مهم پیدا شد"
            elif counts["warn"]:
                state, kind, head = "warn", "warn", f"{fa(counts['warn'])} مورد قابل بهبود پیدا شد"
            else:
                state, kind, head = "ok", "ok", "مشکلی پیدا نشد؛ همه‌چیز سالم به نظر می‌رسه"
            bits = [f"{fa(counts[k])} {strings.SEVERITY[k]}" for k in ("error", "warn", "info") if counts[k]]
            stats = " · ".join(bits)
        self.hero.setProperty("state", state)
        self.hero.style().unpolish(self.hero)
        self.hero.style().polish(self.hero)
        self.hero_icon.set_kind(kind)
        self.headline.setText(head)
        self.stats.setText(stats)
        if self.result is not None:
            s = self.result.snapshot.system
            self.sysline.setText(f"{s.board_manufacturer} {s.board_product}  ·  BIOS {s.bios_version}  ·  {s.cpu}".strip(" ·"))
        self.sysline.setVisible(bool(self.sysline.text()))
        self.notice_label.setText(self.notice)
        self.notice_label.setVisible(bool(self.notice))

        n = len(self._checked_findings())
        self.btn_fix.setEnabled(not self.busy and n > 0)
        self.btn_fix.setText(f"رفع {fa(n)} مورد انتخاب‌شده" if n else "موردی برای رفع انتخاب نشده")

    # ---------- actions ----------
    def _checked_findings(self) -> list:
        return [c.finding for c in self.problem_cards if c.finding.fix_id and c.check.isChecked()]

    def on_copy(self, text: str) -> None:
        QtWidgets.QApplication.clipboard().setText(text)
        self.log(f"{UI['copied']} {text}")
        self.notice = f"{UI['copied']} {text}"
        self.update_hero()

    def on_admin(self) -> None:
        if relaunch_as_admin():
            self.close()

    def on_fix(self) -> None:
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        steps = fixes.collect_steps(self._checked_findings())
        if not steps:
            self._info(UI["nothing_selected"])
            return
        lines = [s.shown[:220] for s in steps]
        intro = f"{fa(len(steps))} کار انجام می‌شه. قبلش نقطهٔ بازیابی ویندوز و پشتیبان تنظیمات ساخته می‌شه."
        if not self._ask(UI["confirm_title"], intro, lines):
            return
        log = self._log_cb()
        self._run_bg(lambda: fixes.execute(steps, self.runner, log), self.on_fix_done)

    def on_fix_done(self, result, error) -> None:
        if error:
            self.log(f"{UI['scan_failed']} {error}")
            self.notice = f"{UI['scan_failed']} {error}"
            self.update_hero()
            return
        self.notice = f"انجام شد: {fa(result.ok)} مورد موفق، {fa(result.failed)} ناموفق. پشتیبان: {result.backup_dir}"
        self.log(self.notice)
        self.start_scan()

    def on_undo(self) -> None:
        directory = backup.latest_undo_dir()
        if directory is None:
            self._info(UI["undo_none"])
            return
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        if not self._ask(UI["confirm_title"], UI["undo_confirm"], [str(directory)]):
            return
        log = self._log_cb()

        def finished(failed, error):
            self.notice = UI["undone"] if not error else f"{UI['scan_failed']} {error}"
            self.log(self.notice)
            self.start_scan()

        self._run_bg(lambda: backup.undo(directory, self.runner, log), finished)

    def on_save(self) -> None:
        if self.result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, UI["save_report"], "usb-report.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report.build_report(self.result))
            self.log(f"{UI['report_saved']} {path}")
            self.notice = f"{UI['report_saved']} {path}"
            self.update_hero()


def load_fonts() -> bool:
    """Register the bundled Vazirmatn font (good Persian + Latin). Falls back to system fonts if missing."""
    loaded = False
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        loaded = QtGui.QFontDatabase.addApplicationFont(str(ttf)) >= 0 or loaded
    return loaded


def make_app(argv=None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    load_fonts()
    app.setFont(QtGui.QFont(FONT_FAMILY, 10))
    return app


def run_gui(runner, demo: bool = False) -> None:
    app = make_app()
    win = MainWindow(runner, demo)
    win.show()
    app.exec()
