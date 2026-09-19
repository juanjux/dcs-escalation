"""What goes in the aircraft's data cartridge.

The SA page's threat rings and its front line do not come from the mission at all --
they come from the .dtc file the DTC page loads -- so what the campaign writes into
that file is the whole feature. These read the file's contents before it is written.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.missiongenerator import dtc
from game.theater import Player
from game.utils import nautical_miles


from game.theater.theatergroundobject import SamGroundObject


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


def _game(*sites: Any, shows: bool = True) -> Any:
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


@pytest.fixture
def always_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtc, "shows_on_mfd", lambda _tgo, _settings: True)


def test_a_site_is_named_by_the_group_that_does_the_shooting(
    always_shown: None,
) -> None:
    """An S-300 with a Strela parked beside it is not a Strela."""
    site = _sam("BELUGA", 0, "")
    site.groups = [
        _group(64.8, "S-300PS 40B6M tr"),
        _group(2.5, "Strela-10M3"),
    ]

    threat = dtc.threats_for(_game(site), Player.BLUE)[0]

    assert threat.kind == "SAM SA-10 'Grumble'"
    assert threat.text == "10"
    assert threat.radius_nm == pytest.approx(64.8)


def test_a_system_dcs_has_no_entry_for_still_gets_its_ring(always_shown: None) -> None:
    """An HQ-9 is not on DCS's list, and mislabelling it is worse than Custom."""
    site = _sam("BELUGA", 0, "")
    site.groups = [_group(64.8, "HQ-9_SR_SJ_202"), _group(2.5, "Strela-10M3")]

    threat = dtc.threats_for(_game(site), Player.BLUE)[0]

    assert threat.kind == "Custom"
    assert threat.radius_nm == pytest.approx(64.8)


def test_what_the_displays_may_not_show_is_not_in_the_cartridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One question, asked once: the ring and the unit symbol agree."""
    monkeypatch.setattr(
        dtc, "shows_on_mfd", lambda tgo, _settings: tgo.name != "HIDDEN"
    )
    shown = _sam("SHOWN", 27, "SNR_75V")
    hidden = _sam("HIDDEN", 27, "SNR_75V")

    threats = dtc.threats_for(_game(shown, hidden), Player.BLUE)

    assert [threat.name for threat in threats] == ["SHOWN"]


def test_a_dead_site_is_not_a_threat(always_shown: None) -> None:
    site = _Site("WRECK", [_group(27, "SNR_75V")], dead=True)

    assert dtc.threats_for(_game(site), Player.BLUE) == []


def test_the_forty_the_cartridge_holds_are_the_forty_that_matter(
    always_shown: None,
) -> None:
    """What falls off the end should be the AAA nobody plans around."""
    sites = [_sam(f"SITE{n:02}", n, "SNR_75V") for n in range(1, 60)]

    threats = dtc.threats_for(_game(*sites), Player.BLUE)

    assert len(threats) == dtc.MAX_THREATS
    assert threats[0].radius_nm == pytest.approx(59)
    assert threats[-1].radius_nm == pytest.approx(20)


def test_a_threat_reads_as_the_cartridge_wants_it() -> None:
    threat = dtc.Threat("URCHIN", "SAM SA-10 'Grumble'", "10", 64.81, 5.0, 6.0)

    assert threat.as_dtc(3) == {
        "id": "MEZ_THRTS_3",
        "num": 3,
        "x": 5.0,
        "y": 6.0,
        "text": "10",
        "threat_type": "SAM SA-10 'Grumble'",
        "threat_ring_radius": 64.8,
        "threat_level": 1,
    }


def test_each_front_becomes_a_line(monkeypatch: pytest.MonkeyPatch) -> None:
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

    lines = dtc.flot_lines(cast(Any, theater))

    assert len(lines) == 1
    assert lines[0]["id"] == "FLOT_1"
    assert lines[0]["note"] == "Alpha to Bravo"
    points = cast(list[dict[str, Any]], lines[0]["points"])
    assert [point["id"] for point in points] == ["FLOT_1_PT_1", "FLOT_1_PT_2"]


def test_only_the_sections_the_campaign_fills_are_written(always_shown: None) -> None:
    """A partial cartridge is valid -- DCS ships its own defaults as one section --
    so nothing here invents radio presets or countermeasure programmes."""
    built = dtc.cartridge(
        _game(_sam("HIPPO", 23, "SNR_75V")), Player.BLUE, "FA-18C_hornet", "Escalation"
    )

    assert built["type"] == "FA-18C_hornet"
    data = cast(dict[str, Any], built["data"])
    assert set(data) == {"name", "type", "terrain", "SA"}
    assert data["terrain"] == "Falklands"
    assert set(data["SA"]) == {"MEZ_THRTS", "FAOR_FLOT"}


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
                        dcs_unit_type=SimpleNamespace(id="FA-18C_hornet")
                    ),
                ),
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


DEFS = Path(
    "D:/SteamLibrary/steamapps/common/DCSWorld/CoreMods/aircraft/FA-18C/DTC/SA/"
    "MEZ_THRTS_defs.lua"
)


@pytest.mark.skipif(not DEFS.is_file(), reason="DCS is not installed here")
def test_every_name_used_is_one_dcs_knows() -> None:
    """A name DCS does not have is an entry the SA page drops without a word."""
    known = set(re.findall(r'name = "([^"]+)"', DEFS.read_text(encoding="utf-8")))

    used = {name for name, _text in dtc.THREAT_BY_UNIT.values()}

    assert used <= known, sorted(used - known)


@pytest.mark.skipif(not DEFS.is_file(), reason="DCS is not installed here")
def test_the_limits_are_the_ones_the_module_enforces() -> None:
    """They are DCS's, not ours, so they are read off its own files."""
    sa = DEFS.parent
    mez = (sa / "MEZ_THRTS.lua").read_text(encoding="utf-8")
    flot = (sa / "FAOR_FLOT.lua").read_text(encoding="utf-8")

    assert f"MAX_MEZ_THRTS    = {dtc.MAX_THREATS}" in mez
    assert f"MAX_FLOT_LINES  = {dtc.MAX_FLOT_LINES}" in flot
    assert f"MAX_LINE_POINTS = {dtc.MAX_LINE_POINTS}" in flot


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
                        dcs_unit_type=SimpleNamespace(id="FA-18C_hornet")
                    ),
                )
            ]
        )
    ]

    written = dtc.write_cartridges(game, tmp_path)

    assert [path.name for path in written] == [
        "Escalation A Campaign FA-18C_hornet.dtc"
    ]
    assert "MEZ_THRTS" in written[0].read_text(encoding="utf-8")
