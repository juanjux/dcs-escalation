"""Indexed queries retain strict boundaries without scanning every polygon."""

import pickle
import random
from pathlib import Path
from typing import Any

import pytest
import shapely
from dcs.mapping import Point
from dcs.terrain import Caucasus
from shapely.geometry import MultiPolygon, Polygon, box

from game.theater.conflicttheater import ConflictTheater
from game.theater.landmap import Landmap, load_landmap, poly_contains


@pytest.fixture
def theater() -> ConflictTheater:
    result = ConflictTheater.__new__(ConflictTheater)
    result.terrain = Caucasus()
    result.landmap = Landmap(
        MultiPolygon([box(0, 0, 100, 100), box(200, 0, 210, 10)]),
        MultiPolygon([box(20, 20, 30, 30), box(120, 20, 130, 30)]),
        MultiPolygon([box(-100, -100, 300, 150)]),
    )
    return result


def _legacy(theater: ConflictTheater, point: Point, ignore: bool) -> tuple[bool, bool]:
    zones = theater.landmap
    assert zones is not None
    excluded = any(
        poly_contains(point.x, point.y, p) for p in zones.exclusion_zones.geoms
    )
    included = poly_contains(point.x, point.y, zones.inclusion_zones)
    sea = any(poly_contains(point.x, point.y, p) for p in zones.sea_zones.geoms)
    return included and (ignore or not excluded), not included and not excluded and sea


@pytest.mark.parametrize("ignore", [False, True])
def test_matches_component_queries_including_edges_and_holes(
    theater: ConflictTheater, ignore: bool
) -> None:
    assert theater.landmap is not None
    rng = random.Random(420)
    points = [(rng.uniform(-120, 320), rng.uniform(-120, 170)) for _ in range(200)]
    for zones in (
        theater.landmap.inclusion_zones,
        theater.landmap.exclusion_zones,
        theater.landmap.sea_zones,
    ):
        for polygon in zones.geoms:
            points.extend(polygon.exterior.coords)
    for x, y in points:
        point = Point(x, y, theater.terrain)
        land, sea = _legacy(theater, point, ignore)
        assert theater.is_on_land(point, ignore) == land
        assert theater.is_in_sea(point) == sea


def test_inclusion_holes_and_empty_maps(theater: ConflictTheater) -> None:
    theater.landmap = Landmap(
        MultiPolygon(
            [
                Polygon(
                    box(0, 0, 100, 100).exterior.coords,
                    [box(20, 20, 30, 30).exterior.coords],
                )
            ]
        ),
        MultiPolygon(),
        MultiPolygon(),
    )
    assert not theater.is_on_land(Point(25, 25, theater.terrain))
    assert not theater.is_in_sea(Point(25, 25, theater.terrain))
    theater.landmap = None
    assert theater.is_on_land(Point(25, 25, theater.terrain))
    assert not theater.is_in_sea(Point(25, 25, theater.terrain))


def test_queries_do_not_iterate_individual_polygons(
    theater: ConflictTheater, monkeypatch: Any
) -> None:
    assert theater.landmap is not None
    zones = theater.landmap
    calls: list[MultiPolygon | Polygon] = []

    def query(x: float, y: float, polygons: MultiPolygon | Polygon) -> bool:
        calls.append(polygons)
        return poly_contains(x, y, polygons)

    monkeypatch.setattr("game.theater.conflicttheater.poly_contains", query)
    assert theater.is_on_land(Point(5, 5, theater.terrain))
    assert calls == [zones.inclusion_zones, zones.exclusion_zones]
    calls.clear()
    assert theater.is_in_sea(Point(150, 40, theater.terrain))
    assert calls == [zones.inclusion_zones, zones.exclusion_zones, zones.sea_zones]


def test_loading_restores_prepared_indexes(
    theater: ConflictTheater, tmp_path: Path
) -> None:
    path = tmp_path / "landmap.p"
    path.write_bytes(pickle.dumps(theater.landmap))
    loaded = load_landmap(path)
    assert loaded is not None
    assert all(
        shapely.is_prepared(zones)
        for zones in (loaded.inclusion_zones, loaded.exclusion_zones, loaded.sea_zones)
    )
