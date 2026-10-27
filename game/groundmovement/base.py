"""Deploy counted base stock as persistent, identity-bearing reserve groups."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Mapping, TYPE_CHECKING
from uuid import UUID, uuid4

from dcs import Point
from shapely.geometry import Point as MapPoint

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.dispatch import ArmorTransit
from game.groundmovement.journey import GroundJourney, GroundRoute
from game.groundmovement.orders import (
    DestinationKind,
    GroundMovementOrder,
    GroundPosition,
    MovementDestination,
    MovementSource,
    TransportManifest,
    plan_transport,
)
from game.groundmovement.planning import movement_destination
from game.groundmovement.routing import CampaignGroundRouter
from game.groundmovement.settings import distance_per_turn, enabled
from game.point_with_heading import PointWithHeading
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import VehicleGroupGroundObject
from game.theater.theatergroup import TheaterGroup, TheaterUnit
from game.utils import Heading

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater.controlpoint import ControlPoint

Stock = tuple[tuple[str, int], ...]


def base_source(game: Game, source_id: UUID, owner: Player) -> ControlPoint:
    base = next((cp for cp in game.theater.controlpoints if cp.id == source_id), None)
    if base is None:
        raise ValueError("The source base does not exist")
    if owner not in (Player.BLUE, Player.RED) or not base.is_friendly(owner):
        raise PermissionError("The source base belongs to another side")
    if base.is_fleet or not base.can_deploy_ground_units:
        raise ValueError("Reserve groups require a land base with ground units")
    return base


def available_stock(base: ControlPoint) -> dict[GroundUnitType, int]:
    """Undeparted transfers still own stock at the base, but already promise it."""
    stock = Counter(base.base.armor)
    for transfer in base.coalition.transfers:
        if transfer.origin is base and not transfer.departed:
            stock.subtract(transfer.units)
    return {unit: count for unit, count in stock.items() if count > 0}


def stock_tuple(units: Mapping[GroundUnitType, int]) -> Stock:
    return tuple(
        sorted((unit.variant_id, count) for unit, count in units.items() if count)
    )


def formation(
    game: Game, center: GroundPosition, count: int
) -> tuple[GroundPosition, ...]:
    """Place separated vehicles near the marker, on mapped, non-excluded land."""
    landmap = game.theater.landmap
    if landmap is None:
        raise ValueError("Reserve groups need land and exclusion-zone data")
    search_radius = math.hypot(600, 600) + 15
    occupied = [
        (unit.position.x, unit.position.y)
        for cp in game.theater.controlpoints
        for tgo in cp.ground_objects
        for unit in tgo.units
        if unit.alive
        and math.hypot(unit.position.x - center.x, unit.position.y - center.z)
        < search_radius
    ]
    for transit in game.ground_movements.transits.values():
        if not transit.finished:
            for p in (getattr(transit, "arrival_positions", None) or {}).values():
                if math.hypot(p.x - center.x, p.z - center.z) < search_radius:
                    occupied.append((p.x, p.z))
    positions = []
    for ring in range(1, 41):
        for x in range(-ring, ring + 1):
            for z in range(-ring, ring + 1):
                if max(abs(x), abs(z)) != ring:
                    continue
                point = GroundPosition(center.x + x * 15, center.z + z * 15)
                shape = MapPoint(point.x, point.z)
                if (
                    landmap.inclusion_zones.covers(shape)
                    and not landmap.exclusion_zones.intersects(shape)
                    and all(
                        (point.x - a) ** 2 + (point.z - b) ** 2 >= 225
                        for a, b in occupied
                    )
                ):
                    positions.append(point)
                    if len(positions) == count:
                        return tuple(positions)
    raise ValueError("Not enough safe ground near this position for the selected group")


@dataclass(frozen=True)
class BaseMovementPreview:
    source_id: UUID
    available: Stock
    requested: Stock
    units: Stock
    automatically_added: Stock
    # Preview-local IDs never consume campaign IDs or reserve inventory.
    virtual_units: tuple[tuple[int, str], ...]
    manifest: TransportManifest
    destination: MovementDestination
    route: GroundRoute
    road_distance_m: float
    offroad_distance_m: float
    arrival_in_turns: int
    departure_positions: tuple[GroundPosition, ...]
    arrival_positions: tuple[GroundPosition, ...]


def preview_base_movement(
    game: Game,
    source_id: UUID,
    owner: Player,
    selected: Mapping[GroundUnitType, int],
    position: GroundPosition,
) -> BaseMovementPreview:
    base = base_source(game, source_id, owner)
    if not enabled(game.settings):
        raise ValueError("Ground Movement and Motor Pool must both be enabled")
    stock = available_stock(base)
    requested = {}
    for unit, count in selected.items():
        if not isinstance(unit, GroundUnitType) or type(count) is not int or count < 0:
            raise ValueError(
                "Select ground unit types with non-negative integer quantities"
            )
        if count > stock.get(unit, 0):
            raise ValueError(f"Not enough available {unit.display_name} at this base")
        if count:
            requested[unit] = count
    if not 1 <= sum(requested.values()) <= 1000:
        raise ValueError("Select between 1 and 1000 available units")
    virtual: dict[int, GroundUnitType] = {}
    for unit in sorted(requested, key=lambda u: u.variant_id):
        for _ in range(requested[unit]):
            virtual[len(virtual) + 1] = unit
    selected_ids = tuple(virtual)
    # Only tractors can be added automatically; do not materialize the whole stock.
    for unit in sorted(stock, key=lambda u: u.variant_id):
        if unit.ground_mobility.can_tow:
            for _ in range(
                min(stock[unit] - requested.get(unit, 0), len(selected_ids))
            ):
                virtual[len(virtual) + 1] = unit
    manifest = plan_transport(virtual, selected_ids)
    if len(manifest.unit_ids) > 1000:
        raise ValueError("The group including its tractors cannot exceed 1000 units")
    included = Counter(virtual[i] for i in manifest.unit_ids)
    added = included - Counter(requested)
    destination = movement_destination(
        game, owner, DestinationKind.POSITION, position=position
    )
    origin = GroundPosition(base.position.x, base.position.y)
    road_budget = distance_per_turn(game.settings, on_road=True)
    offroad_budget = distance_per_turn(game.settings, on_road=False)
    route = CampaignGroundRouter.for_game(game, owner).plan(
        origin, position, road_budget, offroad_budget
    )
    road = sum(s.length for s in route.segments if s.on_road)
    offroad = sum(s.length for s in route.segments if not s.on_road)
    count = len(manifest.unit_ids)
    return BaseMovementPreview(
        source_id,
        stock_tuple(stock),
        stock_tuple(requested),
        stock_tuple(included),
        stock_tuple(added),
        tuple((i, virtual[i].variant_id) for i in manifest.unit_ids),
        manifest,
        destination,
        route,
        road,
        offroad,
        max(1, math.ceil(road / road_budget + offroad / offroad_budget - 1e-9)),
        formation(game, origin, count),
        formation(game, position, count),
    )


def dispatch_base_movement(
    game: Game,
    source_id: UUID,
    owner: Player,
    selected: Mapping[GroundUnitType, int],
    position: GroundPosition,
    events: GameUpdateEvents,
) -> ArmorTransit:
    preview = preview_base_movement(game, source_id, owner, selected, position)
    base = base_source(game, source_id, owner)
    group_id = game.next_group_id()
    name = f"Reserve Armor Group {group_id}"
    tgo = VehicleGroupGroundObject(
        name, PresetLocation(name, base.position), base, None
    )
    tgo.reserve_from_base = True
    identities = {i: game.next_unit_id() for i in preview.manifest.unit_ids}
    units = [
        TheaterUnit(
            identities[i],
            GroundUnitType.named(variant).display_name,
            GroundUnitType.named(variant).dcs_unit_type,
            PointWithHeading.from_point(
                Point(p.x, p.z, game.theater.terrain), Heading.from_degrees(0)
            ),
            tgo,
            ground_unit_variant=variant,
        )
        for (i, variant), p in zip(preview.virtual_units, preview.departure_positions)
    ]
    manifest = TransportManifest(
        tuple(identities[i] for i in preview.manifest.unit_ids),
        tuple((identities[a], identities[b]) for a, b in preview.manifest.towing),
    )
    towing = dict(manifest.towing)
    for unit in units:
        unit.transported_by_id = towing.get(unit.id)
    tgo.groups = [TheaterGroup.from_template(group_id, name, units, tgo)]
    tgo.in_transit = True
    order = GroundMovementOrder(
        uuid4(),
        source_id,
        MovementSource.BASE,
        owner,
        preview.route.segments[0].start,
        preview.destination,
        manifest,
        game.turn,
    )
    transit = ArmorTransit(
        order.id,
        tgo.id,
        GroundJourney(preview.route, last_advanced_turn=game.turn),
        arrival_positions=dict(zip(manifest.unit_ids, preview.arrival_positions)),
    )
    # All rejection paths precede the one stock debit and group registration.
    base.base.commit_losses(
        {GroundUnitType.named(variant): count for variant, count in preview.units}
    )
    base.connected_objectives.append(tgo)
    game.db.tgos.add(tgo.id, tgo)
    game.ground_movements.orders[order.id] = order
    game.ground_movements.transits[order.id] = transit
    events.update_tgo(tgo).update_control_point(base).update_motorpools_at(base)
    return transit
