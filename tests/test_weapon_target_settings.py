"""Target-matched Shrike settings, adapted from RetLab #1366."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import zipfile

import pytest
from dcs import Mission, Point, lua
from dcs.planes import F_4E_45MC
from dcs.terrain import Caucasus

from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon, Weapon
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)

SHRIKE = "{LAU_34_AGM_45B}"
HEAD = "NFP_rfgu_type"
SA3 = ("p-19 s-125 sr", "snr s-125 tr")
SA2 = ("p-19 s-125 sr", "SNR_75V")


def _shrike() -> Weapon:
    weapon = Weapon.with_clsid(SHRIKE)
    assert weapon is not None
    return weapon


def test_matched_head_comes_with_the_full_table() -> None:
    settings = _shrike().settings_for_target(None, SA3)
    assert settings is not None
    assert settings[HEAD] == 9  # Mk 49 Mod 1
    # DCS reads an absent key as not fitted, so the rest are written too.
    assert settings["EAS_bypass_ctrl"] == 1
    assert settings["smoke_marker"] == 0


def test_fan_song_gets_its_own_head_before_the_flat_face_rule() -> None:
    settings = _shrike().settings_for_target(None, SA2)
    assert settings is not None
    assert settings[HEAD] == 5  # Mk 25


def test_an_unlisted_radar_gets_the_broad_head() -> None:
    settings = _shrike().settings_for_target(None, ("Hawk tr", "Hawk sr"))
    assert settings is not None
    assert settings[HEAD] == 10  # Mk 50


def test_a_hand_set_head_and_profile_survive() -> None:
    stored = {HEAD: 2, "EAS_bypass_ctrl": 0, "smoke_marker": 1}
    settings = _shrike().settings_for_target(stored, SA3)
    assert settings is not None
    assert settings[HEAD] == 2
    assert settings["EAS_bypass_ctrl"] == 0
    assert settings["smoke_marker"] == 1


def test_a_head_left_at_default_is_matched_with_the_profile_kept() -> None:
    stored = {HEAD: 1, "EAS_bypass_ctrl": 0}
    settings = _shrike().settings_for_target(stored, SA3)
    assert settings is not None
    assert settings[HEAD] == 9
    assert settings["EAS_bypass_ctrl"] == 0


def test_no_target_leaves_the_stored_settings_alone() -> None:
    stored = {HEAD: 3}
    assert _shrike().settings_for_target(stored, ()) is stored


def test_saving_the_matched_head_stores_it_as_automatic() -> None:
    weapon = _shrike()
    shown = weapon.settings_for_target(None, SA3)
    assert shown is not None
    saved = weapon.strip_target_settings(shown, SA3)
    assert saved[HEAD] == 1
    # Still follows the target once saved.
    again = weapon.settings_for_target(saved, SA2)
    assert again is not None and again[HEAD] == 5


def test_a_different_saved_head_is_kept_as_a_hand_pick() -> None:
    weapon = _shrike()
    saved = weapon.strip_target_settings({HEAD: 2, "EAS_bypass_ctrl": 1}, SA3)
    assert saved[HEAD] == 2


def test_manual_head_matching_target_is_not_reset_by_opening_editor() -> None:
    stored = {HEAD: 9}
    weapon = _shrike()
    shown = weapon.settings_for_target(stored, SA3)
    assert shown is not None
    saved = weapon.strip_target_settings(shown, SA3, stored)
    assert saved[HEAD] == 9
    rematched = weapon.settings_for_target(saved, SA2)
    assert rematched is not None and rematched[HEAD] == 9


def test_target_settings_preserve_unrecognized_mod_settings() -> None:
    stored = {"custom_mod_setting": 42}
    result = _shrike().settings_for_target(stored, SA3)
    assert result is not None
    assert result["custom_mod_setting"] == 42
    assert stored == {"custom_mod_setting": 42}


def test_raw_payload_keeps_settings_and_does_not_mutate_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [(1, {"clsid": SHRIKE, "settings": {HEAD: 2, "smoke_marker": 1}})]
    monkeypatch.setattr(Loadout, "target_unit_ids", staticmethod(lambda _t: SA3))
    result = Loadout.adjust_payload_for_target(payload, object())  # type: ignore[arg-type]
    assert result[0][1]["settings"][HEAD] == 2
    assert result[0][1]["settings"]["smoke_marker"] == 1
    assert result[0][1]["settings"]["EAS_bypass_ctrl"] == 1
    assert payload[0][1]["settings"] == {HEAD: 2, "smoke_marker": 1}


@pytest.mark.parametrize("restrict_date", [False, True])
@pytest.mark.parametrize("player", [False, True])
@pytest.mark.parametrize("player_overrides", [False, True])
def test_generation_matches_heads_independently_of_date_and_serializes_settings(
    restrict_date: bool,
    player: bool,
    player_overrides: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mission = Mission(Caucasus())
    group = mission.flight_group(
        mission.country("USA"),
        "Shrike test",
        F_4E_45MC,
        airport=None,
        position=Point(-200000, 600000, mission.terrain),
        group_size=1,
    )
    aircraft: Any = SimpleNamespace(dcs_unit_type=F_4E_45MC)
    weapon = Weapon.with_clsid("{LAU_34_AGM_45A}")
    assert weapon is not None
    pylon = next(p for p in Pylon.iter_pylons(aircraft) if p.can_equip(weapon))
    loadout = Loadout("Shrike", {pylon.number: weapon}, None, is_custom=True)
    loadout.pylon_settings[pylon.number] = {"smoke_marker": 1}
    pilot: Any = SimpleNamespace(player=player)
    member = FlightMember(pilot, loadout)
    generator = FlightGroupConfigurator.__new__(FlightGroupConfigurator)
    generator.game = SimpleNamespace(  # type: ignore[assignment]
        date=date(2000, 1, 1),
        settings=SimpleNamespace(
            restrict_weapons_by_date=restrict_date,
            apply_target_overrides_to_loadouts=player_overrides,
        ),
    )
    generator.flight = SimpleNamespace(  # type: ignore[assignment]
        package=SimpleNamespace(target=object()),
        unit_type=aircraft,
        squadron=SimpleNamespace(coalition=SimpleNamespace(faction=SimpleNamespace())),
    )
    monkeypatch.setattr(Loadout, "target_unit_ids", staticmethod(lambda _t: SA3))
    generator.setup_payload(group.units[0], member)
    output = tmp_path / "shrike.miz"
    mission.save(str(output))
    with zipfile.ZipFile(output) as archive:
        data = lua.loads(archive.read("mission").decode("utf-8"))["mission"]
    countries = data["coalition"]["blue"]["country"].values()
    units = [
        u
        for c in countries
        for g in c.get("plane", {}).get("group", {}).values()
        for u in g["units"].values()
    ]
    settings = units[0]["payload"]["pylons"][pylon.number]["settings"]
    if not player or player_overrides:
        assert settings[HEAD] == 9
        assert settings["EAS_bypass_ctrl"] == 1
    else:
        assert HEAD not in settings
    assert settings["smoke_marker"] == 1
    assert loadout.pylon_settings[pylon.number] == {"smoke_marker": 1}


def test_loadout_applies_heads_per_pylon(monkeypatch: pytest.MonkeyPatch) -> None:
    weapon = _shrike()
    loadout = Loadout("test", {1: weapon, 2: weapon}, date=None)
    loadout.pylon_settings[2] = {HEAD: 4}
    monkeypatch.setattr(Loadout, "target_unit_ids", staticmethod(lambda _t: SA3))
    target: Any = object()
    loadout.apply_target_overrides(target)
    assert loadout.pylon_settings[1][HEAD] == 9
    assert loadout.pylon_settings[2][HEAD] == 4


@pytest.mark.parametrize("clsid", ["{AGM_78A}", "{AGM_78B}"])
def test_standard_arms_have_one_head_and_no_overrides(clsid: str) -> None:
    weapon = Weapon.with_clsid(clsid)
    assert weapon is not None
    assert weapon.get_target_overrides(SA3) == {}
