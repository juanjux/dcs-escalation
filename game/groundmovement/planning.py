"""Shared, non-mutating validation of armor and SAM movement requests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, TYPE_CHECKING
from uuid import UUID

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.journey import GroundJourney, GroundRoute
from game.groundmovement.mobility import MobilityMode
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
    TransportManifest,
    plan_transport,
)
from game.groundmovement.routing import CampaignGroundRouter
from game.groundmovement.settings import distance_per_turn, enabled
from game.groundmovement.territory import require_friendly_position
from game.theater.player import Player
from game.theater.theatergroundobject import VehicleGroupGroundObject, IadsGroundObject

MovementGroup = VehicleGroupGroundObject | IadsGroundObject

if TYPE_CHECKING:
    from game import Game


@dataclass(frozen=True)
class ArmorMovementUnit:
    id: int
    name: str
    unit_type: str
    mobility: str
    can_tow: bool
    reserved: bool
    selectable: bool


@dataclass(frozen=True)
class ArmorMovementOptions:
    source_id: UUID
    enabled: bool
    units: tuple[ArmorMovementUnit, ...]
    available_tractors: int
    towed_pieces: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ArmorMovementPreview:
    source_id: UUID
    manifest: TransportManifest
    remaining_unit_ids: tuple[int, ...]
    destination: MovementDestination
    route: GroundRoute
    road_distance_m: float
    offroad_distance_m: float
    travel_turns: float
    arrival_in_turns: int
    first_turn_stop: GroundPosition
    warnings: tuple[str, ...]


def armor_source(game: Game, source_id: UUID, owner: Player) -> MovementGroup:
    if owner not in (Player.BLUE, Player.RED):
        raise ValueError("Ground movement needs a BLUE or RED owner")
    try:
        source = game.db.tgos.get(source_id)
    except KeyError as exc:
        raise ValueError("Ground movement source does not exist") from exc
    if not source.is_friendly(owner):
        raise PermissionError("The ground movement source belongs to another side")
    if not isinstance(source, (VehicleGroupGroundObject, IadsGroundObject)):
        raise ValueError("This operation requires an armor group or SAM/radar site")
    return source


def _unit_types(source: MovementGroup) -> dict[int, GroundUnitType]:
    result = {}
    for unit in source.units:
        if not unit.alive or not unit.is_vehicle:
            continue
        unit_type = unit.unit_type
        if isinstance(unit_type, GroundUnitType):
            if unit.id in result:
                raise ValueError("The armor group contains duplicate unit identities")
            result[unit.id] = unit_type
    return result


def _sam_warnings(source: IadsGroundObject) -> list[str]:
    warnings = []
    if any(
        u.alive and (not u.is_vehicle or not isinstance(u.unit_type, GroundUnitType))
        for u in source.units
    ):
        warnings.append(
            "This site contains fixed structures or unsupported units and cannot relocate"
        )
    if any(u.repair_turns_remaining is not None for u in source.units):
        warnings.append(
            "Finish or cancel pending repairs before relocating the whole site"
        )
    if not any(u.alive for u in source.units):
        warnings.append("There are no surviving units to relocate")
    return warnings


def _reserved(game: Game) -> set[int]:
    orders = getattr(game, "ground_movements", None)
    return orders.reserved_unit_ids if orders is not None else set()


def armor_movement_options(
    game: Game, source_id: UUID, owner: Player
) -> ArmorMovementOptions:
    source = armor_source(game, source_id, owner)
    reserved = _reserved(game)
    unit_types = _unit_types(source)
    available = {i: unit for i, unit in unit_types.items() if i not in reserved}
    is_sam = isinstance(source, IadsGroundObject)
    tractors = sum(unit.ground_mobility.can_tow for unit in available.values())
    pieces = sum(
        unit.ground_mobility.mode is MobilityMode.TOWED for unit in available.values()
    )
    warnings = []
    if not enabled(game.settings):
        warnings.append("Ground Movement and Motor Pool must both be enabled")
    if pieces > tractors:
        warnings.append(
            f"{pieces} towed pieces need {pieces} tractors; only {tractors} are available. "
            + (
                "The entire battery needs transport."
                if is_sam
                else "Select a smaller detachment."
            )
        )
    unsupported = sorted(
        {
            unit.display_name
            for unit in available.values()
            if unit.ground_mobility.mode in (MobilityMode.UNKNOWN, MobilityMode.FIXED)
        }
    )
    if unsupported:
        warnings.append("Mobility is not available for: " + ", ".join(unsupported))
    sam_warnings = []
    if isinstance(source, IadsGroundObject):
        sam_warnings = _sam_warnings(source)
        if len(available) != len(unit_types):
            sam_warnings.append("Some battery units are already reserved for movement")
        warnings.extend(sam_warnings)
        warnings.append(
            "SAM/radar sites relocate as a whole. Radars and weapons are packed and unavailable until arrival or an explicit stop."
        )
    sam_ready = not is_sam or (
        not unsupported
        and pieces <= tractors
        and not sam_warnings
        and len(available) == len(unit_types)
    )
    return ArmorMovementOptions(
        source.id,
        enabled(game.settings) and sam_ready,
        tuple(
            ArmorMovementUnit(
                i,
                unit.display_name,
                unit.variant_id,
                unit.ground_mobility.mode.value,
                unit.ground_mobility.can_tow,
                i in reserved,
                i not in reserved
                and unit.ground_mobility.mode
                in (MobilityMode.SELF_PROPELLED, MobilityMode.TOWED),
            )
            for i, unit in sorted(unit_types.items())
        ),
        tractors,
        pieces,
        tuple(warnings),
    )


def movement_destination(
    game: Game,
    owner: Player,
    kind: DestinationKind,
    *,
    position: GroundPosition | None = None,
    base_id: UUID | None = None,
    opposing_base_id: UUID | None = None,
) -> MovementDestination:
    if kind is DestinationKind.POSITION:
        if position is None or base_id is not None or opposing_base_id is not None:
            raise ValueError("A map destination requires only its position")
        require_friendly_position(game, owner, position)
        return MovementDestination(kind, position)
    if kind not in (DestinationKind.BASE, DestinationKind.FRONTLINE):
        raise ValueError("Unknown ground movement destination")
    if position is not None or base_id is None:
        raise ValueError(
            "Base and frontline positions are resolved from their base IDs"
        )
    base = next((cp for cp in game.theater.controlpoints if cp.id == base_id), None)
    if base is None:
        raise ValueError("The destination base does not exist")
    if not base.is_friendly(owner):
        raise PermissionError("The destination base belongs to another side")
    if base.is_fleet:
        raise ValueError("Ground units cannot be delivered to a fleet")
    if not base.can_deploy_ground_units:
        raise ValueError("The destination base cannot host ground units")
    if kind is DestinationKind.FRONTLINE:
        opponent = next(
            (cp for cp in game.theater.controlpoints if cp.id == opposing_base_id), None
        )
        if (
            opponent is None
            or opponent.is_friendly(owner)
            or opponent.captured.is_neutral
        ):
            raise ValueError("A frontline destination requires an opposing enemy base")
        if opponent not in base.front_lines:
            raise ValueError("There is no active front between those bases")
    elif opposing_base_id is not None:
        raise ValueError("A base destination cannot include an opposing base")
    # Frontline reinforcements enter the supporting base's stock. Deployment caps
    # select the deployed force and its reserve; the motor pool is not new stock.
    return MovementDestination(
        kind,
        GroundPosition(base.position.x, base.position.y),
        base.id,
        opposing_base_id,
    )


def preview_armor_movement(
    game: Game,
    source_id: UUID,
    owner: Player,
    selected: Iterable[int],
    destination: MovementDestination,
) -> ArmorMovementPreview:
    source = armor_source(game, source_id, owner)
    if not enabled(game.settings):
        raise ValueError("Ground Movement and Motor Pool must both be enabled")
    if isinstance(source, IadsGroundObject):
        if destination.kind is not DestinationKind.POSITION:
            raise ValueError(
                "SAM sites relocate to friendly positions; they cannot join bases or fronts"
            )
        warnings = _sam_warnings(source)
        if warnings:
            raise ValueError("; ".join(warnings))
    canonical = movement_destination(
        game,
        owner,
        destination.kind,
        position=(
            destination.position
            if destination.kind is DestinationKind.POSITION
            else None
        ),
        base_id=destination.target_id,
        opposing_base_id=destination.opposing_base_id,
    )
    if destination != canonical:
        raise ValueError("The destination position is stale; request a new preview")
    reserved = _reserved(game)
    all_units = _unit_types(source)
    units = {i: unit for i, unit in all_units.items() if i not in reserved}
    manifest = plan_transport(units, selected)
    if isinstance(source, IadsGroundObject) and set(manifest.unit_ids) != set(
        all_units
    ):
        raise ValueError(
            "SAM relocation requires every surviving unit; partial moves are not supported"
        )
    road_budget = distance_per_turn(game.settings, on_road=True)
    offroad_budget = distance_per_turn(game.settings, on_road=False)
    route = CampaignGroundRouter.for_game(game, owner).plan(
        GroundPosition(source.position.x, source.position.y),
        destination.position,
        road_budget,
        offroad_budget,
    )
    road = sum(segment.length for segment in route.segments if segment.on_road)
    offroad = sum(segment.length for segment in route.segments if not segment.on_road)
    turns = road / road_budget + offroad / offroad_budget
    warnings = [
        "Road planning uses the same authored campaign corridors as supply convoys, "
        "not the complete DCS road network. Off-road access must stay on mapped "
        "land and clear exclusion zones."
    ]
    if road == 0:
        warnings.append("This route contains only validated off-road travel")
    return ArmorMovementPreview(
        source.id,
        manifest,
        tuple(sorted(set(all_units) - set(manifest.unit_ids))),
        destination,
        route,
        road,
        offroad,
        turns,
        max(1, math.ceil(turns - 1e-9)),
        GroundJourney(route).preview(road_budget, offroad_budget)[-1],
        tuple(warnings),
    )
