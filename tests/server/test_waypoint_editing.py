"""Editing a flight's route from the map.

The map could only drag a waypoint. Renaming, deleting and inserting one were the
flight editor's alone, so a route drawn on the map had to be finished in a dialog.
These are the endpoints behind the map's own waypoint menu.

The rule about what may be deleted is the flight plan's, not the caller's: the flight
editor has a path that rebuilds the plan around a waypoint it cannot simply drop, and
that is too much to hang off a key on the map, so anything it refuses is refused here
with the reason.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.server.waypoints import routes
from game.utils import feet, meters


def _waypoint(name: str, kind: FlightWaypointType = FlightWaypointType.NAV) -> Any:
    # The position is never read here; a Point needs a terrain, which needs a map.
    return FlightWaypoint(
        name, kind, cast(Any, SimpleNamespace(x=0.0, y=0.0)), meters(0)
    )


class _Plan:
    def __init__(self, waypoints: list[Any], deletable: set[int] | None = None) -> None:
        self.waypoints = waypoints
        self._deletable = deletable if deletable is not None else set()
        self.layout = self

    def can_delete_waypoint(self, waypoint: Any) -> bool:
        return id(waypoint) in self._deletable

    def delete_waypoint(self, waypoint: Any) -> bool:
        if not self.can_delete_waypoint(waypoint):
            return False
        self.waypoints = [w for w in self.waypoints if w is not waypoint]
        return True

    def add_waypoint(self, anchor: Any, following: Any) -> bool:
        if anchor.waypoint_type is FlightWaypointType.TARGET_POINT:
            return False
        index = next(i for i, w in enumerate(self.waypoints) if w is anchor)
        self.waypoints.insert(index + 1, _waypoint("NAV"))
        return True


def _flight(plan: _Plan) -> Any:
    return SimpleNamespace(flight_plan=plan, blue=True, package=None)


def _game(flight: Any) -> Any:
    flight_id = uuid4()
    return (
        flight_id,
        SimpleNamespace(
            db=SimpleNamespace(flights=SimpleNamespace(get=lambda _id: flight)),
            theater=SimpleNamespace(terrain=None),
        ),
    )


@pytest.fixture(autouse=True)
def quiet_publish(monkeypatch: Any) -> None:
    """The re-timing reaches the Qt model and the event stream; neither exists here."""
    monkeypatch.setattr(routes, "_re_time_and_publish", lambda *_args: None)


def test_the_departure_point_is_not_editable() -> None:
    flight = _flight(_Plan([_waypoint("NAV")]))
    with pytest.raises(HTTPException) as excinfo:
        routes._waypoint_of(flight, 0)
    assert excinfo.value.status_code == 403


def test_an_index_past_the_route_is_a_not_found() -> None:
    flight = _flight(_Plan([_waypoint("NAV")]))
    with pytest.raises(HTTPException) as excinfo:
        routes._waypoint_of(flight, 7)
    assert excinfo.value.status_code == 404


def test_renaming_goes_through_the_waypoints_own_rename() -> None:
    """The same call the flight editor's list makes, so a player flight's rename
    reaches the aircraft's waypoint list by the path that already does that."""
    waypoint = _waypoint("NAV")
    waypoint.pretty_name = "NAV"
    flight_id, game = _game(_flight(_Plan([waypoint])))

    routes.edit_waypoint(flight_id, 1, routes.WaypointEdit(name="PUSH"), game)

    assert waypoint.custom_name == "PUSH"
    assert waypoint.display_name == "PUSH"


def test_a_blank_rename_goes_back_to_the_automatic_name() -> None:
    waypoint = _waypoint("NAV")
    waypoint.pretty_name = "NAV"
    waypoint.custom_name = "PUSH"
    flight_id, game = _game(_flight(_Plan([waypoint])))

    routes.edit_waypoint(flight_id, 1, routes.WaypointEdit(name="  "), game)

    assert waypoint.custom_name is None


def test_the_altitude_and_its_reference_are_set_together() -> None:
    waypoint = _waypoint("NAV")
    flight_id, game = _game(_flight(_Plan([waypoint])))

    routes.edit_waypoint(
        flight_id,
        1,
        routes.WaypointEdit(altitude_ft=12000, altitude_reference="RADIO"),
        game,
    )

    assert waypoint.alt == feet(12000)
    assert waypoint.alt_type == "RADIO"


def test_an_unknown_altitude_reference_changes_nothing() -> None:
    """Refused before anything is written, so a bad request cannot half-apply."""
    waypoint = _waypoint("NAV")
    waypoint.pretty_name = "NAV"
    flight_id, game = _game(_flight(_Plan([waypoint])))

    with pytest.raises(HTTPException) as excinfo:
        routes.edit_waypoint(
            flight_id,
            1,
            routes.WaypointEdit(name="PUSH", altitude_reference="AGL"),
            game,
        )

    assert excinfo.value.status_code == 400
    assert waypoint.custom_name is None


def test_a_waypoint_the_flight_can_give_up_is_deleted() -> None:
    keep, drop = _waypoint("NAV"), _waypoint("NAV")
    plan = _Plan([keep, drop], deletable={id(drop)})
    flight_id, game = _game(_flight(plan))

    routes.delete_waypoint(flight_id, 2, game)

    assert [id(w) for w in plan.waypoints] == [id(keep)]


def test_a_structural_waypoint_is_refused_with_the_reason() -> None:
    ingress = _waypoint("INGRESS", FlightWaypointType.INGRESS_STRIKE)
    ingress.pretty_name = "INGRESS"
    plan = _Plan([ingress])
    flight_id, game = _game(_flight(plan))

    with pytest.raises(HTTPException) as excinfo:
        routes.delete_waypoint(flight_id, 1, game)

    assert excinfo.value.status_code == 409
    assert "INGRESS" in excinfo.value.detail
    assert "waypoint tab" in excinfo.value.detail
    assert plan.waypoints == [ingress]


def test_a_nav_point_is_inserted_after_the_one_addressed() -> None:
    first, second = _waypoint("NAV"), _waypoint("NAV")
    plan = _Plan([first, second])
    flight_id, game = _game(_flight(plan))

    routes.insert_waypoint(flight_id, 1, routes.WaypointInsert(), game)

    assert len(plan.waypoints) == 3
    assert plan.waypoints[0] is first
    assert plan.waypoints[2] is second


def test_inserting_before_anchors_on_the_waypoint_in_front() -> None:
    first, second = _waypoint("NAV"), _waypoint("NAV")
    plan = _Plan([first, second])
    flight_id, game = _game(_flight(plan))

    routes.insert_waypoint(flight_id, 2, routes.WaypointInsert(before=True), game)

    assert len(plan.waypoints) == 3
    assert plan.waypoints[0] is first
    assert plan.waypoints[2] is second


def test_inserting_before_the_first_waypoint_still_lands_in_the_route() -> None:
    """There is nothing in front of it that the plan holds -- the departure is not a
    waypoint -- so it anchors on itself rather than refusing."""
    first = _waypoint("NAV")
    plan = _Plan([first])
    flight_id, game = _game(_flight(plan))

    routes.insert_waypoint(flight_id, 1, routes.WaypointInsert(before=True), game)

    assert len(plan.waypoints) == 2


def test_a_layout_with_no_room_is_refused_with_the_reason() -> None:
    target = _waypoint("TARGET", FlightWaypointType.TARGET_POINT)
    target.pretty_name = "TARGET"
    plan = _Plan([target])
    flight_id, game = _game(_flight(plan))

    with pytest.raises(HTTPException) as excinfo:
        routes.insert_waypoint(flight_id, 1, routes.WaypointInsert(), game)

    assert excinfo.value.status_code == 409
    assert "no room" in excinfo.value.detail


def test_the_added_waypoint_is_found_by_identity() -> None:
    """Two nav points on the same spot are equal without being the same waypoint, so
    the new one cannot be found by value."""
    first, second = _waypoint("NAV"), _waypoint("NAV")
    added = _waypoint("NAV")
    assert first == second  # the trap this is guarding

    assert routes._added_waypoint([first, second], [first, added, second]) is added
    assert routes._added_waypoint([first, second], [first, second]) is None


def test_an_insert_the_layout_puts_somewhere_else_is_refused() -> None:
    """A layout keeps its nav points in lists, and a list does not always begin where
    the anchor ends.

    Asked for a point between a takeoff and a hold, the standard layout puts one at
    the head of the outbound leg -- which is on the far side of the hold -- and
    positions it on the near side. The route then doubles back on itself, which is
    what it drew: a Z between the airfield and the hold.
    """
    takeoff = _waypoint("TAKEOFF", FlightWaypointType.TAKEOFF)
    hold = _waypoint("HOLD", FlightWaypointType.LOITER)
    nav = _waypoint("NAV")

    class _Displacing(_Plan):
        def add_waypoint(self, anchor: Any, following: Any) -> bool:
            # Wherever it was asked for, it goes at the head of the outbound leg.
            self.waypoints.insert(2, _waypoint("NAV"))
            return True

        def delete_waypoint(self, waypoint: Any) -> bool:
            # A nav point in one of the nav lists, which the real layout will give up.
            self.waypoints = [w for w in self.waypoints if w is not waypoint]
            return True

    plan = _Displacing([takeoff, hold, nav])
    flight_id, game = _game(_flight(plan))

    with pytest.raises(HTTPException) as excinfo:
        routes.insert_waypoint(flight_id, 2, routes.WaypointInsert(before=True), game)

    assert excinfo.value.status_code == 409
    assert "no room" in excinfo.value.detail
    # And it is taken back out rather than left in the route it spoils.
    assert plan.waypoints == [takeoff, hold, nav]


def test_an_insert_that_lands_where_it_was_asked_for_is_kept() -> None:
    """The same layout, asked for somewhere it can honour."""
    takeoff = _waypoint("TAKEOFF", FlightWaypointType.TAKEOFF)
    hold = _waypoint("HOLD", FlightWaypointType.LOITER)
    nav = _waypoint("NAV")
    plan = _Plan([takeoff, hold, nav])
    flight_id, game = _game(_flight(plan))

    routes.insert_waypoint(flight_id, 2, routes.WaypointInsert(before=False), game)

    assert len(plan.waypoints) == 4
    assert plan.waypoints[1] is hold
    assert plan.waypoints[3] is nav


def test_an_insert_that_cannot_be_taken_back_out_is_left_alone() -> None:
    """Better an odd route than a refusal that leaves a waypoint nobody was told about.

    The real layout always gives up a nav point it has just added, so this is the
    case that should not arise -- but a refusal and a changed route together is the
    one outcome with no way back.
    """
    takeoff = _waypoint("TAKEOFF", FlightWaypointType.TAKEOFF)
    hold = _waypoint("HOLD", FlightWaypointType.LOITER)

    class _Stubborn(_Plan):
        def add_waypoint(self, anchor: Any, following: Any) -> bool:
            self.waypoints.insert(2, _waypoint("NAV"))
            return True

        def delete_waypoint(self, waypoint: Any) -> bool:
            return False

    plan = _Stubborn([takeoff, hold])
    flight_id, game = _game(_flight(plan))

    routes.insert_waypoint(flight_id, 2, routes.WaypointInsert(before=True), game)

    assert len(plan.waypoints) == 3
