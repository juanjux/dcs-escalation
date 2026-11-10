"""Sequential stock-unit matrix for native ground-controller knowledge behavior."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript, DoScriptFile
from dcs.condition import TimeAfter
from dcs.task import OptAlarmState, OptROE, SetImmortalCommand, SetInvisibleCommand
from dcs.translation import String
from dcs.triggers import TriggerOnce
from dcs.vehicles import Armor, Unarmed

from game.missiongenerator.realisticcasluadata import lua_literal

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1] / "resources/plugins/realisticcas"
METHODS = (
    "CONTROL",
    "PRODUCTION",
    "UNIT_ONCE",
    "GROUP_ONCE",
    "UNIT_REFRESH",
    "GROUP_REFRESH",
)
ISOLATION_CASES = (
    ("CLEAR_CONTROL", "CONTROL", False),
    ("FOG_CONTROL", "CONTROL", True),
    ("FOG_PRODUCTION", "PRODUCTION", True),
    ("FOG_UNIT_REFRESH", "UNIT_REFRESH", True),
    ("FOG_GROUP_REFRESH", "GROUP_REFRESH", True),
)


def build_mission(*, sensor_isolation: bool = False) -> Mission:
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 12)
    mission.groundControl.blue_game_masters = 1
    mission.groundControl.red_game_masters = 1
    mission.weather.wind_at_ground.speed = 0
    mission.weather.enable_fog = False
    # Runtime fog is clamped below the cloud base. Keep that limit above the
    # isolation layer, with no automatic weather changes during the sequence.
    mission.weather.auto_fog = False
    mission.weather.clouds_preset = None
    mission.weather.clouds_base = 3000
    mission.weather.clouds_density = 0
    config: dict = {
        "cases": [],
        "duration": 240,
        "ttl": 80,
        "refresh": 5,
        "version": 3 if sensor_isolation else 2,
        "sensorIsolation": sensor_isolation,
        "fogThickness": 1000,
        "fogVisibility": 100,
    }
    cases = (
        ISOLATION_CASES
        if sensor_isolation
        else tuple((method, method, False) for method in METHODS)
    )
    # This exact ray allowed the BLUE_CONTROL tank to fire in the first probe.
    # Only one late-activated pair exists at a time, so every case uses the same
    # terrain, target bearing and range without other targets or physical overlap.
    center = mission.terrain.airports["Senaki-Kolkhi"].position.point_from_heading(
        180, 13000
    )
    for side in (2, 1):
        for suffix, method, dense_fog in cases:
            label = ("BLUE_" if side == 2 else "RED_") + suffix
            country = mission.country("USA" if side == 2 else "Russia")
            enemy = mission.country("Russia" if side == 2 else "USA")
            receiver = mission.vehicle_group(
                country,
                label,
                Armor.M_1_Abrams if side == 2 else Armor.T_72B,
                center,
                heading=90,
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
            # The test owns this initial concealment. The adapter continues the
            # same ownership after the activation waypoint has executed.
            target.points[0].add_task(SetInvisibleCommand(True))
            for group in (receiver, target):
                group.late_activation = True
                group.points[0].ETA_locked = True
                group.points[0].ETA = 0
            config["cases"].append(
                {
                    "label": label,
                    "method": method,
                    "denseFog": dense_fog,
                    "scenario": suffix,
                    "receiver": receiver.units[0].name,
                    "receiverGroup": receiver.name,
                    "name": target.units[0].name,
                    "groupName": target.name,
                    "coalition": 1 if side == 2 else 2,
                    "side": side,
                }
            )
    for name in ("core.lua", "ground-intel.lua", "dcs.lua"):
        trigger = TriggerOnce(comment="Ground controller matrix: " + name)
        trigger.add_condition(TimeAfter(2))
        trigger.add_action(
            DoScriptFile(mission.map_resource.add_resource_file(PLUGIN / name))
        )
        mission.triggerrules.triggers.append(trigger)
    source = (HERE / "ground_intel_controller_probe.lua").read_text("utf-8")
    source = source.replace("__CONFIG__", lua_literal(config))
    trigger = TriggerOnce(comment="Ground controller matrix: automatic sequence")
    trigger.add_condition(TimeAfter(3))
    trigger.add_action(DoScript(String(source)))
    mission.triggerrules.triggers.append(trigger)
    mission.description_text = (
        "Ground intel V3: ten sequential cases, five per side. Clear and dense-fog "
        "controls are compared with production sharing and repeated direct "
        "unit/group knowledge calls. Native fog must prevent the no-intel control "
        "from acquiring the target; otherwise that side is INCONCLUSIVE. Clear "
        "controls must acquire and fire to validate the geometry and weapons. "
        "Knowledge and engagement effects are reported separately, not inferred "
        "from successful API calls. One active tank and one immortal unarmed "
        "target at a time, at 1200 metres on the same terrain ray. Each case "
        "lasts four simulated minutes; total about 41 minutes. Time acceleration "
        "is allowed. No player orders or aircraft modules needed. Wait for "
        "GROUND INTEL V3 COMPLETE. Raw native returns, actual fog settings, "
        "shots and expiry samples are logged under GROUND_INTEL_V3 in dcs.log. "
        "Observations at 20/150 seconds, TTL 80, open fire at 30, hidden movement "
        "at 120. Repeated calls never extend the contact lifetime."
        if sensor_isolation
        else "Ground intel V2: 12 sequential cases, six per side. One active tank and "
        "one immortal unarmed target at a time, always on the same 1200-metre ray. "
        "CONTROL, production adapter, direct unit/group controller calls, and "
        "unit/group calls refreshed every five seconds while the contact is valid. "
        "Each case lasts four simulated minutes. Total about 49 simulated minutes; "
        "time acceleration is allowed. No player orders or aircraft modules needed. "
        "Wait for GROUND INTEL V2 COMPLETE. All cases, raw native API returns, "
        "shots and expiry samples are logged under GROUND_INTEL_V2 in dcs.log. "
        "Observations at 20/150 seconds, TTL 80, open fire at 30, hidden movement "
        "at 120. Repeated diagnostic calls never extend the contact lifetime."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing mission")
    build_mission().save(args.output)
    Mission().load_file(str(args.output))
    print(args.output)
