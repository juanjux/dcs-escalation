"""Squadron rows, totals and sorting exclude aircraft sold this turn."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.ato import FlightType
from game.squadrons import Squadron
from qt_ui.models import AirWingModel
from qt_ui.widgets.squadroninventory import aircraft_on_hand


@pytest.fixture(scope="module")
def app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _squadron(name: str = "Sold squadron", owned: int = 4, pending: int = -4) -> Any:
    squadron = MagicMock(spec=Squadron)
    squadron.name = name
    squadron.nickname = None
    squadron.owned_aircraft = owned
    squadron.pending_deliveries = pending
    squadron.aircraft = SimpleNamespace(display_name="MiG-29S", dcs_id="MiG-29S")
    squadron.location = SimpleNamespace(name="Origin", is_fleet=False)
    squadron.destination = SimpleNamespace(name="Destination")
    squadron.primary_task = FlightType.BARCAP
    squadron.cohesion = None
    squadron.friendship_in_play = False
    squadron.fit_for_duty = [None] * 2
    squadron.living_pilots = [None] * 2
    squadron.untasked_crewed_aircraft = 0
    squadron.coalition = SimpleNamespace(
        game=SimpleNamespace(high_command_for=lambda side: SimpleNamespace(loans=[]))
    )
    return squadron


@pytest.mark.parametrize(
    "owned,pending,expected",
    [(4, -4, 0), (4, -1, 3), (4, 0, 4), (4, 2, 4), (0, 2, 0)],
)
def test_count_excludes_sales_but_not_incoming_purchases(
    owned: int, pending: int, expected: int
) -> None:
    assert aircraft_on_hand(_squadron(owned=owned, pending=pending)) == expected


@pytest.mark.parametrize("pending,expected", [(-4, "0"), (-1, "3"), (0, "4"), (2, "4")])
def test_painted_row_uses_current_count_and_keeps_transfer_visible(
    app: Any, pending: int, expected: str
) -> None:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QStyleOptionViewItem

    from qt_ui.widgets.squadrondelegate import SquadronDelegate

    model = QStandardItemModel()
    item = QStandardItem()
    item.setData(_squadron(pending=pending), AirWingModel.SquadronRole)
    model.appendRow(item)
    delegate = SquadronDelegate(MagicMock())
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 1400, 48)
    painter = MagicMock()

    delegate.paint(painter, option, model.index(0, 0))

    painted = [call.args[-1] for call in painter.drawText.call_args_list]
    assert expected in painted
    assert any("transfer to " in str(text) for text in painted)


def test_totals_and_sort_refresh_when_a_sale_changes(
    app: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QListView

    from qt_ui.widgets.squadrondelegate import SquadronDelegate
    from qt_ui.widgets.squadronpanel import (
        GroupedSquadronModel,
        SquadronFilterProxy,
        SquadronPanel,
    )

    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(SquadronPanel, "_settings", staticmethod(lambda: settings))
    sold = _squadron(pending=0)
    other = _squadron("Other squadron", owned=1, pending=0)
    model = QStandardItemModel()
    for squadron in (sold, other):
        item = QStandardItem()
        item.setData(squadron, AirWingModel.SquadronRole)
        model.appendRow(item)
    proxy = SquadronFilterProxy()
    proxy.setSourceModel(model)
    grouped = GroupedSquadronModel(proxy)
    view = QListView()
    view.setModel(grouped)
    view.setItemDelegate(SquadronDelegate(MagicMock()))
    panel = SquadronPanel(view, proxy, grouped)
    try:
        proxy.set_order("aircraft")
        assert panel.totals.text() == "2 squadrons · 5 aircraft"
        assert proxy.index(0, 0).data(AirWingModel.SquadronRole) is sold

        sold.pending_deliveries = -4
        model.dataChanged.emit(model.index(0, 0), model.index(0, 0))
        assert panel.totals.text() == "2 squadrons · 1 aircraft"
        assert proxy.index(0, 0).data(AirWingModel.SquadronRole) is other

        sold.pending_deliveries = 0
        model.dataChanged.emit(model.index(0, 0), model.index(0, 0))
        assert panel.totals.text() == "2 squadrons · 5 aircraft"
        assert proxy.index(0, 0).data(AirWingModel.SquadronRole) is sold

        sold.pending_deliveries = 2
        model.dataChanged.emit(model.index(0, 0), model.index(0, 0))
        assert panel.totals.text() == "2 squadrons · 5 aircraft"

        panel.filter_field.setText("Other")
        assert panel.totals.text() == "1 of 2 squadrons · 1 aircraft"
    finally:
        panel.close()
