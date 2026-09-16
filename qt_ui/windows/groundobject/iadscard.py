"""The IADS chain of a site, in two halves.

What the site gives the network and what it needs from it are different questions, and
a single list of rows answered them in whatever order the site happened to produce
them: a command centre listed the radars covering it and never said what it directed.
The state sits above both halves, because it is the answer to neither: it is what the
site is doing right now.

A battery gives the network nothing -- it is a leaf, and its radar is off until the
network hands it a target -- so it has no giving half at all.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from game.theater import TheaterGroundObject
from game.theater.iadsnetwork.iadsexplain import IadsLink, IadsPicture
from game.theater.iadsnetwork.iadsstate import IadsState
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.groundobject.common import TONE_INK
from qt_ui.windows.pilot.common import (
    AMBER,
    Clickable,
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

OpenSite = Callable[[TheaterGroundObject], None]


class IadsCard(QWidget):
    """What the site is doing, what it gives the network and what it needs from it."""

    def __init__(
        self, picture: IadsPicture, open_site: Optional[OpenSite] = None
    ) -> None:
        super().__init__()
        self.open_site = open_site
        self.stack = Stack()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        if picture.off is not None:
            self.stack.append(_one_line(picture))
        else:
            self.stack.append(_state_row(picture))
            self._section("Gives the network", picture.gives)
            self._section("Needs from the network", picture.gets)
        self.stack.refresh()

    def _section(self, name: str, links: Sequence[IadsLink]) -> None:
        if not links:
            return
        heading = Row(height=26, fill=HEADING_BG)
        heading.add(label(name.upper(), 10.5, TEXT_LABEL, bold=True))
        heading.stretch()
        self.stack.append(heading)
        for link in links:
            self.stack.append(self._link_row(link))

    def _link_row(self, link: IadsLink) -> Row:
        row = Row(height=44)
        caption = label(link.caption, 10.5, TEXT_LABEL, bold=True)
        caption.setFixedWidth(CAPTION_WIDTH)
        row.add(caption)

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        column.addWidget(self._title(link))
        if link.note:
            column.addWidget(label(link.note, 11, EMPTY))
        holder.setLayout(column)
        row.add(holder)

        row.stretch()
        row.add(chip(link.chip, TONE_INK[link.tone]))
        return row

    def _title(self, link: IadsLink) -> QWidget:
        """The objectives the row names, each one a way into its own dialog."""
        if not link.places or self.open_site is None:
            return label(link.title, 12.5, TEXT_BASE, bold=True)

        holder = QWidget()
        make_transparent(holder)
        names = QHBoxLayout()
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(6)
        for index, place in enumerate(link.places):
            if index:
                names.addWidget(label("·", 12.5, TEXT_LABEL))
            if place.objective is None:
                names.addWidget(label(place.name, 12.5, TEXT_BASE, bold=True))
                continue
            opener = Clickable(place.name, 12.5)
            opener.setStyleSheet(opener.styleSheet() + " font-weight: 600;")
            opener.clicked.connect(
                lambda objective=place.objective: self._open(objective)
            )
            names.addWidget(opener)
        if link.more:
            names.addWidget(label(f"and {link.more} more", 11.5, TEXT_LABEL))
        names.addStretch()
        holder.setLayout(names)
        return holder

    def _open(self, objective: TheaterGroundObject) -> None:
        assert self.open_site is not None
        self.open_site(objective)


def _state_row(picture: IadsPicture) -> Row:
    """What the site is doing, and the verdict Skynet will reach about it."""
    ink = STATE_INK[picture.status.state] if picture.status is not None else TEXT_LABEL
    row = Row(height=38)
    row.add(label(picture.summary, 12, ink))
    row.stretch()
    row.add(chip(picture.verdict, ink if picture.status is not None else EMPTY))
    return row


def _one_line(picture: IadsPicture) -> Row:
    """What a site with no network behind it has to say, in a line."""
    row = Row(height=44)
    row.add(label(picture.summary, 12, TEXT_LABEL))
    row.stretch()
    row.add(chip(picture.verdict, EMPTY))
    return row
