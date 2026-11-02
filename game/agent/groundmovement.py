"""RED reserve movement using the same rules and commands as the player."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any, TYPE_CHECKING
from uuid import UUID

from dcs import Point
from dcs.mapping import LatLng

from game.agent import schemas, views
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.base import (
    BaseMovementPreview,
    available_stock,
    base_source,
    preview_base_movement,
)
from game.groundmovement.dispatch import active_transit
from game.groundmovement.journey import GroundJourney
from game.groundmovement.orders import DestinationKind, GroundPosition
from game.groundmovement.planning import (
    armor_source,
    armor_movement_options,
    movement_destination,
    preview_armor_movement,
)
from game.groundmovement.report import (
    ArmorMovementReport,
    movement_reports,
    preview_token,
)
from game.groundmovement.settings import distance_per_turn, enabled, requested
from game.theater.player import Player
from game.theater.theatergroundobject import VehicleGroupGroundObject, IadsGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.groundmovement.planning import ArmorMovementPreview
    from game.theater.controlpoint import ControlPoint
    from qt_ui.groundmovement import GroundMovementCommands


def _armor(
    game: Game, source_id: UUID, source_kind: str = "armor"
) -> VehicleGroupGroundObject | IadsGroundObject:
    try:
        source = armor_source(game, source_id, Player.RED)
        expected = (
            IadsGroundObject if source_kind == "sam" else VehicleGroupGroundObject
        )
        if not isinstance(source, expected):
            raise ValueError("Source kind does not match the ground group")
        return source
    except (ValueError, PermissionError) as exc:
        raise ValueError(
            "Unknown own ground group or mismatched source_kind (armor/sam)"
        ) from exc


def _base(game: Game, source_id: UUID) -> ControlPoint:
    try:
        return base_source(game, source_id, Player.RED)
    except (ValueError, PermissionError) as exc:
        raise ValueError("Unknown own ground base") from exc


def _ll(game: Game, position: GroundPosition) -> list[float]:
    at = Point(position.x, position.z, game.theater.terrain).latlng()
    return [at.lat, at.lng]


def report(game: Game, item: ArmorMovementReport) -> views.ArmorMovementView:
    return views.ArmorMovementView(
        order_id=str(item.order_id),
        source_id=str(item.source_id),
        detachment_id=str(item.detachment_id),
        status=item.status,
        pause_reason=item.pause_reason,
        destination_kind=item.destination.kind.value,
        destination=_ll(game, item.destination.position),
        base_id=str(item.destination.target_id) if item.destination.target_id else None,
        opposing_base_id=(
            str(item.destination.opposing_base_id)
            if item.destination.opposing_base_id
            else None
        ),
        pos=_ll(game, item.position),
        total_distance_m=round(item.total_distance_m, 1),
        remaining_distance_m=round(item.remaining_distance_m, 1),
        progress_percent=round(item.progress * 100, 1),
        remaining_turns=item.remaining_turns,
        surviving_units=item.surviving_units,
        original_units=item.original_units,
    )


def orders(game: Game, owner: Player = Player.RED) -> list[views.ArmorMovementView]:
    store = getattr(game, "ground_movements", None)
    if store is None:
        return []
    rows: list[views.ArmorMovementView] = []
    cached: dict[UUID, tuple[ArmorMovementReport, ...]] = {}
    for transit in store.transits.values():
        if store.orders[transit.order_id].owner is not owner:
            continue
        if transit.detachment_id not in cached:
            cached[transit.detachment_id] = movement_reports(
                game, transit.detachment_id, owner
            )
        rows.extend(
            report(game, item)
            for item in cached[transit.detachment_id]
            if item.order_id == transit.order_id
        )
    return sorted(rows, key=lambda row: row.order_id)


def context(game: Game, owner: Player) -> views.GroundMovementContextView | None:
    store = getattr(game, "ground_movements", None)
    if store is None or (not requested(game.settings) and not store.transits):
        return None
    groups: list[views.ReserveArmorGroupView] = []
    sam_sites: list[views.ReserveArmorGroupView] = []
    for cp in game.theater.controlpoints:
        if not cp.is_friendly(owner):
            continue
        for group in cp.ground_objects:
            if (
                not isinstance(group, (VehicleGroupGroundObject, IadsGroundObject))
                or group.is_dead
            ):
                continue
            options = armor_movement_options(game, group.id, owner)
            point = group.position.latlng()
            moving = active_transit(game, group.id) is not None
            (sam_sites if isinstance(group, IadsGroundObject) else groups).append(
                views.ReserveArmorGroupView(
                    id=str(group.id),
                    name=group.name,
                    base_id=str(cp.id),
                    pos=[round(point.lat, 5), round(point.lng, 5)],
                    composition=dict(Counter(u.name for u in options.units)),
                    selectable_units=(
                        0
                        if moving or not options.enabled
                        else sum(u.selectable for u in options.units)
                    ),
                    in_transit=moving,
                )
            )
    return views.GroundMovementContextView(
        enabled=enabled(game.settings),
        road_distance_per_turn_m=distance_per_turn(game.settings, on_road=True),
        offroad_distance_per_turn_m=distance_per_turn(game.settings, on_road=False),
        reserve_groups=sorted(groups, key=lambda row: row.id),
        sam_sites=sorted(sam_sites, key=lambda row: row.id),
        orders=orders(game, owner),
    )


def options(game: Game, source_id: UUID, source_kind: str) -> dict[str, Any]:
    if source_kind in ("armor", "sam"):
        _armor(game, source_id, source_kind)
        result = asdict(armor_movement_options(game, source_id, Player.RED))
        result["source_id"] = str(source_id)
        result["in_transit"] = active_transit(game, source_id) is not None
        if result["in_transit"]:
            result["warnings"] += ("Stop this detachment before assigning a new route",)
            for unit in result["units"]:
                unit["selectable"] = False
    elif source_kind == "base":
        base = _base(game, source_id)
        result = {
            "source_id": str(source_id),
            "enabled": enabled(game.settings),
            "units": [
                {
                    "unit_type": unit.variant_id,
                    "name": unit.display_name,
                    "available": count,
                    "mobility": unit.ground_mobility.mode.value,
                    "can_tow": unit.ground_mobility.can_tow,
                }
                for unit, count in sorted(
                    available_stock(base).items(), key=lambda entry: entry[0].variant_id
                )
            ],
        }
    else:
        raise ValueError("Source kind must be armor, sam or base")
    result["source_kind"] = source_kind
    result["bases"] = [
        {"id": str(cp.id), "name": cp.name}
        for cp in game.theater.controlpoints
        if cp.is_friendly(Player.RED) and not cp.is_fleet and cp.can_deploy_ground_units
    ]
    result["fronts"] = [
        {
            "base_id": str(cp.id),
            "opposing_base_id": str(enemy.id),
            "name": f"{cp.name} / {enemy.name}",
        }
        for cp in game.theater.controlpoints
        if cp.is_friendly(Player.RED) and not cp.is_fleet and cp.can_deploy_ground_units
        for enemy in cp.front_lines
        if not enemy.is_friendly(Player.RED)
    ]
    if source_kind == "sam":
        result["bases"] = []
        result["fronts"] = []
    return result


def _selection(request: schemas.GroundMovementRequest) -> dict[GroundUnitType, int]:
    if request.unit_ids is not None or not request.units:
        raise ValueError("Base deployment requires units, not unit_ids")
    try:
        result = {
            GroundUnitType.named(name): count for name, count in request.units.items()
        }
    except KeyError as exc:
        raise ValueError("Unknown ground unit type") from exc
    if len(result) != len(request.units) or any(
        count <= 0 for count in result.values()
    ):
        raise ValueError("Use distinct unit types with positive quantities")
    return result


def _position(
    game: Game, request: schemas.GroundMovementRequest
) -> GroundPosition | None:
    if request.lat is None and request.lng is None:
        return None
    if request.lat is None or request.lng is None:
        raise ValueError("Provide both latitude and longitude")
    point = Point.from_latlng(LatLng(request.lat, request.lng), game.theater.terrain)
    return GroundPosition(point.x, point.y)


def preview(
    game: Game, request: schemas.GroundMovementRequest
) -> ArmorMovementPreview | BaseMovementPreview:
    if request.source_kind == "base":
        _base(game, request.source_id)
    else:
        _armor(game, request.source_id, request.source_kind)
        if request.units is not None or not request.unit_ids:
            raise ValueError("Armor movement requires unit_ids, not units")
    destination = movement_destination(
        game,
        Player.RED,
        DestinationKind(request.destination_kind),
        position=_position(game, request),
        base_id=request.base_id,
        opposing_base_id=request.opposing_base_id,
    )
    if request.source_kind == "base":
        if destination.kind is not DestinationKind.POSITION:
            raise ValueError(
                "Use transfer_ground for base-to-base transfers; reserve deployment needs a GPS position"
            )
        return preview_base_movement(
            game,
            request.source_id,
            Player.RED,
            _selection(request),
            destination.position,
        )
    return preview_armor_movement(
        game, request.source_id, Player.RED, request.unit_ids or [], destination
    )


def preview_view(game: Game, request: schemas.GroundMovementRequest) -> dict[str, Any]:
    result = preview(game, request)
    response: dict[str, Any] = {
        "source_id": str(request.source_id),
        "source_kind": request.source_kind,
        "destination_kind": result.destination.kind.value,
        "destination": _ll(game, result.destination.position),
        "total_distance_m": round(result.route.length, 1),
        "road_distance_m": round(result.road_distance_m, 1),
        "offroad_distance_m": round(result.offroad_distance_m, 1),
        "arrival_in_turns": result.arrival_in_turns,
        "preview_token": preview_token(game, result),
    }
    if isinstance(result, BaseMovementPreview):
        response["first_turn_stop"] = _ll(
            game,
            GroundJourney(result.route).preview(
                distance_per_turn(game.settings, on_road=True),
                distance_per_turn(game.settings, on_road=False),
            )[-1],
        )
        response["warnings"] = []
        response["units"] = dict(result.units)
        response["automatically_added"] = dict(result.automatically_added)
    else:
        response["first_turn_stop"] = _ll(game, result.first_turn_stop)
        response["unit_ids"] = list(result.manifest.unit_ids)
        response["towing"] = [list(pair) for pair in result.manifest.towing]
        response["warnings"] = list(result.warnings)
        response["automatically_included_ids"] = sorted(
            set(result.manifest.unit_ids) - set(request.unit_ids or [])
        )
    return response


def dispatch(
    game: Game,
    commands: GroundMovementCommands,
    request: schemas.GroundMovementDispatchRequest,
) -> dict[str, Any]:
    commands.require_planning(game)
    proposed = preview(game, request)
    if request.source_kind == "base":
        transit = commands.dispatch_base(
            game,
            request.source_id,
            Player.RED,
            _selection(request),
            proposed.destination.position,
            request.preview_token,
        )
    else:
        transit = commands.dispatch(
            game,
            request.source_id,
            Player.RED,
            request.unit_ids or [],
            proposed.destination,
            request.preview_token,
        )
    result = next(
        item
        for item in movement_reports(game, transit.detachment_id, Player.RED)
        if item.order_id == transit.order_id
    )
    return report(game, result).model_dump(exclude_none=True)


def stop(
    game: Game, commands: GroundMovementCommands, order_id: UUID
) -> dict[str, Any]:
    commands.require_planning(game)
    store = getattr(game, "ground_movements", None)
    if (
        store is None
        or order_id not in store.transits
        or store.orders[order_id].owner is not Player.RED
    ):
        raise ValueError("Unknown own ground movement")
    tgo_id = store.transits[order_id].detachment_id
    armor_source(game, tgo_id, Player.RED)
    commands.stop(game, order_id, Player.RED)
    result = next(
        item
        for item in movement_reports(game, tgo_id, Player.RED)
        if item.order_id == order_id
    )
    return report(game, result).model_dump(exclude_none=True)
