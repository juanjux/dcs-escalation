from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from game.commander.objectivefinder import ObjectiveFinder
from game.theater.player import Player


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("transport_type", ["convoys", "cargo_ships"])
def test_interdiction_uses_hostile_transports_at_the_front(
    side: Player, transport_type: str
) -> None:
    own_transport = SimpleNamespace(is_friendly=lambda player: player == side)
    hostile_transport = SimpleNamespace(is_friendly=lambda player: player != side)
    destination = object()
    own_map = Mock()
    own_map.travelling_to.return_value = [own_transport]
    hostile_map = Mock()
    hostile_map.travelling_to.return_value = [hostile_transport, own_transport]
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(perf_disable_convoys=False),
        theater=SimpleNamespace(
            conflicts=lambda: [
                SimpleNamespace(control_point_hostile_to=lambda _: destination)
            ]
        ),
        coalition_for={
            side: SimpleNamespace(
                transfers=SimpleNamespace(**{transport_type: own_map})
            ),
            side.opponent: SimpleNamespace(
                transfers=SimpleNamespace(**{transport_type: hostile_map})
            ),
        }.__getitem__,
    )
    finder = ObjectiveFinder(game, side)

    assert list(getattr(finder, transport_type)()) == [hostile_transport]
    hostile_map.travelling_to.assert_called_once_with(destination)
    own_map.travelling_to.assert_not_called()
