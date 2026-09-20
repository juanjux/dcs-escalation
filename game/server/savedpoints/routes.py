"""Putting a point from the map into one of the player's own aircraft."""

from __future__ import annotations

from uuid import UUID

from dcs.mapping import LatLng, Point
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from game import Game
from game.ato.savedpoints import (
    PointKind,
    SavedPoint,
    add_point,
    kinds_for,
    points_of,
    reaches_the_aircraft,
    receivers,
    remove_point,
    room_for,
)
from game.coordinates import format_latlng
from game.server import GameContext

router: APIRouter = APIRouter(prefix="/saved-points")


class SavedPointJs(BaseModel):
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
    #: The kinds this airframe is offered, in the order it wants them.
    kinds: list[str]
    #: How many more of each kind it has room for, keyed by kind.
    room: dict[str, int]
    #: Whether the airframe itself carries that kind. A kind it does not carry is
    #: still saved -- the kneeboard takes both -- so this is what to say, not what to
    #: refuse.
    into_aircraft: dict[str, bool]
    points: list[SavedPointJs]


class NewPointJs(BaseModel):
    kind: str
    name: str
    lat: float
    lng: float
    altitude_ft: int = 0


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
        into_aircraft={
            kind.value: reaches_the_aircraft(aircraft, kind) for kind in PointKind
        },
        points=[
            SavedPointJs(
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


@router.post("/{flight_id}", operation_id="add_saved_point", response_model=ReceiverJs)
def add(
    flight_id: UUID,
    point: NewPointJs,
    game: Game = Depends(GameContext.require),
) -> ReceiverJs:
    flight = game.db.flights.get(flight_id)
    if flight.client_count <= 0:
        raise HTTPException(
            status_code=400, detail="Nobody is flying that aircraft to read it"
        )
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
    return _describe(game, flight)


@router.delete(
    "/{flight_id}/{index}", operation_id="remove_saved_point", response_model=ReceiverJs
)
def remove(
    flight_id: UUID, index: int, game: Game = Depends(GameContext.require)
) -> ReceiverJs:
    flight = game.db.flights.get(flight_id)
    if not remove_point(flight, index):
        raise HTTPException(status_code=404, detail="No such point")
    return _describe(game, flight)
