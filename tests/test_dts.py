"""The A-10's data transfer system, which is not a .dtc file.

Its own default database says where to put one: a file named
``<mission>_DTS_CDU_Database.lua`` beside the .miz replaces the stock one, and LOAD
ALL on the CDU reads it. It carries waypoints and nothing else, which is a fact about
the aeroplane rather than a gap in the campaign.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.ato.savedpoints import PointKind, SavedPoint
from game.missiongenerator import dts


def _flight(
    callsign: str = "HAWG", aircraft: str = "A-10C_2", *points: SavedPoint
) -> Any:
    return SimpleNamespace(
        callsign=callsign,
        client_count=1,
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=aircraft)),
        saved_points=list(points),
    )


def _point(name: str = "Smoke", altitude_ft: int = 0) -> SavedPoint:
    return SavedPoint(
        kind=PointKind.WAYPOINT, name=name, x=1000.0, y=2000.0, altitude_ft=altitude_ft
    )


def _game(*flights: Any) -> Any:
    latlng = SimpleNamespace(lat=41.5, lng=44.25)

    class Terrain:
        pass

    def point(x: float, y: float, terrain: Any) -> Any:
        return SimpleNamespace(latlng=lambda: latlng)

    return SimpleNamespace(
        blue=SimpleNamespace(
            ato=SimpleNamespace(packages=[SimpleNamespace(flights=list(flights))])
        ),
        theater=SimpleNamespace(terrain=Terrain()),
        _point=point,
    )


@pytest.fixture(autouse=True)
def simple_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The conversion belongs to pydcs; what is under test is the file."""
    monkeypatch.setattr(
        dts,
        "Point",
        lambda x, y, terrain: SimpleNamespace(
            latlng=lambda: SimpleNamespace(lat=41.5, lng=44.25)
        ),
    )


def test_the_file_sits_beside_the_mission_under_its_name() -> None:
    assert dts.path_beside(Path("C:/Missions/retribution_nextturn.miz")) == Path(
        "C:/Missions/retribution_nextturn_DTS_CDU_Database.lua"
    )


def test_only_an_a_10_the_player_flies_with_something_written_down() -> None:
    hog = _flight("HAWG", "A-10C_2", _point())
    empty_hog = _flight("BOAR", "A-10C_2")
    hornet = _flight("TARSIER", "FA-18C_hornet", _point())
    ai = _flight("DRONE", "A-10C_2", _point())
    ai.client_count = 0

    found = list(dts.flights_with_points(_game(hog, empty_hog, hornet, ai)))

    assert [flight.callsign for flight in found] == ["HAWG"]


def test_the_numbering_starts_where_the_mission_stops() -> None:
    """DCS's own sample starts at 51, which is above the mission's own route."""
    lua = dts.database(_game(_flight("HAWG", "A-10C_2", _point(), _point("Convoy"))))

    assert "WP_database[51]" in lua
    assert "WP_database[52]" in lua
    assert "WP_database[50]" not in lua


def test_a_point_carries_the_callsign_it_was_written_for() -> None:
    """One database for the whole mission, not one per aircraft."""
    lua = dts.database(
        _game(
            _flight("HAWG", "A-10C_2", _point("Smoke")),
            _flight("BOAR", "A-10C_2", _point("Convoy")),
        )
    )

    assert "-- HAWG waypoint: Smoke" in lua
    assert "-- BOAR waypoint: Convoy" in lua


def test_an_identifier_the_cdu_will_take() -> None:
    lua = dts.database(
        _game(_flight("HAWG", "A-10C_2", _point("smoke by the bridge, north")))
    )

    written = re.search(r'\["Identifier"\] = "([^"]*)"', lua)
    assert written is not None
    assert written.group(1) == "SMOKE BY THE"
    assert len(written.group(1)) <= dts.NAME_LENGTH


def test_a_point_with_no_usable_name_still_gets_one() -> None:
    lua = dts.database(_game(_flight("HAWG", "A-10C_2", _point("!!!"))))

    assert '["Identifier"] = "PT51"' in lua


def test_the_file_reads_as_the_database_it_replaces() -> None:
    lua = dts.database(_game(_flight("HAWG", "A-10C_2", _point())))

    assert "Database_Common.lua" in lua
    assert "LoadAllAirfields" in lua
    assert lua.startswith("--")


def test_nothing_written_down_takes_last_turn_s_file_away(tmp_path: Path) -> None:
    """A stale one keeps loading points from a turn nobody is flying any more."""
    mission = tmp_path / "retribution_nextturn.miz"
    stale = dts.path_beside(mission)
    stale.write_text("-- last turn", encoding="utf-8")

    assert dts.write_database(_game(_flight("HAWG", "A-10C_2")), mission) is None

    assert not stale.exists()


def test_it_is_written_where_dcs_looks(tmp_path: Path) -> None:
    mission = tmp_path / "retribution_nextturn.miz"

    written = dts.write_database(
        cast(Any, _game(_flight("HAWG", "A-10C_2", _point("Smoke")))), mission
    )

    assert written == dts.path_beside(mission)
    assert written is not None
    assert "SMOKE" in written.read_text(encoding="utf-8")


DEFAULT = Path(
    "D:/SteamLibrary/steamapps/common/DCSWorld/Mods/aircraft/A-10C_2/Cockpit/Scripts/"
    "NavigationComputer/Database/Default_DTS_CDU_DB.lua"
)


@pytest.mark.skipif(not DEFAULT.is_file(), reason="DCS is not installed here")
def test_the_shape_is_the_one_dcs_ships() -> None:
    """Every key written has to be one the stock database uses, or the CDU ignores
    it; and its first index is where ours starts."""
    theirs = DEFAULT.read_text(encoding="utf-8", errors="replace")
    ours = dts.database(_game(_flight("HAWG", "A-10C_2", _point())))

    for key in re.findall(r'\["(\w+)"\]', ours):
        assert f'["{key}"]' in theirs, key
    assert f"WP_database[{dts.FIRST_INDEX}]" in theirs
