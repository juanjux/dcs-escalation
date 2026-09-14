"""A flight that is the whole package has no formation to form.

Joining and splitting is what flights do with each other, so calling those two points
JOIN and SPLIT on a package of one describes something that is not happening. They read
as nav points, and go back to being a join and a split the moment a second flight is in
the package -- however many aircraft each flight has.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from dcs import Point

from game.ato.flightplans.flightplan import FlightPlan
from game.ato.flightplans.formation import FormationLayout
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.utils import feet

_NOWHERE = Point(0, 0, None)  # type: ignore[arg-type]


def _waypoint(name: str, kind: FlightWaypointType, pretty: str) -> FlightWaypoint:
    return FlightWaypoint(
        name,
        kind,
        _NOWHERE,
        feet(20000),
        description=f"{pretty} description",
        pretty_name=pretty,
    )


@dataclass
class _Layout(FormationLayout):
    def iter_waypoints(self) -> Iterator[FlightWaypoint]:
        yield from (self.join, self.split)


def _layout() -> _Layout:
    return _Layout(
        departure=_waypoint("TAKEOFF", FlightWaypointType.TAKEOFF, "Takeoff"),
        custom_waypoints=[],
        arrival=_waypoint("LANDING", FlightWaypointType.LANDING_POINT, "Landing"),
        divert=None,
        bullseye=_waypoint("BULLSEYE", FlightWaypointType.BULLSEYE, "Bullseye"),
        nav_to=[],
        nav_from=[],
        hold=None,
        join=_waypoint("JOIN", FlightWaypointType.JOIN, "Join"),
        split=_waypoint("SPLIT", FlightWaypointType.SPLIT, "Split"),
        refuel=None,
    )


def test_the_only_flight_in_a_package_navigates_where_a_formation_would_join() -> None:
    layout = _layout()
    layout.label_formation_waypoints(alone_in_package=True)
    assert layout.join.waypoint_type is FlightWaypointType.NAV
    assert layout.split.waypoint_type is FlightWaypointType.NAV
    assert layout.join.name == "NAV"
    assert layout.join.pretty_name == "Nav"


def test_adding_a_second_flight_gives_the_join_back() -> None:
    layout = _layout()
    layout.label_formation_waypoints(alone_in_package=True)
    layout.label_formation_waypoints(alone_in_package=False)
    assert layout.join.waypoint_type is FlightWaypointType.JOIN
    assert layout.split.waypoint_type is FlightWaypointType.SPLIT
    assert layout.join.pretty_name == "Join"
    assert layout.split.description == "Depart from package"


def test_the_waypoints_stay_put() -> None:
    """The label is all that moves: the package still meets and parts there, and every
    time in the plan is measured from these two points."""
    layout = _layout()
    join, split = layout.join, layout.split
    positions = (join.position, split.position, join.alt, split.alt)
    layout.label_formation_waypoints(alone_in_package=True)
    assert layout.join is join
    assert layout.split is split
    assert (join.position, split.position, join.alt, split.alt) == positions


def test_a_name_the_player_typed_survives() -> None:
    layout = _layout()
    layout.join.custom_name = "PUSH"
    layout.label_formation_waypoints(alone_in_package=True)
    assert layout.join.custom_name == "PUSH"


class _Plan(FlightPlan[_Layout]):
    """The smallest thing that can answer can_delete_waypoint."""

    @staticmethod
    def builder_type() -> Any:  # pragma: no cover - never built in these tests
        raise NotImplementedError

    def default_tot_offset(self) -> Any:
        from datetime import timedelta

        return timedelta()

    @property
    def tot_waypoint(self) -> FlightWaypoint:
        return self.layout.join

    def tot_for_waypoint(self, waypoint: FlightWaypoint) -> Any:
        return None

    def depart_time_for_waypoint(self, waypoint: FlightWaypoint) -> Any:
        return None

    @property
    def mission_departure_time(self) -> Any:
        from datetime import datetime

        return datetime(2000, 1, 1)

    @property
    def mission_begin_on_station_time(self) -> Any:
        return None


def _plan(flights: int) -> _Plan:
    package = SimpleNamespace(flights=[object()] * flights)
    flight = SimpleNamespace(package=package)
    return _Plan(flight, _layout())  # type: ignore[arg-type]


def test_the_only_flight_in_a_package_may_delete_its_join() -> None:
    """There is nothing to meet, it reads NAV, and the plan does not need rebuilding
    around it -- which is what makes it safe on a flight the AI will fly."""
    plan = _plan(1)
    plan.label_formation_waypoints()
    assert plan.can_delete_waypoint(plan.layout.join)
    assert plan.delete_waypoint(plan.layout.join)
    assert not any(w is plan.layout.join for w in plan.waypoints)


def test_a_package_with_two_flights_does_not_offer_it() -> None:
    """With somebody to meet, the join is structure: taking it out is the degrade path,
    with its warning, not a quiet deletion."""
    plan = _plan(2)
    plan.label_formation_waypoints()
    assert not plan.can_delete_waypoint(plan.layout.join)
    assert not plan.delete_waypoint(plan.layout.join)


def test_a_second_flight_puts_a_deleted_join_back() -> None:
    plan = _plan(1)
    plan.delete_waypoint(plan.layout.join)
    assert not any(w is plan.layout.join for w in plan.waypoints)

    plan.flight.package.flights.append(object())  # type: ignore[arg-type]
    plan.label_formation_waypoints()

    assert any(w is plan.layout.join for w in plan.waypoints)
    assert plan.layout.join.waypoint_type is FlightWaypointType.JOIN


def test_the_deleted_join_is_still_there_for_the_timing() -> None:
    """It leaves the route, not the plan: every time in the plan is measured from it."""
    plan = _plan(1)
    join = plan.layout.join
    plan.delete_waypoint(join)
    assert plan.layout.join is join
