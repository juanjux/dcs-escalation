"""A tanker's own flight plan has to keep pointing at the tanker.

PackageRefuelingFlightPlan.patrol_duration counted the aircraft it would have to fill
with `for self.flight in self.package.flights:` -- the loop variable was the plan's OWN
flight attribute, so after one read the plan pointed at whatever came last in the
package. Everything it then reads off self.flight is another aircraft's: patrol speed,
patrol altitude, take-off time. It was unreachable while the auto-planner never built
this plan, and the refuelling rework makes it reachable.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flightplans.packagerefueling import PackageRefuelingFlightPlan

#: Read through the class so an unbuilt plan can be asked without a real Flight.
_duration: Any = PackageRefuelingFlightPlan.__dict__["patrol_duration"].fget


#: Low enough that the computed per-package time wins, so the tests below still
#: measure what they were written to measure.
_SHORT_HOLD = timedelta(minutes=1)


def _flight(name: str, size: int, hold: timedelta = _SHORT_HOLD) -> Any:
    """package is a property on FlightPlan reading flight.package, so it hangs here."""
    return SimpleNamespace(
        name=name,
        roster=SimpleNamespace(max_size=size),
        package=None,
        coalition=SimpleNamespace(
            game=SimpleNamespace(
                settings=SimpleNamespace(desired_tanker_on_station_time=hold)
            )
        ),
    )


def test_reading_the_duration_does_not_rebind_the_plan_to_another_flight() -> None:
    tanker = _flight("KC-135", 1)
    hornets = _flight("Hornets", 4)
    plan: Any = PackageRefuelingFlightPlan.__new__(PackageRefuelingFlightPlan)
    tanker.package = SimpleNamespace(flights=[tanker, hornets])
    plan.flight = tanker

    duration = _duration(plan)

    assert plan.flight is tanker, "the plan now describes some other aircraft"
    assert isinstance(duration, timedelta)


def test_the_duration_still_counts_every_aircraft_in_the_package() -> None:
    tanker = _flight("KC-135", 1)
    plan: Any = PackageRefuelingFlightPlan.__new__(PackageRefuelingFlightPlan)
    tanker.package = SimpleNamespace(flights=[tanker])
    plan.flight = tanker
    alone = _duration(plan)

    tanker.package = SimpleNamespace(flights=[tanker, _flight("Hornets", 4)])
    with_a_flight_to_fill = _duration(plan)

    assert with_a_flight_to_fill > alone


def test_the_tanker_holds_for_as_long_as_the_campaign_says() -> None:
    """Ten minutes around an arrival time that is itself an estimate is a window the
    receiver misses. The campaign's own figure -- the one that decides how many tankers
    get bought -- is the right length."""
    tanker = _flight("KC-135", 1, hold=timedelta(minutes=60))
    plan: Any = PackageRefuelingFlightPlan.__new__(PackageRefuelingFlightPlan)
    tanker.package = SimpleNamespace(flights=[tanker])
    plan.flight = tanker

    assert _duration(plan) == timedelta(minutes=60)


def test_a_package_that_needs_longer_than_that_gets_longer() -> None:
    """The computed time is a floor, not a ceiling: a big package takes a while to
    fill and the campaign setting must not cut it short."""
    tanker = _flight("KC-135", 1, hold=timedelta(minutes=30))
    plan: Any = PackageRefuelingFlightPlan.__new__(PackageRefuelingFlightPlan)
    tanker.package = SimpleNamespace(
        flights=[tanker] + [_flight(f"flight {i}", 4) for i in range(4)]
    )
    plan.flight = tanker

    assert _duration(plan) > timedelta(minutes=30)
