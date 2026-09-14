from __future__ import annotations

from datetime import datetime
from typing import Optional, Type, TYPE_CHECKING

from dcs.mapping import Point

from .airassault import AirAssaultLayout
from .airlift import AirliftLayout
from .formationattack import (
    FormationAttackBuilder,
    FormationAttackFlightPlan,
    FormationAttackLayout,
)
from .patrolling import PatrollingLayout
from .waypointbuilder import WaypointBuilder
from .. import FlightType
from ..packagewaypoints import PackageWaypoints
from ...utils import feet

if TYPE_CHECKING:
    from ..flight import Flight


class EscortFlightPlan(FormationAttackFlightPlan):
    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    @property
    def split_time(self) -> datetime:
        # Avoid infinite recursion when this escort flight is itself the primary flight
        # This can happen when only escort flights remain in a package
        if (
            self.package.primary_flight
            and self.package.primary_flight != self.flight
            and self.package.primary_flight.flight_plan
        ):
            return self.package.primary_flight.flight_plan.mission_departure_time
        else:
            return super().split_time


class Builder(FormationAttackBuilder[EscortFlightPlan, FormationAttackLayout]):
    @property
    def escorted_flight(self) -> Optional[Flight]:
        """The flight this escort is protecting, or None if there is nobody to protect.

        A package names its primary flight by mission-type priority and the escort
        types sit at the bottom of that list, so a package that holds nothing but
        escorts -- the first flight added to a new package, or one whose strikers were
        all cancelled -- elects an escort as its own primary. Reading that flight's
        plan while its plan is the one being built re-enters this builder, which is an
        unbounded recursion rather than a plan. An escort with nobody but itself (or
        another escort, which resolves back the same way) to escort protects nothing
        in particular, so it flies the package's ordinary geometry instead.
        """
        primary = self.package.primary_flight
        if primary is None or primary is self.flight:
            return None
        if primary.flight_type.is_escort_type:
            return None
        return primary

    def layout(self) -> FormationAttackLayout:
        non_formation_escort = False
        escorted = self.escorted_flight
        if self.package.waypoints_need_regeneration():
            self.package.waypoints = PackageWaypoints.create(
                self.package, self.coalition, dump_debug_info=False
            )
            if escorted:
                departure = escorted.flight_plan.layout.departure
                self.package.waypoints.join = departure.position.lerp(
                    self.package.target.position, 0.2
                )
                non_formation_escort = True

        assert self.package.waypoints is not None
        builder = WaypointBuilder(self.flight)
        ingress, target = builder.escort(
            self.package.waypoints.ingress, self.package.target
        )
        if non_formation_escort:
            target.position = self.package.waypoints.join
        ingress.only_for_player = True
        target.only_for_player = True
        hold = None
        if not (self.flight.is_helo or non_formation_escort):
            hold = builder.hold(self._hold_point())

        join_pos = (
            WaypointBuilder.perturb(self.package.waypoints.ingress, feet(500))
            if self.flight.is_helo
            else self.package.waypoints.join
        )
        join = builder.join(join_pos)

        split = builder.split(self._get_split())

        is_helo = builder.flight.is_helo

        # When escorting a flight that flies a racetrack orbit (AWACS/tanker), hold
        # on that racetrack so the escort actually co-locates with and protects it.
        # Otherwise the hold defaults to the package's target-relative geometry, which
        # can land 70-80 NM away from where the protected flight actually orbits.
        racetrack_hold = self._racetrack_hold_point(escorted)
        if racetrack_hold is not None:
            initial = builder.escort_hold(racetrack_hold)
        else:
            initial = builder.escort_hold(
                target.position if is_helo else self.package.waypoints.initial,
            )

        if escorted and escorted.flight_type in [
            FlightType.AIR_ASSAULT,
            FlightType.TRANSPORT,
        ]:
            layout = escorted.flight_plan.layout
            assert isinstance(layout, AirAssaultLayout) or isinstance(
                layout, AirliftLayout
            )
            if isinstance(layout, AirliftLayout):
                ascent = layout.pickup_ascent or layout.drop_off_ascent
                assert ascent is not None
                join = builder.join(ascent.position)
                if layout.pickup and layout.drop_off_ascent:
                    join = builder.join(layout.drop_off_ascent.position)
            split = builder.split(layout.arrival.position)
            if layout.drop_off:
                initial = builder.escort_hold(
                    layout.drop_off.position,
                )

        refuel = self._build_refuel(builder)

        departure = builder.takeoff(self.flight.departure)
        nav_to = builder.nav_path(
            hold.position if hold else departure.position,
            join.position,
            builder.get_cruise_altitude,
        )

        nav_from = builder.nav_path(
            refuel.position if refuel else split.position,
            self.flight.arrival.position,
            builder.get_cruise_altitude,
        )

        return FormationAttackLayout(
            departure=departure,
            hold=hold,
            nav_to=nav_to,
            join=join,
            ingress=ingress,
            initial=initial,
            targets=[target],
            split=split,
            refuel=refuel,
            nav_from=nav_from,
            arrival=builder.land(self.flight.arrival),
            divert=builder.divert(self.flight.divert),
            bullseye=builder.bullseye(),
            custom_waypoints=list(),
        )

    @staticmethod
    def _racetrack_hold_point(primary: Optional[Flight]) -> Optional[Point]:
        """Center of the protected flight's racetrack, if it flies one.

        AWACS and tanker flights orbit a racetrack that is stationed far from the
        package's target reference (70-80 NM beyond the threat boundary). Returning
        the racetrack center lets the escort hold on the orbit it is meant to
        protect, instead of at the unrelated target-relative escort-hold geometry.
        Returns None for non-racetrack primaries, leaving the default behaviour.
        """
        if primary is None:
            return None
        flight_plan = primary.flight_plan
        if not flight_plan.is_patrol(flight_plan):
            return None
        layout = flight_plan.layout
        assert isinstance(layout, PatrollingLayout)
        return layout.patrol_start.position.midpoint(layout.patrol_end.position)

    def build(self, dump_debug_info: bool = False) -> EscortFlightPlan:
        return EscortFlightPlan(self.flight, self.layout())
