"""A roster that hands its crew back has to stop holding on to them.

It did not, so a pilot could be flying one mission and sitting in the available pool
at the same time. The next flight claimed him again and the same man flew a BARCAP and
a DEAD in the same turn -- the squadron's books showed four pilots claimed for two
people.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.ato.flightroster import FlightRoster
from game.squadrons.pilot import Pilot


class _Squadron:
    def __init__(self, pilots: list[Pilot]) -> None:
        self.available_pilots = list(pilots)

    def claim_available_pilot(self, alongside: Any = ()) -> Pilot | None:
        return self.available_pilots.pop() if self.available_pilots else None

    def claim_pilot(self, pilot: Pilot) -> None:
        if pilot not in self.available_pilots:
            raise ValueError(f"{pilot.name} is not available")
        self.available_pilots.remove(pilot)

    def return_pilot(self, pilot: Pilot) -> None:
        self.available_pilots.append(pilot)

    def return_pilots(self, pilots: Any) -> None:
        self.available_pilots.extend(reversed(list(pilots)))


def _roster(size: int = 2) -> tuple[FlightRoster, _Squadron]:
    squadron = _Squadron([Pilot("El Jefe"), Pilot("Yayo"), Pilot("Tercero")])
    return FlightRoster(squadron, size), squadron  # type: ignore[arg-type]


def test_clearing_gives_the_crew_back() -> None:
    roster, squadron = _roster()
    assert len(squadron.available_pilots) == 1

    roster.clear()

    assert len(squadron.available_pilots) == 3


def test_clearing_also_empties_the_seats() -> None:
    """Or the flight keeps flying them while the squadron offers them to the next one."""
    roster, _ = _roster()
    roster.clear()
    assert list(roster.iter_pilots()) == [None, None]


def test_nobody_can_be_claimed_twice_after_a_clear() -> None:
    first, squadron = _roster()
    crew = [p for p in first.iter_pilots() if p is not None]
    first.clear()

    second = FlightRoster(squadron, 2)  # type: ignore[arg-type]

    assert sorted(p.name for p in second.iter_pilots() if p) == sorted(
        p.name for p in crew
    ), "the same two should come back, in the same order"
    assert not any(p in squadron.available_pilots for p in crew)
