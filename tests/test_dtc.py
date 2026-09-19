"""What goes in an aircraft's data cartridge.

The threat rings and the front line do not come from the mission at all -- they come
from the .dtc file the DTC page loads -- so what the campaign writes into that file is
the whole feature. These read its contents before it is written, and check the shapes,
the names and the limits against DCS's own files whenever DCS is installed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.missiongenerator import dtc
from game.theater import Player
from game.theater.theatergroundobject import SamGroundObject
from game.utils import nautical_miles


class _Site(SamGroundObject):
    """An air-defence objective, built without running its constructor.

    A subclass rather than a stand-in because the cartridge asks what kind of
    objective this is, and ``is_dead`` is a property the real one computes.
    """

    def __init__(self, name: str, groups: list[Any], dead: bool = False) -> None:
        self.name = name
        self.groups = groups
        self.position = cast(Any, SimpleNamespace(x=1000.0, y=2000.0))
        self._dead = dead

    @property
    def is_dead(self) -> bool:
        return self._dead


def _group(reach_nm: float, *unit_ids: str) -> Any:
    units = [
        SimpleNamespace(alive=True, unit_type=SimpleNamespace(dcs_id=unit_id))
        for unit_id in unit_ids
    ]
    return SimpleNamespace(
        units=units, max_threat_range=lambda: nautical_miles(reach_nm)
    )


def _sam(name: str, reach_nm: float, *unit_ids: str) -> Any:
    return _Site(name, [_group(reach_nm, *unit_ids)])


def _game(*sites: Any) -> Any:
    control_point = SimpleNamespace(captured=Player.RED, ground_objects=list(sites))
    return SimpleNamespace(
        theater=SimpleNamespace(
            controlpoints=[control_point],
            terrain=SimpleNamespace(name="Falklands"),
            conflicts=lambda: iter(()),
        ),
        settings=SimpleNamespace(),
        campaign_name="A Campaign",
        blue=SimpleNamespace(ato=SimpleNamespace(packages=[])),
    )


def _threats(count: int) -> list[dtc.Threat]:
    return [
        dtc.Threat(f"SITE{n}", "SAM SA-2 'Guideline'", "2", float(n), 0.0, 0.0)
        for n in range(1, count + 1)
    ]


def _fronts(count: int) -> list[dtc.Front]:
    return [
        dtc.Front(f"Front {n}", ((0.0, 0.0), (10.0, 0.0))) for n in range(1, count + 1)
    ]


@pytest.fixture
def always_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtc, "shows_on_mfd", lambda _tgo, _settings: True)


# ------------------------------------------------------- what the campaign knows


def test_a_site_is_named_by_the_group_that_does_the_shooting(
    always_shown: None,
) -> None:
    """An S-300 with a Strela parked beside it is not a Strela."""
    site = _Site(
        "BELUGA", [_group(64.8, "S-300PS 40B6M tr"), _group(2.5, "Strela-10M3")]
    )

    threat = dtc.threats_for(_game(site), Player.BLUE)[0]

    assert threat.kind == "SAM SA-10 'Grumble'"
    assert threat.text == "10"
    assert threat.radius_nm == pytest.approx(64.8)


def test_a_system_dcs_has_no_entry_for_still_gets_its_ring(always_shown: None) -> None:
    """An HQ-9 is not on DCS's list, and mislabelling it is worse than Custom."""
    site = _Site("BELUGA", [_group(64.8, "HQ-9_SR_SJ_202"), _group(2.5, "Strela-10M3")])

    threat = dtc.threats_for(_game(site), Player.BLUE)[0]

    assert threat.kind == dtc.CUSTOM
    assert threat.radius_nm == pytest.approx(64.8)


def test_what_the_displays_may_not_show_is_not_in_the_cartridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One question, asked once: the ring and the unit symbol agree."""
    monkeypatch.setattr(dtc, "shows_on_mfd", lambda tgo, _settings: tgo.name != "HIDE")
    shown = _sam("SHOWN", 27, "SNR_75V")
    hidden = _sam("HIDE", 27, "SNR_75V")

    threats = dtc.threats_for(_game(shown, hidden), Player.BLUE)

    assert [threat.name for threat in threats] == ["SHOWN"]


def test_a_dead_site_is_not_a_threat(always_shown: None) -> None:
    site = _Site("WRECK", [_group(27, "SNR_75V")], dead=True)

    assert dtc.threats_for(_game(site), Player.BLUE) == []


def test_the_biggest_threats_come_first(always_shown: None) -> None:
    """Whatever an aircraft cannot carry should be the AAA nobody plans around."""
    sites = [_sam(f"SITE{n:02}", n, "SNR_75V") for n in (5, 40, 20)]

    threats = dtc.threats_for(_game(*sites), Player.BLUE)

    assert [threat.radius_nm for threat in threats] == [40, 20, 5]


def test_each_front_becomes_the_points_that_draw_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.utils import Heading

    class Bounds:
        left_position = SimpleNamespace(
            x=0.0,
            y=0.0,
            point_from_heading=lambda _h, _d: SimpleNamespace(x=10.0, y=0.0),
        )
        heading_from_left_to_right = Heading.from_degrees(90)
        length = 1000.0

    monkeypatch.setattr(
        dtc.FrontLineConflictDescription,
        "frontline_bounds",
        staticmethod(lambda _front, _theater: Bounds()),
    )
    theater = SimpleNamespace(
        conflicts=lambda: iter([SimpleNamespace(name="Alpha to Bravo")])
    )

    fronts = dtc.fronts_of(cast(Any, theater))

    assert len(fronts) == 1
    assert fronts[0].name == "Alpha to Bravo"
    assert fronts[0].points == ((0.0, 0.0), (10.0, 0.0))


# --------------------------------------------------- what each aircraft will take


def test_each_aircraft_keeps_it_somewhere_of_its_own() -> None:
    """The Hornet's is on the SA page, the Viper's on the MPD."""
    threats, fronts = _threats(1), _fronts(1)

    assert set(dtc.HornetCartridge().sections(threats, fronts)) == {"SA"}
    assert set(dtc.ViperCartridge().sections(threats, fronts)) == {"MPD"}


def test_the_hornet_writes_its_radius_in_miles() -> None:
    written = dtc.HornetCartridge().sections(_threats(1), [])
    threat = written["SA"]["MEZ_THRTS"][0]

    assert threat["threat_ring_radius"] == 1.0
    assert threat["threat_type"] == "SAM SA-2 'Guideline'"
    assert threat["id"] == "MEZ_THRTS_1"


def test_the_viper_writes_its_radius_in_metres_and_names_its_own_entry() -> None:
    """Each module asks for what it asks for, and the Viper wants a list index."""
    written = dtc.ViperCartridge().sections(_threats(1), [])
    threat = written["MPD"]["THREAT_PTS"][0]

    assert threat["radius"] == 1852
    assert threat["threatName"] == "SAM SA-2 'Guideline'"
    assert threat["def_num"] == dtc.VIPER_THREAT_DEFS["SAM SA-2 'Guideline'"][0]
    assert threat["ring"] is True
    assert threat["id"] == "THREAT_PTS56"


def test_the_viper_flags_each_line_point_rather_than_nesting_it() -> None:
    """Its twenty-five points are shared between four lines, not split among them."""
    written = dtc.ViperCartridge().sections([], _fronts(2))
    points = written["MPD"]["GEO_LINES"]

    assert len(points) == 4
    assert [point["L1"] for point in points] == [True, True, False, False]
    assert [point["L2"] for point in points] == [False, False, True, True]
    assert [point["id"] for point in points] == [
        "GEO_LINES31",
        "GEO_LINES32",
        "GEO_LINES33",
        "GEO_LINES34",
    ]


def test_an_aircraft_carries_as_much_as_it_can_and_says_what_it_dropped() -> None:
    viper = dtc.ViperCartridge()

    threats, fronts = dtc._trim(viper, _threats(30), _fronts(9))

    assert len(threats) == viper.max_threats
    # Four lines is the ceiling, and four two-point lines fit inside twenty-five.
    assert len(fronts) == viper.max_lines


def test_a_long_front_stops_the_next_one_rather_than_overflowing() -> None:
    class Narrow(dtc.HornetCartridge):
        max_lines = 3
        max_line_points = 3

    fronts = dtc._trim(Narrow(), [], _fronts(3))[1]

    assert [front.name for front in fronts] == ["Front 1"]


def test_only_the_sections_its_profile_fills_are_written(always_shown: None) -> None:
    """A partial cartridge is valid -- DCS ships its own defaults as one section --
    so nothing here invents radio presets or countermeasure programmes."""
    built = dtc.cartridge(
        _game(_sam("HIPPO", 23, "SNR_75V")), Player.BLUE, "F-16C_50", "Escalation"
    )

    assert built["type"] == "F-16C_50"
    data = cast(dict[str, Any], built["data"])
    assert set(data) == {"name", "type", "terrain", "MPD"}
    assert data["terrain"] == "Falklands"


def test_only_crewed_flights_in_an_aircraft_with_a_profile_get_one() -> None:
    game = _game()
    game.blue.ato.packages = [
        SimpleNamespace(
            flights=[
                SimpleNamespace(
                    client_count=1,
                    unit_type=SimpleNamespace(
                        dcs_unit_type=SimpleNamespace(id="FA-18C_hornet")
                    ),
                ),
                SimpleNamespace(
                    client_count=0,
                    unit_type=SimpleNamespace(
                        dcs_unit_type=SimpleNamespace(id="F-16C_50")
                    ),
                ),
                # Its module has nowhere to put a ring, so it gets no cartridge.
                SimpleNamespace(
                    client_count=2,
                    unit_type=SimpleNamespace(
                        dcs_unit_type=SimpleNamespace(id="A-10C_2")
                    ),
                ),
            ]
        )
    ]

    assert dtc.player_aircraft(game) == {"FA-18C_hornet"}


def test_a_cartridge_is_written_per_airframe(
    always_shown: None, tmp_path: Path
) -> None:
    game = _game(_sam("HIPPO", 23, "SNR_75V"))
    game.blue.ato.packages = [
        SimpleNamespace(
            flights=[
                SimpleNamespace(
                    client_count=1,
                    unit_type=SimpleNamespace(
                        dcs_unit_type=SimpleNamespace(id=aircraft)
                    ),
                )
                for aircraft in ("FA-18C_hornet", "F-16C_50")
            ]
        )
    ]

    written = dtc.write_cartridges(game, tmp_path)

    assert [path.name for path in written] == [
        "Escalation A Campaign F-16C_50.dtc",
        "Escalation A Campaign FA-18C_hornet.dtc",
    ]
    assert "THREAT_PTS" in written[0].read_text(encoding="utf-8")
    assert "MEZ_THRTS" in written[1].read_text(encoding="utf-8")


# ------------------------------------------------- against DCS's own files


DCS = Path("D:/SteamLibrary/steamapps/common/DCSWorld/CoreMods/aircraft")
HORNET = DCS / "FA-18C/DTC/SA"
VIPER = DCS / "F-16C/DTC/MPD"
installed = pytest.mark.skipif(not DCS.is_dir(), reason="DCS is not installed here")


def _named(path: Path) -> set[str]:
    return set(re.findall(r'name\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8")))


@installed
def test_every_name_used_is_one_both_aircraft_know() -> None:
    """A name a module does not have is an entry it drops without a word."""
    used = {name for name, _text in dtc.THREAT_BY_UNIT.values()}

    assert used <= _named(HORNET / "MEZ_THRTS_defs.lua")
    assert used <= _named(VIPER / "THREAT_PTS_defs.lua")


@installed
def test_the_vipers_own_numbering_is_its_own() -> None:
    """The index and the ceiling are ED's; a drifted copy silently mislabels a ring."""
    text = (VIPER / "THREAT_PTS_defs.lua").read_text(encoding="utf-8")
    theirs = {
        name: (int(number), int(altitude))
        for number, name, altitude in re.findall(
            r'\[(\d+)\]\s*=\s*\{name\s*=\s*"([^"]+)"[^}]*?altitude\s*=\s*(\d+)', text
        )
    }

    for name, ours in dtc.VIPER_THREAT_DEFS.items():
        assert theirs[name] == ours, name


@installed
def test_the_limits_are_the_ones_each_module_enforces() -> None:
    hornet = dtc.HornetCartridge()
    mez = (HORNET / "MEZ_THRTS.lua").read_text(encoding="utf-8")
    flot = (HORNET / "FAOR_FLOT.lua").read_text(encoding="utf-8")
    assert f"MAX_MEZ_THRTS    = {hornet.max_threats}" in mez
    assert f"MAX_FLOT_LINES  = {hornet.max_lines}" in flot
    assert f"MAX_LINE_POINTS = {hornet.max_line_points}" in flot

    viper = dtc.ViperCartridge()
    threats = (VIPER / "THREAT_PTS.lua").read_text(encoding="utf-8")
    lines = (VIPER / "GEO_LINES.lua").read_text(encoding="utf-8")
    assert f"#data.MPD.THREAT_PTS >= {viper.max_threats}" in threats
    assert f"#data.MPD.GEO_LINES > {viper.max_line_points - 1}" in lines


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


def test_the_mission_carries_its_own_cartridges(
    always_shown: None, tmp_path: Path
) -> None:
    """DCS 2.9.29 draws no rings at all without one, and a cartridge the player has
    to go and load is an errand rather than a feature."""
    import zipfile

    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")
    game = _game(_sam("HIPPO", 23, "SNR_75V"))
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
    import zipfile

    mission = tmp_path / "retribution_nextturn.miz"
    with zipfile.ZipFile(mission, "w") as archive:
        archive.writestr("mission", "-- a mission")

    assert dtc.write_into_mission(_game(), mission) == []

    with zipfile.ZipFile(mission) as archive:
        assert archive.namelist() == ["mission"]


def test_the_mirror_is_said_rather_than_left_where_it_was() -> None:
    """A cartridge silent about the mirror leaves it wherever the last one put it,
    and mirroring hands the page back to DCS -- which has no ring for an HQ-9."""
    hornet = dtc.HornetCartridge().sections([], [])
    viper = dtc.ViperCartridge().sections([], [])

    assert hornet["SA"]["mirror_MEZ_THRTS"] is False
    assert viper["MPD"]["mirror_THREAT_PTS"] is False
