from __future__ import annotations

from datetime import timedelta
from typing import Type

from game.theater import FrontLine
from game.utils import Distance, Speed, nautical_miles
from .capbuilder import CapBuilder
from .invalidobjectivelocation import InvalidObjectiveLocation
from .patrolling import PatrollingFlightPlan, PatrollingLayout
from .refuelneed import needs_refuelling
from .waypointbuilder import WaypointBuilder


class BarCapFlightPlan(PatrollingFlightPlan[PatrollingLayout]):
    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    @property
    def patrol_duration(self) -> timedelta:
        return self.flight.coalition.game.settings.desired_barcap_mission_duration

    @property
    def patrol_speed(self) -> Speed:
        return self.flight.unit_type.preferred_patrol_speed(
            self.layout.patrol_start.alt
        )

    @property
    def engagement_distance(self) -> Distance:
        return self.flight.coalition.doctrine.cap_engagement_range


class Builder(CapBuilder[BarCapFlightPlan, PatrollingLayout]):
    def layout(self) -> PatrollingLayout:
        location = self.package.target

        if isinstance(location, FrontLine):
            raise InvalidObjectiveLocation(self.flight.flight_type, location)

        start_pos, end_pos = self.cap_racetrack_for_objective(location, barcap=True)

        builder = WaypointBuilder(self.flight)
        patrol_alt = builder.get_patrol_altitude

        start, end = builder.race_track(start_pos, end_pos, patrol_alt)

        # A BARCAP orbits for hours, so its laps -- not the transit -- are most of what
        # it burns, and it is the flight type most likely to need a tanker. Judging it
        # on the way out and back alone said "it makes it" for a patrol that plainly
        # does not.
        refuel = None
        nav_from_origin = end.position
        settings = self.flight.coalition.game.settings
        hours = settings.desired_barcap_mission_duration.total_seconds() / 3600.0
        on_station = nautical_miles(
            self.flight.unit_type.preferred_patrol_speed(patrol_alt).knots * hours
        )
        meeting_point = self.package.refuel_point
        if meeting_point is not None and needs_refuelling(
            self.flight,
            self.package,
            settings,
            patrol_alt,
            patrol_alt,
            on_station,
        ):
            refuel = builder.refuel(meeting_point)
            nav_from_origin = refuel.position

        return PatrollingLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, start.position, patrol_alt
            ),
            nav_from=builder.nav_path(
                nav_from_origin, self.flight.arrival.position, patrol_alt
            ),
            patrol_start=start,
            patrol_end=end,
            refuel=refuel,
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    def build(self, dump_debug_info: bool = False) -> BarCapFlightPlan:
        return BarCapFlightPlan(self.flight, self.layout())
