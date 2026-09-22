"""The join goes on the route the flight will actually fly.

A fixed fraction of the straight line home is off the route whenever the route is not
straight, so the flight left its track to reach the join and turned back. A fraction
of the route itself costs nothing to reach, and is still early enough that whatever
forms up there -- an escort above all -- is with the package for most of the trip.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point

from game.ato.packagewaypoints import JOIN_FRACTION, join_along_route
from game.utils import meters, nautical_miles

JOIN_DISTANCE = nautical_miles(20)


def _at(north_nm: float, east_nm: float) -> Point:
    return Point(
        nautical_miles(north_nm).meters,
        nautical_miles(east_nm).meters,
        cast(Any, None),
    )


def _coalition(path: list[Point]) -> Any:
    return SimpleNamespace(
        doctrine=SimpleNamespace(join_distance=JOIN_DISTANCE),
        nav_mesh=SimpleNamespace(shortest_path=lambda a, b: path),
    )


def _nm(a: Point, b: Point) -> float:
    return meters(a.distance_to_point(b)).nautical_miles


def test_it_goes_a_third_of_the_way_along_a_straight_route() -> None:
    home, ingress = _at(0, 0), _at(0, 300)
    coalition = _coalition([home, ingress])

    join = join_along_route(coalition, home, ingress)

    assert join is not None
    assert _nm(home, join) == pytest.approx(300 * JOIN_FRACTION, abs=1)


def test_it_lands_on_a_route_that_turns() -> None:
    """The point is on one of the legs, not off in the middle of the dogleg."""
    home, corner, ingress = _at(0, 0), _at(0, 200), _at(200, 200)
    coalition = _coalition([home, corner, ingress])

    join = join_along_route(coalition, home, ingress)

    assert join is not None
    # 35.5% of a 400 nm route is 142 nm, which is still on the first leg.
    assert join.x == pytest.approx(0, abs=100)
    assert _nm(home, join) == pytest.approx(400 * JOIN_FRACTION, abs=1)


def test_it_lands_on_the_second_leg_when_the_first_is_short() -> None:
    home, corner, ingress = _at(0, 0), _at(0, 50), _at(300, 50)
    coalition = _coalition([home, corner, ingress])

    join = join_along_route(coalition, home, ingress)

    assert join is not None
    walked = _nm(home, corner) + _nm(corner, join)
    assert walked == pytest.approx(350 * JOIN_FRACTION, abs=1)


def test_it_never_lands_on_the_ingress() -> None:
    """A short route would otherwise put the join right on top of it."""
    home, ingress = _at(0, 0), _at(0, 25)
    coalition = _coalition([home, ingress])

    join = join_along_route(coalition, home, ingress)

    assert join is not None
    assert _nm(join, ingress) >= JOIN_DISTANCE.nautical_miles - 0.1


def test_a_route_the_navmesh_cannot_find_is_left_to_the_zone_geometry() -> None:
    def refuse(a: Any, b: Any) -> Any:
        raise RuntimeError("outside the navmesh")

    coalition = SimpleNamespace(
        doctrine=SimpleNamespace(join_distance=JOIN_DISTANCE),
        nav_mesh=SimpleNamespace(shortest_path=refuse),
    )

    assert join_along_route(cast(Any, coalition), _at(0, 0), _at(0, 300)) is None


def test_a_route_of_one_point_is_left_to_the_zone_geometry() -> None:
    home = _at(0, 0)

    assert join_along_route(_coalition([home]), home, home) is None
