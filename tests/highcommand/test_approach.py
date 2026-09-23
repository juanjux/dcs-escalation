"""What it costs our aircraft to get a weapon within reach of a point."""

from __future__ import annotations

import math

from dcs import Point
from dcs.terrain import Caucasus

from game.highcommand.approach import Approach, Release, Ring
from game.utils import nautical_miles

TERRAIN = Caucasus()
NM = nautical_miles(1).meters


def _at(x_nm: float, y_nm: float = 0.0) -> Point:
    return Point(x_nm * NM, y_nm * NM, TERRAIN)


def _ring(site: str, x_nm: float, y_nm: float, reach_nm: float) -> Ring:
    return Ring(site=site, x=x_nm * NM, y=y_nm * NM, reach=reach_nm * NM, weight=4.0)


def _distance_nm(point: tuple[float, float], x_nm: float, y_nm: float) -> float:
    return math.hypot(point[0] - x_nm * NM, point[1] - y_nm * NM) / NM


BOMBS = Release(10 * NM)


def test_a_ring_weighs_most_over_its_site_and_nothing_past_its_edge() -> None:
    ring = _ring("GRUMBLE", 0, 0, 40)

    assert ring.weight_at(0, 0) == 4.0
    assert abs(ring.weight_at(20 * NM, 0) - 2.0) < 1e-9
    assert ring.weight_at(41 * NM, 0) == 0


def test_in_the_open_a_route_costs_its_miles() -> None:
    approach = Approach([], [("Batumi", _at(0))], [_at(200)])

    route = approach.route(_at(200), [BOMBS])

    assert route.base == "Batumi"
    assert abs(route.length - 190) < 1e-6
    assert abs(route.cost - 190) < 1e-6
    assert route.rings == ()


def test_a_route_starts_from_the_closest_base() -> None:
    approach = Approach([], [("Batumi", _at(0)), ("Kobuleti", _at(150))], [_at(200)])

    assert approach.route(_at(200), [BOMBS]).base == "Kobuleti"


def test_a_route_goes_round_a_ring_rather_than_through_it() -> None:
    approach = Approach(
        [_ring("GRUMBLE", 100, 0, 30)], [("Batumi", _at(0))], [_at(200)]
    )

    route = approach.route(_at(200), [BOMBS])

    assert min(_distance_nm(point, 100, 0) for point in route.path) > 20
    assert route.length > 190


def test_a_stand_off_weapon_keeps_the_aircraft_out_of_the_ring() -> None:
    standoff = Release(80 * NM, penalty=50)
    approach = Approach(
        [_ring("GRUMBLE", 200, 0, 60)], [("Batumi", _at(0))], [_at(200)]
    )

    route = approach.route(_at(200), [BOMBS, standoff])

    assert route.release == standoff
    assert _distance_nm(route.path[-1], 200, 0) >= 60
    # The weapon still flies over the ring on its way in, and that costs.
    assert [ring.site for _, ring in route.rings] == ["GRUMBLE"]
    assert route.cost > route.length


def test_a_battery_on_the_coast_is_cheaper_than_an_objective_behind_it() -> None:
    standoff = Release(150 * NM, penalty=50)
    coast = _ring("COAST", 200, 0, 100)
    deep = _ring("DEEP", 340, 0, 100)
    approach = Approach([coast, deep], [("Batumi", _at(0))], [_at(200), _at(320)])

    on_the_coast = approach.route(_at(200), [BOMBS, standoff])
    behind_it = approach.route(_at(320), [BOMBS, standoff])

    assert on_the_coast.cost + 100 < behind_it.cost
