"""Destroying or reviving everything at one location, as a cheat."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.sim import GameUpdateEvents
    from game.theater import TheaterGroundObject


def destroy_all(ground_object: TheaterGroundObject, events: GameUpdateEvents) -> int:
    """Kill every unit still standing there, and say how many."""
    killed = 0
    for unit in ground_object.units:
        if unit.alive:
            unit.kill(events)
            killed += 1
    return killed


def revive_all(ground_object: TheaterGroundObject, events: GameUpdateEvents) -> int:
    """Bring back every unit that is dead or under repair, and say how many. A repair
    under way is finished rather than left to run on a unit already standing."""
    revived = 0
    for unit in ground_object.units:
        if unit.alive:
            continue
        unit.repair_turns_remaining = None
        unit.revive(events)
        revived += 1
    return revived
