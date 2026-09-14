"""The mission header that sits above the flight dialog's tabs.

The dialog used to open on a form. What is being edited -- which aircraft, whose
squadron, which package, where it is going -- was spread across three tabs, so the
first thing you did on opening it was read around to find out. The header answers all
of that before you pick a tab, and it stays put while you change them.

The right-hand side is an attention stack: anything that needs a decision -- an empty
seat, a fuel shortfall, a start type that breaks balance -- is a coloured pill, and
clicking one goes to the tab that fixes it. Nothing you have to hunt for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from game.ato.flight import Flight
from game.ato.fuelestimate import estimate_fuel
from game.ato.starttype import StartType
from game.utils import meters
from qt_ui.uiconstants import AIRCRAFT_ICONS
from qt_ui.widgets.squadrondelegate import chip_colours

#: Tab indices in QFlightPlanner, so a pill knows where to send you.
GENERAL_TAB = 0
PAYLOAD_TAB = 1
WAYPOINTS_TAB = 2

HEADER_HEIGHT = 100

BACKGROUND = QColor("#14202B")
BORDER = QColor("#1D2731")

TEXT_PRIMARY = QColor("#F2F7FA")
TEXT_BASE = QColor("#D3DFE8")
TEXT_SECONDARY = QColor("#B7C6D2")
TEXT_TERTIARY = QColor("#8E9DAA")
TEXT_LABEL = QColor("#7C8B99")
TARGET = QColor("#E0A86B")

ICON_X = 20
ICON_Y = 20
CHIP_X = 126
CHIP_Y = 24
CHIP_HEIGHT = 20
CHIP_RADIUS = 4
CHIP_PADDING = 8

#: Baselines, measured from the top of the header. The three lines are set far
#: enough apart that the 20px type on the first does not sit into the second.
LINE_1_BASELINE = 40
LINE_2_Y = 62
LINE_3_Y = 84

#: Severity, coldest to hottest. The pill's two colours are background and text.
PILL_COLOURS = {
    "ok": (QColor("#23372D"), QColor("#86C39A")),
    "warn": (QColor("#3B2D21"), QColor("#E0A86B")),
    "bad": (QColor("#3B2523"), QColor("#D9645E")),
}


def _mono(size: int, bold: bool = False) -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(size)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _clock(when: Optional[datetime]) -> str:
    return when.strftime("%H:%M:%S") if when is not None else "--:--:--"


class FlightIdentity(QWidget):
    """The three lines: what flies, whose it is, and where it goes."""

    def __init__(self, flight: Flight) -> None:
        super().__init__()
        self.flight = flight
        self.setMinimumHeight(HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        flight = self.flight
        x = self._paint_banner(painter)
        x = self._paint_task_chip(painter, max(x, CHIP_X))
        self._paint_type(painter, x + 10)
        self._paint_ownership(painter)
        self._paint_route(painter)

    def _paint_banner(self, painter: QPainter) -> int:
        """The aircraft silhouette, when we have one for this type."""
        # Slashes are not filenames, so the icons are stored with them replaced --
        # the same lookup the ATO panel does.
        name = self.flight.unit_type.dcs_id.replace("/", "_")
        pixmap: Optional[QPixmap] = AIRCRAFT_ICONS.get(name)
        if pixmap is None:
            return ICON_X
        painter.drawPixmap(ICON_X, ICON_Y, pixmap)
        return ICON_X + pixmap.width() + 14

    def _paint_task_chip(self, painter: QPainter, x: int) -> int:
        fill, text = chip_colours(self.flight.flight_type)
        label = str(self.flight.flight_type).upper()
        font = _sans(11, QFont.Weight.Bold)
        width = QFontMetrics(font).horizontalAdvance(label) + CHIP_PADDING * 2
        rect = QRect(x, CHIP_Y, width, CHIP_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, CHIP_RADIUS, CHIP_RADIUS)
        painter.setFont(font)
        painter.setPen(text)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        return x + width

    def _paint_type(self, painter: QPainter, x: int) -> None:
        name = str(self.flight.unit_type)
        font = _sans(20, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(TEXT_PRIMARY)
        painter.drawText(x, LINE_1_BASELINE, name)
        x += QFontMetrics(font).horizontalAdvance(name) + 10
        painter.setFont(_mono(16))
        painter.setPen(TEXT_TERTIARY)
        painter.drawText(x, LINE_1_BASELINE, f"×{self.flight.count}")

    def _paint_ownership(self, painter: QPainter) -> None:
        """Squadron, package, and the time the whole thing is built around."""
        flight = self.flight
        x = ICON_X
        squadron = flight.squadron
        x = self._run(
            painter, x, str(squadron.name), _sans(13), TEXT_SECONDARY, LINE_2_Y
        )
        if squadron.nickname:
            x = self._run(
                painter,
                x + 6,
                f'"{squadron.nickname}"',
                _sans(13),
                TEXT_LABEL,
                LINE_2_Y,
            )
        x = self._run(painter, x + 16, "Package", _sans(13), TEXT_TERTIARY, LINE_2_Y)
        x = self._run(
            painter,
            x + 6,
            str(flight.package.target.name),
            _sans(13),
            TEXT_SECONDARY,
            LINE_2_Y,
        )
        x = self._run(painter, x + 16, "TOT", _sans(13), TEXT_TERTIARY, LINE_2_Y)
        self._run(painter, x + 6, _clock(self._tot()), _mono(13), TEXT_BASE, LINE_2_Y)

    def _paint_route(self, painter: QPainter) -> None:
        """Departure to target to arrival, with how far it is and when it leaves."""
        flight = self.flight
        x = ICON_X
        small = _sans(12)
        x = self._run(
            painter, x, str(flight.departure.name), small, TEXT_LABEL, LINE_3_Y
        )
        x = self._run(painter, x + 6, "→", small, TEXT_LABEL, LINE_3_Y)
        x = self._run(
            painter,
            x + 6,
            str(flight.package.target.name),
            _sans(12, QFont.Weight.Medium),
            TARGET,
            LINE_3_Y,
        )
        x = self._run(painter, x + 6, "→", small, TEXT_LABEL, LINE_3_Y)
        x = self._run(
            painter, x + 6, str(flight.arrival.name), small, TEXT_LABEL, LINE_3_Y
        )

        distance = meters(
            flight.departure.position.distance_to_point(flight.package.target.position)
        ).nautical_miles
        x = self._run(
            painter, x + 16, f"{distance:.0f} nm", _mono(12), TEXT_TERTIARY, LINE_3_Y
        )
        self._run(
            painter,
            x + 16,
            f"dep {_clock(self._takeoff())}",
            _mono(12),
            TEXT_TERTIARY,
            LINE_3_Y,
        )

    def _run(
        self, painter: QPainter, x: int, text: str, font: QFont, colour: QColor, y: int
    ) -> int:
        """Draw one run of text and report where the next one starts."""
        painter.setFont(font)
        painter.setPen(colour)
        painter.drawText(x, y, text)
        return x + QFontMetrics(font).horizontalAdvance(text)

    def _tot(self) -> Optional[datetime]:
        try:
            return self.flight.flight_plan.tot
        except Exception:
            return None

    def _takeoff(self) -> Optional[datetime]:
        try:
            return self.flight.flight_plan.takeoff_time()
        except Exception:
            return None


class AttentionPill(QToolButton):
    """One thing that wants a decision, and the tab that takes it."""

    def __init__(self, text: str, severity: str, tab: int) -> None:
        super().__init__()
        self.tab = tab
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        fill, colour = PILL_COLOURS[severity]
        self.setStyleSheet(
            f"QToolButton {{ background: {fill.name()}; color: {colour.name()};"
            f" border: none; border-radius: 4px; padding: 0 10px;"
            f" font-size: 11px; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {fill.lighter(120).name()}; }}"
        )
        self.setFixedHeight(24)


class FlightHeader(QFrame):
    """Identity on the left, the things that need deciding on the right."""

    jump_to_tab = Signal(int)
    #: Another flight of the same package was picked from the header's selector.
    switch_to_flight = Signal(object)

    def __init__(self, flight: Flight) -> None:
        super().__init__()
        self.flight = flight
        self.setFixedHeight(HEADER_HEIGHT)
        self.setStyleSheet(
            f"QFrame {{ background: {BACKGROUND.name()};"
            f" border: 1px solid {BORDER.name()}; border-radius: 3px; }}"
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 14, 0)
        self.identity = FlightIdentity(flight)
        layout.addWidget(self.identity, 1)

        self.pills = QVBoxLayout()
        self._add_flight_picker(layout)
        # Three pills of 24 with 6 between them is 84, which is what a 100-high
        # header leaves once these margins are taken off.
        self.pills.setContentsMargins(0, 8, 0, 8)
        self.pills.setSpacing(6)
        self.pills.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(self.pills)
        self.setLayout(layout)

        self.refresh()

    def _add_flight_picker(self, layout: QHBoxLayout) -> None:
        """A way to the package's other flights without leaving the dialog.

        Omitted for a package of one, where it would be a control with one choice.
        """
        flights = list(self.flight.package.flights)
        if len(flights) < 2:
            return

        picker = QComboBox()
        picker.setFixedHeight(24)
        picker.setStyleSheet(
            "QComboBox { background: #26343F; color: #B7C6D2;"
            " border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 8px;"
            " font-size: 11.5px; }"
        )
        picker.setToolTip("Edit another flight in this package.")
        for other in flights:
            label = f"{other.flight_type} · {other.unit_type} ×{other.count}"
            picker.addItem(label, other)
        picker.setCurrentIndex(flights.index(self.flight))
        picker.activated.connect(
            lambda index: self.switch_to_flight.emit(picker.itemData(index))
        )

        column = QVBoxLayout()
        column.setContentsMargins(0, 10, 10, 0)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)
        column.addWidget(picker)
        layout.addLayout(column)
        self.flight_picker = picker

    def refresh(self) -> None:
        """Rebuild the identity and the pills from the flight as it stands now."""
        self.identity.update()
        while self.pills.count():
            item = self.pills.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hide before unparenting, and unparent before scheduling the delete.
                # deleteLater only runs on the next turn of the event loop, and until
                # it does the old pill is still painted at whatever geometry it had,
                # which is across the top of the header -- so it has to go. But a
                # *visible* widget with no parent is a top-level window, and Windows
                # duly opened one for a few milliseconds every time the header
                # refreshed, which is every time the TOT offset moves.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for text, severity, tab in self._attention():
            pill = AttentionPill(text, severity, tab)
            pill.clicked.connect(lambda _=False, t=tab: self.jump_to_tab.emit(t))
            self.pills.addWidget(pill)
        self.pills.addStretch()

    def _attention(self) -> list[tuple[str, str, int]]:
        """What is wrong with this flight, worst first."""
        found: list[tuple[str, str, int]] = []

        missing = self.flight.missing_pilots
        if missing:
            seats = "seat" if missing == 1 else "seats"
            found.append((f"{missing} {seats} unassigned", "warn", GENERAL_TAB))

        estimate = estimate_fuel(self.flight)
        if estimate is not None and not estimate.enough:
            short = estimate.required.pounds - estimate.carried.pounds
            found.append((f"short {short:,.0f} lb of fuel", "bad", WAYPOINTS_TAB))

        if self.flight.start_type is not StartType.COLD:
            found.append((f"{self.flight.start_type.value} start", "warn", GENERAL_TAB))

        # Worst first, so the eye lands on the thing that matters most.
        order = {"bad": 0, "warn": 1, "ok": 2}
        return sorted(found, key=lambda item: order[item[1]])
