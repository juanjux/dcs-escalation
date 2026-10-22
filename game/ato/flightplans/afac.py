"""Non-attacking search patrols over a selected area or frontline segment."""

from __future__ import annotations

from datetime import timedelta
from typing import Type

from game.ato.afac import enabled, station_minutes
from game.ato.flighttype import FlightType
from game.theater import FrontLine
from game.utils import Distance, Speed, knots, nautical_miles
from .ibuilder import IBuilder
from .invalidobjectivelocation import InvalidObjectiveLocation
from .patrolling import PatrollingFlightPlan, PatrollingLayout
from .uizonedisplay import UiZone
from .waypointbuilder import WaypointBuilder


class AfacFlightPlan(PatrollingFlightPlan[PatrollingLayout]):
    @property
    def patrol_duration(self) -> timedelta:
        return timedelta(minutes=station_minutes(self.flight.coalition.game.settings))

    @property
    def patrol_speed(self) -> Speed:
        return self.flight.unit_type.preferred_patrol_speed(
            self.layout.patrol_start.alt
        ) or knots(70 if self.flight.is_helo else 160)

    @property
    def engagement_distance(self) -> Distance:
        settings = self.flight.coalition.game.settings
        return nautical_miles(
            settings.cas_engagement_range_distance
            if self.flight.flight_type is FlightType.AFAC_FRONTLINE
            else settings.armed_recon_engagement_range_distance
        )

    def ui_zone(self) -> UiZone:
        if self.flight.flight_type is FlightType.AFAC_FRONTLINE:
            return UiZone(
                [self.layout.patrol_start.position, self.layout.patrol_end.position],
                self.engagement_distance,
            )
        midpoint = (
            self.layout.patrol_start.position + self.layout.patrol_end.position
        ) / 2
        return UiZone([midpoint], self.engagement_distance)

    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder


class Builder(IBuilder[AfacFlightPlan, PatrollingLayout]):
    def layout(self) -> PatrollingLayout:
        settings = self.coalition.game.settings
        if not enabled(settings):
            raise ValueError(
                "AFAC requires Realistic CAS and AFAC search missions enabled"
            )
        target = self.package.target
        if self.flight.flight_type is FlightType.AFAC_FRONTLINE:
            if not isinstance(target, FrontLine):
                raise InvalidObjectiveLocation(self.flight.flight_type, target)
            from game.missiongenerator.frontlineconflictdescription import (
                FrontLineConflictDescription,
            )

            bounds = FrontLineConflictDescription.frontline_bounds(target, self.theater)
            start, end = bounds.left_position, bounds.right_position
        else:
            radius = nautical_miles(
                settings.armed_recon_engagement_range_distance
            ).meters
            start = target.position.point_from_heading(270, radius * 0.5)
            end = target.position.point_from_heading(90, radius * 0.5)
        if end.distance_to_point(
            self.flight.departure.position
        ) < start.distance_to_point(self.flight.departure.position):
            start, end = end, start
        builder = WaypointBuilder(self.flight)
        altitude = builder.get_combat_altitude
        points = builder.race_track(start, end, altitude)
        # The native racetrack only navigates. It receives no CAS or attack task.
        for point, label in zip(points, ("SEARCH START", "SEARCH END")):
            point.name = point.pretty_name = label
            point.description = "AFAC search patrol"
        return PatrollingLayout(
            departure=builder.takeoff(self.flight.departure),
            nav_to=builder.nav_path(
                self.flight.departure.position, start, altitude, self.flight.is_helo
            ),
            nav_from=builder.nav_path(
                end, self.flight.arrival.position, altitude, self.flight.is_helo
            ),
            patrol_start=points[0],
            patrol_end=points[1],
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=[],
        )

    def build(self, dump_debug_info: bool = False) -> AfacFlightPlan:
        return AfacFlightPlan(self.flight, self.layout())
