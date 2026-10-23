"""Build a Game Master AFAC search, marking, Bingo and station-duration probe."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from tempfile import TemporaryDirectory
from typing import Any

from dcs import Mission
from dcs.action import DoScript
from dcs.helicopters import UH_1H
from dcs.planes import MQ_9_Reaper, Yak_52
from dcs.task import OptROE
from dcs.triggers import TriggerStart
from dcs.translation import String
from dcs.vehicles import AirDefence, Unarmed

from game import persistency
from game.ato import FlightType
from game.ato.flightplans.afac import AfacFlightPlan
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.ato.flightplans.uizonedisplay import UiZone
from game.dcs.aircrafttype import AircraftType
from game.dcs.skills import CADET_SKILL
from game.missiongenerator.aircraft.aircraftbehavior import AircraftBehavior
from game.missiongenerator.aircraft.waypoints.afac import AfacSearchBuilder
from game.missiongenerator.luagenerator import LuaGenerator
from game.missiongenerator.realisticcascampaign import prepare_campaign, inject_campaign
from game.missiongenerator.realisticcasluadata import lua_literal
from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
from game.utils import meters, nautical_miles


def build_mission(
    *,
    night: bool = False,
    safety: bool = False,
    cloudy: bool = False,
    quick: bool = False,
) -> Mission:
    if quick and not safety:
        raise ValueError("The quick probe requires safety cases")
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 0 if night else 12)
    mission.groundControl.blue_game_masters = 1
    airport = mission.terrain.airports["Kobuleti"]
    airport.set_coalition("blue")
    if cloudy:
        mission.weather.clouds_preset = None
        mission.weather.clouds_base = 2000
        mission.weather.clouds_thickness = 1000
        mission.weather.clouds_density = 8
    settings = Settings()
    settings.plugins.update(
        {
            "realisticcas": True,
            "realisticcas.afacEnabled": True,
            "realisticcas.afacStationMinutes": 3 if quick else (8 if safety else 2),
            "realisticcas.afacMarkMinutes": 1,
            "realisticcas.probabilisticDetection": False,
            "realisticcas.acquisitionSeconds": 3,
            "realisticcas.debug": True,
        }
    )
    settings.live_pilots_enabled = False
    settings.ai_unlimited_fuel = False
    settings.cas_engagement_range_distance = 10 if safety else 4
    settings.armed_recon_engagement_range_distance = 10 if safety else 4
    game: Any = NS(
        settings=settings,
        theater=NS(
            timezone=timezone(timedelta(hours=4)),
            reference_position=NS(lat=41.9, lng=41.86),
        ),
    )
    flights, mappings, theater_objects = [], {}, {}
    cases = (
        (UH_1H, "UH-1H Iroquois", FlightType.AFAC_AREA, False),
        (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_FRONTLINE, False),
        (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_AREA, True),
        (Yak_52, "Yak-52", FlightType.AFAC_AREA, False),
    )
    if safety:
        cases = (
            (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_AREA, False),
            (UH_1H, "UH-1H Iroquois", FlightType.AFAC_AREA, False),
            (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_AREA, False),
            (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_AREA, False),
        )
    for index, (native, variant, task, bingo) in enumerate(cases):
        center = airport.position.point_from_heading(
            0, 6000 + index * (40000 if safety else 12000)
        )
        start, end = center.point_from_heading(270, 2000), center.point_from_heading(
            90, 2000
        )
        name = "AFAC_" + ("BINGO" if bingo else task.name + "_" + native.id)
        if safety:
            name += f"_SAFETY_{index}"
        aircraft = AircraftType.named(variant)
        altitude = 1000 if aircraft.helicopter else (3500 if safety else 2500)
        group = mission.flight_group_inflight(
            mission.country("USA"),
            name,
            native,
            start.point_from_heading(270, 13000 if safety and not quick else 600),
            altitude,
            speed=200,
        )
        group.units[0].fuel = native.fuel_max * (0.15 if bingo else 0.9)
        if native is UH_1H:
            group.units[0].load_pylon(UH_1H.Pylon5.XM158_M156)
        logical = (
            WaypointBuilder.race_track_start(start, meters(altitude)),
            WaypointBuilder.race_track_end(end, meters(altitude)),
        )
        layout: Any = NS(patrol_start=logical[0], patrol_end=logical[1])
        squadron = NS(
            settings=settings,
            coalition=NS(game=game),
            pilot_skill=lambda _: CADET_SKILL,
        )
        flight: Any = NS(
            flight_type=task,
            unit_type=aircraft,
            is_helo=aircraft.helicopter,
            client_count=0,
            package=NS(),
            state=NS(is_at_ip=False, in_combat=False),
            squadron=squadron,
            coalition=NS(game=game),
        )
        flight.flight_plan = AfacFlightPlan(flight, layout)
        AircraftBehavior(task, NS()).apply_to(flight, group)
        anchor = group.add_waypoint(
            start, altitude, speed=200, name="AFAC SEARCH START"
        )
        AfacSearchBuilder(
            logical[0], group, flight, mission, mission.start_time, NS()
        ).add_tasks(anchor)
        group.add_waypoint(end, altitude, speed=200, name="AFAC SEARCH END")
        group.land_at(airport)
        zone = flight.flight_plan.ui_zone()
        if safety and index == 2:
            zone = UiZone([center], nautical_miles(2))
        flights.append(
            NS(
                flight_type=task,
                units=group.units,
                squadron=squadron,
                work_zone=zone,
                group_name=name,
            )
        )
        mappings[group.units[0].name] = NS(pilot=object(), flight=flight)
        target_group = mission.vehicle_group(
            mission.country("Russia"),
            "AFAC_TARGET_" + str(index),
            Unarmed.Ural_375,
            center,
            group_size=2,
        )
        target_group.add_waypoint(center.point_from_heading(90, 1200), speed=12)
        if safety:
            kind = (
                AirDefence.ZSU_57_2,
                AirDefence.Soldier_stinger,
                AirDefence.Osa_9A33_ln,
                AirDefence.ZSU_57_2,
            )[index]
            defence = mission.vehicle_group(
                mission.country("Russia"), f"AFAC_AA_{index}", kind, center
            )
            defence.points[0].add_task(OptROE(OptROE.Values.WeaponHold))
            if index != 3:
                theater_objects[defence.units[0].name] = NS(
                    theater_unit=NS(
                        ground_object=NS(category="aa", name=f"PROBE_AA_{index}")
                    )
                )
    data = NS(flights=flights, jtacs=[], tic_groups=[])
    mapping: Any = NS(theater_objects=theater_objects, flight=mappings.get)
    plugin = LuaPlugin.from_json(
        "realisticcas", Path("resources/plugins/realisticcas/plugin.json")
    )
    assert plugin is not None
    plugin.set_settings(settings)
    generator = LuaGenerator(game, mission, data, mapping)
    config = prepare_campaign(generator, [plugin])
    setattr(mission, "_afac_probe_config", config)
    inject_campaign(generator, config)
    trigger = TriggerStart(comment="AFAC probe diagnostics")
    trigger.add_action(DoScript(String("""
trigger.action.outText('AFAC marking probe: Game Master only. Huey has 7 smoke rounds; Huey and MQ-9 lase observed moving trucks with code 1688, plus IR at night. Marks last at most 1 minute; station ends at 2 minutes. BINGO returns early, Yak only searches. No AFAC should attack. See RCAS_AFAC_PROBE and REALISTIC_CAS_AFAC in dcs.log.',30)
timer.scheduleFunction(function(_,now)
  local credits=afac_discoveries or {}
  env.info('RCAS_AFAC_PROBE|t='..now..'|discoveries='..#credits)
  for _,row in ipairs(credits) do
    env.info('RCAS_AFAC_PROBE|credit='..row.observer..'|group='..row.group..'|side='..row.coalition)
  end
  for _,row in ipairs(afac_marks or {}) do
    env.info('RCAS_AFAC_PROBE|marked='..row.observer..'|group='..row.group..'|laser='..tostring(row.laser)..'|ir='..tostring(row.infrared)..'|smoke='..tostring(row.smoke))
  end
  return now<600 and now+10 or nil
end,nil,timer.getTime()+10)
""")))
    if not safety:
        mission.triggerrules.triggers.append(trigger)
    if safety:
        units = lua_literal(
            [{"unit": f.units[0].name, "group": f.group_name} for f in flights]
        )
        recovery = lua_literal({"x": airport.position.x, "z": airport.position.y})
        diagnostics = (
            """
trigger.action.outText('AFAC avoidance probe: Game Master only. Case 0: known ZSU-57-2, climb if the native aircraft ceiling permits. Case 1: known Stinger, horizontal standoff. Case 2: SA-8 covers the small zone, abort. Case 3: hidden ZSU, no avoidance before discovery. Defences hold fire so manoeuvres can be observed. Station: __MINUTES__ minutes. The quick case starts close to the search orbit; check climb onset and physical RTB after 5 minutes, not full recovery. See AFAC_SAFETY_PROBE and REALISTIC_CAS_AFAC_NAV in dcs.log.',45)
local cases=__CASES__
local recovery=__RECOVERY__
local departureAnnounced=false
local tracked={}
local outcomesReported=false
for index,row in ipairs(cases)do tracked[row.unit]=index-1 end
local eventNames={}
for _,key in ipairs({'S_EVENT_LAND','S_EVENT_CRASH','S_EVENT_DEAD','S_EVENT_UNIT_LOST'})do
  if world.event[key] then eventNames[world.event[key]]=key end
end
local handler={}
function handler:onEvent(event)
  if not event or not eventNames[event.id] then return end
  local ok,name=pcall(function()return event.initiator:getName()end)
  if ok and tracked[name]~=nil then
    env.info('AFAC_SAFETY_PROBE|EVENT|t='..timer.getTime()..'|case='..tracked[name]..'|event='..eventNames[event.id]..'|unit='..name)
    local row=cases[tracked[name]+1]
    if row.outcome then return end
    row.outcome=event.id==world.event.S_EVENT_LAND and 'landed' or 'lost'
    local landed,lost=0,0
    for _,entry in ipairs(cases)do
      if entry.outcome=='landed' then landed=landed+1 end
      if entry.outcome=='lost' then lost=lost+1 end
    end
    trigger.action.outText('AFAC probe: '..landed..'/'..#cases..' landed, '..lost..' lost. Case '..tracked[name]..': '..eventNames[event.id],30)
    if landed+lost==#cases and not outcomesReported then
      outcomesReported=true
      env.info('AFAC_SAFETY_PROBE|RECOVERY_COMPLETE|t='..timer.getTime()..'|landed='..landed..'|lost='..lost)
      trigger.action.outText('AFAC PROBE FINISHED: '..landed..'/'..#cases..' landed, '..lost..' lost. Recovery results are recorded; the mission can now be ended.',120)
    end
  end
end
world.addEventHandler(handler)
timer.scheduleFunction(function(_,now)
  local allDeparted=true
  for index,row in ipairs(cases)do
    local nav=(RealisticCAS.afacNavigation or {})[row.group]
    if not nav or not nav.exitWaypoint then allDeparted=false end
    local u=Unit.getByName(row.unit)
    if u and u:isExist()then
      local p=u:getPoint();local d=u:getDesc()
      local terrain=land.getHeight({x=p.x,y=p.z})
      local velocity=u:getVelocity()
      local dx,dz=recovery.x-p.x,recovery.z-p.z
      local distance=math.sqrt(dx*dx+dz*dz)
      local closing=distance>0 and (velocity.x*dx+velocity.z*dz)/distance or 0
      env.info('AFAC_SAFETY_PROBE|t='..now..'|case='..(index-1)..'|alt='..p.y..'|x='..p.x..'|z='..p.z..'|Hmax='..tostring(d.Hmax)..'|fuel='..u:getFuel()..'|revision='..tostring(nav and nav.revision)..'|abort='..tostring((RealisticCAS.afacAbort or {})[row.group])..'|active='..tostring(nav and nav.active)..'|finished='..tostring(nav and nav.finished)..'|nextPoint='..tostring(nav and nav.nextPoint)..'|requestedAltitude='..tostring(nav and nav.altitude)..'|stationStart='..tostring((RealisticCAS.afacStations or {})[row.group])..'|return='..tostring((RealisticCAS.afacReturn or {})[row.group])..'|exitWaypoint='..tostring(nav and nav.exitWaypoint)..'|inAir='..tostring(u:inAir())..'|recoveryDistance='..distance..'|closingSpeed='..closing..'|verticalSpeed='..velocity.y..'|terrain='..terrain..'|AGL='..(p.y-terrain))
    elseif not row.unavailableLogged then
      row.unavailableLogged=true
      env.info('AFAC_SAFETY_PROBE|UNAVAILABLE|t='..now..'|case='..(index-1)..'|unit='..row.unit)
    end
  end
  if allDeparted and not departureAnnounced then
    departureAnnounced=true
    trigger.action.outText('AFAC probe: exit orders have been issued to all four groups. Verify that they leave their search orbits and follow their recovery routes; physical return still needs confirmation.',30)
    env.info('AFAC_SAFETY_PROBE|EXIT_ORDERS_COMPLETE|t='..now)
  end
  return now<3600 and now+10 or nil
end,nil,timer.getTime()+5)
""".replace("__CASES__", units)
            .replace("__RECOVERY__", recovery)
            .replace("__MINUTES__", "3" if quick else "8")
        )
        probe = TriggerStart(comment="AFAC avoidance diagnostics")
        probe.add_action(DoScript(String(diagnostics)))
        mission.triggerrules.triggers.append(probe)
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--night", action="store_true")
    parser.add_argument("--safety", action="store_true")
    parser.add_argument("--cloudy", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new mission filename")
    with TemporaryDirectory(prefix="afac-probe-") as profile:
        persistency.setup(profile, False, 0)
        build_mission(
            night=args.night, safety=args.safety, cloudy=args.cloudy, quick=args.quick
        ).save(args.output)
    print(args.output)
