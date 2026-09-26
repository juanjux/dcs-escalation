"""Plugin consumers tolerate missing settings and use the active campaign."""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from game.plugins import LuaPlugin, LuaPluginManager
from game.plugins.luaplugin import PluginSettings
from game.settings import Settings
from game.missiongenerator.realisticcascampaign import validate_compatibility


@pytest.fixture
def plugins(monkeypatch: pytest.MonkeyPatch) -> dict[str, LuaPlugin]:
    result = {}
    for name in ("ctld", "realisticcas"):
        plugin = LuaPlugin.from_json(
            name, Path("resources/plugins") / name / "plugin.json"
        )
        assert plugin is not None
        result[name] = plugin
    monkeypatch.setattr(LuaPluginManager, "_plugins", result)
    monkeypatch.setattr(LuaPluginManager, "_plugins_loaded", True)
    return result


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("name", ["ctld", "realisticcas"])
def test_missing_plugin_and_option_values_use_manifest_defaults(
    plugins: dict[str, LuaPlugin], name: str
) -> None:
    plugin = plugins[name]
    settings = Settings()
    plugin.set_settings(settings)
    settings.plugins.clear()
    assert plugin.enabled == plugin.definition.enabled_by_default
    for option in plugin.options:
        assert option.get_value == option.value
        assert settings.plugin_option(option.identifier) == option.value


@pytest.mark.parametrize("value", [False, 0, "", None])
def test_existing_plugin_values_are_not_replaced(value: Any) -> None:
    option = PluginSettings("test.value", 42)
    option.set_value(value)
    assert option.get_value == value


def test_missing_realistic_cas_setting_does_not_break_preflight(
    plugins: dict[str, LuaPlugin],
) -> None:
    settings = Settings()
    LuaPluginManager.load_settings(settings)
    settings.plugins.clear()
    validate_compatibility(LuaPluginManager.plugins())
    assert not plugins["realisticcas"].enabled


def test_plugin_page_uses_its_settings_and_initializes_missing_options(
    app: Any,
    plugins: dict[str, LuaPlugin],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtGui import QIcon
    from qt_ui import uiconstants
    from qt_ui.windows.settings.plugins import PluginsPage, PluginOptionsBox

    monkeypatch.setitem(uiconstants.ICONS, "Settings", QIcon())
    stale = Settings()
    LuaPluginManager.load_settings(stale)
    stale.plugins.clear()
    active = Settings()
    active.set_plugin_option("ctld", False)
    active.set_plugin_option("realisticcas", True)
    active.set_plugin_option("realisticcas.acquisitionSeconds", 37)
    container: Any = SimpleNamespace(settings=active)
    page = PluginsPage(container)
    assert plugins["ctld"].settings is active
    assert not page.rows[0].checkbox.isChecked()
    assert page.rows[1].checkbox.isChecked()
    box = PluginOptionsBox(plugins["realisticcas"])
    assert active.plugin_option("realisticcas.acquisitionSeconds") == 37
    assert stale.plugins == {}
    box.close()
    active.plugins = {"ctld": True}
    LuaPluginManager.load_settings(stale)
    stale.set_plugin_option("ctld", False)
    page.update_from_settings()
    assert page.rows[0].checkbox.isChecked()
    assert not page.rows[1].checkbox.isChecked()
    assert plugins["ctld"].settings is active
    assert stale.plugin_option("ctld") is False
    page.close()


def test_takeoff_binds_plugins_before_compatibility_check(
    app: Any,
    plugins: dict[str, LuaPlugin],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib
    from game.agent.session import AI_SESSION

    top = importlib.import_module("qt_ui.widgets.QTopPanel")
    monkeypatch.setattr(type(AI_SESSION), "active", property(lambda _: False))
    stale, active = Settings(), Settings()
    LuaPluginManager.load_settings(stale)
    active.set_plugin_option("realisticcas", True)
    messages: list[str] = []
    monkeypatch.setattr(
        top.QMessageBox, "warning", lambda _self, _title, text: messages.append(text)
    )

    def check(items: Any) -> None:
        assert all(plugin.settings is active for plugin in items)
        assert plugins["realisticcas"].enabled
        raise top.RealisticCASConfigurationError("Test preflight stop")

    monkeypatch.setattr(top, "validate_compatibility", check)
    panel: Any = SimpleNamespace(game=SimpleNamespace(settings=active))
    top.QTopPanel.launch_mission(panel)
    assert messages == ["Test preflight stop"]
