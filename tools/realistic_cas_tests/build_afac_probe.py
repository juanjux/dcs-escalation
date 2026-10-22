"""Build a Game Master AFAC search, Bingo and station-duration probe."""

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
from dcs.triggers import TriggerStart
from dcs.translation import String
from dcs.vehicles import Unarmed

from game import persistency
from game.ato import FlightType
from game.ato.flightplans.afac import AfacFlightPlan
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.dcs.aircrafttype import AircraftType
from game.dcs.skills import CADET_SKILL
from game.missiongenerator.aircraft.aircraftbehavior import AircraftBehavior
from game.missiongenerator.aircraft.waypoints.afac import AfacSearchBuilder
from game.missiongenerator.luagenerator import LuaGenerator
from game.missiongenerator.realisticcascampaign import prepare_campaign, inject_campaign
from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
from game.utils import meters


def build_mission(*, night: bool = False) -> Mission:
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 0 if night else 12)
    mission.groundControl.blue_game_masters = 1
    airport = mission.terrain.airports["Kobuleti"]
    airport.set_coalition("blue")
    settings = Settings()
    settings.plugins.update(
        {
            "realisticcas": True,
            "realisticcas.afacEnabled": True,
            "realisticcas.afacStationMinutes": 2,
            "realisticcas.probabilisticDetection": False,
            "realisticcas.acquisitionSeconds": 3,
            "realisticcas.debug": True,
        }
    )
    settings.live_pilots_enabled = False
    settings.ai_unlimited_fuel = False
    settings.cas_engagement_range_distance = 4
    settings.armed_recon_engagement_range_distance = 4
    game: Any = NS(
        settings=settings,
        theater=NS(
            timezone=timezone(timedelta(hours=4)),
            reference_position=NS(lat=41.9, lng=41.86),
        ),
    )
    flights, mappings = [], {}
    cases = (
        (UH_1H, "UH-1H Iroquois", FlightType.AFAC_AREA, False),
        (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_FRONTLINE, False),
        (MQ_9_Reaper, "MQ-9 Reaper", FlightType.AFAC_AREA, True),
        (Yak_52, "Yak-52", FlightType.AFAC_AREA, False),
    )
    for index, (native, variant, task, bingo) in enumerate(cases):
        center = airport.position.point_from_heading(0, 6000 + index * 12000)
        start, end = center.point_from_heading(270, 2000), center.point_from_heading(
            90, 2000
        )
        name = "AFAC_" + ("BINGO" if bingo else task.name + "_" + native.id)
        aircraft = AircraftType.named(variant)
        altitude = 1000 if aircraft.helicopter else 2500
        group = mission.flight_group_inflight(
            mission.country("USA"),
            name,
            native,
            start.point_from_heading(270, 600),
            altitude,
            speed=200,
        )
        group.units[0].fuel = native.fuel_max * (0.15 if bingo else 0.9)
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
        mission.vehicle_group(
            mission.country("Russia"),
            "AFAC_TARGET_" + str(index),
            Unarmed.Ural_375,
            center,
            group_size=2,
        )
    data = NS(flights=flights, jtacs=[], tic_groups=[])
    mapping: Any = NS(theater_objects={}, flight=mappings.get)
    plugin = LuaPlugin.from_json(
        "realisticcas", Path("resources/plugins/realisticcas/plugin.json")
    )
    assert plugin is not None
    plugin.set_settings(settings)
    generator = LuaGenerator(game, mission, data, mapping)
    inject_campaign(generator, prepare_campaign(generator, [plugin]))
    trigger = TriggerStart(comment="AFAC probe diagnostics")
    trigger.add_action(DoScript(String("""
trigger.action.outText('AFAC search probe: Game Master only. Normal flights search for 2 minutes after arrival, then land at Kobuleti. BINGO should return early. No AFAC should attack. Night: Yak warns; Huey/MQ-9 retain thermal observation. See RCAS_AFAC_PROBE in dcs.log.',30)
timer.scheduleFunction(function(_,now)
  local credits=afac_discoveries or {}
  env.info('RCAS_AFAC_PROBE|t='..now..'|discoveries='..#credits)
  for _,row in ipairs(credits) do
    env.info('RCAS_AFAC_PROBE|credit='..row.observer..'|group='..row.group..'|side='..row.coalition)
  end
  return now<600 and now+10 or nil
end,nil,timer.getTime()+10)
""")))
    mission.triggerrules.triggers.append(trigger)
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--night", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new mission filename")
    with TemporaryDirectory(prefix="afac-probe-") as profile:
        persistency.setup(profile, False, 0)
        build_mission(night=args.night).save(args.output)
    print(args.output)
