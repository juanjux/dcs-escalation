"""Generate a small mission to validate native ship/static health restoration."""

from datetime import datetime
from pathlib import Path
import argparse

from dcs import Mission
from dcs.action import DoScript
from dcs.condition import TimeAfter
from dcs.mapping import Point, LatLng
from dcs.planes import A_10C_2
from dcs.ships import PERRY
from dcs.statics import Fortification
from dcs.translation import String
from dcs.triggers import TriggerOnce
from dcs.unit import Skill
from dcs.mission import StartType
from dcs.terrain import Caucasus

from game.missiongenerator.persistenthealth import SetUnitHealth


def build_mission() -> Mission:
    mission = Mission(Caucasus())
    mission.start_time = datetime(2026, 6, 15, 12)
    airport = mission.terrain.airports["Batumi"]
    airport.set_coalition("blue")
    country = mission.country("USA")
    player = mission.flight_group_from_airport(
        country, "Probe player", A_10C_2, airport, start_type=StartType.Warm
    )
    player.units[0].skill = Skill.Player
    targets = []
    action = TriggerOnce(comment="Native health restoration (percent units)")
    action.add_condition(TimeAfter(2))
    for index, health in enumerate((0.35, 0.65, 0.9821209716796899)):
        building = mission.static_group(
            country,
            f"HEALTH_STATIC_{index}",
            Fortification.FARP_CP_Blindage,
            airport.position.point_from_heading(90, 1500 + index * 300),
        ).units[0]
        ship = mission.ship_group(
            country,
            f"HEALTH_SHIP_{index}",
            PERRY,
            Point.from_latlng(LatLng(41.6 + index * 0.01, 41.4), mission.terrain),
        ).units[0]
        for unit in (building, ship):
            action.add_action(SetUnitHealth(unit.id, health))
            targets.append(f'{{name="{unit.name}",expected={health}}}')
    mission.triggerrules.triggers.append(action)
    script = """
        local targets = {TARGETS}
        for _, target in ipairs(targets) do
            local object = Unit.getByName(target.name) or StaticObject.getByName(target.name)
            if object then target.maximum = object:getDesc().life or object:getLife() end
        end
        local function sample(_, now)
            local text = 'NATIVE HEALTH PROBE'
            for _, target in ipairs(targets) do
                local object = Unit.getByName(target.name) or StaticObject.getByName(target.name)
                local current = object and target.maximum and object:getLife() / target.maximum
                local line = string.format('%s expected %.3f%%, actual %s', target.name,
                    target.expected*100, current and string.format('%.3f%%',current*100) or 'MISSING')
                env.info('Escalation health probe: ' .. line)
                text = text .. '\\n' .. line
            end
            text = text .. '\\nSandbox setter=' .. type(a_unit_set_life_percentage) .. ', net=' .. type(net)
            trigger.action.outText(text, 30)
            return now + 15
        end
        timer.scheduleFunction(sample,nil,timer.getTime()+5)
    """.replace("TARGETS", ",".join(targets))
    read = TriggerOnce(comment="Health readings")
    read.add_condition(TimeAfter(1))
    read.add_action(DoScript(String(script)))
    mission.triggerrules.triggers.append(read)
    mission.set_description_text(
        "PERSISTENT HEALTH PROBE — NO CAMPAIGN\n"
        "Unpause and wait 7 seconds. Expected and actual health are displayed and "
        "written to dcs.log every 15 seconds. The native action sets three ships "
        "and three FARP CP Blindage statics to 35%, 65% and 98.212%. No explosions."
    )
    return mission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_mission().save(args.output)
    print(args.output)
