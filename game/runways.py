"""Runway information and selection."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterator, Optional, TYPE_CHECKING

from dcs.terrain.terrain import Airport, RunwayApproach
from dcs.mapping import Point

from game.atcdata import AtcData
from game.dcs.beacons import BeaconType, Beacons
from game.radio.radios import RadioFrequency
from game.radio.tacan import TacanChannel
from game.utils import Heading, Speed, knots, mps
from game.weather.conditions import Conditions

if TYPE_CHECKING:
    from game.dcs.beacons import Beacon
    from game.theater import ConflictTheater


#: Below this there is no meaningful headwind to choose between runways, so the one
#: with an approach aid is preferred. Above it the wind decides.
CALM_WIND: Speed = knots(5)


def runway_centerline(
    theater: ConflictTheater, airport: Airport, runway_name: str
) -> Optional[tuple[Point, float]]:
    """Return a point on the selected runway axis and its precise grid course.

    A localizer at either end identifies the same runway centerline. Project the
    airport reference onto it so configured leg distances remain measured from
    the field, without carrying the reference point's lateral offset. Keep the
    nominal heading as a fallback when no surveyed DCS localizer is available.
    """
    for strip in airport.runways:
        approaches = (strip.main, strip.opposite)
        approach = next((r for r in approaches if r.name == runway_name), None)
        if approach is None:
            continue
        for end in (approach, *[r for r in approaches if r is not approach]):
            for aid in end.beacons:
                beacon = RunwayData._get_beacon(aid.id, theater)
                if beacon is None or beacon.beacon_type not in (
                    BeaconType.BEACON_TYPE_ILS_LOCALIZER,
                    BeaconType.BEACON_TYPE_PRMG_LOCALIZER,
                ):
                    continue
                x, z, direction = (
                    beacon.position_x,
                    beacon.position_z,
                    beacon.direction,
                )
                if x is None or z is None or direction is None:
                    continue
                if not all(math.isfinite(v) for v in (x, z, direction)):
                    continue
                course = min(
                    (direction % 360, (direction + 180) % 360),
                    key=lambda h: abs((h - approach.heading + 180) % 360 - 180),
                )
                if abs((course - approach.heading + 180) % 360 - 180) > 30:
                    continue
                origin = Point(x, z, theater.terrain)
                if origin.distance_to_point(airport.position) > 10000:
                    continue
                north, east = math.cos(math.radians(course)), math.sin(
                    math.radians(course)
                )
                along = (airport.position.x - x) * north + (
                    airport.position.y - z
                ) * east
                center = Point(x + along * north, z + along * east, theater.terrain)
                return center, course
    return None


@dataclass(frozen=True)
class RunwayData:
    airfield_name: str
    runway_heading: Heading
    runway_name: str
    atc: Optional[RadioFrequency] = None
    tacan: Optional[TacanChannel] = None
    tacan_callsign: Optional[str] = None
    ils: Optional[RadioFrequency] = None
    icls: Optional[int] = None
    link4: Optional[RadioFrequency] = None

    @classmethod
    def for_pydcs_runway_runway(
        cls,
        theater: ConflictTheater,
        airport: Airport,
        runway: RunwayApproach,
    ) -> RunwayData:
        """Creates RunwayData for the given runway of an airfield.

        Args:
            theater: The theater the airport is in.
            airport: The airfield the runway belongs to.
            runway: The pydcs runway.
        """
        atc: Optional[RadioFrequency] = None
        tacan: Optional[TacanChannel] = None
        tacan_callsign: Optional[str] = None
        ils: Optional[RadioFrequency] = None
        atc_radio = AtcData.from_pydcs(airport)
        if atc_radio is not None:
            atc = atc_radio.uhf

        for beacon_data in airport.beacons:
            beacon = cls._get_beacon(beacon_data.id, theater)
            if not beacon:
                continue
            if beacon.is_tacan:
                tacan = beacon.tacan_channel
                tacan_callsign = beacon.callsign

        for beacon_data in runway.beacons:
            beacon = cls._get_beacon(beacon_data.id, theater)
            if not beacon:
                continue
            if beacon.beacon_type is BeaconType.BEACON_TYPE_ILS_GLIDESLOPE:
                ils = beacon.frequency

        return cls(
            airfield_name=airport.name,
            runway_heading=Heading(runway.heading),
            runway_name=runway.name,
            atc=atc,
            tacan=tacan,
            tacan_callsign=tacan_callsign,
            ils=ils,
        )

    @staticmethod
    def _get_beacon(beacon_id: str, theater: ConflictTheater) -> Optional[Beacon]:
        try:
            beacon = Beacons.with_id(beacon_id, theater)
            return beacon
        except KeyError:
            # this means pydcs found a beacon in the "standlist"
            # but isn't present in beacons.lua file, which in turn causes problems...
            logging.error(f"Could not find data for '{beacon_id}', skipping beacon...")
            return None

    @classmethod
    def for_pydcs_airport(
        cls, theater: ConflictTheater, airport: Airport
    ) -> Iterator[RunwayData]:
        for runway in airport.runways:
            yield cls.for_pydcs_runway_runway(
                theater,
                airport,
                runway.main,
            )
            yield cls.for_pydcs_runway_runway(
                theater,
                airport,
                runway.opposite,
            )


class RunwayAssigner:
    def __init__(self, conditions: Conditions):
        self.conditions = conditions

    def angle_off_headwind(self, runway: RunwayData) -> Heading:
        wind = Heading.from_degrees(self.conditions.weather.wind.at_0m.direction)
        ideal_heading = wind.opposite
        return runway.runway_heading.angle_between(ideal_heading)

    def get_preferred_runway(
        self, theater: ConflictTheater, airport: Airport
    ) -> RunwayData:
        """Returns the preferred runway for the given airport.

        The wind decides. Below CALM_WIND there is no meaningful headwind to choose
        between runways, so an ILS-equipped runway is preferred instead: two knots of
        wind was otherwise enough to select a bare runway at a field whose instrument
        runway was unused.
        """
        runways = list(RunwayData.for_pydcs_airport(theater, airport))

        if mps(self.conditions.weather.wind.at_0m.speed) < CALM_WIND:
            instrument = [runway for runway in runways if runway.ils is not None]
            if instrument:
                # Of those, the one most into what wind there is.
                return min(instrument, key=lambda r: self.angle_off_headwind(r).degrees)

        # Find the runway with the best headwind first.
        best_runways = [runways[0]]
        best_angle_off_headwind = self.angle_off_headwind(best_runways[0])
        for runway in runways[1:]:
            angle_off_headwind = self.angle_off_headwind(runway)
            if angle_off_headwind == best_angle_off_headwind:
                best_runways.append(runway)
            elif angle_off_headwind < best_angle_off_headwind:
                best_runways = [runway]
                best_angle_off_headwind = angle_off_headwind

        for runway in best_runways:
            # But if there are multiple runways with the same heading,
            # prefer
            # and ILS capable runway.
            if runway.ils is not None:
                return runway

        # Otherwise the only difference between the two is the distance from
        # parking, which we don't know, so just pick the first one.
        return best_runways[0]
