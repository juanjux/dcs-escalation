"""Distance-budget journeys shared by campaign ground transports."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable

from game.groundmovement.orders import GroundPosition


@dataclass(frozen=True)
class GroundSegment:
    start: GroundPosition
    end: GroundPosition
    on_road: bool = True

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.z - self.start.z)


@dataclass(frozen=True)
class GroundRoute:
    segments: tuple[GroundSegment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("A ground route needs at least one nonzero segment")
        for index, segment in enumerate(self.segments):
            if not math.isfinite(segment.length) or segment.length <= 0:
                raise ValueError(
                    "Ground route segments must have positive finite length"
                )
            if type(segment.on_road) is not bool:
                raise ValueError("A ground segment requires its road mode")
            if index and self.segments[index - 1].end != segment.start:
                raise ValueError("Ground route segments must be continuous")

    @classmethod
    def from_points(cls, points: Iterable[GroundPosition]) -> GroundRoute:
        unique: list[GroundPosition] = []
        for point in points:
            if not unique or unique[-1] != point:
                unique.append(point)
        return cls(tuple(GroundSegment(a, b) for a, b in zip(unique, unique[1:])))

    @property
    def length(self) -> float:
        return sum(segment.length for segment in self.segments)

    def position_at(self, distance: float) -> GroundPosition:
        distance = max(0, min(self.length, distance))
        for segment in self.segments:
            if distance <= segment.length:
                fraction = distance / segment.length
                return GroundPosition(
                    segment.start.x + (segment.end.x - segment.start.x) * fraction,
                    segment.start.z + (segment.end.z - segment.start.z) * fraction,
                )
            distance -= segment.length
        return self.segments[-1].end


@dataclass
class GroundJourney:
    route: GroundRoute
    segment_index: int = 0
    segment_progress: float = 0
    last_advanced_turn: int = -1

    @property
    def completed(self) -> bool:
        return self.segment_index == len(self.route.segments)

    @property
    def position(self) -> GroundPosition:
        if self.completed:
            return self.route.segments[-1].end
        segment = self.route.segments[self.segment_index]
        fraction = self.segment_progress / segment.length
        return GroundPosition(
            segment.start.x + (segment.end.x - segment.start.x) * fraction,
            segment.start.z + (segment.end.z - segment.start.z) * fraction,
        )

    @property
    def remaining_distance(self) -> float:
        return (
            sum(s.length for s in self.route.segments[self.segment_index :])
            - self.segment_progress
        )

    @property
    def travelled_distance(self) -> float:
        return self.route.length - self.remaining_distance

    def advance(
        self, turn: int, road_budget: float, offroad_budget: float
    ) -> tuple[GroundPosition, ...]:
        """Spend at most one turn, with proportional cost for each segment's mode."""
        for value in (road_budget, offroad_budget):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("Ground travel budgets must be finite and positive")
        if type(turn) is not int or turn < 0:
            raise ValueError("Invalid movement turn")
        points = [self.position]
        if turn <= self.last_advanced_turn or self.completed:
            return tuple(points)
        self.last_advanced_turn = turn
        remaining_turn = 1.0
        while not self.completed and remaining_turn > 1e-12:
            segment = self.route.segments[self.segment_index]
            budget = road_budget if segment.on_road else offroad_budget
            distance = segment.length - self.segment_progress
            travel = min(distance, remaining_turn * budget)
            remaining_turn = max(0, remaining_turn - travel / budget)
            self.segment_progress += travel
            if self.segment_progress >= segment.length - 1e-8:
                self.segment_index += 1
                self.segment_progress = 0
            if self.position != points[-1]:
                points.append(self.position)
        return tuple(points)

    def preview(
        self, road_budget: float, offroad_budget: float
    ) -> tuple[GroundPosition, ...]:
        return replace(self).advance(
            self.last_advanced_turn + 1, road_budget, offroad_budget
        )
