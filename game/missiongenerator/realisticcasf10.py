"""Explicit BLUE-view F10 scope; only groups created by the frontline generator."""

from __future__ import annotations

from typing import Any


def collect_frontline_map_groups(
    mission: Any, mission_data: Any, registry: dict[str, Any]
) -> list[dict[str, Any]]:
    frontline: set[str] = getattr(mission_data, "frontline_visibility_groups", set())
    managed = {row["name"] for row in registry["groups"]}
    side = mission.coalition.get("red")
    if side is None:
        return []
    result = []
    for country in side.countries.values():
        for group in country.vehicle_group:
            if str(group.name) in frontline and str(group.name) in managed:
                result.append({"name": str(group.name), "id": group.id, "coalition": 1})
    return sorted(result, key=lambda row: row["name"])


def apply_frontline_map_groups(mission: Any, groups: list[dict[str, Any]]) -> None:
    if not groups:
        return
    names = {row["name"] for row in groups}
    for country in mission.coalition["red"].countries.values():
        for group in country.vehicle_group:
            if str(group.name) in names:
                group.hidden = True
    mission.forced_options.user_marks = True
