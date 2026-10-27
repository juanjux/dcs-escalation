"""Incorporate reserve groups reached by a moving front, without replaying combat."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import logging
import math
from typing import TYPE_CHECKING
from uuid import UUID

from dcs import Point
from shapely.geometry import LineString, Point as MapPoint

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.dispatch import active_transit, _cargo_losses, _finish
from game.groundmovement.settings import enabled
from game.missiongenerator.frontlineconflictdescription import (
    FrontLineConflictDescription,
)
from game.theater.frontline import FrontLine
from game.theater.player import Player
from game.theater.theatergroundobject import VehicleGroupGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater.controlpoint import ControlPoint

# Only a geometric tolerance, not an extra combat or reinforcement radius.
_TOUCH_M = 1.0


@dataclass(frozen=True)
class FrontPosition:
    front: FrontLine
    progress: float


def _fronts(game: Game) -> tuple[FrontLine, ...]:
    fronts = {
        front.id: front
        for cp in game.theater.controlpoints
        for front in getattr(cp, "front_lines", {}).values()
        if isinstance(front, FrontLine)
        and not front.blue_cp.is_fleet
        and not front.red_cp.is_fleet
        and front.blue_cp.captured is Player.BLUE
        and front.red_cp.captured is Player.RED
    }
    return tuple(fronts[key] for key in sorted(fronts))


def _route(front: FrontLine) -> LineString:
    return LineString([(point.x, point.y) for point in front.points])


def snapshot_fronts(game: Game) -> tuple[FrontPosition, ...]:
    if not enabled(game.settings):
        return ()
    return tuple(
        FrontPosition(
            front, _route(front).project(MapPoint(front.position.x, front.position.y))
        )
        for front in _fronts(game)
    )


def _within_front_width(
    game: Game, front: FrontLine, route: LineString, progress: float, point: MapPoint
) -> bool:
    width = game.settings.max_frontline_width * 1000
    if route.distance(point) > width / 2 + _TOUCH_M:
        return False
    distance = progress
    segment = front.segments[-1]
    for candidate in front.segments:
        segment = candidate
        if distance <= candidate.length:
            break
        distance -= candidate.length
    projected = route.interpolate(progress)
    center = Point(projected.x, projected.y, game.theater.terrain)
    heading = segment.blue_forward_heading.right
    center = FrontLineConflictDescription.find_ground_position(
        center, width, heading, game.theater
    )
    left = FrontLineConflictDescription.extend_ground_position(
        center, width // 2, heading, game.theater
    )
    right = FrontLineConflictDescription.extend_ground_position(
        center, width // 2, heading.opposite, game.theater
    )
    dx, dy = right.x - left.x, right.y - left.y
    length = math.hypot(dx, dy)
    if length < _TOUCH_M:
        return point.distance(MapPoint(center.x, center.y)) <= _TOUCH_M
    # Mission headings are rounded to degrees. Compare lateral coverage, not
    # sub-metre collinearity with that rounded perpendicular cross-section.
    lateral = ((point.x - left.x) * dx + (point.y - left.y) * dy) / length
    return -_TOUCH_M <= lateral <= length + _TOUCH_M


def _receiver(
    game: Game,
    group: VehicleGroupGroundObject,
    before: dict[UUID, float],
    fronts: tuple[FrontLine, ...],
) -> ControlPoint | None:
    owner = group.control_point.captured
    if owner not in (Player.BLUE, Player.RED):
        return None
    point = MapPoint(group.position.x, group.position.y)
    candidates = []
    for front in fronts:
        route = _route(front)
        if route.length == 0:
            continue
        current = route.project(MapPoint(front.position.x, front.position.y))
        previous = before.get(front.id, current)
        progress = route.project(point)
        # The front must reach this side's group, not advance away from it.
        if owner is Player.BLUE:
            reached = current - _TOUCH_M <= progress <= previous + _TOUCH_M
        else:
            reached = previous - _TOUCH_M <= progress <= current + _TOUCH_M
        if not reached or not _within_front_width(game, front, route, progress, point):
            continue
        base = front.control_point_friendly_to(owner)
        # Prefer the closest actual combat line when several fronts overlap.
        candidates.append(
            (
                point.distance(MapPoint(front.position.x, front.position.y)),
                str(front.id),
                base,
            )
        )
    return (
        min(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None
    )


def integrate_reached_reserves(
    game: Game, before: tuple[FrontPosition, ...], events: GameUpdateEvents
) -> None:
    """Transfer survivors once, closing movement before it can continue past the front."""
    if not enabled(game.settings):
        return
    fronts = _fronts(game)
    previous = {state.front.id: state.progress for state in before}
    groups = [
        tgo
        for cp in game.theater.controlpoints
        for tgo in list(cp.connected_objectives)
        if isinstance(tgo, VehicleGroupGroundObject)
        and getattr(tgo, "absorbed_into_frontline", None) is None
        and not tgo.is_dead
    ]
    for group in sorted(groups, key=lambda tgo: str(tgo.id)):
        base = _receiver(game, group, previous, fronts)
        if base is None:
            continue
        transit = active_transit(game, group.id)
        if transit is not None:
            _cargo_losses(game, transit, events)
        survivors: Counter[GroundUnitType] = Counter()
        try:
            for unit in group.units:
                if unit.alive:
                    unit_type = unit.unit_type
                    if not isinstance(unit_type, GroundUnitType):
                        raise ValueError("Non-ground unit in a reserve group")
                    survivors[unit_type] += 1
        except (KeyError, StopIteration, ValueError):
            logging.exception("Cannot integrate reserve group %s", group.name)
            continue
        if not survivors:
            continue
        if transit is not None:
            _finish(game, transit)
        base.base.commission_units(dict(survivors))
        group.absorbed_into_frontline = base.id
        for formation in group.groups:
            formation.units.clear()
        group.in_transit = False
        group.invalidate_threat_poly()
        # Retain the empty DB object for completed journey reports and old ATO
        # references, but remove it from active objectives and the map.
        group.control_point.connected_objectives.remove(group)
        events.delete_tgo(group).update_control_point(base).update_motorpools_at(base)
        game.message(
            "Reserve integration",
            f"{base.captured.name}: {group.name} joined the frontline at {base.name} "
            f"with {sum(survivors.values())} surviving units. "
            "Deployment limits apply; excess units remain in the Motor Pool.",
        )
