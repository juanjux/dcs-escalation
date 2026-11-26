"""Wire DCS scenario outcome flags to package prerequisites."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from dcs import Mission
from dcs.action import Coalition, MessageToCoalition, SetFlagValue
from dcs.condition import FlagEquals
from dcs.point import MovingPoint
from dcs.task import ControlledTask, OrbitAction, RunScript
from dcs.triggers import Event, TriggerOnce

from game.ato import prerequisites
from game.ato.flightstate import InFlight
from game.ato.flightwaypointtype import FlightWaypointType
from game.missiongenerator.realisticcasluadata import lua_literal
from game.utils import meters

if TYPE_CHECKING:
    from dcs.unitgroup import FlyingGroup
    from game.ato import Flight, FlightWaypoint, Package

SUCCESS = 1
FAILURE = 2


def gate_flag(key: UUID) -> str:
    return f"prerequisites-{key}"


def generate_events(
    mission: Mission, packages: list[Package], side: Coalition, reports: bool
) -> None:
    """Each derived result is final, irrespective of which scenario trigger sets it."""
    selected = {key for p in packages for key in p.prerequisite_flights}
    if not selected:
        return
    for package in packages:
        for flight in package.flights:
            needs = prerequisites.required_by(flight)
            if not needs and flight.id not in selected:
                continue
            key = flight.id
            gate = gate_flag(key)
            result = f"prerequisite-result-{key}"
            label = prerequisites.flight_name(flight)
            if key in selected:
                for value, title in ((SUCCESS, "success"), (FAILURE, "failure")):
                    event = TriggerOnce(Event.NoEvent, f"Scenario {title}: {label}")
                    event.add_condition(
                        FlagEquals(prerequisites.outcome_flag(key), value)
                    )
                    event.add_condition(FlagEquals(result, 0))
                    if needs and value == SUCCESS:
                        event.add_condition(FlagEquals(gate, SUCCESS))
                    event.add_action(SetFlagValue(result, value))
                    mission.triggerrules.triggers.append(event)
            if not needs:
                continue
            # All successes release the wait. Any single failure cancels it.
            for required, value in [
                (needs, SUCCESS),
                *[([source], FAILURE) for source in needs],
            ]:
                event = TriggerOnce(
                    Event.NoEvent,
                    f"Prerequisites for {label}: {'release' if value == SUCCESS else 'cancel'}",
                )
                event.add_condition(FlagEquals(gate, 0))
                for source in required:
                    event.add_condition(
                        FlagEquals(f"prerequisite-result-{source}", value)
                    )
                event.add_action(SetFlagValue(gate, value))
                event.add_action(SetFlagValue(f"end-wait-{key}", 1))
                if value == FAILURE and key in selected:
                    event.add_action(SetFlagValue(result, FAILURE))
                if reports:
                    message = (
                        f"IMAC: {label} — prerequisites complete, continue."
                        if value == SUCCESS
                        else f"IMAC: {label} — {prerequisites.describe(package, required[0])} failed, return to base."
                    )
                    event.add_action(
                        MessageToCoalition(
                            side, mission.translation.create_string(message)
                        )
                    )
                mission.triggerrules.triggers.append(event)


def configure_wait(
    flight: Flight,
    group: FlyingGroup[Any],
    generated: list[tuple[FlightWaypoint, MovingPoint]],
) -> None:
    if not prerequisites.required_by(flight):
        return
    wait = next(
        (
            point
            for src, point in generated
            if src.waypoint_type is FlightWaypointType.PREREQUISITE_WAIT
        ),
        None,
    )
    landing = next(
        (
            point
            for src, point in generated
            if src.waypoint_type is FlightWaypointType.LANDING_POINT
        ),
        None,
    )
    # Fast-forward can spawn an AI group beyond the planned checkpoint. Its
    # first exported point is then the only remaining place to apply the wait.
    if wait is None and isinstance(flight.state, InFlight) and generated:
        if generated[0][0].waypoint_type is FlightWaypointType.LANDING_POINT:
            return
        wait = group.points[0]
    if wait is None or landing is None:
        raise ValueError(
            f"{prerequisites.flight_name(flight)} needs its prerequisite wait waypoint "
            "and a landing waypoint in its remaining route to wait for prerequisites."
        )

    key = flight.id
    speed = flight.unit_type.preferred_patrol_speed(meters(wait.alt))
    orbit = ControlledTask(
        OrbitAction(wait.alt, speed.kph, OrbitAction.OrbitPattern.Circle)
    )
    orbit.start_if_user_flag(f"end-wait-{key}", False)
    orbit.stop_if_user_flag(f"end-wait-{key}", True)
    # Use the generated indices, which take mid-flight starts and omitted points into account.
    command = f"""if trigger.misc.getUserFlag("{gate_flag(key)}") == {FAILURE} then
        local g = Group.getByName({lua_literal(group.name)})
        if g and g:isExist() then
            g:getController():setCommand({{id="SwitchWaypoint",params={{
                fromWaypointIndex={group.points.index(wait) + 1},
                goToWaypointIndex={group.points.index(landing) + 1}
            }}}})
        end
    end"""
    wait.tasks[:0] = [orbit, RunScript(command)]
