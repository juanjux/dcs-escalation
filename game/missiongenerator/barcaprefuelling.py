"""Bind fuel-managed AI BARCAPs to their native orbit and recovery route."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dcs.task import OptRTBOnBingoFuel, RunScript

from game.ato.flighttype import FlightType
from game.ato.fuelestimate import assumed_consumption
from game.ato.prerefuel import compatible
from game.utils import escape_string_for_lua


def _orbit(point: Any) -> dict[str, Any] | None:
    for task in point.tasks:
        data = task.dict()
        if data["id"] == "ControlledTask" and data["params"]["task"]["id"] == "Orbit":
            return dict(data["params"])
    return None


def configure(game: Any, mission: Any, mission_data: Any) -> list[dict[str, Any]]:
    """Do not alter native BINGO until the station flag activates a valid monitor."""
    flights = getattr(mission_data, "flights", [])
    tankers = {t.group_name: t for t in getattr(mission_data, "tankers", [])}
    result = []
    for flight in flights:
        if flight.flight_type is not FlightType.BARCAP or flight.client_units:
            continue
        aircraft = flight.aircraft_type
        maximum = aircraft.max_fuel * 2.2046226218
        bingo = flight.bingo_fuel
        if not maximum or not bingo or not 0 < bingo / maximum < 0.8:
            continue
        group = mission.find_group(flight.group_name)
        if group is None:
            continue
        starts = [(i, _orbit(p)) for i, p in enumerate(group.points) if _orbit(p)]
        ends = [i for i, p in enumerate(group.points) if str(p.name) == "RACETRACK END"]
        if not starts or not ends:
            continue
        start, orbit = starts[0]
        assert orbit is not None
        end_time = orbit.get("stopCondition", {}).get("time")
        if end_time is None:
            continue
        home = []
        for point in group.points[ends[0] + 1 :]:
            if str(point.name) == "REFUEL":
                continue
            data = deepcopy(point.dict())
            data["ETA_locked"] = False
            data["speed_locked"] = True
            home.append(data)
        if not home:
            continue
        available = []
        for other in flights:
            info = tankers.get(other.group_name)
            if (
                info is None
                or other.friendly != flight.friendly
                or not compatible(aircraft, other.aircraft_type)
            ):
                continue
            available.append(
                {
                    "group": other.group_name,
                    "startTime": (
                        info.start_time - game.conditions.start_time
                    ).total_seconds(),
                    "endTime": (
                        info.end_time - game.conditions.start_time
                    ).total_seconds(),
                }
            )
        if not available:
            continue  # Native RTB remains untouched without compatible planned support.
        fuel = aircraft.fuel_consumption or assumed_consumption(aircraft)
        if fuel.cruise <= 0:
            continue
        flag = f"barcap-station-{group.id}"
        config = {
            "group": str(group.name),
            "flag": flag,
            "endTime": end_time,
            "bingo": bingo / maximum,
            "reserve": fuel.min_safe / maximum,
            "burnPerMeter": fuel.cruise / maximum / 1852,
            "tankers": available,
            "home": home,
            "unlimitedOutsideStation": bool(game.settings.ai_unlimited_fuel),
            "gunfighter": aircraft.gunfighter,
            "tankingSeconds": max(900, (4 * len(group.units) + 1) * 60),
        }
        result.append(config)
        quoted = escape_string_for_lua(flag)
        # Keep the unlimited-fuel command first and the orbit last.
        group.points[start].tasks.insert(
            max(0, len(group.points[start].tasks) - 1),
            RunScript(f'trigger.action.setUserFlag("{quoted}", 1)'),
        )
        group.points[ends[0]].tasks.extend(
            [
                RunScript(f'trigger.action.setUserFlag("{quoted}", 0)'),
                OptRTBOnBingoFuel(True),
            ]
        )
    return result
