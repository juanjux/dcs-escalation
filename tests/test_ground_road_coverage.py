"""Authored road identity must not depend on a dissolved microscopic buffer."""

import pytest
from shapely.geometry import MultiPolygon, box

from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment
from game.groundmovement.orders import GroundPosition as P
from game.groundmovement.routing import CampaignGroundRouter
from game.theater.landmap import Landmap


def blocked_land() -> Landmap:
    area = MultiPolygon([box(-1000000, -1000000, 1000000, 1000000)])
    return Landmap(area, area, MultiPolygon())


def road(*points: tuple[float, float]) -> GroundRoute:
    return GroundRoute.from_points(P(*point) for point in points)


@pytest.fixture
def oblique_road() -> GroundRoute:
    # Near-collinear segments at normal DCS projected-coordinate magnitudes.
    return road(
        (-16771.811831439, -782833.73350238),
        (-16988.84937548, -782971.14440179),
        (-17239.232338401, -783131.80424743),
        (-17502.802700047, -783297.89606651),
        (-17632.997287477, -783378.53783909),
        (-17721.408663917, -783435.30708187),
        (-17795.880119186, -783504.02506315),
        (-17913.489260812, -783638.77818428),
    )


@pytest.mark.parametrize("reverse_duplicate", [False, True])
def test_oblique_authored_corridor_keeps_every_edge(
    oblique_road: GroundRoute, reverse_duplicate: bool
) -> None:
    routes = [oblique_road]
    if reverse_duplicate:
        routes.append(
            GroundRoute.from_points(
                [oblique_road.segments[-1].end]
                + [s.start for s in reversed(oblique_road.segments)]
            )
        )
    planner = CampaignGroundRouter(blocked_land(), routes, convoy_corridors=True)
    assert len(planner.edges) == len(oblique_road.segments)
    result = planner.plan(
        oblique_road.segments[0].start, oblique_road.segments[-1].end, 1000, 500
    )
    assert result.length == pytest.approx(oblique_road.length)
    assert all(s.on_road and planner.allowed(s) for s in result.segments)


@pytest.mark.parametrize("fraction", [0.1, 0.25, 0.5, 0.75, 0.9])
def test_interpolated_road_stops_remain_valid(
    oblique_road: GroundRoute, fraction: float
) -> None:
    planner = CampaignGroundRouter(
        blocked_land(), [oblique_road], convoy_corridors=True
    )
    segment = oblique_road.segments[3]
    portion = GroundRoute((segment,))
    middle = portion.position_at(portion.length * fraction)
    planner._validate_position(middle)
    assert planner.allowed(GroundSegment(middle, segment.end))
    assert not planner.allowed(GroundSegment(middle, segment.end, False))
    journey = GroundJourney(portion)
    journey.advance(1, portion.length * fraction, portion.length * fraction / 2)
    planner._validate_position(journey.position)
    assert planner.allowed(GroundSegment(journey.position, segment.end))


def test_coverage_can_span_adjacent_collinear_edges() -> None:
    planner = CampaignGroundRouter(
        blocked_land(), [road((0, 0), (50, 0), (100, 0))], convoy_corridors=True
    )
    assert planner.allowed(GroundSegment(P(25, 0), P(75, 0)))
    assert planner.allowed(GroundSegment(P(75, 0), P(25, 0)))


def test_very_short_interpolated_remnant_keeps_road_permission(
    oblique_road: GroundRoute,
) -> None:
    planner = CampaignGroundRouter(
        blocked_land(), [oblique_road], convoy_corridors=True
    )
    fragment = GroundRoute((oblique_road.segments[3],))
    start = fragment.position_at(fragment.length * 0.66)
    end = fragment.position_at(fragment.length * 0.66 + 0.00001)
    assert planner.allowed(GroundSegment(start, end))


@pytest.mark.parametrize("gap", [0.001, 1, 20])
def test_separate_roads_do_not_authorize_a_new_bridge(gap: float) -> None:
    planner = CampaignGroundRouter(
        blocked_land(),
        [road((0, 0), (50, 0)), road((50 + gap, 0), (100, 0))],
        convoy_corridors=True,
    )
    assert not planner.allowed(GroundSegment(P(25, 0), P(75, 0)))


def test_coverage_does_not_cut_corners_or_widen_the_road() -> None:
    planner = CampaignGroundRouter(
        blocked_land(), [road((0, 0), (50, 0), (50, 50))], convoy_corridors=True
    )
    assert not planner.allowed(GroundSegment(P(25, 0), P(50, 25)))
    assert not planner.allowed(GroundSegment(P(0, 0.01), P(50, 0.01)))
    with pytest.raises(ValueError, match="exclusion"):
        planner._validate_position(P(25, 0.01))
