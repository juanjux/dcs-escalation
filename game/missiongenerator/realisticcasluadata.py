"""Read-only registry export for Realistic CAS (not enabled in campaigns yet).

Names/types/pylons come from the final pydcs mission; roles come from FlightData,
never the group name or DCS's generic CAS task. Environment, prior intelligence,
visibility ownership adapters and the actual plugin injection are separate steps.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from dcs.flyingunit import FlyingUnit

if TYPE_CHECKING:
    from dcs import Mission
    from game.unitmap import UnitMap
    from .missiondata import MissionData


# Exact, installed pydcs CLSIDs. No substring heuristics that mistake ECM/IRST
# for a targeting pod. Integrated optics/radar remain in sensors.lua's profiles.
TARGETING_PODS = frozenset(
    {
        "{AN_ASQ_228}",
        "{A111396E-D3E8-4b9c-8AC9-2432489304D5}",
        "{AAQ-28_LEFT}",
        "{F-15E_AAQ-28_LITENING}",
        "{F-15E_AAQ-33_XR_ATP-SE}",
        "{AN_AAQ_33}",
    }
)

SCRIPT_ORDER = (
    "core.lua",
    "dcs.lua",
    "sensors.lua",
    "environment.lua",
    "detection.lua",
    "detectors-dcs.lua",
    "bootstrap.lua",
)


def render_startup(config: Mapping[str, Any]) -> str | None:
    """Render the final action after SCRIPT_ORDER, without mutating the mission.

    The caller supplies an explicit environment and the final registry. This is
    not wired to the campaign plugin checkbox yet: JTAC/TIC adapters remain open.
    """
    if config.get("enabled") is not True:
        return None
    if config.get("registry", {}).get("schemaVersion") != 1:
        raise ValueError("Unsupported Realistic CAS registry schema")
    seconds = config.get("acquisitionSeconds")
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or not 0 < seconds <= 600
    ):
        raise ValueError("Campaign acquisition time must be explicit and positive")
    if not isinstance(config.get("environment"), Mapping):
        raise ValueError("Explicit Realistic CAS environment required")
    return (
        "do local ok, instance, why = pcall(RealisticCAS.startMission, "
        + lua_literal(config)
        + ")\n"
        "if not ok or not instance then\n"
        "local detail = tostring(ok and why or instance)\n"
        "env.error('REALISTIC_CAS_MISSION|STARTUP_FAILED|' .. detail)\n"
        "trigger.action.outText('Realistic CAS failed to start. See dcs.log: ' .. detail, 30)\n"
        "end end\n"
    )


def lua_literal(value: Any) -> str:
    """Strict typed serializer, independent of LuaData's string-only subtrees."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Non-finite Realistic CAS value")
        return repr(value)
    if isinstance(value, str):
        escaped = []
        for char in value:
            n = ord(char)
            if char in ('"', "\\"):
                escaped.append("\\" + char)
            elif n < 32 or n == 127:
                escaped.append(f"\\{n:03d}")
            else:
                escaped.append(char)
        return '"' + "".join(escaped) + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua_literal(v) for v in value) + "}"
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("Realistic CAS object keys must be strings")
        return (
            "{"
            + ",".join(
                "[" + lua_literal(k) + "]=" + lua_literal(value[k])
                for k in sorted(value)
            )
            + "}"
        )
    raise TypeError(f"Unsupported Realistic CAS value: {type(value).__name__}")


def _controls_visibility(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("id") == "SetInvisible":
            return True
        return any(_controls_visibility(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_controls_visibility(v) for v in value)
    return False


def collect_registry(
    mission: Mission,
    mission_data: MissionData,
    *,
    enabled: bool,
    unit_map: UnitMap | None = None,
    excluded_groups: Collection[str] = (),
) -> dict[str, Any] | None:
    """Collect declared units without modifying pydcs or activating any Lua.

    Off short-circuits before touching either argument. TIC must be adapted before
    use; refusing its combination is safer than silently fighting its Cloak calls.
    Explicit exclusions and ANY waypoint invisibility owner (even SetInvisible
    false) are preserved. Runtime-created groups/trigger-owned visibility require
    adapters and are NOT certified by this registry's waypoint inspection alone.
    """
    if not enabled:
        return None
    if unit_map is None:
        raise ValueError(
            "Realistic CAS requires UnitMap to distinguish SAM objectives from frontline SAMs"
        )
    if mission_data.tic_groups:
        raise ValueError(
            "Realistic CAS: TIC visibility/clone adapter is not integrated yet"
        )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "groups": [],
        "targets": [],
        "observers": [],
        "warnings": [],
        "knownAirDefenseGroups": [],
    }
    roles: dict[str, str] = {}
    for flight in mission_data.flights:
        role = flight.flight_type.value
        for flight_unit in flight.units:
            if flight_unit.name in roles:
                raise ValueError(f"Duplicate FlightData unit: {flight_unit.name}")
            roles[flight_unit.name] = role
    for jtac in mission_data.jtacs:
        previous = roles.get(jtac.unit_name)
        if previous is not None and previous != "JTAC":
            raise ValueError(f"Conflicting JTAC/flight role: {jtac.unit_name}")
        roles[jtac.unit_name] = "JTAC"

    excluded = set(excluded_groups)
    group_names: set[str] = set()
    unit_names: set[str] = set()
    present_air: set[str] = set()
    for side_name, side in (("red", 1), ("blue", 2)):
        coalition = mission.coalition.get(side_name)
        if coalition is None:
            continue
        for country in coalition.countries.values():
            for category, groups in (
                ("ground", country.vehicle_group),
                ("air", country.plane_group),
                ("air", country.helicopter_group),
            ):
                for group in groups:
                    if group.name in group_names:
                        raise ValueError(f"Duplicate DCS group name: {group.name}")
                    group_names.add(group.name)
                    # SamGroundObject has category 'aa'. Use campaign ownership,
                    # NEVER vehicle type, radar range, unit/group name, or movement.
                    # Its generated support groups belong to the same objective.
                    sites = set()
                    if category == "ground":
                        for unit in group.units:
                            mapping = unit_map.theater_objects.get(unit.name)
                            if mapping is not None:
                                objective = mapping.theater_unit.ground_object
                                if objective.category == "aa":
                                    sites.add(objective.name)
                    if sites:
                        result["knownAirDefenseGroups"].append(
                            {
                                "name": group.name,
                                "coalition": side,
                                "objectives": sorted(sites),
                            }
                        )
                    foreign_owner = group.name in excluded or (
                        category == "ground"
                        and any(
                            _controls_visibility(task.dict())
                            for point in group.points
                            for task in point.tasks
                        )
                    )
                    if foreign_owner:
                        result["warnings"].append(
                            f"Excluded visibility-owned group: {group.name}"
                        )
                    if (
                        category == "ground"
                        and not foreign_owner
                        and not sites
                        and group.units
                    ):
                        result["groups"].append(
                            {
                                "name": group.name,
                                "coalition": side,
                                "originalInvisible": False,
                            }
                        )
                    for unit in group.units:
                        if not unit.name or unit.name in unit_names:
                            raise ValueError(
                                f"Empty/duplicate DCS unit name: {unit.name}"
                            )
                        unit_names.add(unit.name)
                        if category == "air":
                            present_air.add(unit.name)
                        if foreign_owner:
                            continue
                        if category == "ground" and not sites:
                            result["targets"].append(
                                {
                                    "name": unit.name,
                                    "groupName": group.name,
                                    "coalition": side,
                                    "typeName": unit.type,
                                }
                            )
                        # Players do not provide scripted AI sensor reports. In a
                        # mixed flight, retain AI wingmen without touching tasks.
                        if getattr(unit.skill, "value", unit.skill) in (
                            "Client",
                            "Player",
                        ):
                            continue
                        observer = {
                            "name": unit.name,
                            "typeName": unit.type,
                            "category": category,
                            "coalition": side,
                        }
                        if category == "air":
                            if not isinstance(unit, FlyingUnit):
                                raise ValueError(
                                    f"Non-aircraft unit in flying group: {unit.name}"
                                )
                            if unit.name not in roles:
                                result["warnings"].append(
                                    f"No FlightData/JTAC role; observer omitted: {unit.name}"
                                )
                                continue
                            observer["role"] = roles[unit.name]
                            clsids = sorted(
                                {
                                    v["CLSID"]
                                    for v in unit.pylons.values()
                                    if v.get("CLSID")
                                }
                            )
                            observer["payloadClsids"] = clsids
                            observer["equipment"] = {
                                "targetingPod": bool(
                                    TARGETING_PODS.intersection(clsids)
                                )
                            }
                        result["observers"].append(observer)
    for name in sorted(roles.keys() - present_air):
        result["warnings"].append(
            f"FlightData/JTAC absent from generated mission: {name}"
        )
    for field in ("groups", "targets", "observers", "knownAirDefenseGroups"):
        result[field].sort(key=lambda row: row["name"])
    result["warnings"].sort()
    return result
