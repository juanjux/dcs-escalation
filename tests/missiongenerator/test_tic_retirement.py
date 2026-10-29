"""Retired TIC options must not change native frontline generation."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from game.ground_forces.ai_ground_planner import CombatGroupRole
from game.ground_forces.combat_stance import CombatStance
from game.missiongenerator.flotgenerator import FlotGenerator
from game.plugins import LuaPluginManager
from game.settings import Settings
from game.utils import Heading


def test_old_campaign_discards_tic_options_without_touching_other_plugins() -> None:
    settings = object.__new__(Settings)
    settings.__setstate__(
        {
            "plugins": {
                "tic": True,
                "tic.boundPause": 7,
                "tic.stormtrooper": True,
                "ticking": True,
                "realisticcas": False,
            },
        }
    )
    assert not any(k == "tic" or k.startswith("tic.") for k in settings.plugins)
    assert settings.plugins["ticking"] is True
    assert settings.plugins["realisticcas"] is False
    LuaPluginManager.load_settings(settings)
    assert "tic" not in {p.identifier for p in LuaPluginManager.plugins()}


@pytest.mark.parametrize(
    ("role", "method"),
    [
        (CombatGroupRole.TANK, "_plan_tank_ifv_action"),
        (CombatGroupRole.IFV, "_plan_tank_ifv_action"),
        (CombatGroupRole.APC, "_plan_apc_atgm_action"),
        (CombatGroupRole.ATGM, "_plan_apc_atgm_action"),
    ],
)
def test_legacy_enabled_setting_cannot_bypass_native_tasking(
    role: CombatGroupRole,
    method: str,
) -> None:
    generator: Any = object.__new__(FlotGenerator)
    generator.game = SimpleNamespace(
        settings=SimpleNamespace(perf_moving_units=True, plugins={"tic": True})
    )
    native = Mock()
    setattr(generator, method, native)
    group = Mock()
    generator.plan_action_for_groups(
        CombatStance.DEFENSIVE,
        [(group, SimpleNamespace(role=role))],
        [],
        Heading.from_degrees(0),
        Mock(),
        Mock(),
    )
    native.assert_called_once()


def test_retired_runtime_is_not_shipped_or_registered() -> None:
    assert not Path("resources/plugins/tic/plugin.json").exists()
    assert not Path("resources/plugins/tic/TIC_v1.1.lua").exists()
    assert not Path("resources/plugins/tic/tic_414_init.lua").exists()
