"""The approach waypoint added ahead of the landing waypoint."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point

from game.ato.flightplans import alignpoint
from game.utils import Heading, feet, meters, nautical_miles


class _Airfield:
    """The parts of an Airfield the module uses."""

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
    """The parts of a NavalControlPoint the module uses."""

    def __init__(self) -> None:
        self.name = "CVN-72"
        self.position = Point(0, 0, cast(Any, None))


@pytest.fixture(autouse=True)
def the_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the doubles pass the isinstance checks."""
    import game.theater.controlpoint as controlpoint

    monkeypatch.setattr(controlpoint, "Airfield", _Airfield)
    monkeypatch.setattr(controlpoint, "NavalControlPoint", _Carrier)


def _conditions(from_degrees: int = 270, mps: float = 0.0) -> Any:
    """Wind in the form DCS stores it: the direction it blows towards."""
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


def test_nothing_is_added_when_the_setting_is_off() -> None:
    assert alignpoint.align_waypoint(_flight(_Airfield(), on=False)) is None


def test_it_is_placed_back_along_the_approach_course() -> None:
    """Runway 09 is flown heading east, so the waypoint is ten miles west."""
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(heading=90)))

    assert waypoint is not None
    assert waypoint.name == "ALIGN"
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(10.0, abs=0.1)
    # DCS x is north and y is east, so west of the field is a negative y.
    assert waypoint.position.y < 0
    assert waypoint.position.x == pytest.approx(0, abs=100)


def test_the_opposite_runway_puts_it_on_the_other_side() -> None:
    """Which is why the wind matters: 27 is flown heading west."""
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(heading=270, runway="27")))

    assert waypoint is not None
    assert waypoint.position.y > 0


def test_the_distance_is_a_setting() -> None:
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(), distance=4.0))

    assert waypoint is not None
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(4.0, abs=0.1)


def test_the_altitude_follows_the_glideslope_and_is_agl() -> None:
    waypoint = alignpoint.align_waypoint(_flight(_Airfield(), distance=10.0))

    assert waypoint is not None
    assert waypoint.alt == feet(3000)
    assert waypoint.alt_type == "RADIO"


def test_a_short_distance_is_floored() -> None:
    assert alignpoint.altitude_for(nautical_miles(3)) == feet(1500)


def test_a_long_distance_is_capped() -> None:
    assert alignpoint.altitude_for(nautical_miles(25)) == feet(6000)


def test_a_field_with_no_runway_data_gets_nothing() -> None:
    assert alignpoint.align_waypoint(_flight(_Airfield(runway=""))) is None


def test_it_is_appended_to_the_return_leg() -> None:
    """The landing waypoint follows nav_from, so the end of that list is the leg
    before it."""
    plan = SimpleNamespace(
        layout=SimpleNamespace(nav_from=[SimpleNamespace(name="NAV")])
    )

    alignpoint.add_to(_flight(_Airfield()), plan)

    assert [waypoint.name for waypoint in plan.layout.nav_from] == ["NAV", "ALIGN"]


def test_a_layout_without_a_nav_leg_home_is_left_alone() -> None:
    alignpoint.add_to(_flight(_Airfield()), SimpleNamespace())
    alignpoint.add_to(_flight(_Airfield()), None)


# ------------------------------------------------------------------- carriers


def test_the_carrier_waypoint_is_astern_on_the_recovery_course() -> None:
    """Wind from the west: the ship steams and recovers west, so the waypoint is
    fifty miles east of it."""
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    waypoint = alignpoint.align_waypoint(flight, _plan())

    assert waypoint is not None
    assert waypoint.name == "ALIGN"
    assert waypoint.position.x == pytest.approx(0, abs=200)
    # No wind, so the ship makes the 25 knots itself: an hour west puts it 25 miles
    # from where it started, and the waypoint fifty miles east of that.
    projected = Point(0, -nautical_miles(25).meters, cast(Any, None))
    away = meters(waypoint.position.distance_to_point(projected))
    assert away.nautical_miles == pytest.approx(50.0, abs=0.2)


def test_it_allows_for_the_ship_moving_during_the_mission() -> None:
    """25 knots for an hour is 25 miles of steaming."""
    calm = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))
    after_an_hour = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=60))
    after_two = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=120))

    assert after_an_hour is not None and after_two is not None
    moved = meters(after_two.position.distance_to_point(after_an_hour.position))
    assert moved.nautical_miles == pytest.approx(25.0, abs=0.5)


def test_wind_over_the_deck_is_speed_the_ship_does_not_have_to_make() -> None:
    blowing = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=12.86))
    windy = alignpoint.align_waypoint(blowing, _plan(minutes_to_landing=60))
    calm = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))
    still = alignpoint.align_waypoint(calm, _plan(minutes_to_landing=60))

    assert windy is not None and still is not None
    # 25 knots of wind covers all of it, so the ship holds station.
    assert alignpoint.steaming_speed(
        blowing.coalition.game.conditions
    ).knots == pytest.approx(0, abs=0.1)
    assert windy.position.y > still.position.y


def test_the_carrier_waypoint_is_at_case_three_marshal_altitude() -> None:
    flight = _flight(_Carrier())

    waypoint = alignpoint.align_waypoint(flight, _plan())

    assert waypoint is not None
    assert waypoint.alt == feet(6000)


def test_without_a_plan_the_landing_time_is_unknown_so_nothing_is_added() -> None:
    assert alignpoint.align_waypoint(_flight(_Carrier())) is None


def test_the_assumed_steaming_stops_at_the_end_of_the_ships_leg() -> None:
    """The generator gives it a single leg of 100 km and no more."""
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    long_mission = alignpoint.align_waypoint(flight, _plan(minutes_to_landing=300))
    longer = alignpoint.align_waypoint(flight, _plan(minutes_to_landing=600))

    assert long_mission is not None and longer is not None
    assert long_mission.position.y == pytest.approx(longer.position.y, abs=1)


def test_it_is_added_before_the_package_has_a_time_over_target() -> None:
    """A plan is first built before its package is timed, and the landing time cannot
    be worked out without one. The waypoint is still placed, on the recovery course
    and against the ship's current position."""
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))
    untimed = SimpleNamespace()  # no landing_time at all

    waypoint = alignpoint.align_waypoint(flight, untimed)

    assert waypoint is not None
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(50.0, abs=0.2)
    assert waypoint.position.y > 0


def test_a_landing_time_before_the_mission_starts_is_treated_as_zero() -> None:
    flight = _flight(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    waypoint = alignpoint.align_waypoint(flight, _plan(minutes_to_landing=-30))

    assert waypoint is not None
    away = meters(waypoint.position.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(50.0, abs=0.2)


# ---------------------------------------------------------------- the hold


DOCTRINE = SimpleNamespace(hold_distance=nautical_miles(25))


def _departing(arrival: Any, *, on: bool = True, conditions: Any = None) -> Any:
    flight = _flight(arrival, conditions=conditions)
    flight.departure = arrival
    flight.coalition.game.settings.align_hold_with_runway = on
    return flight


def test_the_hold_is_on_the_departure_runway_centreline() -> None:
    """Runway 09 is flown heading east, so the hold is east of the field."""
    flight = _departing(_Airfield(heading=90))

    hold = alignpoint.hold_point(flight, DOCTRINE)

    assert hold is not None
    assert hold.y > 0
    assert hold.x == pytest.approx(0, abs=200)
    away = meters(hold.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(25.0, abs=0.2)


def test_the_hold_follows_the_runway_in_use() -> None:
    flight = _departing(_Airfield(heading=270, runway="27"))

    hold = alignpoint.hold_point(flight, DOCTRINE)

    assert hold is not None
    assert hold.y < 0


def test_a_carrier_holds_on_its_recovery_course() -> None:
    """Wind from the west, so the ship points west and so does the climb out."""
    flight = _departing(_Carrier(), conditions=_conditions(from_degrees=270, mps=0.0))

    hold = alignpoint.hold_point(flight, DOCTRINE)

    assert hold is not None
    assert hold.y < 0


def test_nothing_is_placed_when_the_setting_is_off() -> None:
    assert alignpoint.hold_point(_departing(_Airfield(), on=False), DOCTRINE) is None


def test_a_field_with_no_runway_data_holds_where_it_always_did() -> None:
    assert alignpoint.hold_point(_departing(_Airfield(runway="")), DOCTRINE) is None


def test_how_far_out_the_hold_sits_is_a_setting() -> None:
    flight = _departing(_Airfield(heading=90))
    flight.coalition.game.settings.align_hold_distance_nm = 40.0

    hold = alignpoint.hold_point(flight, DOCTRINE)

    assert hold is not None
    away = meters(hold.distance_to_point(Point(0, 0, cast(Any, None))))
    assert away.nautical_miles == pytest.approx(40.0, abs=0.2)


def test_without_the_setting_the_doctrine_decides() -> None:
    """A save written before the setting existed, and any other caller."""
    assert (
        alignpoint.hold_distance_from(SimpleNamespace(), DOCTRINE)
        == DOCTRINE.hold_distance
    )
