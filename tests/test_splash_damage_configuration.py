"""Verify plugin defaults and saved options at the Lua configuration boundary."""

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings

PLUGIN_DIR = Path("resources/plugins/splashdamage3")
METADATA = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
OPTIONS = METADATA["specificOptions"]
ALIASES = {"cluster_bomblet_reduction_modifier": "cluster_bomblet_reductionmodifier"}


def configured_script(overrides: dict[str, Any] | None = None) -> tuple[Any, Any]:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    script = (PLUGIN_DIR / METADATA["scriptsWorkOrders"][0]["file"]).read_text(
        encoding="utf-8"
    )
    # Execute the real defaults table without starting DCS event handlers.
    defaults = re.search(r"splash_damage_options = \{.*?^\}", script, re.M | re.S)
    assert defaults is not None
    lua.execute(defaults.group())
    native = dict(lua.globals().splash_damage_options.items())
    lua.execute("env={info=function() end}; dcsRetribution={}")
    plugin = LuaPlugin.from_json("splashdamage3", PLUGIN_DIR / "plugin.json")
    assert plugin is not None
    settings = Settings()
    settings.plugins.update(
        {f"splashdamage3.{key}": value for key, value in (overrides or {}).items()}
    )
    plugin.set_settings(settings)
    generator = Mock()
    plugin.inject_configuration(generator)
    preamble = generator.inject_lua_trigger.call_args.args[0]
    lua.execute(preamble)
    for work_order in METADATA["configurationWorkOrders"]:
        lua.execute((PLUGIN_DIR / work_order["file"]).read_text(encoding="utf-8"))
    return native, lua.globals().splash_damage_options


@pytest.mark.parametrize("option", OPTIONS, ids=lambda option: option["mnemonic"])
def test_effective_defaults_match_script_except_ground_snapping(
    option: dict[str, Any],
) -> None:
    native, configured = configured_script()
    name = ALIASES.get(option["mnemonic"], option["mnemonic"])
    expected = native[name]
    if name == "snap_to_ground_if_destroyed_by_large_explosion":
        assert expected is True
        expected = False
    assert configured[name] == expected


@pytest.mark.parametrize("option", OPTIONS, ids=lambda option: option["mnemonic"])
def test_numeric_defaults_are_selectable(option: dict[str, Any]) -> None:
    value = option["defaultValue"]
    if type(value) in (int, float):
        assert (
            option.get("minimumValue", 0) <= value <= option.get("maximumValue", 10000)
        )


def test_saved_overrides_keep_their_units() -> None:
    _, configured = configured_script(
        {
            "overall_scaling": 3,
            "rocket_multiplier": 250,
            "dynamic_blast_radius_modifier": 150,
            "ordnance_protection_radius": 800,
            "snap_to_ground_if_destroyed_by_large_explosion": True,
            "wave_explosions": False,
        }
    )
    assert configured.overall_scaling == 0.03
    assert configured.rocket_multiplier == 2.5
    assert configured.dynamic_blast_radius_modifier == 1.5
    assert configured.ordnance_protection_radius == 800
    assert configured.snap_to_ground_if_destroyed_by_large_explosion is True
    assert configured.wave_explosions is False


def test_larger_user_multiplier_is_selectable() -> None:
    overall = next(o for o in OPTIONS if o["mnemonic"] == "overall_scaling")
    assert overall["maximumValue"] >= 200
    _, configured = configured_script({"overall_scaling": 200})
    assert configured.overall_scaling == 2
