"""Buy towing trucks without replacing a mobile SAM battery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from dcs import Point

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.dispatch import active_transit
from game.groundmovement.mobility import MobilityMode, movement_mobility
from game.groundmovement.planning import armor_source
from game.point_with_heading import PointWithHeading
from game.theater.player import Player
from game.theater.theatergroundobject import SamGroundObject
from game.theater.theatergroup import TheaterGroup, TheaterUnit

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents


@dataclass(frozen=True)
class TruckOffer:
    unit_type: str
    name: str
    price: float


@dataclass(frozen=True)
class SamTruckOptions:
    source_id: UUID
    towed_units: int
    truck_limit: int
    owned_trucks: int
    remaining: int
    offers: tuple[TruckOffer, ...]
    reason: str | None = None


def sam_truck_options(game: Game, source_id: UUID, owner: Player) -> SamTruckOptions:
    source = armor_source(game, source_id, owner)
    towed = owned = 0
    mobile = isinstance(source, SamGroundObject)
    # Include destroyed pieces and trucks: repairing them must not increase the
    # battery beyond its allowance. Existing trucks can be repaired, not rebought.
    for unit in source.units:
        kind = unit.unit_type if unit.is_vehicle else None
        if isinstance(kind, GroundUnitType):
            mobility = movement_mobility(kind)
            towed += mobility.mode is MobilityMode.TOWED
            owned += mobility.can_tow
            if unit.alive and mobility.mode not in (
                MobilityMode.TOWED,
                MobilityMode.SELF_PROPELLED,
            ):
                mobile = False
        elif unit.alive:
            mobile = False
    limit = towed + 2 if mobile and towed else 0
    trucks = (
        sorted(
            (
                u
                for u in source.coalition.faction.accessible_units
                if isinstance(u, GroundUnitType) and movement_mobility(u).can_tow
            ),
            key=lambda u: u.variant_id,
        )
        if limit
        else []
    )
    reason = None
    if not limit:
        reason = "Only mobile SAM batteries with towed units can buy towing trucks"
    elif source.in_transit or active_transit(game, source.id) is not None:
        reason = "Stop the battery before buying towing trucks"
    elif not any(u.alive for u in source.units):
        reason = "Repair the battery before buying towing trucks"
    elif not trucks:
        reason = "This faction has no towing trucks available"
    elif owned >= limit:
        reason = "The battery has reached its towing truck limit"
    return SamTruckOptions(
        source.id,
        towed,
        limit,
        owned,
        max(0, limit - owned),
        tuple(TruckOffer(u.variant_id, u.display_name, u.price) for u in trucks),
        reason,
    )


def buy_sam_trucks(
    game: Game,
    source_id: UUID,
    owner: Player,
    unit_name: str,
    quantity: int,
    events: GameUpdateEvents,
) -> tuple[int, ...]:
    if type(quantity) is not int or quantity < 1:
        raise ValueError("Truck quantity must be a positive integer")
    options = sam_truck_options(game, source_id, owner)
    if options.reason:
        raise ValueError(options.reason)
    if quantity > options.remaining:
        raise ValueError(
            f"The battery can own at most {options.truck_limit} towing trucks; "
            f"only {options.remaining} more can be bought"
        )
    offer = next((o for o in options.offers if o.unit_type == unit_name), None)
    if offer is None:
        raise ValueError("Select an available faction towing truck")
    source = armor_source(game, source_id, owner)
    coalition = source.coalition
    cost = offer.price * quantity
    if cost > coalition.budget:
        raise ValueError("Not enough money to buy these towing trucks")
    kind = GroundUnitType.named(offer.unit_type)
    existing = list(source.units)
    positions: list[Point] = []
    for i in range(quantity):
        # Search a sparse ring around the site; do not overlap existing pieces.
        for slot in range(360):
            distance = 60 + 20 * (slot // 18)
            point = source.position.point_from_heading(slot % 18 * 20, distance)
            if all(point.distance_to_point(u.position) >= 15 for u in existing):
                if all(point.distance_to_point(p) >= 15 for p in positions):
                    break
        else:
            raise ValueError("No space remains for towing trucks beside this battery")
        positions.append(point)
    group = TheaterGroup(
        game.next_group_id(),
        f"{source.name} towing trucks",
        PointWithHeading.from_point(source.position, source.heading),
        [],
        source,
    )
    for point in positions:
        unit = TheaterUnit(
            game.next_unit_id(),
            kind.variant_id,
            kind.dcs_unit_type,
            PointWithHeading.from_point(point, source.heading),
            source,
            ground_unit_variant=kind.variant_id,
        )
        group.units.append(unit)
        existing.append(unit)
    source.groups.append(group)
    coalition.adjust_budget(-cost)
    game.theater.iads_network.invalidate_state_map()
    events.update_tgo(source)
    return tuple(u.id for u in group.units)
