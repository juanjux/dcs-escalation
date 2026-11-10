"""Existing groups may exit a local placement exclusion, not ignore route masks."""

from dataclasses import replace
from pathlib import Path

import pytest
from dcs.mapping import LatLng, Point
from dcs.terrain import Nevada
from shapely.geometry import MultiPolygon, Polygon, box

from game.groundmovement.egress import allowed_origin_exit
from game.groundmovement.journey import GroundJourney, GroundSegment
from game.groundmovement.orders import GroundPosition as P
from game.groundmovement.routing import CampaignGroundRouter, GroundRouteError
from game.theater.landmap import Landmap, load_landmap


def router(*exclusions: object) -> CampaignGroundRouter:
    return CampaignGroundRouter(
        Landmap(
            MultiPolygon([box(-2000, -2000, 2000, 2000)]),
            MultiPolygon(exclusions),
            MultiPolygon(),
        ),
        [],
    )


def test_exit_is_real_offroad_travel_and_tail_detours_normally() -> None:
    planner = router(box(-10, -10, 10, 10), box(40, -20, 60, 20))
    route = planner.plan(P(0, 0), P(100, 0), 100, 50)
    first, *tail = route.segments
    assert first.start == P(0, 0)
    assert first.length == pytest.approx(10.1)
    assert not first.on_road and not planner.allowed(first)
    assert allowed_origin_exit(planner.landmap, first)
    assert tail[-1].end == P(100, 0)
    assert all(not s.on_road and planner.allowed(s) for s in tail)
    assert route.length > 100
    journey = GroundJourney(route)
    journey.advance(1, 100, 5)
    assert journey.segment_index == 0
    assert journey.travelled_distance == pytest.approx(5)
    assert planner.allowed_exit_remainder(
        GroundSegment(journey.position, first.end, False), first
    )


def test_another_exit_is_used_when_nearest_one_has_no_route() -> None:
    # The nearest edge opens into a sealed hole. An outer edge is farther away,
    # but can reach the destination without crossing the exclusion a second time.
    obstacle = Polygon(
        [(-20, -20), (20, -20), (20, 20), (-20, 20)],
        [[(-5, -5), (5, -5), (5, 5), (-5, 5)]],
    )
    planner = router(obstacle)
    route = planner.plan(P(10, 0), P(100, 0), 100, 50)
    assert route.segments[0].end == P(20.1, 0)
    assert all(planner.allowed(s) for s in route.segments[1:])


@pytest.mark.parametrize("origin", [P(0, 0), P(0, 10), P(10, 10)])
def test_origin_on_exclusion_boundary_can_also_exit(origin: P) -> None:
    planner = router(box(-10, -10, 10, 10))
    route = planner.plan(origin, P(100, 0), 100, 50)
    assert route.segments[0].start == origin
    assert allowed_origin_exit(planner.landmap, route.segments[0])
    assert all(planner.allowed(s) for s in route.segments[1:])


def test_excluded_destination_stays_forbidden() -> None:
    planner = router(box(-10, -10, 10, 10), box(90, -10, 110, 10))
    with pytest.raises(GroundRouteError, match="position is in an exclusion"):
        planner.plan(P(0, 0), P(100, 0), 100, 50)


def test_large_exclusion_has_no_local_exit() -> None:
    planner = router(box(-700, -700, 700, 700))
    with pytest.raises(GroundRouteError, match="no safe local exit.*600 m"):
        planner.plan(P(0, 0), P(1000, 0), 100, 50)


def test_exit_permission_cannot_cross_hostile_territory() -> None:
    planner = router(box(-10, -10, 10, 10))
    planner.offroad_permission = lambda s: s.start.x >= 10.1
    with pytest.raises(GroundRouteError, match="no safe local exit"):
        planner.plan(P(0, 0), P(100, 0), 100, 50)


@pytest.mark.parametrize("sea", [box(-30, -30, 30, 30), box(5, -30, 6, 30)])
def test_exit_cannot_cross_water(sea: object) -> None:
    planner = router(box(-10, -10, 10, 10))
    planner.landmap = replace(planner.landmap, sea_zones=MultiPolygon([sea]))
    # Restrict ownership to the eastbound exit to ensure it must cross the sea.
    planner.offroad_permission = lambda s: s.end.x > 0 and s.end.z == 0
    with pytest.raises(GroundRouteError):
        planner.plan(P(0, 0), P(100, 0), 100, 50)


def test_exit_cannot_start_outside_mapped_land() -> None:
    planner = router(box(-10, -10, 10, 10))
    planner.landmap = replace(
        planner.landmap, inclusion_zones=MultiPolygon([box(5, -100, 100, 100)])
    )
    with pytest.raises(GroundRouteError, match="outside mapped land"):
        planner.plan(P(0, 0), P(50, 0), 100, 50)


@pytest.mark.parametrize(
    "segment",
    [
        GroundSegment(P(0, 0), P(100, 0), False),  # arbitrary shortcut after exit
        GroundSegment(P(0, 0), P(10.1, 0), True),  # no road-speed exception
        GroundSegment(P(-20, 0), P(10.1, 0), False),  # enter from valid land
        GroundSegment(P(0, 0), P(5, 0), False),  # stop inside exclusion
    ],
)
def test_exit_exception_does_not_authorize_other_segments(
    segment: GroundSegment,
) -> None:
    assert not allowed_origin_exit(router(box(-10, -10, 10, 10)).landmap, segment)


def test_exit_cannot_leave_then_reenter_an_exclusion() -> None:
    planner = router(box(-10, -10, 10, 10), box(20, -10, 30, 10))
    assert not allowed_origin_exit(
        planner.landmap, GroundSegment(P(0, 0), P(30.1, 0), False)
    )


@pytest.mark.parametrize(
    "segment",
    [
        GroundSegment(P(5, 1), P(10.1, 0), False),  # off saved exit line
        GroundSegment(P(-1, 0), P(10.1, 0), False),  # before original start
        GroundSegment(P(5, 0), P(20, 0), False),  # altered endpoint
        GroundSegment(P(5, 0), P(10.1, 0), True),  # altered road mode
    ],
)
def test_saved_exit_only_allows_its_original_suffix(segment: GroundSegment) -> None:
    planner = router(box(-10, -10, 10, 10))
    assert not planner.allowed_exit_remainder(
        segment, GroundSegment(P(0, 0), P(10.1, 0), False)
    )


def test_nevada_placement_near_exclusion_edge_can_reach_clear_land() -> None:
    terrain = Nevada()
    land = load_landmap(Path("resources/theaters/nevada/landmap.p"))
    assert land is not None
    planner = CampaignGroundRouter(land, [])

    def position(lat: float, lng: float) -> P:
        point = Point.from_latlng(LatLng(lat, lng), terrain)
        return P(point.x, point.y)

    origin, destination = position(36.21664, -115.33637), position(36.86, -115.55)
    route = planner.plan(origin, destination, 193121.28, 96560.64)
    assert route.segments[0].start == origin
    assert route.segments[0].length == pytest.approx(286.81, abs=0.1)
    assert allowed_origin_exit(land, route.segments[0])
    assert route.segments[-1].end == destination
    assert all(planner.allowed(s) for s in route.segments[1:])
