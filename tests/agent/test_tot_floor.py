"""A package cannot be over its target before its flights can get there.

GeneraLLM set a DEAD package to TOT +5 min from a base ~29 minutes away. The API took
it, `validate` returned within_window:true, and the mission generator turned the
resulting negative push time into a hold release scheduled for -865 s. Nothing in the
loop said no.

The floor is the slowest flight's ``minimum_duration_from_start_to_tot`` — startup,
taxi, takeoff and transit.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.agent import planner

_NOW = datetime(2030, 6, 2, 9, 0, 0)


def _package(*minutes: float, target: str = "FAWN") -> Any:
    flights = [
        SimpleNamespace(
            flight_plan=SimpleNamespace(
                minimum_duration_from_start_to_tot=lambda m=m: timedelta(minutes=m),
                # Every real flight plan carries one; the floor now reads it, because
                # a flight offset AHEAD of its package needs the package that much
                # later than its own transit demands.
                tot_offset=timedelta(),
            ),
            departure=SimpleNamespace(name="Ramat David"),
        )
        for m in minutes
    ]
    return SimpleNamespace(
        flights=flights, target=SimpleNamespace(name=target), time_over_target=None
    )


def test_the_floor_is_the_slowest_flight() -> None:
    floor = planner.earliest_tot_minutes(_package(12.0, 28.7, 9.0), _NOW)
    assert floor == (29, "Ramat David")


def test_a_package_with_nothing_measurable_has_no_floor() -> None:
    assert planner.earliest_tot_minutes(_package(), _NOW) is None


def test_an_unreachable_tot_is_raised_to_the_floor() -> None:
    pkg = _package(28.7)
    spec = SimpleNamespace(tot_minutes=5)
    planner._apply_tot(pkg, spec, _NOW)
    assert pkg.time_over_target == _NOW + timedelta(minutes=29)


def test_a_reachable_tot_is_left_alone() -> None:
    pkg = _package(28.7)
    planner._apply_tot(pkg, SimpleNamespace(tot_minutes=45), _NOW)
    assert pkg.time_over_target == _NOW + timedelta(minutes=45)


def test_the_clamp_is_reported_not_silent() -> None:
    """The planner must be able to tell that it did not get the TOT it asked for."""
    game: Any = SimpleNamespace()
    pkg = _package(28.7)

    class FakeAto:
        packages = [pkg]

    def fake_coalition(_game: Any, _side: str) -> Any:
        return SimpleNamespace(ato=FakeAto())

    original = planner.views.coalition_for_side
    planner.views.coalition_for_side = fake_coalition  # type: ignore[assignment]
    try:
        game.conditions = SimpleNamespace(start_time=_NOW)
        result = planner.set_package_tot(game, "red", 0, 5)
    finally:
        planner.views.coalition_for_side = original
    assert result.ok
    assert "unreachable" in (result.detail or "")
    assert "+29" in (result.detail or "")
    assert "Ramat David" in (result.detail or "")
    assert pkg.time_over_target == _NOW + timedelta(minutes=29)


def test_an_asap_tot_is_never_reported_late() -> None:
    """The regression GeneraLLM hit: five of six packages flagged, all of them ASAP.

    set_tot_asap uses TotEstimator.earliest_tot, which is this same minimum, so an ASAP
    TOT lands exactly on it. Rounding the TOT down to minutes while rounding the floor
    up made every package with a fractional minimum look a minute late.
    """
    pkg = _package(28.2)
    asap_tot = _NOW + timedelta(minutes=28.2)  # what set_tot_asap produces
    assert planner.tot_shortfall(pkg, _NOW, asap_tot) is None


def test_a_genuinely_early_tot_is_still_reported() -> None:
    pkg = _package(28.2)
    assert planner.tot_shortfall(pkg, _NOW, _NOW + timedelta(minutes=5)) == (
        29,
        "Ramat David",
    )


def test_seconds_of_drift_are_not_an_issue() -> None:
    """A plan rebuilt after the TOT was set can move the minimum by a few seconds."""
    pkg = _package(28.2)
    just_short = _NOW + timedelta(minutes=28.2) - timedelta(seconds=10)
    assert planner.tot_shortfall(pkg, _NOW, just_short) is None


def test_the_reported_minute_is_always_reachable() -> None:
    """It is rounded UP: +28 would still be short of a 28.2-minute transit."""
    pkg = _package(28.2)
    earliest = planner.earliest_tot_minutes(pkg, _NOW)
    assert earliest is not None
    assert (
        planner.tot_shortfall(pkg, _NOW, _NOW + timedelta(minutes=earliest[0])) is None
    )
