"""Disconnected roads must not prevent valid off-road detours."""

from pathlib import Path

import pytest
from dcs.mapping import LatLng, Point
from dcs.terrain import Afghanistan
from shapely.geometry import MultiPolygon, box

from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment
from game.groundmovement.orders import GroundPosition as P
from game.groundmovement.routing import CampaignGroundRouter, GroundRouteError
from game.theater.landmap import Landmap, load_landmap


def router(*obstacles: object) -> CampaignGroundRouter:
    return CampaignGroundRouter(
        Landmap(
            MultiPolygon([box(-100, -100, 200, 100)]),
            MultiPolygon(obstacles),
            MultiPolygon(),
        ),
        [],
    )


def test_detour_around_exclusion_uses_offroad_budget() -> None:
    planner = router(box(40, -10, 60, 10))
    route = planner.plan(P(0, 0), P(100, 0), 200, 100)
    assert len(route.segments) > 1
    assert all(not s.on_road and planner.allowed(s) for s in route.segments)
    assert route.length > 100
    journey = GroundJourney(route)
    journey.advance(1, 200, 100)
    assert not journey.completed
    assert journey.travelled_distance == pytest.approx(100)
    journey.advance(2, 200, 100)
    assert journey.completed


def test_disconnected_roads_allow_clear_direct_offroad_travel() -> None:
    planner = router(box(40, -5, 60, 5))
    roads = [
        GroundRoute.from_points([P(0, 0), P(30, 0)]),
        GroundRoute.from_points([P(70, 0), P(100, 0)]),
    ]
    planner = CampaignGroundRouter(planner.landmap, roads, convoy_corridors=True)
    assert planner.plan(P(0, 10), P(100, 10), 200, 100).segments == (
        GroundSegment(P(0, 10), P(100, 10), False),
    )


def test_no_detour_across_disconnected_land() -> None:
    planner = router(box(40, -100, 60, 100))
    with pytest.raises(GroundRouteError):
        planner.plan(P(0, 0), P(100, 0), 200, 100)


def test_search_widens_to_find_a_longer_detour() -> None:
    land = Landmap(
        MultiPolygon([box(-200000, -200000, 200000, 200000)]),
        MultiPolygon([box(40000, -60000, 60000, 60000)]),
        MultiPolygon(),
    )
    planner = CampaignGroundRouter(land, [])
    route = planner.plan(P(0, 0), P(100000, 0), 200000, 100000)
    assert any(abs(s.end.z) > 60000 for s in route.segments)
    assert all(planner.allowed(s) for s in route.segments)


def test_detour_can_choose_other_side_when_permission_blocks_one_side() -> None:
    planner = router(box(40, -10, 60, 10))
    planner.offroad_permission = lambda s: s.start.z >= 0 and s.end.z >= 0
    route = planner.plan(P(0, 0), P(100, 0), 200, 100)
    assert all(s.start.z >= 0 and s.end.z >= 0 for s in route.segments)


@pytest.mark.parametrize("origin", [(32.44069, 65.61963), (32.62, 65.88)])
def test_afghanistan_groups_can_detour_to_southern_front(
    origin: tuple[float, float],
) -> None:
    terrain = Afghanistan()
    land = load_landmap(Path("resources/theaters/afghanistan/landmap.p"))
    assert land is not None
    planner = CampaignGroundRouter(land, [])

    def position(lat: float, lng: float) -> P:
        point = Point.from_latlng(LatLng(lat, lng), terrain)
        return P(point.x, point.y)

    start, end = position(*origin), position(32.13002, 66.91016)
    assert not planner.allowed(GroundSegment(start, end, False))
    route = planner.plan(start, end, 193121.28, 96560.64)
    assert route.segments[0].start == start
    assert route.segments[-1].end == end
    assert all(not s.on_road and planner.allowed(s) for s in route.segments)
