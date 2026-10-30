"""Persistent drawing identities and bounded native export."""

import pickle
from types import SimpleNamespace
from typing import Any

import pytest

from game.ato.savedpoints import SavedDrawing, add_drawing, drawings_of
from game.missiongenerator.saveddrawings import (
    append_apache_drawings,
    cockpit_lines,
    fit_points,
)


def shape(name: str = "Line", count: int = 30, closed: bool = False) -> SavedDrawing:
    return SavedDrawing(name, [(float(i), float(i % 3)) for i in range(count)], closed)


def test_old_squadron_gets_independent_drawing_list_and_stable_uuid() -> None:
    first: Any = SimpleNamespace(squadron=SimpleNamespace())
    second: Any = SimpleNamespace(squadron=SimpleNamespace())
    drawing = shape()
    assert add_drawing(first, drawing)
    assert drawings_of(first) == [drawing]
    assert not drawings_of(second)
    del drawing.id
    identity = drawings_of(first)[0].id
    assert drawings_of(first)[0].id == identity
    assert pickle.loads(pickle.dumps(drawing)).id == identity


@pytest.mark.parametrize("aircraft", ["FA-18C_hornet", "FA-18E", "FA-18F"])
def test_hornet_keeps_boundary_slot_and_closed_outlines(aircraft: str) -> None:
    drawings = [shape(str(i), closed=True) for i in range(4)]
    fitted = cockpit_lines(aircraft, drawings)
    assert len(fitted) == 2
    assert all(len(points) == 7 and points[0] == points[-1] for _, points in fitted)
    assert len(drawings[0].points) == 30


def test_viper_drawings_share_fifteen_points_without_touching_originals() -> None:
    drawings = [shape(str(i), count=5) for i in range(5)]
    fitted = cockpit_lines("F-16C_50", drawings)
    assert len(fitted) == 3
    assert sum(len(points) for _, points in fitted) == 15
    assert cockpit_lines("A-10C_2", drawings) == []
    assert fit_points([(0, 0), (1, 1), (2, 1)], 3, True) == ()


def test_apache_keeps_areas_and_splits_lines_with_shared_endpoints() -> None:
    mission: dict[str, Any] = {"Lines": [], "Areas": []}
    append_apache_drawings(mission, [shape("Area", 4, True), shape("Line", 8)])
    assert len(mission["Areas"]) == 1
    assert len(mission["Lines"]) == 3
    assert mission["Lines"][0]["vertices"][-1] == mission["Lines"][1]["vertices"][0]
    assert all(2 <= len(line["vertices"]) <= 4 for line in mission["Lines"])
    append_apache_drawings(mission, [shape("Extra", 4, True)] * 20)
    assert len(mission["Areas"]) == 12
    assert len(mission["Lines"]) <= 15


def test_drawing_count_and_numerical_guards() -> None:
    flight: Any = SimpleNamespace(squadron=SimpleNamespace())
    assert not add_drawing(flight, SavedDrawing("Broken", [(0, 0), (float("nan"), 1)]))
    assert all(add_drawing(flight, shape(str(i))) for i in range(50))
    assert not add_drawing(flight, shape("Too many"))
