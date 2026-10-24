"""An AFAC search orbit starts its station clock on arrival, not at planned TOT."""

import json

from dcs.point import MovingPoint
from dcs.task import ControlledTask, OrbitAction, RunScript, SetUnlimitedFuelCommand

from game.ato.flightplans.afac import AfacFlightPlan
from .pydcswaypointbuilder import PydcsWaypointBuilder


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
        orbit.stop_if_lua_predicate(f"""(function()
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
