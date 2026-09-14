from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, TYPE_CHECKING, TypeGuard, Optional

from game.typeguard import self_type_guard
from game.utils import Speed
from .flightplan import FlightPlan
from .loiter import LoiterFlightPlan, LoiterLayout
from ..flightwaypointtype import FlightWaypointType

if TYPE_CHECKING:
    from ..flightwaypoint import FlightWaypoint


@dataclass
class FormationLayout(LoiterLayout, ABC):
    join: FlightWaypoint
    split: FlightWaypoint
    refuel: Optional[FlightWaypoint]

    #: Which of the two the player has deleted, by name. They are kept rather than
    #: removed: every time in the plan is measured from them, and the package meets and
    #: parts there. They are only offered for deletion while the flight is the whole
    #: package -- where there is nothing to meet and they read as nav points -- and a
    #: second flight in the package puts them back in the route.
    dropped: set[str] = field(default_factory=set, kw_only=True)

    def drop(self, waypoint: FlightWaypoint) -> bool:
        """Take the join or the split out of the route. Says whether it was one."""
        for name in ("join", "split"):
            if waypoint is getattr(self, name):
                if not hasattr(self, "dropped"):
                    # Saved before this existed.
                    self.dropped = set()
                self.dropped.add(name)
                return True
        return False

    def is_droppable(self, waypoint: FlightWaypoint) -> bool:
        return waypoint is self.join or waypoint is self.split

    def dropped_waypoints(self) -> list[FlightWaypoint]:
        dropped = getattr(self, "dropped", ())
        return [getattr(self, name) for name in ("join", "split") if name in dropped]

    def label_formation_waypoints(self, alone_in_package: bool) -> None:
        """Name the join and the split for the size of the package.

        A flight that is the whole package has nobody to meet and nobody to leave, so
        calling those two points JOIN and SPLIT says something that is not happening.
        On its own they read as nav points, and they go back to being a join and a
        split the moment a second flight joins the package.

        Only the labels move. The package still meets and parts there, every time in
        the plan is measured from them, and the mission generator finds them through
        this layout rather than through the label -- so the tasks that hang off a join
        or a split, which are about the package and not about formation flying (the
        escort task, the flag that releases the escorts, jamming, unlimited fuel),
        are written exactly as before.
        """
        if not alone_in_package:
            # A join to fly to again, even if it was deleted while there was nothing
            # to join.
            getattr(self, "dropped", set()).clear()
        for waypoint, formation in (
            (
                self.join,
                ("JOIN", FlightWaypointType.JOIN, "Rendezvous with package", "Join"),
            ),
            (
                self.split,
                ("SPLIT", FlightWaypointType.SPLIT, "Depart from package", "Split"),
            ),
        ):
            name, kind, description, pretty_name = (
                ("NAV", FlightWaypointType.NAV, "NAV", "Nav")
                if alone_in_package
                else formation
            )
            waypoint.name = name
            waypoint.waypoint_type = kind
            waypoint.description = description
            waypoint.pretty_name = pretty_name

    def delete_waypoint(self, waypoint: FlightWaypoint) -> bool:
        if waypoint == self.refuel:
            self.refuel = None
            return True
        elif super().delete_waypoint(waypoint):
            return True
        return False


class FormationFlightPlan(LoiterFlightPlan, ABC):
    @property
    @abstractmethod
    def package_speed_waypoints(self) -> set[FlightWaypoint]: ...

    @property
    def combat_speed_waypoints(self) -> set[FlightWaypoint]:
        return self.package_speed_waypoints

    def request_escort_at(self) -> FlightWaypoint | None:
        return self.layout.join

    def dismiss_escort_at(self) -> FlightWaypoint | None:
        return self.layout.split

    @cached_property
    def best_flight_formation_speed(self) -> Speed:
        """The best speed this flight is capable at all formation waypoints.

        To ease coordination with other flights, we aim to have a single mission
        speed used by the formation for all waypoints. As such, this function
        returns the highest ground speed that the flight is capable of flying at
        all of its formation waypoints.
        """
        speeds = []
        for previous_waypoint, waypoint in self.edges():
            if waypoint in self.package_speed_waypoints:
                speeds.append(
                    self.best_speed_between_waypoints(previous_waypoint, waypoint)
                )
        return min(speeds)

    def speed_between_waypoints(self, a: FlightWaypoint, b: FlightWaypoint) -> Speed:
        if (
            speed := self.package.formation_speed(self.flight.is_helo)
        ) and b in self.package_speed_waypoints:
            return speed
        return super().speed_between_waypoints(a, b)

    @property
    def travel_time_to_rendezvous(self) -> timedelta:
        """The estimated time between the first waypoint and the join point."""
        return self._travel_time_to_waypoint(self.layout.join)

    @property
    @abstractmethod
    def join_time(self) -> datetime: ...

    @property
    @abstractmethod
    def split_time(self) -> datetime: ...

    def tot_for_waypoint(self, waypoint: FlightWaypoint) -> datetime | None:
        if waypoint == self.layout.join:
            return self.join_time
        elif waypoint == self.layout.split:
            return self.split_time
        return None

    @property
    def push_time(self) -> datetime:
        hold2join_time = (
            self.travel_time_between_waypoints(
                self.layout.hold,
                self.layout.join,
            )
            if self.layout.hold
            else timedelta(0)
        )
        return self.join_time - hold2join_time

    @property
    def mission_begin_on_station_time(self) -> datetime | None:
        return None

    @property
    def mission_departure_time(self) -> datetime:
        return self.split_time

    @self_type_guard
    def is_formation(
        self, flight_plan: FlightPlan[Any]
    ) -> TypeGuard[FormationFlightPlan]:
        return True
