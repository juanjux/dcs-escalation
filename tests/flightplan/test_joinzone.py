"""Where the join point goes when the route cannot be used to place it.

This is the fallback for ``join_along_route``: a ring at 35% of the straight line from
home to the target, and a ring behind the ingress when nothing in the first is usable.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point
from shapely.geometry import MultiPolygon, Point as ShapelyPoint

from game.flightplan.joinzonegeometry import JoinZoneGeometry
from game.utils import meters, nautical_miles

JOIN_DISTANCE = nautical_miles(20)


def _coalition(threat: Any = None) -> Any:
    return SimpleNamespace(
        doctrine=SimpleNamespace(join_distance=JOIN_DISTANCE),
        opponent=SimpleNamespace(
            threat_zone=SimpleNamespace(all=threat or MultiPolygon([]))
        ),
    )


def _at(east_nm: float) -> Point:
    """A point that far east of the origin, in a straight line."""
    return Point(0, nautical_miles(east_nm).meters, cast(Any, None))


def _join(target_nm: float, ingress_nm: float, threat: Any = None) -> Point:
    home, target, ingress = _at(0), _at(target_nm), _at(ingress_nm)
    return JoinZoneGeometry(
        target, home, ingress, cast(Any, _coalition(threat))
    ).find_best_join_point()


def _from_home(point: Point) -> float:
    return meters(point.distance_to_point(_at(0))).nautical_miles


def _behind(join: Point, ingress_nm: float) -> float:
    return meters(join.distance_to_point(_at(ingress_nm))).nautical_miles


def test_it_goes_a_third_of_the_way_to_the_target() -> None:
    """Early enough that whatever forms up there is with the package for most of the
    trip."""
    join = _join(target_nm=400, ingress_nm=355)

    assert 400 * 0.35 - 1 <= _from_home(join) <= 400 * 0.36 + 1


def test_the_same_holds_for_a_stand_off_ingress() -> None:
    join = _join(target_nm=400, ingress_nm=250)

    assert 400 * 0.35 - 1 <= _from_home(join) <= 400 * 0.36 + 1


def test_a_threatened_ring_falls_back_to_one_behind_the_ingress() -> None:
    """Otherwise there is nothing to pick and the join lands on the ingress itself."""
    # Deep enough that the ring at 35% is inside it and its edge is well beyond.
    home = _at(0)
    threat = MultiPolygon(
        [ShapelyPoint(home.x, home.y).buffer(nautical_miles(200).meters)]
    )

    join = _join(target_nm=400, ingress_nm=250, threat=threat)

    assert _behind(join, 250) == pytest.approx(JOIN_DISTANCE.nautical_miles, abs=2)


def test_it_stays_between_home_and_the_target() -> None:
    join = _join(target_nm=400, ingress_nm=250)

    assert 0 < _from_home(join) < 400
