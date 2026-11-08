"""Sparse local feeds and a radio backbone derived from the available sites."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TYPE_CHECKING

from .iadsrole import IadsRole

if TYPE_CHECKING:
    from game.theater.theatergroundobject import TheaterGroundObject


RADIO_ROLES = frozenset({IadsRole.CONNECTION_NODE, IadsRole.COMMAND_CENTER})


class Components:
    """Union-find for a deterministic minimum-length spanning forest."""

    def __init__(self, size: int) -> None:
        self.parents = list(range(size))

    def root(self, item: int) -> int:
        while item != self.parents[item]:
            self.parents[item] = self.parents[self.parents[item]]
            item = self.parents[item]
        return item

    def join(self, left: int, right: int) -> bool:
        left, right = self.root(left), self.root(right)
        if left == right:
            return False
        self.parents[right] = left
        return True


def sparse_connections(
    objects: Iterable[TheaterGroundObject],
    friendly: Callable[[TheaterGroundObject, TheaterGroundObject], bool],
    settings_for: Callable[[TheaterGroundObject], Any],
) -> dict[TheaterGroundObject, list[TheaterGroundObject]]:
    """Keep radio sectors connected, without an all-to-all proximity mesh.

    Radio links form a minimum-length backbone. Additional backbone edges preserve
    any single-router-loss bypass that the full range graph provides. Consumers
    attach locally, with a second attachment only when it supplies a path to
    command that avoids their first hop. Power is a separate nearest-station
    feed: neither towers nor power stations relay electricity.

    Health does not choose the wiring. Destroying a dependency cuts its links;
    it does not silently reroute them to every other station in range.
    """
    sites = sorted(objects, key=lambda obj: obj.original_name)
    result: dict[TheaterGroundObject, list[TheaterGroundObject]] = {
        obj: [] for obj in sites
    }
    routers = [
        obj for obj in sites if IadsRole.for_category(obj.category) in RADIO_ROLES
    ]
    plants = [
        obj
        for obj in sites
        if IadsRole.for_category(obj.category) is IadsRole.POWER_SOURCE
    ]

    def distance(left: TheaterGroundObject, right: TheaterGroundObject) -> float:
        return left.position.distance_to_point(right.position)

    ranges = {
        obj: IadsRole.for_category(obj.category)
        .connection_range(settings_for(obj))
        .meters
        for obj in [*routers, *plants]
    }

    def reach(obj: TheaterGroundObject) -> float:
        return ranges[obj]

    # An infrastructure link is bidirectional, so both radio endpoints must reach.
    edges = sorted(
        (distance(left, right), i, j)
        for i, left in enumerate(routers)
        for j, right in enumerate(routers[:i])
        if friendly(left, right)
        and distance(left, right) <= min(reach(left), reach(right))
    )
    selected: set[tuple[int, int]] = set()
    components = Components(len(routers))
    for _, left, right in edges:
        if components.join(left, right):
            selected.add((left, right))

    commands = {
        i
        for i, obj in enumerate(routers)
        if IadsRole.for_category(obj.category) is IadsRole.COMMAND_CENTER
    }
    # A tower or command centre must not become an avoidable single point of
    # failure just because the shortest tree happened to route through it.
    failure_components = []
    for failed in range(len(routers)):
        surviving = Components(len(routers))
        for left, right in sorted(selected):
            if failed not in (left, right):
                surviving.join(left, right)
        for _, left, right in edges:
            if failed not in (left, right) and surviving.join(left, right):
                selected.add((left, right))
        failure_components.append(surviving)

    for left, right in sorted(selected):
        result[routers[left]].append(routers[right])
        result[routers[right]].append(routers[left])

    command_components = {components.root(i) for i in commands}
    for obj in sites:
        if obj in plants:
            continue
        power = sorted(
            (
                plant
                for plant in plants
                if friendly(obj, plant) and distance(obj, plant) <= reach(plant)
            ),
            key=lambda plant: (distance(obj, plant), plant.original_name),
        )
        if power:
            result[obj].append(power[0])
        if obj in routers:
            continue
        nearby = sorted(
            (
                i
                for i, router in enumerate(routers)
                if friendly(obj, router) and distance(obj, router) <= reach(router)
            ),
            key=lambda i: (
                components.root(i) not in command_components,
                distance(obj, routers[i]),
                routers[i].original_name,
            ),
        )
        if not nearby:
            continue
        first = nearby[0]
        result[obj].append(routers[first])
        surviving = failure_components[first]
        roots = {surviving.root(i) for i in commands if i != first}
        backup = next((i for i in nearby[1:] if surviving.root(i) in roots), None)
        if backup is not None:
            result[obj].append(routers[backup])
    return result
