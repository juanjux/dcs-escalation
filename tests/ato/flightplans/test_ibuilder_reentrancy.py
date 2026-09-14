"""A flight plan that asks for itself must fail loudly instead of overflowing.

A flight's plan is only assigned once its builder's ``build`` returns, so any plan that
reaches another flight's plan and comes back round to its own hands an empty builder
back to itself and builds again, forever. The escort that escorted itself was one such
cycle; the shape can reappear whenever a layout reads a second flight.

The planner already shows ``PlanningError`` to the player as a dialog it can recover
from, so a cycle should raise one naming both ends of it rather than a thousand
identical stack frames that name nothing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from game.ato.flightplans.ibuilder import IBuilder
from game.ato.flightplans.planningerror import PlanningError


def _flight(name: str) -> Any:
    """A flight double with a readable name, since the names are what is asserted."""
    flight: Any = MagicMock()
    flight.__str__.return_value = name
    flight.package.target.is_friendly.return_value = True
    return flight


class _SelfReferentialBuilder(IBuilder[Any, Any]):
    """Asks for the plan it is in the middle of building."""

    def __init__(self, flight: Any) -> None:
        super().__init__(flight)
        self.builds = 0

    def build(self, dump_debug_info: bool = False) -> Any:
        self.builds += 1
        return self.get_or_build()


class _DelegatingBuilder(IBuilder[Any, Any]):
    """Reads another flight's plan while building, the way an escort does."""

    def __init__(self, flight: Any) -> None:
        super().__init__(flight)
        self.other: IBuilder[Any, Any] | None = None
        self.builds = 0

    def build(self, dump_debug_info: bool = False) -> Any:
        self.builds += 1
        assert self.other is not None
        return ["plan for", self.flight, "after", self.other.get_or_build()]


class _FailsOnceBuilder(IBuilder[Any, Any]):
    """Fails the first build and succeeds the second, to prove the flag is cleared."""

    def __init__(self, flight: Any) -> None:
        super().__init__(flight)
        self.builds = 0

    def build(self, dump_debug_info: bool = False) -> Any:
        self.builds += 1
        if self.builds == 1:
            raise PlanningError("no route today")
        return ["plan"]


def test_a_builder_that_asks_for_the_plan_it_is_building_raises_a_planning_error() -> (
    None
):
    builder = _SelfReferentialBuilder(_flight("Uzi 1-1"))

    with pytest.raises(PlanningError):
        builder.regenerate()

    # Once, not once per stack frame: the cycle is cut at the first repeat.
    assert builder.builds == 1


def test_the_planning_error_names_both_flights_in_the_cycle() -> None:
    escort = _DelegatingBuilder(_flight("Uzi 1-1"))
    striker = _DelegatingBuilder(_flight("Colt 2-1"))
    escort.other = striker
    striker.other = escort

    with pytest.raises(PlanningError) as caught:
        escort.regenerate()

    assert "Uzi 1-1" in str(caught.value)
    assert "Colt 2-1" in str(caught.value)


def test_a_plan_may_still_read_the_plan_of_a_different_flight() -> None:
    # Nesting is normal -- an escort reads the flight it escorts -- so the guard must
    # be per builder rather than a single "somebody is planning" flag.
    tanker = _FailsOnceBuilder(_flight("Magic 1-1"))
    tanker.builds = 1  # Past its scripted failure.
    escort = _DelegatingBuilder(_flight("Uzi 1-1"))
    striker = _DelegatingBuilder(_flight("Colt 2-1"))
    escort.other = striker
    striker.other = tanker

    escort.regenerate()

    assert escort.existing_flight_plan is not None
    assert striker.existing_flight_plan is not None


def test_a_failed_build_leaves_the_builder_able_to_try_again() -> None:
    builder = _FailsOnceBuilder(_flight("Uzi 1-1"))

    with pytest.raises(PlanningError):
        builder.regenerate()
    builder.regenerate()

    assert builder.existing_flight_plan == ["plan"]
