"""Time player-planned attacks behind covering SEAD/DEAD packages.

Adapted from RetLab #1253 without its reconnaissance or scheduler dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.ato.traveltime import TotEstimator
from game.theater.theatergroundobject import IadsGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.ato import Package
    from game.theater import MissionTarget

SEAD_WINDOW_LEAD = timedelta(minutes=2)
SEAD_WINDOW_DURATION = timedelta(minutes=8)
SUPPRESSION_TASKS = frozenset({FlightType.SEAD, FlightType.DEAD})
COORDINATED_STRIKE_TYPES = frozenset(
    {
        FlightType.STRIKE,
        FlightType.BAI,
        FlightType.OCA_RUNWAY,
        FlightType.OCA_AIRCRAFT,
        FlightType.CAS,
    }
)
ORGANIC_SUPPRESSION = frozenset(
    {FlightType.SEAD, FlightType.SEAD_ESCORT, FlightType.SEAD_SWEEP}
)


@dataclass
class CoordinatedTot:
    tot: datetime
    behind: list[Package] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _ring_covers(site: MissionTarget, target: MissionTarget) -> bool:
    threat_range = getattr(site, "max_threat_range", None)
    if threat_range is None:
        return False
    ring = threat_range().meters
    return ring > 0 and site.position.distance_to_point(target.position) <= ring


def _covering_sams(package: Package) -> list[IadsGroundObject]:
    coalition = package.flights[0].coalition
    return [
        tgo
        for cp in coalition.game.theater.controlpoints
        if not cp.captured.is_neutral
        for tgo in cp.ground_objects
        if isinstance(tgo, IadsGroundObject)
        and not tgo.is_friendly(coalition.player)
        and not tgo.is_dead
        and tgo.has_live_radar_sam
        and _ring_covers(tgo, package.target)
    ]


def plan_coordinated_tot(
    package: Package,
    packages: Iterable[Package],
    now: datetime,
    mission_length: timedelta,
) -> CoordinatedTot:
    """Find a reachable suppression window, otherwise retain ASAP with warnings."""
    earliest = TotEstimator(package).earliest_tot(now)
    result = CoordinatedTot(earliest)
    if not package.flights or package.primary_task not in COORDINATED_STRIKE_TYPES:
        return result
    coalition = package.flights[0].coalition
    suppression = [
        p
        for p in packages
        if p is not package
        and p.flights
        and p.flights[0].coalition is coalition
        and p.primary_task in SUPPRESSION_TASKS
        and p.time_over_target != datetime.min
        and isinstance(p.target, IadsGroundObject)
        and not p.target.is_friendly(coalition.player)
        and not p.target.is_dead
    ]
    providers = [p for p in suppression if _ring_covers(p.target, package.target)]
    if providers:
        window_start = max(p.time_over_target for p in providers) + SEAD_WINDOW_LEAD
        window_end = window_start + SEAD_WINDOW_DURATION
        moved = max(earliest, window_start)
        if moved > now + mission_length:
            result.warnings.append(
                f"The SEAD window cannot be reached before the mission ends "
                f"({window_start:%H:%M} opening). Flying ASAP."
            )
        elif earliest > window_end:
            result.warnings.append(
                f"The SEAD window closes at {window_end:%H:%M}, before this "
                f"package can arrive ({earliest:%H:%M}). Flying ASAP."
            )
        else:
            result.tot = moved
            result.behind = providers
    if not any(f.flight_type in ORGANIC_SUPPRESSION for f in package.flights):
        suppressed = {id(p.target) for p in providers}
        for sam in _covering_sams(package):
            if id(sam) not in suppressed:
                result.warnings.append(
                    f"{sam.name}'s SAM ring covers the target with no SEAD or "
                    "DEAD package planned against it."
                )
    return result


def apply_tot_mode(
    package: Package,
    packages: Iterable[Package],
    now: datetime,
    mission_length: timedelta,
) -> CoordinatedTot | None:
    if package.auto_coordinated:
        plan = plan_coordinated_tot(package, packages, now, mission_length)
        package.time_over_target = plan.tot
        return plan
    if package.auto_asap:
        package.set_tot_asap(now)
    return None


def retime_coordinated_packages(game: Game) -> None:
    """Finalize suppression first, before flight states and the mission are built."""
    for coalition in (game.blue, game.red):
        packages = list(coalition.ato.packages)
        timed = [
            p
            for p in packages
            if p.auto_coordinated and p.flights and p.all_flights_waiting_for_start()
        ]
        timed.sort(key=lambda p: p.primary_task not in SUPPRESSION_TASKS)
        for package in timed:
            apply_tot_mode(
                package,
                packages,
                game.conditions.start_time,
                game.settings.desired_player_mission_duration,
            )
