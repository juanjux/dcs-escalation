"""An escort on a patrol used to be a question with no answer.

The package's escort window is asked of every flight in it. An escort answers with a
time taken from the flight it is protecting; a patrol being protected answers with a
time taken from the window. Between the two the question asked itself, and the answer
was a RecursionError -- which killed whatever request was in flight, including the one
call the map draws itself from, so the map went blank.

Two things stop it: an escort is not part of the window it provides, and a package
that is asked for the window while it is already working it out says nobody.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

from game.ato.flightplans.escort import EscortFlightPlan
from game.ato.package import Package


def test_an_escort_is_not_part_of_the_window_it_provides() -> None:
    plan = cast(EscortFlightPlan, SimpleNamespace())

    assert EscortFlightPlan.request_escort_at(plan) is None
    assert EscortFlightPlan.dismiss_escort_at(plan) is None


class _AsksTheWindowBack:
    """A flight plan whose timing is taken from the window being worked out."""

    def __init__(self, package: Any) -> None:
        self.package = package
        self.asked = 0

    def request_escort_at(self) -> object:
        return "join"

    def dismiss_escort_at(self) -> object:
        return "split"

    def tot_for_waypoint(self, waypoint: object) -> datetime | None:
        self.asked += 1
        # What a patrol does: its own time comes from the package's escort window.
        return self.package.escort_end_time

    def depart_time_for_waypoint(self, waypoint: object) -> datetime | None:
        return self.package.escort_end_time


def test_a_package_asked_for_the_window_while_working_it_out_says_nobody() -> None:
    class Cyclic:
        def __init__(self) -> None:
            self.plan = _AsksTheWindowBack(self)
            self.flights = [SimpleNamespace(flight_plan=self.plan)]

        @property
        def escort_end_time(self) -> datetime | None:
            return Package.escort_end_time.fget(self)  # type: ignore[attr-defined]

        @property
        def escort_start_time(self) -> datetime | None:
            return Package.escort_start_time.fget(self)  # type: ignore[attr-defined]

        def _working_out_the_escort_window(self) -> Any:
            return Package._working_out_the_escort_window(cast(Package, self))

        @property
        def _escort_end_time(self) -> datetime | None:
            return Package._escort_end_time.fget(self)  # type: ignore[attr-defined]

        @property
        def _escort_start_time(self) -> datetime | None:
            return Package._escort_start_time.fget(self)  # type: ignore[attr-defined]

    package = Cyclic()

    assert package.escort_end_time is None
    # Asked once on the way in, and not again on the way round.
    assert package.plan.asked == 1

    package.plan.asked = 0
    assert package.escort_start_time is None
    assert package.plan.asked == 1


def test_the_window_can_be_worked_out_again_afterwards() -> None:
    """The guard is about one call in flight, not a package that has been asked once."""

    class Cyclic:
        def __init__(self) -> None:
            self.plan = _AsksTheWindowBack(self)
            self.flights = [SimpleNamespace(flight_plan=self.plan)]

        @property
        def escort_end_time(self) -> datetime | None:
            return Package.escort_end_time.fget(self)  # type: ignore[attr-defined]

        def _working_out_the_escort_window(self) -> Any:
            return Package._working_out_the_escort_window(cast(Package, self))

        @property
        def _escort_end_time(self) -> datetime | None:
            return Package._escort_end_time.fget(self)  # type: ignore[attr-defined]

    package = Cyclic()
    package.escort_end_time
    package.plan.asked = 0

    assert package.escort_end_time is None
    assert package.plan.asked == 1
