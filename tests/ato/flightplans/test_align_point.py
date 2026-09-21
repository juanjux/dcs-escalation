"""The waypoint that puts a flight on the runway centreline before it gets there.

The route used to end at the airfield, which is a point and not a direction: the
aeroplane arrived on whatever heading the leg before it happened to leave, and lining
up was the player's problem at the worst moment to have one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point

from game.ato.flightplans import alignpoint
from game.utils import Heading, feet, meters, nautical_miles


class _Airfield:
    """Enough of an Airfield to be one: the diagnosis asks isinstance()."""

    def __init__(self, heading: int = 90, runway: str = "09") -> None:
        self.name = "Rio Gallegos"
        self.theater = object()
        self.position = Point(0, 0, cast(Any, SimpleNamespace(name="terrain")))
        self._runway = SimpleNamespace(
            runway_heading=Heading.from_degrees(heading), runway_name=runway
        )

    def active_runway(self, theater: Any, conditions: Any, dynamic: Any) -> Any:
        return self._runway


@pytest.fixture(autouse=True)
def airfield_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """_Airfield passes the isinstance check the real one would."""
    import game.theater.controlpoint as controlpoint

    monkeypatch.setattr(controlpoint, "Airfield", _Airfield)


def _flight(arrival: Any, *, on: bool = True, distance: float = 10.0) -> Any:
    settings = SimpleNamespace(align_before_landing=on, align_distance_nm=distance)
    return SimpleNamespace(
        arrival=arrival,
        coalition=SimpleNamespace(
            game=SimpleNamespace(settings=settings, conditions=object())
        ),
    )


def test_off_by_default_nothing_is_added() -> None:
    assert alignpoint.align_waypoint(_flight(_Airfield(), on=False)) is None


def test_it_sits_back_down_the_approach_course() -> None:
    """Runway 09 is flown heading east, so the fix is ten miles WEST of the field."""
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(heading=90)))

    assert waypoint is not None
    assert waypoint.name == "ALIGN"
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(10.0, abs=0.1)
    # DCS x is north and y is east, so west of the field is a negative y.
    assert waypoint.position.y < 0
    assert waypoint.position.x == pytest.approx(0, abs=100)


def test_the_other_end_of_the_same_runway_is_the_other_side_of_the_field() -> None:
    """Which is the whole point of reading the wind: 27 is flown heading west."""
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(heading=270, runway="27")))

    assert waypoint is not None
    assert waypoint.position.y > 0


def test_how_far_out_is_a_setting() -> None:
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(), distance=4.0))

    assert waypoint is not None
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(4.0, abs=0.1)


def test_its_height_is_the_glideslope_from_there() -> None:
    """Three degrees is about 300 ft a mile, and it is above the field, not the sea."""
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(), distance=10.0))

    assert waypoint is not None
    assert waypoint.alt == feet(3000)
    assert waypoint.alt_type == "RADIO"


def test_a_short_one_is_still_flown_at_a_sensible_height() -> None:
    assert alignpoint.altitude_for(nautical_miles(3)) == feet(1500)


def test_a_long_one_does_not_put_the_run_in_in_the_stratosphere() -> None:
    assert alignpoint.altitude_for(nautical_miles(25)) == feet(6000)


def test_a_field_with_no_runway_in_its_data_gets_nothing() -> None:
    assert alignpoint.align_waypoint(_flight(_Airfield(runway=""))) is None


def test_a_carrier_gets_nothing() -> None:
    """It moves, and it is flown to by a pattern rather than a straight-in."""
    carrier = SimpleNamespace(name="CVN-72", position=Point(0, 0, cast(Any, None)))

    assert alignpoint.align_waypoint(_flight(carrier)) is None


def test_it_goes_last_on_the_way_home() -> None:
    """The landing waypoint follows nav_from, so the end of that list is the leg
    before it."""
    layout = SimpleNamespace(nav_from=[SimpleNamespace(name="NAV")])

    alignpoint.add_to(_flight(_Airfield()), layout)

    assert [waypoint.name for waypoint in layout.nav_from] == ["NAV", "ALIGN"]


def test_a_layout_that_does_not_fly_home_along_a_nav_leg_is_left_alone() -> None:
    alignpoint.add_to(_flight(_Airfield()), SimpleNamespace())
    alignpoint.add_to(_flight(_Airfield()), None)
