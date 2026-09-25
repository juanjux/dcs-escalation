"""The turn log, as a list of events rather than a wall of timestamps.

Every line used to read `[2012-05-18 21:03:44][11] Repairs at Waterbuck in progress, 1
turn remaining` — twenty-eight characters of prefix, repeated on every row, that never
answered a question anyone had. The wall clock is the moment the message object was
built, which is not a fact about the campaign at all.

A row now carries the turn in mono, a category chip, and the message. The turn number is
the only time that means anything here, and the category is what makes the list
filterable; the full timestamp moves to the tooltip for the one case where it matters,
which is telling two identical messages apart.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.infos.information import Information
from game.infos.places import place_named_in

ROW_HEIGHT = 26
TURN_X = 14
CHIP_X = 52
CHIP_Y = 5
CHIP_HEIGHT = 16
CHIP_RADIUS = 3
CHIP_WIDTH = 60
MESSAGE_X = 124
BASELINE = 18
MARGIN = 14

PANEL_BG = "#14202B"
HEAD_BG = "#1B2732"
SEPARATOR = QColor("#1D2731")
HOVER_FILL = QColor("#1A2A38")

TURN_INK = QColor("#6B7A87")
MESSAGE_INK = QColor("#D3DFE8")
NOUN_INK = QColor("#F2F7FA")
NEW_BAR = QColor("#E0A86B")
ACCENT = "#8FC3F0"
CAPTION = "#6B7A87"

#: fill, ink. The four the log actually produces.
CATEGORIES = {
    "REPAIR": (QColor("#3B2D21"), QColor("#E0A86B")),
    "ALLY": (QColor("#22384A"), QColor("#8FC3F0")),
    "ENEMY": (QColor("#3B2523"), QColor("#D9645E")),
    "INFO": (QColor("#26343F"), QColor("#9FADB9")),
}

#: What the segmented filter offers, and which categories each shows.
FILTERS: list[tuple[str, Optional[set[str]]]] = [
    ("All", None),
    ("Allied", {"ALLY"}),
    ("Repairs", {"REPAIR"}),
    ("Enemy", {"ENEMY"}),
]


def category_of(info: Information) -> str:
    """Which of the four an entry belongs to, read off the wording that made it.

    The log has no category field: every message is a sentence built at the call site,
    so this classifies on the words those twenty-odd sites use. Anything unrecognised
    is INFO, which is also where the turn boundaries and the campaign start belong.
    """
    title = info.title.lower()
    if "opfor" in title or "lost!" in title or "lost its source" in title:
        return "ENEMY"
    if "repair" in title:
        return "REPAIR"
    if "captured!" in title or "we have" in title or "redeploy" in title:
        return "ALLY"
    return "INFO"


def _font(
    pixels: float, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False
):
    font = QFont("Consolas") if mono else QFont()
    font.setPixelSize(int(pixels))
    font.setWeight(weight)
    return font


class EventItem(QStandardItem):
    """One log entry, with everything the row needs already worked out."""

    def __init__(self, info: Information, current_turn: int) -> None:
        super().__init__()
        self.info = info
        self.category = category_of(info)
        self.is_new = info.turn == current_turn
        self.setEditable(False)
        self.setText(f"{info.title} {info.text}".strip())
        if info.timestamp is not None:
            self.setToolTip(
                f"Turn {info.turn} · {info.timestamp:%Y-%m-%d %H:%M:%S}\n"
                f"{info.title}\n{info.text}".strip()
            )


class EventDelegate(QStyledItemDelegate):
    """Turn, category, message. Nothing else fits in 26 px and nothing else is wanted."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        item = index.model().itemFromIndex(index)
        if not isinstance(item, EventItem):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(option.rect)
        painter.translate(option.rect.topLeft())
        width = option.rect.width()

        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(0, 0, width, ROW_HEIGHT, HOVER_FILL)
        if item.is_new:
            painter.fillRect(0, 0, 3, ROW_HEIGHT, NEW_BAR)

        painter.setFont(_font(11, mono=True))
        painter.setPen(TURN_INK)
        painter.drawText(TURN_X, BASELINE, f"T{item.info.turn}")

        fill, ink = CATEGORIES[item.category]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            CHIP_X, CHIP_Y, CHIP_WIDTH, CHIP_HEIGHT, CHIP_RADIUS, CHIP_RADIUS
        )
        painter.setFont(_font(9.5, QFont.Weight.Bold))
        painter.setPen(ink)
        painter.drawText(
            QRect(CHIP_X, CHIP_Y, CHIP_WIDTH, CHIP_HEIGHT),
            Qt.AlignmentFlag.AlignCenter,
            item.category,
        )

        # The title is the noun the eye should land on; the body is the detail.
        painter.setFont(_font(12, QFont.Weight.DemiBold))
        painter.setPen(NOUN_INK)
        title = item.info.title
        painter.drawText(MESSAGE_X, BASELINE, title)
        after = MESSAGE_X + painter.fontMetrics().horizontalAdvance(title)

        if item.info.text:
            painter.setFont(_font(12))
            painter.setPen(MESSAGE_INK)
            room = width - after - MARGIN - 8
            painter.drawText(
                after + 8,
                BASELINE,
                painter.fontMetrics().elidedText(
                    item.info.text, Qt.TextElideMode.ElideRight, max(20, room)
                ),
            )

        painter.fillRect(0, ROW_HEIGHT - 1, width, 1, SEPARATOR)
        painter.restore()


class EventList(QListView):
    """The entries, newest first, filtered by category and by turn."""

    def __init__(self, game: Optional[Game]) -> None:
        super().__init__()
        self.game = game
        self.categories: Optional[set[str]] = None
        self.all_turns = False
        self.entries = QStandardItemModel(self)
        self.setModel(self.entries)
        self.setItemDelegate(EventDelegate())
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setStyleSheet(f"QListView {{ background: {PANEL_BG}; border: none; }}")
        self.doubleClicked.connect(self.show_place)
        self.update_list()

    def show_place(self, index: QModelIndex) -> None:
        """Move the map to the base or site the entry names, at the zoom the player
        left it at. An entry that names none does nothing."""
        from game.server import EventStream
        from game.sim import GameUpdateEvents

        item = self.entries.itemFromIndex(index)
        if self.game is None or not isinstance(item, EventItem):
            return
        place = place_named_in(self.game, item.info)
        if place is not None:
            EventStream.put_nowait(GameUpdateEvents().look_at(place.position.latlng()))

    def set_filter(self, categories: Optional[set[str]]) -> None:
        self.categories = categories
        self.update_list()

    def set_all_turns(self, all_turns: bool) -> None:
        self.all_turns = all_turns
        self.update_list()

    def update_list(self) -> None:
        self.entries.clear()
        if self.game is None:
            return
        turn = self.game.turn
        for info in reversed(self.game.informations):
            if not self.all_turns and info.turn != turn:
                continue
            item = EventItem(info, turn)
            if self.categories is not None and item.category not in self.categories:
                continue
            self.entries.appendRow(item)

    def setGame(self, game: Optional[Game]) -> None:  # noqa: N802 - Qt naming
        self.game = game
        self.update_list()


class EventsPanel(QWidget):
    """The log under the map: a head with the filters, and the entries."""

    def __init__(self, game: Optional[Game]) -> None:
        super().__init__()
        self.game = game
        self.setStyleSheet(f"EventsPanel {{ background: {PANEL_BG}; }}")

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.setLayout(column)

        head = QWidget()
        head.setFixedHeight(30)
        head.setStyleSheet(f"background: {HEAD_BG};")
        row = QHBoxLayout()
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)
        head.setLayout(row)

        caption = QLabel("EVENTS")
        font = _font(10.5, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        caption.setFont(font)
        caption.setStyleSheet(f"color: {CAPTION};")
        row.addWidget(caption)
        row.addSpacing(8)

        self.filters: list[QPushButton] = []
        for name, categories in FILTERS:
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(name == "All")
            button.setFixedHeight(20)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { border: none; border-radius: 3px; padding: 0 9px;"
                f" color: {CAPTION}; font-size: 11px; background: transparent; }}"
                f"QPushButton:checked {{ background: #26343F; color: {ACCENT}; }}"
                "QPushButton:hover { background: #22303B; }"
            )
            button.clicked.connect(
                lambda _checked, wanted=categories, chosen=button: self._filter(
                    wanted, chosen
                )
            )
            row.addWidget(button)
            self.filters.append(button)
        row.addStretch()

        self.all_turns = QPushButton("Show all turns")
        self.all_turns.setCheckable(True)
        self.all_turns.setFixedHeight(20)
        self.all_turns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_turns.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0;"
            f" color: {ACCENT}; font-size: 11px; }}"
            "QPushButton:checked { text-decoration: underline; }"
        )
        self.all_turns.clicked.connect(
            lambda checked: self.event_list.set_all_turns(checked)
        )
        row.addWidget(self.all_turns)
        column.addWidget(head)

        self.event_list = EventList(game)
        column.addWidget(self.event_list, 1)

    def _filter(self, categories: Optional[set[str]], chosen: QPushButton) -> None:
        for button in self.filters:
            button.setChecked(button is chosen)
        self.event_list.set_filter(categories)

    def setGame(self, game: Optional[Game]) -> None:  # noqa: N802 - Qt naming
        self.game = game
        self.event_list.setGame(game)

    def update(self) -> None:  # type: ignore[override]
        self.event_list.update_list()
