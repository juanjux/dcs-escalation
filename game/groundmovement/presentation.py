"""Resolve movement placeholders without changing campaign unit ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.theater.theatergroundobject import VehicleGroupGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject


def empty_movement_group(tgo: TheaterGroundObject) -> bool:
    """An evacuated source or delivered detachment is not a destroyed formation."""
    if not isinstance(tgo, VehicleGroupGroundObject) or any(tgo.units):
        return False
    game = getattr(getattr(tgo.control_point, "coalition", None), "game", None)
    movements = getattr(game, "ground_movements", None)
    return movements is not None and (
        any(order.source_id == tgo.id for order in movements.orders.values())
        or any(t.detachment_id == tgo.id for t in movements.transits.values())
    )


def departed_detachments(
    game: Game, source: TheaterGroundObject
) -> list[VehicleGroupGroundObject]:
    """Find the actual formations behind an empty source, including later moves."""
    if not isinstance(source, VehicleGroupGroundObject) or any(source.units):
        return []
    movements = getattr(game, "ground_movements", None)
    if movements is None:
        return []
    pending = [source.id]
    visited = set(pending)
    result = []
    while pending:
        source_id = pending.pop()
        for transit in movements.transits.values():
            order = movements.orders[transit.order_id]
            if order.source_id != source_id or transit.detachment_id in visited:
                continue
            visited.add(transit.detachment_id)
            detachment = game.db.tgos.get(transit.detachment_id)
            if not isinstance(detachment, VehicleGroupGroundObject):
                continue
            if any(detachment.units):
                result.append(detachment)
            else:
                pending.append(detachment.id)
    return sorted(result, key=lambda tgo: tgo.name)
