"""Isolate native mountain recovery from AFAC scripts and task replacement."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript
from dcs.mapping import Point
from dcs.planes import MQ_9_Reaper
from dcs.task import Nothing, OptROE
from dcs.translation import String
from dcs.triggers import TriggerStart


def build_mission() -> Mission:
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
    for cruise, name in ((False, "RECOVERY_DIRECT"), (True, "RECOVERY_CRUISE")):
        group = mission.flight_group_inflight(
            mission.country("USA"),
            name,
            MQ_9_Reaper,
            origin.point_from_heading(90, 500 if cruise else 0),
            3506,
            speed=400,
        )
        group.task = Nothing.name
        group.units[0].fuel = MQ_9_Reaper.fuel_max * 0.85
        group.points[0].add_task(OptROE(OptROE.Values.WeaponHold))
        if cruise:
            group.add_waypoint(
                airport.position.point_from_heading(270, 18520),
                6000,
                speed=400,
                name="RECOVERY CRUISE",
            )
        group.land_at(airport)
    trigger = TriggerStart(comment="Native mountain recovery controls, no AFAC")
    trigger.add_action(DoScript(String("""
trigger.action.outText('Native recovery control: diagnostics only, no Realistic CAS or scripted navigation. RECOVERY_DIRECT flies straight to Kobuleti landing; RECOVERY_CRUISE first flies at 6000 m to a coastal navigation point. Game Master only. Watch for a crash in the first 10 simulated minutes; continue until the cruise control reaches the coast if possible. See AFAC_RECOVERY_CONTROL in dcs.log.',45)
local records={}
for _,name in ipairs({'RECOVERY_DIRECT','RECOVERY_CRUISE'})do
  local group=Group.getByName(name)
  records[#records+1]={name=name,unit=group:getUnits()[1]:getName()}
end
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
      env.info('AFAC_RECOVERY_CONTROL|t='..now..'|case='..row.name..'|x='..p.x..'|z='..p.z..'|alt='..p.y..'|AGL='..(p.y-h)..'|terrain='..h..'|verticalSpeed='..v.y..'|fuel='..unit:getFuel()..'|inAir='..tostring(unit:inAir()))
    elseif not row.missing then
      row.missing=true
      env.info('AFAC_RECOVERY_CONTROL|UNAVAILABLE|t='..now..'|case='..row.name)
    end
  end
  return now<3600 and now+5 or nil
end,nil,timer.getTime()+1)
""")))
    mission.triggerrules.triggers.append(trigger)
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new mission filename")
    build_mission().save(args.output)
    print(args.output)
