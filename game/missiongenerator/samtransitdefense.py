"""Register eligible moving SAMs and retain their original waypoint sequence."""

from __future__ import annotations

from typing import Any

from dcs import Mission
from dcs.lua import dumps
from dcs.task import RunScript

from game.groundmovement.samdefense import transit_defense
from game.theater.theatergroundobject import IadsGroundObject
from game.unitmap import UnitMap


def configure(mission: Mission, unit_map: UnitMap | None) -> list[dict[str, Any]]:
    if unit_map is None:
        return []
    rows = []
    for side in mission.coalition.values():
        for country in side.countries.values():
            for group in country.vehicle_group:
                if len(group.points) < 2:
                    continue
                mappings = [unit_map.theater_objects.get(u.name) for u in group.units]
                if not mappings or any(m is None for m in mappings):
                    continue
                objectives = [m.theater_unit.ground_object for m in mappings if m]
                tgo = objectives[0]
                if not (
                    isinstance(tgo, IadsGroundObject)
                    and getattr(tgo, "in_transit", False)
                    and all(o is tgo for o in objectives)
                ):
                    continue
                if any(u.alive and u.transported_by_id is not None for u in tgo.units):
                    continue
                profile = transit_defense(u.type for u in group.units)
                if profile is None:
                    continue
                for index, point in enumerate(group.points, 1):
                    point.tasks.append(
                        RunScript(
                            "if ESCALATION_SAM_TRANSIT then "
                            f"ESCALATION_SAM_TRANSIT.reached({dumps(group.name)},{index}) end"
                        )
                    )
                rows.append(
                    dict(
                        name=group.name,
                        units=[u.name for u in group.units],
                        range=profile.range_m,
                        ceiling=profile.ceiling_m,
                        minRange=profile.min_range_m,
                        route=list(group.dict()["route"]["points"].values()),
                    )
                )
    return rows
