"""Stock-unit native ground-intelligence A/B and concealment probe, AI only."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript, DoScriptFile
from dcs.task import OptAlarmState, OptROE, SetImmortalCommand
from dcs.translation import String
from dcs.triggers import TriggerOnce
from dcs.condition import TimeAfter
from dcs.vehicles import Armor, Unarmed

from game.missiongenerator.realisticcasluadata import lua_literal

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1] / "resources/plugins/realisticcas"


def build_mission() -> Mission:
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 12)
    mission.groundControl.blue_game_masters = 1
    mission.groundControl.red_game_masters = 1
    mission.weather.wind_at_ground.speed = 0
    mission.weather.enable_fog = False
    config: dict = {"cases": [], "groups": [], "targets": [], "observers": []}
    airport = mission.terrain.airports["Senaki-Kolkhi"]
    for index, (side, shared) in enumerate(
        ((2, True), (2, False), (1, True), (1, False))
    ):
        label = ("BLUE" if side == 2 else "RED") + ("_SHARED" if shared else "_CONTROL")
        country = mission.country("USA" if side == 2 else "Russia")
        enemy = mission.country("Russia" if side == 2 else "USA")
        center = airport.position.point_from_heading(180, 5000 + index * 8000)
        receiver = mission.vehicle_group(
            country,
            label,
            Armor.M_1_Abrams if side == 2 else Armor.T_72B,
            center,
        )
        receiver.points[0].add_task(OptROE(OptROE.Values.WeaponHold))
        receiver.points[0].add_task(OptAlarmState(2))
        target = mission.vehicle_group(
            enemy,
            label + "_TARGET",
            Unarmed.Ural_375,
            center.point_from_heading(90, 1200),
        )
        target.points[0].add_task(OptROE(OptROE.Values.WeaponHold))
        target.points[0].add_task(SetImmortalCommand(True))
        unit = target.units[0]
        meta = {
            "name": unit.name,
            "groupName": target.name,
            "coalition": 1 if side == 2 else 2,
        }
        config["groups"].append({"name": target.name, "originalInvisible": False})
        config["targets"].append(meta)
        if shared:
            config["observers"].append(
                {
                    "name": receiver.units[0].name,
                    "category": "ground",
                    "coalition": side,
                }
            )
        config["cases"].append(
            dict(
                meta,
                label=label,
                receiver=receiver.units[0].name,
                receiverGroup=receiver.name,
                side=side,
                shared=shared,
            )
        )
    for name in ("core.lua", "ground-intel.lua", "dcs.lua"):
        trigger = TriggerOnce(comment="Ground intel probe: " + name)
        trigger.add_condition(TimeAfter(2))
        trigger.add_action(
            DoScriptFile(mission.map_resource.add_resource_file(PLUGIN / name))
        )
        mission.triggerrules.triggers.append(trigger)
    source = (HERE / "ground_intel_probe.lua").read_text("utf-8")
    source = source.replace("__CONFIG__", lua_literal(config))
    trigger = TriggerOnce(comment="Ground intel probe: automatic phases")
    trigger.add_condition(TimeAfter(3))
    trigger.add_action(DoScript(String(source)))
    mission.triggerrules.triggers.append(trigger)
    mission.description_text = (
        "Ground intelligence A/B probe, stock units, AI only. Do not issue orders. "
        "Run until GROUND INTEL PROBE COMPLETE (240 simulated seconds). "
        "Real contact sharing versus unnotified control tanks on both sides. "
        "Scripted observations at 20 and 140 seconds; contacts last 40 seconds. "
        "Targets move while concealed. Immortal, unarmed trucks preserve the memory test. "
        "Native visibility, target-memory and firing observations are recorded in dcs.log "
        "under GROUND_INTEL_PROBE. No campaign or save is loaded or modified."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing mission")
    build_mission().save(args.output)
    reopened = Mission()
    reopened.load_file(str(args.output))
    print(args.output)
