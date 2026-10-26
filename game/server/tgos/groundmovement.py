"""Player armor movement previews, commands and progress."""

from __future__ import annotations

from uuid import UUID

from dcs import Point
from dcs.mapping import LatLng
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from game import Game
from game.groundmovement.orders import DestinationKind, GroundPosition
from game.groundmovement.planning import (
    ArmorMovementOptions,
    armor_movement_options,
    movement_destination,
    preview_armor_movement,
    armor_source,
)
from game.groundmovement.orders import MovementDestination
from game.groundmovement.report import (
    ArmorMovementReport,
    movement_reports,
    preview_token,
)
from game.server.dependencies import GameContext
from game.server.leaflet import LeafletPoint
from game.theater.player import Player
from qt_ui.groundmovement import GroundMovementCommands, MovementCommandError

router = APIRouter()


class MovementPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_ids: list[StrictInt] = Field(min_length=1, max_length=1000)
    destination_kind: DestinationKind
    position: LeafletPoint | None = None
    base_id: UUID | None = None
    opposing_base_id: UUID | None = None


class MovementDispatchRequest(MovementPreviewRequest):
    preview_token: str = Field(min_length=64, max_length=64)


class MovementSegmentJs(BaseModel):
    start: LeafletPoint
    end: LeafletPoint
    on_road: bool
    distance_m: float


class MovementPreviewJs(BaseModel):
    source_id: UUID
    unit_ids: list[int]
    automatically_included_ids: list[int]
    remaining_unit_ids: list[int]
    towing: list[tuple[int, int]]
    destination_kind: DestinationKind
    destination: LeafletPoint
    base_id: UUID | None
    opposing_base_id: UUID | None
    segments: list[MovementSegmentJs]
    road_distance_m: float
    offroad_distance_m: float
    travel_turns: float
    arrival_in_turns: int
    first_turn_stop: LeafletPoint
    warnings: list[str]
    dispatch_available: bool = True
    preview_token: str


class MovementReportJs(BaseModel):
    order_id: UUID
    source_id: UUID
    detachment_id: UUID
    status: str
    pause_reason: str | None
    destination_kind: DestinationKind
    destination: LeafletPoint
    base_id: UUID | None
    opposing_base_id: UUID | None
    position: LeafletPoint
    total_distance_m: float
    remaining_distance_m: float
    progress: float
    remaining_turns: int | None
    surviving_units: int | None
    original_units: int
    towing: list[tuple[int, int]]

    @classmethod
    def for_report(cls, game: Game, report: ArmorMovementReport) -> MovementReportJs:
        return cls(
            **{
                key: value
                for key, value in vars(report).items()
                if key not in ("destination", "position")
            },
            destination_kind=report.destination.kind,
            destination=_latlng(game, report.destination.position),
            base_id=report.destination.target_id,
            opposing_base_id=report.destination.opposing_base_id,
            position=_latlng(game, report.position),
        )


def commands() -> GroundMovementCommands:
    return GameContext.get_model().ground_movement_commands


def _latlng(game: Game, position: GroundPosition) -> LeafletPoint:
    return LeafletPoint.from_latlng(
        Point(position.x, position.z, game.theater.terrain).latlng()
    )


def _destination(game: Game, request: MovementPreviewRequest) -> MovementDestination:
    position = None
    if request.position is not None:
        if not (
            -90 <= request.position.lat <= 90 and -180 <= request.position.lng <= 180
        ):
            raise ValueError("Invalid latitude or longitude")
        point = Point.from_latlng(
            LatLng(request.position.lat, request.position.lng), game.theater.terrain
        )
        position = GroundPosition(point.x, point.y)
    return movement_destination(
        game,
        Player.BLUE,
        request.destination_kind,
        position=position,
        base_id=request.base_id,
        opposing_base_id=request.opposing_base_id,
    )


def _error(exc: Exception) -> HTTPException:
    return HTTPException(
        (
            403
            if isinstance(exc, PermissionError)
            else 409 if isinstance(exc, MovementCommandError) else 400
        ),
        detail=str(exc),
    )


@router.get(
    "/{tgo_id}/ground-movement/options",
    operation_id="armor_ground_movement_options",
)
def options(
    tgo_id: UUID,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> ArmorMovementOptions:
    try:
        return service.run(
            lambda: service.inspect(
                game, lambda: armor_movement_options(game, tgo_id, Player.BLUE)
            )
        )
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{tgo_id}/ground-movement/preview",
    operation_id="preview_armor_ground_movement",
    response_model=MovementPreviewJs,
)
def preview(
    tgo_id: UUID,
    request: MovementPreviewRequest,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> MovementPreviewJs:
    """Validate a proposed detachment without reserving, moving or copying units."""
    try:
        return service.run(
            lambda: service.inspect(game, lambda: _preview(game, tgo_id, request))
        )
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


def _preview(
    game: Game, tgo_id: UUID, request: MovementPreviewRequest
) -> MovementPreviewJs:
    result = preview_armor_movement(
        game, tgo_id, Player.BLUE, request.unit_ids, _destination(game, request)
    )
    return MovementPreviewJs(
        source_id=result.source_id,
        unit_ids=list(result.manifest.unit_ids),
        automatically_included_ids=sorted(
            set(result.manifest.unit_ids) - set(request.unit_ids)
        ),
        remaining_unit_ids=list(result.remaining_unit_ids),
        towing=list(result.manifest.towing),
        destination_kind=result.destination.kind,
        destination=_latlng(game, result.destination.position),
        base_id=result.destination.target_id,
        opposing_base_id=result.destination.opposing_base_id,
        segments=[
            MovementSegmentJs(
                start=_latlng(game, segment.start),
                end=_latlng(game, segment.end),
                on_road=segment.on_road,
                distance_m=segment.length,
            )
            for segment in result.route.segments
        ],
        road_distance_m=result.road_distance_m,
        offroad_distance_m=result.offroad_distance_m,
        travel_turns=result.travel_turns,
        arrival_in_turns=result.arrival_in_turns,
        first_turn_stop=_latlng(game, result.first_turn_stop),
        warnings=list(result.warnings),
        preview_token=preview_token(game, result),
    )


@router.get("/{tgo_id}/ground-movement", operation_id="armor_ground_movements")
def progress(
    tgo_id: UUID,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> list[MovementReportJs]:
    def inspect() -> list[MovementReportJs]:
        armor_source(game, tgo_id, Player.BLUE)
        return [
            MovementReportJs.for_report(game, report)
            for report in movement_reports(game, tgo_id, Player.BLUE)
        ]

    try:
        return service.run(lambda: service.inspect(game, inspect))
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.post("/{tgo_id}/ground-movement", operation_id="dispatch_armor_ground_movement")
def dispatch(
    tgo_id: UUID,
    request: MovementDispatchRequest,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> MovementReportJs:
    def execute() -> MovementReportJs:
        transit = service.dispatch(
            game,
            tgo_id,
            Player.BLUE,
            request.unit_ids,
            _destination(game, request),
            request.preview_token,
        )
        return MovementReportJs.for_report(
            game, movement_reports(game, transit.detachment_id, Player.BLUE)[0]
        )

    try:
        return service.run(execute)
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc


@router.post(
    "/{tgo_id}/ground-movement/{order_id}/stop",
    operation_id="stop_armor_ground_movement",
)
def stop(
    tgo_id: UUID,
    order_id: UUID,
    game: Game = Depends(GameContext.require),
    service: GroundMovementCommands = Depends(commands),
) -> MovementReportJs:
    def execute() -> MovementReportJs:
        armor_source(game, tgo_id, Player.BLUE)
        reports = movement_reports(game, tgo_id, Player.BLUE)
        if not any(report.order_id == order_id for report in reports):
            raise ValueError("No such movement for this armor group")
        service.stop(game, order_id, Player.BLUE)
        report = next(
            report
            for report in movement_reports(game, tgo_id, Player.BLUE)
            if report.order_id == order_id
        )
        return MovementReportJs.for_report(game, report)

    try:
        return service.run(execute)
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc
