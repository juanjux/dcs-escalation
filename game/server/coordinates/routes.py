"""Formatting a point on the map, in the campaign's chosen coordinate format."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dcs.mapping import LatLng, Point

from game import Game
from game.coordinates import CoordinateFormat, format_latlng
from game.server import GameContext

router: APIRouter = APIRouter(prefix="/coordinates")


class CoordinatesJs(BaseModel):
    text: str
    format: str
    #: Every format for the same point, so a client can offer the others without asking
    #: again.
    all: dict[str, str]


@router.get("/", operation_id="get_coordinates", response_model=CoordinatesJs)
def get_coordinates(
    lat: float, lng: float, game: Game = Depends(GameContext.require)
) -> CoordinatesJs:
    chosen = getattr(game.settings, "coordinate_format", CoordinateFormat.DDM)
    latlng = LatLng(lat, lng)
    return CoordinatesJs(
        text=format_latlng(latlng, chosen),
        format=chosen.name,
        all={fmt.name: format_latlng(latlng, fmt) for fmt in CoordinateFormat},
    )
