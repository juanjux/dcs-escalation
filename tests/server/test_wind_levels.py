"""The map is told the turn's wind at the three levels DCS models."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.weather import Wind

from game.server.game.models import WindLevelJs
from game.weather.wind import WindConditions


def test_the_three_levels_as_dcs_keeps_them() -> None:
    wind = WindConditions(Wind(308, 11.7), Wind(337, 22.2), Wind(9, 39.1))
    game: Any = SimpleNamespace(
        conditions=SimpleNamespace(weather=SimpleNamespace(wind=wind))
    )

    levels = WindLevelJs.for_game(game)

    assert [(w.altitude_m, w.blows_to, w.speed_mps) for w in levels] == [
        (0, 308, 11.7),
        (2000, 337, 22.2),
        (8000, 9, 39.1),
    ]
