"""Regression tests for a standalone UI feature."""

from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any

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
