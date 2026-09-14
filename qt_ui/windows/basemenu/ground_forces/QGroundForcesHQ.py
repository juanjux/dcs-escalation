"""The ground tab: what you can buy on the left, what you have and what to do with it
on the right.

The catalogue and the stance combo used to share a two-cell grid with nothing saying
they were different questions, and what was actually deployed here was in a paragraph
at the top of the window. The three now sit as three cards, and only the catalogue
scrolls.
"""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.theater import ControlPoint
from qt_ui.models import GameModel
from qt_ui.widgets.cards import (
    HINT,
    caption,
    carded,
    make_transparent,
    shrinkable,
)
from qt_ui.windows.basemenu.buylist import AMBER, BRIGHT, QUIET
from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import (
    QArmorRecruitmentMenu,
)
from qt_ui.windows.basemenu.ground_forces.QGroundForcesStrategy import (
    QGroundForcesStrategy,
)

#: The right-hand column holds two cards that do not scroll; the catalogue takes the
#: rest, because it is the only thing here long enough to need the width. A range
#: rather than a fixed width: pinned at 380 it set the smallest the whole window
#: could be, and the window grew itself on opening to make room.
SIDE_WIDTH = 380
SIDE_MIN_WIDTH = 280


def count_chip(count: int, name: str) -> QWidget:
    """ "4 Leopard 2A4" -- the figure first, because that is what is being compared."""
    row = QHBoxLayout()
    row.setContentsMargins(8, 3, 8, 3)
    row.setSpacing(6)

    number = QLabel(str(count))
    number.setStyleSheet(
        f"font-size: 12px; font-weight: 600; color: {BRIGHT};"
        " background: transparent; border: none;"
    )
    row.addWidget(number)

    label = QLabel(name)
    label.setStyleSheet(
        f"font-size: 11.5px; color: {QUIET}; background: transparent; border: none;"
    )
    row.addWidget(shrinkable(label), 1)

    holder = QWidget()
    holder.setObjectName(f"unitChip{id(holder)}")
    holder.setStyleSheet(
        f"#{holder.objectName()} {{ background: #1B2732; border: 1px solid #26343F;"
        " border-radius: 3px; }}"
    )
    holder.setLayout(row)
    return holder


class QGroundForcesHQ(QWidget):
    def __init__(self, cp: ControlPoint, game_model: GameModel) -> None:
        super().__init__()
        self.cp = cp
        self.game_model = game_model

        self.units_here = QWidget()
        self._units_here_layout = QVBoxLayout()
        self._units_here_layout.setContentsMargins(0, 0, 0, 0)
        self.units_here.setLayout(self._units_here_layout)
        make_transparent(self.units_here)
        self.refresh_units_here()

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(12)
        side.addWidget(QGroundForcesStrategy(cp, game_model.game))
        side.addLayout(carded("Units here", self.units_here))
        side.addStretch()

        side_holder = QWidget()
        make_transparent(side_holder)
        side_holder.setMinimumWidth(SIDE_MIN_WIDTH)
        side_holder.setMaximumWidth(SIDE_WIDTH)
        side_holder.setLayout(side)

        buying = QVBoxLayout()
        buying.setContentsMargins(0, 0, 0, 0)
        buying.addLayout(
            _section(
                "Buy ground units",
                QArmorRecruitmentMenu(cp, game_model),
                (
                    "built here, ready next turn"
                    if cp.has_factory
                    else "built at the nearest friendly factory and driven here"
                ),
            )
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(buying, 1)
        layout.addWidget(side_holder)
        self.setLayout(layout)

        # An order does not put a unit here -- it arrives next turn -- but it does
        # change the "ordered" line, which is the card's whole point this turn.
        game_model.transfer_model.inventory_changed.connect(self.refresh_units_here)

    def refresh_units_here(self) -> None:
        while self._units_here_layout.count():
            taken = self._units_here_layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.deleteLater()
        self._units_here_layout.addWidget(self._units_here())

    def _units_here(self) -> QWidget:
        transfers = self.game_model.game.coalition_for(self.cp.captured).transfers
        allocation = self.cp.allocated_ground_units(transfers)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        present = sorted(
            ((unit, count) for unit, count in self.cp.base.armor.items() if count),
            key=lambda pair: (-pair[1], pair[0].display_name),
        )
        if not present:
            nothing = QLabel("Nothing deployed here.")
            nothing.setStyleSheet(
                f"font-size: 11.5px; color: {HINT}; background: transparent;"
                " border: none;"
            )
            column.addWidget(nothing)
        else:
            chips = _Wrapped()
            for unit_type, count in present:
                chips.add(count_chip(count, unit_type.display_name))
            column.addWidget(chips)

        pending = []
        if allocation.total_transferring:
            pending.append(f"{allocation.total_transferring} en route")
        if allocation.total_ordered:
            pending.append(f"{allocation.total_ordered} ordered")
        if allocation.total_transferring_out:
            pending.append(f"{allocation.total_transferring_out} transferring out")
        if pending:
            note = QLabel(" · ".join(pending))
            note.setStyleSheet(
                f"font-size: 11px; color: {AMBER}; background: transparent;"
                " border: 1px dashed #4A3A28; border-radius: 3px; padding: 3px 8px;"
            )
            column.addWidget(shrinkable(note))

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(column)
        return holder


class _Wrapped(QWidget):
    """Chips that wrap to the next line rather than running off the card.

    Qt has no flow layout, and a grid of two columns is close enough for a list of
    unit types: the names are long, so two a line is what fits anyway.
    """

    COLUMNS = 2

    def __init__(self) -> None:
        super().__init__()
        make_transparent(self)
        self._grid = QVBoxLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(6)
        self.setLayout(self._grid)
        self._line: QHBoxLayout | None = None
        self._in_line = 0

    def add(self, chip: QWidget) -> None:
        if self._line is None or self._in_line == self.COLUMNS:
            self._line = QHBoxLayout()
            self._line.setContentsMargins(0, 0, 0, 0)
            self._line.setSpacing(6)
            self._grid.addLayout(self._line)
            self._in_line = 0
        self._line.addWidget(chip)
        self._in_line += 1
        if self._in_line == self.COLUMNS:
            self._line.addStretch()


def _section(name: str, content: QWidget, hint: str) -> QVBoxLayout:
    """cards.section, but letting the content take the spare height rather than the
    caption, so the catalogue fills the tab."""
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(8)
    column.addWidget(caption(name, hint))
    column.addWidget(content, 1)
    return column
