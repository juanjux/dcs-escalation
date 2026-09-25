"""The location cheat destroys or revives everything at one location, and works out
again what the turn derives from what is standing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional, cast

from game.theater.locationcheat import destroy_all, revive_all
from game.theater.theatergroundobject import MotorpoolGroundObject


class _Unit:
    def __init__(self, alive: bool, repair: Optional[int] = None) -> None:
        self.alive = alive
        self.repair_turns_remaining = repair

    def kill(self, events: Any) -> None:
        self.alive = False

    def revive(self, events: Any) -> None:
        self.alive = True


class _Game:
    def __init__(self) -> None:
        self.zones: list[Any] = []
        self.stats: list[Any] = []
        self.game_stats = SimpleNamespace(update=self.stats.append)

    def compute_threat_zones(self, events: Any) -> None:
        self.zones.append(events)


class _Events:
    def __init__(self) -> None:
        self.motorpools: list[Any] = []

    def update_motorpools_at(self, *control_points: Any) -> None:
        self.motorpools.extend(control_points)


def _game() -> Any:
    return _Game()


def _events() -> Any:
    return _Events()


def _site(*units: _Unit) -> Any:
    return SimpleNamespace(groups=[SimpleNamespace(id=1, units=list(units))])


def _motorpool(armor: dict[str, int], *units: _Unit) -> Any:
    pool = MotorpoolGroundObject.__new__(MotorpoolGroundObject)
    pool.control_point = cast(Any, SimpleNamespace(base=SimpleNamespace(armor=armor)))
    pool.groups = [cast(Any, SimpleNamespace(id=7, units=list(units)))]
    pool.motorpool_unit_types = {7: cast(Any, "T-72B")}
    return pool


def test_destroying_kills_what_stands_and_says_how_many() -> None:
    units = [_Unit(True), _Unit(False), _Unit(True)]
    game = _game()

    assert destroy_all(game, _site(*units), _events()) == 2
    assert not any(unit.alive for unit in units)


def test_reviving_finishes_a_repair_under_way() -> None:
    units = [_Unit(True), _Unit(False, repair=2), _Unit(False)]
    game = _game()

    assert revive_all(game, _site(*units), _events()) == 2
    assert all(unit.alive for unit in units)
    assert all(unit.repair_turns_remaining is None for unit in units)


def test_the_threat_zones_are_worked_out_again() -> None:
    game = _game()
    events = _events()

    destroy_all(game, _site(_Unit(True)), events)
    revive_all(game, _site(_Unit(False)), events)

    assert game.zones == [events, events]
    assert game.stats == []


def test_a_motor_pool_takes_its_vehicles_out_of_the_base_reserve() -> None:
    """Otherwise the pool is filled again from the reserve the next time it is
    drawn, and the cheat does nothing."""
    armor = {"T-72B": 10}
    pool = _motorpool(armor, _Unit(True), _Unit(True))
    game = _game()
    events = _events()

    assert destroy_all(game, pool, events) == 2

    assert armor == {"T-72B": 8}
    assert events.motorpools == [pool.control_point]
    assert game.stats == [game]


def test_reviving_a_motor_pool_puts_them_back() -> None:
    armor = {"T-72B": 8}
    pool = _motorpool(armor, _Unit(False), _Unit(True))
    game = _game()

    assert revive_all(game, pool, _events()) == 1

    assert armor == {"T-72B": 9}
