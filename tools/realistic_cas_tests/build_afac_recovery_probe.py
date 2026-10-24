"""Isolate native mountain recovery from AFAC scripts and task replacement."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript
from dcs.mapping import Point
from dcs.planes import MQ_9_Reaper
from dcs.task import Nothing, OptROE, OrbitAction, SwitchWaypoint
from dcs.translation import String
from dcs.triggers import TriggerStart

from game.missiongenerator.realisticcasluadata import _native_route_value, lua_literal


def build_mission(*, replacement_matrix: bool = False) -> Mission:
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 12)
    mission.groundControl.blue_game_masters = 1
    airport = mission.terrain.airports["Kobuleti"]
    airport.set_coalition("blue")
    mission.weather.clouds_preset = None
    mission.weather.clouds_base = 2000
    mission.weather.clouds_thickness = 1000
    mission.weather.clouds_density = 8
    # Last observed mountain recovery position, shortly after the AFAC abort.
    origin = Point(-191986.29741099, 634286.1456362, mission.terrain)
    cases = (
        (
            ("NATIVE_DIRECT", False, False),
            ("NATIVE_SWITCH", False, True),
            ("REPLACED_DIRECT", True, False),
            ("REPLACED_SWITCH", True, True),
        )
        if replacement_matrix
        else (
            ("RECOVERY_DIRECT", False, False),
            ("RECOVERY_CRUISE", False, False),
        )
    )
    replacements = {}
    for index, (name, replaced, switch) in enumerate(cases):
        cruise = name == "RECOVERY_CRUISE"
        speed = 200 if replacement_matrix else 400
        group = mission.flight_group_inflight(
            mission.country("USA"),
            name,
            MQ_9_Reaper,
            origin.point_from_heading(90, 500 * index),
            3506,
            speed=speed,
        )
        group.task = Nothing.name
        group.units[0].fuel = MQ_9_Reaper.fuel_max * 0.85
        group.points[0].add_task(OptROE(OptROE.Values.WeaponHold))
        if switch:
            for _ in range(2):
                group.add_waypoint(group.points[0].position, 3506, speed=speed)
        if replaced:
            group.points[0].add_task(
                OrbitAction(3506, speed, OrbitAction.OrbitPattern.Circle)
            )
        elif switch:
            group.points[0].add_task(SwitchWaypoint(1, 4))
        if cruise:
            group.add_waypoint(
                airport.position.point_from_heading(270, 18520),
                6000,
                speed=400,
                name="RECOVERY CRUISE",
            )
        group.land_at(airport)
        if replaced:
            replacements[name] = _native_route_value([p.dict() for p in group.points])

    description = (
        "Recovery matrix: four MQ-9s at 200 km/h. Native direct landing versus "
        "native waypoint skip; the other two start in Orbit and receive the same "
        "routes via setTask after 30 seconds. No Realistic CAS. Run for at least "
        "10 simulated minutes; diagnostics report crashes and terrain clearance."
        if replacement_matrix
        else "Native recovery control: diagnostics only, no Realistic CAS or scripted navigation. RECOVERY_DIRECT flies straight to Kobuleti landing; RECOVERY_CRUISE first flies at 6000 m to a coastal navigation point. Game Master only. Watch for a crash in the first 10 simulated minutes; continue until the cruise control reaches the coast if possible. See AFAC_RECOVERY_CONTROL in dcs.log."
    )
    trigger = TriggerStart(comment="Native mountain recovery controls, no AFAC")
    diagnostics = """
trigger.action.outText(__DESCRIPTION__,45)
local records={}
for _,name in ipairs(__NAMES__)do
  local group=Group.getByName(name)
  records[#records+1]={name=name,unit=group:getUnits()[1]:getName()}
end
local replacements=__REPLACEMENTS__
timer.scheduleFunction(function()
  for name,points in pairs(replacements)do
    local group=Group.getByName(name)
    local p=group:getUnits()[1]:getPoint()
    for i=1,#points-1 do
      points[i]={x=p.x,y=p.z,alt=p.y,alt_type='BARO',speed=200/3.6,
        speed_locked=true,ETA_locked=false,type='Turning Point',action='Turning Point',
        properties={vnav=1,scale=0,angle=0,vangle=0,steer=2},
        task={id='ComboTask',params={tasks={}}}}
    end
    if #points>2 then
      points[1].task.params.tasks[1]={number=1,auto=false,enabled=true,id='WrappedAction',
        params={action={id='SwitchWaypoint',params={fromWaypointIndex=1,goToWaypointIndex=#points}}}}
    end
    group:getController():setTask({id='Mission',params={airborne=true,route={points=points}}})
    env.info('AFAC_RECOVERY_CONTROL|REPLACED|t='..timer.getTime()..'|case='..name..'|alt='..p.y..'|x='..p.x..'|z='..p.z)
  end
end,nil,timer.getTime()+30)
local events={}
for _,key in ipairs({'S_EVENT_LAND','S_EVENT_CRASH','S_EVENT_DEAD','S_EVENT_UNIT_LOST'})do
  if world.event[key] then events[world.event[key]]=key end
end
local handler={}
function handler:onEvent(event)
  if not event or not events[event.id] then return end
  local ok,name=pcall(function()return event.initiator:getName()end)
  for _,row in ipairs(records)do
    if ok and row.unit==name then
      env.info('AFAC_RECOVERY_CONTROL|EVENT|t='..timer.getTime()..'|case='..row.name..'|event='..events[event.id])
      trigger.action.outText(row.name..': '..events[event.id],20)
    end
  end
end
world.addEventHandler(handler)
timer.scheduleFunction(function(_,now)
  for _,row in ipairs(records)do
    local unit=Unit.getByName(row.unit)
    if unit and unit:isExist() then
      local p=unit:getPoint();local v=unit:getVelocity()
      local h=land.getHeight({x=p.x,y=p.z})
      env.info('AFAC_RECOVERY_CONTROL|t='..now..'|case='..row.name..'|x='..p.x..'|z='..p.z..'|alt='..p.y..'|AGL='..(p.y-h)..'|terrain='..h..'|verticalSpeed='..v.y..'|groundSpeed='..math.sqrt(v.x*v.x+v.z*v.z)..'|fuel='..unit:getFuel()..'|inAir='..tostring(unit:inAir()))
    elseif not row.missing then
      row.missing=true
      env.info('AFAC_RECOVERY_CONTROL|UNAVAILABLE|t='..now..'|case='..row.name)
    end
  end
  return now<3600 and now+5 or nil
end,nil,timer.getTime()+1)
timer.scheduleFunction(function()
  trigger.action.outText('Recovery control: 10 simulated minutes completed. The early mountain crossing is recorded; the mission can be ended, or continued to check landing.',45)
end,nil,timer.getTime()+600)
"""
    diagnostics = (
        diagnostics.replace("__DESCRIPTION__", lua_literal(description))
        .replace("__NAMES__", lua_literal([name for name, _, _ in cases]))
        .replace("__REPLACEMENTS__", lua_literal(replacements))
    )
    trigger.add_action(DoScript(String(diagnostics)))
    mission.triggerrules.triggers.append(trigger)
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replacement-matrix", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new mission filename")
    build_mission(replacement_matrix=args.replacement_matrix).save(args.output)
    print(args.output)
