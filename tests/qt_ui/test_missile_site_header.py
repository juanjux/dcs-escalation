"""Missile sites do not use the fallback reserve armor group heading."""

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from game.theater.player import Player
from qt_ui.windows.groundobject.common import kind_of, kind_chip_text
from qt_ui.windows.groundobject.header import LocationHeader
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_missile_targets import missiles  # noqa: F401


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_missile_site_header_names_its_type(missiles: Any, owner: Player) -> None:
    app = QApplication.instance() or QApplication([])
    w = missiles
    w.a._coalition.player = owner
    w.a._coalition.game = w.game
    expected = f"MISSILE SITE · {owner.name}"
    assert kind_of(w.site) == "MISSILE SITE"
    assert kind_chip_text(w.site, w.a) == expected
    header = LocationHeader(w.site, w.a, None)
    try:
        texts = [label.text() for label in header.findChildren(QLabel)]
        assert expected in texts
        assert not any("RESERVE ARMOR GROUP" in text for text in texts)
        assert kind_of(w.target) == "RESERVE ARMOR GROUP"
        assert kind_of(w.ship) == "NAVAL"
    finally:
        header.close()
        header.deleteLater()
