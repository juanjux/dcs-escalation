"""Surviving ship and building health across campaign turns."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing
    from game.sim import GameUpdateEvents
    from game.theater import TheaterGroundObject, TheaterUnit


def enabled(settings: object) -> bool:
    return bool(getattr(settings, "persistent_damage_enabled", True))


def repair_percent(settings: object) -> int:
    return max(
        0, min(100, int(getattr(settings, "persistent_damage_repair_percent", 30)))
    )


def repaired_health(health: float, percent: int) -> float:
    if health <= 0 or health >= 1 or percent <= 0:
        return health
    result = health + (1 - health) * percent / 100
    # Round to full health once less than half a percent of damage remains.
    return 1.0 if result >= 0.995 else result


def parse_health(raw: Any) -> dict[str, float]:
    """Ignore malformed state entries and support Lua's empty-table encoding."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for name, value in raw.items():
        if (
            isinstance(name, str)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and 0 <= value <= 1
        ):
            result[name] = float(value)
    return result


def commit_damage(game: Game, debriefing: Debriefing, events: GameUpdateEvents) -> None:
    if not enabled(game.settings):
        return
    for name, fraction in getattr(
        debriefing.state_data, "persistent_health", {}
    ).items():
        mapping = debriefing.unit_map.theater_units(name)
        scenery = debriefing.unit_map.scenery_object(name) if mapping is None else None
        unit = (
            mapping.theater_unit
            if mapping is not None
            else (scenery.ground_unit if scenery is not None else None)
        )
        if unit is None or not unit.alive or not unit.persistent_damage_eligible:
            continue
        if fraction <= 0:
            unit.kill(events)
        else:
            unit.health = fraction
            events.update_tgo(unit.ground_object)
            if unit.ground_object.is_control_point:
                events.update_control_point(unit.ground_object.control_point)


def repair_damage(game: Game, events: GameUpdateEvents) -> None:
    """Called once at the turn boundary, including skipped turns."""
    percent = repair_percent(game.settings)
    for tgo in game.theater.ground_objects:
        for unit in tgo.units:
            if not unit.alive:
                continue
            before = unit.health_fraction
            if not enabled(game.settings) or not unit.persistent_damage_eligible:
                unit.health = 1.0
            else:
                unit.health = repaired_health(before, percent)
            if unit.health_fraction != before:
                events.update_tgo(tgo)
                if tgo.is_control_point:
                    events.update_control_point(tgo.control_point)


def health_report(units: Iterable[TheaterUnit], settings: object) -> dict[str, Any]:
    """Percentages use original health, not the fraction of units still alive."""
    rows: list[dict[str, Any]] = []
    for unit in units:
        current = unit.health_fraction
        persistent = enabled(settings) and unit.persistent_damage_eligible
        percent = repair_percent(settings) if persistent else 100
        after = repaired_health(current, percent)
        rows.append(
            {
                "id": unit.id,
                "name": unit.unit_name,
                "health_percent": round(current * 100, 2),
                "persistent": persistent,
                "damage_repaired_per_turn_percent": percent,
                "repair_next_turn_percent": round((after - current) * 100, 2),
                "health_next_turn_percent": round(after * 100, 2),
            }
        )
    count = len(rows) or 1
    return {
        "health_percent": round(sum(row["health_percent"] for row in rows) / count, 2),
        "repair_next_turn_percent": round(
            sum(row["repair_next_turn_percent"] for row in rows) / count, 2
        ),
        "health_next_turn_percent": round(
            sum(row["health_next_turn_percent"] for row in rows) / count, 2
        ),
        "damage_repaired_per_turn_percent": (
            repair_percent(settings) if any(row["persistent"] for row in rows) else 100
        ),
        "units": rows,
    }


def report_for_tgo(tgo: TheaterGroundObject) -> dict[str, Any]:
    game = getattr(getattr(tgo.control_point, "coalition", None), "game", None)
    return health_report(tgo.units, getattr(game, "settings", None))
