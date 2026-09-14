"""What an escort escorts when the package holds nothing but escorts.

A package elects its primary flight by mission-type priority and the escort types are
the last two entries in that list, so a package containing only escorts -- the first
flight added to a new package, or one whose strikers were all cancelled -- names an
escort as its own primary. The escort layout reads the primary flight's plan, and a
flight's plan is only assigned once its builder returns, so an escort that escorts
itself used to hand its own half-built builder back to itself and recurse until the
stack ran out: creating the flight raised RecursionError instead of planning it.

An escort with nobody but itself to protect escorts nobody, and flies the package's
ordinary geometry.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from game.ato.flightplans.escort import Builder
from game.ato.flighttype import FlightType


class _FlightBeingPlanned:
    """A flight whose plan does not exist yet, because it is being built right now.

    Reading ``flight_plan`` is precisely the mistake under test, so it fails loudly
    rather than recursing the way the real builder would.
    """

    def __init__(self, flight_type: FlightType) -> None:
        self.flight_type = flight_type
        self.package: Any = None

    @property
    def flight_plan(self) -> Any:
        raise AssertionError("asked a flight being planned for its own flight plan")


def _escort_builder(
    flight_type: FlightType = FlightType.ESCORT,
) -> tuple[Builder, _FlightBeingPlanned, SimpleNamespace]:
    """An escort builder for a flight in a package whose primary is set by the test.

    ``__init__`` is bypassed: the property under test reads only the flight and its
    package, and a real builder wants a whole campaign behind it.
    """
    flight = _FlightBeingPlanned(flight_type)
    package = SimpleNamespace(primary_flight=None)
    flight.package = package
    builder: Builder = object.__new__(Builder)
    builder.flight = flight  # type: ignore[assignment]
    return builder, flight, package


def _other_flight(flight_type: FlightType) -> SimpleNamespace:
    return SimpleNamespace(flight_type=flight_type)


def test_escort_that_is_its_own_package_primary_escorts_nobody() -> None:
    builder, flight, package = _escort_builder()
    package.primary_flight = flight

    assert builder.escorted_flight is None


def test_sead_escort_that_is_its_own_package_primary_escorts_nobody() -> None:
    builder, flight, package = _escort_builder(FlightType.SEAD_ESCORT)
    package.primary_flight = flight

    assert builder.escorted_flight is None


def test_escort_whose_primary_is_another_escort_escorts_nobody() -> None:
    # A package of two escorts elects the SEAD escort as primary; following it just
    # arrives at a second flight with the same problem.
    builder, _, package = _escort_builder()
    package.primary_flight = _other_flight(FlightType.SEAD_ESCORT)

    assert builder.escorted_flight is None


def test_escort_of_a_striker_still_escorts_the_striker() -> None:
    builder, _, package = _escort_builder()
    strike = _other_flight(FlightType.STRIKE)
    package.primary_flight = strike

    assert builder.escorted_flight is strike


def test_escort_in_a_package_with_no_primary_flight_escorts_nobody() -> None:
    builder, _, package = _escort_builder()
    package.primary_flight = None

    assert builder.escorted_flight is None


def test_self_escort_never_reaches_the_flight_plan_that_recursed() -> None:
    # The recursion entered through _racetrack_hold_point, which reads the escorted
    # flight's plan. Composed with escorted_flight it must no longer get there.
    builder, flight, package = _escort_builder()
    package.primary_flight = flight

    hold: Optional[Any] = Builder._racetrack_hold_point(builder.escorted_flight)

    assert hold is None
