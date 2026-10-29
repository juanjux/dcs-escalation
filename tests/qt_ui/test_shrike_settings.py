"""The weapon editor shows target matching without converting manual picks."""

from types import SimpleNamespace
from typing import Any
import importlib
import os

import pytest
from dcs.planes import F_4E_45MC

from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon, Weapon

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("player", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_editor_preserves_automatic_and_manual_heads(
    qt_app: Any,
    manual: bool,
    player: bool,
    enabled: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(
        "qt_ui.windows.mission.flight.payload.QPylonEditor"
    )
    head = "NFP_rfgu_type"
    weapon = Weapon.with_clsid("{LAU_34_AGM_45A}")
    assert weapon is not None
    loadout = Loadout("Shrike", {1: weapon}, None)
    if manual:
        loadout.pylon_settings[1] = {head: 9, "smoke_marker": 1, "mod_setting": 42}
    pilot: Any = SimpleNamespace(player=player)
    member = FlightMember(pilot, loadout)
    flight: Any = SimpleNamespace(
        unit_type=SimpleNamespace(dcs_unit_type=F_4E_45MC),
        package=SimpleNamespace(target=object()),
    )
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(
            restrict_weapons_by_date=False,
            apply_target_overrides_to_loadouts=enabled,
        )
    )
    monkeypatch.setattr(
        Loadout, "target_unit_ids", staticmethod(lambda _t: ("snr s-125 tr",))
    )
    shown = []

    class Dialog:
        def __init__(self, store: Weapon, settings: Any, parent: Any) -> None:
            self.settings = store.create_settings(settings)
            assert self.settings is not None
            shown.append(self.settings.to_dict())

        def exec(self) -> bool:
            return True

        def get_settings_dict(self) -> Any:
            assert self.settings is not None
            return self.settings.to_dict()

    monkeypatch.setattr(module, "QWeaponSettingsDialog", Dialog)
    editor = module.QPylonEditor(game, flight, member, Pylon(1, {weapon}))
    editor.open_settings_dialog()
    matches = not player or enabled
    assert shown[0][head] == (9 if manual or matches else 1)
    assert loadout.pylon_settings[1][head] == (9 if manual else 1)
    if manual:
        assert loadout.pylon_settings[1]["smoke_marker"] == 1
        assert loadout.pylon_settings[1]["mod_setting"] == 42
    editor.close()
