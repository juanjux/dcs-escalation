"""A squadron with aircraft does not relocate off a damaged runway.

The mission leaves out any flight from a damaged runway, ferries included, and the
squadron arrived at its new base at the end of the turn all the same: aircraft trapped
behind a cratered runway walked out of it.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from game.migrator import Migrator
from game.squadrons.squadron import Squadron

NOW = datetime(2026, 9, 21, 20, 0)


def _base(name: str, operational: bool) -> Any:
    return SimpleNamespace(
        name=name,
        runway_is_operational=lambda: operational,
        unclaimed_parking=lambda parking_type: 99,
        can_operate=lambda aircraft: True,
    )


def _squadron(location: Any, aircraft: int) -> Any:
    planned: list[datetime] = []
    return SimpleNamespace(
        location=location,
        destination=None,
        owned_aircraft=aircraft,
        expected_size_next_turn=aircraft,
        aircraft=SimpleNamespace(helicopter=False, lha_capable=False, flyable=False),
        coalition=SimpleNamespace(
            game=SimpleNamespace(settings=SimpleNamespace(ground_start_ai_planes=True))
        ),
        replan_ferry_flights=planned.append,
        planned=planned,
    )


def test_a_squadron_with_aircraft_cannot_leave_a_damaged_runway() -> None:
    squadron = _squadron(_base("Rio Gallegos", operational=False), aircraft=4)

    with pytest.raises(RuntimeError, match="runway is damaged"):
        Squadron.plan_relocation(squadron, _base("Punta Arenas", True), NOW)

    assert squadron.destination is None
    assert squadron.planned == []


def test_an_empty_squadron_can_still_leave_it() -> None:
    """Sell the aircraft and the pilots can go: nothing has to take off."""
    squadron = _squadron(_base("Rio Gallegos", operational=False), aircraft=0)
    destination = _base("Punta Arenas", True)

    Squadron.plan_relocation(squadron, destination, NOW)

    assert squadron.destination is destination
    assert squadron.planned == [NOW]


def test_an_order_already_given_off_a_damaged_runway_is_cancelled_on_load() -> None:
    stranded = _squadron(_base("Rio Gallegos", operational=False), aircraft=4)
    moving = _squadron(_base("Ushuaia", operational=True), aircraft=2)
    emptied = _squadron(_base("Rio Gallegos", operational=False), aircraft=0)
    cancelled: list[Any] = []
    for squadron in (stranded, moving, emptied):
        squadron.destination = _base("Punta Arenas", True)
        squadron.cancel_ferry_flights = lambda s=squadron: cancelled.append(s)
    wing = SimpleNamespace(iter_squadrons=lambda: iter([stranded, moving, emptied]))
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(
        blue=SimpleNamespace(air_wing=wing),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter([]))),
    )

    migrator._cancel_relocations_off_damaged_runways()

    assert cancelled == [stranded]
    assert stranded.destination is None
    assert moving.destination is not None and emptied.destination is not None
