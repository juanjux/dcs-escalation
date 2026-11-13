from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from dcs import Point
from dcs.terrain import Caucasus

from game.ato.flightplans.dead import Builder as DeadBuilder
from game.ato.flightplans.strike import Builder as StrikeBuilder
from game.data.doctrine import MODERN_DOCTRINE
from game.utils import nautical_miles

TERRAIN = Caucasus()


def point(north: float, east: float = 0) -> Point:
    return Point(nautical_miles(north).meters, nautical_miles(east).meters, TERRAIN)


@pytest.mark.parametrize("builder_type", [StrikeBuilder, DeadBuilder])
@pytest.mark.parametrize(
    ("first_turn", "threatened", "expected"),
    [
        (point(0, 10), False, point(0, 5)),
        (point(0, 60), False, point(0, 25)),
        (point(0, 1), False, None),
        (point(0, 10), True, None),
    ],
    ids=["on-route", "doctrine-limit", "near-entry", "threatened"],
)
def test_off_map_attack_hold_follows_the_outbound_route(
    builder_type: type[StrikeBuilder] | type[DeadBuilder],
    first_turn: Point,
    threatened: bool,
    expected: Point | None,
) -> None:
    entry, join = point(0), point(10, 10)
    route = Mock(return_value=[entry, first_turn, join])
    flight: Any = SimpleNamespace(
        departure=SimpleNamespace(is_offmap=True, position=entry),
        package=SimpleNamespace(waypoints=SimpleNamespace(join=join)),
        coalition=SimpleNamespace(
            doctrine=MODERN_DOCTRINE,
            game=SimpleNamespace(settings=SimpleNamespace()),
            nav_mesh=SimpleNamespace(shortest_path=route),
            opponent=SimpleNamespace(
                threat_zone=SimpleNamespace(
                    path_threatened=Mock(return_value=threatened)
                )
            ),
        ),
    )
    hold = builder_type(flight)._hold_point(join)
    route.assert_called_once_with(entry, join)
    if expected is None:
        assert hold is None
    else:
        assert hold is not None
        assert hold.distance_to_point(expected) == pytest.approx(0, abs=1e-6)
