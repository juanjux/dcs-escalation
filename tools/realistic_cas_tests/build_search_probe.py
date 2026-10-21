"""Standalone Cobra route probe with a controlled initially invisible target."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

from dcs import Mission
from dcs.action import DoScript
from dcs.helicopters import AH_1W
from dcs.mission import StartType
from dcs.planes import A_10C_2
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
    player = mission.flight_group_from_airport(
        blue, "Probe player", A_10C_2, airport, start_type=StartType.Warm
    )
    player.units[0].skill = Skill.Player
    names = []
    for index, role in enumerate((FlightType.CAS, FlightType.ARMED_RECON)):
        center = (
            mission.terrain.airports["Kobuleti"]
            .position.point_from_heading(0, 1500 + index * 3500)
            .point_from_heading(90, 1000)
        )
        name = f"SEARCH_PROBE_{role.name}"
        names.append(name)
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
        logical = object()
        anchor = group.add_waypoint(center, 300, speed=180, name="SEARCH AREA")
        anchor.alt_type = "RADIO"
        anchor.add_task(EngageTargetsInZone(center, 2000, [Targets.All.GroundUnits]))
        group.land_at(airport)
        plan = NS(
            layout=NS(patrol_start=logical),
            tot_waypoint=logical,
            tot=now,
            patrol_end_time=now + timedelta(minutes=6),
            ui_zone=lambda center=center: NS(points=[center], radius=nautical_miles(1)),
        )
        flight = NS(
            client_count=0,
            is_helo=True,
            flight_type=role,
            flight_plan=plan,
            coalition=NS(
                game=NS(settings=NS(plugins={"realisticcas": True})),
                doctrine=NS(cas_duration=timedelta(minutes=6)),
            ),
        )
        add_search_pattern(flight, group, now, [(logical, anchor)])
        mission.vehicle_group(red, f"SEARCH_TARGET_{index}", Unarmed.Ural_375, center)
    script = """
local names={'SEARCH_PROBE_CAS','SEARCH_PROBE_ARMED_RECON'}
for i=0,1 do
    Group.getByName('SEARCH_TARGET_'..i):getController():setCommand({id='SetInvisible',params={value=true}})
end
local previous={}
local revealed=false
timer.scheduleFunction(function(_,now)
    local text='COBRA SEARCH PROBE: targets hidden until t=180'
    for _,name in ipairs(names) do
        local g=Group.getByName(name)
        local u=g and g:getUnit(1)
        if u and u:isExist() then
            local p=u:getPoint()
            local old=previous[name] or p
            local moved=math.sqrt((p.x-old.x)^2+(p.z-old.z)^2)
            local line=string.format('%s t=%.0f moved=%.0fm fuel=%.1f%%',name,now,moved,u:getFuel()*100)
            env.info('REALISTIC_CAS_SEARCH_PROBE|'..line)
            text=text..'\\n'..line
            previous[name]=p
        end
    end
    if now>=180 and not revealed then
        for i=0,1 do
            Group.getByName('SEARCH_TARGET_'..i):getController():setCommand({id='SetInvisible',params={value=false}})
        end
        revealed=true
        env.info('REALISTIC_CAS_SEARCH_PROBE|targets now visible')
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
        "Unpause and watch the two AI Cobras on F10. Targets are deliberately invisible "
        "for three minutes, then revealed. Movement is logged every 15 seconds. "
        "Both flights should keep moving, engage when able, and exit after six minutes "
        "or below 20% fuel. This isolates native route behavior, not detection probabilities."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_mission().save(args.output)
    print(args.output)
