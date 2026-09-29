"""Flight rows show the current start type without overlapping the aircraft name."""

import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from game.ato.flighttype import FlightType
from game.ato.starttype import StartType
from qt_ui.models import PackageModel
from qt_ui.widgets.atodelegates import (
    FLIGHT_ROW_HEIGHT,
    LINE_1,
    LINE_2,
    MARGIN,
    FlightRowDelegate,
)


@pytest.fixture(scope="module")
def qt_app() -> Any:
    yield QApplication.instance() or QApplication([])


class RecordingPainter(QPainter):
    def __init__(self, image: QImage) -> None:
        super().__init__(image)
        self.texts: list[tuple[str, QRect]] = []

    def drawText(self, *args: Any) -> Any:
        if isinstance(args[0], QRect):
            rect = QRect(args[0])
        else:
            x, baseline, text = args
            metrics = self.fontMetrics()
            rect = QRect(
                x,
                baseline - metrics.ascent(),
                metrics.horizontalAdvance(text),
                metrics.height(),
            )
        self.texts.append((args[-1], rect))
        return super().drawText(*args)


@pytest.mark.parametrize("width", [380, 540, 1060])
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("clients", [0, 1, 4])
@pytest.mark.parametrize("start_type", list(StartType))
def test_start_badge_is_current_and_right_aligned(
    qt_app: Any, width: int, selected: bool, clients: int, start_type: StartType
) -> None:
    now = datetime(2026, 9, 29, 9, 25)
    flight = SimpleNamespace(
        start_type=start_type,
        flight_type=FlightType.DEAD,
        unit_type=SimpleNamespace(display_name="F/A-18C Hornet (Lot 20)"),
        count=1,
        squadron=SimpleNamespace(name="VMFA-21"),
        departure=SimpleNamespace(name="CVN-72 Abraham Lincoln"),
        client_count=clients,
        flight_plan=SimpleNamespace(takeoff_time=lambda: now, landing_time=now),
    )
    model = QStandardItemModel()
    item = QStandardItem()
    item.setData(flight, PackageModel.FlightRole)
    model.appendRow(item)
    delegate = FlightRowDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, width, FLIGHT_ROW_HEIGHT)
    if selected:
        option.state |= QStyle.StateFlag.State_Selected

    # Repainting after an edit must read the updated value from the same flight.
    for current in (start_type, StartType.IN_FLIGHT):
        flight.start_type = current
        image = QImage(width, FLIGHT_ROW_HEIGHT, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = RecordingPainter(image)
        try:
            delegate.paint(painter, option, model.index(0, 0))
            texts = dict(painter.texts)
            badge = texts[current.value]
            task = texts[str(FlightType.DEAD)]
            assert badge.right() == width - MARGIN - 1
            assert badge.top() == LINE_2 - 11
            assert task.bottom() < badge.top()
            assert all(
                rect.right() < badge.left()
                for text, rect in painter.texts
                if text.startswith("VMFA") or "player seat" in text
            )
            assert all(
                rect.right() < task.left()
                for text, rect in painter.texts
                if text.startswith(("F/A-18", "×"))
            )
            assert any("player seat" in text for text in texts) == bool(clients)
            assert (
                delegate.sizeHint(option, model.index(0, 0)).height()
                == FLIGHT_ROW_HEIGHT
            )
            assert any(
                rect.top() > LINE_1
                for text, rect in painter.texts
                if text.startswith("dep")
            )
        finally:
            painter.end()
