"""Where the join point goes.

It used to sit on a ring at 35% of the straight line from home to the target, which
is off the route whenever the route is not straight, and a long way short of the
ingress whenever a stand-off weapon pushed the ingress out. The flight left its track
to reach the join and turned back onto it afterwards.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point
from shapely.geometry import MultiPolygon

from game.flightplan.joinzonegeometry import MIN_JOIN_FRACTION, JoinZoneGeometry
from game.utils import Heading, meters, nautical_miles

JOIN_DISTANCE = nautical_miles(20)


def _coalition() -> Any:
    return SimpleNamespace(
        doctrine=SimpleNamespace(join_distance=JOIN_DISTANCE),
        opponent=SimpleNamespace(threat_zone=SimpleNamespace(all=MultiPolygon([]))),
    )


def _at(east_nm: float) -> Point:
    """A point that far east of the origin, in a straight line."""
    return Point(0, nautical_miles(east_nm).meters, cast(Any, None))


def _join(target_nm: float, ingress_nm: float) -> Point:
    """The join for a target that far out, with the ingress that far from home."""
    home = _at(0)
    target = _at(target_nm)
    ingress = _at(ingress_nm)
    return JoinZoneGeometry(target, home, ingress, _coalition()).find_best_join_point()


def _from_home(point: Point) -> float:
    return meters(point.distance_to_point(_at(0))).nautical_miles


def _behind(join: Point, ingress_nm: float) -> float:
    """How far the join is from the ingress."""
    return meters(join.distance_to_point(_at(ingress_nm))).nautical_miles


def test_it_sits_just_behind_a_distant_ingress() -> None:
    """A 150 nm stand-off weapon puts the ingress 250 nm out; the join belongs there
    and not 110 nm short of it."""
    join = _join(target_nm=400, ingress_nm=250)

    assert _behind(join, 250) == pytest.approx(JOIN_DISTANCE.nautical_miles, abs=1)


def test_it_does_not_add_a_detour_to_reach_it() -> None:
    join = _join(target_nm=400, ingress_nm=250)

    detour = _from_home(join) + _behind(join, 250) - 250
    assert detour < 5


def test_an_ordinary_ingress_is_also_joined_just_before() -> None:
    """Not only the stand-off case: 45 nm from a 400 nm target is 355 nm out."""
    join = _join(target_nm=400, ingress_nm=355)

    assert _behind(join, 355) == pytest.approx(JOIN_DISTANCE.nautical_miles, abs=1)


def test_a_close_ingress_falls_back_to_a_fraction_of_the_leg() -> None:
    """There is no room to form up behind an ingress five miles from the airfield, so
    the join goes back to where it always was."""
    join = _join(target_nm=80, ingress_nm=5)

    assert 80 * 0.35 - 1 <= _from_home(join) <= 80 * 0.36 + 1


def test_the_fallback_starts_where_the_ring_would_reach_home() -> None:
    target_nm = 400.0
    floor = target_nm * MIN_JOIN_FRACTION + 2 * JOIN_DISTANCE.nautical_miles

    just_short = _join(target_nm=target_nm, ingress_nm=floor - 5)
    just_over = _join(target_nm=target_nm, ingress_nm=floor + 5)

    assert target_nm * 0.35 - 1 <= _from_home(just_short) <= target_nm * 0.36 + 1
    assert _behind(just_over, floor + 5) == pytest.approx(
        JOIN_DISTANCE.nautical_miles, abs=1
    )


def test_it_is_never_inside_the_ingress_bubble() -> None:
    """The doctrine's join distance is a minimum, not a target."""
    for ingress_nm in (150, 200, 250, 355):
        join = _join(target_nm=400, ingress_nm=ingress_nm)
        assert _behind(join, ingress_nm) >= JOIN_DISTANCE.nautical_miles - 0.5


def test_it_stays_between_home_and_the_target() -> None:
    join = _join(target_nm=400, ingress_nm=250)

    assert 0 < _from_home(join) < 400
