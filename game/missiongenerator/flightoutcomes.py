"""Publish DCS objective and flight-end events for selected ATO prerequisites."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from dcs.action import SetFlagValue
from dcs.condition import FlagEquals, UnitDead
from dcs.task import RunScript
from dcs.triggers import Event, TriggerOnce

from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.prerequisites import (
    OBJECTIVE_FLIGHTS,
    flight_name,
    objective_units,
    outcome_flag,
)
from game.missiongenerator.realisticcasluadata import lua_literal

if TYPE_CHECKING:
    from dcs.point import MovingPoint
    from game.ato import Flight, FlightWaypoint
    from .luagenerator import LuaGenerator


def objective_ids(target: object, exported: dict[int, int]) -> list[int] | None:
    """None means the scenario cannot certify completion. [] means already complete."""
    tagged = objective_units(target)
    if not tagged:
        return None
    alive = [unit.id for unit in tagged if unit.alive]
    if any(key not in exported for key in alive):
        # A live campaign unit omitted from the .miz has no DCS death event.
        return None
    return [exported[key] for key in alive]


def inject(generator: LuaGenerator) -> None:
    unit_map = generator.unit_map
    if unit_map is None:
        return
    packages = [p for side in generator.game.coalitions for p in side.ato.packages]
    selected = {key for p in packages for key in p.prerequisite_flights}
    providers = {
        f.id: f
        for p in packages
        for f in p.flights
        if f.id in selected and f.flight_type in OBJECTIVE_FLIGHTS
    }
    if not providers:
        return
    members: dict[UUID, list[str]] = {key: [] for key in providers}
    for name, entry in unit_map.aircraft.items():
        if entry.flight.id in members:
            members[entry.flight.id].append(name)
    exported = {
        mapping.theater_unit.id: mapping.dcs_unit.id
        for mapping in unit_map.theater_objects.values()
    }
    for key, flight in providers.items():
        ids = objective_ids(flight.package.target, exported)
        if ids is None:
            continue
        success = TriggerOnce(
            Event.NoEvent, f"Objective complete: {flight_name(flight)}"
        )
        success.add_condition(FlagEquals(outcome_flag(key), 0))
        for unit_id in ids:
            success.add_condition(UnitDead(unit_id))
        success.add_action(SetFlagValue(outcome_flag(key), 1))
        generator.mission.triggerrules.triggers.append(success)
    generator.inject_plugin_script(
        "imac", "ground-stores.lua", "imac-ground-stores.lua"
    )
    generator.inject_plugin_script("base", "flight-outcomes.lua", "flight-outcomes.lua")
    config = {str(key): names for key, names in members.items()}
    generator.inject_lua_trigger(
        f"EscalationFlightOutcomes.start({lua_literal(config)})", "Flight outcomes"
    )


def mark_return(
    flight: Flight, generated: list[tuple[FlightWaypoint, MovingPoint]]
) -> None:
    if flight.flight_type not in OBJECTIVE_FLIGHTS or not any(
        flight.id in p.prerequisite_flights for p in flight.coalition.ato.packages
    ):
        return
    layout = flight.flight_plan.layout
    # A solo flight's split may be labelled NAV or omitted from the route.
    return_points = [
        getattr(layout, "split", None),
        getattr(layout, "refuel", None),
        *getattr(layout, "nav_from", ()),
    ]
    for source, native in generated:
        if any(source is wp for wp in return_points) or source.waypoint_type in {
            FlightWaypointType.EGRESS,
            FlightWaypointType.SPLIT,
            FlightWaypointType.LANDING_POINT,
        }:
            native.tasks.insert(
                0,
                RunScript(
                    f'trigger.action.setUserFlag("prerequisite-return-{flight.id}", 1)'
                ),
            )
            break
