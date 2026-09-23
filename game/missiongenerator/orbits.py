"""The racetracks the blue side's tankers, AEW&C and CAPs fly in a mission.

Each of those flights orbits between two waypoints: the race-track start
(``PATROL_TRACK``) and the race-track end (``PATROL``). A recovery tanker has no fixed
racetrack -- it follows its carrier -- so it has no orbit here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dcs import Point

from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType
from game.utils import nautical_miles

if TYPE_CHECKING:
    from game.missiongenerator.aircraft.flightdata import FlightData
    from game.missiongenerator.missiondata import MissionData

SUPPORT_FLIGHT_TYPES = (FlightType.REFUELING, FlightType.AEWC)
CAP_FLIGHT_TYPES = (FlightType.BARCAP, FlightType.TARCAP)

#: Two CAP racetracks whose centres are this close, on the same course or its
#: reciprocal, are one station that more than one flight takes turns on.
SAME_STATION_DISTANCE_M = 15_000.0
SAME_STATION_COURSE_DEG = 25.0

#: The narrowest an orbit is shown, as the distance from the leg to the edge. A CAP
#: station is always shown this wide: a CAP leaves its racetrack to chase contacts,
#: so the shape marks the station rather than where the flight will be.
MIN_HALF_WIDTH_M = nautical_miles(2).meters

#: A tanker or AEW&C orbit is shown as wide as its turns need. The AI turns shallow
#: and overshoots the end of the leg before rolling in, so the half-width is the turn
#: radius at 20 degrees of bank plus 3 nm. The RetLab fork measured KC-135s up to
#: 19 km off the leg, an E-3A 13.8 km and an E-2C 8.9 km; this contains them.
TURN_BANK_DEG = 20.0
TURN_MARGIN_M = nautical_miles(3).meters


@dataclass(frozen=True)
class Orbit:
    """One flight's racetrack."""

    flight: FlightData
    start: Point
    end: Point

    @property
    def centre(self) -> tuple[float, float]:
        return (self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2

    @property
    def length_m(self) -> float:
        return self.start.distance_to_point(self.end)

    @property
    def course(self) -> float:
        """Compass course from start to end, in degrees. DCS x is north, y east."""
        if self.length_m < 1.0:
            return 0.0
        return (
            math.degrees(
                math.atan2(self.end.y - self.start.y, self.end.x - self.start.x)
            )
            % 360
        )

    @property
    def half_width(self) -> float:
        """How far either side of its leg a tanker or AEW&C is to be found."""
        speed = self.flight.patrol_speed
        if speed is None:
            return MIN_HALF_WIDTH_M
        v = speed.meters_per_second
        turn_radius = v * v / (9.81 * math.tan(math.radians(TURN_BANK_DEG)))
        return max(MIN_HALF_WIDTH_M, turn_radius + TURN_MARGIN_M)

    def box(self) -> tuple[tuple[float, float], ...]:
        """The rectangle round the orbit, aligned with its leg: four corners and the
        first one again, since no cockpit display closes a line by itself."""
        width = self.half_width
        half_length = self.length_m / 2 + width
        course = math.radians(self.course)
        along = (math.cos(course), math.sin(course))
        across = (-math.sin(course), math.cos(course))
        x, y = self.centre
        corners = [
            (
                x + along[0] * length + across[0] * side,
                y + along[1] * length + across[1] * side,
            )
            for length, side in (
                (half_length, width),
                (half_length, -width),
                (-half_length, -width),
                (-half_length, width),
            )
        ]
        return tuple(corners + corners[:1])


def orbit_of(flight: FlightData) -> Optional[Orbit]:
    """The flight's racetrack, or None when its route has no race-track pair."""
    start: Optional[Point] = None
    end: Optional[Point] = None
    for waypoint in flight.waypoints:
        if waypoint.waypoint_type == FlightWaypointType.PATROL_TRACK:
            start = waypoint.position
        elif waypoint.waypoint_type == FlightWaypointType.PATROL:
            end = waypoint.position
    if start is None or end is None:
        return None
    return Orbit(flight, start, end)


def _blue_orbits(
    mission_data: MissionData, types: tuple[FlightType, ...]
) -> list[Orbit]:
    orbits = []
    for flight in mission_data.flights:
        if flight.flight_type not in types or not flight.friendly.is_blue:
            continue
        orbit = orbit_of(flight)
        if orbit is not None:
            orbits.append(orbit)
    return orbits


def support_orbits(mission_data: MissionData) -> list[Orbit]:
    """Every blue tanker and AEW&C racetrack."""
    return _blue_orbits(mission_data, SUPPORT_FLIGHT_TYPES)


def tanker_orbits(mission_data: MissionData) -> list[Orbit]:
    """Every blue tanker racetrack."""
    return _blue_orbits(mission_data, (FlightType.REFUELING,))


def _same_station(first: Orbit, second: Orbit) -> bool:
    if math.dist(first.centre, second.centre) > SAME_STATION_DISTANCE_M:
        return False
    difference = abs(first.course - second.course) % 360
    difference = min(difference, 360 - difference)
    return min(difference, 180 - difference) <= SAME_STATION_COURSE_DEG


def cap_stations(mission_data: MissionData) -> list[Orbit]:
    """Every blue BARCAP and TARCAP station once, however many flights fly it.

    Flights relieving each other on a station plan racetracks a few miles apart, and
    sometimes in opposite directions. The first flight's racetrack stands for the
    station.
    """
    stations: list[Orbit] = []
    for orbit in _blue_orbits(mission_data, CAP_FLIGHT_TYPES):
        if not any(_same_station(orbit, station) for station in stations):
            stations.append(orbit)
    return stations
