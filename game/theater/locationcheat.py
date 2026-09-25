"""Destroying or reviving everything at one location, as a cheat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.sim import GameUpdateEvents
    from game.theater import TheaterGroundObject
    from game.theater.theatergroup import TheaterGroup


def destroy_all(
    game: Game, ground_object: TheaterGroundObject, events: GameUpdateEvents
) -> int:
    """Kill every unit still standing there, and say how many."""
    killed = 0
    for group in ground_object.groups:
        for unit in group.units:
            if unit.alive:
                unit.kill(events)
                _count_in_reserve(ground_object, group, -1)
                killed += 1
    _settle(game, ground_object, events)
    return killed


def revive_all(
    game: Game, ground_object: TheaterGroundObject, events: GameUpdateEvents
) -> int:
    """Bring back every unit that is dead or under repair, and say how many. A repair
    under way is finished rather than left to run on a unit already standing."""
    revived = 0
    for group in ground_object.groups:
        for unit in group.units:
            if unit.alive:
                continue
            unit.repair_turns_remaining = None
            unit.revive(events)
            _count_in_reserve(ground_object, group, 1)
            revived += 1
    _settle(game, ground_object, events)
    return revived


def _count_in_reserve(
    ground_object: TheaterGroundObject, group: TheaterGroup, change: int
) -> None:
    """A motor pool's vehicles are its base's reserve armour, which loses them, or gets
    them back, as it would from a strike. Otherwise the pool is filled again from the
    reserve as soon as it is next drawn."""
    if not isinstance(ground_object, MotorpoolGroundObject):
        return
    unit_type = ground_object.motorpool_unit_types.get(group.id)
    if unit_type is None:
        return
    armor = ground_object.control_point.base.armor
    armor[unit_type] = max(0, armor.get(unit_type, 0) + change)


def _settle(
    game: Game, ground_object: TheaterGroundObject, events: GameUpdateEvents
) -> None:
    """Work out again what the turn derives from what is standing: the threat zones the
    flights are planned around and, for a motor pool, the armour the intel counts."""
    if isinstance(ground_object, MotorpoolGroundObject):
        events.update_motorpools_at(ground_object.control_point)
        game.game_stats.update(game)
    game.compute_threat_zones(events)
