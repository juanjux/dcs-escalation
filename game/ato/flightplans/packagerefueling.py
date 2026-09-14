from __future__ import annotations

from datetime import datetime, timedelta
from typing import Type

from dcs import Point

from game.utils import Distance, Heading, meters
from .ibuilder import IBuilder
from .planningerror import PlanningError
from .patrolling import PatrollingLayout
from .refuelingflightplan import RefuelingFlightPlan
from .waypointbuilder import WaypointBuilder
from ..flightwaypoint import FlightWaypoint
from ..flightwaypointtype import FlightWaypointType

#: How early the tanker is on station relative to when the package is calculated to
#: reach the refuelling point.
#:
#: It used to be ninety seconds, which assumed the calculation was right. It is not:
#: a flight that fought, took a longer route around a threat, or simply flew its legs
#: at a different speed arrives minutes out either way, and nearly always late. Ninety
#: seconds of slack means the tanker is still climbing, or already gone.
EARLY_BY = timedelta(minutes=10)


class PackageRefuelingFlightPlan(RefuelingFlightPlan):
    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    @property
    def patrol_duration(self) -> timedelta:
        """How long the tanker holds -- the campaign's figure, never less than the
        time the package itself needs.

        The old answer was only the second half of that: five minutes plus four a head
        for whoever is in the package, which for a single flight is ten minutes. A
        ten-minute window around an arrival time that is itself an estimate is a window
        the receiver misses most of the time. The campaign already has an opinion about
        how long a tanker should stay up -- the same one that decides how many tankers
        the auto-planner buys -- so use it, and keep the computed time as a floor for
        the case where a big package needs longer than that.
        """
        # TODO: Only consider aircraft that can refuel with this tanker type.
        refuel_time_minutes = 5
        # `for self.flight in ...` rebound the plan's OWN flight to the last one in
        # the package, so afterwards the tanker was timed and flown off some other
        # aircraft's figures -- patrol_speed, patrol_altitude, takeoff_time. It was
        # dormant while the auto-planner never produced this plan; it does now.
        for member in self.package.flights:
            flight_size = member.roster.max_size
            refuel_time_minutes = refuel_time_minutes + 4 * flight_size + 1

        needed = timedelta(minutes=refuel_time_minutes)
        configured = self.flight.coalition.game.settings.desired_tanker_on_station_time
        return max(needed, configured)

    def target_area_waypoint(self) -> FlightWaypoint:
        return FlightWaypoint(
            "TARGET AREA",
            FlightWaypointType.TARGET_GROUP_LOC,
            self.package.target.position,
            meters(0),
            "RADIO",
        )

    @property
    def patrol_start_time(self) -> datetime:
        altitude = self.flight.unit_type.patrol_altitude

        if altitude is None:
            altitude = Distance.from_feet(20000)

        # Cheat in a FlightWaypoint for the refuel point.
        meeting_point = self.package.refuel_point
        if meeting_point is None:
            raise PlanningError(
                "Cannot plan a tanker for a package with nowhere to meet it"
            )
        refuel: Point = meeting_point
        refuel_waypoint: FlightWaypoint = FlightWaypoint(
            "REFUEL", FlightWaypointType.REFUEL, refuel, altitude
        )

        target_area = self.target_area_waypoint()
        package_waypoints = self.package.waypoints
        if package_waypoints is None:
            # A defensive package -- a BARCAP over a friendly base -- has no split
            # point, because it has no package geometry at all. Its receivers come
            # straight back from what they were covering.
            delay: timedelta = self.total_time_between_waypoints(
                target_area, refuel_waypoint
            )
        else:
            split_waypoint: FlightWaypoint = FlightWaypoint(
                "SPLIT", FlightWaypointType.SPLIT, package_waypoints.split, altitude
            )
            delay = self.total_time_between_waypoints(
                target_area, split_waypoint
            ) + self.total_time_between_waypoints(split_waypoint, refuel_waypoint)

        return self.package.time_over_target + delay - EARLY_BY


class Builder(IBuilder[PackageRefuelingFlightPlan, PatrollingLayout]):
    def layout(self) -> PatrollingLayout:
        racetrack_half_distance = Distance.from_nautical_miles(20).meters

        racetrack_center = self.package.refuel_point
        if racetrack_center is None:
            raise PlanningError(
                "Cannot plan a tanker for a package with nowhere to meet it"
            )

        # The track lies along the direction the receivers come home from, so they
        # meet it head-on rather than across it. A defensive package has no split
        # point to take that direction from -- no package geometry is solved for one --
        # so it comes from what the package is covering instead.
        package_waypoints = self.package.waypoints
        toward = (
            package_waypoints.split
            if package_waypoints is not None
            else self.package.target.position
        )
        split_heading = Heading.from_degrees(
            racetrack_center.heading_between_point(toward)
        )
        home_heading = split_heading.opposite

        racetrack_start = racetrack_center.point_from_heading(
            split_heading.degrees, racetrack_half_distance
        )

        racetrack_end = racetrack_center.point_from_heading(
            home_heading.degrees, racetrack_half_distance
        )

        builder = WaypointBuilder(self.flight)

        altitude = builder.get_patrol_altitude

        racetrack = builder.race_track(racetrack_start, racetrack_end, altitude)

        return PatrollingLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, racetrack_start, altitude
            ),
            nav_from=builder.nav_path(
                racetrack_end, self.flight.arrival.position, altitude
            ),
            patrol_start=racetrack[0],
            patrol_end=racetrack[1],
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    def build(self, dump_debug_info: bool = False) -> PackageRefuelingFlightPlan:
        return PackageRefuelingFlightPlan(self.flight, self.layout())
