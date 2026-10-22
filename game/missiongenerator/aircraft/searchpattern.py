"""Bounded AI search routes use the assigned area, never hidden target positions."""

from datetime import datetime
import json
import logging
import math
from typing import Any

from dcs.task import ControlledTask, RunScript

from game.ato import FlightType
from game.utils import knots


def add_search_pattern(
    flight: Any, group: Any, now: datetime, generated: list[tuple[Any, Any]]
) -> bool:
    settings = flight.coalition.game.settings
    if (
        not settings.plugins.get("realisticcas", False)
        or flight.client_count
        or flight.flight_type not in (FlightType.CAS, FlightType.ARMED_RECON)
    ):
        return False
    plan = flight.flight_plan
    if not callable(getattr(plan, "ui_zone", None)):
        return False
    zone = plan.ui_zone()
    objective = (
        plan.layout.patrol_start
        if flight.flight_type == FlightType.CAS
        else plan.tot_waypoint
    )
    anchor = next(
        (native for logical, native in generated if logical is objective), None
    )
    if anchor is None:
        return (
            False  # In-air flight has already passed the objective: do not rewind it.
        )
    if flight.flight_type == FlightType.CAS:
        end = plan.patrol_end_time
    else:
        end = plan.tot + flight.coalition.doctrine.cas_duration
    deadline = (end - now).total_seconds()
    if deadline <= 0:
        return False
    center = zone.points[0]
    # Small target zones need a standoff circuit rather than impossible tight turns.
    # Engagement remains restricted to the original ingress task's zone.
    half_width = min(1500.0, max(250.0, zone.radius.meters * 0.35))
    speed = max(
        float(anchor.speed), knots(60 if flight.is_helo else 180).meters_per_second
    )
    insertion = group.points.index(anchor) + 1
    if insertion >= len(group.points):
        return False  # No exit leg exists; never create an invalid waypoint jump.
    added = []
    for index, (dx, dy) in enumerate(((-1, -1), (-1, 1), (1, 1), (1, -1)), 1):
        point = center.new_in_same_map(
            center.x + dx * half_width, center.y + dy * half_width
        )
        native = group.add_waypoint(
            point, anchor.alt, speed=speed * 3.6, name=f"SEARCH {index}"
        )
        native.alt_type = anchor.alt_type
        added.append(native)
    del group.points[-len(added) :]
    group.points[insertion:insertion] = added
    # Old departure/arrival TOTs do not include this optional search circuit.
    for point in group.points[insertion:]:
        point.ETA_locked = False
        point.speed_locked = True
    start_index = insertion + 1  # DCS command waypoint indexes are one-based.
    end_index = insertion + len(added)
    name = json.dumps(str(group.name), ensure_ascii=False)
    exit_index = end_index + 1
    # A waypoint switch alone does not stop an active en-route engagement. Give
    # the native task the same limits, including while combat suspends navigation.
    fuel_condition = f"""(function()
local g=Group.getByName({name})
if not g or not g:isExist() then return true end
for _,u in ipairs(g:getUnits()) do
    if u:isExist() and u:getFuel()<0.2 then return true end
end
return false
end)()"""
    for native in group.points[:insertion]:
        for index, task in enumerate(native.tasks):
            if task.id == "EngageTargetsInZone":
                bounded = ControlledTask(task)
                bounded.enabled, bounded.auto = task.enabled, task.auto
                native.tasks[index] = task = bounded
            if (
                task.id != "ControlledTask"
                or task.params.get("task", {}).get("id") != "EngageTargetsInZone"
            ):
                continue
            stop = task.params.setdefault("stopCondition", {})
            stop["time"] = min(
                stop.get("time", math.ceil(deadline)), math.ceil(deadline)
            )
            existing = stop.get("condition")
            stop["condition"] = (
                f"({existing}) or ({fuel_condition})" if existing else fuel_condition
            )
    for offset, point in enumerate(added):
        current_index = start_index + offset
        script = f"""do
local g=Group.getByName({name})
if not g or not g:isExist() then return end
env.info('REALISTIC_CAS_SEARCH|'..{name}..' corner={current_index} t='..timer.getTime())
local destination=nil
if timer.getTime()>={deadline:.3f} then
    destination={exit_index}
end
for _,unit in ipairs(g:getUnits()) do
    if unit:isExist() and unit:getFuel()<0.2 then
        destination={exit_index}
    end
end
if not destination and {current_index}=={end_index} then destination={start_index} end
if destination then
    env.info('REALISTIC_CAS_SEARCH|'..{name}..' switch {current_index}->'..destination)
    g:getController():setCommand({{id='SwitchWaypoint',params={{
    fromWaypointIndex={current_index},goToWaypointIndex=destination
    }}}})
end
end
"""
        point.add_task(RunScript(script))
    logging.info(
        "Realistic CAS: moving search circuit for %s until mission time %.0f",
        group.name,
        deadline,
    )
    return True
