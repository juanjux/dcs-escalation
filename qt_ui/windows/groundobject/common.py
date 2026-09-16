"""The pieces the location dialog is drawn with.

The palette and the row/card primitives come from the pilot dialog, which took them
from the Air Wing; only what a location needs and nothing else has is here: the
health bar with three colours, a compass that is drawn rather than rotated, and the
words for what kind of thing an objective is.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from game.data.groups import GroupTask
from game.theater import (
    ControlPoint,
    TheaterGroundObject,
)
from game.theater.iadsnetwork.iadsexplain import LinkTone
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    EwrGroundObject,
    IadsGroundObject,
    NavalGroundObject,
)
from game.utils import Heading
from qt_ui.windows.pilot.common import (
    ACCENT,
    AMBER,
    BAR_TRACK,
    GREEN,
    RED,
    TEXT_LABEL,
)

#: The three states a site's units can be in, in the order the bar stacks them.
ALIVE_INK = GREEN
REPAIRING_INK = AMBER
DESTROYED_INK = RED

#: The fill behind a chip, per tone. Dim enough to sit on a card without shouting.
TONE_INK = {
    LinkTone.GOOD: GREEN,
    LinkTone.WARN: AMBER,
    LinkTone.BAD: RED,
    LinkTone.INFO: ACCENT,
}


class HealthBar(QWidget):
    """Alive, repairing and destroyed in one bar.

    Three numbers rather than a fraction: a battery with four wrecks and two units
    coming back is not the same site as one with six wrecks, and the difference is
    what the player is deciding about.
    """

    def __init__(
        self,
        alive: int,
        repairing: int,
        total: int,
        width: int = 200,
        height: int = 6,
    ) -> None:
        super().__init__()
        self.alive = alive
        self.repairing = repairing
        self.total = max(total, 1)
        self.setFixedSize(width, height)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2

        track = QPainterPath()
        track.addRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.fillPath(track, QColor(BAR_TRACK))

        left = 0.0
        for count, ink in ((self.alive, ALIVE_INK), (self.repairing, REPAIRING_INK)):
            if count <= 0:
                continue
            width = self.width() * count / self.total
            segment = QPainterPath()
            segment.addRoundedRect(left, 0, width, self.height(), radius, radius)
            painter.fillPath(segment, QColor(ink))
            left += width
        painter.end()


class Compass(QWidget):
    """The heading as a dial with a needle.

    Drawn rather than a rotated pixmap: the pixmap was a 32 px arrow that lost a pixel
    of itself at every angle that was not a multiple of ninety degrees.
    """

    def __init__(self, heading: Heading, size: int = 32) -> None:
        super().__init__()
        self.heading = heading
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_heading(self, heading: Heading) -> None:
        self.heading = heading
        self.update()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(1, 1, self.width() - 2, self.height() - 2)

        painter.setPen(QPen(QColor(TEXT_LABEL), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(box)

        centre = box.center()
        radians = math.radians(self.heading.degrees)
        reach = box.width() / 2 - 3
        tip = QPointF(
            centre.x() + math.sin(radians) * reach,
            centre.y() - math.cos(radians) * reach,
        )
        needle = QPen(QColor(ACCENT), 2)
        needle.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(needle)
        painter.drawLine(centre, tip)
        painter.end()


def kind_of(ground_object: TheaterGroundObject) -> str:
    """What this objective is, in the words the map uses for it."""
    if isinstance(ground_object, BuildingGroundObject):
        return ground_object.category.upper()
    if isinstance(ground_object, NavalGroundObject):
        return "NAVAL"
    if isinstance(ground_object, IadsGroundObject):
        if ground_object.carries_gps_jammer:
            return "GPS JAMMER"
        if isinstance(ground_object, EwrGroundObject):
            return "EWR"
        return "SAM"
    return "ARMOR"


#: The reach of an air-defence site, in the words a player would use for it. The task
#: is what the campaign picked the site for, and it survives whatever is bought there
#: later, so it says more than the class the objective was created as.
TASK_NAMES = {
    GroupTask.LORAD: "LONG RANGE",
    GroupTask.MERAD: "MEDIUM RANGE",
    GroupTask.SHORAD: "SHORT RANGE",
    GroupTask.AAA: "AAA",
    GroupTask.EARLY_WARNING_RADAR: "RADAR",
    GroupTask.POINT_DEFENSE: "POINT DEFENCE",
}


def owner_of(control_point: ControlPoint) -> str:
    if control_point.captured.is_neutral:
        return "NEUTRAL"
    return "BLUE" if control_point.captured.is_blue else "RED"


def kind_chip_text(ground_object: TheaterGroundObject, cp: ControlPoint) -> str:
    parts = [kind_of(ground_object)]
    # A jamming site is named by what it does; the slot the campaign put it in says
    # nothing about its reach.
    task: Optional[GroupTask] = (
        None if parts[0] == "GPS JAMMER" else getattr(ground_object, "task", None)
    )
    reach = TASK_NAMES.get(task) if task is not None else None
    if reach is not None and reach != parts[0]:
        parts.append(reach)
    parts.append(owner_of(cp))
    return " · ".join(parts)
