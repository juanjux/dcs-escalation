"""Render geographic drawing pages without network access."""

from pathlib import Path
from typing import Any

import pytest
from dcs.terrain import Caucasus
from PIL import Image

from game.ato.savedpoints import SavedDrawing
from game.missiongenerator.drawingspage import DrawingsPage


def test_pages_keep_all_vertices_and_do_not_require_cockpit_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    def basemap(extent: Any, width: int, height: int, **kwargs: Any) -> Image.Image:
        captured.append(extent)
        return Image.new("RGB", (width, height), "#305050")

    monkeypatch.setattr("game.missiongenerator.drawingspage.render_basemap", basemap)
    monkeypatch.setattr(
        "game.missiongenerator.drawingspage.tile_cache_dir", lambda: tmp_path
    )
    drawings = [
        SavedDrawing("Area", [(0, 0), (0, 10000), (5000, 10000), (5000, 0)], True),
        SavedDrawing("Line", [(0, 0), (15000, 5000), (20000, 8000)]),
    ]
    pages = DrawingsPage.paginate("Hawg 1-1", drawings, Caucasus(), False)
    assert len(pages) == 1
    image = tmp_path / "drawings.png"
    pages[0].write(image)
    assert Image.open(image).size == (960, 1080)
    assert "Area" in image.with_suffix(".txt").read_text("utf8")
    assert captured[0].span_x_m > 20000
    assert captured[0].span_y_m > 10000
    assert len(DrawingsPage.paginate("Hawg", drawings * 5, Caucasus(), True)) == 2
