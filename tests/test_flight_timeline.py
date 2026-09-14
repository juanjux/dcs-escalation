"""The flight row's third line: departure, the working waypoint, and landing.

Which waypoint is "the working one" depends on the kind of flight plan, and the
point of showing it is to line the package's flights up against each other when
setting TOT offsets.
"""

from __future__ import annotations

import datetime
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qt_ui.widgets.atodelegates import flight_timeline

OFF = datetime.datetime(2020, 1, 1, 20, 0)
DOWN = datetime.datetime(2020, 1, 1, 21, 14)


class _Plan:
    landing_time = DOWN

    def takeoff_time(self) -> datetime.datetime:
        return OFF


class Strike(_Plan):
    ingress_time = datetime.datetime(2020, 1, 1, 20, 31)


class Sweep(_Plan):
    sweep_start_time = datetime.datetime(2020, 1, 1, 20, 25)


class SeadSweep(_Plan):
    """A SEAD sweep runs in on an ingress like the rest of the package."""

    ingress_time = datetime.datetime(2020, 1, 1, 20, 28)


class Patrol(_Plan):
    patrol_start_time = datetime.datetime(2020, 1, 1, 20, 20)


class Ferry:
    def takeoff_time(self) -> datetime.datetime:
        return OFF

    @property
    def landing_time(self) -> datetime.datetime:
        raise NotImplementedError


def _labels(plan: object) -> list[str]:
    return [label for label, _ in flight_timeline(plan)]


def test_a_strike_shows_its_ingress() -> None:
    assert flight_timeline(Strike()) == [
        ("dep", OFF),
        ("ing", Strike.ingress_time),
        ("land", DOWN),
    ]


def test_a_sead_sweep_shows_an_ingress_like_the_package() -> None:
    assert _labels(SeadSweep()) == ["dep", "ing", "land"]


def test_a_fighter_sweep_shows_where_the_corridor_starts() -> None:
    assert flight_timeline(Sweep())[1] == ("sweep", Sweep.sweep_start_time)


def test_a_patrol_shows_where_the_orbit_starts() -> None:
    assert flight_timeline(Patrol())[1] == ("racestart", Patrol.patrol_start_time)


def test_a_flight_with_no_working_waypoint_shows_only_the_two_ends() -> None:
    assert _labels(_Plan()) == ["dep", "land"]


def test_a_plan_that_cannot_say_when_it_lands_still_shows_the_rest() -> None:
    assert _labels(Ferry()) == ["dep"]
