"""The A-10's navigation computer, written into the mission.

It has no cartridge, so the saved points go where "Prepare Mission" puts the cockpit:
Avionics/<type>/<unit>/CDU/SETTINGS.lua. Everything pinned here was measured against
DCS's own output rather than read off a document, because there is no document.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

from game.ato.savedpoints import PointKind, SavedPoint
from game.missiongenerator import a10cdu


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


# ------------------------------------------------- where it goes and what is in it


def test_it_goes_where_prepare_mission_puts_the_cockpit() -> None:
    assert a10cdu.inside_mission(_flight()) == "Avionics/A-10C_2/7/CDU/SETTINGS.lua"


def test_the_terrain_system_is_switched_on(monkeypatch: Any) -> None:
    """Without it every waypoint in the aircraft reads EL: *****, whatever else the
    file says. It is what gives a point the height of the ground under it."""
    written = _settings(_flight(saved=[_point("SMOKE")]), monkeypatch)

    assert '["dtsas_func"]=1' in written
    assert '["dtsas_cr"]=1' in written


def test_no_elevation_is_written(monkeypatch: Any) -> None:
    """The aircraft recomputes it from the terrain and ignores what the file says,
    which is DCS's own height for the spot rather than the real world's."""
    written = _settings(_flight(saved=[_point("SMOKE")]), monkeypatch)

    assert '["wpt_elev"]' not in written


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

    assert numbers == ["0", "1", "2", "4"]


def test_the_first_route_point_is_the_aircraft_itself(monkeypatch: Any) -> None:
    written = _settings(_flight(route=2), monkeypatch)

    assert '["wpt_id"]="INIT POSIT"' in written


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
