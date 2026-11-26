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


def test_package_list_sorts_and_paints_the_selected_dependency(qt_app: Any) -> None:
    from unittest.mock import Mock
    from uuid import uuid4
    from PySide6.QtCore import Qt
    from game.ato.airtaaskingorder import AirTaskingOrder
    from game.ato.package import Package
    from game.db import Database
    from qt_ui.models import AtoModel
    from qt_ui.widgets.ato import QPackageList
    from qt_ui.widgets.atodelegates import PackageRowDelegate, ROW_HEIGHT

    db: Database[Any] = Database()

    def make_package(name: str, when: datetime) -> Package:
        target: Any = SimpleNamespace(name=name)
        package = Package(target, db)
        package.time_over_target = when
        return package

    follow = make_package("Gazelle", datetime(2026, 1, 1, 20, 52, 55))
    source = make_package("Boulder City", datetime(2026, 1, 1, 21))
    pending = make_package("Unscheduled", datetime.min)
    sweep: Any = SimpleNamespace(
        id=uuid4(),
        flight_type=FlightType.SWEEP,
        package=source,
        flight_plan=SimpleNamespace(tot=datetime(2026, 1, 1, 20, 45)),
        count=1,
        missing_pilots=0,
        client_count=0,
    )
    source.flights.append(sweep)
    db.add(sweep.id, sweep)
    follow.prerequisite_flights.append(sweep.id)
    gm: Any = Mock(game=None)
    source_model = AtoModel(gm, AirTaskingOrder([pending, source, follow]))
    view = QPackageList(gm, source_model)
    model = view.model()

    def rows() -> list[Package]:
        return [
            model.index(i, 0).data(AtoModel.PackageRole)
            for i in range(model.rowCount())
        ]

    try:
        assert rows() == [follow, source, pending]
        view.setCurrentIndex(model.index(0, 0))
        assert view.package_model(view.currentIndex()).package is follow
        view.package_model(model.index(1, 0)).set_tot(datetime(2026, 1, 1, 20, 50))
        assert rows() == [source, follow, pending]
        assert view.selected_item is follow and view.currentIndex().row() == 1

        idx = view.currentIndex()
        label = "Depends on: Fighter Sweep #1 Boulder City TOT 20:50"
        assert idx.data(Qt.ItemDataRole.ToolTipRole) == label
        delegate = PackageRowDelegate()
        option = QStyleOptionViewItem()
        height = delegate.sizeHint(option, idx).height()
        assert (
            height > ROW_HEIGHT
            and delegate.sizeHint(option, model.index(0, 0)).height() == ROW_HEIGHT
        )
        option.rect = QRect(0, 0, 650, height)
        image = QImage(650, height, QImage.Format.Format_ARGB32)
        painter = RecordingPainter(image)
        try:
            delegate.paint(painter, option, idx)
            assert dict(painter.texts)[label].bottom() < height
        finally:
            painter.end()
        view.delete_package(idx)
        assert rows() == [source, pending]
    finally:
        view.deleteLater()


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
