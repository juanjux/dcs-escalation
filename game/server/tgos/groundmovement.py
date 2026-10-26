"""Read-only armor movement eligibility and route previews for the player."""

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
)
from game.server.dependencies import GameContext
from game.server.leaflet import LeafletPoint
from game.theater.player import Player

router = APIRouter()


class MovementPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_ids: list[StrictInt] = Field(min_length=1, max_length=1000)
    destination_kind: DestinationKind
    position: LeafletPoint | None = None
    base_id: UUID | None = None
    opposing_base_id: UUID | None = None


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
    dispatch_available: bool = False


def _error(exc: Exception) -> HTTPException:
    return HTTPException(
        403 if isinstance(exc, PermissionError) else 400, detail=str(exc)
    )


@router.get(
    "/{tgo_id}/ground-movement/options",
    operation_id="armor_ground_movement_options",
)
def options(
    tgo_id: UUID, game: Game = Depends(GameContext.require)
) -> ArmorMovementOptions:
    try:
        return armor_movement_options(game, tgo_id, Player.BLUE)
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
) -> MovementPreviewJs:
    """Validate a proposed detachment without reserving, moving or copying units."""
    try:
        position = None
        if request.position is not None:
            if not (
                -90 <= request.position.lat <= 90
                and -180 <= request.position.lng <= 180
            ):
                raise ValueError("Invalid latitude or longitude")
            point = Point.from_latlng(
                LatLng(request.position.lat, request.position.lng), game.theater.terrain
            )
            position = GroundPosition(point.x, point.y)
        destination = movement_destination(
            game,
            Player.BLUE,
            request.destination_kind,
            position=position,
            base_id=request.base_id,
            opposing_base_id=request.opposing_base_id,
        )
        result = preview_armor_movement(
            game, tgo_id, Player.BLUE, request.unit_ids, destination
        )
    except (ValueError, PermissionError) as exc:
        raise _error(exc) from exc

    def latlng(position: GroundPosition) -> LeafletPoint:
        return LeafletPoint.from_latlng(
            Point(position.x, position.z, game.theater.terrain).latlng()
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
        destination=latlng(result.destination.position),
        base_id=result.destination.target_id,
        opposing_base_id=result.destination.opposing_base_id,
        segments=[
            MovementSegmentJs(
                start=latlng(segment.start),
                end=latlng(segment.end),
                on_road=segment.on_road,
                distance_m=segment.length,
            )
            for segment in result.route.segments
        ],
        road_distance_m=result.road_distance_m,
        offroad_distance_m=result.offroad_distance_m,
        travel_turns=result.travel_turns,
        arrival_in_turns=result.arrival_in_turns,
        first_turn_stop=latlng(result.first_turn_stop),
        warnings=list(result.warnings),
    )
