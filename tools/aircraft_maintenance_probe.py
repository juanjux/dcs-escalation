"""Generate standalone Caucasus missions for aircraft damage telemetry checks."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from dcs import Mission
from dcs.action import DoScript, DoScriptFile
from dcs.condition import TimeAfter
from dcs.helicopters import UH_1H
from dcs.mission import StartType
from dcs.planes import A_10C_2, F_16C_50, FA_18C_hornet
from dcs.terrain import Caucasus
from dcs.terrain.terrain import ParkingSlot
from dcs.translation import String
from dcs.triggers import Event, TriggerOnce
from dcs.unit import Skill

SCRIPT = Path(__file__).with_suffix(".lua")
PLAYER_TYPES = {"a10": A_10C_2, "hornet": FA_18C_hornet}


def build_mission(player: str = "a10", scenario: str = "damage") -> Mission:
    if scenario not in ("damage", "off-field"):
        raise ValueError(f"Unknown probe scenario: {scenario}")
    mission = Mission(Caucasus())
    mission.start_time = datetime(2026, 6, 15, 12)
    batumi = mission.terrain.airports["Batumi"]
    kobuleti = mission.terrain.airports["Kobuleti"]
    for airport in (batumi, kobuleti):
        airport.set_coalition("blue")
    for name in ("Sochi-Adler", "Gudauta"):
        mission.terrain.airports[name].set_coalition("red")
    country = mission.country("USA")
    group = mission.flight_group_from_airport(
        country,
        "Maintenance probe player",
        PLAYER_TYPES[player],
        batumi,
        start_type=StartType.Warm,
    )
    group.units[0].name = "PROBE_PLAYER"
    group.units[0].skill = Skill.Player
    tracked = ["PROBE_PLAYER"]
    targets = []
    used: list[ParkingSlot] = []
    types: list[Any] = [A_10C_2, FA_18C_hornet, F_16C_50, UH_1H]
    for index, aircraft_type in enumerate(types):
        slots = list(kobuleti.free_parking_slots(aircraft_type))
        slot = max(
            slots,
            key=lambda s: min(
                (s.position.distance_to_point(p.position) for p in used), default=0
            ),
        )
        used.append(slot)
        target = mission.flight_group_from_airport(
            country,
            f"Maintenance target {index + 1}",
            aircraft_type,
            kobuleti,
            start_type=StartType.Cold,
            parking_slots=[slot],
        )
        name = f"PROBE_TARGET_{index + 1}"
        target.units[0].name = name
        target.uncontrolled = True
        targets.append(name)
        tracked.append(name)
    runway = batumi.runways[0]
    # Continue along the sea-side approach waypoint, not the opposite, inland
    # side where a low-altitude spawn can intersect the terrain.
    approach = batumi.position.point_from_heading(runway.heading, 12000)
    arrival = mission.flight_group_inflight(
        country,
        "Maintenance landing control",
        A_10C_2,
        approach,
        altitude=500,
        speed=350,
    )
    arrival.units[0].name = "PROBE_RETURNING_A10"
    arrival.units[0].skill = Skill.Excellent
    arrival.add_runway_waypoint(batumi, distance=6000)
    arrival.land_at(batumi)
    tracked.append(arrival.units[0].name)

    def strings(values: list[str]) -> str:
        return "{" + ",".join('"' + value + '"' for value in values) + "}"

    bases = []
    for name in ("Batumi", "Kobuleti", "Sochi-Adler", "Gudauta"):
        airport = mission.terrain.airports[name]
        side = 2 if name in ("Batumi", "Kobuleti") else 1
        bases.append(
            f'{{name="{name}",x={airport.position.x},z={airport.position.y},coalition={side}}}'
        )
    setup = (
        'ESCALATION_AIRCRAFT_PROBE = {player="PROBE_PLAYER",units='
        + strings(tracked)
        + ",targets="
        + strings(targets)
        + ",bases={"
        + ",".join(bases)
        + "},automatic_damage="
        + ("false" if scenario == "off-field" else "true")
        + "}"
    )
    trigger = TriggerOnce(Event.NoEvent, "Aircraft maintenance telemetry")
    trigger.add_condition(TimeAfter(1))
    trigger.add_action(DoScript(String(setup)))
    trigger.add_action(DoScriptFile(mission.map_resource.add_resource_file(SCRIPT)))
    mission.triggerrules.triggers.append(trigger)
    mission.set_description_text(
        "AIRCRAFT MAINTENANCE TELEMETRY — DIAGNOSTIC ONLY\n\n"
        "Start in a hot aircraft at Batumi. No campaign or workshop rules run.\n"
        "1. Unpause and wait 100 seconds. Four parked AI targets at Kobuleti "
        "receive increasingly strong blasts. The player is NOT automatically damaged.\n"
        "2. F10 > Aircraft maintenance probe > Show health readings.\n"
        "3. An AI A-10 attempts a normal landing at Batumi; allow up to 10 minutes.\n"
        "4. Optional: sample health, jettison the canopy normally, then select "
        "Mark canopy change for comparison. No damage is inferred from that marker.\n"
        "5. Optional: fly, use the small PLAYER blast, and land or make a forced "
        "landing near a friendly base. Crash/ejection tests require separate runs.\n\n"
        "Results: Saved Games/DCS/Logs/dcs.log, prefix ESCALATION_AIRCRAFT_PROBE. "
        "If file access is already available, also Saved Games/DCS/_debug_logs/"
        "aircraft-maintenance-probe-*.jsonl. No security settings need changing.\n"
        "The nearest-base comparison covers Batumi, Kobuleti, Sochi-Adler and Gudauta."
    )
    if scenario == "off-field":
        mission.set_description_text(
            "OFF-FIELD LANDING TELEMETRY — DIAGNOSTIC ONLY\n\n"
            "Start hot at Batumi. There is no automatic damage to any aircraft.\n"
            "1. Take off normally, then land on dry terrain OUTSIDE an airport, "
            "not on its runway or taxiway. Choose a suitable flat area near Batumi.\n"
            "2. Stay in the aircraft, stopped, for at least 30 seconds. Do not "
            "eject, leave the slot or end the mission during this interval.\n"
            "3. F10 > Aircraft maintenance probe > Mark off-field landing attempt. "
            "This only labels the observation; it does not force a landing event.\n"
            "4. Show health readings, then exit the mission.\n\n"
            "First establish a surviving off-field landing with an undamaged aircraft. "
            "A separate, optional run can use Small blast near PLAYER before landing; "
            "this can destroy the aircraft and is not needed for the first run.\n"
            "An AI A-10 also lands normally at Batumi as a control.\n"
            "The recorder captures native landing/crash events, airborne transitions, "
            "health, speed, position and distances to friendly/enemy bases. A marker "
            "or a stationary unit alone is NOT proof of recovery.\n\n"
            "Results: Saved Games/DCS/Logs/dcs.log, prefix ESCALATION_AIRCRAFT_PROBE. "
            "If file access is already available, also Saved Games/DCS/_debug_logs/"
            "aircraft-maintenance-probe-*.jsonl. No campaign is modified."
        )
    return mission


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--aircraft", choices=PLAYER_TYPES, default="a10")
    parser.add_argument("--scenario", choices=("damage", "off-field"), default="damage")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite {args.output}")
    if not args.output.parent.is_dir():
        parser.error("The output directory must already exist")
    build_mission(args.aircraft, args.scenario).save(str(args.output))
    print(args.output)


if __name__ == "__main__":
    main()
