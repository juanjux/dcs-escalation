"""Existing campaigns retain Combined Arms slots and CTLD settings."""

from types import SimpleNamespace as NS
from typing import Any

from game.game import Game
from game.lasercodes.lasercoderegistry import LaserCodeRegistry
from game.settings import Settings


def test_retired_jtac_settings_are_ignored_in_old_saves() -> None:
    saved = {
        "use_jtac": True,
        "jtac_count": 2,
        "plugins": {
            "MooseAutolase": True,
            "MooseAutolase.JtacAlphaSmoke": True,
            "ctld.autolase": False,
            "ctld.jtacsmoke": True,
            "ctld.fc3LaserCode": True,
        },
    }
    settings = object.__new__(Settings)
    settings.__setstate__(saved)

    assert "use_jtac" not in vars(settings)
    assert settings.jtac_count == 2
    assert settings.plugin_option("ctld.autolase") is False
    assert "ctld.jtacsmoke" not in settings.plugins
    assert "ctld.fc3LaserCode" not in settings.plugins
    assert not any(key.startswith("MooseAutolase") for key in settings.plugins)


def test_old_frontline_laser_code_is_released_without_releasing_player_code() -> None:
    registry = LaserCodeRegistry()
    retired = registry.alloc_laser_code()
    player_code = registry.alloc_laser_code()
    front = NS(laser_code=retired)
    buddy_lase = NS(weapon_laser_code=retired, tgp_laser_code=player_code)
    own_lase = NS(weapon_laser_code=player_code, tgp_laser_code=player_code)
    flight = NS(iter_members=lambda: [buddy_lase, own_lase])
    game: Any = NS(
        theater=NS(conflicts=lambda: [front]),
        blue=NS(ato=NS(packages=[NS(flights=[flight])])),
        red=NS(ato=NS(packages=[])),
        laser_code_registry=registry,
    )

    Game._retire_frontline_laser_codes(game)
    Game._retire_frontline_laser_codes(game)

    assert not hasattr(front, "laser_code")
    assert buddy_lase.weapon_laser_code is None
    assert buddy_lase.tgp_laser_code == own_lase.weapon_laser_code == player_code
    assert registry.allocated_codes == {player_code.code}
    assert registry.alloc_laser_code() == retired
