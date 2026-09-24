"""A relocation and its ferry flights stay together.

Deleting the package that held a squadron's ferries left the relocation standing: the
squadron still arrived at the end of the turn having flown nothing, and ordering the
relocation again was ignored as one already under way, with an answer that all was well.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.agent import planner, views
from game.ato.flighttype import FlightType
from game.squadrons.squadron import Squadron

NOW = datetime(2026, 9, 25, 20, 0)
GAME: Any = SimpleNamespace()


def _flight(squadron: Any, task: FlightType = FlightType.FERRY) -> Any:
    return SimpleNamespace(squadron=squadron, flight_type=task)


def _package(*flights: Any) -> Any:
    return SimpleNamespace(
        target=SimpleNamespace(name="Ushuaia"), flights=list(flights)
    )


def _coalition(*packages: Any, squadrons: tuple[Any, ...] = ()) -> Any:
    held = list(packages)
    ato = SimpleNamespace(
        packages=held, remove_package=held.remove, clear=lambda: held.clear()
    )
    return SimpleNamespace(
        ato=ato, air_wing=SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    )


class _Squadron:
    """Hashable, as the real one is: the ferries are gathered by squadron."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.destination: Any = "Ushuaia"
        self.owned_aircraft = 4

    def __str__(self) -> str:
        return self.name


def _relocating(name: str) -> Any:
    return _Squadron(name)


@pytest.fixture
def side(monkeypatch: pytest.MonkeyPatch) -> Any:
    chosen: dict[str, Any] = {}
    monkeypatch.setattr(
        views, "coalition_for_side", lambda game, side: chosen["coalition"]
    )
    return chosen


def test_ordering_the_same_relocation_again_plans_its_ferries_again() -> None:
    replanned: list[datetime] = []
    squadron: Any = SimpleNamespace(
        location=SimpleNamespace(runway_is_operational=lambda: True, sunk=False),
        destination="Ushuaia",
        owned_aircraft=4,
        replan_ferry_flights=replanned.append,
    )

    Squadron.plan_relocation(squadron, cast(Any, "Ushuaia"), NOW)

    assert replanned == [NOW]


def test_deleting_its_ferries_cancels_the_relocation(side: Any) -> None:
    h6, busy = _relocating("H-6"), _relocating("IL-78")
    ferries = _package(_flight(h6), _flight(h6))
    patrol = _package(_flight(busy, FlightType.BARCAP))
    side["coalition"] = _coalition(ferries, patrol, squadrons=(h6, busy))

    result = planner.delete_package(GAME, "red", 0)

    assert result.ok and h6.destination is None
    assert "cancelled the relocation" in (result.detail or "")
    # Its relocation had no ferries in that package: it stands.
    assert busy.destination == "Ushuaia"


def test_clearing_every_package_cancels_every_relocation_in_them(side: Any) -> None:
    h6, tanker = _relocating("H-6"), _relocating("IL-78")
    side["coalition"] = _coalition(
        _package(_flight(h6)), _package(_flight(tanker)), squadrons=(h6, tanker)
    )

    result = planner.clear_packages(GAME, "red")

    assert result.ok
    assert (h6.destination, tanker.destination) == (None, None)
