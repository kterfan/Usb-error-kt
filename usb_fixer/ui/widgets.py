"""Reusable widgets: status icon, check box, chips, and the cards of the dashboard."""

from __future__ import annotations

import html

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import strings
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
    # every line gets its own RLM, so a line that starts with Latin text still reads right-to-left
    lbl = QtWidgets.QLabel(text if (rich or name == "mono") else RLM + text.replace("\n", "\n" + RLM))
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


class Section(QtWidgets.QWidget):
    """Section heading with an optional subtitle, used between groups of cards."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 10, 4, 0)
        lay.setSpacing(2)
        lay.addWidget(label(title, "sectionTitle"))
        if subtitle:
            lay.addWidget(label(subtitle, "sub"))


def risk_chip(risk: str) -> QtWidgets.QLabel:
    return chip(strings.RISK_LABEL.get(risk, risk), {"safe": "fix", "low": "manual", "caution": "error"}.get(risk, ""))


class AdviceBox(QtWidgets.QFrame):
    """The 'what should I do' part of a card: always visible, one sentence plus link buttons."""

    def __init__(self, text: str, links=(), parent=None):
        super().__init__(parent)
        self.setObjectName("advice")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        self.text = label(text)
        lay.addWidget(self.text)
        if links:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(4)
            for lbl, url in links:
                row.addWidget(link_button(lbl, url))
            row.addStretch(1)
            lay.addLayout(row)


class ProblemCard(Card):
    """One finding: icon, title, summary, the recommendation (always visible), fix toggle, more details."""

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
        if finding.reverted:
            chips.addWidget(chip("دوباره برگشته", "error"))
        if finding.fix_id:
            chips.addWidget(chip("قابل رفع خودکار", "fix"))
            chips.addWidget(risk_chip(strings.FIX_INFO[finding.fix_id]["risk"]))
        elif finding.manual:
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

        reco = finding.recommendation
        self.advice = AdviceBox(reco, finding.links[:2]) if reco else None
        if self.advice:
            lay.addWidget(self.advice)

        self.details = label(self._details_html(), rich=True)
        lay.addWidget(self.details)
        self.details.setVisible(False)

    def _details_html(self) -> str:
        f = self.finding
        sub = theme.color("sub")
        parts = ['<div dir="rtl">']
        parts.append("".join(f'<p style="margin:3px 0">{html.escape(l)}</p>' for l in f.detail.split("\n") if l.strip()))
        if f.fix_id:
            info = strings.FIX_INFO[f.fix_id]
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["fix_header"])}</b><br>{esc(info["plain"])}<br>'
                         f'<span style="color:{sub}">{esc(info["undo_note"])}</span></p>')
        if f.manual and len(f.manual_texts) > (0 if f.fix_id else 1):
            rest = f.manual_texts if f.fix_id else f.manual_texts[1:]
            items = "".join(f'<li style="margin:2px 0">{esc(m)}</li>' for m in rest)
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["manual_header"])}</b></p><ul style="margin-top:2px">{items}</ul>')
        if len(f.links) > 2:
            link = theme.color("link")
            items = "".join(f'<li style="margin:2px 0"><a style="color:{link}" href="{html.escape(u)}">{esc(lbl)}</a></li>' for lbl, u in f.links[2:])
            parts.append(f'<p style="margin:10px 0 2px 0"><b>{esc(UI["links_header"])}</b></p><ul style="margin-top:2px">{items}</ul>')
        parts.append("</div>")
        return "".join(parts)

    def toggle_details(self) -> None:
        show = self.details.isHidden()
        self.details.setVisible(show)
        self.summary.setVisible(not show)
        self.more.setText("بستن جزئیات" if show else "جزئیات")


class TechToggle(QtWidgets.QWidget):
    """'Technical details' link that reveals label/value rows (IDs, versions) with a copy button."""

    copied = QtCore.Signal(str)

    def __init__(self, rows: list, copy_value: str = "", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QtWidgets.QHBoxLayout()
        self.button = QtWidgets.QPushButton("جزئیات فنی ▾")
        self.button.setObjectName("link")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.toggle)
        top.addWidget(self.button)
        top.addStretch(1)
        lay.addLayout(top)
        self.body = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self.body)
        grid.setContentsMargins(6, 0, 6, 0)
        grid.setHorizontalSpacing(12)
        for i, (k, v) in enumerate(rows):
            grid.addWidget(label(k, "sub", wrap=False), i, 0)
            val = label(v, "mono", wrap=True)
            val.setLayoutDirection(Qt.LeftToRight)
            grid.addWidget(val, i, 1)
        if copy_value:
            b = QtWidgets.QPushButton("کپی شناسه")
            b.setObjectName("ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: self.copied.emit(copy_value))
            grid.addWidget(b, 0, 2)
        grid.setColumnStretch(1, 1)
        lay.addWidget(self.body)
        self.body.setVisible(False)

    def toggle(self) -> None:
        show = self.body.isHidden()
        self.body.setVisible(show)
        self.button.setText("جزئیات فنی ▴" if show else "جزئیات فنی ▾")


class DeviceRow(Card):
    """One physical device in plain words: type, name, maker, status; IDs hidden under technical details."""

    def __init__(self, dev, parent=None):
        sev = {"error": "error", "absent": "", "ok": ""}[dev.status]
        super().__init__(sev, parent)
        self.device = dev
        lay = card_layout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        kind = {"error": "error", "absent": "info", "ok": "ok"}[dev.status]
        row.addWidget(IconBadge(kind, 30), 0, Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        title = dev.name + (f"  ×{dev.count}" if dev.count > 1 else "")
        col.addWidget(label(title, "cardTitle"))
        meta = "، ".join(x for x in (dev.type_label, dev.vendor, dev.status_text) if x)
        col.addWidget(label(meta, "sub"))
        row.addLayout(col, 1)
        lay.addLayout(row)
        self.tech = TechToggle([("شناسه‌ها", "\n".join(dev.ids))], dev.ids[0] if dev.ids else "")
        lay.addWidget(self.tech)


class VerdictCard(Card):
    """Big direct answer at the top of a page."""

    def __init__(self, ok: bool, title: str, text: str, actions=(), links=(), parent=None):
        super().__init__("ok" if ok else "warn", parent)
        lay = card_layout(self)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(IconBadge("ok" if ok else "warn", 44), 0, Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(title, "cardTitle"))
        if text:
            col.addWidget(label(text, "sub"))
        row.addLayout(col, 1)
        lay.addLayout(row)
        for item in actions:
            lay.addWidget(AdviceBox(item[0], [item[1:]] if len(item) == 3 else []))
        if links:
            box = QtWidgets.QHBoxLayout()
            for text_, url in links:
                box.addWidget(link_button(text_, url))
            box.addStretch(1)
            lay.addLayout(box)


class ControllerCardWidget(Card):
    copied = QtCore.Signal(str)

    def __init__(self, card, parent=None):
        super().__init__("ok" if card.ok else "warn", parent)
        self.card = card
        lay = card_layout(self)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(IconBadge("ok" if card.ok else "warn", 34), 0, Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(card.title, "cardTitle"))
        col.addWidget(label(f"درایور: {card.driver_text}", "sub"))
        if card.advice:
            col.addWidget(label(card.advice))
        row.addLayout(col, 1)
        lay.addLayout(row)
        if card.links:
            links = QtWidgets.QHBoxLayout()
            for text, url in card.links:
                links.addWidget(link_button(text, url))
            links.addStretch(1)
            lay.addLayout(links)
        self.tech = TechToggle([("نام در ویندوز", card.name)] + list(card.tech), card.hardware_id)
        self.tech.copied.connect(self.copied.emit)
        lay.addWidget(self.tech)


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
            grid.addWidget(label(v or "—"), i, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
