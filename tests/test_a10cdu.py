"""The A-10's navigation computer, written into the mission.

It has no cartridge, so the saved points go where "Prepare Mission" puts the cockpit:
Avionics/<type>/<unit>/CDU/SETTINGS.lua. Everything pinned here was measured against
DCS's own output rather than read off a document, because there is no document.
"""

from __future__ import annotations

import re
import zipfile
import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest
from dcs.lua import loads

from game.ato.savedpoints import PointKind, SavedPoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.flightwaypoint import FlightWaypoint
from dcs.mapping import Point
from dcs.terrain import Caucasus
from game.missiongenerator import a10cdu
from game.missiongenerator.kneeboard import (
    FlightPlanBuilder,
    SeadTaskPage,
    StrikeTaskPage,
)
from game.utils import NauticalUnits, meters


class _Terrain:
    """Enough of one to turn a position into a latitude and a longitude."""

    name = "Caucasus"


def _latlng(x: float, y: float) -> Any:
    return SimpleNamespace(lat=42.0 + x / 100000.0, lng=42.0 + y / 100000.0)


def _waypoint(name: str, x: float, y: float) -> Any:
    return SimpleNamespace(
        display_name=name,
        position=SimpleNamespace(x=x, y=y),
        alt=SimpleNamespace(meters=0.0),
    )


def _point(name: str, x: float = 1000.0, y: float = 2000.0) -> SavedPoint:
    return SavedPoint(kind=PointKind.WAYPOINT, name=name, x=x, y=y)


def _flight(
    aircraft: str = "A-10C_2",
    route: int = 4,
    saved: Optional[list[SavedPoint]] = None,
    crewed: int = 1,
) -> Any:
    return SimpleNamespace(
        aircraft_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=aircraft)),
        client_units=[SimpleNamespace(id=7)] * crewed,
        units=[SimpleNamespace(id=7)],
        waypoints=[_waypoint(f"LEG{n}", float(n), float(n)) for n in range(route)],
        saved_points=saved if saved is not None else [],
    )


def _settings(flight: Any, monkeypatch: Any) -> str:
    monkeypatch.setattr(
        a10cdu,
        "Point",
        lambda x, y, terrain: SimpleNamespace(latlng=lambda: _latlng(x, y)),
    )
    return a10cdu.settings(flight, _Terrain())


@pytest.fixture(autouse=True)
def ground_height(monkeypatch: Any) -> None:
    """Tests must not query the public elevation service."""
    monkeypatch.setattr(a10cdu, "elevation_m", lambda lat, lng: 123.5)


# ------------------------------------------------- where it goes and what is in it


def test_it_goes_where_prepare_mission_puts_the_cockpit() -> None:
    assert a10cdu.inside_mission(_flight()) == "Avionics/A-10C_2/7/CDU/SETTINGS.lua"


def test_the_terrain_system_is_switched_on(monkeypatch: Any) -> None:
    """Without it every waypoint in the aircraft reads EL: *****, whatever else the
    file says. It is what gives a point the height of the ground under it."""
    written = _settings(_flight(saved=[_point("SMOKE")]), monkeypatch)

    assert '["dtsas_func"]=1' in written
    assert '["dtsas_cr"]=1' in written


def test_route_elevations_are_written_without_relying_on_terrain_ranging(
    monkeypatch: Any,
) -> None:
    flight = _flight(saved=[_point("SMOKE")])
    flight.waypoints[1].alt = meters(6000)
    written = loads(_settings(flight, monkeypatch))["settings"]["waypoints"]

    for slot in range(1, 5):
        assert written[slot]["wpt_elev"] == 123.5
        assert written[slot]["wpt_elev_present"] == 1
        assert written[slot]["wpt_cr"] == 0


@pytest.mark.parametrize("height_ft", [0, 1234, -100])
def test_saved_points_keep_their_entered_msl_elevations(
    monkeypatch: Any, height_ft: int
) -> None:
    point = _point("SMOKE")
    point.altitude_ft = height_ft
    written = loads(_settings(_flight(saved=[point]), monkeypatch))["settings"]
    assert written["waypoints"][5]["wpt_elev"] == pytest.approx(height_ft * 0.3048)
    assert written["waypoints"][5]["wpt_elev_present"] == 1


def test_missing_ground_height_does_not_claim_an_elevation_is_present(
    monkeypatch: Any, caplog: Any
) -> None:
    monkeypatch.setattr(a10cdu, "elevation_m", lambda lat, lng: None)
    written = loads(_settings(_flight(saved=[_point("SMOKE")]), monkeypatch))
    waypoint = written["settings"]["waypoints"][1]
    assert "wpt_elev" not in waypoint
    assert waypoint["wpt_elev_present"] == 0
    assert waypoint["wpt_cr"] == 1
    assert "No ground elevation" in caplog.text


def test_underwater_ground_height_is_clamped_to_sea_level(monkeypatch: Any) -> None:
    monkeypatch.setattr(a10cdu, "elevation_m", lambda lat, lng: -30)
    written = loads(_settings(_flight(saved=[_point("SEA")]), monkeypatch))
    assert written["settings"]["waypoints"][1]["wpt_elev"] == 0


def test_the_saved_points_get_a_flight_plan_of_their_own(monkeypatch: Any) -> None:
    """Plan 1 is the mission route and cannot be overridden -- measured -- so what
    keeps the route clean is the points not being on it."""
    written = _settings(
        _flight(route=5, saved=[_point("SMOKE"), _point("SHIP")]), monkeypatch
    )

    assert '["fp_name"]="EXTRA"' in written
    assert re.findall(r'\["wpt_number"\]=(\d+)', written) == ["6", "7"]


def test_a_flight_with_nothing_written_down_gets_no_plan(monkeypatch: Any) -> None:
    written = _settings(_flight(), monkeypatch)

    assert "flight_plans" not in written


# ------------------------------------------------------------- the numbering


def test_a_saved_point_follows_the_route(monkeypatch: Any) -> None:
    """The aircraft numbers a waypoint by its place in the table, not by the wpt_num
    written beside it, and the route counts from 0."""
    assert a10cdu.numbers_for(5, 2) == [6, 7]
    assert a10cdu.numbers_for(0, 3) == [1, 2, 3]


def test_the_route_keeps_its_own_numbers(monkeypatch: Any) -> None:
    written = _settings(_flight(route=3, saved=[_point("SMOKE")]), monkeypatch)
    numbers = re.findall(r'\["wpt_num"\]=(\d+)', written)

    assert numbers == ["1", "2", "3", "4"]


def test_the_first_route_point_is_the_aircraft_itself(monkeypatch: Any) -> None:
    written = _settings(_flight(route=2), monkeypatch)

    assert '["wpt_id"]="INIT POSIT"' in written


@pytest.mark.parametrize("aircraft", ["A-10C", "A-10C_2", "FA-18C_hornet"])
@pytest.mark.parametrize("saved", [False, True])
def test_kneeboard_numbers_follow_the_exported_database(
    monkeypatch: Any, aircraft: str, saved: bool
) -> None:
    flight = _flight(aircraft=aircraft, saved=[_point("EXTRA")] if saved else [])
    terrain = Caucasus()
    kinds = (
        [
            FlightWaypointType.TAKEOFF,
            FlightWaypointType.LOITER,
            FlightWaypointType.NAV,
            FlightWaypointType.INGRESS_STRIKE,
        ]
        + [FlightWaypointType.TARGET_POINT] * 9
        + [FlightWaypointType.LANDING_POINT]
    )
    flight.waypoints = [
        FlightWaypoint(
            name=f"POINT{index}",
            pretty_name=f"POINT{index}",
            waypoint_type=kind,
            position=Point(index * 1000, index * 1000, terrain),
        )
        for index, kind in enumerate(kinds)
    ]
    first = 1 if aircraft in a10cdu.AIRCRAFT and saved else 0
    numbers = list(a10cdu.route_numbers(flight))
    assert numbers == list(range(first, first + len(kinds)))

    builder = FlightPlanBuilder(datetime.datetime(2026, 1, 1), NauticalUnits())
    for number, waypoint in zip(numbers, flight.waypoints):
        builder.add_waypoint(number, waypoint)
    rows = builder.build()
    assert rows[3][0] == str(3 + first)  # ingress
    assert rows[4][0] == f"{4 + first}-{12 + first}"

    strike = list(StrikeTaskPage(flight, False).targets)
    assert [target.number for target in strike] == list(range(4 + first, 13 + first))
    sead = SeadTaskPage(flight, False)._waypoint_number_by_position()
    assert list(sead.values()) == list(range(4 + first, 13 + first))

    if first:
        cdu = loads(_settings(flight, monkeypatch))["settings"]["waypoints"]
        for target in strike:
            assert cdu[target.number]["wpt_num"] == target.number
            assert cdu[target.number]["wpt_id"] == target.waypoint.display_name
        assert a10cdu.numbers_for(len(kinds), 1) == [len(kinds) + 1]


# ------------------------------------------------------------------- the names


def test_a_name_is_cut_to_what_the_cdu_shows(monkeypatch: Any) -> None:
    written = _settings(_flight(saved=[_point("A very long name indeed")]), monkeypatch)

    assert '["wpt_id"]="A VERY LONG "' in written


def test_a_point_with_no_usable_name_still_gets_one(monkeypatch: Any) -> None:
    written = _settings(_flight(route=2, saved=[_point("¿¿¿")]), monkeypatch)

    assert '["wpt_id"]="PT3"' in written


# ---------------------------------------------------------- into the mission


def test_only_a_crewed_a10_with_points_is_written(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        a10cdu,
        "Point",
        lambda x, y, terrain: SimpleNamespace(latlng=lambda: _latlng(x, y)),
    )
    mission = tmp_path / "turn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    data = SimpleNamespace(
        flights=[
            _flight(saved=[_point("SMOKE")]),
            _flight(saved=[_point("SHIP")], crewed=0),  # nobody in it
            _flight(),  # nothing written down
            _flight(
                aircraft="FA-18C_hornet", saved=[_point("SMOKE")]
            ),  # has a cartridge
        ]
    )
    game = SimpleNamespace(theater=SimpleNamespace(terrain=_Terrain()))

    written = a10cdu.write_into_mission(cast(Any, game), data, mission)

    assert written == ["Avionics/A-10C_2/7/CDU/SETTINGS.lua"]
    with zipfile.ZipFile(mission) as archive:
        assert "mission" in archive.namelist()
        assert '["fp_name"]="EXTRA"' in archive.read(written[0]).decode("utf-8")


def test_nothing_to_write_leaves_the_mission_alone(tmp_path: Path) -> None:
    mission = tmp_path / "turn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    game = SimpleNamespace(theater=SimpleNamespace(terrain=_Terrain()))

    assert (
        a10cdu.write_into_mission(cast(Any, game), SimpleNamespace(flights=[]), mission)
        == []
    )

    with zipfile.ZipFile(mission) as archive:
        assert archive.namelist() == ["mission"]
