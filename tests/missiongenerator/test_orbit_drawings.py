"""The blue tanker, AEW&C and CAP orbits drawn on the F10 map."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from dcs import Point
from dcs.drawing.drawings import StandardLayer
from dcs.mission import Mission
from dcs.terrain import Caucasus

from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType
from game.missiongenerator.drawingsgenerator import DrawingsGenerator
from game.missiongenerator.missiondata import AwacsInfo, TankerInfo
from game.missiongenerator.orbits import MIN_HALF_WIDTH_M, cap_stations
from game.radio.radios import MHz
from game.radio.tacan import TacanBand, TacanChannel
from game.theater import Player
from game.utils import Speed, knots


def _flight(
    mission: Mission,
    flight_type: FlightType,
    callsign: str,
    start: tuple[float, float],
    end: Optional[tuple[float, float]],
    side: Player = Player.BLUE,
    speed: Optional[Speed] = None,
) -> Any:
    terrain = mission.terrain
    waypoints = [
        SimpleNamespace(
            waypoint_type=FlightWaypointType.TAKEOFF, position=Point(0, 0, terrain)
        ),
        SimpleNamespace(
            waypoint_type=FlightWaypointType.PATROL_TRACK,
            position=Point(*start, terrain),
        ),
    ]
    if end is not None:
        waypoints.append(
            SimpleNamespace(
                waypoint_type=FlightWaypointType.PATROL, position=Point(*end, terrain)
            )
        )
    return SimpleNamespace(
        flight_type=flight_type,
        friendly=side,
        waypoints=waypoints,
        callsign=callsign,
        aircraft_type=SimpleNamespace(display_name="KC-135 Stratotanker"),
        group_name=f"{callsign} group",
        patrol_speed=speed,
    )


def _tanker_info(group_name: str) -> TankerInfo:
    return TankerInfo(
        group_name=group_name,
        callsign="Texaco",
        freq=MHz(251),
        blue=Player.BLUE,
        variant="KC-135 Stratotanker",
        tacan=TacanChannel(72, TacanBand.Y),
        start_time=None,  # type: ignore[arg-type]
        end_time=None,  # type: ignore[arg-type]
    )


def _awacs_info(group_name: str) -> AwacsInfo:
    return AwacsInfo(
        group_name=group_name,
        callsign="Overlord",
        freq=MHz(305),
        blue=Player.BLUE,
        depature_location=None,
        start_time=None,  # type: ignore[arg-type]
        end_time=None,  # type: ignore[arg-type]
        unit=None,  # type: ignore[arg-type]
    )


def _mission() -> Mission:
    return Mission(Caucasus())


def _generate(mission: Mission, flights: list[Any], **radios: Any) -> list[Any]:
    data = SimpleNamespace(
        flights=flights,
        tankers=radios.get("tankers", []),
        awacs=radios.get("awacs", []),
    )
    generator = DrawingsGenerator(mission, SimpleNamespace(), data)  # type: ignore[arg-type]
    generator.generate_cap_stations()
    generator.generate_support_orbits()
    return list(mission.drawings.get_layer(StandardLayer.Blue).objects)


def _texts(objects: list[Any]) -> list[str]:
    return [o.text for o in objects if hasattr(o, "text")]


def test_a_tanker_is_labelled_with_its_frequency_and_tacan() -> None:
    mission = _mission()
    tanker = _flight(
        mission, FlightType.REFUELING, "Texaco 1", (0, 0), (50_000, 0), speed=knots(300)
    )
    objects = _generate(mission, [tanker], tankers=[_tanker_info("Texaco 1 group")])
    assert [o.name for o in objects] == [
        "Texaco 1 orbit",
        "Texaco 1  KC-135 Stratotanker label",
    ]
    assert _texts(objects) == ["Texaco 1  KC-135 Stratotanker\n251 MHz AM  TCN 72Y"]


def test_an_awacs_has_no_tacan_to_give() -> None:
    mission = _mission()
    awacs = _flight(mission, FlightType.AEWC, "Overlord 1", (0, 0), (50_000, 0))
    objects = _generate(mission, [awacs], awacs=[_awacs_info("Overlord 1 group")])
    assert _texts(objects) == ["Overlord 1  KC-135 Stratotanker\n305 MHz AM"]


def test_an_orbit_with_no_radio_record_still_draws() -> None:
    mission = _mission()
    tanker = _flight(mission, FlightType.REFUELING, "Texaco 1", (0, 0), (50_000, 0))
    objects = _generate(mission, [tanker])
    assert _texts(objects) == ["Texaco 1  KC-135 Stratotanker"]


def test_only_blue_racetracks_are_drawn() -> None:
    mission = _mission()
    flights = [
        _flight(mission, FlightType.REFUELING, "Red 1", (0, 0), (1, 0), Player.RED),
        _flight(mission, FlightType.STRIKE, "Strike 1", (0, 0), (50_000, 0)),
        _flight(mission, FlightType.REFUELING, "Arco 1", (0, 0), None),
    ]
    assert _generate(mission, flights) == []


def test_a_faster_orbit_is_drawn_wider() -> None:
    mission = _mission()
    slow = _flight(
        mission, FlightType.REFUELING, "Slow 1", (0, 0), (50_000, 0), speed=knots(150)
    )
    fast = _flight(
        mission,
        FlightType.REFUELING,
        "Fast 1",
        (0, 200_000),
        (50_000, 200_000),
        speed=knots(450),
    )
    objects = _generate(mission, [slow, fast])

    def width(name: str) -> float:
        shape = next(o for o in objects if o.name == name)
        return max(abs(point.y) for point in shape.points)

    assert width("Slow 1 orbit") >= MIN_HALF_WIDTH_M - 1
    assert width("Fast 1 orbit") > width("Slow 1 orbit")


def test_relieving_caps_on_one_station_are_drawn_once() -> None:
    mission = _mission()
    first = _flight(mission, FlightType.BARCAP, "Colt 1", (0, 0), (40_000, 0))
    # The relief flies the same station a few miles off, the other way round.
    relief = _flight(mission, FlightType.BARCAP, "Colt 2", (43_000, 3_000), (2_000, 0))
    elsewhere = _flight(
        mission, FlightType.TARCAP, "Dodge 1", (0, 90_000), (0, 130_000)
    )
    data: Any = SimpleNamespace(flights=[first, relief, elsewhere])
    assert [s.flight.callsign for s in cap_stations(data)] == ["Colt 1", "Dodge 1"]
    assert _texts(_generate(mission, [first, relief, elsewhere])) == [
        "CAP Colt 1",
        "TARCAP Dodge 1",
    ]


def test_a_repeated_callsign_gets_a_name_of_its_own() -> None:
    mission = _mission()
    flights = [
        _flight(mission, FlightType.REFUELING, "Texaco 1", (0, 0), (1_000, 0)),
        _flight(
            mission, FlightType.REFUELING, "Texaco 1", (0, 90_000), (1_000, 90_000)
        ),
    ]
    names = [o.name for o in _generate(mission, flights)]
    assert names == [
        "Texaco 1 orbit",
        "Texaco 1  KC-135 Stratotanker label",
        "Texaco 1 orbit 2",
        "Texaco 1  KC-135 Stratotanker label 2",
    ]


def test_nothing_is_drawn_without_the_generated_flights() -> None:
    mission = _mission()
    generator = DrawingsGenerator(mission, SimpleNamespace())  # type: ignore[arg-type]
    generator.generate_cap_stations()
    generator.generate_support_orbits()
    assert mission.drawings.get_layer(StandardLayer.Blue).objects == []
