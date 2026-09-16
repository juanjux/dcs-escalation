"""The header of a location: what it is, whose it is, and how much of it is left."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from game.theater import ControlPoint, TheaterGroundObject
from game.theater.iadsnetwork.iadsexplain import IadsPicture, NoNetwork
from game.theater.iadsnetwork.iadsstate import IadsState
from qt_ui.widgets.cards import make_transparent
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

#: What the site's IADS state reads as, and in what colour.
STATE_INK = {
    IadsState.NETWORKED: GREEN,
    IadsState.AUTONOMOUS: AMBER,
    IadsState.DARK: "#8E9DAA",
    IadsState.DESTROYED: RED,
}


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
        if iads is not None:
            status.addWidget(self._iads_pill(iads))
        damage = self._damage(ground_object)
        if damage:
            status.addWidget(chip(damage, RED, "#2A1A1A"))
        status.addStretch()
        column.addLayout(status)
        holder.setLayout(column)
        return holder

    @staticmethod
    def _figures(ground_object: TheaterGroundObject, cp: ControlPoint) -> str:
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
    def _iads_pill(iads: IadsPicture) -> QWidget:
        if iads.off is not None:
            ink = EMPTY if iads.off is NoNetwork.STANDALONE else TEXT_LABEL
        else:
            assert iads.status is not None
            ink = STATE_INK[iads.status.state]
        return label(iads.summary, 12, ink)

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
