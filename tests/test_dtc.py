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
from typing import Any, cast

import pytest

from game.missiongenerator import dtc
from game.theater import Player


def _game(*, fronts: int = 0) -> Any:
    names = [SimpleNamespace(name=f"Front {n}") for n in range(1, fronts + 1)]
    return SimpleNamespace(
        theater=SimpleNamespace(
            controlpoints=[],
            terrain=SimpleNamespace(name="Falklands"),
            conflicts=lambda: iter(names),
        ),
        settings=SimpleNamespace(),
        campaign_name="A Campaign",
        blue=SimpleNamespace(ato=SimpleNamespace(packages=[])),
    )


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
    hornet = dtc.HornetCartridge().sections([])
    viper = dtc.ViperCartridge().sections([])

    assert hornet["SA"]["mirror_MEZ_THRTS"] is True
    assert viper["MPD"]["mirror_THREAT_PTS"] is True
    # And the list stays empty, so nothing here can name a threat wrongly.
    assert hornet["SA"]["MEZ_THRTS"] == []
    assert "THREAT_PTS" not in viper["MPD"]


def test_the_fronts_are_written_because_no_mirror_invents_them() -> None:
    flot = dtc.HornetCartridge().sections(_fronts(1))["SA"]["FAOR_FLOT"]["FLOT"]

    assert len(flot) == 1
    assert flot[0]["id"] == "FLOT_1"
    assert [point["id"] for point in flot[0]["points"]] == [
        "FLOT_1_PT_1",
        "FLOT_1_PT_2",
    ]


def test_the_page_is_told_which_line_to_show() -> None:
    """DCS spells 4 as NONE and starts there, so a cartridge that says nothing about
    it carries a line nobody is ever shown."""
    assert dtc.HornetCartridge().sections(_fronts(1))["SA"]["Default_FLOT_Line"] == 1
    # Nothing to draw, so nothing is selected rather than an empty line.
    assert dtc.HornetCartridge().sections([])["SA"]["Default_FLOT_Line"] == dtc.NONE


def test_the_viper_flags_each_line_point_rather_than_nesting_it() -> None:
    """Its twenty-five points are shared between four lines, not split among them."""
    points = dtc.ViperCartridge().sections(_fronts(2))["MPD"]["GEO_LINES"]

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
    assert set(dtc.HornetCartridge().sections([])) == {"SA"}
    assert set(dtc.ViperCartridge().sections([])) == {"MPD"}


@pytest.mark.parametrize("aircraft", ["FA-18E", "FA-18F", "EA-18G"])
def test_the_super_hornets_carry_the_hornet_s_cartridge(aircraft: str) -> None:
    """The CJS mod ships the same sections under another type name, so they are the
    same profile rather than three copies of it."""
    profile = dtc.CARTRIDGES[aircraft]
    hornet = dtc.CARTRIDGES["FA-18C_hornet"]

    assert profile.sections(_fronts(1)) == hornet.sections(_fronts(1))
    assert profile.max_lines == hornet.max_lines


def test_a_long_front_stops_the_next_one_rather_than_overflowing() -> None:
    class Narrow(dtc.HornetCartridge):
        max_lines = 3
        max_line_points = 3

    assert [front.name for front in dtc._trim(Narrow(), _fronts(3))] == ["Front 1"]


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
    game = _game()
    _crewed(game, ("FA-18C_hornet", 2), ("F-16C_50", 1))

    written = dtc.write_into_mission(game, mission)

    assert written == [
        "DTC/retribution_nextturn F-16C_50.dtc",
        "DTC/retribution_nextturn FA-18C_hornet.dtc",
        "DTC/retribution_nextturn.dtc",
    ]
    with zipfile.ZipFile(mission) as archive:
        assert "mission" in archive.namelist()
        card = json.loads(archive.read("DTC/retribution_nextturn.dtc").decode("utf-8"))
    # The mission's own name goes to whoever has the most seats in it.
    assert card["type"] == "FA-18C_hornet"


def test_nothing_to_carry_leaves_the_mission_alone(tmp_path: Path) -> None:
    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")

    assert dtc.write_into_mission(_game(), mission) == []

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
    sa = dtc.HornetCartridge().sections(_fronts(1))["SA"]

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


def test_the_one_in_the_mission_is_named_after_the_mission(tmp_path: Path) -> None:
    """Which is what a cartridge that works carries. The copy for the DTC page keeps
    the campaign's name, because that is the list it has to be findable in."""
    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    game = _game()
    _crewed(game, ("FA-18C_hornet", 1))

    dtc.write_into_mission(game, mission)
    with zipfile.ZipFile(mission) as archive:
        inside = json.loads(
            archive.read("DTC/retribution_nextturn.dtc").decode("utf-8")
        )

    assert inside["name"] == "retribution_nextturn"
    assert inside["data"]["name"] == "retribution_nextturn"
    assert dtc.write_cartridges(game, tmp_path)[0].name.startswith("Escalation")


@installed
def test_every_key_the_module_declares_is_one_we_write() -> None:
    """Read off the module's own data skeleton, so a DCS update that adds a key to
    the SA section fails here rather than in the cockpit."""
    import re

    skeleton = (HORNET.parent / "FA-18C_hornet_DTC.lua").read_text(encoding="utf-8")
    body = skeleton[skeleton.index("SA = {") : skeleton.index("WYPT = {")]
    theirs = set(re.findall(r"(\w+)\s*=", body)) - {"SA"}

    ours = set(dtc.HornetCartridge().sections([])["SA"])

    assert theirs <= ours, sorted(theirs - ours)


# ------------------------------------------------ naming the cartridge on the unit


class _Unit:
    """A flying unit, as much of one as the binder touches."""

    def __init__(self, unit_type: str, human: bool = True) -> None:
        self.type = unit_type
        self.human = human
        self.written: dict[str, Any] = {}

    def is_human(self) -> bool:
        return self.human

    def dict(self) -> dict[str, Any]:
        return dict(self.written)


def _mission(*units: Any) -> Any:
    country = SimpleNamespace(
        plane_group=[SimpleNamespace(units=list(units))], helicopter_group=[]
    )
    return SimpleNamespace(
        coalition={"blue": SimpleNamespace(countries={"USA": country})}
    )


def test_only_a_crewed_aircraft_that_takes_one_is_bound() -> None:
    """A cartridge in the .miz is only on the shelf: the unit has to name it, which
    is what the mission editor writes and what a probe that draws the rings carries."""
    hornet = _Unit("FA-18C_hornet")
    ai = _Unit("FA-18C_hornet", human=False)
    hog = _Unit("A-10C_2")

    bound = dtc.bind_to_units(_mission(hornet, ai, hog), "retribution_nextturn")

    assert bound == 1
    assert getattr(hornet, dtc.CARTRIDGE_ON_UNIT) == "retribution_nextturn"
    assert not hasattr(ai, dtc.CARTRIDGE_ON_UNIT)
    assert not hasattr(hog, dtc.CARTRIDGE_ON_UNIT)


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
