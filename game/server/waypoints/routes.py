from typing import Any, Optional
from uuid import UUID

from dcs.mapping import LatLng, Point
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.responses import Response

from game import Game
from game.ato import Flight
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.server import GameContext
from game.server.leaflet import LeafletPoint
from game.server.waypoints.models import FlightWaypointJs
from game.sim import GameUpdateEvents
from game.utils import feet, meters

router: APIRouter = APIRouter(prefix="/waypoints")


def waypoints_for_flight(flight: Flight) -> list[FlightWaypointJs]:
    departure = FlightWaypointJs.for_waypoint(
        FlightWaypoint(
            "TAKEOFF",
            FlightWaypointType.TAKEOFF,
            flight.departure.position,
            meters(0),
            "RADIO",
        ),
        flight,
        0,
    )
    return [departure] + [
        FlightWaypointJs.for_waypoint(w, flight, i)
        for i, w in enumerate(flight.flight_plan.waypoints, 1)
    ]


@router.get(
    "/{flight_id}",
    operation_id="list_all_waypoints_for_flight",
    response_model=list[FlightWaypointJs],
)
def all_waypoints_for_flight(
    flight_id: UUID, game: Game = Depends(GameContext.require)
) -> list[FlightWaypointJs]:
    return waypoints_for_flight(game.db.flights.get(flight_id))


class WaypointEdit(BaseModel):
    """What the map's waypoint dialog can change. Absent means "leave it"."""

    name: Optional[str] = None
    altitude_ft: Optional[float] = None
    altitude_reference: Optional[str] = None


class WaypointInsert(BaseModel):
    """Where a new nav point goes, relative to the one addressed.

    ``position`` is where the player clicked, which for a click on a leg is the leg.
    Without one the new waypoint lands half way along, as the flight editor's Add NAV
    puts it.
    """

    before: bool = False
    position: Optional[LeafletPoint] = None


def _waypoint_of(flight: Flight, waypoint_idx: int) -> FlightWaypoint:
    """The waypoint that index addresses, or the reason it addresses nothing.

    Index 0 is the departure, which the map draws but the flight plan does not hold:
    it is where the aircraft is, and nothing about it is editable.
    """
    if waypoint_idx == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The departure point is where the aircraft is.",
        )
    try:
        return flight.flight_plan.waypoints[waypoint_idx - 1]
    except IndexError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{flight} has no waypoint {waypoint_idx}",
        )


def _package_model_of(flight: Flight) -> Any:
    model = (
        GameContext.get_model()
        .ato_model_for(flight.blue)
        .find_matching_package_model(flight.package)
    )
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find PackageModel owning {flight}",
        )
    return model


def _re_time_and_publish(flight: Flight, events: GameUpdateEvents) -> None:
    """Every edit changes the route, so the package is re-timed and the map redrawn."""
    from game.server import EventStream

    _package_model_of(flight).update_tot()
    EventStream.put_nowait(events.update_flight(flight))


@router.post(
    "/{flight_id}/{waypoint_idx}/position",
    operation_id="set_waypoint_position",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def set_position(
    flight_id: UUID,
    waypoint_idx: int,
    position: LeafletPoint,
    game: Game = Depends(GameContext.require),
) -> None:
    flight = game.db.flights.get(flight_id)
    waypoint = _waypoint_of(flight, waypoint_idx)
    waypoint.position = Point.from_latlng(
        LatLng(position.lat, position.lng), game.theater.terrain
    )
    events = GameUpdateEvents()
    update_package_waypoints_if_primary_flight(waypoint, flight, events)
    _re_time_and_publish(flight, events)


@router.patch(
    "/{flight_id}/{waypoint_idx}",
    operation_id="edit_waypoint",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def edit_waypoint(
    flight_id: UUID,
    waypoint_idx: int,
    edit: WaypointEdit,
    game: Game = Depends(GameContext.require),
) -> None:
    """Rename a waypoint, or change the height it is flown at.

    The rename is the one the flight editor's list already does, so it reaches the
    aircraft's own waypoint list on a player flight by the same path.
    """
    flight = game.db.flights.get(flight_id)
    waypoint = _waypoint_of(flight, waypoint_idx)
    if edit.altitude_reference is not None and edit.altitude_reference not in (
        "BARO",
        "RADIO",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Altitude reference is BARO or RADIO.",
        )
    if edit.name is not None:
        waypoint.apply_name_edit(edit.name)
    if edit.altitude_ft is not None:
        waypoint.alt = feet(edit.altitude_ft)
    if edit.altitude_reference is not None:
        waypoint.alt_type = edit.altitude_reference  # type: ignore[assignment]
    _re_time_and_publish(flight, GameUpdateEvents())


@router.delete(
    "/{flight_id}/{waypoint_idx}",
    operation_id="delete_waypoint",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_waypoint(
    flight_id: UUID,
    waypoint_idx: int,
    game: Game = Depends(GameContext.require),
) -> None:
    """Take a waypoint out of the route, if it is one the flight can give up.

    Anything else is refused with the reason rather than quietly rebuilding the plan
    around it: the flight editor has a path that degrades the plan to a custom one,
    and that is too much to hang off a key on the map.
    """
    flight = game.db.flights.get(flight_id)
    waypoint = _waypoint_of(flight, waypoint_idx)
    plan = flight.flight_plan
    if not plan.can_delete_waypoint(waypoint) or not plan.delete_waypoint(waypoint):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{waypoint.display_name} is part of this flight's plan. It can be "
                "removed from the flight's waypoint tab, which can rebuild the plan "
                "around it."
            ),
        )
    _re_time_and_publish(flight, GameUpdateEvents())


@router.post(
    "/{flight_id}/{waypoint_idx}/insert",
    operation_id="insert_waypoint",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def insert_waypoint(
    flight_id: UUID,
    waypoint_idx: int,
    insert: WaypointInsert,
    game: Game = Depends(GameContext.require),
) -> None:
    """Put a nav point next to the one addressed.

    The layout decides where a nav point may go -- it belongs to the way out or the
    way home, and not every waypoint sits on one of them -- so a refusal here is the
    plan saying there is no room rather than something unimplemented.
    """
    flight = game.db.flights.get(flight_id)
    _waypoint_of(flight, waypoint_idx)
    waypoints = flight.flight_plan.waypoints
    # add_waypoint inserts AFTER its anchor, so inserting before a waypoint is
    # inserting after the one in front of it.
    anchor_idx = max(1, waypoint_idx - 1 if insert.before else waypoint_idx)
    anchor = waypoints[anchor_idx - 1]
    following = waypoints[anchor_idx] if anchor_idx < len(waypoints) else None
    before = list(waypoints)
    if not flight.flight_plan.layout.add_waypoint(anchor, following):
        raise _no_room(anchor)

    added = _added_waypoint(before, flight.flight_plan.waypoints)
    if added is not None and not _landed_after(flight, anchor, added):
        # The layout keeps its nav points in lists, and a list does not always begin
        # where the anchor ends: asked for a point between a takeoff and a hold, it
        # puts one at the head of the outbound leg, which is on the far side of the
        # hold, and positions it on the near side. The route then doubles back.
        #
        # Refused only if it can be taken back out: a refusal that leaves the
        # waypoint in the route says nothing happened while something did, and the
        # player would have no way to find the thing to undo.
        if flight.flight_plan.layout.delete_waypoint(added):
            raise _no_room(anchor)

    if insert.position is not None and added is not None:
        added.position = Point.from_latlng(
            LatLng(insert.position.lat, insert.position.lng), game.theater.terrain
        )
    _re_time_and_publish(flight, GameUpdateEvents())


def _no_room(anchor: FlightWaypoint) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"There is no room for a waypoint next to {anchor.display_name}. Nav "
            "points go on the way out or on the way home."
        ),
    )


def _landed_after(
    flight: Flight, anchor: FlightWaypoint, added: FlightWaypoint
) -> bool:
    """Whether the new waypoint went where it was asked to go.

    The layout is free to put it somewhere else, and if it does the route ends up
    visiting it out of the order its position implies -- which draws as a detour
    back the way the flight came.
    """
    # By identity: two nav points on the same spot are equal without being the same
    # waypoint, so index() would find whichever of them came first.
    at = {
        id(waypoint): index
        for index, waypoint in enumerate(flight.flight_plan.waypoints)
    }
    if id(added) not in at or id(anchor) not in at:
        return False
    return at[id(added)] == at[id(anchor)] + 1


def _added_waypoint(
    before: list[FlightWaypoint], after: list[FlightWaypoint]
) -> Optional[FlightWaypoint]:
    """The one waypoint the route gained, by identity.

    Asked of the route rather than of the layout: which list a nav point lands in is
    the layout's business, and it has three of them.
    """
    known = {id(waypoint) for waypoint in before}
    for waypoint in after:
        if id(waypoint) not in known:
            return waypoint
    return None


def formation_waypoint(
    flight: Flight, kind: FlightWaypointType
) -> FlightWaypoint | None:
    """A flight's join or split, whatever it happens to be labelled.

    A lone AI ship's two package waypoints read as NAV -- it has no formation to form --
    so matching on the label would miss them here, and would then drag the first nav
    point of every other flight in the package instead. The layout knows which waypoint
    is which; a custom flight plan has no layout to ask, and falls back to the label.
    """
    from game.ato.flightplans.formation import FormationLayout

    layout = flight.flight_plan.layout
    if isinstance(layout, FormationLayout):
        return layout.join if kind is FlightWaypointType.JOIN else layout.split
    for wpt in flight.flight_plan.iter_waypoints():
        if wpt.waypoint_type is kind:
            return wpt
    return None


def update_package_waypoints_if_primary_flight(
    waypoint: FlightWaypoint,
    flight: Flight,
    events: GameUpdateEvents,
) -> None:
    wpts = flight.package.waypoints
    if flight is flight.package.primary_flight and wpts:
        moved: FlightWaypointType | None = None
        if waypoint is formation_waypoint(flight, FlightWaypointType.JOIN):
            moved = FlightWaypointType.JOIN
            wpts.join = waypoint.position
        elif waypoint is formation_waypoint(flight, FlightWaypointType.SPLIT):
            moved = FlightWaypointType.SPLIT
            wpts.split = waypoint.position
        elif waypoint.waypoint_type is FlightWaypointType.REFUEL:
            wpts.refuel = waypoint.position
        elif "INGRESS" in waypoint.waypoint_type.name:
            wpts.ingress = waypoint.position
            wpts.initial = wpts.get_initial_point(
                waypoint.position, flight.package.target.position
            )
        else:
            return
        for f in flight.package.flights:
            if f is flight:
                continue
            counterpart = (
                formation_waypoint(f, moved)
                if moved is not None
                else _same_kind_of_waypoint(f, waypoint)
            )
            if counterpart is not None:
                counterpart.position = waypoint.position.new_in_same_map(
                    waypoint.position.x, waypoint.position.y
                )
                events.update_flight(f)


def _same_kind_of_waypoint(
    flight: Flight, waypoint: FlightWaypoint
) -> FlightWaypoint | None:
    for wpt in flight.flight_plan.iter_waypoints():
        if wpt.waypoint_type == waypoint.waypoint_type or (
            "INGRESS" in wpt.waypoint_type.name
            and "INGRESS" in waypoint.waypoint_type.name
        ):
            return wpt
    return None
