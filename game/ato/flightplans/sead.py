from __future__ import annotations

from datetime import timedelta
from typing import Type

from game.theater import TheaterGroundObject
from .formationattack import (
    FormationAttackBuilder,
    FormationAttackFlightPlan,
    FormationAttackLayout,
)
from ..flightwaypointtype import FlightWaypointType


class SeadFlightPlan(FormationAttackFlightPlan):
    @staticmethod
    def builder_type() -> Type[Builder]:
        return Builder

    def default_tot_offset(self) -> timedelta:
        return -timedelta(minutes=1)


class Builder(FormationAttackBuilder[SeadFlightPlan, FormationAttackLayout]):
    def layout(self) -> FormationAttackLayout:
        location = self.package.target
        # Only ground objectives expose individual units with coordinates (the
        # same list the SEAD kneeboard page renders). Against those, give each
        # listed emitter its own waypoint; against e.g. naval groups the kneeboard
        # lists no per-unit coordinates, so fall back to the single target area.
        targets = (
            self.sead_targets_for(location)
            if isinstance(location, TheaterGroundObject)
            else None
        )
        return self._build(FlightWaypointType.INGRESS_SEAD, targets)

    def build(self, dump_debug_info: bool = False) -> SeadFlightPlan:
        return SeadFlightPlan(self.flight, self.layout())
