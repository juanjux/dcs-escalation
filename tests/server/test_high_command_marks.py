"""The map's High Command marks: one per point an order is about."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.highcommand.campaign import Task
from game.highcommand.orders import HighCommand, Order
from game.highcommand.prizes import Prize
from game.server.highcommand.models import HighCommandMarkJs

TURN = 14


def _at(lat: float) -> Any:
    return SimpleNamespace(latlng=lambda: SimpleNamespace(lat=lat, lng=-60.0))


def _order(
    objective: str, tier: int, expires_on: int, task: Task | None = None
) -> Order:
    return Order(
        objective=objective,
        tier=tier,
        ordered_on=TURN - 1,
        expires_on=expires_on,
        prize=Prize("cash", 5, False, "Cash.", ()),
        task=task,
        base="Punta Arenas" if task else "",
    )


def _game(*orders: Order, enabled: bool = True) -> Any:
    return SimpleNamespace(
        turn=TURN,
        settings=SimpleNamespace(high_command_enabled=enabled, high_command_orders=3),
        high_command=HighCommand(orders=list(orders)),
        theater=SimpleNamespace(
            ground_objects=[SimpleNamespace(name="TURKEY", position=_at(-54.0))],
            controlpoints=[SimpleNamespace(name="Punta Arenas", position=_at(-53.0))],
        ),
    )


def test_a_base_asked_twice_is_one_mark_with_the_soonest_turns() -> None:
    game = _game(
        _order("TURKEY", 2, TURN + 3),
        _order("Punta Arenas (OCA/Aircraft)", 1, TURN + 3, Task.AIRCRAFT),
        _order("Punta Arenas (OCA/Runway)", 0, TURN + 1, Task.RUNWAY),
    )

    marks = {mark.name: mark for mark in HighCommandMarkJs.all_in_game(game)}

    assert set(marks) == {"TURKEY", "Punta Arenas"}
    base = marks["Punta Arenas"]
    assert (base.orders, base.soonest, base.last_turn) == (2, 1, True)
    assert base.position.lat == -53.0
    turkey = marks["TURKEY"]
    assert (turkey.orders, turkey.soonest, turkey.last_turn) == (1, 3, False)
    assert turkey.tooltip == "High Command order · high tier · Cash."


def test_an_objective_no_longer_on_the_map_gets_no_mark() -> None:
    assert HighCommandMarkJs.all_in_game(_game(_order("HERRING", 0, TURN + 2))) == []


def test_with_the_high_command_off_there_are_no_marks() -> None:
    game = _game(_order("TURKEY", 2, TURN + 3), enabled=False)

    assert HighCommandMarkJs.all_in_game(game) == []
