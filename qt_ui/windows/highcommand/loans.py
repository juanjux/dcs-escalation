"""The On loan tab: the squadrons lent by a ticket, and when each goes back."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from qt_ui.uiconstants import AIRCRAFT_ICONS
from qt_ui.widgets.cards import card, make_transparent
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.model import LoanView
from qt_ui.windows.highcommand.rows import draw, elide, font, mono_font
from qt_ui.windows.pilot.common import label

LOAN_ROW = 64
BANNER = QSize(91, 24)
TEXT_LEFT = 120


class TimedRow(QWidget):
    """Something that lasts some turns: what it is, a line under it, and the turns
    until it ends; with the aircraft's banner when it is a squadron."""

    def __init__(
        self,
        title: str,
        line: str,
        turns_left: int,
        until: int,
        dcs_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.line = line
        self.turns_left = turns_left
        self.until = until
        self.dcs_id = dcs_id
        self.setFixedHeight(LOAN_ROW)

    @property
    def last_turn(self) -> bool:
        return self.turns_left <= 1

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(
            rect, QColor(ink.LAST_TURN_FILL if self.last_turn else ink.CARD)
        )
        if self.last_turn:
            painter.fillRect(QRect(0, 0, 3, rect.height()), QColor(ink.ORANGE))
        painter.setPen(QColor(ink.DIVIDER))
        painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)

        text_left = 14
        if self.dcs_id is not None:
            text_left = TEXT_LEFT
            where = QRect(
                14,
                (rect.height() - BANNER.height()) // 2,
                BANNER.width(),
                BANNER.height(),
            )
            pixmap = AIRCRAFT_ICONS.get(self.dcs_id)
            if pixmap is not None:
                painter.drawPixmap(
                    where,
                    pixmap.scaled(
                        BANNER,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ),
                )
            else:
                painter.setPen(QColor(ink.DIVIDER))
                painter.drawRect(where)

        right = rect.width() - 14
        number = str(self.turns_left)
        face = mono_font(18, QFont.Weight.DemiBold)
        width = QFontMetrics(face).horizontalAdvance(number)
        draw(
            painter,
            right - width,
            28,
            number,
            face,
            ink.ORANGE if self.last_turn else ink.BODY,
        )
        note = (
            f"last turn · turn {self.until}"
            if self.last_turn
            else f"turns · turn {self.until}"
        )
        small = font(10.5)
        note_width = QFontMetrics(small).horizontalAdvance(note)
        draw(painter, right - note_width, 48, note, small, ink.MUTED)

        room = right - max(width, note_width) - 16 - text_left
        title = font(13, QFont.Weight.DemiBold)
        draw(painter, text_left, 26, elide(title, self.title, room), title, ink.TITLE)
        body = font(11.5)
        draw(painter, text_left, 46, elide(body, self.line, room), body, ink.MUTED)
        painter.end()


def loan_row(loan: LoanView) -> TimedRow:
    return TimedRow(
        loan.aircraft,
        f"{loan.squadron} · {loan.count} aircraft · {loan.base}",
        loan.turns_left,
        loan.until,
        loan.dcs_id,
    )


class LoansPage(QWidget):
    """The squadrons on loan, the soonest to go back first."""

    def __init__(self) -> None:
        super().__init__()
        heading = QHBoxLayout()
        heading.setContentsMargins(14, 8, 14, 8)
        for text in ("Squadrons on loan", "Goes back"):
            caption = label(text.upper(), 10.5, ink.CAPTION, bold=True)
            caption.setStyleSheet(caption.styleSheet() + " letter-spacing: 1px;")
            heading.addWidget(caption)
            if text != "Goes back":
                heading.addStretch()
        head = QWidget()
        head.setLayout(heading)
        make_transparent(head)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {ink.DIVIDER}; border: none;")

        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(head)
        column.addWidget(rule)
        column.addLayout(self.rows)
        self.list = card()
        self.list.setLayout(column)

        self.empty = label(
            "Nothing on loan. A squadron joins on loan when an AWACS, tanker or"
            " squadron ticket is spent.",
            12.5,
            ink.QUIET,
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 0, 14, 14)
        layout.addWidget(self.list)
        layout.addWidget(self.empty, 1)
        layout.addStretch()
        self.setLayout(layout)

    def show_loans(self, loans: Sequence[LoanView]) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for loan in loans:
            self.rows.addWidget(loan_row(loan))
        self.list.setVisible(bool(loans))
        self.empty.setVisible(not loans)
