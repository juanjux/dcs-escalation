"""The units of a location, grouped, classed and folded.

Twenty rows of "SAM Patriot LN" say nothing; the same units under their group, each
carrying what it is for, with the identical live ones folded into one row, are about
eight. Destroyed and repairing sort first, because they are what the dialog is open
for.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from game.theater import TheaterGroundObject
from game.theater.theatergroup import TheaterUnit
from qt_ui.widgets.coordinatelabel import CoordinateLabel
from qt_ui.windows.groundobject.common import (
    ALIVE_INK,
    DESTROYED_INK,
    REPAIRING_INK,
)
from qt_ui.windows.pilot.common import (
    AIR_FAMILY,
    EMPTY,
    GREEN,
    GROUND_FAMILY,
    HEADING_BG,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    chip,
    label,
)

RepairCall = Callable[[TheaterUnit, int], None]


def state_of(unit: TheaterUnit) -> tuple[str, str]:
    """The unit's state as a chip and the colour of its bar."""
    if unit.alive:
        return "", ALIVE_INK
    if unit.repair_turns_remaining is not None:
        turns = unit.repair_turns_remaining
        return f"REPAIRING · {turns} TURN{'S' if turns != 1 else ''}", REPAIRING_INK
    return "DESTROYED", DESTROYED_INK


def sort_key(unit: TheaterUnit) -> tuple[int, str]:
    if not unit.alive and unit.repair_turns_remaining is None:
        first = 0
    elif not unit.alive:
        first = 1
    else:
        first = 2
    return first, str(unit.name)


def describe_unit(unit: TheaterUnit) -> str:
    """What the unit is, rather than which model it is."""
    if unit.unit_type is None:
        return ""
    return str(unit.unit_type.unit_class.description)


def unit_note(unit: TheaterUnit) -> str:
    if unit.unit_type is None:
        return ""
    return str(unit.unit_type.unit_class.note)


def type_name(unit: TheaterUnit) -> str:
    if unit.unit_type is not None:
        return str(unit.unit_type.display_name)
    return str(unit.name or unit.type.name)


def price_of(unit: TheaterUnit) -> int:
    return unit.unit_type.price if unit.unit_type is not None else 0


class UnitCard(QWidget):
    """One card per location: a heading per group, a row per unit or per fold."""

    def __init__(
        self,
        ground_object: TheaterGroundObject,
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
        self._build()

    # ------------------------------------------------------------------ building

    def _build(self) -> None:
        for group in self.ground_object.groups:
            units = sorted(group.units, key=sort_key)
            if not units:
                continue
            self.stack.append(self._group_heading(group, units))
            for name, same in self._fold(units).items():
                if len(same) == 1:
                    self.stack.append(self._unit_row(same[0], indent=14))
                else:
                    self._folded(name, same)
        self.stack.refresh()

    @staticmethod
    def _fold(units: Sequence[TheaterUnit]) -> "OrderedDict[str, list[TheaterUnit]]":
        """Units of one type together, in the order the first of them sorted to."""
        folded: OrderedDict[str, list[TheaterUnit]] = OrderedDict()
        for unit in units:
            folded.setdefault(type_name(unit), []).append(unit)
        return folded

    def _group_heading(self, group: object, units: Sequence[TheaterUnit]) -> Row:
        alive = sum(1 for unit in units if unit.alive)
        family = AIR_FAMILY if self.ground_object.is_iads else GROUND_FAMILY
        row = Row(height=24, fill=HEADING_BG)
        name = str(getattr(group, "name", "") or "Units")
        row.add(label(name.upper(), 10.5, family, bold=True))
        row.stretch()
        row.add(
            label(
                f"{alive} / {len(units)}",
                11,
                GREEN if alive == len(units) else TEXT_LABEL,
                monospace=True,
            )
        )
        return row

    def _folded(self, name: str, units: list[TheaterUnit]) -> None:
        """One row for n identical units, with the positions under it."""
        alive = sum(1 for unit in units if unit.alive)
        hurt = len(units) - alive
        parent = Row(height=36, interactive=True)
        marker = label("▾" if hurt else "▸", 10, TEXT_LABEL)
        parent.add(marker)
        parent.add(label(name, 12.5, TEXT_BASE, bold=True))
        parent.add(label(f"×{len(units)}", 11, TEXT_LABEL, monospace=True))
        described = describe_unit(units[0])
        if described:
            parent.add(label(described, 11, TEXT_LABEL))
        parent.stretch()
        parent.add(
            label(
                f"{alive} alive · {hurt} down" if hurt else "all alive",
                11,
                TEXT_LABEL if hurt else GREEN,
            )
        )

        children = [self._unit_row(unit, indent=40) for unit in units]
        for child in children:
            child.setVisible(bool(hurt))
        marker.setText("▾" if hurt else "▸")

        def toggle() -> None:
            opening = not children[0].isVisible()
            for row in children:
                row.setVisible(opening)
            marker.setText("▾" if opening else "▸")
            self.stack.refresh()

        parent.clicked.connect(toggle)
        self.stack.append(parent)
        for child in children:
            self.stack.append(child)

    def _unit_row(self, unit: TheaterUnit, indent: int) -> Row:
        state, ink = state_of(unit)
        row = Row(height=36, margins=(indent, 0, 14, 0))
        row.add(_dot(ink))
        row.add(label(type_name(unit), 12.5, TEXT_BASE, bold=True))
        described = describe_unit(unit)
        if described:
            row.add(label(described, 11, TEXT_LABEL))
        note = unit_note(unit)
        if note:
            row.add(label(f"· {note}", 11, EMPTY))
        row.add(label(str(unit.id).zfill(4), 11, EMPTY, monospace=True))
        if state:
            row.add(chip(state, ink))
        row.stretch()
        button = self._repair_button(unit)
        if button is not None:
            row.add(button)
        row.add(CoordinateLabel(unit.position, self.settings))
        return row

    def _repair_button(self, unit: TheaterUnit) -> Optional[QWidget]:
        if self.repair is None or unit.alive or not unit.repairable:
            return None
        if unit.repair_turns_remaining is not None:
            return None
        price = price_of(unit)
        button = QPushButton(f"Repair  ${price}M")
        button.setProperty("style", "btn-success")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(
            # clicked emits a checked bool first; absorb it, or it binds over the unit.
            lambda checked=False, u=unit, p=price: self._repair(u, p)
        )
        return button

    def _repair(self, unit: TheaterUnit, price: int) -> None:
        assert self.repair is not None
        self.repair(unit, price)


def _dot(ink: str) -> QWidget:
    """The state of a unit, small enough to read as punctuation."""
    dot = label("●", 9, ink)
    dot.setFixedWidth(10)
    return dot


def repairable_units(ground_object: TheaterGroundObject) -> list[TheaterUnit]:
    """The wrecks a Repair all would pay for."""
    return [
        unit
        for unit in ground_object.units
        if not unit.alive and unit.repairable and unit.repair_turns_remaining is None
    ]
