"""Map categories and location badges follow replacement units, not old slots."""

from typing import Any

import pytest
from dcs import Point

from game.data.groups import GroupTask
from game.server.tgos.models import TgoJs
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import EwrGroundObject, SamGroundObject
from qt_ui.windows.groundobject.common import kind_chip_text
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_missile_targets import populate
from pydcs_extensions.usamilitaryassetspack import (
    CH_THAAD_ANTPY2,
    CH_THAAD_M1120,
)


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("radar_slot", [True, False])
def test_replacements_update_map_category_and_header_without_mutating_save_data(
    world: Any, owner: Player, radar_slot: bool
) -> None:
    w = world
    w.game.settings.set_plugin_option("gpsjamming", False)
    w.a._coalition.player = owner
    w.a._coalition.game = w.game
    location = PresetLocation("SITE", Point(0, 0, w.game.theater.terrain))
    site = (
        EwrGroundObject("SITE", location, w.a)
        if radar_slot
        else SamGroundObject("SITE", location, w.a, GroupTask.LORAD)
    )
    original = (type(site), site.category, site.task)
    populate(w.game, site, CH_THAAD_ANTPY2, 100)
    for unit_type, category, label in [
        (CH_THAAD_M1120, "aa", "SAM"),
        (CH_THAAD_ANTPY2, "ewr", "EWR"),
        (CH_THAAD_M1120, "aa", "SAM"),
    ]:
        site.groups[0].units[0].type = unit_type
        assert TgoJs.for_tgo(site).category == category
        text = kind_chip_text(site, w.a)
        assert text.startswith(label + " · ")
        assert text.endswith(owner.name)
        if category == "aa":
            assert "RADAR" not in text
        else:
            assert "LONG RANGE" not in text
        assert (type(site), site.category, site.task) == original
    site.clear()
    assert TgoJs.for_tgo(site).category == ("ewr" if radar_slot else "aa")
