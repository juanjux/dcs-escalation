import random
from datetime import datetime, timedelta
from typing import List

from dcs.point import MovingPoint
from dcs.task import (
    ControlledTask,
    EscortTaskAction,
    OptECMUsing,
    OptFormation,
    OptROE,
    Targets,
    SetUnlimitedFuelCommand,
)

from game.ato import FlightType
from game.data.doctrine import Doctrine
from game.theater import NavalControlPoint
from game.utils import nautical_miles, feet
from .pydcswaypointbuilder import PydcsWaypointBuilder


class JoinPointBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        # Unlimited fuel option : disable at racetrack start. Must be first option to work.
        if self.flight.squadron.coalition.game.settings.ai_unlimited_fuel:
            if waypoint.tasks and isinstance(
                waypoint.tasks[0], SetUnlimitedFuelCommand
            ):
                waypoint.tasks[0] = SetUnlimitedFuelCommand(False)
            else:
                waypoint.tasks.insert(0, SetUnlimitedFuelCommand(False))

        if self.flight.is_helo:
            waypoint.tasks.append(OptFormation.rotary_wedge())
        else:
            waypoint.tasks.append(OptFormation.finger_four_open())

        doctrine = self.flight.coalition.doctrine

        if self.flight.flight_type in (FlightType.ESCORT, FlightType.SEAD_ESCORT):
            # Escorts spawn at ReturnFire (see configure_escort): under OpenFire --
            # "engage ONLY designated targets" -- a pre-join escort has an empty
            # legal-target set and cannot even shoot back. The Escort ControlledTask
            # below is the first target designation, so escalate here, where escort
            # duty actually begins. The in-flight spawn path re-applies JOIN tasks to
            # a mid-mission spawn's first point, so late spawns pick this up too.
            waypoint.tasks.append(OptROE(OptROE.Values.OpenFire))

        if self.flight.flight_type == FlightType.ESCORT:
            targets = [
                Targets.All.Air.Planes.Fighters.id,
                Targets.All.Air.Planes.MultiroleFighters.id,
            ]
            if self.flight.is_helo:
                targets = [
                    Targets.All.Air.Helicopters.id,
                    Targets.All.GroundUnits.AirDefence.id,
                    Targets.All.GroundUnits.Infantry.id,
                    Targets.All.GroundUnits.GroundVehicles.ArmoredVehicles.id,
                    Targets.All.Naval.Ships.ArmedShips.LightArmedShips.id,
                ]
            self.configure_escort_tasks(
                waypoint,
                targets,
                max_dist=doctrine.escort_engagement_range.nautical_miles,
                vertical_spacing=doctrine.escort_spacing.feet,
            )

        elif self.flight.flight_type in [
            FlightType.SEAD_SWEEP,
            FlightType.SEAD,
            FlightType.SEAD_ESCORT,
            FlightType.DEAD,
        ]:
            settings = self.flight.coalition.game.settings
            # Read behind the plugin check, not before it: the EW jamming plugin is
            # gone, so the option does not exist and asking for it raised.
            if settings.plugins.get("ewrj") and settings.plugin_option_or(
                "ewrj.ai_jammer_enabled", False
            ):
                self.offensive_jamming(waypoint, "start")
                self.defensive_jamming(waypoint, "start")

            if self.flight.flight_type == FlightType.SEAD_ESCORT:
                self.handle_sead_escort(doctrine, waypoint)
                # Let the AI use ECM to preemptively defend themselves.
                ecm_option = OptECMUsing(
                    value=OptECMUsing.Values.UseIfDetectedLockByRadar
                )
                waypoint.tasks.append(ecm_option)
            else:
                # Let the AI use ECM to defend themselves.
                ecm_option = OptECMUsing(value=OptECMUsing.Values.UseIfOnlyLockByRadar)
                waypoint.tasks.append(ecm_option)
        elif not self.flight.flight_type.is_air_to_air:
            # Capture any non A/A type to avoid issues with SPJs that use the primary radar such as the F/A-18C.
            # You can bully them with STT to not be able to fire radar guided missiles at you,
            # so best choice is to not let them perform jamming for now.

            # Let the AI use ECM to defend themselves.
            ecm_option = OptECMUsing(value=OptECMUsing.Values.UseIfOnlyLockByRadar)
            waypoint.tasks.append(ecm_option)

    def handle_sead_escort(self, doctrine: Doctrine, waypoint: MovingPoint) -> None:
        if isinstance(self.flight.package.target, NavalControlPoint):
            self.configure_escort_tasks(
                waypoint,
                [
                    Targets.All.Naval.id,
                    Targets.All.GroundUnits.AirDefence.AAA.SAMRelated.id,
                ],
                max_dist=doctrine.sead_escort_engagement_range.nautical_miles,
                vertical_spacing=doctrine.sead_escort_spacing.feet,
            )
        else:
            self.configure_escort_tasks(
                waypoint,
                [Targets.All.GroundUnits.AirDefence.AAA.SAMRelated.id],
                max_dist=doctrine.sead_escort_engagement_range.nautical_miles,
                vertical_spacing=doctrine.sead_escort_spacing.feet,
            )

    def configure_escort_tasks(
        self,
        waypoint: MovingPoint,
        target_types: List[str],
        max_dist: float = 30.0,
        vertical_spacing: float = 2000.0,
    ) -> None:
        rx = (random.random() + 0.1) * 333
        ry = feet(vertical_spacing).meters
        rz = (random.random() + 0.1) * 166 * random.choice([-1, 1])
        pos = {"x": rx, "y": ry, "z": rz}
        engage_dist = int(nautical_miles(max_dist).meters)

        if self.flight.is_helo:
            for key in pos:
                pos[key] *= 0.25
            engage_dist = int(engage_dist * 0.25)

        group_id = None
        if self.package.primary_flight is not None:
            group_id = self.package.primary_flight.group_id

        escort = ControlledTask(
            EscortTaskAction(
                group_id=group_id,
                engagement_max_dist=engage_dist,
                targets=target_types,
                position=pos,
            )
        )

        escort.stop_if_user_flag(f"split-{id(self.package)}", True)

        handover = self.escort_handover()
        if handover is not None:
            escort.start_after_time(handover)

        waypoint.tasks.append(escort)

    def escort_handover(self) -> int | None:
        """When an escort flying *ahead* takes up station, in seconds from mission start.

        The DCS Escort task ties a flight to the one it protects from the join point
        on, so an escort given an "ahead" TOT offset used to spend the whole head
        start orbiting the join and cross the target with its package anyway. Pushing
        the formation station forward instead does not help: DCS clamps the offset and
        the flight ends up less than a minute in front (flown, 12-09-2026).

        Holding the task back does. The escort flies its own route and keeps the head
        start; the task takes over when the flight it protects reaches its ingress
        point, which is roughly where it would have picked it up anyway, so the attack
        and the way home are still covered.

        None for an escort that is not ahead of its package: it takes up station at
        the join as it always has.
        """
        if self.flight.flight_plan.tot_offset >= timedelta():
            return None
        handover = self._protected_ingress_time()
        if handover is None:
            return None
        elapsed = int((handover - self.now).total_seconds())
        # Not ahead of the mission start after all (a late-planned package, a flight
        # spawned in mid-air): escort from the join, as before.
        return elapsed if elapsed > 0 else None

    def _protected_ingress_time(self) -> datetime | None:
        """When the flight this escort protects reaches its ingress point."""
        primary = self.package.primary_flight
        if primary is not None and primary is not self.flight:
            ingress = getattr(primary.flight_plan, "ingress_time", None)
            if ingress is not None:
                return ingress
        # Nothing with an ingress to protect -- a tanker or an AWACS on a racetrack.
        # The escort's own ingress is the package's less the head start, so give the
        # head start back to find the moment the package gets there.
        own = getattr(self.flight.flight_plan, "ingress_time", None)
        if own is None:
            return None
        return own - self.flight.flight_plan.tot_offset
