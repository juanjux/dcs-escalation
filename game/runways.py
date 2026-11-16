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
from game.utils import Heading
from game.weather.conditions import Conditions

if TYPE_CHECKING:
    from game.dcs.beacons import Beacon
    from game.theater import ConflictTheater


# A small headwind component is treated as calm for runway selection.
MIN_RUNWAY_HEADWIND_MPS = 1.0


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

    def get_preferred_runway(
        self, theater: ConflictTheater, airport: Airport
    ) -> RunwayData:
        """Choose a runway using the surface wind component along its axis.

        When no runway has a meaningful headwind, use the calm-wind preference.
        Calm conditions and equal headwinds use ILS and then terrain data order.
        """
        runways = list(RunwayData.for_pydcs_airport(theater, airport))
        wind = self.conditions.weather.wind.at_0m
        if wind.speed >= MIN_RUNWAY_HEADWIND_MPS:
            headwinds = []
            for runway in runways:
                axis = runway_centerline(theater, airport, runway.runway_name)
                course = axis[1] if axis is not None else runway.runway_heading.degrees
                # DCS stores the direction of travel of the wind vector.
                headwind = -wind.speed * math.cos(math.radians(course - wind.direction))
                headwinds.append((runway, headwind))
            best_headwind = max(headwind for _, headwind in headwinds)
            if best_headwind >= MIN_RUNWAY_HEADWIND_MPS:
                runways = [
                    runway
                    for runway, headwind in headwinds
                    if math.isclose(headwind, best_headwind, abs_tol=1e-6)
                ]
        return next(
            (runway for runway in runways if runway.ils is not None), runways[0]
        )
