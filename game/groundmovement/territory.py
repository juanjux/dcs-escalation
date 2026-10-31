"""Ground-position control from land bases and authored campaign road sectors."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import LineString, Point
from shapely.ops import substring

from game.groundmovement.orders import GroundPosition
from game.groundmovement.journey import GroundSegment
from game.theater.frontline import FrontLine
from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game


def _control_distances(game: Game, position: GroundPosition) -> dict[Player, float]:
    """Use the nearest land base or road sector; ties are not controlled territory.

    Roads between opposing bases are split at the current front, not halfway
    between the bases. Fleets cannot claim land. This is a ground-movement rule,
    not a change to aircraft recovery or a global campaign territory model.
    """
    point = Point(position.x, position.z)
    distances = {player: math.inf for player in Player}
    bases = [cp for cp in game.theater.controlpoints if not cp.is_fleet]
    base_ids = {cp.id for cp in bases}
    seen = set()
    for base in bases:
        distances[base.captured] = min(
            distances[base.captured],
            point.distance(Point(base.position.x, base.position.y)),
        )
        for other, points in base.convoy_routes.items():
            pair = frozenset((base.id, other.id))
            if other.id not in base_ids or pair in seen or base is other:
                continue
            seen.add(pair)
            if base.captured is other.captured:
                if len(points) < 2:
                    continue
                road = LineString([(p.x, p.y) for p in points])
                distances[base.captured] = min(
                    distances[base.captured], point.distance(road)
                )
                continue
            front = base.front_lines.get(other)
            if not isinstance(front, FrontLine):
                continue
            road = LineString([(p.x, p.y) for p in front.points])
            progress = road.project(Point(front.position.x, front.position.y))
            for player, start, end in (
                (Player.BLUE, 0, progress),
                (Player.RED, progress, road.length),
            ):
                sector = substring(road, start, end)
                distances[player] = min(distances[player], point.distance(sector))
    return distances


def position_owner(game: Game, position: GroundPosition) -> Player | None:
    distances = _control_distances(game, position)
    nearest = min(distances.values())
    owners = [
        player
        for player, distance in distances.items()
        if math.isfinite(distance) and abs(distance - nearest) <= 1e-6
    ]
    return owners[0] if len(owners) == 1 else None


def segment_is_friendly(game: Game, owner: Player, segment: GroundSegment) -> bool:
    """Conservatively certify the entire detour, not just its destination.

    Distances to control sources are 1-Lipschitz. A midpoint ownership margin
    larger than the leg length therefore certifies both halves. Subdivide near
    borders; ambiguous sub-millimetre strips remain unavailable.
    """
    pending = [segment]
    while pending:
        leg = pending.pop()
        middle = GroundPosition(
            (leg.start.x + leg.end.x) / 2, (leg.start.z + leg.end.z) / 2
        )
        distances = _control_distances(game, middle)
        friendly = distances[owner]
        hostile = min(d for player, d in distances.items() if player is not owner)
        if not math.isfinite(friendly) or hostile - friendly <= 1e-6:
            return False
        if hostile - friendly > leg.length:
            continue
        if leg.length <= 0.001:
            return False
        pending.extend(
            (
                GroundSegment(leg.start, middle, False),
                GroundSegment(middle, leg.end, False),
            )
        )
    return True


def require_friendly_position(
    game: Game, owner: Player, position: GroundPosition
) -> None:
    if (
        owner not in (Player.BLUE, Player.RED)
        or position_owner(game, position) is not owner
    ):
        raise PermissionError("A GPS destination must be in friendly territory")
