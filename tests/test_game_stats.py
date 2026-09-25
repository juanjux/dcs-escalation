"""The statistics keep one entry per turn."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.models.game_stats import GameStats


def test_updating_a_turn_again_replaces_its_entry() -> None:
    stats = GameStats()
    game: Any = SimpleNamespace(turn=0, theater=SimpleNamespace(controlpoints=[]))

    stats.update(game)
    stats.update(game)
    assert len(stats.data_per_turn) == 1

    game.turn = 1
    stats.update(game)
    stats.update(game)
    assert len(stats.data_per_turn) == 2
