"""Which base or site a log entry is about.

The log has no field for it: every entry is a sentence built where it happened. What the
sentences do have is the place's name, and bases and sites have names nothing else in
the log uses.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from game import Game
    from game.infos.information import Information
    from game.theater import MissionTarget


def place_named_in(game: Game, info: Information) -> Optional[MissionTarget]:
    """The base or site the entry names; the longest name when it names several, so a
    site is not taken for the base inside its own name."""
    text = f"{info.title} {info.text}"
    places: dict[str, MissionTarget] = {}
    for cp in game.theater.controlpoints:
        places.setdefault(cp.name, cp)
    for tgo in game.theater.ground_objects:
        places.setdefault(tgo.name, tgo)
    for name in sorted(places, key=len, reverse=True):
        if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text):
            return places[name]
    return None
