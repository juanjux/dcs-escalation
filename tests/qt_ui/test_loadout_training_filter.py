"""Filtering pylon choices must never change the fitted payload."""

import os
import sys
from datetime import date
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import Mock

import pytest

from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon, Weapon, WeaponGroup, WeaponType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def qt_errors(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    errors: list[Any] = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: errors.append(args))
    yield
    assert not errors


def store(name: str, clsid: str = "test", year: int | None = None) -> Weapon:
    group = WeaponGroup("Test", WeaponType.UNKNOWN, year, None)
    weapon = Weapon(clsid, group)
    object.__setattr__(
        weapon, "pydcs_data", {"name": name, "clsid": clsid, "weight": 100}
    )
    return weapon


@pytest.mark.parametrize(
    "name",
    [
        "Smoke Generator - red",
        "Smokewinder - blue",
        "OV10_SMOKE",
        "LAU-105 - 2 x Captive AIM-9M for ACM",
        "LAU-117 - CATM-65K - Captive Trg Round for Mav K (CCD)",
        "Python-5 Training",
        "R-8R Inert",
        "CBU_DUMMY pod",
        "LAU-68 M274 Practice Smk",
        "BDU-50HD * 6",
        "BRU-41A - 4 x BDU-33",
        "AN/ASQ-T50 TCTS Pod - ACMI Pod",
        "SUU-25 - 8 x Illumination Flare, LUU-2B",
        "SUU-25 * 8 LUU-2",
        "2 LUU-2",
        "SAB-100MN",
        "LGTR",
        "LAU-117 - TGM-65D - Trg Round for Mav D (IIR)",
        "TGM-65G",
        "TGM-65H",
        "MXU-648 Travel Pod",
        "LAU-131 M156 WP",
        '2x LAU-3 pod - 19 x 2.75" FFAR, UnGd Rkts M156, Wht Phos (TER)',
        "B-8M1 - 20 x UnGd Rkts, 80 mm S-8OM IL",
        "B-8V20A - 20 x UnGd Rkts, 80 mm S-8TsM SM Orange",
        "MATRA F1 - 36 x UnGd Rkts, 68 mm SNEB Type 250 F1B TP-SM",
        "Telson 8 - 8 x UnGd Rkts, 68 mm SNEB Type 252 H1 TP",
    ],
)
def test_training_and_non_combat_names(name: str) -> None:
    assert store(name).is_training_or_non_combat


@pytest.mark.parametrize(
    "name",
    [
        "AIM-9M Sidewinder",
        "CBU-105 WCMD",
        "GBU-54 Laser & GPS Guided Bomb",
        "Inertial guided missile",
        "Fuel tank FT600",
        "AN/AAQ-28 LITENING - Targeting Pod",
        "ALQ-184 - ECM Pod",
        "ADM-141 TALD",
        "ALE-40 Dispensers (30 Flares)",
        "Eclair-M 6/0 : 48 flares",
        "KB Flare/Chaff dispenser pod",
        "Mk-84 AIR TP * 2",
        "Mk-84 AIR (BSU-50) - 2000 lb TP Chute Retarded Bomb HD",
        "SM-2 Standard Missile",
        "APU-68 - S-24B - 240mm UnGd Rkt, 235kg, HE/Frag, (Low Smk)",
        "APU-6 - 6 x 9M127 Vikhr - ATGM, LOSBR, Tandem HEAT/Frag",
        "LAU-131 - 7 x UnGd Rkts, 70 mm Hydra 70 M151 HE",
        "LAU-68 - 7 x UnGd Rkts, 70 mm Hydra 70 Mk 5 HEAT",
        "LAU-131 - 7 x Laser Guided Rkts, 70 mm Hydra 70 M282 MPP APKWS",
        "Clean",
        "Unknown mod store",
    ],
)
def test_combat_and_support_stores_stay_visible(name: str) -> None:
    assert not store(name).is_training_or_non_combat


def test_clsid_identifies_short_mod_names() -> None:
    assert store("Sidewinder", "{MOD_LAU127_CATM-9M}").is_training_or_non_combat


@pytest.mark.parametrize("pod", ["LAU-131", "LAU-68"])
@pytest.mark.parametrize(
    "round_name",
    ["M156 SM", "M257 IL", "M274 TP-SM", "Mk 1 HE", "Mk 61 TP", "WTU-1/B TP"],
)
@pytest.mark.parametrize("rack", ["", "BRU-42: 2 x ", "BRU-42: 3 x "])
def test_hydra_rocket_roles(pod: str, round_name: str, rack: str) -> None:
    name = f"{rack}{pod} - 7 x UnGd Rkts, 70 mm Hydra 70 {round_name}"
    assert store(name).is_training_or_non_combat


def test_real_a10_rocket_choices_are_filtered(app: Any) -> None:
    from dcs.planes import A_10C_2
    from qt_ui.windows.mission.flight.payload.QPylonEditor import QPylonEditor

    aircraft: Any = SimpleNamespace(dcs_unit_type=A_10C_2)
    flight: Any = SimpleNamespace(unit_type=aircraft)
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(restrict_weapons_by_date=False)
    )
    member = FlightMember(None, Loadout("Empty", {}, None))
    pylon = Pylon.for_aircraft(aircraft, 2)
    editor = QPylonEditor(game, flight, member, pylon)
    roles = ("M156 SM", "M257 IL", "M274 TP-SM", "Mk 1 HE", "Mk 61 TP", "WTU-1/B TP")
    for role in roles:
        weapons = [w for w in pylon.allowed if role in w.name]
        assert weapons, role
        for weapon in weapons:
            assert editor.weapon_combo.findData(weapon) == -1, weapon.name
    editor.set_show_training(True)
    for weapon in pylon.allowed:
        assert editor.weapon_combo.findData(weapon) >= 0, weapon.name
    assert member.loadout.pylons == {}


@pytest.fixture
def setup_editor(app: Any) -> Any:
    from qt_ui.windows.mission.flight.payload.QPylonEditor import QPylonEditor

    live = store("AIM-9M", "live")
    captive = store("Captive AIM-9M", "captive")
    future = store("Future training round", "future", 2099)
    pylon = Pylon(1, {live, captive, future})
    member = FlightMember(None, Loadout("Custom", {1: live}, None, True))
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(
            restrict_weapons_by_date=False, apply_target_overrides_to_loadouts=False
        ),
        date=date(2000, 1, 1),
    )
    flight: Any = SimpleNamespace(
        squadron=SimpleNamespace(coalition=SimpleNamespace(faction=SimpleNamespace())),
        unit_type=None,
    )
    return SimpleNamespace(
        editor=QPylonEditor(game, flight, member, pylon),
        live=live,
        captive=captive,
        future=future,
        member=member,
        flight=flight,
        game=game,
        pylon=pylon,
    )


def test_filter_defaults_off_and_never_changes_payload(setup_editor: Any) -> None:
    data = setup_editor
    editor = data.editor
    combo = editor.weapon_combo
    changed = Mock()
    editor.pylon_changed.connect(changed)
    data.member.loadout.pylon_settings[1] = {"laser_code": 1688}
    assert combo.findData(data.captive) == -1
    assert combo.currentData() == data.live
    for show in (True, False, True, False):
        editor.set_show_training(show)
        assert (combo.findData(data.captive) >= 0) == show
        assert combo.currentData() == data.live
        assert data.member.loadout.pylons == {1: data.live}
        assert data.member.loadout.pylon_settings == {1: {"laser_code": 1688}}
    changed.assert_not_called()


def test_fitted_training_store_remains_until_replaced(setup_editor: Any) -> None:
    data = setup_editor
    editor = data.editor
    combo = editor.weapon_combo
    editor.set_show_training(True)
    combo.setCurrentIndex(combo.findData(data.captive))
    data.member.loadout.pylon_settings[1] = {"test": 42}
    editor.set_show_training(False)
    assert combo.currentData() == data.captive
    assert data.member.loadout.pylons[1] == data.captive
    assert data.member.loadout.pylon_settings[1] == {"test": 42}
    combo.setCurrentIndex(combo.findData(data.live))
    assert combo.findData(data.captive) == -1
    assert 1 not in data.member.loadout.pylon_settings
    combo.setCurrentIndex(0)
    assert data.member.loadout.pylons[1] is None


def test_preset_and_member_changes_display_hidden_stores(setup_editor: Any) -> None:
    data = setup_editor
    training = Loadout("Training", {1: data.captive}, None)
    data.member.loadout = training
    data.editor.set_from(training)
    assert data.editor.weapon_combo.currentData() == data.captive
    second = FlightMember(None, Loadout("Combat", {1: data.live}, None))
    data.editor.set_flight_member(second)
    assert data.editor.weapon_combo.currentData() == data.live
    assert data.editor.weapon_combo.findData(data.captive) == -1
    assert training.pylons == {1: data.captive}


def test_clean_pylon_survives_filter_changes(setup_editor: Any) -> None:
    clean = Weapon.with_clsid("<CLEAN>")
    assert clean is not None
    data = setup_editor
    data.member.loadout = Loadout("Clean", {1: clean}, None)
    data.editor.set_from(data.member.loadout)
    for show in (True, False, True):
        data.editor.set_show_training(show)
        assert data.editor.weapon_combo.currentData() == clean
        assert data.member.loadout.pylons[1] == clean


def test_show_training_still_respects_date_restrictions(setup_editor: Any) -> None:
    from qt_ui.windows.mission.flight.payload.QPylonEditor import QPylonEditor

    data = setup_editor
    data.game.settings.restrict_weapons_by_date = True
    editor = QPylonEditor(data.game, data.flight, data.member, data.pylon)
    editor.set_show_training(True)
    assert editor.weapon_combo.findData(data.captive) >= 0
    assert editor.weapon_combo.findData(data.future) == -1


def test_checkbox_updates_all_pylons(setup_editor: Any, monkeypatch: Any) -> None:
    from qt_ui.windows.mission.flight.payload.QLoadoutEditor import QLoadoutEditor

    data = setup_editor
    monkeypatch.setattr(
        Pylon,
        "iter_pylons",
        classmethod(
            lambda cls, aircraft: iter([data.pylon, Pylon(2, data.pylon.allowed)])
        ),
    )
    editor = QLoadoutEditor(data.flight, data.member, data.game)
    assert editor.show_training_check.text() == "Show training and non-combat"
    assert not editor.show_training_check.isChecked()
    for show in (True, False):
        editor.show_training_check.setChecked(show)
        for pylon in editor.iter_pylon_editors():
            assert (pylon.weapon_combo.findData(data.captive) >= 0) == show
    assert data.member.loadout.pylons == {1: data.live}


def test_search_cannot_reveal_filtered_stores(setup_editor: Any) -> None:
    combo = setup_editor.editor.weapon_combo
    combo.threshold = 1
    combo.showPopup()
    combo._search.setText("captive")
    assert combo.findData(setup_editor.captive) == -1
    combo.hidePopup()
