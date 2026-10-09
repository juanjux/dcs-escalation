"""Putting a point from the map into one of the player's own aircraft."""

from __future__ import annotations

from uuid import UUID

from dcs.mapping import LatLng, Point
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from game import Game
from game.ato.flight import Flight
from game.ato.savedpoints import (
    PointKind,
    SavedPoint,
    add_point,
    kinds_for,
    points_of,
    receivers,
    remove_point,
    room_for,
)
from game.coordinates import format_latlng
from game.server import GameContext
from game.server.leaflet import LeafletPoint
from .notifications import publish_points_changed

router: APIRouter = APIRouter(prefix="/saved-points")


class SavedPointJs(BaseModel):
    id: UUID
    position: LeafletPoint
    kind: str
    name: str
    #: Written in the campaign's own coordinate format, so the map, the kneeboard and
    #: this all say the same thing about the same spot.
    coordinates: str
    altitude_ft: int


class ReceiverJs(BaseModel):
    """One aircraft the player is flying, and what it will still take."""

    id: UUID
    #: What to call this flight in a list. A flight has no callsign until the mission
    #: is generated -- what the rest of the app shows is the name the player gave it,
    #: and most flights have none -- so an unnamed one is called after its task.
    callsign: str
    aircraft: str
    #: Where it leaves from, to tell two flights of the same task and jet apart.
    departure: str
    #: The kinds this airframe can be handed, in the order it wants them. A kind it
    #: cannot be given is not in the list: the control does not offer it rather than
    #: offering it and then explaining itself.
    kinds: list[str]
    #: How many more of each kind it has room for, keyed by kind.
    room: dict[str, int]
    points: list[SavedPointJs]


class NewPointJs(BaseModel):
    kind: str
    name: str
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    altitude_ft: int = 0


class SavedPointPosition(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)


class SavedPointEdit(BaseModel):
    name: str | None = None
    position: SavedPointPosition | None = None


def _kind(name: str) -> PointKind:
    try:
        return PointKind(name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"No such kind of point: {name}")


def _describe(game: Game, flight: object) -> ReceiverJs:
    from game.ato.flight import Flight

    assert isinstance(flight, Flight)
    aircraft = flight.unit_type.dcs_unit_type.id
    chosen = getattr(game.settings, "coordinate_format", None)
    return ReceiverJs(
        id=flight.id,
        callsign=flight.custom_name or str(flight.flight_type.value),
        aircraft=flight.unit_type.display_name,
        departure=flight.departure.name,
        kinds=[kind.value for kind in kinds_for(aircraft)],
        room={kind.value: room_for(flight, kind) for kind in PointKind},
        points=[
            SavedPointJs(
                id=point.id,
                position=LeafletPoint.from_latlng(
                    Point(point.x, point.y, game.theater.terrain).latlng()
                ),
                kind=point.kind.value,
                name=point.name,
                coordinates=(
                    format_latlng(
                        Point(point.x, point.y, game.theater.terrain).latlng(), chosen
                    )
                    if chosen is not None
                    else ""
                ),
                altitude_ft=point.altitude_ft,
            )
            for point in points_of(flight)
        ],
    )


@router.get("/", operation_id="list_point_receivers", response_model=list[ReceiverJs])
def list_receivers(game: Game = Depends(GameContext.require)) -> list[ReceiverJs]:
    """Every aircraft the player is actually flying this turn."""
    return [_describe(game, flight) for flight in receivers(game.blue)]


def _player_flight(game: Game, flight_id: UUID) -> Flight:
    try:
        flight = game.db.flights.get(flight_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such flight")
    if not any(one is flight for one in receivers(game.blue)):
        raise HTTPException(status_code=403, detail="Not a player aircraft")
    return flight


def _point(game: Game, flight_id: UUID, point_id: UUID) -> SavedPoint:
    for point in points_of(_player_flight(game, flight_id)):
        if point.id == point_id:
            return point
    raise HTTPException(status_code=404, detail="No such point")


@router.patch(
    "/{flight_id}/points/{point_id}",
    operation_id="edit_saved_point",
    response_model=ReceiverJs,
)
def edit(
    flight_id: UUID,
    point_id: UUID,
    changes: SavedPointEdit,
    game: Game = Depends(GameContext.require),
) -> ReceiverJs:
    point = _point(game, flight_id, point_id)
    at = None
    height = None
    if changes.position is not None:
        # Validate before changing the name so an invalid move cannot half-apply.
        at = Point.from_latlng(
            LatLng(changes.position.lat, changes.position.lng), game.theater.terrain
        )
        from game.elevation import elevation_ft

        height = elevation_ft(changes.position.lat, changes.position.lng)
        # Elevation lookup can block while Qt removes the point or its flight.
        # Resolve again before applying any edits to avoid a detached update.
        point = _point(game, flight_id, point_id)
    if changes.name is not None:
        point.name = changes.name.strip()[:24] or point.name
    if at is not None:
        point.x, point.y = at.x, at.y
        if height is not None:
            point.altitude_ft = max(0, height)
    publish_points_changed()
    return _describe(game, _player_flight(game, flight_id))


@router.delete(
    "/{flight_id}/points/{point_id}",
    operation_id="delete_saved_point_by_id",
    response_model=ReceiverJs,
)
def delete_by_id(
    flight_id: UUID, point_id: UUID, game: Game = Depends(GameContext.require)
) -> ReceiverJs:
    point = _point(game, flight_id, point_id)
    flight = _player_flight(game, flight_id)
    points_of(flight)[:] = [one for one in points_of(flight) if one is not point]
    publish_points_changed()
    return _describe(game, flight)


@router.post("/{flight_id}", operation_id="add_saved_point", response_model=ReceiverJs)
def add(
    flight_id: UUID,
    point: NewPointJs,
    game: Game = Depends(GameContext.require),
) -> ReceiverJs:
    flight = _player_flight(game, flight_id)
    at = Point.from_latlng(LatLng(point.lat, point.lng), game.theater.terrain)
    saved = SavedPoint(
        kind=_kind(point.kind),
        name=point.name.strip()[:24] or "Point",
        x=at.x,
        y=at.y,
        altitude_ft=max(0, point.altitude_ft),
    )
    if not add_point(flight, saved):
        raise HTTPException(
            status_code=409, detail=f"{flight.callsign} has no room for another"
        )
    publish_points_changed()
    return _describe(game, flight)


@router.delete(
    "/{flight_id}/{index}", operation_id="remove_saved_point", response_model=ReceiverJs
)
def remove(
    flight_id: UUID, index: int, game: Game = Depends(GameContext.require)
) -> ReceiverJs:
    flight = _player_flight(game, flight_id)
    if not remove_point(flight, index):
        raise HTTPException(status_code=404, detail="No such point")
    publish_points_changed()
    return _describe(game, flight)
