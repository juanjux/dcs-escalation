"""Identity-preserving armor detachments and turn-boundary travel."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Iterable, TYPE_CHECKING
from uuid import UUID

from dcs import Point

from game.groundmovement.journey import GroundJourney, GroundSegment
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
    MovementSource,
)
from game.groundmovement.planning import (
    armor_source,
    movement_destination,
    preview_armor_movement,
    _unit_types,
)
from game.groundmovement.routing import CampaignGroundRouter
from game.groundmovement.settings import distance_per_turn, enabled
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import VehicleGroupGroundObject
from game.theater.theatergroup import TheaterGroup

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater.controlpoint import ControlPoint


@dataclass
class ArmorTransit:
    order_id: UUID
    detachment_id: UUID
    journey: GroundJourney
    finished: bool = False
    pause_reason: str | None = None
    final_unit_count: int | None = None
    arrival_positions: dict[int, GroundPosition] | None = None


def active_transit(game: Game, tgo_id: UUID) -> ArmorTransit | None:
    movements = getattr(game, "ground_movements", None)
    if movements is None:
        return None
    return next(
        (
            t
            for t in movements.transits.values()
            if not t.finished and t.detachment_id == tgo_id
        ),
        None,
    )


def dispatch_armor(
    game: Game,
    source_id: UUID,
    owner: Player,
    selected: Iterable[int],
    destination: MovementDestination,
    events: GameUpdateEvents,
) -> ArmorTransit:
    """Revalidate the request and move existing objects, never inventory copies."""
    if active_transit(game, source_id) is not None:
        raise ValueError("Stop this detachment before issuing another movement")
    selected = tuple(selected)
    preview = preview_armor_movement(game, source_id, owner, selected, destination)
    source = armor_source(game, source_id, owner)
    identities = set(preview.manifest.unit_ids)
    units = [u for u in source.units if u.id in identities]
    if len(units) != len(identities):
        raise ValueError("The source inventory changed; request a new preview")
    group_id = game.next_group_id()
    detachment = VehicleGroupGroundObject(
        f"{source.name} detachment {group_id}",
        PresetLocation(source.original_name, source.position, source.heading),
        source.control_point,
        source.task,
    )
    detachment.groups = [
        TheaterGroup.from_template(group_id, detachment.name, units, detachment)
    ]
    detachment.in_transit = True
    detachment.reserve_from_base = getattr(source, "reserve_from_base", False)
    order = game.ground_movements.plan(
        game.settings,
        source_id=source_id,
        source_kind=MovementSource.ARMOR,
        owner=owner,
        origin=GroundPosition(source.position.x, source.position.y),
        destination=destination,
        units=_unit_types(source),
        selected=selected,
        turn=game.turn,
    )
    transit = ArmorTransit(
        order.id,
        detachment.id,
        GroundJourney(preview.route, last_advanced_turn=game.turn),
    )
    # All validation has completed. From here, each unit has exactly one parent.
    for group in source.groups:
        group.units[:] = [u for u in group.units if u.id not in identities]
    for unit in units:
        unit.ground_object = detachment
        unit.transported_by_id = dict(preview.manifest.towing).get(unit.id)
    source.control_point.connected_objectives.append(detachment)
    game.db.tgos.add(detachment.id, detachment)
    game.ground_movements.transits[order.id] = transit
    source.invalidate_threat_poly()
    events.update_tgo(source).update_tgo(detachment)
    return transit


def _relocate(tgo: VehicleGroupGroundObject, point: GroundPosition) -> None:
    dx, dz = point.x - tgo.position.x, point.z - tgo.position.y
    tgo.position = Point(point.x, point.z, tgo.position._terrain)
    for group in tgo.groups:
        group.position.x += dx
        group.position.y += dz
        for unit in group.units:
            unit.position.x += dx
            unit.position.y += dz
    tgo.invalidate_threat_poly()


def _finish(game: Game, transit: ArmorTransit) -> None:
    if transit.final_unit_count is None:
        transit.final_unit_count = sum(
            unit.alive for unit in game.db.tgos.get(transit.detachment_id).units
        )
    transit.finished = True
    transit.pause_reason = None
    order = game.ground_movements.orders[transit.order_id]
    game.ground_movements.orders[order.id] = replace(order, completed=True)
    _unload(game, transit)


def _unload(game: Game, transit: ArmorTransit) -> None:
    tgo = game.db.tgos.get(transit.detachment_id)
    tgo.in_transit = False
    for unit in tgo.units:
        unit.transported_by_id = None
        positions = getattr(transit, "arrival_positions", None)
        if transit.journey.completed and positions and unit.id in positions:
            unit.position.x = positions[unit.id].x
            unit.position.y = positions[unit.id].z
    tgo.invalidate_threat_poly()


def stop_armor(
    game: Game, order_id: UUID, owner: Player, events: GameUpdateEvents
) -> None:
    """Unload and keep the surviving detachment where it is, without a refund."""
    order = game.ground_movements.orders[order_id]
    if order.owner is not owner:
        raise PermissionError("The movement belongs to another side")
    transit = game.ground_movements.transits[order_id]
    if transit.finished:
        return
    _cargo_losses(game, transit, events)
    transit.final_unit_count = sum(
        unit.alive for unit in game.db.tgos.get(transit.detachment_id).units
    )
    transit.finished = True
    game.ground_movements.cancel(order_id)
    _unload(game, transit)
    events.update_tgo(game.db.tgos.get(transit.detachment_id))


def _cargo_losses(game: Game, transit: ArmorTransit, events: GameUpdateEvents) -> None:
    units = {u.id: u for u in game.db.tgos.get(transit.detachment_id).units}
    for unit in units.values():
        if unit.alive and unit.transported_by_id is not None:
            tractor = units.get(unit.transported_by_id)
            if tractor is None or not tractor.alive:
                unit.kill(events)


def validate_transit(game: Game, transit: ArmorTransit) -> MovementDestination:
    order = game.ground_movements.orders[transit.order_id]
    destination = movement_destination(
        game,
        order.owner,
        order.destination.kind,
        position=(
            order.destination.position
            if order.destination.kind is DestinationKind.POSITION
            else None
        ),
        base_id=order.destination.target_id,
        opposing_base_id=order.destination.opposing_base_id,
    )
    if destination != order.destination:
        raise ValueError("The destination changed")
    router = CampaignGroundRouter.for_game(game, order.owner)
    remaining = list(transit.journey.route.segments[transit.journey.segment_index :])
    if remaining:
        remaining[0] = GroundSegment(
            transit.journey.position, remaining[0].end, remaining[0].on_road
        )
    if not all(
        router.allowed(s)
        and (
            s.on_road
            or router.offroad_permission is None
            or router.offroad_permission(s)
        )
        for s in remaining
    ):
        raise ValueError("The route is no longer available")
    return destination


def rehome_before_capture(
    game: Game, base: ControlPoint, events: GameUpdateEvents
) -> None:
    """Detach departing units before capture depopulates uncapturable TGOs."""
    movements = getattr(game, "ground_movements", None)
    if movements is None:
        return
    for transit in movements.transits.values():
        tgo = game.db.tgos.get(transit.detachment_id)
        if tgo.control_point is not base or not any(unit.alive for unit in tgo.units):
            continue
        owner = game.ground_movements.orders[transit.order_id].owner
        candidates = [
            cp
            for cp in game.theater.controlpoints
            if cp is not base and cp.is_friendly(owner) and not cp.is_fleet
        ]
        if candidates:
            closest = min(
                candidates, key=lambda cp: cp.position.distance_to_point(tgo.position)
            )
            base.connected_objectives.remove(tgo)
            closest.connected_objectives.append(tgo)
            tgo.control_point = closest
            events.update_tgo(tgo)


def advance_armor(game: Game, events: GameUpdateEvents) -> None:
    """Commit one distance budget after mission casualties, once per turn."""
    movements = getattr(game, "ground_movements", None)
    if movements is None:
        return
    for transit in movements.transits.values():
        if transit.finished:
            continue
        tgo = game.db.tgos.get(transit.detachment_id)
        assert isinstance(tgo, VehicleGroupGroundObject)
        _cargo_losses(game, transit, events)
        if not any(u.alive for u in tgo.units):
            _finish(game, transit)
            continue
        if not enabled(game.settings):
            transit.pause_reason = "Ground Movement is disabled"
            continue
        try:
            destination = validate_transit(game, transit)
        except (ValueError, PermissionError) as exc:
            transit.pause_reason = str(exc)
            continue
        transit.pause_reason = None
        transit.journey.advance(
            game.turn,
            distance_per_turn(game.settings, on_road=True),
            distance_per_turn(game.settings, on_road=False),
        )
        _relocate(tgo, transit.journey.position)
        events.update_tgo(tgo)
        if not transit.journey.completed:
            continue
        if destination.kind is not DestinationKind.POSITION:
            base = next(
                cp
                for cp in game.theater.controlpoints
                if cp.id == destination.target_id
            )
            survivors: Counter[GroundUnitType] = Counter()
            for unit in tgo.units:
                if unit.alive:
                    unit_type = unit.unit_type
                    assert isinstance(unit_type, GroundUnitType)
                    survivors[unit_type] += 1
            base.base.commission_units(dict(survivors))
            transit.final_unit_count = sum(survivors.values())
            # Remove delivered units, so they cannot be spawned or repaired twice.
            for group in tgo.groups:
                group.units.clear()
            events.update_control_point(base).update_motorpools_at(base)
        _finish(game, transit)
        events.update_tgo(tgo)
