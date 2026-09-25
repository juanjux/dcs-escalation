"""Double-clicking a log entry moves the map to the base or site it names."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

from game.infos.information import Information
from game.infos.places import place_named_in

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _place(name: str) -> Any:
    return SimpleNamespace(
        name=name, position=SimpleNamespace(latlng=lambda: f"{name} position")
    )


BATUMI, BATUMI_PORT = _place("Batumi"), _place("Batumi Port")
GRUMBLE, OX = _place("GRUMBLE"), _place("OX")

GAME: Any = SimpleNamespace(
    turn=5,
    theater=SimpleNamespace(
        controlpoints=[BATUMI], ground_objects=[GRUMBLE, OX, BATUMI_PORT]
    ),
)


def _named(title: str, text: str = "") -> Any:
    return place_named_in(GAME, Information(title, text, turn=5))


def test_an_entry_names_the_base_or_site_it_is_about() -> None:
    assert _named("OPFOR has finished repairs at GRUMBLE (AA Defense Site)") is GRUMBLE
    assert _named("Batumi lost its source for ground unit reinforcements.") is BATUMI
    assert _named("High Command", "OX: A ticket for a SAM battery.") is OX


def test_the_longest_name_wins_and_names_are_whole_words() -> None:
    assert _named("Repairs at Batumi Port in progress") is BATUMI_PORT
    assert _named("Oxygen shortage") is None


def test_double_clicking_an_entry_moves_the_map_without_zooming(
    monkeypatch: Any,
) -> None:
    from PySide6.QtWidgets import QApplication

    from game.server import EventStream
    from qt_ui.windows.infos.eventlist import EventList

    QApplication.instance() or QApplication([])
    sent: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    game: Any = SimpleNamespace(
        turn=5,
        theater=GAME.theater,
        informations=[
            Information("Mission ended", "", turn=5),
            Information("OPFOR has finished repairs at GRUMBLE", "", turn=5),
        ],
    )
    events = EventList(game)

    events.doubleClicked.emit(events.entries.index(0, 0))
    events.doubleClicked.emit(events.entries.index(1, 0))

    assert [(e.fly_to, e.fly_to_zoom) for e in sent] == [("GRUMBLE position", None)]
