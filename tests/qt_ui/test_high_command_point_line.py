"""The line a point's window shows when the point is an order's objective."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.highcommand.campaign import Task
from game.highcommand.orders import HighCommand, Order
from game.highcommand.prizes import Prize

TURN = 14


def _order(objective: str, expires_on: int, task: Task | None = None) -> Order:
    return Order(
        objective=objective,
        tier=1,
        ordered_on=TURN - 1,
        expires_on=expires_on,
        prize=Prize("cash", 5, True, "Cash.", ()),
        task=task,
        base="Punta Arenas" if task else "",
    )


ORDERS = [
    _order("TURKEY", TURN + 3),
    _order("Punta Arenas (OCA/Aircraft)", TURN + 3, Task.AIRCRAFT),
    _order("Punta Arenas (OCA/Runway)", TURN + 1, Task.RUNWAY),
]


def _game(enabled: bool = True) -> Any:
    return SimpleNamespace(
        turn=TURN,
        settings=SimpleNamespace(high_command_enabled=enabled, high_command_orders=3),
        high_command=HighCommand(orders=list(ORDERS)),
    )


@pytest.fixture
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_a_site_and_a_base_find_their_own_orders() -> None:
    from qt_ui.windows.highcommand.pointline import (
        orders_at_base,
        orders_at_ground_object,
    )

    game = _game()

    assert [o.objective for o in orders_at_ground_object(game, "TURKEY")] == ["TURKEY"]
    assert len(orders_at_base(game, "Punta Arenas")) == 2
    assert orders_at_ground_object(game, "Punta Arenas") == []


def test_no_line_without_an_order_or_with_the_high_command_off(qt_app: Any) -> None:
    from qt_ui.windows.highcommand.pointline import objective_line

    assert objective_line(_game(), [], print) is None
    assert objective_line(_game(enabled=False), ORDERS[:1], print) is None


def test_one_order_opens_from_anywhere_on_the_line(qt_app: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from qt_ui.windows.highcommand.pointline import objective_line

    opened: list[str] = []
    line = objective_line(_game(), ORDERS[:1], opened.append)
    assert line is not None

    QTest.mouseClick(line, Qt.MouseButton.LeftButton)

    assert opened == ["TURKEY"]


def test_a_base_with_two_orders_has_a_link_for_each(qt_app: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from qt_ui.windows.highcommand.pointline import Link, objective_line

    opened: list[str] = []
    line = objective_line(_game(), ORDERS[1:], opened.append, base=True)
    assert line is not None

    links = line.findChildren(Link)
    for link in links:
        QTest.mouseClick(link, Qt.MouseButton.LeftButton)
    QTest.mouseClick(line, Qt.MouseButton.LeftButton)

    assert opened == ["Punta Arenas (OCA/Aircraft)", "Punta Arenas (OCA/Runway)"]
