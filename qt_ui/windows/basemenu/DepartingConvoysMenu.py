"""Convoys leaving this base: where each is going, what is in it, and a strike on it.

A convoy is the one time-critical thing on an enemy base -- it is here this turn and
gone the next -- and it was a group box titled "Convoy 002 to FARP B2" with a column
of unit icons and a button called "Attack", which does not create an attack but plans
a package.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.theater import ControlPoint
from game.transfers import MultiGroupTransport
from qt_ui.dialogs import Dialog
from qt_ui.models import GameModel
from qt_ui.uiconstants import VEHICLES_ICONS
from qt_ui.widgets.cards import CAPTION, HINT, card, make_transparent
from qt_ui.widgets.controls import KEY
from qt_ui.windows.basemenu.buylist import BRIGHT


class ConvoyCard(QWidget):
    """One convoy: its destination in the heading, its cargo under it."""

    def __init__(self, convoy: MultiGroupTransport) -> None:
        super().__init__()
        self.convoy = convoy

        column = QVBoxLayout()
        column.setContentsMargins(14, 10, 14, 10)
        column.setSpacing(8)
        column.addLayout(self._heading())
        for unit_type, count in sorted(
            convoy.units.items(), key=lambda pair: (-pair[1], pair[0].display_name)
        ):
            column.addWidget(self._cargo(unit_type, count))
        if not convoy.units:
            empty = QLabel("Carrying nothing.")
            empty.setStyleSheet(
                f"font-size: 11.5px; color: {HINT}; background: transparent;"
                " border: none;"
            )
            column.addWidget(empty)

        holder = card()
        holder.setLayout(column)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(holder)
        self.setLayout(outer)

    def _heading(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        name = QLabel(f"{self.convoy.name} → {self.convoy.destination}")
        name.setStyleSheet(
            f"font-size: 13.5px; font-weight: 600; color: {BRIGHT};"
            " background: transparent; border: none;"
        )
        row.addWidget(name)

        total = sum(self.convoy.units.values())
        note = QLabel(f"{total} unit{'' if total == 1 else 's'} · departs this turn")
        note.setStyleSheet(
            f"font-size: 11px; color: {CAPTION}; background: transparent;"
            " border: none;"
        )
        row.addWidget(note)
        row.addStretch()

        strike = QPushButton("Plan strike…")
        strike.setProperty("style", "btn-danger")
        strike.clicked.connect(self.on_attack)
        row.addWidget(strike)
        return row

    def _cargo(self, unit_type: object, count: int) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        icon = QLabel()
        icon.setFixedWidth(64)
        dcs_id = getattr(unit_type, "dcs_id", None)
        if dcs_id in VEHICLES_ICONS:
            icon.setPixmap(VEHICLES_ICONS[dcs_id])
        icon.setStyleSheet("background: transparent; border: none;")
        row.addWidget(icon)

        name = QLabel(getattr(unit_type, "display_name", str(unit_type)))
        name.setStyleSheet(
            f"font-size: 12.5px; color: {KEY}; background: transparent; border: none;"
        )
        row.addWidget(name)
        row.addStretch()

        figure = QLabel(str(count))
        figure.setStyleSheet(
            f"font-size: 12.5px; font-weight: 600; color: {BRIGHT};"
            " background: transparent; border: none;"
        )
        row.addWidget(figure)

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(row)
        return holder

    def on_attack(self) -> None:
        # TODO: Maintain Convoy list in Game.
        # The fact that we create these here makes some of the other bookkeeping
        # complicated. We could instead generate this at the start of the turn (and
        # update whenever transfers are created or canceled) and also use that time to
        # precalculate things like the next stop and group names.
        Dialog.open_new_package_dialog(self.convoy, parent=self.window())


def departing_from(
    cp: ControlPoint, game_model: GameModel
) -> list[MultiGroupTransport]:
    """Every convoy and cargo ship leaving this base this turn."""
    transfers = game_model.game.coalition_for(cp.captured).transfers
    return [
        *transfers.convoys.departing_from(cp),
        *transfers.cargo_ships.departing_from(cp),
    ]


class DepartingConvoysMenu(QWidget):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super().__init__()

        column = QVBoxLayout()
        column.setContentsMargins(0, 8, 0, 0)
        column.setSpacing(10)

        convoys = departing_from(cp, game_model)
        for convoy in convoys:
            column.addWidget(ConvoyCard(convoy))
        if not convoys:
            nothing = QLabel(f"Nothing is leaving {cp.name} this turn.")
            nothing.setStyleSheet(
                f"font-size: 12px; color: {HINT}; background: transparent;"
                " border: none;"
            )
            column.addWidget(nothing)
        column.addStretch()

        content = QWidget()
        make_transparent(content)
        content.setLayout(column)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        self.setLayout(layout)
