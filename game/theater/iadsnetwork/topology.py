"""Fixed power feeds and range-limited radio candidates."""

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
    """Wire two nearest stations without replacing a destroyed power feed.

    Radio candidates are separate: their active uplinks depend on the current
    availability of the radio network, not on this physical power wiring.
    """
    sites = sorted(objects, key=lambda obj: obj.original_name)
    result: dict[TheaterGroundObject, list[TheaterGroundObject]] = {
        obj: [] for obj in sites
    }
    plants = [
        obj
        for obj in sites
        if IadsRole.for_category(obj.category) is IadsRole.POWER_SOURCE
    ]

    def distance(left: TheaterGroundObject, right: TheaterGroundObject) -> float:
        return left.position.distance_to_point(right.position)

    for obj in sites:
        if obj in plants:
            continue
        power = sorted(
            (
                plant
                for plant in plants
                if friendly(obj, plant)
                and distance(obj, plant)
                <= IadsRole.POWER_SOURCE.connection_range(settings_for(plant)).meters
            ),
            key=lambda plant: (distance(obj, plant), plant.original_name),
        )
        result[obj].extend(power[:2])
    return result


def radio_candidates(
    objects: Iterable[TheaterGroundObject],
    friendly: Callable[[TheaterGroundObject, TheaterGroundObject], bool],
    settings_for: Callable[[TheaterGroundObject], Any],
) -> dict[TheaterGroundObject, list[tuple[TheaterGroundObject, int]]]:
    """Return possible radios, not simultaneous connections, in stable order."""
    sites = sorted(objects, key=lambda obj: obj.original_name)
    routers = [
        obj for obj in sites if IadsRole.for_category(obj.category) in RADIO_ROLES
    ]
    ranges = {
        obj: IadsRole.for_category(obj.category)
        .connection_range(settings_for(obj))
        .meters
        for obj in routers
    }
    result: dict[TheaterGroundObject, list[tuple[TheaterGroundObject, int]]] = {}
    for obj in sites:
        if IadsRole.for_category(obj.category) is IadsRole.POWER_SOURCE or getattr(
            obj, "carries_gps_jammer", False
        ):
            result[obj] = []
            continue
        candidates = []
        for router in routers:
            if router is obj or not friendly(obj, router):
                continue
            reach = ranges[router]
            if obj in ranges:
                reach = min(reach, ranges[obj])
            distance = obj.position.distance_to_point(router.position)
            if distance <= reach:
                candidates.append((router, int(distance + 0.5)))
        result[obj] = sorted(
            candidates,
            key=lambda item: (
                IadsRole.for_category(item[0].category) is not IadsRole.CONNECTION_NODE,
                item[1],
                item[0].original_name,
            ),
        )
    return result
