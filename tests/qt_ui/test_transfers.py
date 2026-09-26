"""Regression tests for a standalone UI feature."""

from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


from game.theater import Player


def test_transfers_filter_and_cancel_the_source_row(app: Any) -> None:
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from qt_ui.models import TransferModel
    from qt_ui.windows.intel.transfers import TransfersPane

    class Model(QStandardItemModel):
        def cancel_transfer_at_index(self, index: Any) -> None:
            self.removeRow(index.row())

    model: Any = Model()
    for name, side in (("Red", Player.RED), ("Blue", Player.BLUE)):
        item = QStandardItem(name)
        item.setData(
            SimpleNamespace(player=side, description="To base"),
            TransferModel.TransferRole,
        )
        model.appendRow(item)
    pane = TransfersPane(model)
    assert pane.proxy.rowCount() == 1
    pane.view.setCurrentIndex(pane.proxy.index(0, 0))
    assert pane.cancel.isEnabled()
    pane.cancel_selected()
    assert model.rowCount() == 1
    assert model.item(0).text() == "Red"
    pane.show_side(Player.RED)
    pane.view.setCurrentIndex(pane.proxy.index(0, 0))
    assert not pane.cancel.isEnabled()
    pane.close()
