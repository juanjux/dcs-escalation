"""The location cheat destroys or revives everything at one location."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from game.theater.locationcheat import destroy_all, revive_all

EVENTS: Any = SimpleNamespace()


class _Unit:
    def __init__(self, alive: bool, repair: Optional[int] = None) -> None:
        self.alive = alive
        self.repair_turns_remaining = repair

    def kill(self, events: Any) -> None:
        self.alive = False

    def revive(self, events: Any) -> None:
        self.alive = True


def test_destroying_kills_what_stands_and_says_how_many() -> None:
    units = [_Unit(True), _Unit(False), _Unit(True)]
    site: Any = SimpleNamespace(units=units)

    assert destroy_all(site, EVENTS) == 2
    assert not any(unit.alive for unit in units)


def test_reviving_finishes_a_repair_under_way() -> None:
    units = [_Unit(True), _Unit(False, repair=2), _Unit(False)]
    site: Any = SimpleNamespace(units=units)

    assert revive_all(site, EVENTS) == 2
    assert all(unit.alive for unit in units)
    assert all(unit.repair_turns_remaining is None for unit in units)
