"""Frontline MANPADS budgets and spatial assignment to combat formations."""

from __future__ import annotations

from typing import Sequence

from dcs.mapping import Point
from dcs.unitgroup import VehicleGroup

from game.data.units import UnitClass
from game.ground_forces.ai_ground_planner import CombatGroup, CombatGroupRole

DEFAULT_VEHICLES_PER_MANPAD_TEAM = 8
COMBAT_ROLES = frozenset(
    {
        CombatGroupRole.TANK,
        CombatGroupRole.APC,
        CombatGroupRole.IFV,
        CombatGroupRole.ARTILLERY,
        CombatGroupRole.SHORAD,
        CombatGroupRole.ATGM,
        CombatGroupRole.RECON,
    }
)


def is_combat_vehicle(group: CombatGroup) -> bool:
    return group.role in COMBAT_ROLES and group.unit_type.unit_class not in (
        UnitClass.MANPAD,
        UnitClass.INFANTRY,
        UnitClass.LOGISTICS,
    )


def additional_manpad_teams(
    groups: Sequence[CombatGroup], vehicles_per_team: int
) -> int:
    """Round the vehicle-based allowance to the nearest team, counting existing launchers."""
    if vehicles_per_team <= 0:
        return 0
    vehicles = sum(group.size for group in groups if is_combat_vehicle(group))
    allowance = (2 * vehicles + vehicles_per_team) // (2 * vehicles_per_team)
    existing = sum(
        group.size for group in groups if group.unit_type.unit_class is UnitClass.MANPAD
    )
    return max(0, allowance - existing)


def select_manpad_hosts(
    groups: Sequence[tuple[VehicleGroup, CombatGroup]],
    count: int,
    occupied: Sequence[Point],
) -> list[VehicleGroup]:
    """Prefer carriers and spread teams among the available formations."""
    candidates = [
        (vehicle, group) for vehicle, group in groups if is_combat_vehicle(group)
    ]
    if not candidates or count <= 0:
        return []
    selected: list[VehicleGroup] = []
    positions = list(occupied)
    unused = list(candidates)
    for _ in range(count):
        if not unused:
            unused = list(candidates)
        carriers = [
            item
            for item in unused
            if item[1].role in (CombatGroupRole.APC, CombatGroupRole.IFV)
        ]
        pool = carriers or unused
        if positions:
            chosen = max(
                pool,
                key=lambda item: min(
                    item[0].points[0].position.distance_to_point(position)
                    for position in positions
                ),
            )
        else:
            chosen = pool[0]
        selected.append(chosen[0])
        positions.append(chosen[0].points[0].position)
        unused.remove(chosen)
    return selected
