"""Opt-in IMAC metadata. Enemy flight plans are never exported as intelligence."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from dcs.lua import dumps
from dcs.task import RunScript
from dcs.vehicles import vehicle_map
from dcs.ships import ship_map
from dcs.unit import Static

from game.ato import FlightType
from game.data.units import UnitClass
from game.data.radar_db import LAUNCHER_TRACKER_PAIRS
from game.groundmovement.samdefense import transit_defense
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsnetwork import SkynetNode
from game.theater.player import Player
from .afacthreats import envelope

SCRIPTS = ("geometry.lua", "commander.lua", "dcs.lua")
DEFAULTS: dict[str, float | bool] = {
    "blue": True,
    "red": True,
    "reports": True,
    "debug": False,
    "interval": 10,
    "interceptRangeNm": 120,
    "patrolLeashNm": 80,
    "pursuitSeconds": 180,
    "defendRangeNm": 45,
    "holdSeconds": 600,
}
CAP_TYPES = {FlightType.BARCAP, FlightType.TARCAP}
STRIKE_TYPES = {
    FlightType.STRIKE,
    FlightType.BAI,
    FlightType.OCA_AIRCRAFT,
    FlightType.OCA_RUNWAY,
    FlightType.ANTISHIP,
    FlightType.CAS,
    FlightType.ARMED_RECON,
}
SUPPORT_TYPES = {
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.RECOVERY,
    FlightType.TRANSPORT,
    FlightType.FERRY,
}


def _array(value: Any) -> Any:
    """Keep native route tables one-based when passing through Python lists."""
    if isinstance(value, dict):
        if value and all(type(k) is int for k in value):
            if set(value) != set(range(1, len(value) + 1)):
                raise ValueError("IMAC: non-contiguous route table")
            return [_array(value[i]) for i in range(1, len(value) + 1)]
        return {k: _array(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_array(v) for v in value]
    return value


def options(plugins: Any) -> dict[str, Any] | None:
    plugin = next((p for p in plugins if p.identifier == "imac" and p.enabled), None)
    if plugin is None:
        return None
    result: dict[str, Any] = dict(DEFAULTS)
    result.update(
        (o.identifier.removeprefix("imac."), o.get_value) for o in plugin.options
    )
    bounds = {
        "interval": (5, 60),
        "interceptRangeNm": (20, 200),
        "patrolLeashNm": (10, 150),
        "pursuitSeconds": (30, 600),
        "defendRangeNm": (10, 100),
        "holdSeconds": (60, 1800),
    }
    for key, default in DEFAULTS.items():
        value = result[key]
        if isinstance(default, bool):
            if type(value) is not bool:
                raise ValueError(f"IMAC: {key} must be boolean")
        elif (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not bounds[key][0] <= value <= bounds[key][1]
        ):
            raise ValueError(f"IMAC: {key} outside {bounds[key]}")
    for name in SCRIPTS:
        if not (Path("resources/plugins/imac") / name).is_file():
            raise FileNotFoundError(name)
    return result


def configure(generator: Any, config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Run after other generators finish changing native routes; off is inert."""
    if config is None:
        return None
    mission, data = generator.mission, generator.mission_data
    result: dict[str, Any] = {
        "options": config,
        "flights": [],
        "sensors": [],
        "commandCenters": [],
        "threats": [],
    }
    groups: dict[str, tuple[Any, int]] = {}
    for side_name, side in (("red", 1), ("blue", 2)):
        coalition = mission.coalition.get(side_name)
        if coalition is None:
            continue
        for country in coalition.countries.values():
            for group in country.plane_group + country.helicopter_group:
                groups[group.name] = group, side
                result["sensors"].extend(
                    {"name": u.name, "group": group.name, "side": side, "air": True}
                    for u in group.units
                )
            for group in country.vehicle_group + country.ship_group:
                result["sensors"].extend(
                    {
                        "name": u.name,
                        "group": group.name,
                        "side": side,
                        "air": False,
                        "priority": getattr(
                            vehicle_map.get(u.type), "detection_range", 0
                        )
                        >= 40000
                        or group in country.ship_group,
                    }
                    for u in group.units
                    if getattr(vehicle_map.get(u.type), "detection_range", 0) > 0
                    or group in country.ship_group
                )
    for flight in data.flights:
        native = groups.get(flight.group_name)
        if native is None:
            continue
        group, side = native
        # A mixed AI/client group also belongs entirely to the human player.
        human = bool(flight.client_units or any(u.is_human() for u in group.units))
        role = flight.flight_type
        if role in CAP_TYPES:
            mode = "cap"
        elif role in STRIKE_TYPES:
            mode = "strike"
        elif role in SUPPORT_TYPES:
            mode = "support"
        elif role == FlightType.DEAD:
            mode = "dead"
        else:
            # AFAC and escort navigation already have dedicated owners.
            mode = "observe"
        if human:
            mode = "observe"  # Still protect human flights, but never task them.
        if len(group.points) < 2:
            continue
        start, end, end_time = 0, len(group.points), None
        attack_index = len(group.points)
        for index, point in enumerate(group.points, 1):
            if point.name == "RACETRACK START":
                start = index
                for task in point.tasks:
                    task_data = task.dict()
                    if task_data.get("params", {}).get("task", {}).get("id") == "Orbit":
                        end_time = (
                            task_data["params"].get("stopCondition", {}).get("time")
                        )
            if point.name in ("SPLIT", "RACETRACK END"):
                end = min(end, index)
            if any(
                wp.waypoint_type.name.startswith("INGRESS_")
                and abs(wp.position.x - point.position.x) < 1
                and abs(wp.position.y - point.position.y) < 1
                for wp in flight.waypoints
            ):
                attack_index = min(attack_index, index)
        if mode == "cap" and (not start or end_time is None):
            mode = "observe"  # Never invent a patrol window.
        maximum = flight.aircraft_type.max_fuel * 2.2046226218
        bingo = (flight.bingo_fuel / maximum) if maximum and flight.bingo_fuel else 0.25
        # Missing or implausible performance data must not authorize long detours.
        if not math.isfinite(bingo) or not 0 < bingo < 0.8:
            mode, bingo = "observe", 0.25
        burn = getattr(flight.aircraft_type, "fuel_consumption", None)
        if burn is None:
            burn = getattr(flight.aircraft_type, "assumed_consumption", None)
        burn_per_meter = burn.cruise / maximum / 1852 if burn and maximum else None
        if burn_per_meter is not None and (
            not math.isfinite(burn_per_meter) or burn_per_meter <= 0
        ):
            burn_per_meter = None
        # Hook every point before blocking Orbit/attack tasks. Recovery is a copy
        # of the final route, including carrier links and off-map despawn actions.
        if mode != "observe":
            for index, point in enumerate(group.points, 1):
                point.tasks.insert(
                    0,
                    RunScript(
                        "if EscalationIMAC then EscalationIMAC.reached("
                        f"{dumps(group.name)}, {index}) end"
                    ),
                )
        route = copy.deepcopy(_array(group.dict()["route"]["points"]))
        result["flights"].append(
            {
                "group": group.name,
                "side": side,
                "mode": mode,
                "awacs": role == FlightType.AEWC,
                "deadSupport": role == FlightType.DEAD,
                "route": route,
                "stationStart": start,
                "recoveryIndex": end,
                "attackIndex": attack_index,
                "endTime": end_time,
                "bingo": bingo,
                "burnPerMeter": burn_per_meter,
                "gunfighter": getattr(flight.aircraft_type, "gunfighter", False),
                "package": str(id(flight.package)),
            }
        )
    iads_nodes = generator.game.theater.iads_network.skynet_nodes(generator.game)
    power_members = {
        node.dcs_name: getattr(node, "static_members", [])
        for node in iads_nodes
        if node.iads_role is IadsRole.POWER_SOURCE
    }
    for node in iads_nodes:
        if node.iads_role is IadsRole.COMMAND_CENTER:
            command: dict[str, Any] = {
                "name": node.dcs_name + " object",
                "key": node.dcs_name,
                "side": 2 if node.player.is_blue else 1,
                "power": list(
                    dict.fromkeys(
                        member + " object"
                        for name in node.connections.get(
                            IadsRole.POWER_SOURCE.value, []
                        )
                        for member in (power_members.get(name) or [name])
                    )
                ),
            }
            members = getattr(node, "static_members", [])
            if members:
                command["members"] = [name + " object" for name in members]
            if getattr(node, "requires_power", False):
                command["requiresPower"] = True
            result["commandCenters"].append(command)
    # Basic IADS does not enrol infrastructure. A physical standalone command
    # centre still provides command authority even without the Skynet plugin.
    known_centres = {row["name"] for row in result["commandCenters"]}
    if generator.unit_map is not None:
        visited: set[int] = set()
        for entry in generator.unit_map.theater_objects.values():
            objective = entry.theater_unit.ground_object
            if objective.category != "commandcenter" or id(objective) in visited:
                continue
            visited.add(id(objective))
            standalone_side = next(
                (
                    s
                    for p, s in ((Player.BLUE, 2), (Player.RED, 1))
                    if objective.is_friendly(p)
                ),
                None,
            )
            if standalone_side is None:
                continue
            for group in objective.groups:
                if getattr(group, "iads_role", None) is not IadsRole.COMMAND_CENTER:
                    continue
                key = SkynetNode.dcs_name_for_group(group)
                name = key + " object"
                mapped = generator.unit_map.theater_objects.get(name)
                if (
                    name not in known_centres
                    and mapped
                    and isinstance(mapped.dcs_unit, Static)
                ):
                    command = {
                        "name": name,
                        "key": key,
                        "side": standalone_side,
                        "power": [],
                    }
                    if len(group.units) > 1:
                        command["members"] = [
                            u.unit_name + " object" for u in group.units
                        ]
                    result["commandCenters"].append(command)
                    known_centres.add(name)
    _threats(generator, result)
    return result


def _threats(generator: Any, result: dict[str, Any]) -> None:
    """Ground intelligence is confined to known sites and shared CAS discoveries."""
    mapping = generator.unit_map
    if mapping is None:
        raise ValueError("IMAC requires UnitMap for coalition-known SAM intelligence")
    settings = generator.game.settings
    fog = settings.plugin_option_or("realisticcas", False)
    armor = fog and settings.plugin_option_or("realisticcas.includeArmorGroups", False)
    trackers: dict[int, list[str]] = {}
    tracking_classes = {
        UnitClass.TRACK_RADAR,
        UnitClass.SEARCH_TRACK_RADAR,
        UnitClass.TELAR,
    }
    for name, entry in mapping.theater_objects.items():
        unit = entry.theater_unit
        if unit.unit_type is not None and unit.unit_type.unit_class in tracking_classes:
            trackers.setdefault(id(unit.ground_object), []).append(name)
    for side_name, side in (("red", 1), ("blue", 2)):
        coalition = generator.mission.coalition.get(side_name)
        if coalition is None:
            continue
        for country in coalition.countries.values():
            for group in country.vehicle_group:
                hidden = (
                    fog
                    and group.name in generator.mission_data.frontline_visibility_groups
                )
                for unit in group.units:
                    threat = envelope(unit.type)
                    entry = mapping.theater_objects.get(unit.name)
                    if threat is None:
                        continue
                    objective = entry.theater_unit.ground_object if entry else None
                    packed = objective is not None and getattr(
                        objective, "in_transit", False
                    )
                    reactive = None
                    if packed and objective is not None:
                        if len(group.points) > 1 and not any(
                            u.alive and u.transported_by_id is not None
                            for u in objective.units
                        ):
                            reactive = transit_defense(u.type for u in group.units)
                        if reactive is None:
                            continue
                        threat = {
                            "radius": reactive.range_m,
                            "ceiling": reactive.ceiling_m,
                        }
                    concealed = hidden or (
                        armor
                        and objective is not None
                        and objective.category == "armor"
                    )
                    is_launcher = (
                        entry is not None
                        and entry.theater_unit.unit_type is not None
                        and entry.theater_unit.unit_type.unit_class
                        is UnitClass.LAUNCHER
                    )
                    native = vehicle_map.get(unit.type)
                    required = (
                        LAUNCHER_TRACKER_PAIRS.get(native)
                        if native is not None
                        else None
                    )
                    radars = trackers.get(id(objective), []) if is_launcher else []
                    if required:
                        radars = (
                            [
                                name
                                for name, candidate in mapping.theater_objects.items()
                                if candidate.theater_unit.ground_object is objective
                                and candidate.dcs_unit.type in {r.id for r in required}
                            ]
                            if objective is not None
                            else [
                                other.name
                                for other in group.units
                                if other.type in {r.id for r in required}
                            ]
                        )
                    result["threats"].append(
                        dict(
                            threat,
                            name=unit.name,
                            group=group.name,
                            side=side,
                            known=not concealed,
                            initialPoint=(
                                {"x": unit.position.x, "z": unit.position.y}
                                if not concealed
                                else None
                            ),
                            needsRadar=not reactive and (is_launcher or bool(required)),
                            radars=radars,
                            transitDefense=reactive is not None,
                        )
                    )
            for group in country.ship_group:
                for unit in group.units:
                    radius = getattr(ship_map.get(unit.type), "air_weapon_dist", 0)
                    if (
                        not isinstance(radius, (int, float))
                        or not math.isfinite(radius)
                        or radius <= 0
                    ):
                        continue
                    result["threats"].append(
                        {
                            "name": unit.name,
                            "group": group.name,
                            "side": side,
                            "known": True,
                            "radius": radius,
                            "initialPoint": {
                                "x": unit.position.x,
                                "z": unit.position.y,
                            },
                        }
                    )


def inject(generator: Any, config: dict[str, Any] | None) -> None:
    if config is None:
        return
    for name in SCRIPTS:
        generator.inject_plugin_script("imac", name, f"imac-{name}")
    generator.inject_lua_trigger(
        "EscalationIMAC.start(" + dumps(config) + ")", "In-Mission Air Commander"
    )
