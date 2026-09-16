"""The IADS chain of a site, in two halves.

What the site gives the network and what it needs from it are different questions, and
a single list of rows answered them in whatever order the site happened to produce
them: a command centre listed the radars covering it and never said what it directed.
The giving half carries the verdict, because that is what the site is doing for the
network right now.
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from game.theater.iadsnetwork.iadsexplain import IadsLink, IadsPicture, NoNetwork
from game.theater.iadsnetwork.iadsstate import IadsState
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.groundobject.common import TONE_INK
from qt_ui.windows.pilot.common import (
    AMBER,
    EMPTY,
    GREEN,
    HEADING_BG,
    RED,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    chip,
    label,
)

#: Wide enough for the longest caption at the size it is drawn.
CAPTION_WIDTH = 112

#: What the site's state reads as, and in what colour.
STATE_INK = {
    IadsState.NETWORKED: GREEN,
    IadsState.AUTONOMOUS: AMBER,
    IadsState.DARK: "#8E9DAA",
    IadsState.DESTROYED: RED,
}


class IadsCard(QWidget):
    """Two sections: what this site gives the network, and what it gets from it."""

    def __init__(self, picture: IadsPicture) -> None:
        super().__init__()
        self.stack = Stack()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        if picture.off is not None:
            self.stack.append(_one_line(picture))
        else:
            self._section("Gives the network", picture.gives, picture)
            self._section("Needs from the network", picture.gets, picture)
        self.stack.refresh()

    def _section(
        self, name: str, links: Sequence[IadsLink], picture: IadsPicture
    ) -> None:
        if not links and picture.gives:
            # A battery gives nothing but its guns; an empty second half would be the
            # only thing said about it.
            return
        heading = Row(height=26, fill=HEADING_BG)
        heading.add(label(name.upper(), 10.5, TEXT_LABEL, bold=True))
        heading.stretch()
        if links is picture.gives:
            heading.add(_verdict(picture))
        self.stack.append(heading)
        if links is picture.gives:
            self.stack.append(_state_row(picture))
        for link in links:
            self.stack.append(_link_row(link))


def _verdict(picture: IadsPicture) -> QWidget:
    if picture.status is None:
        return chip(picture.verdict, EMPTY)
    return chip(picture.verdict, STATE_INK[picture.status.state])


def _state_row(picture: IadsPicture) -> Row:
    """What the site is doing for the network, in a line."""
    ink = STATE_INK[picture.status.state] if picture.status is not None else TEXT_LABEL
    row = Row(height=34)
    row.add(label(picture.summary, 12, ink))
    row.stretch()
    return row


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
