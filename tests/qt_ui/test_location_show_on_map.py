"""A site's window moves the map to it, and leaves the zoom where it was."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_show_on_map_moves_the_map_without_zooming(monkeypatch: Any) -> None:
    from game.server import EventStream
    from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu

    sent: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    window: Any = SimpleNamespace(
        ground_object=SimpleNamespace(position=SimpleNamespace(latlng=lambda: "here"))
    )

    QGroundObjectMenu._show_on_map(window)

    assert [(events.fly_to, events.fly_to_zoom) for events in sent] == [("here", None)]
