"""Dependency confirmations leave both switches coherent on accept and cancel."""

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QGridLayout, QMessageBox, QSpinBox, QWidget

from game.groundmovement import settings as movement
from game.settings import Settings
from game.settings.optiondescription import SETTING_DESCRIPTION_KEY


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Any:
    from qt_ui import uiconstants

    monkeypatch.setitem(uiconstants.ICONS, "Settings", QIcon())
    return QApplication.instance() or QApplication([])


def test_enable_cancel_and_accept_update_switches_and_options(
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QCheckBox
    from game.settings.settings import GROUND_MOVEMENT_SECTION, MISSION_GENERATOR_PAGE
    from qt_ui.windows.settings.QSettingsWindow import AutoSettingsLayout

    settings = Settings(motorpool_enabled=False)
    container: Any = SimpleNamespace(settings=settings)
    widget = QWidget()
    layout = AutoSettingsLayout(
        MISSION_GENERATOR_PAGE, GROUND_MOVEMENT_SECTION, container, lambda: None
    )
    widget.setLayout(layout)
    checkbox = layout.settings_map["ground_movement_enabled"]
    budget = layout.settings_map["ground_movement_road_miles_per_turn"]
    assert isinstance(checkbox, QCheckBox) and isinstance(budget, QSpinBox)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    checkbox.setChecked(True)
    assert not checkbox.isChecked() and not budget.isEnabled()
    assert vars(settings)["motorpool_enabled"] is False
    assert not movement.requested(settings)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    checkbox.setChecked(True)
    assert checkbox.isChecked() and budget.isEnabled() and budget.value() == 120
    assert movement.enabled(settings) and settings.motorpool_enabled
    checkbox.setChecked(False)
    assert not movement.requested(settings) and not budget.isEnabled()
    assert settings.motorpool_enabled
    widget.close()


def test_motorpool_checkbox_cancel_accept_and_programmatic_refresh(
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qt_ui.windows.settings.QSettingsWindow import (
        AutoSettingsLayout,
        QSettingsWidget,
    )

    settings = Settings()
    movement.set_enabled(settings, True)
    parent = QWidget()
    layout = QGridLayout(parent)
    changed: list[bool] = []
    owner: Any = SimpleNamespace(
        sc=SimpleNamespace(settings=settings),
        settings_map={},
        settings_changed=lambda: changed.append(True),
        addWidget=layout.addWidget,
        write_full_settings=lambda: None,
    )
    description = Settings.__dataclass_fields__["motorpool_enabled"].metadata[
        SETTING_DESCRIPTION_KEY
    ]
    AutoSettingsLayout.add_checkbox_for(owner, 0, "motorpool_enabled", description)
    checkbox = owner.settings_map["motorpool_enabled"]
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    checkbox.setChecked(False)
    assert checkbox.isChecked() and vars(settings)["motorpool_enabled"] is True
    assert movement.enabled(settings) and not changed
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    checkbox.setChecked(False)
    assert not checkbox.isChecked() and vars(settings)["motorpool_enabled"] is False
    assert not movement.requested(settings) and changed == [True]

    movement.set_enabled(settings, True, enable_motorpool=True)
    container: Any = SimpleNamespace(
        settings=settings,
        pluginsPage=SimpleNamespace(update_from_settings=lambda: None),
        pages={
            "test": SimpleNamespace(
                groups=[SimpleNamespace(layout=owner)], refresh_page=lambda: None
            )
        },
    )
    QSettingsWidget.refresh_all_pages(container)
    assert checkbox.isChecked() and changed == [True]
    parent.close()
