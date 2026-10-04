"""The main window: a card dashboard with automatic light/dark theme (Qt / PySide6)."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal

from .. import about, backup, devices, fixes, guard, guide, live, report, state, strings
from ..diagnostics import analyze, scan
from ..system import is_admin, relaunch_as_admin
from . import theme
from .widgets import (
    AdviceBox, Card, CheckBox, ControllerCardWidget, DeviceRow, IconBadge, InfoCard, ProblemCard, Section,
    VerdictCard, card_layout, chip, label, link_button, risk_chip,
)

UI = strings.UI
FONT_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"
ICON_PNG = Path(__file__).resolve().parent.parent / "data" / "icon.png"
FONT_FAMILY = "Vazirmatn"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MODES = ("auto", "light", "dark")
MODE_LABEL = {"auto": "تم: خودکار", "light": "تم: روشن", "dark": "تم: تاریک"}
PAGES = ("problems", "live", "devices", "drivers", "system")
PAGE_TITLES = ("مشکلات", "تست زنده", "دستگاه‌ها", "درایورها و BIOS", "سیستم و نگهبان")
SIDE_TEXT = {
    "hardware": "به احتمال زیاد مشکل سخت‌افزاریه (کابل، پورت، برق یا خود دستگاه)",
    "software": "مشکل نرم‌افزاریه و می‌شه از داخل ویندوز درستش کرد",
    "none": "مشکلی دیده نشد",
}


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
    finished = Signal(object, object, object)  # done callback, value, error (busy work)
    side = Signal(object, object, object)  # same, for quiet background work (BIOS check, guard status)
    progress = Signal(float, int)


# ---------------------------------------------------------------- dialogs
class ConfirmDialog(QtWidgets.QDialog):
    """Explains every action in plain words: what it does, risk, can it be undone, and my advice."""

    def __init__(self, parent, findings: list, steps: list):
        super().__init__(parent)
        self.setWindowTitle(UI["confirm_title"])
        self.setMinimumWidth(720)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)

        fix_ids = []
        for f in findings:
            if f.fix_id and f.fix_id not in fix_ids:
                fix_ids.append(f.fix_id)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(IconBadge("info", 40), 0, Qt.AlignTop)
        head.addWidget(label(f"این {fa(len(fix_ids))} کار انجام می‌شه. هر کدوم رو به زبان ساده توضیح دادم:", "cardTitle"), 1)
        lay.addLayout(head)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        body = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 6, 0)
        bl.setSpacing(8)
        self.blocks = []
        for fid in fix_ids:
            info = strings.FIX_INFO[fid]
            card = Card({"safe": "ok", "low": "info", "caution": "warn"}[info["risk"]])
            cl = card_layout(card)
            top = QtWidgets.QHBoxLayout()
            top.addWidget(label(strings.FIXES[fid][0], "cardTitle"), 1)
            top.addWidget(risk_chip(info["risk"]), 0, Qt.AlignTop)
            top.addWidget(chip("قابل برگشت" if info["reversible"] else "برگشت لازم نداره"), 0, Qt.AlignTop)
            cl.addLayout(top)
            cl.addWidget(label(info["plain"]))
            cl.addWidget(label(info["undo_note"], "sub"))
            cl.addWidget(AdviceBox(info["reco"]))
            bl.addWidget(card)
            self.blocks.append(fid)
        bl.addStretch(1)
        scroll.setWidget(body)
        scroll.setMinimumHeight(min(520, 170 * max(1, len(fix_ids))))
        lay.addWidget(scroll, 1)

        has_backup = any(s.backup_reg or s.undo for s in steps)
        safety = ["قبل از شروع، برنامه سعی می‌کنه یه نقطهٔ بازیابی ویندوز بسازه (اگه System Restore روشن باشه)."]
        safety.append("از تنظیمات برق و رجیستری که عوض می‌شن پشتیبان گرفته می‌شه و دکمهٔ «برگرداندن تغییرات» برشون می‌گردونه."
                      if has_backup else "این کارها تنظیمی رو عوض نمی‌کنن که لازم باشه برگرده.")
        lay.addWidget(label("\n".join(safety), "sub"))

        self.tech_btn = QtWidgets.QPushButton("فرمان‌های فنی ▾")
        self.tech_btn.setObjectName("link")
        self.tech_btn.clicked.connect(self._toggle_tech)
        lay.addWidget(self.tech_btn, 0, Qt.AlignRight)
        self.tech = QtWidgets.QPlainTextEdit("\n".join(s.shown[:240] for s in steps))
        self.tech.setReadOnly(True)
        self.tech.setLayoutDirection(Qt.LeftToRight)
        self.tech.setMaximumHeight(140)
        lay.addWidget(self.tech)
        self.tech.setVisible(False)

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

    def _toggle_tech(self) -> None:
        show = self.tech.isHidden()
        self.tech.setVisible(show)
        self.tech_btn.setText("فرمان‌های فنی ▴" if show else "فرمان‌های فنی ▾")


def logo_label(size: int) -> QtWidgets.QLabel:
    """The app logo, sharp on high-DPI screens."""
    lbl = QtWidgets.QLabel()
    lbl.setObjectName("logo")
    ratio = QtWidgets.QApplication.instance().devicePixelRatio() if QtWidgets.QApplication.instance() else 1.0
    pix = QtGui.QPixmap(str(ICON_PNG))
    if not pix.isNull():
        pix = pix.scaled(round(size * ratio), round(size * ratio), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(ratio)
        lbl.setPixmap(pix)
    lbl.setFixedSize(size, size)
    return lbl


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("درباره")
        self.setMinimumWidth(520)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(8)
        lay.addWidget(logo_label(112), 0, Qt.AlignHCenter)
        for text, name in ((about.APP_NAME_FA, "headline"), (about.APP_NAME, "appname"), (f"نسخهٔ {about.VERSION_LABEL}", "sub")):
            lbl = label(text, name)
            lbl.setAlignment(Qt.AlignHCenter)
            lay.addWidget(lbl)
        lay.addSpacing(6)
        lay.addWidget(label(about.credit_line_fa(), "cardTitle"))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(link_button("گیت‌هاب سازنده: github.com/kterfan", about.GITHUB_PROFILE))
        row.addWidget(link_button("کد منبع برنامه", about.GITHUB_REPO))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(6)
        lay.addWidget(label(about.PRIVACY_FA, "sub"))
        lay.addWidget(label("فونت: Vazirmatn (مجوز SIL OFL 1.1). رابط: Qt / PySide6.", "sub"))
        lay.addWidget(label(about.COPYRIGHT, "sub"))
        lay.addStretch(1)
        ok = QtWidgets.QPushButton(UI["btn_ok"])
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok, 0, Qt.AlignLeft)


# ---------------------------------------------------------------- main window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, runner, demo: bool = False, bios_fetch=None, online: bool = True):
        super().__init__()
        self.runner = runner
        self.demo = demo
        self.admin = demo or is_admin()
        self.bios_fetch = bios_fetch
        if demo and bios_fetch is None:
            from ..demo import fake_asus_fetch

            self.bios_fetch = fake_asus_fetch
        self.online = online
        self.settings = make_settings()
        self.mode = self.settings.value("theme", "auto")
        if self.mode not in MODES:
            self.mode = "auto"
        self.result = None
        self.findings: list = []
        self.bios = None
        self.bios_checking = False
        self.guard_installed = None
        self.problem_cards: list = []
        self.device_rows: list = []
        self.controller_cards: list = []
        self.live_result = None
        self.live_running = False
        self.live_stop = False
        self.live_duration = 30.0
        self.live_interval = 1.5
        self.busy = False
        self.notice = ""
        self.bridge = Bridge()
        self.bridge.log.connect(self.log)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.side.connect(lambda done, value, error: done(value, error))
        self.bridge.progress.connect(self._on_live_progress)

        self.setWindowTitle(f"{about.APP_NAME_FA} · {about.APP_NAME} {about.VERSION}" + (" (دمو)" if demo else ""))
        self.resize(1140, 820)
        self.setMinimumSize(920, 660)
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
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(theme.stylesheet(palette))
        pal = app.palette()  # rich-text links (<a>) take their colour from the palette, not the stylesheet
        pal.setColor(QtGui.QPalette.Link, QtGui.QColor(palette["link"]))
        pal.setColor(QtGui.QPalette.LinkVisited, QtGui.QColor(palette["link"]))
        app.setPalette(pal)
        self.theme_btn.setText(MODE_LABEL[self.mode])
        if self.result is not None:
            self.render()
        self.render_live()
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
        v.setContentsMargins(24, 16, 24, 10)
        v.setSpacing(12)

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
        top.addWidget(logo_label(30))
        top.addWidget(label(about.APP_NAME, "appname", wrap=False))
        top.addWidget(chip(f"نسخهٔ {about.VERSION_LABEL}"))
        top.addStretch(1)
        self.about_btn = QtWidgets.QPushButton("درباره")
        self.about_btn.setObjectName("ghost")
        self.about_btn.clicked.connect(self.show_about)
        top.addWidget(self.about_btn)
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
        hv.setContentsMargins(26, 20, 26, 12)
        hv.setSpacing(8)
        hrow = QtWidgets.QHBoxLayout()
        hrow.setSpacing(18)
        self.hero_icon = IconBadge("busy", 64)
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
        self.btn_fix.clicked.connect(lambda: self.on_fix())
        actions.addWidget(self.btn_fix)
        small = QtWidgets.QHBoxLayout()
        small.setSpacing(6)
        self.btn_live = QtWidgets.QPushButton("تست زنده")
        self.btn_scan = QtWidgets.QPushButton(UI["scan"])
        self.btn_undo = QtWidgets.QPushButton("برگرداندن تغییرات")
        self.btn_save = QtWidgets.QPushButton(UI["save_report"])
        for b, fn in ((self.btn_live, lambda: self.go("live")), (self.btn_scan, self.on_rescan),
                      (self.btn_undo, self.on_undo), (self.btn_save, self.on_save)):
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

        # navigation + pages
        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(6)
        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_buttons = []
        self.stack = QtWidgets.QStackedWidget()
        self.page_layouts = []
        for i, name in enumerate(PAGE_TITLES):
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

        # footer: log toggle + credit
        foot = QtWidgets.QHBoxLayout()
        self.log_toggle = QtWidgets.QPushButton(UI["log_header"] + " ▾")
        self.log_toggle.setObjectName("link")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        foot.addWidget(self.log_toggle)
        foot.addStretch(1)
        self.credit = label(f'{about.credit_line_fa()} · <a href="{about.GITHUB_PROFILE}">github.com/kterfan</a> · نسخهٔ {about.VERSION}',
                            "footer", wrap=False, rich=True)
        foot.addWidget(self.credit)
        v.addLayout(foot)
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(130)
        v.addWidget(self.log_box)
        self.log_box.hide()

    def go(self, page: str) -> None:
        i = PAGES.index(page)
        self.nav_buttons[i].setChecked(True)
        self.stack.setCurrentIndex(i)

    # ---------- helpers ----------
    def toggle_log(self) -> None:
        show = self.log_box.isHidden()
        self.log_box.setVisible(show)
        self.log_toggle.setText(UI["log_header"] + (" ▴" if show else " ▾"))

    def log(self, message: str) -> None:
        self.log_box.appendPlainText(message)

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.progress.setVisible(busy or self.live_running)
        for b in (self.btn_scan, self.btn_undo, self.btn_live):
            b.setEnabled(not busy)
        self.update_hero()

    def _ask_fix(self, findings: list, steps: list) -> bool:
        return ConfirmDialog(self, findings, steps).exec() == QtWidgets.QDialog.Accepted

    def make_confirm_dialog(self, findings=None):
        """The dialog "رفع" would show for the currently selected problems (None if nothing is selected)."""
        chosen = list(findings) if findings is not None else self._checked_findings()
        steps = fixes.collect_steps(chosen)
        return ConfirmDialog(self, chosen, steps) if steps else None

    def _ask(self, title: str, text: str) -> bool:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes = box.addButton(UI["btn_yes"], QtWidgets.QMessageBox.AcceptRole)
        box.addButton(UI["btn_cancel"], QtWidgets.QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

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

    def _run_side(self, work, done) -> None:
        def target():
            try:
                self.bridge.side.emit(done, work(), None)
            except Exception as exc:
                self.bridge.side.emit(done, None, exc)

        threading.Thread(target=target, daemon=True).start()

    def _on_finished(self, done, value, error) -> None:
        self._set_busy(False)
        done(value, error)

    def _log_cb(self):
        return lambda m: self.bridge.log.emit(m)

    @staticmethod
    def _clear(layout: QtWidgets.QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    # ---------- scan ----------
    def on_rescan(self) -> None:
        self.notice = ""
        self.start_scan()

    def start_scan(self) -> None:
        applied = state.applied_ids()
        self._run_bg(lambda: scan(self.runner, applied=applied), self.on_scan_done)

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
        if self.bios is not None:  # keep the online answer from the previous scan
            self._reanalyze()
        self.render()
        self.update_hero()
        for w in result.snapshot.warnings:
            self.log("⚠ " + w)
        if self.online and self.bios is None and not self.bios_checking:
            self.start_bios_check()
        self._run_side(lambda: guard.is_installed(self.runner), self._on_guard_status)

    def _reanalyze(self) -> None:
        self.result.bios = self.bios
        self.result.findings = self.findings = analyze(
            self.result.snapshot, bios=self.bios, applied=state.applied_ids()
        )

    def start_bios_check(self) -> None:
        from .. import bios as bios_mod

        self.bios_checking = True
        system = self.result.snapshot.system
        self._run_side(lambda: bios_mod.check_latest(system, self.bios_fetch), self._on_bios_done)

    def _on_bios_done(self, value, error) -> None:
        self.bios_checking = False
        if error or value is None:
            self.log(f"چک آنلاین BIOS انجام نشد: {error}")
            return
        self.bios = value
        self.log(f"BIOS: {value.status} (نصب‌شده {value.installed}، آخرین {value.latest or '?'}) {value.reason}".strip())
        if self.result is not None:
            self._reanalyze()
            self.render()
            self.update_hero()

    def _on_guard_status(self, value, error) -> None:
        self.guard_installed = bool(value) if not error else None
        if self.result is not None:
            self.render_system()

    # ---------- rendering ----------
    def render(self) -> None:
        self.render_problems()
        self.render_devices()
        self.render_drivers()
        self.render_system()

    def render_problems(self) -> None:
        lay = self.page_layouts[0]
        old = {c.finding.key + str(c.finding.targets): c.check.isChecked() for c in self.problem_cards}
        self._clear(lay)
        self.problem_cards = []
        if not self.findings:
            ok = Card("ok")
            row = QtWidgets.QHBoxLayout(ok)
            row.setContentsMargins(18, 16, 18, 16)
            row.addWidget(IconBadge("ok", 40))
            row.addWidget(label(UI["no_findings"] + " برای امتحان یه دستگاه خاص، «تست زنده» رو بزن."), 1)
            lay.addWidget(ok)
        for f in self.findings:
            key = f.key + str(f.targets)
            checked = old.get(key, bool(f.fix_id) and fixes.DEFAULT_CHECKED.get(f.fix_id, False))
            card = ProblemCard(f, checked)
            card.toggled.connect(self.update_hero)
            lay.addWidget(card)
            self.problem_cards.append(card)
        extra = fixes.reset_stack_finding(self.result.snapshot)
        if extra is not None:
            lay.addWidget(Section("ابزار اضافه", "اگه چند دستگاه با هم مشکل دارن یا بعد از Sleep هیچ USBای کار نمی‌کنه."))
            key = extra.key + str(extra.targets)
            card = ProblemCard(extra, old.get(key, False))
            card.toggled.connect(self.update_hero)
            lay.addWidget(card)
            self.problem_cards.append(card)
        lay.addStretch(1)

    def render_devices(self) -> None:
        lay = self.page_layouts[2]
        self._clear(lay)
        self.device_rows = []
        items = devices.build(self.result.snapshot)
        groups = (
            ("yours", "دستگاه‌های وصل‌شده", "چیزهایی که خودت وصل کردی"),
            ("system", "هاب‌ها و بخش‌های سیستمی", "این‌ها بخشی از خود کامپیوتر هستن؛ معمولاً لازم نیست کاری باهاشون داشته باشی"),
            ("past", "قبلاً وصل بوده، الان نیست", "فقط ردشون تو ویندوز مونده؛ مشکلی ایجاد نمی‌کنن"),
        )
        for gid, title, sub in groups:
            members = [d for d in items if d.group == gid]
            if not members:
                continue
            bad = sum(1 for d in members if d.status == "error")
            lay.addWidget(Section(f"{title} ({fa(len(members))})" + (f"، {fa(bad)} مورد مشکل‌دار" if bad else ""), sub))
            for d in members:
                row = DeviceRow(d)
                row.tech.copied.connect(self.on_copy)
                lay.addWidget(row)
                self.device_rows.append(row)
        if not items:
            lay.addWidget(label("هیچ دستگاه USBای پیدا نشد.", "sub"))
        lay.addStretch(1)

    def render_drivers(self) -> None:
        lay = self.page_layouts[3]
        self._clear(lay)
        rep = guide.build_report(self.result.snapshot.system, self.bios)
        self.driver_report = rep
        lay.addWidget(VerdictCard(rep.verdict_ok, rep.verdict_title, rep.verdict_text, rep.actions))
        if rep.controllers:
            lay.addWidget(Section("کنترلرهای USB کامپیوترت", "هر کدوم یه گروه از پورت‌ها رو می‌گردونه"))
        self.controller_cards = []
        for c in rep.controllers:
            w = ControllerCardWidget(c)
            w.copied.connect(self.on_copy)
            lay.addWidget(w)
            self.controller_cards.append(w)
        lay.addWidget(Section("BIOS مادربرد"))
        checking = self.bios_checking and self.bios is None
        bios_card = VerdictCard(rep.bios_ok is not False, rep.bios_title,
                                "در حال چک کردن سایت سازنده…" if checking else rep.bios_text,
                                links=rep.bios_links)
        lay.addWidget(bios_card)
        lay.addStretch(1)

    def render_system(self) -> None:
        lay = self.page_layouts[4]
        self._clear(lay)
        s = self.result.snapshot.system
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
        lay.addWidget(self._guard_card())
        lay.addStretch(1)

    def _guard_card(self) -> QtWidgets.QWidget:
        card = Card("ok" if self.guard_installed else "info")
        cl = card_layout(card)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(IconBadge("ok" if self.guard_installed else "info", 36), 0, Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        status = {True: "روشنه", False: "خاموشه", None: "نامعلوم"}[self.guard_installed]
        col.addWidget(label(f"نگهبان ماندگاری: {status}", "cardTitle"))
        col.addWidget(label(
            "بعضی رفع‌ها ممکنه بعد از آپدیت ویندوز یا با ابزار برق سازنده برگردن. نگهبان موقع ورود به ویندوز چک می‌کنه "
            "و فقط همون تنظیم‌هایی رو که با این برنامه درست کردی، اگه برگشته باشن دوباره درست می‌کنه. "
            "هر وقت خواستی خاموشش کن.", "sub"))
        applied = sorted(state.applied_ids())
        if applied:
            col.addWidget(label("رفع‌های ثبت‌شده: " + "، ".join(strings.FIXES[a][0] for a in applied if a in strings.FIXES), "sub"))
        row.addLayout(col, 1)
        cl.addLayout(row)
        problem = "" if self.demo else guard.location_problem(guard.exe_path())
        self.guard_btn = QtWidgets.QPushButton("خاموش کردن نگهبان" if self.guard_installed else "روشن کردن نگهبان")
        self.guard_btn.setObjectName("ghost")
        self.guard_btn.clicked.connect(self.on_guard_toggle)
        self.guard_btn.setEnabled(not problem or bool(self.guard_installed))
        cl.addWidget(self.guard_btn, 0, Qt.AlignLeft)
        if problem and not self.guard_installed:
            cl.addWidget(label(problem, "sub"))
        return card

    # ---------- live test ----------
    def render_live(self) -> None:
        lay = self.page_layouts[1]
        self._clear(lay)
        intro = Card("info")
        il = card_layout(intro)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(IconBadge("busy" if self.live_running else "info", 44), 0, Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        col.addWidget(label("تست زنده: ببینیم موقع وصل کردن دستگاه دقیقاً چی می‌شه", "cardTitle"))
        col.addWidget(label(
            "۱) اگه دستگاه وصله، جداش کن.  ۲) «شروع تست» رو بزن.  ۳) ظرف ۳۰ ثانیه دستگاه رو وصل کن.\n"
            "برنامه می‌بینه ویندوز چه واکنشی نشون داد و می‌گه مشکل از سخت‌افزاره (کابل/پورت/دستگاه) یا از ویندوز.", "sub"))
        row.addLayout(col, 1)
        il.addLayout(row)
        self.live_status = label("", "sub")
        il.addWidget(self.live_status)
        self.live_btn = QtWidgets.QPushButton("توقف" if self.live_running else "شروع تست")
        self.live_btn.setObjectName("primary")
        self.live_btn.clicked.connect(self.on_live_button)
        il.addWidget(self.live_btn, 0, Qt.AlignLeft)
        lay.addWidget(intro)

        r = self.live_result
        if r is not None and not self.live_running:
            ok = r.kind == "ok"
            card = Card("ok" if ok else ("warn" if r.side == "hardware" else "error"))
            cl = card_layout(card)
            top = QtWidgets.QHBoxLayout()
            top.addWidget(IconBadge("ok" if ok else "warn", 44), 0, Qt.AlignTop)
            col = QtWidgets.QVBoxLayout()
            col.addWidget(label(r.title, "cardTitle"))
            col.addWidget(chip(SIDE_TEXT[r.side], "fix" if r.side != "hardware" else "manual"), 0, Qt.AlignRight)
            col.addWidget(label(r.explanation))
            top.addLayout(col, 1)
            cl.addLayout(top)
            if r.steps:
                cl.addWidget(AdviceBox("\n".join(f"{fa(i + 1)}) {s}" for i, s in enumerate(r.steps))))
            buttons = QtWidgets.QHBoxLayout()
            usable = self._live_fixes(r)
            if usable:
                b = QtWidgets.QPushButton("رفع پیشنهادی")
                b.setObjectName("primary")
                b.clicked.connect(lambda: self.on_fix(usable))
                buttons.addWidget(b)
            again = QtWidgets.QPushButton("دوباره تست کن")
            again.setObjectName("ghost")
            again.clicked.connect(self.start_live)
            buttons.addWidget(again)
            buttons.addStretch(1)
            cl.addLayout(buttons)
            lay.addWidget(card)
            self.live_result_card = card
        lay.addStretch(1)

    def _live_fixes(self, r) -> list:
        """Fixes offered by the live test, using the current scan's data where a fix needs it."""
        out = []
        current = {f.fix_id: f for f in self.findings if f.fix_id}
        for f in r.fixes:
            if f.fix_id == "disable_suspend":
                if "disable_suspend" in current:  # only if it is actually on
                    out.append(current["disable_suspend"])
            else:
                out.append(f)
        return out

    def on_live_button(self) -> None:
        if self.live_running:
            self.live_stop = True
        else:
            self.start_live()

    def start_live(self) -> None:
        if self.live_running:
            return
        self.go("live")
        self.live_running = True
        self.live_stop = False
        self.live_result = None
        self.render_live()
        self.progress.show()
        self.live_status.setText("منتظرم دستگاه رو وصل کنی…")

        def work():
            return live.run_test(
                self.runner, self.live_duration, self.live_interval,
                on_progress=lambda t, n: self.bridge.progress.emit(t, n),
                should_stop=lambda: self.live_stop,
            )

        self._run_side(work, self._on_live_done)

    def _on_live_progress(self, elapsed: float, count: int) -> None:
        if not self.live_running or not hasattr(self, "live_status"):
            return
        left = max(0, int(self.live_duration - elapsed))
        text = f"منتظرم دستگاه رو وصل کنی… {fa(left)} ثانیه مونده"
        if count:
            text = f"یه دستگاه دیده شد؛ صبر کن ویندوز راه‌اندازیش کنه… ({fa(count)} بخش)"
        self.live_status.setText(text)

    def _on_live_done(self, value, error) -> None:
        self.live_running = False
        self.progress.setVisible(self.busy)
        if error:
            self.log(f"تست زنده انجام نشد: {error}")
        self.live_result = value
        self.render_live()
        if value is not None:
            self.log(f"تست زنده: {value.title}")

    # ---------- hero ----------
    def update_hero(self) -> None:
        if self.busy and self.result is None:
            state_, kind, head, stats = "busy", "busy", "در حال بررسی سیستم…", "چند ثانیه صبر کن."
        elif self.busy:
            state_, kind, head, stats = "busy", "busy", "در حال انجام کار…", "لطفاً پنجره رو نبند."
        elif self.result is None:
            state_, kind, head, stats = "busy", "busy", "آماده برای اسکن", ""
        else:
            counts = {k: sum(1 for f in self.findings if f.severity == k) for k in ("error", "warn", "info")}
            if counts["error"]:
                state_, kind, head = "error", "error", f"{fa(counts['error'])} مشکل مهم پیدا شد"
            elif counts["warn"]:
                state_, kind, head = "warn", "warn", f"{fa(counts['warn'])} مورد قابل بهبود پیدا شد"
            else:
                state_, kind, head = "ok", "ok", "مشکلی پیدا نشد؛ همه‌چیز سالم به نظر می‌رسه"
            bits = [f"{fa(counts[k])} {strings.SEVERITY[k]}" for k in ("error", "warn", "info") if counts[k]]
            stats = "، ".join(bits)
        self.hero.setProperty("state", state_)
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

    def on_fix(self, findings=None) -> None:
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        chosen = list(findings) if findings is not None else self._checked_findings()
        steps = fixes.collect_steps(chosen)
        if not steps:
            self._info(UI["nothing_selected"])
            return
        if not self._ask_fix(chosen, steps):
            return
        log = self._log_cb()
        self._run_bg(lambda: fixes.execute(steps, self.runner, log), self.on_fix_done)

    def on_fix_done(self, result, error) -> None:
        if error:
            self.log(f"{UI['scan_failed']} {error}")
            self.notice = f"{UI['scan_failed']} {error}"
            self.update_hero()
            return
        rp = "نقطهٔ بازیابی ساخته شد." if result.restore_point else "نقطهٔ بازیابی ساخته نشد (System Restore خاموشه یا اخیراً ساخته شده)."
        self.notice = (f"انجام شد: {fa(result.ok)} مورد موفق، {fa(result.failed)} ناموفق. {rp} "
                       "برای اطمینان، دستگاهت رو با «تست زنده» امتحان کن.")
        self.log(self.notice + f" پشتیبان: {result.backup_dir}")
        self.start_scan()

    def on_undo(self) -> None:
        directory = backup.latest_undo_dir()
        if directory is None:
            self._info(UI["undo_none"])
            return
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        if not self._ask(UI["confirm_title"], UI["undo_confirm"]):
            return
        log = self._log_cb()

        def finished(failed, error):
            self.notice = UI["undone"] if not error else f"{UI['scan_failed']} {error}"
            self.log(self.notice)
            self.start_scan()

        self._run_bg(lambda: backup.undo(directory, self.runner, log), finished)

    def on_guard_toggle(self) -> None:
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        if self.guard_installed:
            cmd, msg = guard.remove_cmd(), "نگهبان خاموش شد."
        else:
            exe = guard.exe_path() or sys.executable
            cmd, msg = guard.install_cmd(exe), "نگهبان روشن شد؛ از ورود بعدی به ویندوز کارش رو شروع می‌کنه."

        def done(res, error):
            if error or not res.ok:
                self._info(f"انجام نشد: {(error or res.err or res.out)}", warn=True)
            else:
                self.notice = msg
                self.log(msg)
            self._run_side(lambda: guard.is_installed(self.runner), self._on_guard_status)
            self.update_hero()

        self._run_bg(lambda: self.runner(cmd), done)

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
    app.setApplicationName(about.APP_NAME)
    app.setApplicationVersion(about.VERSION)
    load_fonts()
    app.setFont(QtGui.QFont(FONT_FAMILY, 10))
    if ICON_PNG.is_file():
        app.setWindowIcon(QtGui.QIcon(str(ICON_PNG)))  # title bar, taskbar, dialogs
    return app


def run_gui(runner, demo: bool = False) -> None:
    app = make_app()
    win = MainWindow(runner, demo)
    win.show()
    app.exec()
