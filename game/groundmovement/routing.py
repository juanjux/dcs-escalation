"""Validated access to the road corridors authored in a campaign."""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass
from typing import Iterable, TYPE_CHECKING

from shapely import STRtree
from shapely.geometry import LineString, Point

from game.groundmovement.journey import GroundRoute, GroundSegment
from game.groundmovement.orders import GroundPosition

if TYPE_CHECKING:
    from game import Game
    from game.theater.landmap import Landmap
    from game.theater.player import Player


class GroundRouteError(ValueError):
    pass


@dataclass(frozen=True)
class RoadAccess:
    distance: float
    edge: int
    position: GroundPosition
    component: int


class _ConvoyRoadCoverage:
    """Recognize road centerlines without dissolving sub-millimetre polygons."""

    _TOLERANCE = 1e-6

    def __init__(self, segments: Iterable[GroundSegment]) -> None:
        self.lines = [
            LineString([(s.start.x, s.start.z), (s.end.x, s.end.z)]) for s in segments
        ]
        self.index = STRtree(self.lines)

    def covers(self, geometry: Point | LineString) -> bool:
        nearby = self.index.query(
            geometry, predicate="dwithin", distance=self._TOLERANCE
        )
        if isinstance(geometry, Point):
            return bool(len(nearby))
        start, end = geometry.coords[0], geometry.coords[-1]
        length = geometry.length
        if length == 0:
            return self.covers(Point(start))
        ux, uz = (end[0] - start[0]) / length, (end[1] - start[1]) / length
        intervals = []
        for index in nearby:
            road = self.lines[index]
            # Testing endpoints on the same straight segment also handles very
            # short interpolated remnants, whose own heading can lose precision.
            if (
                road.distance(Point(start)) <= self._TOLERANCE
                and road.distance(Point(end)) <= self._TOLERANCE
            ):
                return True
            a, b = road.coords
            # Only collinear authored segments can cover this straight leg.
            # Merely reaching a road at both ends must not authorize a shortcut.
            if any(
                abs((p[0] - start[0]) * uz - (p[1] - start[1]) * ux) > self._TOLERANCE
                for p in (a, b)
            ):
                continue
            lo, hi = sorted(
                (p[0] - start[0]) * ux + (p[1] - start[1]) * uz for p in (a, b)
            )
            intervals.append((max(0.0, lo), min(length, hi)))
        covered = 0.0
        for lo, hi in sorted(intervals):
            if lo > covered + self._TOLERANCE:
                return False
            covered = max(covered, hi)
            if covered >= length - self._TOLERANCE:
                return True
        return False


class CampaignGroundRouter:
    """Use known roads, with individually validated off-road access segments.

    Crossings of road polylines do not imply a junction: they might be overpasses.
    Roads connect at shared points or via a validated access link at their base.
    Authored convoy corridors use the same road permissions as supply convoys;
    terrain masks still validate off-road access and unverified road segments.
    """

    def __init__(
        self,
        landmap: Landmap | None,
        roads: Iterable[GroundRoute],
        base_access: Iterable[GroundSegment] = (),
        *,
        convoy_corridors: bool = False,
    ) -> None:
        if landmap is None:
            raise GroundRouteError("Ground movement needs land and exclusion-zone data")
        self.landmap = landmap
        self.roads = [segment for road in roads for segment in road.segments]
        if any(not segment.on_road for segment in self.roads):
            raise GroundRouteError(
                "A campaign road corridor must contain road segments"
            )
        # The land map is a coarse placement mask, not DCS's road network.
        # Match the supply convoy policy only on these authored polylines. The
        # one-micrometre tolerance accommodates projected/interpolated positions;
        # it is not an off-road corridor or permission to infer new bridges.
        self._convoy_roads = (
            _ConvoyRoadCoverage(self.roads) if convoy_corridors else None
        )
        self.edges = list(
            {
                frozenset((segment.start, segment.end)): segment
                for segment in self.roads
                if self.allowed(segment)
            }.values()
        )
        self.access = [
            segment
            for segment in base_access
            if not segment.on_road and segment.length > 0 and self.allowed(segment)
        ]

    def allowed(self, segment: GroundSegment) -> bool:
        line = LineString(
            [(segment.start.x, segment.start.z), (segment.end.x, segment.end.z)]
        )
        if (
            segment.on_road
            and self._convoy_roads is not None
            and self._convoy_roads.covers(line)
        ):
            return True
        return bool(
            self.landmap.inclusion_zones.covers(line)
            and not self.landmap.exclusion_zones.intersects(line)
        )

    def _validate_position(self, position: GroundPosition) -> None:
        point = Point(position.x, position.z)
        if self._convoy_roads is not None and self._convoy_roads.covers(point):
            return
        if not self.landmap.inclusion_zones.covers(point):
            raise GroundRouteError("Ground movement position is outside mapped land")
        if self.landmap.exclusion_zones.intersects(point):
            raise GroundRouteError("Ground movement position is in an exclusion zone")

    @classmethod
    def for_game(cls, game: Game, owner: Player) -> CampaignGroundRouter:
        roads = []
        access = []
        for base in game.theater.controlpoints:
            if not base.is_friendly(owner):
                continue
            for destination, points in base.convoy_routes.items():
                if not destination.is_friendly(owner):
                    continue
                try:
                    road = GroundRoute.from_points(
                        GroundPosition(point.x, point.y) for point in points
                    )
                except ValueError as exc:
                    raise GroundRouteError(
                        f"Invalid campaign road from {base.name} to {destination.name}"
                    ) from exc
                roads.append(road)
                for cp, endpoint in (
                    (base, road.segments[0].start),
                    (destination, road.segments[-1].end),
                ):
                    position = GroundPosition(cp.position.x, cp.position.y)
                    if position != endpoint:
                        access.append(GroundSegment(position, endpoint, False))
        return cls(game.theater.landmap, roads, access, convoy_corridors=True)

    @staticmethod
    def _connect(
        graph: dict[GroundPosition, dict[GroundPosition, bool]],
        start: GroundPosition,
        end: GroundPosition,
        on_road: bool,
    ) -> None:
        if start == end:
            return
        # When an access link overlaps an authored road, retain road travel.
        graph.setdefault(start, {})[end] = on_road or graph.get(start, {}).get(
            end, False
        )
        graph.setdefault(end, {})[start] = graph[start][end]

    def _graph(self) -> dict[GroundPosition, dict[GroundPosition, bool]]:
        graph: dict[GroundPosition, dict[GroundPosition, bool]] = {}
        for segment in itertools.chain(self.edges, self.access):
            self._connect(graph, segment.start, segment.end, segment.on_road)
        return graph

    @staticmethod
    def _components(
        graph: dict[GroundPosition, dict[GroundPosition, bool]],
    ) -> dict[GroundPosition, int]:
        components: dict[GroundPosition, int] = {}
        for position in graph:
            if position in components:
                continue
            component = len(components)
            todo = [position]
            components[position] = component
            while todo:
                for neighbor in graph[todo.pop()]:
                    if neighbor not in components:
                        components[neighbor] = component
                        todo.append(neighbor)
        return components

    def _entries(
        self, position: GroundPosition, components: dict[GroundPosition, int]
    ) -> list[RoadAccess]:
        entries = []
        for index, edge in enumerate(self.edges):
            dx, dz = edge.end.x - edge.start.x, edge.end.z - edge.start.z
            fraction = max(
                0.0,
                min(
                    1.0,
                    (
                        (position.x - edge.start.x) * dx
                        + (position.z - edge.start.z) * dz
                    )
                    / (dx * dx + dz * dz),
                ),
            )
            projection = GroundPosition(
                edge.start.x + fraction * dx, edge.start.z + fraction * dz
            )
            segment = GroundSegment(position, projection, False)
            if (
                segment.length <= 1e-6
                and self._convoy_roads is not None
                and self._convoy_roads.covers(Point(position.x, position.z))
            ):
                projection = position
                segment = GroundSegment(position, position, False)
            if segment.length == 0 or self.allowed(segment):
                entries.append(
                    RoadAccess(
                        segment.length, index, projection, components[edge.start]
                    )
                )
        return sorted(entries, key=lambda entry: (entry.distance, entry.edge))

    def plan(
        self,
        origin: GroundPosition,
        destination: GroundPosition,
        road_budget: float,
        offroad_budget: float,
    ) -> GroundRoute:
        for budget in (road_budget, offroad_budget):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, (float, int))
                or not math.isfinite(budget)
                or budget <= 0
            ):
                raise GroundRouteError(
                    "Ground movement budgets must be positive and finite"
                )
        self._validate_position(origin)
        self._validate_position(destination)
        if origin == destination:
            raise GroundRouteError("The ground group is already at that position")
        if not self.roads:
            direct = GroundSegment(origin, destination, False)
            if not self.allowed(direct):
                raise GroundRouteError(
                    "No roads or validated direct off-road route are available"
                )
            return GroundRoute((direct,))
        if not self.edges:
            raise GroundRouteError(
                "Campaign roads cross water or exclusion zones; no verified route"
            )

        graph = self._graph()
        components = self._components(graph)
        entries = self._entries(origin, components)
        destination_entries = self._entries(destination, components)
        for reachable, endpoint in (
            (entries, "group"),
            (destination_entries, "destination"),
        ):
            if not reachable:
                raise GroundRouteError(
                    f"No validated off-road access connects the {endpoint} to a campaign road. "
                    "Access is blocked by mapped water or exclusion zones."
                )
        exits: dict[int, RoadAccess] = {}
        for entry in destination_entries:
            exits.setdefault(entry.component, entry)
        pair = next(
            (
                (entry, exits[entry.component])
                for entry in entries
                if entry.component in exits
            ),
            None,
        )
        if pair is None:
            reason = (
                "The authored corridors are disconnected or a connecting off-road "
                "access is blocked."
                if self._convoy_roads is not None
                else "Mapped water or exclusion zones may block intermediate road segments."
            )
            raise GroundRouteError(
                "Both ends can reach a road, but the campaign road network between "
                f"them is disconnected. {reason}"
            )
        entry, exit = pair
        for point in (entry, exit):
            edge = self.edges[point.edge]
            self._connect(graph, point.position, edge.start, True)
            self._connect(graph, point.position, edge.end, True)
        if entry.edge == exit.edge:
            self._connect(graph, entry.position, exit.position, True)
        self._connect(graph, origin, entry.position, False)
        self._connect(graph, exit.position, destination, False)

        serial = itertools.count()
        queue = [(0.0, next(serial), origin)]
        costs = {origin: 0.0}
        previous: dict[GroundPosition, tuple[GroundPosition, bool]] = {}
        while queue:
            cost, _, position = heapq.heappop(queue)
            if cost > costs[position]:
                continue
            if position == destination:
                break
            for neighbor, on_road in graph[position].items():
                segment = GroundSegment(position, neighbor, on_road)
                candidate = cost + segment.length / (
                    road_budget if on_road else offroad_budget
                )
                if candidate < costs.get(neighbor, math.inf):
                    costs[neighbor] = candidate
                    previous[neighbor] = (position, on_road)
                    heapq.heappush(queue, (candidate, next(serial), neighbor))
        if destination not in previous:
            raise GroundRouteError("No connected campaign road route is available")
        segments = []
        position = destination
        while position != origin:
            before, on_road = previous[position]
            segments.append(GroundSegment(before, position, on_road))
            position = before
        return GroundRoute(tuple(reversed(segments)))
