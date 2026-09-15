"""Plugin option help survives JSON loading and reaches labels and controls."""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any

import pytest

from game.plugins.luaplugin import LuaPlugin

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize("value", [True, 20, 0.5, "text"])
@pytest.mark.parametrize("help_text", ["Range < 5 & height > 2.", ""])
def test_option_help_and_editing(
    qt_app: Any, tmp_path: Path, value: Any, help_text: str
) -> None:
    from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLineEdit, QSpinBox

    from qt_ui.windows.settings.plugins import PluginOptionsBox

    option = {"mnemonic": "value", "nameInUI": "Value", "defaultValue": value}
    if help_text:
        option["descriptionInUI"] = help_text
    manifest = tmp_path / "plugin.json"
    manifest.write_text(
        json.dumps(
            {
                "nameInUI": "Test",
                "descriptionInUI": "Plugin description, not option help.",
                "specificOptions": [option],
                "scriptsWorkOrders": [],
                "configurationWorkOrders": [],
            }
        )
    )
    plugin = LuaPlugin.from_json("testhelp", manifest)
    assert plugin is not None
    assert plugin.options[0].description == help_text
    box = PluginOptionsBox(plugin)
    try:
        widget = box.widgets["testhelp.value"]
        expected = f"<qt>{escape(help_text)}</qt>" if help_text else ""
        assert box.labels["testhelp.value"].toolTip() == expected
        assert widget.toolTip() == expected
        if isinstance(widget, QCheckBox):
            widget.setChecked(False)
            assert plugin.options[0].get_value is False
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setValue(2)
            assert plugin.options[0].get_value == 2
        elif isinstance(widget, QLineEdit):
            widget.setText("edited")
            assert plugin.options[0].get_value == "edited"
        else:
            pytest.fail("Missing option control")
    finally:
        box.close()


def test_all_realistic_cas_options_have_help(qt_app: Any) -> None:
    from qt_ui.windows.settings.plugins import PluginOptionsBox

    plugin = LuaPlugin.from_json(
        "realisticcas", ROOT / "resources/plugins/realisticcas/plugin.json"
    )
    assert plugin is not None
    box = PluginOptionsBox(plugin, with_description=False)
    try:
        for option in plugin.options:
            assert option.description.strip(), option.identifier
            expected = f"<qt>{escape(option.description)}</qt>"
            assert box.labels[option.identifier].toolTip() == expected
            assert box.widgets[option.identifier].toolTip() == expected
        terrain = next(
            o for o in plugin.options if o.identifier == "realisticcas.terrainProfile"
        )
        assert terrain.get_value == 0
        assert "ONE" in terrain.description
        assert "Nevada" in terrain.description
    finally:
        box.close()
