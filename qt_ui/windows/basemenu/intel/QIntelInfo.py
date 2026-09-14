"""What is at an enemy base, grouped by what it is and by what you would do about it.

It was a column of group boxes named after DCS task constants -- CAS, AFAC,
GroundAttack -- one per aircraft role, with a "Front line units" box at the bottom.
Those names come from the unit table rather than from the decision being made, and an
air-defence site did not appear at all, which is the one thing that decides whether a
strike on this base is worth planning.
"""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.theater import ControlPoint, ParkingType
from game.transfers import MultiGroupTransport
from qt_ui.models import GameModel
from qt_ui.widgets.cards import CAPTION, HINT, carded, make_transparent
from qt_ui.widgets.controls import KEY, mono
from qt_ui.windows.basemenu.buylist import BRIGHT, QUIET
from qt_ui.windows.basemenu.DepartingConvoysMenu import ConvoyCard, departing_from
from qt_ui.windows.basemenu.header import air_defences, site_name

EVERY_PARKING = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)


def _line(name: str, count: str) -> QWidget:
    """A name on the left and its figure on the right, so the counts line up."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    label = QLabel(name)
    label.setStyleSheet(
        f"font-size: 12.5px; color: {KEY}; background: transparent; border: none;"
    )
    row.addWidget(label)
    row.addStretch()

    figure = QLabel(count)
    figure.setFont(mono(12))
    figure.setStyleSheet(
        f"color: {BRIGHT}; background: transparent; border: none; font-weight: 600;"
    )
    row.addWidget(figure)

    holder = QWidget()
    make_transparent(holder)
    holder.setFixedHeight(22)
    holder.setLayout(row)
    return holder


def _group(name: str, total: str, lines: list[QWidget]) -> QWidget:
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)

    heading = QHBoxLayout()
    heading.setContentsMargins(0, 0, 0, 0)
    title = QLabel(name.upper())
    title.setStyleSheet(
        f"font-size: 10px; font-weight: bold; letter-spacing: 1px; color: {CAPTION};"
        " background: transparent; border: none;"
    )
    heading.addWidget(title)
    heading.addStretch()
    summary = QLabel(total)
    summary.setStyleSheet(
        f"font-size: 11px; color: {QUIET}; background: transparent; border: none;"
    )
    heading.addWidget(summary)
    column.addLayout(heading)

    for line in lines:
        column.addWidget(line)

    holder = QWidget()
    make_transparent(holder)
    holder.setLayout(column)
    return holder


class QIntelInfo(QWidget):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super().__init__()
        self.cp = cp
        self.game_model = game_model

        column = QVBoxLayout()
        column.setContentsMargins(0, 8, 0, 0)
        column.setSpacing(14)
        for group in self.groups():
            column.addWidget(group)
        # A convoy is here this turn and gone the next, so it is repeated here rather
        # than left in its own tab where it would be found the turn after.
        for convoy in departing_from(cp, game_model):
            column.addWidget(_leaving(convoy))
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

    def groups(self) -> list[QWidget]:
        cards = []
        aircraft = self.aircraft_lines()
        if aircraft:
            cards.append(
                _group("Aircraft", f"{sum(aircraft.values())} here", _lines(aircraft))
            )

        defences = self.air_defence_lines()
        if defences:
            sites = sum(defences.values())
            cards.append(
                _group(
                    "Air defence",
                    f"{sites} site" + ("" if sites == 1 else "s"),
                    _lines(defences),
                )
            )

        ground = self.ground_lines()
        if ground:
            cards.append(
                _group("Ground units", f"{sum(ground.values())} here", _lines(ground))
            )

        if not cards:
            nothing = QLabel("Nothing is known to be at this base.")
            nothing.setStyleSheet(
                f"font-size: 12px; color: {HINT}; background: transparent;"
                " border: none;"
            )
            cards.append(nothing)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        for card_content in cards:
            column.addWidget(card_content)

        inner = QWidget()
        make_transparent(inner)
        inner.setLayout(column)

        holder = QWidget()
        holder.setLayout(carded("Known units", inner))
        return [holder]

    # -- what is here --------------------------------------------------------

    def aircraft_lines(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for unit_type, count in self.cp.allocated_aircraft(
            EVERY_PARKING
        ).present.items():
            if count:
                counts[unit_type.display_name] += count
        return dict(counts)

    def ground_lines(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for unit_type, count in self.cp.base.armor.items():
            if count:
                counts[unit_type.display_name] += count
        return dict(counts)

    def air_defence_lines(self) -> dict[str, int]:
        """One entry per kind of site, counted -- "SA-15 Tor  2" -- because what
        matters is how many of each you have to get past, not their code names."""
        counts: dict[str, int] = defaultdict(int)
        for site in air_defences(self.cp):
            counts[site_name(site)] += 1
        return dict(counts)


def _lines(counts: dict[str, int]) -> list[QWidget]:
    return [
        _line(name, str(count))
        for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _leaving(convoy: MultiGroupTransport) -> QWidget:
    holder = QWidget()
    holder.setLayout(carded("Convoy leaving", ConvoyCard(convoy)))
    return holder
