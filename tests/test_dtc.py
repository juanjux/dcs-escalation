"""What goes in an aircraft's data cartridge.

DCS 2.9.29 moved the Hornet's SA-page threat rings behind the cartridge: with none
loaded the page is blank however the units are flagged. What brings them back is one
switch -- mirror the mission's own threats -- measured on probe missions where a site
flagged ``hiddenOnMFD`` stayed off the page while its neighbours showed. These read
the file's contents before it is written, and check the shapes and the limits against
DCS's own files whenever DCS is installed.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence, cast

import pytest
from dcs import Point
from dcs.terrain import Caucasus

from game.ato.savedpoints import capacity_for
from game.missiongenerator import dtc
from game.theater import Player


def _air_wing(*aircraft: str) -> Any:
    squadrons = [
        SimpleNamespace(
            aircraft=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=unit_id))
        )
        for unit_id in aircraft
    ]
    return SimpleNamespace(iter_squadrons=lambda: iter(squadrons))


def _game(
    *,
    fronts: int = 0,
    countermeasures: bool = False,
    roe: bool = False,
    blue: Sequence[str] = (),
    red: Sequence[str] = (),
) -> Any:
    names = [SimpleNamespace(name=f"Front {n}") for n in range(1, fronts + 1)]
    return SimpleNamespace(
        theater=SimpleNamespace(
            controlpoints=[],
            terrain=SimpleNamespace(name="Falklands"),
            conflicts=lambda: iter(names),
        ),
        settings=SimpleNamespace(
            dtc_viper_countermeasures=countermeasures, dtc_viper_roe=roe
        ),
        campaign_name="A Campaign",
        blue=SimpleNamespace(
            ato=SimpleNamespace(packages=[]), air_wing=_air_wing(*blue)
        ),
        red=SimpleNamespace(air_wing=_air_wing(*red)),
    )


class _Unit:
    """A flying unit, as much of one as the binder touches."""

    def __init__(self, unit_type: str = "FA-18C_hornet", human: bool = True) -> None:
        self.type = unit_type
        self.human = human

    def is_human(self) -> bool:
        return self.human


def _waypoint(name: str, x: float, y: float, alt_m: float = 6096.0) -> Any:
    from game.ato.flightwaypointtype import FlightWaypointType

    return SimpleNamespace(
        waypoint_type=FlightWaypointType.NAV,
        display_name=name,
        position=SimpleNamespace(x=x, y=y),
        alt=SimpleNamespace(meters=alt_m),
    )


def _route(length: int) -> list[Any]:
    return [_waypoint(f"WP{n}", float(n), float(n)) for n in range(length)]


def _flight_data(
    aircraft: str = "FA-18C_hornet",
    callsign: str = "ENFIELD11",
    crewed: int = 1,
    route: int = 4,
    saved: Sequence[Any] = (),
) -> Any:
    from game.ato.flighttype import FlightType

    units = [_Unit(aircraft) for _ in range(crewed)]
    return SimpleNamespace(
        flight_type=FlightType.STRIKE,
        friendly=Player.BLUE,
        aircraft_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=aircraft)),
        callsign=callsign,
        client_units=units,
        waypoints=_route(route),
        saved_points=list(saved),
    )


def _mission_data(*flights: Any) -> Any:
    return SimpleNamespace(flights=list(flights))


def _saved(kind: str, name: str, x: float, y: float, altitude_ft: int = 0) -> Any:
    return SimpleNamespace(kind=kind, name=name, x=x, y=y, altitude_ft=altitude_ft)


def _fronts(count: int) -> list[dtc.Front]:
    return [
        dtc.Front(f"Front {n}", ((0.0, 0.0), (10.0, 0.0))) for n in range(1, count + 1)
    ]


def _crewed(game: Any, *seats: tuple[str, int]) -> None:
    game.blue.ato.packages = [
        SimpleNamespace(
            flights=[
                SimpleNamespace(
                    client_count=count,
                    unit_type=SimpleNamespace(
                        dcs_unit_type=SimpleNamespace(id=aircraft)
                    ),
                )
                for aircraft, count in seats
            ]
        )
    ]


# ----------------------------------------------------------------- the one switch


def test_the_rings_are_mirrored_rather_than_drawn() -> None:
    """Listing them by hand works and looks wrong -- plain white rings instead of
    DCS's yellow dashed ones -- and needs every threat mapped to a name DCS knows."""
    hornet = dtc.HornetCartridge().sections([], [])
    viper = dtc.ViperCartridge().sections([], [])

    assert hornet["SA"]["mirror_MEZ_THRTS"] is True
    assert viper["MPD"]["mirror_THREAT_PTS"] is True
    # And the list stays empty, so nothing here can name a threat wrongly.
    assert hornet["SA"]["MEZ_THRTS"] == []
    assert "THREAT_PTS" not in viper["MPD"]


def test_the_fronts_are_written_because_no_mirror_invents_them() -> None:
    flot = dtc.HornetCartridge().sections(_fronts(1), [])["SA"]["FAOR_FLOT"]["FLOT"]

    assert len(flot) == 1
    assert flot[0]["id"] == "FLOT_1"
    assert [point["id"] for point in flot[0]["points"]] == [
        "FLOT_1_PT_1",
        "FLOT_1_PT_2",
    ]


def test_the_page_is_told_which_line_to_show() -> None:
    """DCS spells 4 as NONE and starts there, so a cartridge that says nothing about
    it carries a line nobody is ever shown."""
    assert (
        dtc.HornetCartridge().sections(_fronts(1), [])["SA"]["Default_FLOT_Line"] == 1
    )
    # Nothing to draw, so nothing is selected rather than an empty line.
    assert dtc.HornetCartridge().sections([], [])["SA"]["Default_FLOT_Line"] == dtc.NONE


def test_the_viper_flags_each_line_point_rather_than_nesting_it() -> None:
    """Its twenty-five points are shared between four lines, not split among them."""
    points = dtc.ViperCartridge().sections(_fronts(2), [])["MPD"]["GEO_LINES"]

    assert len(points) == 4
    assert [point["L1"] for point in points] == [True, True, False, False]
    assert [point["L2"] for point in points] == [False, False, True, True]
    assert [point["id"] for point in points] == [
        "GEO_LINES31",
        "GEO_LINES32",
        "GEO_LINES33",
        "GEO_LINES34",
    ]


def test_each_aircraft_keeps_it_somewhere_of_its_own() -> None:
    assert set(dtc.HornetCartridge().sections([], [])) == {"SA"}
    assert set(dtc.ViperCartridge().sections([], [])) == {"MPD"}


@pytest.mark.parametrize("aircraft", ["FA-18E", "FA-18F", "EA-18G"])
def test_the_super_hornets_carry_the_hornet_s_cartridge(aircraft: str) -> None:
    """The CJS mod ships the same sections under another type name, so they are the
    same profile rather than three copies of it."""
    profile = dtc.CARTRIDGES[aircraft]
    hornet = dtc.CARTRIDGES["FA-18C_hornet"]

    assert profile.sections(_fronts(1), []) == hornet.sections(_fronts(1), [])
    assert profile.max_lines == hornet.max_lines


def _bar(name: str, *points: tuple[float, float]) -> dtc.Front:
    return dtc.Front(name, tuple(points))


def test_the_fronts_are_joined_into_one_line_across_the_theater() -> None:
    """Drawn apart they are stubs that do not say which side is hostile."""
    line = dtc.join_fronts(
        [
            _bar("Middle", (30.0, 0.0), (20.0, 0.0)),
            _bar("East", (40.0, 0.0), (50.0, 0.0)),
            _bar("West", (0.0, 0.0), (10.0, 0.0)),
        ]
    )

    assert line is not None
    assert line.name == "FLOT"
    # From one end of the theater to the other, each front turned to continue it.
    assert list(line.points) in (
        [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
        + [(40.0, 0.0), (50.0, 0.0)],
        [(50.0, 0.0), (40.0, 0.0), (30.0, 0.0), (20.0, 0.0)]
        + [(10.0, 0.0), (0.0, 0.0)],
    )


def test_a_single_front_keeps_its_name() -> None:
    line = dtc.join_fronts([_bar("Front 1", (0.0, 0.0), (10.0, 0.0))])

    assert line == _bar("Front 1", (0.0, 0.0), (10.0, 0.0))
    assert dtc.join_fronts([]) is None


def test_a_line_too_long_for_the_aircraft_loses_its_flattest_points() -> None:
    wavy = [(float(x), 0.0 if x != 4 else 5.0) for x in range(9)]

    kept = dtc.simplified(wavy, 3)

    # Both ends stay, and the one point that bends the line is the one kept.
    assert kept == [(0.0, 0.0), (4.0, 5.0), (8.0, 0.0)]


def test_the_hornet_draws_the_whole_front_on_the_one_line_it_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SA page draws only the selected FLOT line, so a front split over three
    would show a third of itself."""
    bars = [
        _bar(f"Front {n}", (0.0, n * 20.0), (10.0, n * 20.0 + 5.0)) for n in range(5)
    ]
    monkeypatch.setattr(dtc, "fronts_of", lambda theater: bars)

    built = dtc.cartridge(_game(), Player.BLUE, "FA-18C_hornet", "Escalation")
    flot = built["data"]["SA"]["FAOR_FLOT"]["FLOT"]

    assert len(flot) == 1
    assert len(flot[0]["points"]) == dtc.HornetCartridge.max_line_points
    ends = {(p["x"], p["y"]) for p in (flot[0]["points"][0], flot[0]["points"][-1])}
    assert ends == {(0.0, 0.0), (10.0, 85.0)}

    viper = dtc.cartridge(_game(), Player.BLUE, "F-16C_50", "Escalation")
    points = viper["data"]["MPD"]["GEO_LINES"]
    # The Viper has room for all ten, on the first line.
    assert len(points) == 10
    assert all(point["L1"] for point in points)


# ------------------------------------------------------------------ the whole file


def test_only_the_sections_its_profile_fills_are_written() -> None:
    """A partial cartridge is valid -- DCS ships its own defaults as one section --
    so nothing here invents radio presets or countermeasure programmes."""
    built = dtc.cartridge(_game(), Player.BLUE, "F-16C_50", "Escalation")

    assert built["type"] == "F-16C_50"
    data = cast(dict[str, Any], built["data"])
    assert set(data) == {"name", "type", "terrain", "MPD"}
    assert data["terrain"] == "Falklands"


def test_only_crewed_flights_in_an_aircraft_with_a_profile_get_one() -> None:
    game = _game()
    _crewed(
        game,
        ("FA-18C_hornet", 1),
        ("F-16C_50", 0),
        # Its module has nowhere to put a ring or a line, so it gets no cartridge.
        ("A-10C_2", 2),
    )

    assert dtc.player_aircraft(game) == {"FA-18C_hornet"}


def test_the_mission_carries_its_own_cartridges(tmp_path: Path) -> None:
    """A cartridge the player has to go and load is an errand, not a feature."""
    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    data = _mission_data(
        _flight_data(callsign="ENFIELD11"),
        _flight_data(aircraft="F-16C_50", callsign="SPRINGFIELD21"),
    )

    written = dtc.write_into_mission(_game(), data, mission)

    assert written == [
        "DTC/retribution_nextturn ENFIELD11.dtc",
        "DTC/retribution_nextturn SPRINGFIELD21.dtc",
    ]
    with zipfile.ZipFile(mission) as archive:
        assert "mission" in archive.namelist()
        card = json.loads(
            archive.read("DTC/retribution_nextturn ENFIELD11.dtc").decode("utf-8")
        )
    assert card["type"] == "FA-18C_hornet"


def test_nothing_to_carry_leaves_the_mission_alone(tmp_path: Path) -> None:
    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")

    assert dtc.write_into_mission(_game(), _mission_data(), mission) == []

    with zipfile.ZipFile(mission) as archive:
        assert archive.namelist() == ["mission"]


def test_a_copy_goes_where_it_can_be_loaded_by_hand(tmp_path: Path) -> None:
    game = _game()
    _crewed(game, ("FA-18C_hornet", 1))

    written = dtc.write_cartridges(game, tmp_path)

    assert [path.name for path in written] == [
        "Escalation A Campaign FA-18C_hornet.dtc"
    ]
    assert "mirror_MEZ_THRTS" in written[0].read_text(encoding="utf-8")


# ------------------------------------------------- against DCS's own files


DCS = Path("D:/SteamLibrary/steamapps/common/DCSWorld/CoreMods/aircraft")
HORNET = DCS / "FA-18C/DTC/SA"
VIPER = DCS / "F-16C/DTC/MPD"
installed = pytest.mark.skipif(not DCS.is_dir(), reason="DCS is not installed here")


@installed
def test_the_limits_are_the_ones_each_module_enforces() -> None:
    hornet = dtc.HornetCartridge()
    flot = (HORNET / "FAOR_FLOT.lua").read_text(encoding="utf-8")
    assert f"MAX_FLOT_LINES  = {hornet.max_lines}" in flot
    assert f"MAX_LINE_POINTS = {hornet.max_line_points}" in flot

    viper = dtc.ViperCartridge()
    lines = (VIPER / "GEO_LINES.lua").read_text(encoding="utf-8")
    assert f"#data.MPD.GEO_LINES > {viper.max_line_points - 1}" in lines


@installed
def test_none_really_is_what_dcs_calls_four_and_where_it_starts() -> None:
    flot = (HORNET / "FAOR_FLOT.lua").read_text(encoding="utf-8")

    assert f'{{text = "NONE", id = {dtc.NONE}}}' in flot
    assert f'"coLSA_FLOT_Default_FLOT_Line", "selectItem", {dtc.NONE}' in flot


@installed
def test_the_mirror_is_a_switch_the_module_really_reads() -> None:
    """If it were not, the cartridge would be a file DCS ignores."""
    threats = (HORNET / "MEZ_THRTS.lua").read_text(encoding="utf-8")
    viper = (VIPER.parent / "F-16C_50_DTC.lua").read_text(encoding="utf-8")

    assert "data.SA.mirror_MEZ_THRTS" in threats
    assert "mirror_THREAT_PTS" in viper


MOD_DTC = Path(
    "C:/Users/juanj/Saved Games/DCS/Mods/aircraft/"
    "CJS Super Hornet Mod v2.4 Core Module/DTC"
)


@pytest.mark.skipif(
    not MOD_DTC.is_dir(), reason="the Super Hornet mod is not installed here"
)
@pytest.mark.parametrize("aircraft", ["FA-18E", "FA-18F", "EA-18G"])
def test_the_mod_really_does_keep_them_where_the_hornet_does(aircraft: str) -> None:
    """If a mod update moved a section, the cartridge would write into a key nothing
    reads."""
    definition = (MOD_DTC / f"{aircraft}_DTC.lua").read_text(
        encoding="utf-8", errors="replace"
    )

    assert f'type = "{aircraft}"' in definition
    assert "MEZ_THRTS" in definition
    assert "FAOR_FLOT" in definition


def test_the_sa_section_is_written_whole() -> None:
    """A cartridge that draws the rings carries a complete section; one that names
    three keys out of eleven is a shape the loader has never been handed."""
    sa = dtc.HornetCartridge().sections(_fronts(1), [])["SA"]

    assert set(sa) == {
        "CAP_PTS",
        "CORRIDORS",
        "MEZ_THRTS",
        "SETTINGS",
        "FAOR_FLOT",
        "Default_CAP_Point",
        "Default_CORRIDORS_Point",
        "Default_FAOR_Line",
        "Default_FLOT_Line",
        "Default_MEZ_THRTS_Level",
        "mirror_MEZ_THRTS",
    }


def test_a_cartridge_answers_to_exactly_one_name(tmp_path: Path) -> None:
    """File name, the name inside it, and the name the unit asks for: one string.
    Two cartridges answering to the same name is a coin toss nobody wrote down."""
    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    game = _game()
    _crewed(game, ("FA-18C_hornet", 1))
    flight = _flight_data(callsign="ENFIELD11")

    written = dtc.write_into_mission(game, _mission_data(flight), mission)
    with zipfile.ZipFile(mission) as archive:
        inside = json.loads(archive.read(written[0]).decode("utf-8"))

    wanted = "retribution_nextturn ENFIELD11"
    assert written == [f"DTC/{wanted}.dtc"]
    assert inside["name"] == wanted
    assert inside["data"]["name"] == wanted
    # And it is the name the units of that flight are sent looking for.
    dtc.bind_to_units(_mission_data(flight), "retribution_nextturn")
    assert getattr(flight.client_units[0], dtc.CARTRIDGE_ON_UNIT) == wanted
    # The copy for the DTC page keeps the campaign's name: that is the list it has to
    # be findable in.
    assert dtc.write_cartridges(game, tmp_path)[0].name.startswith("Escalation")


@installed
def test_every_key_the_module_declares_is_one_we_write() -> None:
    """Read off the module's own data skeleton, so a DCS update that adds a key to
    the SA section fails here rather than in the cockpit."""
    import re

    skeleton = (HORNET.parent / "FA-18C_hornet_DTC.lua").read_text(encoding="utf-8")
    body = skeleton[skeleton.index("SA = {") : skeleton.index("WYPT = {")]
    theirs = set(re.findall(r"(\w+)\s*=", body)) - {"SA"}

    ours = set(dtc.HornetCartridge().sections([], [])["SA"])

    assert theirs <= ours, sorted(theirs - ours)


# ------------------------------------------------ naming the cartridge on the unit


def test_only_a_crewed_aircraft_that_takes_one_is_bound() -> None:
    """A cartridge in the .miz is only on the shelf: the unit has to name it, which
    is what the mission editor writes and what a probe that draws the rings carries."""
    hornets = _flight_data(callsign="ENFIELD11", crewed=2)
    ai = _flight_data(callsign="CHEVY31", crewed=0)
    hogs = _flight_data(aircraft="A-10C_2", callsign="HAWG11")

    bound = dtc.bind_to_units(_mission_data(hornets, ai, hogs), "retribution_nextturn")

    assert bound == 2
    for unit in hornets.client_units:
        assert getattr(unit, dtc.CARTRIDGE_ON_UNIT) == "retribution_nextturn ENFIELD11"
    assert not hasattr(hogs.client_units[0], dtc.CARTRIDGE_ON_UNIT)


def test_each_flight_is_sent_to_its_own_cartridge() -> None:
    """What goes in one is that flight's: its route, and its own saved points."""
    one = _flight_data(callsign="ENFIELD11")
    two = _flight_data(callsign="ENFIELD21")

    dtc.bind_to_units(_mission_data(one, two), "retribution_nextturn")

    assert getattr(one.client_units[0], dtc.CARTRIDGE_ON_UNIT) != getattr(
        two.client_units[0], dtc.CARTRIDGE_ON_UNIT
    )


def test_a_bound_unit_writes_the_table_dcs_reads() -> None:
    """Key for key, the shape SAMRING_03's Hornet carries."""

    class Unit:
        def dict(self) -> dict[str, Any]:
            return {"type": "FA-18C_hornet"}

    dtc.teach_to_write_cartridges(Unit)
    unit = Unit()
    setattr(unit, dtc.CARTRIDGE_ON_UNIT, "retribution_nextturn")

    assert unit.dict()["DTC"] == {
        "AutoLoad": True,
        "Cartridges": [{"name": "retribution_nextturn", "default": True}],
    }


def test_a_unit_that_was_never_bound_writes_nothing_extra() -> None:
    class Unit:
        def dict(self) -> dict[str, Any]:
            return {"type": "MiG-29A"}

    dtc.teach_to_write_cartridges(Unit)

    assert "DTC" not in Unit().dict()


def test_teaching_twice_does_not_wrap_twice() -> None:
    """The mission is generated over and over in one session."""

    class Unit:
        def dict(self) -> dict[str, Any]:
            return {}

    dtc.teach_to_write_cartridges(Unit)
    once = Unit.dict
    dtc.teach_to_write_cartridges(Unit)

    assert Unit.dict is once


# ------------------------------------------- the points the player wrote down


def _nav(profile: dtc.Cartridge, route: int, saved: int) -> list[dtc.NavPoint]:
    points = [_saved("waypoint", f"P{n}", float(n), float(n)) for n in range(saved)]
    return dtc.navigation_set(profile, _route(route), points)


def test_nothing_written_down_leaves_the_navigation_set_alone() -> None:
    """The mission's own route is what the aircraft starts with. Rewriting it to say
    the same thing is risk for nothing, so no navigation section is written at all."""
    assert _nav(dtc.HornetCartridge(), route=13, saved=0) == []
    assert "WYPT" not in dtc.HornetCartridge().sections([], [])


def test_the_route_comes_first_and_keeps_its_numbers() -> None:
    """With the mirror off the cartridge is the whole navigation set, so the flight
    plan goes in it too, point for point, or the aircraft loses its route."""
    points = _nav(dtc.HornetCartridge(), route=13, saved=2)

    assert [point.number for point in points] == list(range(15))
    assert [point.on_route for point in points] == [True] * 13 + [False] * 2
    assert points[13].name == "P0"


def test_the_flight_plan_is_sequence_one_and_the_saved_points_are_sequence_two() -> (
    None
):
    """Stepping SEQ1 is the route, unchanged. The points the player wrote down are
    one switch away rather than in no sequence at all, which is the only other way
    to reach them -- typing each number into the HSI."""
    section = dtc.HornetCartridge().sections([], _nav(dtc.HornetCartridge(), 13, 2))
    written = section["WYPT"]["NAV_PTS"]

    assert section["WYPT"]["mirror_NAV_PTS"] is False
    assert [point["R1"] for point in written] == [True] * 13 + [False] * 2
    assert [point["R1_order"] for point in written[:13]] == list(range(1, 14))
    assert all(point["R1_order"] is None for point in written[13:])
    assert [point["R2"] for point in written] == [False] * 13 + [True] * 2
    assert [point["R2_order"] for point in written[13:]] == [1, 2]
    assert all(not point["R3"] for point in written)


def test_the_hornet_stops_before_home_and_the_bullseye() -> None:
    """58 is where HOME goes and 59 is the bullseye, so the set stops at 57."""
    points = _nav(dtc.HornetCartridge(), route=13, saved=80)

    assert points[-1].number == 57
    assert len(points) == 58


def test_the_viper_counts_from_one_and_stops_at_twenty_five() -> None:
    points = _nav(dtc.ViperCartridge(), route=5, saved=40)

    assert [point.number for point in points[:2]] == [1, 2]
    assert points[-1].number == 25


def test_a_route_that_fills_the_module_is_left_alone() -> None:
    """Truncating a flight plan is worse than not adding the points."""
    assert _nav(dtc.ViperCartridge(), route=26, saved=1) == []


def test_the_viper_writes_its_own_record() -> None:
    written = dtc.ViperCartridge().sections([], _nav(dtc.ViperCartridge(), 3, 1))["MPD"]

    assert written["mirror_NAV_PTS"] is False
    assert [point["id"] for point in written["NAV_PTS"]] == [
        "STPT1",
        "STPT2",
        "STPT3",
        "STPT4",
    ]
    assert [point["R1"] for point in written["NAV_PTS"]] == [True, True, True, False]
    assert written["NAV_PTS"][0]["type"] == "STPT"


def test_a_saved_point_carries_its_name_and_its_altitude() -> None:
    point = _saved("waypoint", "Smoke over the ridge", 10.0, 20.0, altitude_ft=1000)
    (written,) = dtc.navigation_set(dtc.HornetCartridge(), [], [point])

    assert written.name == "Smoke over the ridge"
    assert (written.x, written.y) == (10.0, 20.0)
    assert round(written.alt_m) == 305


def test_the_mod_s_tanker_super_hornets_read_one_too() -> None:
    """DCS's own DTC editor lists them beside the E and the F, which is the list that
    settles which aircraft can be handed a cartridge."""
    for aircraft in ("FA-18ET", "FA-18FT"):
        assert dtc.CARTRIDGES[aircraft].sections([], []).keys() == {"SA"}
        assert capacity_for(aircraft) == capacity_for("FA-18E")


def test_a_saved_point_is_numbered_as_the_aircraft_numbers_it() -> None:
    """A Hornet whose route is nine points puts the first saved one at 9, and a
    kneeboard that called it 1 was one the player could not read off."""
    assert dtc.steerpoint_numbers("FA-18C_hornet", 9, 2) == [9, 10]
    assert dtc.steerpoint_numbers("F-16C_50", 4, 3) == [5, 6, 7]


def test_the_numbering_stops_where_the_module_does() -> None:
    assert dtc.steerpoint_numbers("F-16C_50", 24, 5) == [25]
    assert dtc.steerpoint_numbers("F-16C_50", 25, 5) == []


def test_an_airframe_with_no_cartridge_is_numbered_from_one() -> None:
    """Which is what the A-10's own database does."""
    assert dtc.steerpoint_numbers("A-10C_2", 6, 2) == [7, 8]


# ------------------------------------------------------------------ the tanker boxes


TERRAIN = Caucasus()


def _orbiting(
    dcs_id: str, callsign: str, start: tuple[float, float], end: tuple[float, float]
) -> Any:
    from game.ato.flighttype import FlightType
    from game.ato.flightwaypointtype import FlightWaypointType

    def at(kind: Any, x: float, y: float) -> Any:
        return SimpleNamespace(waypoint_type=kind, position=Point(x, y, TERRAIN))

    return SimpleNamespace(
        flight_type=FlightType.REFUELING,
        friendly=Player.BLUE,
        callsign=callsign,
        aircraft_type=SimpleNamespace(dcs_id=dcs_id),
        patrol_speed=None,
        waypoints=[
            at(FlightWaypointType.PATROL_TRACK, *start),
            at(FlightWaypointType.PATROL, *end),
        ],
    )


def _striking(target: tuple[float, float]) -> Any:
    from game.ato.flightwaypointtype import FlightWaypointType

    return SimpleNamespace(
        waypoints=[
            SimpleNamespace(
                waypoint_type=FlightWaypointType.TARGET_POINT,
                position=Point(*target, TERRAIN),
            )
        ]
    )


def _tankers() -> Any:
    return SimpleNamespace(
        flights=[
            _orbiting("KC-135", "Shell 1", (0.0, 0.0), (40_000.0, 0.0)),
            _orbiting("KC135MPRS", "Texaco 1", (0.0, 100_000.0), (40_000.0, 100_000.0)),
            _orbiting("S-3B Tanker", "Arco 1", (0.0, 300_000.0), (40_000.0, 300_000.0)),
        ]
    )


def test_each_aircraft_is_shown_only_the_tankers_it_can_use() -> None:
    """A Hornet has a probe and a Viper a receptacle for the boom."""
    hornet = dtc.tanker_boxes(dtc.HornetCartridge(), _tankers())
    viper = dtc.tanker_boxes(dtc.ViperCartridge(), _tankers())

    assert [box.name for box in hornet] == ["Texaco 1", "Arco 1"]
    assert [box.name for box in viper] == ["Shell 1"]


def test_the_tanker_nearest_the_target_comes_first() -> None:
    boxes = dtc.tanker_boxes(
        dtc.HornetCartridge(), _tankers(), _striking((20_000.0, 290_000.0))
    )

    assert [box.name for box in boxes] == ["Arco 1", "Texaco 1"]


def test_a_box_is_closed_and_encloses_the_orbit() -> None:
    (box,) = dtc.tanker_boxes(dtc.ViperCartridge(), _tankers())

    assert len(box.points) == dtc.BOX_POINTS
    assert box.points[0] == box.points[-1]
    xs = [x for x, _ in box.points]
    ys = [y for _, y in box.points]
    # The leg runs north from 0 to 40 km; the box stands off it by the orbit's width
    # on every side.
    assert min(xs) < 0 < 40_000 < max(xs)
    assert min(ys) < 0 < max(ys)


def test_the_hornet_takes_the_boxes_on_its_faor_lines() -> None:
    boxes = dtc.tanker_boxes(dtc.HornetCartridge(), _tankers())
    sa = dtc.HornetCartridge().sections([], [], boxes)["SA"]

    faor = sa["FAOR_FLOT"]["FAOR"]
    assert [line["note"] for line in faor] == ["Texaco 1", "Arco 1"]
    assert [point["id"] for point in faor[0]["points"]] == [
        f"FAOR_1_PT_{n}" for n in range(1, 6)
    ]
    # The page draws the selected line only, so the first one has to be selected.
    assert sa["Default_FAOR_Line"] == 1
    assert dtc.HornetCartridge().sections([], [])["SA"]["Default_FAOR_Line"] == (
        dtc.NONE
    )


def test_the_viper_s_boxes_leave_the_front_the_rest_of_its_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_front = [
        dtc.Front(f"Front {n}", ((n * 30_000.0, 0.0), (n * 30_000.0 + 10_000.0, 5.0)))
        for n in range(20)
    ]
    monkeypatch.setattr(dtc, "fronts_of", lambda theater: long_front)
    tankers = _tankers()
    tankers.flights.append(
        _orbiting("KC_10_Extender", "Shell 2", (0.0, 50_000.0), (40_000.0, 50_000.0))
    )

    built = dtc.cartridge(
        _game(), Player.BLUE, "F-16C_50", "Escalation", mission_data=tankers
    )
    points = built["data"]["MPD"]["GEO_LINES"]

    assert len(points) == dtc.ViperCartridge.max_line_points
    front = [point for point in points if point["L1"]]
    assert len(front) == 25 - 2 * dtc.BOX_POINTS
    assert [point["note"] for point in points if point["L2"]] == ["Shell 1"] * 5
    assert [point["note"] for point in points if point["L3"]] == ["Shell 2"] * 5


# ------------------------------------------------------- the Viper's countermeasures


def test_the_countermeasure_programs_are_only_written_when_asked_for() -> None:
    viper = dtc.cartridge(_game(), Player.BLUE, "F-16C_50", "Escalation")
    assert "CMDS" not in viper["data"]["MPD"]

    hornet = dtc.cartridge(
        _game(countermeasures=True), Player.BLUE, "FA-18C_hornet", "Escalation"
    )
    assert "CMDS" not in json.dumps(hornet)


def test_man_1_is_flares_and_man_6_chaff_both_from_the_stick() -> None:
    built = dtc.cartridge(
        _game(countermeasures=True), Player.BLUE, "F-16C_50", "Escalation"
    )
    cmds = built["data"]["MPD"]["CMDS"]
    programs = cmds["CMDSProgramSettings"]

    assert list(programs) == [
        "MAN1", "MAN2", "MAN3", "MAN4", "MAN5", "MAN6", "AUTO1", "AUTO2", "AUTO3", "BYP"
    ]  # fmt: skip
    assert programs["MAN1"]["Chaff"]["BurstQuantity"] == 0
    assert programs["MAN1"]["Flare"]["BurstQuantity"] > 0
    assert programs["MAN6"]["Flare"]["BurstQuantity"] == 0
    assert programs["MAN6"]["Chaff"]["BurstQuantity"] > 0
    # Every other program is the module's own, written whole.
    assert programs["MAN5"]["Chaff"]["SalvoQuantity"] == 20
    assert set(programs["AUTO2"]) == {"Chaff", "Flare", "Other1", "Other2"}
    # The per-threat choice of automatic program stays the module's.
    assert set(cmds) == {"CMDSBingoSettings", "CMDSProgramSettings"}


@installed
def test_the_stock_programs_are_the_module_s_own() -> None:
    """A DCS update that retunes a program fails here rather than in the cockpit."""
    import re

    text = (VIPER / "CMDS_defs.lua").read_text(encoding="utf-8")
    block = text[text.index("CMDSProgramSettings") : text.index("CMDSPrograms =")]
    found = re.findall(
        r"(\w+) = \{\s*BurstQuantity = ([\d.]+),\s*BurstInterval = ([\d.]+),"
        r"\s*SalvoQuantity = ([\d.]+),\s*SalvoInterval = ([\d.]+),?\s*\}",
        block,
    )
    values = [tuple(float(v) for v in match[1:]) for match in found]
    # Four dispensers a program, in the order the file lists the programs.
    assert [match[0] for match in found[:4]] == ["Chaff", "Flare", "Other1", "Other2"]
    ours = [
        dispenser
        for chaff, flare in dtc.STOCK_CMDS_PROGRAMS.values()
        for dispenser in (chaff, flare, dtc.STOCK_OTHER, dtc.STOCK_OTHER)
    ]
    assert values == [tuple(float(v) for v in dispenser) for dispenser in ours]


@installed
def test_the_loader_reads_the_programs_where_they_are_written() -> None:
    """DCS's sample cartridges keep them at data.CMDS, where the loader does not look:
    it reads them inside the MPD section."""
    loader = (VIPER.parent / "F-16C_50_DTC.lua").read_text(encoding="utf-8")

    mpd = loader.index('if i == "MPD"')
    assert loader.index("tbl[i].CMDS.CMDSProgramSettings") > mpd


# ------------------------------------------------------------ the Viper's ROE tab


def test_a_family_takes_the_side_of_whoever_alone_flies_it() -> None:
    game = _game(
        roe=True,
        blue=("F-16C_50", "KC-135", "FA-18C_hornet"),
        red=("MiG-29S", "F-16A", "Tu-95MS"),
    )

    built = dtc.cartridge(game, Player.BLUE, "F-16C_50", "Escalation")
    roe = built["data"]["MPD"]["ROE"]
    sides = {row["group_name"]: row["sovereignty"] for row in roe["List"]}

    assert sides["KC-135"] == sides["F/A-18"] == dtc.FRIENDLY
    assert sides["MiG-29"] == sides["Tu-95"] == dtc.HOSTILE
    # Both fly an F-16, so an F-16 is nobody's until it is identified otherwise.
    assert sides["F-16"] == dtc.UNKNOWN
    # Nobody flies a Tornado: it stays where the module starts it.
    assert sides["Tornado GR4"] == dtc.UNKNOWN
    # Every row, in the module's order, since the loader replaces the list whole.
    assert [row["group_name"] for row in roe["List"]] == list(dtc.ROE_FAMILIES)
    assert roe["Settings"] == {"TypeSovereignty": True, "Mode4Status": True}


def test_the_roe_table_is_left_to_the_module_when_switched_off() -> None:
    built = dtc.cartridge(_game(), Player.BLUE, "F-16C_50", "Escalation")

    assert "ROE" not in built["data"]["MPD"]


@installed
def test_the_families_are_the_module_s_own() -> None:
    """The rows and their order are ROE_defs.lua's, and every unit threat_base.lua
    puts in a family is in ours: a DCS update that adds a variant fails here."""
    import re

    rows = re.findall(
        r'group_name = "([^"]+)"', (VIPER / "ROE_defs.lua").read_text(encoding="utf-8")
    )
    assert rows == list(dtc.ROE_FAMILIES)

    base = (VIPER.parent / "threat_base.lua").read_text(encoding="utf-8")
    for chunk in base.split('group_name = "')[1:]:
        family = chunk[: chunk.index('"')]
        if family not in dtc.ROE_FAMILIES:
            continue
        units = {unit for unit in re.findall(r'unit_type = "([^"]*)"', chunk) if unit}
        assert units <= set(dtc.ROE_FAMILIES[family]), (family, units)
