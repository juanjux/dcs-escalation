from __future__ import annotations

from pydantic import BaseModel

from uuid import UUID

from game.ato import Flight, FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.flighttype import FlightType
from game.server.leaflet import LeafletPoint
from game.theater.theatergroundobject import TheaterGroundObject

#: What the flight is there for. A target is not somewhere the aircraft flies to and
#: then leaves from -- it releases at it, from wherever the run takes it -- so drawing
#: the route through it says something about the plan that is not true, and on a strike
#: with several aim points it says it several times over.
TARGET_TYPES = {
    FlightWaypointType.TARGET_POINT,
    FlightWaypointType.TARGET_GROUP_LOC,
    FlightWaypointType.TARGET_SHIP,
}

#: Waypoints whose altitude is not a height the flight flies at. A target's is the
#: ground it is standing on, and a takeoff's is the airfield: reporting "0 ft RADIO"
#: for either is a number that looks like a setting and is not one.
NO_ALTITUDE = TARGET_TYPES | {
    FlightWaypointType.TAKEOFF,
    FlightWaypointType.LANDING_POINT,
    FlightWaypointType.DIVERT,
    FlightWaypointType.PICKUP_ZONE,
    FlightWaypointType.DROPOFF_ZONE,
    FlightWaypointType.CARGO_STOP,
    FlightWaypointType.BULLSEYE,
}


def target_moves_the_mission(flight: Flight) -> bool:
    """Whether dragging this flight's target waypoint changes what it does.

    Armed recon hunts inside a circle centred on its own target waypoint, so moving
    it moves the search -- except against a motorpool, where the circle is pinned to
    the garage on purpose and moving the waypoint only changes where the aircraft
    flies over. Everything else attacks a group it was given rather than a place, so
    moving the mark says the plan changed when it has not.
    """
    from game.theater.theatergroundobject import MotorpoolGroundObject

    return flight.flight_type is FlightType.ARMED_RECON and not isinstance(
        flight.package.target, MotorpoolGroundObject
    )


def target_id_of(flight: Flight) -> UUID | None:
    """The objective this flight was sent against, when it is one the map knows.

    A front line or a convoy has no ground-object dialog to open, so it has no id
    here either, and the marker falls back to saying what it is.
    """
    target = flight.package.target
    if isinstance(target, TheaterGroundObject):
        return target.id
    return None


def timing_info(flight: Flight, waypoint_idx: int) -> str:
    if waypoint_idx == 0:
        return f"Depart T+{flight.flight_plan.takeoff_time():%H:%M:%S}"

    waypoint = flight.flight_plan.waypoints[waypoint_idx - 1]
    prefix = "TOT"
    time = flight.flight_plan.tot_for_waypoint(waypoint)
    if time is None:
        prefix = "Depart"
        time = flight.flight_plan.depart_time_for_waypoint(waypoint)
    if time is None:
        return ""
    return f"{prefix} {time:%H:%M:%S}"


def leg_speed(flight: Flight, waypoint_idx: int) -> float:
    """Knots on the leg into this waypoint, or 0 where there is no leg.

    The plan owns this: a package flies its formation speed between the join and the
    split whatever each flight would do alone, so asking the aircraft would be wrong.
    """
    if waypoint_idx < 1:
        return 0.0
    waypoints = flight.flight_plan.waypoints
    if waypoint_idx > len(waypoints):
        return 0.0
    destination = waypoints[waypoint_idx - 1]
    if waypoint_idx == 1:
        origin = FlightWaypoint(
            "TAKEOFF",
            FlightWaypointType.TAKEOFF,
            flight.departure.position,
        )
    else:
        origin = waypoints[waypoint_idx - 2]
    try:
        return float(
            flight.flight_plan.speed_between_waypoints(origin, destination).knots
        )
    except Exception:
        # A custom plan can be asked about a pair it has no opinion on. Nothing to
        # show is better than a dialog that will not open.
        return 0.0


class FlightWaypointJs(BaseModel):
    name: str
    position: LeafletPoint
    altitude_ft: float
    altitude_reference: str
    is_movable: bool
    should_mark: bool
    include_in_path: bool
    timing: str
    #: Its place in the route, which is how every other endpoint addresses it.
    index: int
    #: Whether the flight can give it up without its plan being rebuilt. The map
    #: refuses the ones it cannot rather than quietly degrading the plan.
    can_delete: bool
    #: What the flight flies the leg into this waypoint at. Computed from the plan --
    #: there is no per-waypoint speed to set -- so the dialog shows it and no more.
    speed_kts: float
    #: Whether this is what the flight came for. Marked rather than drawn through.
    is_target: bool
    #: The objective it is part of, when the map has a dialog for it. Double-clicking
    #: the mark opens that instead of a waypoint editor: what a player wants at a
    #: target is what is down there, not what altitude the waypoint claims.
    target_id: UUID | None
    #: Whether its altitude is a height the flight flies at rather than the ground.
    shows_altitude: bool

    class Config:
        title = "Waypoint"

    @staticmethod
    def for_waypoint(
        waypoint: FlightWaypoint, flight: Flight, waypoint_idx: int
    ) -> FlightWaypointJs:
        # Target *points* are the exact location of a unit, whereas the target area is
        # only the center of the objective. Allow moving the latter since its exact
        # location isn't very important.
        #
        # Landing, and divert should be changed in the flight settings UI, takeoff
        # cannot be changed because that's where the plane is.
        #
        # Moving the bullseye reference only makes it wrong.
        is_target = waypoint.waypoint_type in TARGET_TYPES

        is_movable = waypoint.waypoint_type not in {
            FlightWaypointType.BULLSEYE,
            FlightWaypointType.DIVERT,
            FlightWaypointType.LANDING_POINT,
            FlightWaypointType.TAKEOFF,
        }
        if is_target:
            is_movable = target_moves_the_mission(flight)

        # We don't need a marker for the departure waypoint (and it's likely
        # coincident with the landing waypoint, so hard to see). We do want to draw
        # the path from it though.
        #
        # We also don't need the landing waypoint since we'll be drawing that path
        # as well, and it's clear what it is, and only obscured the CP icon.
        #
        # The divert waypoint also obscures the CP. We don't draw the path to it,
        # but it can be seen in the flight settings page, so it's not really a
        # problem to exclude it.
        #
        # Bullseye ought to be (but currently isn't) drawn *once* rather than as a
        # flight waypoint.
        should_mark = waypoint.waypoint_type not in {
            FlightWaypointType.BULLSEYE,
            FlightWaypointType.DIVERT,
            FlightWaypointType.LANDING_POINT,
            FlightWaypointType.TAKEOFF,
        }

        include_in_path = not is_target and waypoint.waypoint_type not in {
            FlightWaypointType.BULLSEYE,
            FlightWaypointType.DIVERT,
        }

        return FlightWaypointJs(
            name=waypoint.display_name,
            position=waypoint.position.latlng(),
            altitude_ft=waypoint.alt.feet,
            altitude_reference=waypoint.alt_type,
            is_movable=is_movable,
            should_mark=should_mark,
            include_in_path=include_in_path,
            timing=timing_info(flight, waypoint_idx),
            index=waypoint_idx,
            # A target is what the package was fragged against; dropping one from
            # the map would quietly change the mission into a different one.
            can_delete=waypoint_idx > 0
            and not is_target
            and flight.flight_plan.can_delete_waypoint(waypoint),
            speed_kts=leg_speed(flight, waypoint_idx),
            is_target=is_target,
            target_id=target_id_of(flight) if is_target else None,
            shows_altitude=waypoint.waypoint_type not in NO_ALTITUDE,
        )
