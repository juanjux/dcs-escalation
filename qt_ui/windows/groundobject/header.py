"""The header of a location: what it is, whose it is, and how much of it is left."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from game.theater import ControlPoint, TheaterGroundObject
from game.theater.theatergroundobject import BuildingGroundObject
from game.theater.iadsnetwork.iadsexplain import IadsPicture
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.groundobject.buildingcard import buildings_of, reward_for
from qt_ui.windows.groundobject.common import (
    DESTROYED_INK,
    HealthBar,
    kind_chip_text,
    owner_of,
)
from qt_ui.windows.pilot.common import (
    ACCENT,
    AMBER,
    EMPTY,
    GREEN,
    PANEL,
    RED,
    TEXT_LABEL,
    TEXT_PRIMARY,
    chip,
    label,
)

#: The fill behind the kind chip, per side.
KIND_FILL = {"BLUE": "#22384A", "RED": "#3B2523", "NEUTRAL": ""}


class LocationHeader(QWidget):
    """Name, kind, the figures worth planning against, and one status line."""

    def __init__(
        self,
        ground_object: TheaterGroundObject,
        cp: ControlPoint,
        iads: Optional[IadsPicture] = None,
    ) -> None:
        super().__init__()
        self.setObjectName(f"locationHeader{id(self)}")
        self.setStyleSheet(
            f"#{self.objectName()} {{ background: {PANEL}; border: none; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)
        row.addWidget(self._identity(ground_object, cp, iads), 1)
        if isinstance(ground_object, BuildingGroundObject) and reward_for(
            ground_object
        ):
            row.addWidget(self._income(ground_object))
        else:
            row.addWidget(self._health(ground_object))
        self.setLayout(row)

    def _identity(
        self,
        ground_object: TheaterGroundObject,
        cp: ControlPoint,
        iads: Optional[IadsPicture],
    ) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        owner = owner_of(cp)
        name = QHBoxLayout()
        name.setSpacing(10)
        name.addWidget(label(ground_object.obj_name, 24, TEXT_PRIMARY, bold=True))
        name.addWidget(
            chip(
                kind_chip_text(ground_object, cp),
                ACCENT if owner == "BLUE" else (RED if owner == "RED" else TEXT_LABEL),
                KIND_FILL[owner],
                outline=owner == "NEUTRAL",
            )
        )
        name.addStretch()
        column.addLayout(name)
        column.addWidget(label(self._figures(ground_object, cp), 12.5, TEXT_LABEL))

        status = QHBoxLayout()
        status.setSpacing(8)
        warning = self._warning(ground_object, cp)
        if warning:
            status.addWidget(label(f"▲  {warning}", 12, AMBER))
        damage = self._damage(ground_object)
        if damage:
            status.addWidget(chip(damage, RED, "#2A1A1A"))
        status.addStretch()
        column.addLayout(status)
        holder.setLayout(column)
        return holder

    @staticmethod
    def _figures(ground_object: TheaterGroundObject, cp: ControlPoint) -> str:
        if isinstance(ground_object, BuildingGroundObject):
            buildings = buildings_of(ground_object)
            count = len(buildings)
            parts = [cp.name, f"{count} building{'s' if count != 1 else ''}"]
            reward = reward_for(ground_object)
            if reward:
                parts.append(f"each pays ${reward:g}M / turn while standing")
            return "  ·  ".join(parts)

        parts = [cp.name]
        threat = ground_object.max_threat_range()
        detection = ground_object.max_detection_range()
        if threat.meters > 0:
            parts.append(f"threat {threat.nautical_miles:.0f} nm")
        if detection.meters > 0:
            parts.append(f"detection {detection.nautical_miles:.0f} nm")
        if ground_object.purchasable and ground_object.value:
            parts.append(f"value ${ground_object.value}M")
        return "  ·  ".join(parts)

    @staticmethod
    def _damage(ground_object: TheaterGroundObject) -> str:
        units = list(ground_object.units)
        destroyed = sum(
            1
            for unit in units
            if not unit.alive and unit.repair_turns_remaining is None
        )
        repairing = sum(
            1
            for unit in units
            if not unit.alive and unit.repair_turns_remaining is not None
        )
        parts = []
        if destroyed:
            parts.append(f"{destroyed} destroyed")
        if repairing:
            parts.append(f"{repairing} repairing")
        return " · ".join(parts)

    @staticmethod
    def _warning(ground_object: TheaterGroundObject, cp: ControlPoint) -> str:
        """What the loss of these buildings costs the base they belong to."""
        if not isinstance(ground_object, BuildingGroundObject):
            return ""
        if ground_object.is_ammo_depot:
            standing = cp.active_ammo_depots_count
            total = cp.total_ammo_depots_count
            if standing == total:
                return ""
            supply = cp.front_line_capacity_with(standing)
            return (
                f"Ammo at {cp.name} down to {standing}/{total} — "
                f"{supply} front-line units can be supplied"
            )
        if ground_object.is_factory and not cp.has_factory:
            return f"No factory standing at {cp.name} — no ground units are built here"
        return ""

    @staticmethod
    def _income(ground_object: TheaterGroundObject) -> QWidget:
        """What the objective pays now against what it pays whole."""
        buildings = buildings_of(ground_object)
        reward = reward_for(ground_object)
        standing = sum(1 for building in buildings if building.alive)
        now = standing * reward
        whole = len(buildings) * reward

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)

        column.addWidget(_right(label("INCOME", 10, TEXT_LABEL, bold=True)))
        figure = QHBoxLayout()
        figure.setSpacing(6)
        figure.addStretch()
        figure.addWidget(
            label(
                f"${now:g}M",
                20,
                GREEN if standing == len(buildings) else TEXT_PRIMARY,
                bold=True,
                monospace=True,
            )
        )
        figure.addWidget(label(f"of ${whole:g}M", 12, TEXT_LABEL))
        column.addLayout(figure)
        # No "-$4M until repaired" line: the bar and the two figures above it already
        # say what is missing, and a minus sign beside money reads as a cost.
        column.addWidget(HealthBar(standing, 0, len(buildings)))
        holder.setLayout(column)
        return holder

    @staticmethod
    def _health(ground_object: TheaterGroundObject) -> QWidget:
        units = list(ground_object.units)
        alive = sum(1 for unit in units if unit.alive)
        repairing = sum(
            1
            for unit in units
            if not unit.alive and unit.repair_turns_remaining is not None
        )

        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)

        figure = QHBoxLayout()
        figure.setSpacing(6)
        figure.addStretch()
        figure.addWidget(label("ALIVE", 10, TEXT_LABEL, bold=True))
        figure.addWidget(
            label(
                f"{alive} / {len(units)}",
                20,
                GREEN if alive == len(units) else TEXT_PRIMARY,
                bold=True,
                monospace=True,
            )
        )
        column.addLayout(figure)
        column.addWidget(HealthBar(alive, repairing, len(units)))

        legend = QHBoxLayout()
        legend.setSpacing(10)
        legend.addStretch()
        for text, ink in (
            ("alive", GREEN),
            ("repairing", AMBER),
            ("destroyed", DESTROYED_INK),
        ):
            legend.addWidget(label(f"■ {text}", 9.5, ink))
        column.addLayout(legend)
        holder.setLayout(column)
        return holder


def _right(widget: QWidget) -> QWidget:
    """One widget pushed to the right of its own row."""
    holder = QWidget()
    make_transparent(holder)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch()
    row.addWidget(widget)
    holder.setLayout(row)
    return holder
