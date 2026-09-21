"""The waypoint that puts a flight on the runway centreline before it gets there.

The route used to end at the airfield, which is a point and not a direction: the
aeroplane arrived on whatever heading the leg before it happened to leave, and lining
up was the player's problem at the worst moment to have one.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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


class _Carrier:
    """A ship steaming into the wind, which is all a recovery course is."""

    def __init__(self) -> None:
        self.name = "CVN-72"
        self.position = Point(0, 0, cast(Any, None))


@pytest.fixture(autouse=True)
def the_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """The doubles pass the isinstance checks the real ones would."""
    import game.theater.controlpoint as controlpoint

    monkeypatch.setattr(controlpoint, "Airfield", _Airfield)
    monkeypatch.setattr(controlpoint, "NavalControlPoint", _Carrier)


def _conditions(from_degrees: int = 270, mps: float = 0.0) -> Any:
    """Wind as DCS gives it: the direction it blows towards."""
    return SimpleNamespace(
        start_time=datetime(2026, 9, 22, 8, 0),
        weather=SimpleNamespace(
            wind=SimpleNamespace(
                at_0m=SimpleNamespace(
                    direction=Heading.from_degrees(from_degrees).opposite.degrees,
                    speed=mps,
                )
            )
        ),
    )


def _plan(minutes_to_landing: int = 60) -> Any:
    return SimpleNamespace(
        landing_time=datetime(2026, 9, 22, 8, 0) + timedelta(minutes=minutes_to_landing)
    )


def _flight(
    arrival: Any,
    *,
    on: bool = True,
    distance: float = 10.0,
    carrier_distance: float = 50.0,
    conditions: Any = None,
) -> Any:
    settings = SimpleNamespace(
        align_before_landing=on,
        align_distance_nm=distance,
        align_carrier_distance_nm=carrier_distance,
    )
    return SimpleNamespace(
        arrival=arrival,
        coalition=SimpleNamespace(
            game=SimpleNamespace(
                settings=settings, conditions=conditions or _conditions()
            )
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


def test_it_goes_last_on_the_way_home() -> None:
    """The landing waypoint follows nav_from, so the end of that list is the leg
    before it."""
    plan = SimpleNamespace(
        layout=SimpleNamespace(nav_from=[SimpleNamespace(name="NAV")])
    )

    alignpoint.add_to(_flight(_Airfield()), plan)

    assert [waypoint.name for waypoint in plan.layout.nav_from] == ["NAV", "ALIGN"]


def test_a_layout_that_does_not_fly_home_along_a_nav_leg_is_left_alone() -> None:
    alignpoint.add_to(_flight(_Airfield()), SimpleNamespace())
    alignpoint.add_to(_flight(_Airfield()), None)


# --------------------------------------------------------------- the carrier


def test_the_carrier_point_is_astern_on_the_recovery_course() -> None:
    """Wind from the west, so she steams west and recovers west: the marshal is
    fifty miles EAST of her."""
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    waypoint = alignpoint.align_waypoint(flight, _plan())

    assert waypoint is not None
    assert waypoint.name == "ALIGN"
    assert waypoint.position.x == pytest.approx(0, abs=200)
    # No wind to help, so she makes the twenty-five knots herself: an hour west puts
    # her twenty-five miles from where she started, and the marshal fifty east of her.
    steamed = nautical_miles(25)
    she_will_be = Point(0, -steamed.meters, cast(Any, None))
    away = meters(waypoint.position.distance_to_point(she_will_be))
    assert away.nautical_miles == pytest.approx(50.0, abs=0.2)


def test_it_allows_for_where_she_will_have_got_to() -> None:
    """Twenty-five knots for an hour is twenty-five miles of steaming."""
    calm = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))
    still = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=60))
    later = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=120))

    assert still is not None and later is not None
    # A second hour of steaming west puts the marshal a further 25 nm west.
    moved = meters(later.position.distance_to_point(still.position))
    assert moved.nautical_miles == pytest.approx(25.0, abs=0.5)


def test_a_wind_over_the_deck_is_speed_she_does_not_have_to_make() -> None:
    blowing = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=12.86))
    windy = alignpoint.align_waypoint(blowing, _plan(minutes_to_landing=60))
    calm = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))
    still = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=60))

    assert windy is not None and still is not None
    # Twenty-five knots of wind is the whole of it: she holds station.
    assert alignpoint.steaming_speed(
        blowing.coalition.game.conditions
    ).knots == pytest.approx(0, abs=0.1)
    assert windy.position.y > still.position.y


def test_the_carrier_marshal_is_at_the_height_a_case_three_flies() -> None:
    flight = _flight(_Carrier())

    waypoint = alignpoint.align_waypoint(flight, _plan())

    assert waypoint is not None
    assert waypoint.alt == feet(6000)


def test_without_a_plan_there_is_no_telling_where_she_will_be() -> None:
    assert alignpoint.align_waypoint(_flight(_Carrier())) is None


def test_she_is_not_assumed_to_steam_past_the_end_of_her_leg() -> None:
    """The generator gives her one leg of a hundred kilometres and no more."""
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    long_mission = alignpoint.align_waypoint(flight, _plan(minutes_to_landing=300))
    longer = alignpoint.align_waypoint(flight, _plan(minutes_to_landing=600))

    assert long_mission is not None and longer is not None
    assert long_mission.position.y == pytest.approx(longer.position.y, abs=1)
