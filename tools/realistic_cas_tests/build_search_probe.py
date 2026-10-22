"""Standalone Cobra route probe with a controlled initially invisible target."""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

from dcs import Mission
from dcs.action import DoScript
from dcs.helicopters import AH_1W
from dcs.task import CAS, EngageTargetsInZone, Targets
from dcs.translation import String
from dcs.triggers import TriggerStart
from dcs.unit import Skill
from dcs.vehicles import Unarmed

from game.ato import FlightType
from game.missiongenerator.aircraft.searchpattern import add_search_pattern
from game.utils import nautical_miles


def build_mission() -> Mission:
    mission = Mission()
    now = datetime(2026, 6, 1, 12)
    mission.start_time = now
    airport = mission.terrain.airports["Batumi"]
    airport.set_coalition("blue")
    blue, red = mission.country("USA"), mission.country("Russia")
    mission.groundControl.blue_game_masters = 1
    cases = (
        (FlightType.CAS, False),
        (FlightType.ARMED_RECON, False),
        (FlightType.CAS, True),
        (FlightType.ARMED_RECON, True),
    )
    for index, (role, control) in enumerate(cases):
        center = (
            mission.terrain.airports["Kobuleti"]
            .position.point_from_heading(0, 1500 + index * 8000)
            .point_from_heading(90, 1000)
        )
        name = f"SEARCH_{'CONTROL' if control else 'PROBE'}_{role.name}"
        group = mission.flight_group_inflight(
            blue,
            name,
            AH_1W,
            center.point_from_heading(270, 700),
            1000,
            speed=180,
            maintask=CAS,
        )
        group.units[0].skill = Skill.Excellent
        group.load_task_default_loadout(CAS)
        # AircraftBehavior.configure_behavior does this in campaign generation.
        # Leaving pydcs' generic CAS order here bypasses the assigned target zone.
        group.points[0].tasks.clear()
        logical = object()
        anchor = group.add_waypoint(center, 300, speed=180, name="SEARCH AREA")
        anchor.alt_type = "RADIO"
        anchor.add_task(EngageTargetsInZone(center, 2000, [Targets.All.GroundUnits]))
        group.land_at(airport)
        plan = NS(
            layout=NS(patrol_start=logical),
            tot_waypoint=logical,
            tot=now,
            patrol_end_time=now + timedelta(minutes=12),
            ui_zone=lambda center=center: NS(points=[center], radius=nautical_miles(1)),
        )
        flight = NS(
            client_count=0,
            is_helo=True,
            flight_type=role,
            flight_plan=plan,
            coalition=NS(
                game=NS(settings=NS(plugins={"realisticcas": True})),
                doctrine=NS(cas_duration=timedelta(minutes=12)),
            ),
        )
        add_search_pattern(flight, group, now, [(logical, anchor)])
        if control:
            # Matched geometry and engagement, but no scripted navigation at all.
            # An unrolled route lasts longer than the observation window.
            corners = group.points[2:6]
            for corner in corners:
                corner.tasks.clear()
            group.points[2:6] = [deepcopy(p) for _ in range(16) for p in corners]
        mission.vehicle_group(red, f"SEARCH_TARGET_{index}", Unarmed.Ural_375, center)
    script = """
local names={'SEARCH_PROBE_CAS','SEARCH_PROBE_ARMED_RECON',
    'SEARCH_CONTROL_CAS','SEARCH_CONTROL_ARMED_RECON'}
for i=0,3 do
    Group.getByName('SEARCH_TARGET_'..i):getController():setCommand({id='SetInvisible',params={value=true}})
end
local previous={}
local revealed=false
local handler={}
function handler:onEvent(event)
    if event.id~=world.event.S_EVENT_SHOT and event.id~=world.event.S_EVENT_HIT
        and event.id~=world.event.S_EVENT_DEAD then return end
    local u=event.initiator
    local name=u and u:getName() or '?'
    local target=event.target and event.target:getName() or '?'
    env.info(string.format('REALISTIC_CAS_SEARCH_PROBE|event=%s t=%.1f initiator=%s target=%s',
        event.id,event.time or timer.getTime(),name,target))
end
world.addEventHandler(handler)
timer.scheduleFunction(function(_,now)
    local text='COBRA SEARCH PROBE: targets hidden until t=180'
    for _,name in ipairs(names) do
        local g=Group.getByName(name)
        local u=g and g:getUnit(1)
        if u and u:isExist() then
            local p=u:getPoint()
            local old=previous[name] or p
            local moved=math.sqrt((p.x-old.x)^2+(p.z-old.z)^2)
            local velocity=u:getVelocity()
            local speed=math.sqrt(velocity.x^2+velocity.y^2+velocity.z^2)
            local contacts=#g:getController():getDetectedTargets()
            local agl=p.y-land.getHeight({x=p.x,y=p.z})
            local line=string.format('%s t=%.0f moved=%.0fm speed=%.1fm/s AGL=%.0fm fuel=%.1f%% contacts=%d',
                name,now,moved,speed,agl,u:getFuel()*100,contacts)
            env.info('REALISTIC_CAS_SEARCH_PROBE|'..line)
            text=text..'\\n'..line
            previous[name]=p
        end
    end
    if now>=180 and not revealed then
        for i=0,3 do
            Group.getByName('SEARCH_TARGET_'..i):getController():setCommand({id='SetInvisible',params={value=false}})
        end
        revealed=true
        env.info('REALISTIC_CAS_SEARCH_PROBE|targets now visible')
    end
    if revealed then
        for i=0,3 do
            local g=Group.getByName('SEARCH_TARGET_'..i)
            local u=g and g:getUnit(1)
            env.info(string.format('REALISTIC_CAS_SEARCH_PROBE|target=%d life=%.1f',
                i,u and u:isExist() and u:getLife() or 0))
        end
    end
    trigger.action.outText(text,14)
    return now+15
end,nil,timer.getTime()+15)
"""
    trigger = TriggerStart(comment="Controlled hidden-target search test")
    trigger.add_action(DoScript(String(script)))
    mission.triggerrules.triggers.append(trigger)
    mission.set_description_text(
        "COBRA SEARCH ROUTE PROBE — NO CAMPAIGN\n"
        "Join the blue Game Master slot; no player aircraft is needed. "
        "V2: watch four AI Cobras on F10. Targets are invisible for three minutes, "
        "then revealed. PROBE flights use the revised search loop; CONTROL flights "
        "fly the same geometry as a long ordinary route, without waypoint switches. "
        "Areas are 8 km apart to avoid overlapping engagement zones. Observe for "
        "15 minutes: which flights stop, fire, destroy their target and resume? "
        "PROBE flights should exit after 12 minutes or below 20% fuel. CONTROL routes "
        "last longer by design. Speed, AGL, native contact counts, shots, hits, deaths "
        "and route switches are logged. This tests native AI, not plugin detection."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_mission().save(args.output)
    print(args.output)
