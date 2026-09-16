"""The buildings of a location, as rows.

Five 300-pixel tiles with a photograph of fire in them did not scale to a location
with nine buildings, and said less than a row: what it is, whether it stands, what it
pays and where it is.
"""

from __future__ import annotations

import os
from functools import partial
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from game.config import REWARDS
from game.theater import TheaterGroundObject
from game.theater.theatergroundobject import BuildingGroundObject
from game.theater.theatergroup import TheaterUnit
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.coordinatelabel import CoordinateLabel
from qt_ui.windows.groundobject.common import (
    ALIVE_INK,
    DESTROYED_INK,
    REPAIRING_INK,
    two_tone_button,
)
from qt_ui.windows.pilot.common import (
    EMPTY,
    GREEN,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    chip,
    label,
)

RepairCall = Callable[[TheaterUnit, float], None]

PICTURES = "./resources/ui/units/buildings"
THUMBNAIL = (42, 28)

#: What a destroyed building's picture is worth: enough to recognise, not enough to
#: read as standing.
DEAD_OPACITY = 0.45


def kind_of(ground_object: TheaterGroundObject) -> str:
    """The category in the words the rest of the dialog uses."""
    from qt_ui.windows.groundobject.common import BUILDING_NAMES

    category = ground_object.category
    return BUILDING_NAMES.get(category, category).lower()


def reward_for(ground_object: TheaterGroundObject) -> float:
    return REWARDS.get(ground_object.category, 0)


def buildings_of(ground_object: TheaterGroundObject) -> list[TheaterUnit]:
    """The buildings worth listing: fortifications are scenery, as they always were."""
    from game.data.building_data import FORTIFICATION_BUILDINGS

    return [
        static
        for static in ground_object.statics
        if static not in FORTIFICATION_BUILDINGS
    ]


def repairable_buildings(ground_object: TheaterGroundObject) -> list[TheaterUnit]:
    return [
        building
        for building in buildings_of(ground_object)
        if not building.alive and building.repair_turns_remaining is None
    ]


def thumbnail(building: TheaterUnit) -> Optional[QWidget]:
    """The recon picture, small. None when the building has no picture at all."""
    path = os.path.join(PICTURES, f"{building.icon}.png")
    if building.icon == "missing" or not os.path.isfile(path):
        return None
    picture = QPixmap(path).scaled(
        *THUMBNAIL,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not building.alive:
        dimmed = QPixmap(picture.size())
        dimmed.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dimmed)
        painter.setOpacity(DEAD_OPACITY)
        painter.drawPixmap(0, 0, picture)
        painter.end()
        picture = dimmed

    holder = QLabel()
    holder.setPixmap(picture)
    holder.setFixedSize(*THUMBNAIL)
    holder.setStyleSheet("background: transparent; border: none;")
    return holder


class BuildingCard(QWidget):
    """One row per building: what it is, whether it stands, and what it pays."""

    def __init__(
        self,
        ground_object: BuildingGroundObject,
        settings: object,
        repair: Optional[RepairCall],
    ) -> None:
        super().__init__()
        self.ground_object = ground_object
        self.settings = settings
        self.repair = repair

        self.stack = Stack()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        for building in sorted(buildings_of(ground_object), key=self._order):
            self.stack.append(self._row(building))
        self.stack.refresh()

    @staticmethod
    def _order(building: TheaterUnit) -> tuple[int, str]:
        if not building.alive and building.repair_turns_remaining is None:
            return 0, str(building.name)
        if not building.alive:
            return 1, str(building.name)
        return 2, str(building.name)

    def _row(self, building: TheaterUnit) -> Row:
        row = Row(height=44)
        picture = thumbnail(building)
        if picture is not None:
            row.add(picture)

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)

        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(label(str(building.name), 12.5, TEXT_BASE, bold=True))
        title.addWidget(label(kind_of(self.ground_object), 11, TEXT_LABEL))
        state, ink = self._state(building)
        if state:
            title.addWidget(chip(state, ink))
        title.addStretch()
        column.addLayout(title)

        pays = self._pay_line(building)
        if pays is not None:
            column.addWidget(pays)
        holder.setLayout(column)
        row.add(holder)
        row.stretch()

        button = self._repair_button(building)
        if button is not None:
            row.add(button)
        row.add(CoordinateLabel(building.position, self.settings, compact=True))
        return row

    @staticmethod
    def _state(building: TheaterUnit) -> tuple[str, str]:
        if building.alive:
            return "", ALIVE_INK
        if building.repair_turns_remaining is not None:
            turns = building.repair_turns_remaining
            return f"REPAIRING · {turns} TURN{'S' if turns != 1 else ''}", REPAIRING_INK
        return "DESTROYED", DESTROYED_INK

    def _pay_line(self, building: TheaterUnit) -> Optional[QWidget]:
        reward = reward_for(self.ground_object)
        if not reward:
            # Comms, power and command centres pay nothing; what they are worth is
            # the network they hold up, and the header says that.
            return None
        text = f"pays ${reward:g}M / turn"
        if building.alive:
            return label(text, 11, GREEN)
        struck = label(text, 11, "#6B7A87")
        struck.setStyleSheet(struck.styleSheet() + " text-decoration: line-through;")
        return struck

    def _repair_button(self, building: TheaterUnit) -> Optional[QWidget]:
        if self.repair is None or building.alive:
            return None
        if building.repair_turns_remaining is not None:
            return None
        price = self.ground_object.repair_cost()
        if price <= 0:
            return None
        return two_tone_button(
            "Repair",
            f"${price:g}M",
            handler=partial(self.repair, building, price),
        )
