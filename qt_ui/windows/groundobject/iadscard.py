"""The IADS chain of a site, one row per link.

The verdict is in the header; this is how it was reached. On an own site the rows are
what to repair, on an enemy site what to bomb, which is the one thing a striker wants
to know about a red SAM and the dialog never said.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from game.theater.iadsnetwork.iadsexplain import IadsLink, IadsPicture
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.groundobject.common import TONE_INK
from qt_ui.windows.pilot.common import (
    EMPTY,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    chip,
    label,
)

#: Wide enough for the longest caption at the size it is drawn.
CAPTION_WIDTH = 112


class IadsCard(QWidget):
    """One row per kind of link: who cues it, who directs it, what powers it."""

    def __init__(self, picture: IadsPicture) -> None:
        super().__init__()
        self.stack = Stack()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        if not picture.links:
            self.stack.append(_one_line(picture))
        else:
            for link in picture.links:
                self.stack.append(_link_row(link))
        self.stack.refresh()


def _one_line(picture: IadsPicture) -> Row:
    """What a site with no network behind it has to say, in a line."""
    row = Row(height=44)
    row.add(label(picture.summary, 12, TEXT_LABEL))
    row.stretch()
    row.add(chip(picture.verdict, EMPTY))
    return row


def _link_row(link: IadsLink) -> Row:
    row = Row(height=44)
    caption = label(link.caption, 10.5, TEXT_LABEL, bold=True)
    caption.setFixedWidth(CAPTION_WIDTH)
    row.add(caption)

    holder = QWidget()
    make_transparent(holder)
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(1)
    column.addWidget(label(link.title, 12.5, TEXT_BASE, bold=True))
    if link.note:
        column.addWidget(label(link.note, 11, EMPTY))
    holder.setLayout(column)
    row.add(holder)

    row.stretch()
    row.add(chip(link.chip, TONE_INK[link.tone]))
    return row
