"""Local off-road exits for existing groups inside placement exclusions."""

from __future__ import annotations

import math

from shapely.geometry import LineString, Point

from game.groundmovement.journey import GroundSegment
from game.groundmovement.orders import GroundPosition
from game.theater.landmap import Landmap

# Match the local recovery radius used for abstract base stock handoffs.
MAX_ORIGIN_EXIT_METERS = 600.0
_CLEARANCE = 0.1


def allowed_origin_exit(landmap: Landmap, segment: GroundSegment) -> bool:
    """Allow only a short, contiguous exit from the starting exclusion."""
    if segment.on_road or not 0 < segment.length <= MAX_ORIGIN_EXIT_METERS:
        return False
    start = Point(segment.start.x, segment.start.z)
    end = Point(segment.end.x, segment.end.z)
    line = LineString([start, end])
    if (
        not landmap.exclusion_zones.covers(start)
        or landmap.exclusion_zones.intersects(end)
        or not landmap.inclusion_zones.covers(line)
        or landmap.sea_zones.intersects(line)
    ):
        return False
    blocked = line.intersection(landmap.exclusion_zones)
    # Separate intervals would leave and re-enter an exclusion. The endpoint
    # must be just outside the boundary, not an arbitrary shortcut beyond it.
    return bool(
        blocked.geom_type in ("Point", "LineString")
        and blocked.covers(start)
        and end.distance(blocked) <= _CLEARANCE * 1.01
    )


def origin_exits(landmap: Landmap, origin: GroundPosition) -> list[GroundSegment]:
    """Find nearby exit points without moving the group's actual position."""
    start = Point(origin.x, origin.z)
    candidates: dict[GroundPosition, GroundSegment] = {}
    for polygon in landmap.exclusion_zones.geoms:
        if not polygon.covers(start):
            continue
        for ring in (polygon.exterior, *polygon.interiors):
            coords = list(ring.coords)
            for a, b in zip(coords, coords[1:]):
                edge = LineString([a, b])
                boundary = edge.interpolate(edge.project(start))
                dx, dz = boundary.x - origin.x, boundary.y - origin.z
                distance = math.hypot(dx, dz)
                if distance + _CLEARANCE > MAX_ORIGIN_EXIT_METERS:
                    continue
                if distance > 0:
                    ends = [
                        GroundPosition(
                            boundary.x + dx / distance * _CLEARANCE,
                            boundary.y + dz / distance * _CLEARANCE,
                        )
                    ]
                else:
                    # An origin on an edge or vertex still needs to step off
                    # the forbidden boundary before normal planning can start.
                    ends = [
                        GroundPosition(
                            origin.x + math.cos(angle) * _CLEARANCE,
                            origin.z + math.sin(angle) * _CLEARANCE,
                        )
                        for angle in (math.radians(h) for h in range(0, 360, 15))
                    ]
                for end in ends:
                    segment = GroundSegment(origin, end, False)
                    if allowed_origin_exit(landmap, segment):
                        candidates[end] = segment
    return sorted(candidates.values(), key=lambda s: (s.length, s.end.x, s.end.z))
