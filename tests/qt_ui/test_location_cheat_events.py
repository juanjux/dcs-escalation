"""The location cheat sends the map what killing or reviving the units changed."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_the_cheat_publishes_the_events_its_units_changed(monkeypatch: Any) -> None:
    from qt_ui.windows.groundobject import QGroundObjectMenu as menu

    given: list[Any] = []
    published: list[Any] = []
    monkeypatch.setattr(menu, "destroy_all", lambda site, events: given.append(events))
    monkeypatch.setattr(menu, "revive_all", lambda site, events: given.append(events))
    window: Any = SimpleNamespace(ground_object="site", _update_game=published.append)

    menu.QGroundObjectMenu._cheat_destroy_all(window)
    menu.QGroundObjectMenu._cheat_revive_all(window)

    assert len(given) == 2
    assert all(sent is made for sent, made in zip(published, given))
