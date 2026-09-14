"""Which waypoints the map draws a line through, and which it only marks.

The route was drawn through the target, which says the flight goes there and then
leaves, and on a strike with several aim points said it several times over. A flight
does not fly to its target; it releases at it. So the line runs ingress to split and
the targets are marked instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.server.waypoints.models import FlightWaypointJs
from game.utils import meters


def _waypoint(kind: FlightWaypointType, name: str = "WP") -> Any:
    # A real Point needs a terrain, which needs a map; the view only asks it for a
    # lat/lng, so a stand-in that answers that is the whole of what it needs.
    position = cast(
        Any, SimpleNamespace(x=0.0, y=0.0, latlng=lambda: {"lat": 0.0, "lng": 0.0})
    )
    return FlightWaypoint(name, kind, position, meters(0))


class _Plan:
    def __init__(self, waypoints: list[Any]) -> None:
        self.waypoints = waypoints

    def takeoff_time(self) -> Any:
        raise AssertionError("not asked for in these tests")

    def tot_for_waypoint(self, _waypoint: Any) -> None:
        return None

    def depart_time_for_waypoint(self, _waypoint: Any) -> None:
        return None

    def can_delete_waypoint(self, _waypoint: Any) -> bool:
        return True

    def speed_between_waypoints(self, _origin: Any, _destination: Any) -> Any:
        raise ValueError("no opinion")


def _view(
    kind: FlightWaypointType,
    flight_type: Any = None,
    target: Any = None,
) -> FlightWaypointJs:
    from game.ato.flighttype import FlightType

    waypoint = _waypoint(kind)
    flight = cast(
        Any,
        SimpleNamespace(
            flight_plan=_Plan([waypoint]),
            departure=SimpleNamespace(position=SimpleNamespace(x=0.0, y=0.0)),
            flight_type=flight_type or FlightType.STRIKE,
            package=SimpleNamespace(target=target or SimpleNamespace()),
        ),
    )
    # Index 1 so the timing lookup takes the waypoint path rather than the takeoff one.
    return FlightWaypointJs.for_waypoint(waypoint, flight, 1)


@pytest.mark.parametrize(
    "kind",
    [
        FlightWaypointType.TARGET_POINT,
        FlightWaypointType.TARGET_GROUP_LOC,
        FlightWaypointType.TARGET_SHIP,
    ],
)
def test_a_target_is_marked_but_not_drawn_through(kind: FlightWaypointType) -> None:
    view = _view(kind)
    assert view.is_target
    assert view.should_mark
    assert not view.include_in_path


@pytest.mark.parametrize(
    "kind",
    [
        FlightWaypointType.NAV,
        FlightWaypointType.INGRESS_STRIKE,
        FlightWaypointType.SPLIT,
        FlightWaypointType.JOIN,
        FlightWaypointType.PATROL,
    ],
)
def test_the_rest_of_the_route_is_drawn_as_it_was(kind: FlightWaypointType) -> None:
    view = _view(kind)
    assert not view.is_target
    assert view.include_in_path


def test_the_bullseye_is_still_neither_marked_nor_drawn(dummy: None = None) -> None:
    """It was already out of the path, and it is not a target either."""
    view = _view(FlightWaypointType.BULLSEYE)
    assert not view.is_target
    assert not view.should_mark
    assert not view.include_in_path


def test_takeoff_is_drawn_through_but_not_marked() -> None:
    """The line starts at the airfield; the pin there would only cover its icon."""
    view = _view(FlightWaypointType.TAKEOFF)
    assert not view.is_target
    assert not view.should_mark
    assert view.include_in_path


@pytest.mark.parametrize(
    "kind",
    [
        FlightWaypointType.TARGET_POINT,
        FlightWaypointType.TARGET_GROUP_LOC,
        FlightWaypointType.TARGET_SHIP,
    ],
)
def test_a_target_cannot_be_renamed_deleted_or_dragged(
    kind: FlightWaypointType,
) -> None:
    """It is what the package was fragged against, and the plan is not a sketch."""
    view = _view(kind)
    assert not view.can_delete
    assert not view.is_movable


def test_an_armed_recon_target_can_be_dragged_because_it_moves_the_search() -> None:
    """Armed recon hunts inside a circle centred on this waypoint, so the drag lands."""
    from game.ato.flighttype import FlightType

    view = _view(
        FlightWaypointType.TARGET_GROUP_LOC, flight_type=FlightType.ARMED_RECON
    )
    assert view.is_movable


def test_armed_recon_against_a_motorpool_cannot_be_dragged() -> None:
    """The circle is pinned to the garage there, so the drag would move the flyover
    point and leave the hunt where it was -- half an effect, which is worse than
    none."""
    from game.ato.flighttype import FlightType
    from game.theater.theatergroundobject import MotorpoolGroundObject

    motorpool = cast(Any, object.__new__(MotorpoolGroundObject))
    motorpool.id = uuid4()
    view = _view(
        FlightWaypointType.TARGET_GROUP_LOC,
        flight_type=FlightType.ARMED_RECON,
        target=motorpool,
    )
    assert not view.is_movable


def test_a_target_names_the_objective_it_belongs_to() -> None:
    """So the mark can open what is down there instead of a waypoint editor."""
    from game.theater.theatergroundobject import SamGroundObject

    objective = cast(Any, object.__new__(SamGroundObject))
    objective.id = uuid4()
    view = _view(FlightWaypointType.TARGET_POINT, target=objective)
    assert view.target_id == objective.id


def test_a_target_that_is_not_a_ground_object_names_nothing() -> None:
    """A convoy or a front line has no dialog to open, so the menu says so instead
    of offering a button that would do nothing."""
    view = _view(FlightWaypointType.TARGET_GROUP_LOC)
    assert view.target_id is None


@pytest.mark.parametrize(
    "kind",
    [
        FlightWaypointType.TARGET_POINT,
        FlightWaypointType.TAKEOFF,
        FlightWaypointType.LANDING_POINT,
        FlightWaypointType.DROPOFF_ZONE,
        FlightWaypointType.PICKUP_ZONE,
    ],
)
def test_an_altitude_that_is_the_ground_is_not_reported(
    kind: FlightWaypointType,
) -> None:
    """ "0 ft RADIO" on a target reads as a setting; it is the terrain."""
    assert not _view(kind).shows_altitude


@pytest.mark.parametrize(
    "kind",
    [
        FlightWaypointType.NAV,
        FlightWaypointType.INGRESS_STRIKE,
        FlightWaypointType.PATROL,
        FlightWaypointType.JOIN,
    ],
)
def test_an_altitude_the_flight_flies_at_is(kind: FlightWaypointType) -> None:
    assert _view(kind).shows_altitude
