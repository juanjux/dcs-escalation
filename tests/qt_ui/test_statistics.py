"""Regression tests for a standalone UI feature."""

from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


from game.models.game_stats import GameTurnMetadata
from game.theater import Player
from qt_ui.windows.intel.statistics import StatisticsPane, history


def test_financial_and_pilot_statistics_are_recorded(monkeypatch: Any) -> None:
    from game.models.game_stats import GameStats
    from game import income

    monkeypatch.setattr(
        income,
        "Income",
        lambda game, player: SimpleNamespace(total=12 if player.is_blue else 8),
    )

    def coalition(budget: float) -> Any:
        return SimpleNamespace(
            budget=budget,
            air_wing=SimpleNamespace(
                iter_squadrons=lambda: iter(
                    [
                        SimpleNamespace(
                            current_roster=[
                                SimpleNamespace(alive=True),
                                SimpleNamespace(alive=False),
                            ]
                        )
                    ]
                )
            ),
        )

    game: Any = SimpleNamespace(
        turn=0,
        theater=SimpleNamespace(controlpoints=[]),
        blue=coalition(90),
        red=coalition(70),
    )
    stats = GameStats()
    stats.update(game)
    blue = stats.data_per_turn[0].allied_units
    red = stats.data_per_turn[0].enemy_units
    assert (blue.money, blue.income, blue.pilots, blue.bases) == (90, 12, 1, 0)
    assert (red.money, red.income) == (70, 8)


def test_statistics_preserve_missing_history_and_toggle(app: Any) -> None:
    old, current = GameTurnMetadata(), GameTurnMetadata()
    current.allied_units.money = 123.5
    current.enemy_units.money = 60
    game: Any = SimpleNamespace(
        game_stats=SimpleNamespace(data_per_turn=[old, current])
    )
    assert history(game, Player.BLUE, "money") == [(0, None), (1, 123.5)]
    pane = StatisticsPane(game)
    pane.show_side(Player.RED)
    for check in pane.checks.values():
        check.setChecked(False)
    assert game.intel_statistics_metrics == []
    pane.checks["money"].setChecked(True)
    assert game.intel_statistics_metrics == ["money"]
    pane.close()


def test_empty_statistics_are_supported(app: Any) -> None:
    game: Any = SimpleNamespace(game_stats=SimpleNamespace(data_per_turn=[]))
    pane = StatisticsPane(game)
    pane.compare.setChecked(False)
    pane.close()
