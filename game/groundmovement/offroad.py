"""Terrain-validated off-road detours used when campaign roads cannot connect."""

from __future__ import annotations

import heapq
import itertools
import math
from typing import Callable

from shapely import constrained_delaunay_triangles
from shapely.geometry import MultiPolygon, Point, Polygon, box

from game.groundmovement.journey import GroundRoute, GroundSegment
from game.groundmovement.orders import GroundPosition
from game.theater.landmap import Landmap


def offroad_route(
    landmap: Landmap,
    origin: GroundPosition,
    destination: GroundPosition,
    allowed: Callable[[GroundSegment], bool],
) -> GroundRoute | None:
    """Search connected land triangles, then remove unnecessary waypoints.

    Exclusion boundaries are forbidden, so leave a small clearance instead of
    routing exactly along their vertices. Every returned leg is checked against
    the original terrain and the caller's ownership restrictions.
    """
    direct = GroundSegment(origin, destination, False)
    if allowed(direct):
        return GroundRoute((direct,))
    start, end = Point(origin.x, origin.z), Point(destination.x, destination.z)
    # Start locally so large theater masks do not create a theater-wide mesh
    # for a short movement. Widen only when the local corridor cannot connect.
    margin = max(1000.0, direct.length / 2)
    while True:
        bounds = (
            min(origin.x, destination.x) - margin,
            min(origin.z, destination.z) - margin,
            max(origin.x, destination.x) + margin,
            max(origin.z, destination.z) + margin,
        )
        window = box(*bounds)
        blocked = landmap.exclusion_zones.intersection(window).union(
            landmap.sea_zones.intersection(window)
        )
        # Preserve valid endpoints arbitrarily close to an exclusion boundary.
        clearance = min(0.1, start.distance(blocked) / 2, end.distance(blocked) / 2)
        free = landmap.inclusion_zones.intersection(window).difference(
            blocked.buffer(clearance)
        )
        polygons = [free] if isinstance(free, Polygon) else list(free.geoms)
        area = next((p for p in polygons if p.covers(start) and p.covers(end)), None)
        if area is not None:
            route = _triangle_route(area, origin, destination, allowed)
            if route is not None:
                return route
        a, b, c, d = landmap.inclusion_zones.bounds
        if bounds[0] <= a and bounds[1] <= b and bounds[2] >= c and bounds[3] >= d:
            return None
        margin *= 2


def _triangle_route(
    area: Polygon | MultiPolygon,
    origin: GroundPosition,
    destination: GroundPosition,
    allowed: Callable[[GroundSegment], bool],
) -> GroundRoute | None:
    start, end = Point(origin.x, origin.z), Point(destination.x, destination.z)
    triangles = list(constrained_delaunay_triangles(area).geoms)
    centers = [GroundPosition(t.centroid.x, t.centroid.y) for t in triangles]
    graph: dict[GroundPosition, list[GroundPosition]] = {}
    portals: dict[GroundPosition, tuple[GroundPosition, GroundPosition]] = {}

    def connect(a: GroundPosition, b: GroundPosition) -> None:
        if a != b:
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)

    # Midpoints of shared edges are portals. Center-to-portal segments stay
    # inside their convex triangle, unlike arbitrary links between centers.
    for triangle, center in zip(triangles, centers):
        coords = list(triangle.exterior.coords)
        for a, b in zip(coords, coords[1:]):
            portal = GroundPosition((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            portals[portal] = (GroundPosition(*a), GroundPosition(*b))
            connect(center, portal)
            if triangle.covers(start):
                connect(origin, portal)
            if triangle.covers(end):
                connect(destination, portal)
        if triangle.covers(start):
            connect(origin, center)
        if triangle.covers(end):
            connect(destination, center)

    serial = itertools.count()
    queue = [(0.0, next(serial), origin)]
    costs = {origin: 0.0}
    previous: dict[GroundPosition, GroundPosition] = {}
    checked: dict[frozenset[GroundPosition], bool] = {}
    visited: set[GroundPosition] = set()
    while queue:
        _, _, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)
        if current == destination:
            break
        for neighbor in graph.get(current, []):
            key = frozenset((current, neighbor))
            if key not in checked:
                checked[key] = allowed(GroundSegment(current, neighbor, False))
            if not checked[key]:
                continue
            distance = math.hypot(neighbor.x - current.x, neighbor.z - current.z)
            candidate = costs[current] + distance
            if candidate < costs.get(neighbor, math.inf):
                costs[neighbor] = candidate
                previous[neighbor] = current
                estimate = candidate + math.hypot(
                    destination.x - neighbor.x, destination.z - neighbor.z
                )
                heapq.heappush(queue, (estimate, next(serial), neighbor))
    if destination not in previous:
        return None
    points = [destination]
    while points[-1] != origin:
        points.append(previous[points[-1]])
    points.reverse()
    pulled = _pull_string(points, portals)
    if all(allowed(GroundSegment(a, b, False)) for a, b in zip(pulled, pulled[1:])):
        points = pulled
    segments = []
    index = 0
    while index < len(points) - 1:
        following = len(points) - 1
        while following > index + 1 and not allowed(
            GroundSegment(points[index], points[following], False)
        ):
            following -= 1
        segments.append(GroundSegment(points[index], points[following], False))
        index = following
    return GroundRoute(tuple(segments))


def _pull_string(
    points: list[GroundPosition],
    edges: dict[GroundPosition, tuple[GroundPosition, GroundPosition]],
) -> list[GroundPosition]:
    """Pull a string through the oriented triangle portals in linear time."""

    def area(a: GroundPosition, b: GroundPosition, c: GroundPosition) -> float:
        return (c.x - a.x) * (b.z - a.z) - (b.x - a.x) * (c.z - a.z)

    portals = [(points[0], points[0])]
    for index, point in enumerate(points[1:-1], 1):
        if point not in edges:
            continue
        a, b = edges[point]
        if area(points[index - 1], points[index + 1], a) < 0:
            portals.append((a, b))
        else:
            portals.append((b, a))
    portals.append((points[-1], points[-1]))
    apex = left = right = points[0]
    apex_index = left_index = right_index = 0
    result = [apex]
    index = 1
    while index < len(portals):
        new_left, new_right = portals[index]
        if area(apex, right, new_right) <= 0:
            if apex == right or area(apex, left, new_right) > 0:
                right, right_index = new_right, index
            else:
                result.append(left)
                apex, apex_index = left, left_index
                left = right = apex
                left_index = right_index = apex_index
                index = apex_index + 1
                continue
        if area(apex, left, new_left) >= 0:
            if apex == left or area(apex, right, new_left) < 0:
                left, left_index = new_left, index
            else:
                result.append(right)
                apex, apex_index = right, right_index
                left = right = apex
                left_index = right_index = apex_index
                index = apex_index + 1
                continue
        index += 1
    if result[-1] != points[-1]:
        result.append(points[-1])
    return [p for index, p in enumerate(result) if index == 0 or p != result[index - 1]]
