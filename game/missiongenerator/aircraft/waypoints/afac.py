"""Native AFAC search routes and station timing."""

import json
from typing import Any

from dcs.point import MovingPoint
from dcs.task import ControlledTask, OrbitAction, RunScript, SetUnlimitedFuelCommand
from dcs.unitgroup import FlyingGroup

from game.ato import Flight, FlightType
from game.ato.flightplans.afac import AfacFlightPlan
from game.theater import FrontLine
from game.utils import Heading
from .pydcswaypointbuilder import PydcsWaypointBuilder


def add_frontline_search_loop(flight: Flight, group: FlyingGroup[Any]) -> None:
    """Fly both sides of the assigned DCS frontline zone on native waypoints."""
    plan = flight.flight_plan
    front = flight.package.target
    anchor = getattr(group, "_afac_search_point", None)
    if not isinstance(plan, AfacFlightPlan) or not isinstance(front, FrontLine):
        return
    if anchor not in group.points:
        return
    insertion = group.points.index(anchor) + 1
    if insertion + 1 >= len(group.points):
        return
    start, end = plan.ui_zone().points
    if start.distance_to_point(end) < 1:
        return

    # Use the ATO order to give consecutive flights on the same front different circuits.
    flights = (
        candidate
        for package in flight.coalition.ato.packages
        if package.target == front
        for candidate in package.flights
        if candidate.flight_type is FlightType.AFAC_FRONTLINE
    )
    alternate = next(
        (index % 2 for index, candidate in enumerate(flights) if candidate is flight), 0
    )
    forward = Heading.from_degrees(start.heading_between_point(end)).right
    if forward.angle_between(front.blue_forward_heading).degrees > 90:
        forward = forward.opposite
    if flight.coalition.player.is_red:
        forward = forward.opposite
    radius = plan.engagement_distance.meters
    enemy = radius * (0.45 + 0.15 * alternate)
    friendly = radius * (0.20 + 0.10 * alternate)
    corners = (
        start.point_from_heading(forward.degrees, enemy),
        end.point_from_heading(forward.degrees, enemy),
        end.point_from_heading(forward.opposite.degrees, friendly),
        start.point_from_heading(forward.opposite.degrees, friendly),
    )
    # Keep the existing SEARCH START/END and their fuel and station tasks.
    search_orbit = getattr(group, "_afac_search_orbit", None)
    if search_orbit not in anchor.tasks:
        return
    anchor.tasks.remove(search_orbit)
    loop = []
    speed = plan.patrol_speed.kph
    for index, corner in enumerate(corners, 1):
        point = group.add_waypoint(
            corner, anchor.alt, speed=speed, name=f"SEARCH {index}"
        )
        point.alt_type = anchor.alt_type
        loop.append(point)
    del group.points[-len(loop) :]
    group.points[insertion:insertion] = loop
    setattr(group, "_afac_search_loop", tuple(loop))

    first, last = insertion + 1, insertion + len(loop)
    name = json.dumps(str(group.name), ensure_ascii=False)
    seconds = int(plan.patrol_duration.total_seconds())
    for index, point in enumerate(loop, first):
        point.ETA_locked = False
        point.speed_locked = True
        point.add_task(RunScript(f"""do
local g=Group.getByName({name})
if not g or not g:isExist() then return end
local cas=RealisticCAS or {{}}
local start=(cas.afacStations or {{}})[{name}]
local done=(cas.afacAbort or {{}})[{name}] or (cas.afacReturn or {{}})[{name}] or
    (start and timer.getTime()>=start+{seconds})
for _,u in ipairs(g:getUnits()) do
    if u:isExist() then
        if u:getPlayerName() then return end
        if u:getFuel()<0.2 then done=true end
    end
end
local nextPoint=done and {last+1} or ({index}=={last} and {first})
if nextPoint then
    g:getController():setCommand({{id='SwitchWaypoint',params={{
        fromWaypointIndex={index},goToWaypointIndex=nextPoint
    }}}})
end
end"""))


class AfacSearchBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        plan = self.flight.flight_plan
        if not isinstance(plan, AfacFlightPlan):
            raise TypeError("AFAC search requires an AFAC flight plan")
        name = json.dumps(str(self.group.name), ensure_ascii=False)
        # Retain the native point identity until the final route is assembled.
        setattr(self.group, "_afac_search_point", waypoint)
        setattr(self.group, "_afac_patrol_speed", plan.patrol_speed.meters_per_second)
        setattr(
            self.group,
            "_afac_restore_unlimited_fuel",
            self.flight.squadron.coalition.game.settings.ai_unlimited_fuel,
        )
        waypoint.add_task(SetUnlimitedFuelCommand(False))
        waypoint.add_task(
            RunScript(
                "RealisticCAS=RealisticCAS or {}; RealisticCAS.afacStations=RealisticCAS.afacStations or {}; "
                f"RealisticCAS.afacStations[{name}]=RealisticCAS.afacStations[{name}] or timer.getTime()"
            )
        )
        orbit = ControlledTask(
            OrbitAction(
                altitude=waypoint.alt,
                pattern=OrbitAction.OrbitPattern.RaceTrack,
                speed=int(plan.patrol_speed.kph),
            )
        )
        orbit.stop_after_duration(int(plan.patrol_duration.total_seconds()))
        orbit.stop_if_lua_predicate(f"""return (function()
local g=Group.getByName({name})
if not g or not g:isExist() then return true end
local start=(RealisticCAS.afacStations or {{}})[{name}]
if (RealisticCAS.afacAbort or {{}})[{name}] or
    (RealisticCAS.afacReturn or {{}})[{name}] or
    (start and timer.getTime()>=start+{int(plan.patrol_duration.total_seconds())}) then return true end
for _,u in ipairs(g:getUnits()) do
    if u:isExist() and u:getFuel()<0.2 then return true end
end
return false
end)()""")
        waypoint.add_task(orbit)
        setattr(self.group, "_afac_search_orbit", orbit)
