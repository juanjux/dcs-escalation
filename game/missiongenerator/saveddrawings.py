"""Fit user drawings into existing DTC line partitions without changing routes."""

from collections.abc import Sequence
from typing import Any

from game.ato.savedpoints import SavedDrawing

XY = tuple[float, float]


def fit_points(points: Sequence[XY], maximum: int, closed: bool) -> tuple[XY, ...]:
    vertices = list(points)
    if closed and vertices and vertices[0] == vertices[-1]:
        vertices.pop()
    room = maximum - int(closed)
    if room < (3 if closed else 2):
        return ()
    if len(vertices) > room:
        vertices = [
            vertices[round(i * (len(vertices) - 1) / (room - 1))] for i in range(room)
        ]
    if closed and vertices:
        vertices.append(vertices[0])
    return tuple(vertices)


def cockpit_lines(
    aircraft: str,
    drawings: Sequence[SavedDrawing],
) -> list[tuple[str, tuple[XY, ...]]]:
    """Hornet: two seven-point FLOT lines. Viper: three sets sharing 15 points."""
    hornet = aircraft in {
        "FA-18C_hornet",
        "FA-18E",
        "FA-18F",
        "EA-18G",
        "FA-18ET",
        "FA-18FT",
    }
    if not hornet and aircraft != "F-16C_50":
        return []
    count, budget = (2, 14) if hornet else (3, 15)
    result: list[tuple[str, tuple[XY, ...]]] = []
    for drawing in drawings:
        if len(result) >= count:
            break
        points = fit_points(
            drawing.points, min(7, budget) if hornet else budget, drawing.closed
        )
        if len(points) < (4 if drawing.closed else 2):
            continue
        result.append((drawing.name, points))
        budget -= len(points)
    return result


def append_apache_drawings(
    mission: dict[str, Any],
    drawings: Sequence[SavedDrawing],
) -> None:
    """Keep quadrilaterals as areas; split other outlines into 2–4 point lines."""
    lines, areas = mission["Lines"], mission["Areas"]
    for drawing in drawings:
        points = list(drawing.points)
        if drawing.closed and points and points[-1] == points[0]:
            points.pop()
        if drawing.closed and len(points) == 4 and len(areas) < 12:
            areas.append(
                {
                    "note": drawing.name[:40],
                    "vertices": [{"x": x, "y": y} for x, y in points],
                    "caption_pos": [],
                    "center_pos": {"x": 0, "y": 0},
                }
            )
            continue
        if drawing.closed and points:
            points.append(points[0])
        pieces = [points[i : i + 4] for i in range(0, len(points) - 1, 3)]
        if len(lines) + len(pieces) > 15:
            continue
        lines.extend(
            {
                "type_num": 6,
                "text": "",
                "note": drawing.name[:40],
                "vertices": [{"x": x, "y": y} for x, y in piece],
            }
            for piece in pieces
        )
