"""Create reserve armor groups from player-owned base stock."""

from uuid import UUID

from dcs import Point
from dcs.mapping import LatLng
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from game import Game
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.base import available_stock, base_source, preview_base_movement
from game.groundmovement.orders import GroundPosition
from game.groundmovement.report import movement_reports, preview_token
from game.groundmovement.settings import enabled
from game.server.dependencies import GameContext
from game.server.leaflet import LeafletPoint
from game.server.tgos.groundmovement import (
    MovementReportJs,
    MovementSegmentJs,
    _error,
    _latlng,
    commands,
)
from game.theater.player import Player
from qt_ui.groundmovement import GroundMovementCommands

router = APIRouter()


class BaseMovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    units: dict[str, StrictInt] = Field(min_length=1, max_length=1000)
    position: LeafletPoint


class BaseMovementDispatchRequest(BaseMovementRequest):
    preview_token: str = Field(min_length=64, max_length=64)


def selection(request: BaseMovementRequest) -> dict[GroundUnitType, int]:
    try:
        selected = {
            GroundUnitType.named(name): count for name, count in request.units.items()
        }
        if len(selected) != len(request.units):
            raise ValueError("Select each ground unit type only once")
        return selected
    except KeyError as exc:
        raise ValueError("Unknown ground unit type") from exc


def position(game: Game, request: BaseMovementRequest) -> GroundPosition:
    if not (-90 <= request.position.lat <= 90 and -180 <= request.position.lng <= 180):
        raise ValueError("Invalid latitude or longitude")
    point = Point.from_latlng(
        LatLng(request.position.lat, request.position.lng), game.theater.terrain
    )
    return GroundPosition(point.x, point.y)


class BaseStockUnitJs(BaseModel):
    unit_type: str
    name: str
    available: int
    mobility: str
    can_tow: bool


class BaseMovementOptionsJs(BaseModel):
    enabled: bool
    units: list[BaseStockUnitJs]


class BaseMovementPreviewJs(BaseModel):
    source_id: UUID
    units: dict[str, int]
    automatically_added: dict[str, int]
    segments: list[MovementSegmentJs]
    road_distance_m: float
    offroad_distance_m: float
    arrival_in_turns: int
    preview_token: str


@router.get(
    "/{cp_id}/ground-movement/options", operation_id="base_ground_movement_options"
)
def options(
    cp_id: UUID,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> BaseMovementOptionsJs:
    def inspect() -> BaseMovementOptionsJs:
        base = base_source(game, cp_id, Player.BLUE)
        return BaseMovementOptionsJs(
            enabled=enabled(game.settings),
            units=[
                BaseStockUnitJs(
                    unit_type=u.variant_id,
                    name=u.display_name,
                    available=n,
                    mobility=u.ground_mobility.mode.value,
                    can_tow=u.ground_mobility.can_tow,
                )
                for u, n in sorted(
                    available_stock(base).items(), key=lambda item: item[0].variant_id
                )
            ],
        )

    try:
        return service.run(lambda: service.inspect(game, inspect))
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{cp_id}/ground-movement/preview", operation_id="preview_base_ground_movement"
)
def preview(
    cp_id: UUID,
    request: BaseMovementRequest,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> BaseMovementPreviewJs:
    def inspect() -> BaseMovementPreviewJs:
        result = preview_base_movement(
            game, cp_id, Player.BLUE, selection(request), position(game, request)
        )
        return BaseMovementPreviewJs(
            source_id=cp_id,
            units=dict(result.units),
            automatically_added=dict(result.automatically_added),
            segments=[
                MovementSegmentJs(
                    start=_latlng(game, s.start),
                    end=_latlng(game, s.end),
                    on_road=s.on_road,
                    distance_m=s.length,
                )
                for s in result.route.segments
            ],
            road_distance_m=result.road_distance_m,
            offroad_distance_m=result.offroad_distance_m,
            arrival_in_turns=result.arrival_in_turns,
            preview_token=preview_token(game, result),
        )

    try:
        return service.run(lambda: service.inspect(game, inspect))
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.post("/{cp_id}/ground-movement", operation_id="dispatch_base_ground_movement")
def dispatch(
    cp_id: UUID,
    request: BaseMovementDispatchRequest,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> MovementReportJs:
    def execute() -> MovementReportJs:
        result = service.dispatch_base(
            game,
            cp_id,
            Player.BLUE,
            selection(request),
            position(game, request),
            request.preview_token,
        )
        return MovementReportJs.for_report(
            game, movement_reports(game, result.detachment_id, Player.BLUE)[0]
        )

    try:
        return service.run(execute)
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.get("/{cp_id}/ground-movement", operation_id="base_ground_movements")
def progress(
    cp_id: UUID,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> list[MovementReportJs]:
    def inspect() -> list[MovementReportJs]:
        base_source(game, cp_id, Player.BLUE)
        return [
            MovementReportJs.for_report(game, r)
            for r in movement_reports(game, cp_id, Player.BLUE)
        ]

    try:
        return service.run(lambda: service.inspect(game, inspect))
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc
