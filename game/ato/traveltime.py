from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from game.utils import Distance, SPEED_OF_SOUND_AT_SEA_LEVEL, Speed, mach

if TYPE_CHECKING:
    from .flight import Flight
    from .package import Package


class GroundSpeed:
    @classmethod
    def for_flight(cls, flight: Flight, altitude: Distance) -> Speed:
        # TODO: Expose both a cruise speed and target speed.
        # The cruise speed can be used for ascent, hold, join, and RTB to save
        # on fuel, but mission speed will be fast enough to keep the flight
        # safer.

        # DCS's max speed is in kph at 0 MSL.
        max_speed = flight.unit_type.max_speed
        if max_speed > SPEED_OF_SOUND_AT_SEA_LEVEL:
            # Aircraft is supersonic. Limit to mach 0.85 to conserve fuel and
            # account for heavily loaded jets.
            return mach(0.85, altitude)

        # For subsonic aircraft, assume the aircraft can reasonably perform at
        # 80% of its maximum, and that it can maintain the same mach at altitude
        # as it can at sea level. This probably isn't great assumption, but
        # might. be sufficient given the wiggle room. We can come up with
        # another heuristic if needed.
        cruise_mach = max_speed.mach() * (0.7 if flight.is_helo else 0.85)
        return mach(cruise_mach, altitude)


# TODO: Most if not all of this should move into FlightPlan.
class TotEstimator:
    def __init__(self, package: Package) -> None:
        self.package = package

    #: How many times to re-measure after moving the TOT. Each flight's takeoff moves
    #: with the package, but not all of them one-for-one, so a single pass can still
    #: leave someone short. Three is plenty in practice and bounds the work.
    PUSH_PASSES = 3

    def earliest_tot(self, now: datetime) -> datetime:
        if not self.package.flights:
            return now

        tot = max(self.earliest_tot_for_flight(f, now) for f in self.package.flights)
        return self._pushed_until_everyone_can_start(tot, now)

    def _pushed_until_everyone_can_start(
        self, tot: datetime, now: datetime
    ) -> datetime:
        """Move the TOT later until no flight is asked to take off in the past.

        The estimate above works back from each flight plan's transit to its own TOT,
        which is right for anything that runs in on a target. A patrol in a package
        does not work that way: it takes its station time from the package's escort
        window rather than from the package TOT, so its takeoff can still land before
        the mission starts even when the estimate says there is room. Rather than model
        each kind of plan, ask the plans themselves and push until they are all content.
        """
        for _ in range(self.PUSH_PASSES):
            shortfall = self._largest_shortfall(tot, now)
            if shortfall <= timedelta():
                break
            tot += shortfall
        return tot

    def _largest_shortfall(self, tot: datetime, now: datetime) -> timedelta:
        """How far the earliest takeoff in the package falls before ``now``.

        Measured with ``tot`` standing in for the package's time over target. Flight
        plan times are derived from it on demand, so nothing has to be rebuilt; the
        original is restored whatever happens.
        """
        original = self.package.time_over_target
        worst = timedelta()
        try:
            self.package.time_over_target = tot
            for flight in self.package.flights:
                try:
                    takeoff = flight.flight_plan.takeoff_time()
                except Exception:
                    # A plan that cannot say yet is not a reason to refuse a TOT.
                    continue
                worst = max(worst, now - takeoff)
        finally:
            self.package.time_over_target = original
        return worst

    @staticmethod
    def earliest_tot_for_flight(flight: Flight, now: datetime) -> datetime:
        """Estimate the earliest time the flight can reach the target position.

        The interpretation of the TOT depends on the flight plan type. See the various
        FlightPlan implementations for details.

        Args:
            flight: The flight to get the earliest TOT for.
            now: The current mission time.

        Returns:
            The earliest possible TOT for the given flight.
        """
        flight_time = flight.flight_plan.minimum_duration_from_start_to_tot()
        # A flight is over the target at the package TOT plus its own offset, so one
        # asked to arrive early needs the package that much later.
        return now + flight_time - flight.flight_plan.tot_offset
