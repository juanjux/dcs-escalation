from dcs.point import MovingPoint
from dcs.task import RefuelingTaskAction, ControlledTask

from .pydcswaypointbuilder import PydcsWaypointBuilder

#: Refuel until every unit is at least this full, then break off. Relative to
#: INTERNAL capacity, which is what ``Unit.getFuel`` reports -- a flight still
#: carrying a drop tank reads above 1.0 and so is never sent to the tanker.
TOPPED_OFF = 0.5


class RefuelPointBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        if not self.ai_despawn(waypoint, True):
            refuel = ControlledTask(RefuelingTaskAction())
            # Stop condition only. There used to be a start condition as well --
            # "every unit is at or above 20%" -- which meant a flight that arrived
            # at the tanker below a fifth of its fuel, the one case the whole
            # feature exists for, never started refuelling at all. With only the
            # stop condition, a flight that does not need fuel breaks off the
            # moment it arrives (the condition is already true) and one that does
            # takes on fuel until it is half full.
            refuel.stop_if_lua_predicate(self._get_lua_predicate(TOPPED_OFF))
            waypoint.add_task(refuel)
        return super().add_tasks(waypoint)

    def _get_lua_predicate(self, fuel_level: float) -> str:
        return f"""
            local group = Group.getByName('{self.group.name}')
            if group == nil then return true end
            local okfuel = true
            for i, unitObject in pairs(group:getUnits()) do
                if Unit.getFuel(unitObject) < {fuel_level} then okfuel = false; break end
            end
            return okfuel
            """
