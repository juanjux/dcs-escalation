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


def test_cover_combo_preserves_saved_ids_and_refresh_does_not_write(
    qt_app: Any,
) -> None:
    from PySide6.QtWidgets import QComboBox

    from game.settings import Settings
    from qt_ui.windows.settings.plugins import PluginOptionsBox

    plugin = LuaPlugin.from_json(
        "realisticcas", ROOT / "resources/plugins/realisticcas/plugin.json"
    )
    assert plugin is not None
    plugin.set_settings(Settings())
    option = next(
        o for o in plugin.options if o.identifier == "realisticcas.terrainProfile"
    )
    option.set_value(4)  # Existing campaign's numeric value, before creating UI.
    box = PluginOptionsBox(plugin)
    try:
        widget = box.widgets[option.identifier]
        assert isinstance(widget, QComboBox)
        assert widget.currentText() == "Forest"
        assert widget.currentData() == 4
        assert [widget.itemData(i) for i in range(widget.count())] == list(range(6))
        widget.setCurrentIndex(widget.findData(1))
        assert option.get_value == 1 and type(option.get_value) is int
        option.set_value(5)
        box.update_from_settings(option.settings)
        assert widget.currentText() == "City" and option.get_value == 5
        option.set_value(99)  # Invalid old value must not silently become desert.
        box.update_from_settings(option.settings)
        assert widget.currentIndex() == -1 and option.get_value == 99
    finally:
        box.close()


@pytest.mark.parametrize(
    ("mnemonic", "default_metres", "default_feet"),
    [("visualMaxAGL", 3500, 11483), ("opticalMaxAGL", 7010.4, 23000)],
)
def test_height_controls_use_feet_but_preserve_metres(
    qt_app: Any, mnemonic: str, default_metres: float, default_feet: int
) -> None:
    from PySide6.QtWidgets import QDoubleSpinBox

    from game.settings import Settings
    from qt_ui.windows.settings.plugins import PluginOptionsBox

    plugin = LuaPlugin.from_json(
        "realisticcas", ROOT / "resources/plugins/realisticcas/plugin.json"
    )
    assert plugin is not None
    plugin.set_settings(Settings())
    option = next(
        o for o in plugin.options if o.identifier == f"realisticcas.{mnemonic}"
    )
    box = PluginOptionsBox(plugin)
    try:
        widget = box.widgets[option.identifier]
        assert isinstance(widget, QDoubleSpinBox)
        assert widget.suffix() == " ft"
        assert widget.value() == default_feet
        assert option.get_value == default_metres
        option.set_value(6500)
        box.update_from_settings(option.settings)
        assert widget.value() == 21325
        assert option.get_value == 6500  # No rounding on refresh.
        widget.setValue(23000)
        assert option.get_value == pytest.approx(7010.4)
        for bound in (widget.minimum(), widget.maximum()):
            widget.setValue(bound)
            assert option.min <= option.get_value <= option.max
    finally:
        box.close()
    # Loading an old integer-valued save also uses the feet control.
    option.set_value(6500)
    reopened = PluginOptionsBox(plugin)
    try:
        assert option.get_value == 6500
        control = reopened.widgets[option.identifier]
        assert isinstance(control, QDoubleSpinBox)
        assert control.value() == 21325
    finally:
        reopened.close()


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
