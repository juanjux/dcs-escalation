"""Full-resolution saved drawings on the existing geographic kneeboard basemap."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dcs.mapping import Point
from PIL import ImageDraw

from game.ato.savedpoints import SavedDrawing
from game.missiongenerator.kneeboard_page import KneeboardPage
from game.missiongenerator.kneeboard_recon.basemap import render_basemap
from game.missiongenerator.kneeboard_recon.extent import MapExtent, aspect_correct
from game.missiongenerator.kneeboard_recon.projection import Projector
from game.persistency import tile_cache_dir

if TYPE_CHECKING:
    from dcs.terrain.terrain import Terrain


class DrawingsPage(KneeboardPage):
    def __init__(
        self,
        callsign: str,
        drawings: list[SavedDrawing],
        terrain: Terrain,
        dark: bool,
        page: int = 1,
    ) -> None:
        self.callsign, self.drawings, self.terrain = callsign, drawings, terrain
        self.dark, self.page = dark, page

    @classmethod
    def paginate(
        cls,
        callsign: str,
        drawings: list[SavedDrawing],
        terrain: Terrain,
        dark: bool,
    ) -> list[DrawingsPage]:
        valid = [d for d in drawings if len(d.points) >= 2]
        return [
            cls(callsign, valid[i : i + 8], terrain, dark, i // 8 + 1)
            for i in range(0, len(valid), 8)
        ]

    def write(self, path: Path) -> None:
        from game.missiongenerator.kneeboard import KneeboardPageWriter

        writer = KneeboardPageWriter(dark_theme=self.dark)
        writer.title(f"{self.callsign} drawings ({self.page})")
        points = [p for drawing in self.drawings for p in drawing.points]
        if not points:
            writer.write(path)
            return
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        margin = max(500, max(max(xs) - min(xs), max(ys) - min(ys)) * 0.08)
        width, height = 912, 780
        extent = aspect_correct(
            MapExtent(
                min(xs) - margin,
                max(xs) + margin,
                min(ys) - margin,
                max(ys) + margin,
                self.terrain,
            ),
            width,
            height,
        )
        image = render_basemap(extent, width, height, cache_dir=tile_cache_dir())
        draw = ImageDraw.Draw(image)
        projector = Projector(extent, width, height)
        colours = [
            "#ffe040",
            "#68e6ff",
            "#ff9c6b",
            "#b0f078",
            "#f7b5ff",
            "#ff7474",
            "#a7bcff",
            "#ffffff",
        ]
        for number, drawing in enumerate(self.drawings, start=1):
            vertices = [
                projector.project(Point(x, y, self.terrain)) for x, y in drawing.points
            ]
            if drawing.closed:
                vertices.append(vertices[0])
            colour = colours[number - 1]
            draw.line(vertices, fill="black", width=7)
            draw.line(vertices, fill=colour, width=4)
            if drawing.closed:
                x = round(sum(v[0] for v in vertices[:-1]) / (len(vertices) - 1))
                y = round(sum(v[1] for v in vertices[:-1]) / (len(vertices) - 1))
            else:
                x, y = vertices[len(vertices) // 2]
            draw.text(
                (x + 5, y + 5),
                str(number),
                fill=colour,
                font=writer.heading_font,
                stroke_width=2,
                stroke_fill="black",
            )
        draw.text(
            (width - 28, 8),
            "N",
            font=writer.heading_font,
            fill="white",
            stroke_width=2,
            stroke_fill="black",
        )
        draw.line([(width - 20, 65), (width - 20, 40)], fill="white", width=3)
        writer.image.paste(image, (24, 80))
        for number, drawing in enumerate(self.drawings, start=1):
            x = 24 + ((number - 1) % 2) * 456
            y = 880 + ((number - 1) // 2) * 35
            writer.draw.text(
                (x, y),
                f"{number}. {drawing.name}",
                font=writer.table_font,
                fill=writer.foreground_fill,
            )
            writer.text_buffer.append(f"{number}. {drawing.name}: {drawing.points}")
        writer.write(path)
