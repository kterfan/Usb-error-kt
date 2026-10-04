"""Reusable widgets: status icon, check box, chips, and the cards of the dashboard."""

from __future__ import annotations

import html

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import report, strings
from . import theme

UI = strings.UI


def open_url(url: str) -> None:
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


def sev_color(kind: str) -> QtGui.QColor:
    return QtGui.QColor(theme.color({"error": "error", "warn": "warn", "info": "info", "ok": "ok", "busy": "primary"}[kind]))


class IconBadge(QtWidgets.QWidget):
    """A round status icon (check / cross / exclamation / i / spinner) drawn with the painter."""

    def __init__(self, kind: str = "info", size: int = 40, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        if kind == "busy":
            self._timer.start(40)
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + 18) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        col = sev_color(self.kind)
        bg = QtGui.QColor(col)
        bg.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(self.rect())
        pen = QtGui.QPen(col, max(2.0, w / 14), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        def pt(x, y):
            return QtCore.QPointF(x * w, y * w)

        k = self.kind
        if k == "ok":
            path = QtGui.QPainterPath(pt(0.28, 0.52))
            path.lineTo(pt(0.44, 0.68))
            path.lineTo(pt(0.73, 0.34))
            p.drawPath(path)
        elif k == "error":
            p.drawLine(pt(0.34, 0.34), pt(0.66, 0.66))
            p.drawLine(pt(0.66, 0.34), pt(0.34, 0.66))
        elif k == "warn":
            p.drawLine(pt(0.5, 0.27), pt(0.5, 0.57))
            p.drawPoint(pt(0.5, 0.72))
        elif k == "info":
            p.drawPoint(pt(0.5, 0.30))
            p.drawLine(pt(0.5, 0.45), pt(0.5, 0.72))
        else:  # busy: rotating arc
            rect = QtCore.QRectF(w * 0.22, w * 0.22, w * 0.56, w * 0.56)
            p.drawArc(rect, int(-self._angle * 16), 270 * 16)


class CheckBox(QtWidgets.QCheckBox):
    """Check box with its own painting (rounded box + drawn tick), correct in RTL and both themes."""

    def sizeHint(self) -> QtCore.QSize:
        fm = self.fontMetrics()
        return QtCore.QSize(fm.horizontalAdvance(self.text()) + 40, 28)

    def paintEvent(self, _event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        size = 20
        rtl = self.layoutDirection() == Qt.RightToLeft
        x = self.width() - size - 2 if rtl else 2
        box = QtCore.QRectF(x, (self.height() - size) / 2, size, size)
        on = self.isChecked()
        hover = self.underMouse() and self.isEnabled()
        main = QtGui.QColor(theme.color("primary"))
        if not self.isEnabled():
            main = QtGui.QColor(theme.color("disabled"))
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(main)
        else:
            p.setPen(QtGui.QPen(main if hover else QtGui.QColor(theme.color("disabled")), 2))
            p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box, 6, 6)
        if on:
            p.setPen(QtGui.QPen(QtGui.QColor("white"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QtGui.QPainterPath(QtCore.QPointF(box.left() + size * 0.26, box.top() + size * 0.52))
            path.lineTo(box.left() + size * 0.44, box.top() + size * 0.70)
            path.lineTo(box.left() + size * 0.76, box.top() + size * 0.32)
            p.drawPath(path)
        p.setPen(QtGui.QColor(theme.color("text") if self.isEnabled() else theme.color("disabled")))
        text_rect = QtCore.QRectF(0, 0, self.width() - size - 12, self.height())
        if not rtl:
            text_rect = QtCore.QRectF(size + 10, 0, self.width() - size - 10, self.height())
        p.drawText(text_rect, Qt.AlignVCenter | (Qt.AlignRight if rtl else Qt.AlignLeft), self.text())


def chip(text: str, kind: str = "") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("chip")
    lbl.setProperty("kind", kind)
    return lbl


RLM = "\u200f"  # right-to-left mark: makes a line that starts with Latin text still an RTL paragraph


def label(text: str, name: str = "", wrap: bool = True, rich: bool = False) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text if (rich or name == "mono") else RLM + text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if rich:
        lbl.setTextFormat(Qt.RichText)
        lbl.setOpenExternalLinks(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    return lbl


def link_button(text: str, url: str) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(text)
    b.setObjectName("link")
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(lambda: open_url(url))
    return b


def esc(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def first_sentence(text: str, limit: int = 150) -> str:
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    line = lines[0] if lines else ""
    if line.endswith(":") and len(lines) > 1:
        line = line[:-1] + ": " + lines[1].lstrip("• ")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


class Card(QtWidgets.QFrame):
    def __init__(self, severity: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("sev", severity)
        self.setAttribute(Qt.WA_StyledBackground, True)


def card_layout(card: QtWidgets.QFrame) -> QtWidgets.QVBoxLayout:
    lay = QtWidgets.QVBoxLayout(card)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(8)
    return lay


class ProblemCard(Card):
    """One finding: icon, title, one-line summary, chips, a 'fix' check box and expandable details."""

    toggled = QtCore.Signal()

    def __init__(self, finding, checked: bool, parent=None):
        super().__init__(finding.severity, parent)
        self.finding = finding
        lay = card_layout(self)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(IconBadge(finding.severity, 40), 0, Qt.AlignTop)

        col = QtWidgets.QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(finding.title, "cardTitle"))
        self.summary = label(first_sentence(finding.detail), "sub")
        col.addWidget(self.summary)
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(chip(strings.SEVERITY[finding.severity], "error" if finding.severity == "error" else ""))
        if finding.fix_id:
            chips.addWidget(chip("قابل رفع خودکار", "fix"))
        if finding.manual:
            chips.addWidget(chip("نیاز به اقدام دستی", "manual"))
        chips.addStretch(1)
        col.addLayout(chips)
        row.addLayout(col, 1)

        side = QtWidgets.QVBoxLayout()
        side.setSpacing(6)
        self.check = CheckBox("رفع شود")
        self.check.setChecked(checked)
        self.check.toggled.connect(lambda _v: self.toggled.emit())
        side.addWidget(self.check, 0, Qt.AlignLeft)
        self.check.setVisible(bool(finding.fix_id))  # after addWidget: reparenting would undo an earlier hide
        self.more = QtWidgets.QPushButton("جزئیات")
        self.more.setObjectName("link")
        self.more.setCursor(Qt.PointingHandCursor)
        self.more.clicked.connect(self.toggle_details)
        side.addWidget(self.more, 0, Qt.AlignLeft)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row)

        self.details = label(self._details_html(), rich=True)
        lay.addWidget(self.details)
        self.details.setVisible(False)

    def _details_html(self) -> str:
        f = self.finding
        sub = theme.color("sub")
        parts = [f'<div dir="rtl">']
        parts.append("".join(f'<p style="margin:3px 0">{html.escape(l)}</p>' for l in f.detail.split("\n") if l.strip()))
        if f.fix_id:
            title, desc = strings.FIXES[f.fix_id]
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["fix_header"])}</b><br>{esc(title)}؛ <span style="color:{sub}">{esc(desc)}</span></p>')
        if f.manual:
            items = "".join(f'<li style="margin:2px 0">{esc(m)}</li>' for m in f.manual_texts)
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["manual_header"])}</b></p><ul style="margin-top:2px">{items}</ul>')
        if f.links:
            link = theme.color("link")
            items = "".join(
                f'<li style="margin:2px 0"><a style="color:{link}" href="{html.escape(u)}">{esc(lbl)}</a></li>' for lbl, u in f.links
            )
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["links_header"])}</b></p><ul style="margin-top:2px">{items}</ul>')
        parts.append("</div>")
        return "".join(parts)

    def toggle_details(self) -> None:
        show = self.details.isHidden()
        self.details.setVisible(show)
        self.summary.setVisible(not show)
        self.more.setText("بستن جزئیات" if show else "جزئیات")


class DriverCard(Card):
    """One USB controller (or the board): exact names/IDs and links for a manual update."""

    copied = QtCore.Signal(str)

    def __init__(self, card, parent=None):
        super().__init__("ok" if not card.advice or card.is_generic else "info", parent)
        self.card = card
        lay = card_layout(self)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label(card.name, "cardTitle"), 1)
        if card.vendor:
            top.addWidget(chip(card.vendor), 0, Qt.AlignTop)
        if card.hardware_id:
            top.addWidget(chip("درایور عمومی ویندوز" if card.is_generic else "درایور سازنده", "manual" if card.is_generic else "fix"), 0, Qt.AlignTop)
        lay.addLayout(top)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        r = 0
        if card.hardware_id:
            sub = f"  (SUBSYS_{card.subsystem})" if card.subsystem else ""
            grid.addWidget(label(UI["col_hwid"], "sub", wrap=False), r, 0)
            hw = label(card.hardware_id + sub, "mono", wrap=False)
            hw.setLayoutDirection(Qt.LeftToRight)
            grid.addWidget(hw, r, 1, Qt.AlignLeft)
            copy = QtWidgets.QPushButton("کپی")
            copy.setObjectName("ghost")
            copy.setCursor(Qt.PointingHandCursor)
            copy.clicked.connect(lambda: self.copied.emit(card.hardware_id))
            grid.addWidget(copy, r, 2, Qt.AlignLeft)
            r += 1
        inst = " ".join(x for x in (card.provider, card.version, card.driver_date) if x)
        if inst:
            grid.addWidget(label(UI["col_driver"], "sub", wrap=False), r, 0)
            val = label(inst, "mono", wrap=False)
            val.setLayoutDirection(Qt.LeftToRight)
            grid.addWidget(val, r, 1, Qt.AlignLeft)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)

        for a in card.advice[:1]:
            lay.addWidget(label("• " + a, "sub"))
        if card.links:
            links = QtWidgets.QHBoxLayout()
            for text, url in card.links:
                links.addWidget(link_button(text, url))
            links.addStretch(1)
            lay.addLayout(links)


class InfoCard(Card):
    """Title + label/value rows (used for the system page)."""

    def __init__(self, title: str, rows: list, parent=None):
        super().__init__("", parent)
        lay = card_layout(self)
        lay.addWidget(label(title, "cardTitle"))
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        for i, (k, v) in enumerate(rows):
            grid.addWidget(label(k, "sub", wrap=False), i, 0, Qt.AlignTop)
            val = label(v or "—")
            grid.addWidget(val, i, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)


def card_text(card) -> str:
    return "\n".join(report.card_lines(card))
