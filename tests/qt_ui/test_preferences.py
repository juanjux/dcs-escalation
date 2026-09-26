"""Regression tests for a standalone UI feature."""

from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


def test_preferences_are_reachable_under_general(app: Any, monkeypatch: Any) -> None:
    from qt_ui import liberation_install
    from qt_ui import liberation_theme

    liberation_theme.set_theme_index(0)

    for name, value in (
        ("get_dcs_install_directory", ""),
        ("get_saved_game_dir", ""),
        ("prefer_liberation_payloads", False),
        ("setup_preferences_on_every_start", False),
        ("server_port", 16880),
    ):
        monkeypatch.setattr(liberation_install, name, lambda v=value: v)
    from game.settings import Settings
    from qt_ui.windows.settings.QSettingsWindow import AutoSettingsPage
    from qt_ui.windows.preferences.QLiberationPreferences import PreferencesPane

    sc: Any = SimpleNamespace(settings=Settings())
    page = AutoSettingsPage("General", sc, lambda: None)
    assert page.sections is not None
    page.sections.setCurrentRow(page.stack.count() - 1)
    assert isinstance(page.stack.currentWidget(), PreferencesPane)
    page.refresh_page()
    assert isinstance(page.stack.currentWidget(), PreferencesPane)
    page.close()


def test_campaign_settings_do_not_read_application_preferences(
    app: Any, monkeypatch: Any
) -> None:
    from game.settings import Settings
    from qt_ui import liberation_install
    from qt_ui.windows.settings.QSettingsWindow import AutoSettingsPage

    def unexpected_read() -> str:
        raise AssertionError("Application preferences were loaded before selection")

    monkeypatch.setattr(
        liberation_install, "get_dcs_install_directory", unexpected_read
    )
    container: Any = SimpleNamespace(settings=Settings())
    page = AutoSettingsPage("General", container, lambda: None)
    page.refresh_page()
    assert page.preferences_index is not None
    page.close()


def test_application_preferences_save_on_change_without_apply(
    app: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    from PySide6.QtWidgets import QPushButton
    from qt_ui import liberation_install, liberation_theme
    from qt_ui.windows.preferences.QLiberationPreferences import (
        PreferencesPane,
        QMessageBox,
    )

    for name, value in (
        ("get_dcs_install_directory", str(tmp_path)),
        ("get_saved_game_dir", str(tmp_path)),
        ("prefer_liberation_payloads", False),
        ("setup_preferences_on_every_start", False),
        ("server_port", 16880),
    ):
        monkeypatch.setattr(liberation_install, name, lambda v=value: v)
    monkeypatch.setattr(liberation_theme, "__theme_index", 0, raising=False)
    setup, save, theme_save = Mock(), Mock(), Mock()
    monkeypatch.setattr(liberation_install, "setup", setup)
    monkeypatch.setattr(liberation_install, "save_config", save)
    monkeypatch.setattr(liberation_theme, "save_theme_config", theme_save)
    critical = Mock(side_effect=AssertionError("Autosave must not open a modal dialog"))
    monkeypatch.setattr(QMessageBox, "critical", critical)
    monkeypatch.setattr(QMessageBox, "warning", critical)
    pane = PreferencesPane()
    prefs = pane.preferences
    assert not any(
        "Apply" in button.text() for button in pane.findChildren(QPushButton)
    )
    save.assert_not_called()
    for change in (
        lambda: prefs.payloads_cb.setChecked(True),
        lambda: prefs.setup_every_start_cb.setChecked(True),
        lambda: prefs.port_input.setValue(16881),
        lambda: prefs.themeSelect.setCurrentIndex(
            (prefs.themeSelect.currentIndex() + 1) % prefs.themeSelect.count()
        ),
    ):
        previous = save.call_count
        change()
        assert save.call_count == previous + 1
    setup.assert_called_with(str(tmp_path), str(tmp_path), True, True, 16881)
    previous = save.call_count
    prefs.edit_saved_game_dir.setText(str(tmp_path / "missing"))
    assert save.call_count == previous
    assert pane.status.text().startswith("Not saved")
    prefs.edit_saved_game_dir.setText(str(tmp_path))
    assert save.call_count == previous + 1
    prefs.edit_dcs_install_dir.setText(str(tmp_path / "missing"))
    assert save.call_count == previous + 1
    prefs.edit_dcs_install_dir.setText(str(tmp_path))
    assert save.call_count == previous + 2
    assert pane.status.text().startswith("Saved")
    assert theme_save.call_count == save.call_count
    pane.close()
