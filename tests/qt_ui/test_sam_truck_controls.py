"""Truck purchases expose the shared allowance and refresh after buying."""

import os
from types import SimpleNamespace as NS
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox
import pytest

from game.groundmovement.samtrucks import sam_truck_options
from game.theater.player import Player
from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_sam_trucks import battery, buy  # noqa: F401


@pytest.fixture
def app() -> Any:
    return QApplication.instance() or QApplication([])


def test_controls_obey_remaining_shared_limit_and_refresh(
    app: Any, battery: Any
) -> None:
    w = battery
    calls = []
    context: Any = NS(
        game=w.game,
        ground_object=w.sam,
        _viewer=Player.BLUE,
        game_model=NS(
            ground_movement_commands=NS(buy_sam_trucks=lambda *args: calls.append(args))
        ),
        _rebuild=lambda: calls.append("refresh"),
    )
    holder = QGroundObjectMenu._towing_truck_purchase(
        context, sam_truck_options(w.game, w.sam.id, Player.BLUE)
    )
    spin = holder.findChild(QSpinBox, "sam-towing-truck-quantity")
    purchase = holder.findChild(QPushButton, "buy-sam-towing-trucks")
    assert spin is not None and purchase is not None
    assert spin.maximum() == 4 and purchase.isEnabled()
    spin.setValue(3)
    assert "$9M" in purchase.text()
    purchase.click()
    assert calls[0][-2:] == ("Truck Ural-375", 3) and calls[1] == "refresh"
    holder.close()
    holder.deleteLater()


def test_controls_disable_at_cap_and_when_unaffordable(app: Any, battery: Any) -> None:
    w = battery
    context: Any = NS(game=w.game, ground_object=w.sam, _viewer=Player.BLUE)
    w.a.coalition.budget = 0
    holder = QGroundObjectMenu._towing_truck_purchase(
        context, sam_truck_options(w.game, w.sam.id, Player.BLUE)
    )
    purchase = holder.findChild(QPushButton, "buy-sam-towing-trucks")
    assert purchase is not None and not purchase.isEnabled()
    holder.deleteLater()
    w.a.coalition.budget = 100
    buy(w, 4)
    holder = QGroundObjectMenu._towing_truck_purchase(
        context, sam_truck_options(w.game, w.sam.id, Player.BLUE)
    )
    purchase = holder.findChild(QPushButton, "buy-sam-towing-trucks")
    assert purchase is not None and not purchase.isEnabled()
    assert "limit" in purchase.toolTip()
    holder.deleteLater()
