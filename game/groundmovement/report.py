"""Read-only progress reports for dispatched armor groups."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from dcs import Point

from game.coordinates import format_for
from game.groundmovement.dispatch import validate_transit
from game.groundmovement.orders import MovementDestination, GroundPosition
from game.groundmovement.settings import distance_per_turn, enabled
from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game
    from game.groundmovement.planning import ArmorMovementPreview
    from game.groundmovement.base import BaseMovementPreview


def preview_token(
    game: Game, preview: ArmorMovementPreview | BaseMovementPreview
) -> str:
    """Reject confirmation of a preview from an older turn or inventory state."""
    return hashlib.sha256(repr((game.turn, preview)).encode()).hexdigest()


def destination_label(game: Game, destination: MovementDestination) -> str:
    if destination.target_id is None:
        return format_for(
            game.settings,
            Point(destination.position.x, destination.position.z, game.theater.terrain),
        )
    names = {base.id: base.name for base in game.theater.controlpoints}
    name = names.get(destination.target_id, "Unavailable base")
    if destination.opposing_base_id is not None:
        name += " / " + names.get(destination.opposing_base_id, "Unavailable front")
    return name


@dataclass(frozen=True)
class ArmorMovementReport:
    order_id: UUID
    source_id: UUID
    detachment_id: UUID
    status: str
    pause_reason: str | None
    destination: MovementDestination
    position: GroundPosition
    total_distance_m: float
    remaining_distance_m: float
    progress: float
    remaining_turns: int | None
    surviving_units: int | None
    original_units: int
    towing: tuple[tuple[int, int], ...]


def movement_reports(
    game: Game, tgo_id: UUID, owner: Player
) -> tuple[ArmorMovementReport, ...]:
    """Include departures from this source and journeys of this detachment."""
    store = getattr(game, "ground_movements", None)
    if store is None:
        return ()
    reports = []
    for transit in store.transits.values():
        order = store.orders[transit.order_id]
        if order.owner is not owner or tgo_id not in (
            order.source_id,
            transit.detachment_id,
        ):
            continue
        tgo = game.db.tgos.get(transit.detachment_id)
        units = {unit.id: unit for unit in tgo.units}
        alive = [
            unit
            for unit in units.values()
            if unit.alive
            and (
                unit.transported_by_id is None
                or (
                    unit.transported_by_id in units
                    and units[unit.transported_by_id].alive
                )
            )
        ]
        # Keep completed reports stable if the stationary group is dispatched again.
        final_count = getattr(transit, "final_unit_count", None)
        count: int | None = (
            final_count if transit.finished and final_count is not None else len(alive)
        )
        # Older base deliveries removed their units without recording the count.
        if (
            transit.finished
            and transit.journey.completed
            and not alive
            and final_count is None
        ):
            count = None
        lost = count == 0 and not transit.journey.completed
        reason = None
        if order.cancelled:
            status = "stopped"
        elif lost:
            status = "lost"
        elif transit.finished:
            status = "arrived"
        else:
            if not enabled(game.settings):
                reason = "Ground Movement and Motor Pool must both be enabled"
            else:
                try:
                    validate_transit(game, transit)
                except (ValueError, PermissionError) as exc:
                    reason = str(exc)
            status = "paused" if reason else "moving"
        journey = transit.journey
        remaining_turns = None
        if status == "moving":
            try:
                turns = sum(
                    (
                        segment.length
                        - (
                            journey.segment_progress
                            if index == journey.segment_index
                            else 0
                        )
                    )
                    / distance_per_turn(game.settings, on_road=segment.on_road)
                    for index, segment in enumerate(journey.route.segments)
                    if index >= journey.segment_index
                )
                remaining_turns = math.ceil(max(0, turns - 1e-10))
            except ValueError as exc:
                status, reason = "paused", str(exc)
        reports.append(
            ArmorMovementReport(
                order.id,
                order.source_id,
                transit.detachment_id,
                status,
                reason,
                order.destination,
                journey.position,
                journey.route.length,
                journey.remaining_distance,
                journey.travelled_distance / journey.route.length,
                remaining_turns,
                count,
                len(order.manifest.unit_ids),
                tuple(
                    (unit.id, unit.transported_by_id)
                    for unit in alive
                    if unit.transported_by_id is not None and not transit.finished
                ),
            )
        )
    return tuple(reports)
