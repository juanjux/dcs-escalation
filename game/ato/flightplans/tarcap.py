from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Type

from game.utils import Distance, Speed, nautical_miles
from .capbuilder import CapBuilder
from .refuelneed import needs_refuelling
from .patrolling import PatrollingFlightPlan, PatrollingLayout
from .waypointbuilder import WaypointBuilder

if TYPE_CHECKING:
    from ..flightwaypoint import FlightWaypoint


@dataclass
class TarCapLayout(PatrollingLayout):
    """Kept as its own type only so the plan class can be parameterised on it.

    The refuel slot, and the waypoint ordering that carries it, now belong to every
    patrol (:class:`PatrollingLayout`), so there is nothing left to add here.
    """


class TarCapFlightPlan(PatrollingFlightPlan[TarCapLayout]):
    @property
    def patrol_duration(self) -> timedelta:
        # Only has an effect when no flight in the package has requested an escort. If
        # one has, the CAP stays for as long as the escorted mission does, or until it
        # is winchester or bingo.
        #
        # Its own setting rather than the BARCAP one: a BARCAP guards a base for hours
        # and a TARCAP covers an attack. It used to read doctrine.cap_duration, which is
        # a flat 30 minutes in all three doctrines -- Doctrine.from_settings does map
        # the BARCAP setting onto it, but nothing has ever called that method, so the
        # number a player typed never reached a TARCAP.
        return self.flight.coalition.game.settings.desired_tarcap_mission_duration

    @property
    def patrol_speed(self) -> Speed:
        return self.flight.unit_type.preferred_patrol_speed(
            self.layout.patrol_start.alt
        )

    @property
    def engagement_distance(self) -> Distance:
        return self.flight.coalition.doctrine.cap_engagement_range

    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    @property
    def combat_speed_waypoints(self) -> set[FlightWaypoint]:
        return {self.layout.patrol_start, self.layout.patrol_end}

    def default_tot_offset(self) -> timedelta:
        return -timedelta(minutes=2)

    def depart_time_for_waypoint(self, waypoint: FlightWaypoint) -> datetime | None:
        if waypoint == self.layout.patrol_end:
            return self.patrol_end_time
        return super().depart_time_for_waypoint(waypoint)

    @property
    def patrol_start_time(self) -> datetime:
        start = self.package.escort_start_time
        if start is not None:
            return start + self.tot_offset
        return self.tot

    @property
    def patrol_end_time(self) -> datetime:
        end = self.package.escort_end_time
        if end is not None:
            return end
        return super().patrol_end_time


class Builder(CapBuilder[TarCapFlightPlan, TarCapLayout]):
    def layout(self) -> TarCapLayout:
        location = self.package.target

        builder = WaypointBuilder(self.flight)
        patrol_alt = builder.get_patrol_altitude

        orbit0p, orbit1p = self.cap_racetrack_for_objective(location, barcap=False)

        start, end = builder.race_track(orbit0p, orbit1p, patrol_alt)

        refuel = None
        nav_from_origin = orbit1p

        # TARCAP asked for neither a helicopter check nor a tanker in the air wing,
        # so it was the one plan that added the waypoint unconditionally.
        #
        # Its laps are most of what it burns: a patrol judged on the way out and back
        # alone comes out at about half its real need, which is the one flight type
        # that most often does want a tanker.
        settings = self.flight.coalition.game.settings
        hours = settings.desired_tarcap_mission_duration.total_seconds() / 3600.0
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

        return TarCapLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, orbit0p, patrol_alt
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

    def build(self, dump_debug_info: bool = False) -> TarCapFlightPlan:
        return TarCapFlightPlan(self.flight, self.layout())
