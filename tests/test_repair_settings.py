"""Damage settings grouping, dependency controls and saved-unit migration."""

import os
import pickle
from types import SimpleNamespace
from typing import Any

import pytest

from game.settings import Settings
from game.settings.settings import (
    AIRCRAFT_REPAIRS_BOX,
    CAMPAIGN_MANAGEMENT_PAGE,
    HQ_AUTOMATION_SECTION,
    PERSISTENT_DAMAGE_SECTION,
    REPAIR_TIMES_BOX,
    SHIP_BUILDING_REPAIRS_BOX,
)
from game.theater.controlpoint import ControlPoint, RunwayStatus


def test_repair_settings_have_one_subpage_and_three_boxes() -> None:
    assert PERSISTENT_DAMAGE_SECTION in Settings.sections(CAMPAIGN_MANAGEMENT_PAGE)
    assert list(
        Settings.subsections(CAMPAIGN_MANAGEMENT_PAGE, PERSISTENT_DAMAGE_SECTION)
    ) == [
        AIRCRAFT_REPAIRS_BOX,
        SHIP_BUILDING_REPAIRS_BOX,
        REPAIR_TIMES_BOX,
    ]
    hq = dict(Settings.fields(CAMPAIGN_MANAGEMENT_PAGE, HQ_AUTOMATION_SECTION))
    for name in (
        "automate_runway_repair",
        "automate_building_repairs",
        "automate_ground_object_repairs",
    ):
        assert name in hq
    durations = dict(
        Settings.fields(
            CAMPAIGN_MANAGEMENT_PAGE, PERSISTENT_DAMAGE_SECTION, REPAIR_TIMES_BOX
        )
    )
    assert set(durations) == {
        "building_repair_turns",
        "ground_object_repair_turns",
        "runway_repair_turns",
    }
    assert not set(durations) & set(hq)
    assert all(option.enabled_when is None for option in durations.values())


@pytest.mark.parametrize("price", [0, 0.05, 0.125, 10])
def test_old_mechanic_cost_migrates_once_in_presets_and_pickled_campaigns(
    price: float,
) -> None:
    saved = {
        "aircraft_mechanic_price": price,
        "aircraft_repair_percent": 100 / 3,
        "persistent_damage_repair_percent": 30,
    }
    migrated = Settings.deserialize_state_dict(dict(saved))
    assert migrated["aircraft_mechanic_cost"] == round(price * 1_000_000)
    assert "aircraft_mechanic_price" not in migrated
    assert Settings.deserialize_state_dict(dict(migrated)) == migrated
    settings = Settings.__new__(Settings)
    settings.__setstate__(saved)
    restored = pickle.loads(pickle.dumps(settings))
    assert restored.aircraft_mechanic_cost == round(price * 1_000_000)
    assert restored.aircraft_repair_percent == 100 / 3
    assert restored.persistent_damage_repair_percent == 30


def test_new_dollar_cost_takes_precedence_over_a_stale_legacy_key() -> None:
    result = Settings.deserialize_state_dict(
        {"aircraft_mechanic_price": 0.05, "aircraft_mechanic_cost": 123456}
    )
    assert result["aircraft_mechanic_cost"] == 123456


def test_defaults_are_fifty_thirty_four_and_fifty_thousand_dollars() -> None:
    settings = Settings()
    assert settings.aircraft_repair_percent == 50
    assert settings.persistent_damage_repair_percent == 34
    assert settings.aircraft_mechanic_cost == 50_000


@pytest.mark.parametrize("turns", [0, 1, 4, 7])
def test_manual_and_automatic_runway_entrypoint_uses_campaign_duration(
    turns: int,
) -> None:
    settings = Settings()
    settings.runway_repair_turns = turns
    runway = RunwayStatus(damaged=True)
    base: Any = SimpleNamespace(
        runway_can_be_repaired=True,
        runway_status=runway,
        coalition=SimpleNamespace(game=SimpleNamespace(settings=settings)),
    )
    ControlPoint.begin_runway_repair(base)
    assert runway.repair_turns_remaining == (turns or None)
    for _ in range(turns):
        assert runway.damaged
        runway.process_turn()
    assert not runway.damaged
    assert runway.repair_turns_remaining is None


def test_damage_subpage_controls_grey_out_independently_and_refresh_live(
    tmp_path: Any,
) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QCheckBox, QSpinBox, QWidget
    from qt_ui.windows.settings.QSettingsWindow import AutoSettingsLayout
    from qt_ui.widgets.spinsliders import FloatSpinSlider

    app = QApplication.instance() or QApplication([])
    settings = Settings()
    container: Any = SimpleNamespace(settings=settings)
    layout = AutoSettingsLayout(
        CAMPAIGN_MANAGEMENT_PAGE, PERSISTENT_DAMAGE_SECTION, container, lambda: None
    )
    widget = QWidget()
    widget.setLayout(layout)
    aircraft = layout.settings_map["aircraft_maintenance_enabled"]
    ships = layout.settings_map["persistent_damage_enabled"]
    assert isinstance(aircraft, QCheckBox) and isinstance(ships, QCheckBox)

    def check_dependents(box: str, enabled: bool, switch: str) -> None:
        for name, _ in Settings.fields(
            CAMPAIGN_MANAGEMENT_PAGE, PERSISTENT_DAMAGE_SECTION, box
        ):
            if name == switch:
                assert layout.label_map[name].isEnabled()
                continue
            assert layout.label_map[name].isEnabled() == enabled
            control = layout.settings_map[name]
            if isinstance(control, FloatSpinSlider):
                assert control.spinner.isEnabled() == enabled
                slider_item = control.itemAt(0)
                assert slider_item is not None
                slider = slider_item.widget()
                assert slider is not None and slider.isEnabled() == enabled
            else:
                assert control.isEnabled() == enabled

    check_dependents(AIRCRAFT_REPAIRS_BOX, False, "aircraft_maintenance_enabled")
    check_dependents(SHIP_BUILDING_REPAIRS_BOX, True, "persistent_damage_enabled")
    aircraft.setChecked(True)
    ships.setChecked(False)
    check_dependents(AIRCRAFT_REPAIRS_BOX, True, "aircraft_maintenance_enabled")
    check_dependents(SHIP_BUILDING_REPAIRS_BOX, False, "persistent_damage_enabled")
    cost = layout.settings_map["aircraft_mechanic_cost"]
    assert isinstance(cost, QSpinBox) and cost.value() == 50_000
    cost.setValue(75_000)
    assert settings.aircraft_mechanic_cost == 75_000
    for name in (
        "building_repair_turns",
        "ground_object_repair_turns",
        "runway_repair_turns",
    ):
        assert layout.settings_map[name].isEnabled()
    aircraft.setChecked(False)
    check_dependents(AIRCRAFT_REPAIRS_BOX, False, "aircraft_maintenance_enabled")
    widget.resize(1250, 1100)
    widget.show()
    app.processEvents()
    assert widget.grab().save(str(tmp_path / "repair-settings.png"))
    widget.close()
