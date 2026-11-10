"""Build an unattended native CAP/SAM comparison without mods or player orders."""

import argparse
import copy
import tempfile
from datetime import datetime
from pathlib import Path

from dcs import Mission
from dcs.action import DoScript, DoScriptFile
from dcs.condition import TimeAfter
from dcs.lua import dumps
from dcs.planes import B_52H, F_16C_50, Su_27, Tu_95MS
from dcs.statics import Fortification
from dcs.task import (
    CAP,
    Nothing,
    ControlledTask,
    EngageTargets,
    OptAlarmState,
    OptReactOnThreat,
    OptROE,
    OrbitAction,
    RunScript,
    SetImmortalCommand,
    Targets,
)
from dcs.translation import String
from dcs.triggers import TriggerOnce
from dcs.unit import Skill
from dcs.vehicles import AirDefence

from game.missiongenerator.imac import DEFAULTS, SCRIPTS, _array

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "resources/plugins/imac"


def build_mission() -> Mission:
    mission = Mission()
    mission.start_time = datetime(2026, 6, 1, 12)
    mission.groundControl.blue_game_masters = 1
    mission.groundControl.red_game_masters = 1
    config = {
        "options": dict(DEFAULTS, debug=True, reports=False, interceptRangeNm=20),
        "flights": [],
        "sensors": [],
        "threats": [],
        "commandCenters": [],
    }
    cases = []
    center = mission.terrain.airports["Senaki-Kolkhi"].position.point_from_heading(
        180, 13000
    )
    station = center.point_from_heading(270, 70000)
    for side in (2, 1):
        country = mission.country("USA" if side == 2 else "Russia")
        enemy = mission.country("Russia" if side == 2 else "USA")
        cc = mission.static_group(
            country,
            "BLUE_CC" if side == 2 else "RED_CC",
            Fortification._Command_Center,
            center.point_from_heading(0, 3000 + side * 1000),
        )
        config["commandCenters"].append(
            {"name": cc.units[0].name, "key": cc.name, "side": side, "power": []}
        )
        for guarded in (False, True):
            name = ("BLUE_" if side == 2 else "RED_") + (
                "GUARDED" if guarded else "CONTROL"
            )
            plane = F_16C_50 if side == 2 else Su_27
            fighter = mission.flight_group_inflight(
                country, name, plane, station, 6500, 800, CAP, group_size=2
            )
            for unit in fighter.units:
                unit.heading = 90
                unit.skill = Skill.Excellent
                unit.fuel = plane.fuel_max * 0.95
            fighter.points[0].tasks.clear()
            fighter.points[0].tasks.extend(
                [
                    SetImmortalCommand(True),
                    OptROE(OptROE.Values.OpenFire),
                    OptReactOnThreat(OptReactOnThreat.Values.NoReaction),
                ]
            )
            entry = fighter.add_waypoint(
                station.point_from_heading(90, 1000), 6500, 800, "RACETRACK START"
            )
            entry.tasks.append(EngageTargets(50 * 1852, [Targets.All.Air]))
            orbit = ControlledTask(
                OrbitAction(6500, 800, OrbitAction.OrbitPattern.RaceTrack)
            )
            orbit.stop_after_time(3600)
            entry.tasks.append(orbit)
            fighter.add_waypoint(
                station.point_from_heading(0, 10000), 6500, 800, "RACETRACK END"
            )
            fighter.add_waypoint(
                station.point_from_heading(270, 40000), 6500, 800, "ALIGN"
            )
            for index, point in enumerate(fighter.points, 1):
                point.tasks.insert(
                    0,
                    RunScript(
                        f"if EscalationIMAC then EscalationIMAC.reached({dumps(name)},{index}) end"
                    ),
                )
            config["flights"].append(
                {
                    "group": name,
                    "side": side,
                    "mode": "cap",
                    "stationStart": 2,
                    "recoveryIndex": 3,
                    "attackIndex": 4,
                    "endTime": 3600,
                    "bingo": 0.2,
                    "burnPerMeter": 0.000001,
                    "route": copy.deepcopy(_array(fighter.dict()["route"]["points"])),
                }
            )
            config["sensors"].extend(
                {"name": unit.name, "group": name, "side": side, "air": True}
                for unit in fighter.units
            )
            target_point = center.point_from_heading(90, 5000)
            bomber = mission.flight_group_inflight(
                enemy,
                name + "_BAIT",
                Tu_95MS if side == 2 else B_52H,
                target_point,
                6500,
                600,
                Nothing,
            )
            bomber.points[0].tasks.clear()
            bomber.points[0].tasks.extend(
                [SetImmortalCommand(True), OptROE(OptROE.Values.WeaponHold)]
            )
            bomber.points[0].tasks.append(
                OrbitAction(6500, 600, OrbitAction.OrbitPattern.Circle)
            )
            sam = mission.vehicle_group_platoon(
                enemy,
                name + "_SAM",
                [
                    AirDefence.SA_11_Buk_SR_9S18M1,
                    AirDefence.SA_11_Buk_CC_9S470M1,
                    AirDefence.SA_11_Buk_LN_9A310M1,
                    AirDefence.SA_11_Buk_LN_9A310M1,
                ],
                center,
            )
            sam.points[0].tasks.extend(
                [OptAlarmState(2), OptROE(OptROE.Values.OpenFire)]
            )
            config["threats"].append(
                {
                    "name": sam.units[2].name,
                    "group": sam.name,
                    "side": 3 - side,
                    "known": True,
                    "radius": AirDefence.SA_11_Buk_LN_9A310M1.threat_range,
                    "ceiling": 22000,
                    "needsRadar": True,
                    "radars": [unit.name for unit in sam.units[2:]],
                }
            )
            for group in (fighter, bomber, sam):
                group.late_activation = True
                group.points[0].ETA_locked = True
                group.points[0].ETA = 0
            cases.append(
                {
                    "group": name,
                    "bait": bomber.name,
                    "sam": sam.name,
                    "guarded": guarded,
                    "side": side,
                    "radius": AirDefence.SA_11_Buk_LN_9A310M1.threat_range,
                    "center": {"x": center.x, "z": center.y},
                }
            )
    for name in SCRIPTS:
        trigger = TriggerOnce(comment="IMAC CAP probe: " + name)
        trigger.add_condition(TimeAfter(2))
        trigger.add_action(
            DoScriptFile(mission.map_resource.add_resource_file(PLUGIN / name))
        )
        mission.triggerrules.triggers.append(trigger)
    driver = (HERE / "imac_cap_sam_probe.lua").read_text("utf-8")
    driver = driver.replace(
        "__CONFIG__", dumps({"config": config, "cases": cases, "duration": 420})
    )
    trigger = TriggerOnce(comment="IMAC CAP probe: automatic comparison")
    trigger.add_condition(TimeAfter(3))
    trigger.add_action(DoScript(String(driver)))
    mission.triggerrules.triggers.append(trigger)
    mission.description_text = (
        "IMAC native CAP SAM guard: four sequential seven-minute cases. BLUE F-16 "
        "and RED Su-27 pairs, with SAM avoidance disabled/enabled. Each pair has "
        "a native 50-NM EngageTargets task and a bomber behind an operational Buk. "
        "IMAC intercept range is limited to 20 NM to isolate native pursuit. "
        "All aircraft are immortal intentionally; measure tracks and ring entry, "
        "not losses. The Buk is removed automatically after 210 seconds to test "
        "safe resumption. Both sides use physical standalone command centres. "
        "No mods, aircraft modules or F10 input required. Time acceleration is "
        "allowed. Wait about 28 simulated minutes for IMAC CAP SAM COMPLETE. "
        "Native pursuit, avoidance orders, minimum distance of every patrol "
        "member and resumption are logged under IMAC_CAP_SAM. Orders alone are "
        "not proof of a safe flight path; the control must approach the SAM."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing mission")
    from game import persistency

    with tempfile.TemporaryDirectory(prefix="imac-cap-probe-") as directory:
        persistency.setup(directory, False, 16889)
        build_mission().save(args.output)
    Mission().load_file(str(args.output))
    print(args.output)
