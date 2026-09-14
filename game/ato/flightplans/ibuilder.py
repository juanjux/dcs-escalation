from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, Optional, TYPE_CHECKING, TypeVar

from game.navmesh import NavMeshError
from .flightplan import FlightPlan, Layout
from .planningerror import PlanningError
from ..packagewaypoints import PackageWaypoints

if TYPE_CHECKING:
    from game.coalition import Coalition
    from game.data.doctrine import Doctrine
    from game.theater import ConflictTheater, Player
    from game.threatzones import ThreatZones
    from ..flight import Flight
    from ..package import Package


FlightPlanT = TypeVar("FlightPlanT", bound=FlightPlan[Any])
LayoutT = TypeVar("LayoutT", bound=Layout)


class IBuilder(ABC, Generic[FlightPlanT, LayoutT]):
    #: The flight whose plan is being built right now, innermost first. A plan is
    #: allowed to read another flight's plan -- an escort reads the flight it escorts
    #: -- so builds do legitimately nest; this only exists so that a build that comes
    #: back round to a flight already on the stack can say who asked.
    _flight_being_planned: ClassVar[Optional[Flight]] = None

    #: Whether build() is on the stack for this builder. Declared here rather than in
    #: __init__ alone because builders are pickled into the save, and one restored from
    #: a save written before the guard existed has no instance attribute to read.
    _building: bool = False

    def __init__(self, flight: Flight) -> None:
        self.flight = flight
        self._flight_plan: FlightPlanT | None = None
        self.settings = self.flight.coalition.game.settings

    @property
    def existing_flight_plan(self) -> FlightPlanT | None:
        """The plan if one has been built, without building one to answer."""
        return self._flight_plan

    def get_or_build(self) -> FlightPlanT:
        if self._flight_plan is None:
            self.regenerate()
            assert self._flight_plan is not None
        return self._flight_plan

    def regenerate(self, dump_debug_info: bool = False) -> None:
        if self._building:
            # The plan is only assigned once build() returns, so a flight asked for its
            # own plan mid-build answers by building it again, forever. Stopping here
            # turns what was a stack overflow into a message the planner can show and
            # the player can read, naming both ends of the loop.
            raise PlanningError(
                f"Cannot plan {self.flight}: {self._flight_being_planned} asked for "
                f"its flight plan while that plan was still being built. The flight "
                f"plans in this package depend on each other in a cycle."
            )
        self._building = True
        outer = IBuilder._flight_being_planned
        IBuilder._flight_being_planned = self.flight
        try:
            self._generate_package_waypoints_if_needed(dump_debug_info)
            self._flight_plan = self.build(dump_debug_info)
        except NavMeshError as ex:
            color = "blue" if self.flight.squadron.player.is_blue else "red"
            raise PlanningError(
                f"Could not plan {color} {self.flight.flight_type.value} from "
                f"{self.flight.departure} to {self.package.target}"
            ) from ex
        finally:
            IBuilder._flight_being_planned = outer
            self._building = False

    def _generate_package_waypoints_if_needed(self, dump_debug_info: bool) -> None:
        # Package waypoints are only valid for offensive missions. Skip this if the
        # target is friendly.
        if self.package.target.is_friendly(self.is_player):
            return

        if self.package.waypoints_need_regeneration() or dump_debug_info:
            self.package.waypoints = PackageWaypoints.create(
                self.package, self.coalition, dump_debug_info
            )

    @property
    def theater(self) -> ConflictTheater:
        return self.flight.departure.theater

    @abstractmethod
    def build(self, dump_debug_info: bool = False) -> FlightPlanT: ...

    @property
    def package(self) -> Package:
        return self.flight.package

    @property
    def coalition(self) -> Coalition:
        return self.flight.coalition

    @property
    def is_player(self) -> Player:
        return self.coalition.player

    @property
    def doctrine(self) -> Doctrine:
        return self.coalition.doctrine

    @property
    def threat_zones(self) -> ThreatZones:
        return self.coalition.opponent.threat_zone
