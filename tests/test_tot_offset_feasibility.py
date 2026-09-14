"""The package TOT must leave room for a flight that is asked to arrive AHEAD.

A flight is over the target at the package TOT plus its own offset, so a flight
three minutes ahead needs the package scheduled three minutes later than its own
transit demands. Without that, its plan is built backwards from a time it cannot
reach, its takeoff lands before the mission starts, and the clamp makes it arrive
LATE -- the exact opposite of what the offset asked for.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

from game.ato.traveltime import TotEstimator

NOW = datetime.datetime(2020, 1, 1, 8, 0, 0)


def _flight(minutes_to_tot: int, offset_minutes: float) -> Any:
    plan = SimpleNamespace(
        tot_offset=datetime.timedelta(minutes=offset_minutes),
        minimum_duration_from_start_to_tot=lambda: datetime.timedelta(
            minutes=minutes_to_tot
        ),
    )
    return SimpleNamespace(flight_plan=plan)


def _package(*flights: Any) -> Any:
    # Every real package carries a time over target; the estimate is measured against
    # it and puts it back, so the double needs one too.
    return SimpleNamespace(flights=list(flights), time_over_target=NOW)


def test_flight_with_no_offset_is_unchanged() -> None:
    package = _package(_flight(30, 0))
    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=30
    )


def test_ahead_flight_pushes_the_package_later() -> None:
    """30 minutes of transit, wanted 3 minutes early -> package TOT at +33."""
    package = _package(_flight(30, -3))
    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=33
    )


def test_behind_flight_does_not_hold_the_package_back() -> None:
    """A flight arriving 3 minutes late has 3 more minutes to get there."""
    package = _package(_flight(30, 3))
    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=27
    )


def test_the_ahead_flight_can_set_the_package_time() -> None:
    """The escort is quicker but wants to be early; it, not the slowest flight
    without an offset, is what the package has to wait for."""
    strikers = _flight(30, 0)
    escort_ahead = _flight(29, -5)
    package = _package(strikers, escort_ahead)

    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=34
    )


def test_every_flight_can_reach_its_own_tot_at_the_earliest_package_tot() -> None:
    """The property that matters: nobody is given a takeoff before mission start."""
    flights = [_flight(30, 0), _flight(22, -3), _flight(35, 2)]
    package = _package(*flights)
    tot = TotEstimator(package).earliest_tot(NOW)

    for flight in flights:
        own_tot = tot + flight.flight_plan.tot_offset
        needed = flight.flight_plan.minimum_duration_from_start_to_tot()
        assert own_tot - needed >= NOW


class _PatrolPlan:
    """A patrol in a package takes its station time from the package's escort window,
    not from the package TOT, so its takeoff does not move one-for-one with the TOT.

    ``escort_lead`` is how far before the package TOT the escort window opens.
    """

    def __init__(
        self,
        package: Any,
        escort_lead: datetime.timedelta,
        transit: datetime.timedelta,
        offset_minutes: float = 0,
    ) -> None:
        self.package = package
        self.escort_lead = escort_lead
        self.transit = transit
        self.tot_offset = datetime.timedelta(minutes=offset_minutes)

    @property
    def patrol_start_time(self) -> datetime.datetime:
        return self.package.time_over_target - self.escort_lead + self.tot_offset

    def takeoff_time(self) -> datetime.datetime:
        return self.patrol_start_time - self.transit

    def minimum_duration_from_start_to_tot(self) -> datetime.timedelta:
        # What the analytic estimate sees: transit to its own TOT. It knows nothing
        # about the escort window, which is exactly the gap being covered.
        return self.transit


class _StrikePlan:
    def __init__(self, transit: datetime.timedelta, package: Any) -> None:
        self.transit = transit
        self.package = package
        self.tot_offset = datetime.timedelta()

    def takeoff_time(self) -> datetime.datetime:
        return self.package.time_over_target - self.transit

    def minimum_duration_from_start_to_tot(self) -> datetime.timedelta:
        return self.transit


def _live_package() -> Any:
    package: Any = SimpleNamespace(flights=[], time_over_target=NOW)
    strike = SimpleNamespace(
        flight_plan=_StrikePlan(datetime.timedelta(minutes=30), package)
    )
    # On station 15 minutes before the package, 20 minutes of transit to get there.
    patrol = SimpleNamespace(
        flight_plan=_PatrolPlan(
            package, datetime.timedelta(minutes=15), datetime.timedelta(minutes=20)
        )
    )
    package.flights = [strike, patrol]
    return package


def test_a_patrol_is_not_asked_to_take_off_before_the_mission_starts() -> None:
    """The analytic estimate gives +30 (the strike's transit), but the patrol has to
    be on station at TOT-15 and needs 20 minutes to get there, so it would be sent off
    5 minutes before the mission began."""
    package = _live_package()

    tot = TotEstimator(package).earliest_tot(NOW)

    assert tot >= NOW + datetime.timedelta(minutes=35)
    package.time_over_target = tot
    for flight in package.flights:
        assert flight.flight_plan.takeoff_time() >= NOW


def test_the_package_tot_is_left_alone_while_measuring() -> None:
    package = _live_package()
    package.time_over_target = NOW + datetime.timedelta(hours=3)

    TotEstimator(package).earliest_tot(NOW)

    assert package.time_over_target == NOW + datetime.timedelta(hours=3)


def test_a_package_everyone_can_make_is_not_pushed() -> None:
    package: Any = SimpleNamespace(flights=[], time_over_target=NOW)
    package.flights = [
        SimpleNamespace(
            flight_plan=_StrikePlan(datetime.timedelta(minutes=30), package)
        )
    ]

    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=30
    )


def test_a_plan_that_cannot_say_when_it_takes_off_is_skipped() -> None:
    class Mute(_StrikePlan):
        def takeoff_time(self) -> datetime.datetime:
            raise RuntimeError("no flight plan yet")

    package: Any = SimpleNamespace(flights=[], time_over_target=NOW)
    package.flights = [
        SimpleNamespace(flight_plan=Mute(datetime.timedelta(minutes=30), package))
    ]

    assert TotEstimator(package).earliest_tot(NOW) == NOW + datetime.timedelta(
        minutes=30
    )
