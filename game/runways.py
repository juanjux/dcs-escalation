"""Runway information and selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Optional, TYPE_CHECKING

from dcs.terrain.terrain import Airport, RunwayApproach

from game.atcdata import AtcData
from game.dcs.beacons import BeaconType, Beacons
from game.radio.radios import RadioFrequency
from game.radio.tacan import TacanChannel
from game.utils import Heading, Speed, knots, mps
from game.weather.conditions import Conditions

if TYPE_CHECKING:
    from game.dcs.beacons import Beacon
    from game.theater import ConflictTheater


#: Under this there is no headwind worth chasing, so the runway with the approach
#: aid is the one to use -- which is what a real field does in calm air, and what a
#: flight plan's approach course should be lined up with. Above it the wind decides,
#: as it did before.
CALM_WIND: Speed = knots(5)


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

        The wind decides, and where there is no wind to speak of the approach aid
        does: two knots of breeze used to be enough to send everybody to a runway
        with nothing on it, at a field whose instrument runway was sitting there
        unused.
        """
        runways = list(RunwayData.for_pydcs_airport(theater, airport))

        if mps(self.conditions.weather.wind.at_0m.speed) < CALM_WIND:
            instrument = [runway for runway in runways if runway.ils is not None]
            if instrument:
                # Still the most into what little wind there is, of the ones that
                # have the aid.
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
