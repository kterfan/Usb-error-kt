"""The window (Qt / PySide6, which does proper right-to-left and mixed Persian/English text).

Scan and fixes run in a worker thread; results come back through Qt signals.
"""

from __future__ import annotations

import html
import sys
import threading

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal

from . import backup, fixes, guide, report, strings
from .diagnostics import scan
from .system import is_admin, relaunch_as_admin

UI = strings.UI
SEV_COLOR = {"error": "#c62828", "warn": "#e65100", "info": "#1565c0"}
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

STYLE = """
* { font-size: 10.5pt; }
QPushButton { padding: 6px 14px; border: 1px solid #b0b7c3; border-radius: 5px; background: #f6f7f9; }
QPushButton:hover { background: #eaeef5; }
QPushButton:disabled { color: #9aa0a6; background: #f1f1f1; }
QPushButton#primary { background: #1565c0; color: white; border-color: #0d47a1; font-weight: bold; }
QPushButton#primary:disabled { background: #9fb8d8; border-color: #9fb8d8; }
QTreeWidget { border: 1px solid #c9ced6; alternate-background-color: #f7f9fc; }
QTreeWidget::item { padding: 5px 2px; }
QTextBrowser, QPlainTextEdit { border: 1px solid #c9ced6; background: white; }
QTabBar::tab { padding: 7px 16px; }
QFrame#banner { background: #fff3cd; border: 1px solid #f0d98a; border-radius: 5px; }
QLabel#summary { font-size: 13pt; font-weight: bold; }
QLabel#sysline { color: #555; }
"""


def fa(n: int) -> str:
    return str(n).translate(FA_DIGITS)


def esc(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def block(text: str) -> str:
    """Paragraphs with an explicit RTL base direction (a line that begins with Latin text stays right-aligned)."""
    return "".join(f'<p dir="rtl" style="margin:2px 0">{html.escape(line)}</p>' for line in text.split("\n") if line.strip())


def bullets(items) -> str:
    return "<ul>" + "".join(f'<li dir="rtl">{i}</li>' for i in items) + "</ul>"


def finding_html(f) -> str:
    color = SEV_COLOR.get(f.severity, "#333")
    parts = [
        f'<h3 style="color:{color}; margin-bottom:4px">{esc(f.title)}</h3>',
        block(f.detail),
    ]
    if f.fix_id:
        title, desc = strings.FIXES[f.fix_id]
        parts.append(f"<p><b>{esc(UI['fix_header'])}</b><br>{esc(title)}؛ {esc(desc)}</p>")
    if f.manual:
        parts.append(f"<p><b>{esc(UI['manual_header'])}</b></p>" + bullets(esc(m) for m in f.manual_texts))
    if f.links:
        parts.append(
            f"<p><b>{esc(UI['links_header'])}</b></p>"
            + bullets(f'<a href="{html.escape(u)}">{esc(label)}</a>' for label, u in f.links)
        )
    return "".join(parts)


def card_html(card) -> str:
    rows = []
    if card.vendor:
        rows.append((UI["col_vendor"], card.vendor))
    if card.hardware_id:
        sub = f" (SUBSYS_{card.subsystem})" if card.subsystem else ""
        rows.append((UI["col_hwid"], card.hardware_id + sub))
    inst = " ".join(x for x in (card.provider, card.version, card.driver_date) if x)
    if inst:
        rows.append((UI["col_driver"], inst))
    table = "".join(
        f'<tr><td style="padding:2px 0 2px 14px"><b>{esc(k)}</b></td><td dir="ltr" style="text-align:right">{esc(v)}</td></tr>'
        for k, v in rows
    )
    return (
        f'<h3 dir="rtl">{esc(card.name)}</h3><table>{table}</table>'
        + bullets(esc(a) for a in card.advice)
        + f"<p><b>{esc(UI['links_header'])}</b></p>"
        + bullets(f'<a href="{html.escape(u)}">{esc(label)}</a>' for label, u in card.links)
    )


class Bridge(QtCore.QObject):
    """Carries results from worker threads back to the GUI thread."""

    log = Signal(str)
    finished = Signal(object, object, object)  # done callback, value, error


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, runner, demo: bool = False):
        super().__init__()
        self.runner = runner
        self.demo = demo
        self.admin = demo or is_admin()
        self.result = None
        self.findings: list = []
        self.cards: list = []
        self.bridge = Bridge()
        self.bridge.log.connect(self.log)
        self.bridge.finished.connect(self._on_finished)

        self.setWindowTitle(UI["app_title"] + (" (دمو)" if demo else ""))
        self.resize(1100, 760)
        self._build()
        self.start_scan()

    # ---------- layout ----------
    def _build(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        v = QtWidgets.QVBoxLayout(root)

        if not self.admin:
            banner = QtWidgets.QFrame(objectName="banner")
            h = QtWidgets.QHBoxLayout(banner)
            h.addWidget(QtWidgets.QLabel(UI["admin_banner"]), 1)
            b = QtWidgets.QPushButton(UI["admin_button"])
            b.clicked.connect(self.on_admin)
            h.addWidget(b)
            v.addWidget(banner)

        self.summary = QtWidgets.QLabel("", objectName="summary")
        self.sysline = QtWidgets.QLabel("", objectName="sysline")
        self.sysline.setWordWrap(True)
        v.addWidget(self.summary)
        v.addWidget(self.sysline)

        bar = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton(UI["scan"])
        self.btn_fix = QtWidgets.QPushButton(UI["fix"], objectName="primary")
        self.btn_undo = QtWidgets.QPushButton(UI["undo"])
        self.btn_save = QtWidgets.QPushButton(UI["save_report"])
        for b, fn in ((self.btn_scan, self.start_scan), (self.btn_fix, self.on_fix),
                      (self.btn_undo, self.on_undo), (self.btn_save, self.on_save)):
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.progress.setTextVisible(False)
        self.progress.hide()
        bar.addWidget(self.progress)
        v.addLayout(bar)

        self.tabs = QtWidgets.QTabWidget()
        v.addWidget(self.tabs, 1)

        # Findings
        split = QtWidgets.QSplitter(Qt.Vertical)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([UI["col_fix"], UI["col_sev"], UI["col_title"]])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.tree.currentItemChanged.connect(self.on_select)
        self.detail = QtWidgets.QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        split.addWidget(self.tree)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)
        split.setSizes([300, 320])
        self.tabs.addTab(split, UI["tab_findings"])

        # Devices
        self.dev_tree = QtWidgets.QTreeWidget()
        self.dev_tree.setHeaderLabels([UI["col_name"], UI["col_status"], UI["col_id"]])
        self.dev_tree.setRootIsDecorated(False)
        self.dev_tree.setAlternatingRowColors(True)
        self.dev_tree.setColumnWidth(0, 360)
        self.dev_tree.setColumnWidth(1, 110)
        self.tabs.addTab(self.dev_tree, UI["tab_devices"])

        # Manual update guide
        gsplit = QtWidgets.QSplitter(Qt.Vertical)
        gleft = QtWidgets.QWidget()
        gl = QtWidgets.QVBoxLayout(gleft)
        gl.setContentsMargins(0, 0, 0, 0)
        self.guide_tree = QtWidgets.QTreeWidget()
        self.guide_tree.setHeaderLabels([UI["col_name"], UI["col_vendor"], UI["col_driver"], UI["col_date"]])
        self.guide_tree.setRootIsDecorated(False)
        self.guide_tree.setAlternatingRowColors(True)
        self.guide_tree.currentItemChanged.connect(self.on_guide_select)
        self.guide_tree.setColumnWidth(0, 420)
        self.guide_tree.setColumnWidth(1, 90)
        self.guide_tree.setColumnWidth(2, 220)
        gl.addWidget(self.guide_tree, 1)
        self.btn_copy = QtWidgets.QPushButton(UI["copy_id"])
        self.btn_copy.clicked.connect(self.on_copy_id)
        gl.addWidget(self.btn_copy)
        self.guide_detail = QtWidgets.QTextBrowser()
        self.guide_detail.setOpenExternalLinks(True)
        gsplit.addWidget(gleft)
        gsplit.addWidget(self.guide_detail)
        gsplit.setStretchFactor(0, 3)
        gsplit.setStretchFactor(1, 5)
        gsplit.setSizes([180, 440])
        self.tabs.addTab(gsplit, UI["tab_guide"])

        # System
        self.sys_text = QtWidgets.QTextBrowser()
        self.tabs.addTab(self.sys_text, UI["tab_system"])

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(120)
        self.log_box.setPlaceholderText(UI["log_header"])
        v.addWidget(self.log_box)

    # ---------- helpers ----------
    def log(self, message: str) -> None:
        self.log_box.appendPlainText(message)

    def _busy(self, busy: bool) -> None:
        for b in (self.btn_scan, self.btn_fix, self.btn_undo):
            b.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _ask(self, title: str, text: str, detail: str = "") -> bool:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        if detail:
            box.setDetailedText(detail)
        yes = box.addButton(UI["btn_yes"], QtWidgets.QMessageBox.AcceptRole)
        box.addButton(UI["btn_cancel"], QtWidgets.QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def _info(self, text: str, warn: bool = False) -> None:
        (QtWidgets.QMessageBox.warning if warn else QtWidgets.QMessageBox.information)(self, UI["app_title"], text)

    def _run_bg(self, work, done) -> None:
        def target():
            try:
                self.bridge.finished.emit(done, work(), None)
            except Exception as exc:  # shown to the user, not swallowed
                self.bridge.finished.emit(done, None, exc)

        self._busy(True)
        threading.Thread(target=target, daemon=True).start()

    def _on_finished(self, done, value, error) -> None:
        self._busy(False)
        done(value, error)

    def _log_cb(self):
        return lambda m: self.bridge.log.emit(m)

    # ---------- scan ----------
    def start_scan(self) -> None:
        self.summary.setText(UI["scanning"])
        self._run_bg(lambda: scan(self.runner), self.on_scan_done)

    def on_scan_done(self, result, error) -> None:
        if error:
            msg = f"{UI['scan_failed']} {error}"
            self.summary.setText(UI["scan_failed"])
            self.log(msg)
            self._info(msg, warn=True)
            return
        self.result = result
        self.findings = result.findings
        snap = result.snapshot

        # summary
        counts = {s: sum(1 for f in self.findings if f.severity == s) for s in ("error", "warn", "info")}
        if self.findings:
            bits = [f"{fa(counts[s])} {strings.SEVERITY[s]}" for s in ("error", "warn", "info") if counts[s]]
            self.summary.setText(f"{fa(len(self.findings))} مورد پیدا شد ({'، '.join(bits)})")
        else:
            self.summary.setText("مشکلی پیدا نشد")
        s = snap.system
        self.sysline.setText(
            f"{UI['sys_board']}: {s.board_manufacturer} {s.board_product}   |   "
            f"{UI['sys_bios']}: {s.bios_version}   |   {s.cpu}".strip()
        )

        # findings
        self.tree.clear()
        for f in self.findings:
            item = QtWidgets.QTreeWidgetItem(["", strings.SEVERITY[f.severity], f.title])
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(SEV_COLOR[f.severity])))
            item.setForeground(2, QtGui.QBrush(QtGui.QColor(SEV_COLOR[f.severity])))
            if f.fix_id:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if fixes.DEFAULT_CHECKED.get(f.fix_id, False) else Qt.Unchecked)
            self.tree.addTopLevelItem(item)
        if self.findings:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self.detail.setHtml(f"<p>{esc(UI['no_findings'])}</p>")

        # devices
        self.dev_tree.clear()
        for d in snap.devices:
            status = f"خطا {d.error_code}" if d.has_error else ("غایب" if d.is_ghost else d.status)
            it = QtWidgets.QTreeWidgetItem([d.name, status, d.instance_id])
            if d.has_error:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(SEV_COLOR["error"])))
            self.dev_tree.addTopLevelItem(it)

        # guide
        self.cards = guide.build_cards(snap.system)
        self.guide_tree.clear()
        for c in self.cards:
            self.guide_tree.addTopLevelItem(
                QtWidgets.QTreeWidgetItem([c.name, c.vendor, f"{c.provider} {c.version}".strip(), c.driver_date])
            )
        if self.cards:
            self.guide_tree.setCurrentItem(self.guide_tree.topLevelItem(0))
        else:
            self.guide_detail.setHtml(f"<p>{esc(UI['guide_intro'])}</p>")

        # system
        self.sys_text.setHtml("<br>".join(esc(line) for line in report.system_lines(snap)))
        for w in snap.warnings:
            self.log("⚠ " + w)

    # ---------- selection ----------
    def on_select(self, current, _previous=None) -> None:
        if current is None:
            return
        self.detail.setHtml(finding_html(self.findings[self.tree.indexOfTopLevelItem(current)]))

    def on_guide_select(self, current, _previous=None) -> None:
        if current is None:
            return
        self.guide_detail.setHtml(card_html(self.cards[self.guide_tree.indexOfTopLevelItem(current)]))

    def on_copy_id(self) -> None:
        item = self.guide_tree.currentItem()
        if item is None:
            return
        card = self.cards[self.guide_tree.indexOfTopLevelItem(item)]
        if card.hardware_id:
            QtWidgets.QApplication.clipboard().setText(card.hardware_id)
            self.log(f"{UI['copied']} {card.hardware_id}")

    # ---------- actions ----------
    def on_admin(self) -> None:
        if relaunch_as_admin():
            self.close()

    def _checked_findings(self) -> list:
        out = []
        for i, f in enumerate(self.findings):
            item = self.tree.topLevelItem(i)
            if f.fix_id and item is not None and item.checkState(0) == Qt.Checked:
                out.append(f)
        return out

    def on_fix(self) -> None:
        if not self.admin:
            self._info(UI["need_admin"], warn=True)
            return
        steps = fixes.collect_steps(self._checked_findings())
        if not steps:
            self._info(UI["nothing_selected"])
            return
        lines = [f"• {s.shown[:200]}" for s in steps]
        if not self._ask(UI["confirm_title"], f"{UI['confirm_intro']}\n\n{UI['confirm_question']}", "\n".join(lines)):
            return
        log = self._log_cb()
        self._run_bg(lambda: fixes.execute(steps, self.runner, log), self.on_fix_done)

    def on_fix_done(self, result, error) -> None:
        if error:
            self.log(f"{UI['scan_failed']} {error}")
            return
        self.log(f"{UI['done']} (موفق: {fa(result.ok)}، ناموفق: {fa(result.failed)})")
        self.log(f"پشتیبان: {result.backup_dir}")
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
        self._run_bg(
            lambda: backup.undo(directory, self.runner, log),
            lambda failed, error: self.log(UI["undone"] if not error else f"{UI['scan_failed']} {error}"),
        )

    def on_save(self) -> None:
        if self.result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, UI["save_report"], "usb-report.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report.build_report(self.result))
            self.log(f"{UI['report_saved']} {path}")


def make_app(argv=None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setFont(QtGui.QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    return app


def run_gui(runner, demo: bool = False) -> None:
    app = make_app()
    win = MainWindow(runner, demo)
    win.show()
    app.exec()
