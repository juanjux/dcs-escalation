"""Dependency confirmations leave both switches coherent on accept and cancel."""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QGridLayout, QMessageBox, QSpinBox, QWidget

from game.groundmovement import settings as movement
from game.plugins import LuaPlugin, LuaPluginManager
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
    tmp_path: Path,
) -> None:
    from qt_ui.windows.settings.plugins import PluginsPage, PluginOptionsBox

    plugin = LuaPlugin.from_json(
        "groundmovement", Path("resources/plugins/groundmovement/plugin.json")
    )
    assert plugin is not None
    monkeypatch.setattr(LuaPluginManager, "_plugins", {"groundmovement": plugin})
    monkeypatch.setattr(LuaPluginManager, "_plugins_loaded", True)
    settings = Settings()
    settings.motorpool_enabled = False
    container: Any = SimpleNamespace(settings=settings)
    page = PluginsPage(container)
    row = page.rows[0]
    notices: list[str] = []
    changed: list[bool] = []
    page.changed.connect(lambda: changed.append(True))

    def decline(*args: Any) -> Any:
        notices.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    row.checkbox.setChecked(True)
    assert notices and not changed
    assert not row.checkbox.isChecked() and not row.gear.isEnabled()
    assert vars(settings)["motorpool_enabled"] is False
    assert not movement.requested(settings)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    row.checkbox.setChecked(True)
    assert changed == [True]
    assert row.checkbox.isChecked() and row.gear.isEnabled()
    assert movement.enabled(settings)
    assert vars(settings)["motorpool_enabled"] is True
    options = PluginOptionsBox(plugin)
    budget = options.widgets["groundmovement.roadMilesPerTurn"]
    assert isinstance(budget, QSpinBox) and budget.value() == 120
    options.resize(700, 220)
    options.show()
    app.processEvents()
    assert options.grab().save(str(tmp_path / "ground-movement-options.png"))
    options.close()
    row.checkbox.setChecked(False)
    assert vars(settings)["motorpool_enabled"] is True
    assert not movement.requested(settings)
    assert not row.gear.isEnabled()
    page.close()


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
