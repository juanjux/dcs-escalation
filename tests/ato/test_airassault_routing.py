"""Helicopter assault detours must earn their distance through reduced exposure."""

from types import SimpleNamespace as NS
from typing import Any, cast

from dcs.mapping import Point
import pytest
from shapely.geometry import LineString, box
from shapely.geometry.base import BaseGeometry

from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.ato.flightplans.airassault import Builder as AssaultBuilder
from game.theater.controlpoint import ControlPointType
from game.theater.missiontarget import MissionTarget
from game.utils import feet


def point(x: float, y: float) -> Point:
    return Point(x, y, cast(Any, None))


def builder(path: list[Point], threats: BaseGeometry) -> WaypointBuilder:
    zones = NS(
        all=threats,
        path_threatened=lambda a, b: threats.intersects(
            LineString([(a.x, a.y), (b.x, b.y)])
        ),
    )
    coalition = NS(
        doctrine=NS(),
        opponent=NS(threat_zone=zones),
        nav_mesh=NS(shortest_path=lambda a, b: path),
        bullseye=None,
        game=NS(settings=NS()),
    )
    return WaypointBuilder(cast(Any, NS(coalition=coalition)))


def test_prunes_a_long_detour_with_more_exposure_into_the_target_area() -> None:
    start, corner, target = point(0, 0), point(0, 100000), point(100000, 0)
    route = [start, corner, target]
    planner = builder(route, box(80000, -20000, 120000, 20000))
    assert list(planner.clean_nav_points(route)) == [corner]
    assert list(planner.clean_nav_points(route, prune_threatened_detours=True)) == []


def test_keeps_a_useful_short_detour_around_an_intervening_defence() -> None:
    start, corner, target = point(-10000, 0), point(0, 7000), point(10000, 0)
    route = [start, corner, target]
    planner = builder(route, box(-5000, -3000, 5000, 3000))
    assert list(planner.clean_nav_points(route, prune_threatened_detours=True)) == [
        corner
    ]


def test_prunes_small_exposure_saving_that_does_not_justify_a_huge_detour() -> None:
    start, corner, target = point(-10000, 0), point(0, 100000), point(10000, 0)
    route = [start, corner, target]
    planner = builder(route, box(-100, -100, 100, 100))
    assert list(planner.clean_nav_points(route, prune_threatened_detours=True)) == []


@pytest.mark.parametrize("reverse", [False, True])
def test_inbound_and_outbound_keep_endpoints_and_radio_altitude(reverse: bool) -> None:
    route = [point(0, 0), point(0, 100000), point(100000, 0)]
    if reverse:
        route.reverse()
    planner = builder(route, box(80000, -20000, 120000, 20000))
    nav = planner.nav_path(
        route[0], route[-1], feet(200), True, prune_threatened_detours=True
    )
    assert not nav
    assert len(route) == 3


def test_retained_detour_preserves_requested_radio_height(monkeypatch: Any) -> None:
    route = [point(-10000, 0), point(0, 7000), point(10000, 0)]
    planner = builder(route, box(-5000, -3000, 5000, 3000))
    monkeypatch.setattr(WaypointBuilder, "perturb", staticmethod(lambda p: p))
    nav = planner.nav_path(
        route[0], route[-1], feet(200), True, prune_threatened_detours=True
    )
    assert len(nav) == 1 and nav[0].position == route[1]
    assert nav[0].alt == feet(200) and nav[0].alt_type == "RADIO"


def test_other_flight_types_keep_the_existing_routing_policy() -> None:
    route = [point(0, 0), point(0, 100000), point(100000, 0)]
    planner = builder(route, box(80000, -20000, 120000, 20000))
    assert len(planner.nav_path(route[0], route[-1], feet(200))) == 1


@pytest.mark.parametrize(
    "aircraft,is_helo", [("CH-47Fbl1", True), ("UH-60A", True), ("C-130J-30", False)]
)
def test_assault_builder_enables_exposure_pruning_only_for_helicopters(
    aircraft: str,
    is_helo: bool,
    monkeypatch: Any,
) -> None:
    start, corner, target = point(0, 0), point(0, 100000), point(100000, 0)
    planner = builder([start, corner, target], box(80000, -20000, 120000, 20000))
    flight: Any = planner.flight
    flight.is_helo = is_helo
    flight.is_c130j = not is_helo
    flight.plane_altitude_offset = 0
    flight.unit_type = NS(
        dcs_id=aircraft,
        preferred_cruise_altitude=feet(200),
        preferred_combat_altitude=feet(200),
    )
    flight.coalition.doctrine.min_combat_altitude = feet(0)
    flight.coalition.doctrine.max_combat_altitude = feet(50000)
    flight.coalition.game.settings.heli_combat_alt_agl = 200
    flight.coalition.game.theater = NS(nearest_land_pos=lambda p: p)
    flight.coalition.bullseye = NS(position=start)
    flight.coalition.nav_mesh.shortest_path = lambda a, b: [a, corner, b]
    flight.departure = NS(position=start, cptype=ControlPointType.OFF_MAP)
    flight.arrival = flight.departure
    flight.divert = None
    flight.package = NS(
        target=MissionTarget("Objective", target), waypoints=NS(ingress=point(90000, 0))
    )
    monkeypatch.setattr(WaypointBuilder, "perturb", staticmethod(lambda p: p))
    layout = AssaultBuilder(flight).layout()
    assert not layout.pickup
    assert layout.ingress.position == layout.join.position
    if is_helo:
        assert not layout.nav_to and not layout.nav_from
        assert layout.drop_off is not None and layout.drop_off.alt_type == "RADIO"
    else:
        assert len(layout.nav_to) == 1 and len(layout.nav_from) == 1
