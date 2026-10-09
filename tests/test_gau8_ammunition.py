"""Gun ammunition survives payload editing, persistence and mission generation."""

import pickle
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dcs import Mission, Point, lua
from dcs.planes import A_10A, A_10C, A_10C_2, FA_18C_hornet
from dcs.terrain import Caucasus

from game.ato.flightmember import FlightMember
from game.ato.flightmembers import FlightMembers
from game.ato.flighttype import FlightType
from game.ato.loadouts import Loadout
from game.data.gunammunition import GAU8_AMMUNITION
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)


@pytest.mark.parametrize("ammo", [1, 2, 3, None])
def test_loadout_copies_and_save_reload_preserve_ammunition(ammo: int | None) -> None:
    loadout = Loadout("Test", {}, None, ammo_type=ammo)
    for copy in (
        loadout.clone(),
        loadout.derive_custom("Custom"),
        pickle.loads(pickle.dumps(loadout)),
    ):
        assert copy.ammo_type == ammo
    # Both date-degradation paths must retain the gun's selected ammunition.
    aircraft: Any = SimpleNamespace(has_built_in_target_pod=False)
    faction: Any = SimpleNamespace()
    for loadout_date in (None, date(1990, 1, 1)):
        loadout.date = loadout_date
        assert (
            loadout.degrade_for_date(aircraft, date(2000, 1, 1), faction).ammo_type
            == ammo
        )


def test_old_save_defaults_to_unspecified_ammunition() -> None:
    loadout = Loadout.__new__(Loadout)
    loadout.__setstate__(
        {"name": "Old", "pylons": {}, "date": None, "is_custom": False}
    )
    assert loadout.ammo_type is None


@pytest.mark.parametrize("ammo", [1, 2, 3])
def test_named_presets_and_task_defaults_keep_ammunition(
    ammo: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = {"CAS": {"name": "CAS", "pylons": {}, "ammo_type": ammo}}
    monkeypatch.setattr(A_10C_2, "load_payloads", classmethod(lambda cls: payloads))
    monkeypatch.setattr(A_10C_2, "payloads", payloads)
    aircraft: Any = SimpleNamespace(dcs_unit_type=A_10C_2)
    assert next(Loadout.iter_for_aircraft(aircraft)).ammo_type == ammo
    assert (
        Loadout.default_for_task_and_aircraft(FlightType.CAS, A_10C_2).ammo_type == ammo
    )


def test_shared_and_independent_member_loadouts_keep_ammunition() -> None:
    roster = FlightMembers.__new__(FlightMembers)
    roster.members = [
        FlightMember(None, Loadout("Test", {}, None, ammo_type=n)) for n in (1, 2)
    ]
    roster.use_same_loadout_for_all_members()
    roster.members[0].loadout.ammo_type = 3
    assert roster.members[1].loadout.ammo_type == 3
    roster.use_distinct_loadouts_for_each_member()
    roster.members[0].loadout.ammo_type = 2
    assert roster.members[1].loadout.ammo_type == 3


@pytest.mark.parametrize("aircraft", [A_10A, A_10C, A_10C_2, FA_18C_hornet])
def test_generated_mission_contains_each_guns_selected_ammunition(
    aircraft: Any, tmp_path: Path
) -> None:
    mission = Mission(Caucasus())
    group = mission.flight_group(
        mission.country("USA"),
        "Ammo test",
        aircraft,
        airport=None,
        position=Point(-200000, 600000, mission.terrain),
        group_size=4,
    )
    generator = FlightGroupConfigurator.__new__(FlightGroupConfigurator)
    generator.game = SimpleNamespace(settings=SimpleNamespace(restrict_weapons_by_date=False))  # type: ignore[assignment]
    for unit, ammo in zip(group.units, (1, 2, 3, None)):
        generator.setup_payload(
            unit, FlightMember(None, Loadout("Ammo", {}, None, ammo_type=ammo))
        )
    path = tmp_path / "ammunition.miz"
    mission.save(str(path))
    with zipfile.ZipFile(path) as archive:
        data = lua.loads(archive.read("mission").decode("utf-8"))["mission"]
    units = [
        unit
        for country in data["coalition"]["blue"]["country"].values()
        for flight in country.get("plane", {}).get("group", {}).values()
        for unit in flight["units"].values()
    ]
    assert len(units) == 4
    expected: list[int | None] = (
        [None] * 4 if aircraft is FA_18C_hornet else [1, 2, 3, 1]
    )
    assert [unit["payload"].get("ammo_type") for unit in units] == expected


def test_gau8_choices_match_installed_dcs() -> None:
    root = Path("D:/SteamLibrary/steamapps/common/DCSWorld/CoreMods/aircraft/A-10")
    if not root.is_dir():
        pytest.skip("DCS is not installed here")
    text = (root / "A-10A.lua").read_text(encoding="utf-8")
    block = text[text.index("ammo_type =") : text.index("Guns =")]
    assert [block.index(label) for label in GAU8_AMMUNITION.values()] == sorted(
        block.index(label) for label in GAU8_AMMUNITION.values()
    )
    assert "defines only differences between A-10C and A-10A" in (
        root / "A-10C.lua"
    ).read_text(encoding="utf-8")
    assert "defines only differences between A-10C 2 and A-10C" in (
        root / "A-10C_2.lua"
    ).read_text(encoding="utf-8")
