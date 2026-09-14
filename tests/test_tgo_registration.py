"""An objective added to a campaign already under way is still clickable.

db.tgos is filled once, at turn 0. Anything added later -- a motorpool the migrator
creates for a save written before motorpools existed -- was never in it, so asking the
server for it by UUID raised KeyError and the info window never opened.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from game.db.gamedb import GameDb
from game.migrator import Migrator


def _game(*tgos: Any) -> Any:
    db = GameDb()
    cp = SimpleNamespace(connected_objectives=list(tgos))
    return SimpleNamespace(db=db, theater=SimpleNamespace(controlpoints=[cp]))


def _tgo() -> Any:
    return SimpleNamespace(id=uuid4())


def test_an_objective_added_after_turn_zero_is_registered() -> None:
    tgo = _tgo()
    game = _game(tgo)
    Migrator._register_new_tgos(SimpleNamespace(game=game))  # type: ignore[arg-type]

    assert game.db.tgos.get(tgo.id) is tgo


def test_registering_twice_is_not_an_error() -> None:
    """Database.add raises on a duplicate, and the step runs on every load."""
    tgo = _tgo()
    game = _game(tgo)
    migrator = SimpleNamespace(game=game)
    Migrator._register_new_tgos(migrator)  # type: ignore[arg-type]
    Migrator._register_new_tgos(migrator)  # type: ignore[arg-type]

    assert game.db.tgos.get(tgo.id) is tgo
