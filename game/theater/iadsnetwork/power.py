"""Power carried by independent air-defence vehicles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.data.radar_db import SELF_CONTAINED_AIR_DEFENCES
from game.data.units import UnitClass
from .iadsrole import IadsRole

if TYPE_CHECKING:
    from game.theater.theatergroup import IadsGroundGroup, TheaterUnit


def integrated_power_units(group: IadsGroundGroup) -> list[TheaterUnit]:
    """Local supplies of a group made only of self-contained air defences.

    Support trucks do not change its power requirements. Separate radars, command
    vehicles or dependent launchers do, even when destroyed: losing part of a
    large battery must not make the rest electrically independent.
    """
    if getattr(group, "iads_role", None) not in (
        IadsRole.SAM,
        IadsRole.SAM_AS_EWR,
        IadsRole.EWR,
        IadsRole.POINT_DEFENSE,
    ):
        return []
    supplies = []
    for unit in group.units:
        if getattr(unit, "type", None) in SELF_CONTAINED_AIR_DEFENCES:
            supplies.append(unit)
        else:
            unit_type = getattr(unit, "unit_type", None)
            if unit_type is None or unit_type.unit_class not in (
                UnitClass.LOGISTICS,
                UnitClass.POWER,
            ):
                return []
    return supplies
