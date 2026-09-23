from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dcs import Point
from dcs.drawing import LineStyle, Rgba
from dcs.drawing.drawings import StandardLayer
from dcs.mission import Mission

from game import Game
from game.ato.flighttype import FlightType
from game.missiongenerator.frontlineconflictdescription import (
    FrontLineConflictDescription,
)
from game.missiongenerator.missiondata import TankerInfo
from game.missiongenerator.orbits import (
    MIN_HALF_WIDTH_M,
    Orbit,
    cap_stations,
    support_orbits,
)

# Misc config settings for objects drawn in ME mission file (and F10 map)
from game.theater import TRIGGER_RADIUS_CAPTURE

if TYPE_CHECKING:
    from game.missiongenerator.missiondata import MissionData

FRONTLINE_COLORS = Rgba(255, 0, 0, 255)
WHITE = Rgba(255, 255, 255, 255)
CP_RED = Rgba(255, 0, 0, 80)
CP_BLUE = Rgba(0, 0, 255, 80)
CP_NEUTRAL = Rgba(128, 128, 128, 80)
BLUE_PATH_COLOR = Rgba(0, 0, 255, 100)
RED_PATH_COLOR = Rgba(255, 0, 0, 100)
ACTIVE_PATH_COLOR = Rgba(255, 80, 80, 100)
ORBIT_LINE = Rgba(0, 200, 255, 255)
ORBIT_FILL = Rgba(0, 200, 255, 55)
NO_FILL = Rgba(0, 0, 0, 0)
ORBIT_LABEL_TEXT = Rgba(0, 190, 255, 255)
ORBIT_LABEL_FILL = Rgba(0, 30, 45, 150)


class DrawingsGenerator:
    """
    Generate drawn objects for the F10 map and mission editor
    """

    def __init__(
        self, mission: Mission, game: Game, mission_data: Optional[MissionData] = None
    ) -> None:
        self.mission = mission
        self.game = game
        #: The generated flights. Without them there are no orbits to draw.
        self.mission_data = mission_data
        self.player_layer = self.mission.drawings.get_layer(StandardLayer.Blue)
        #: Names already given to a drawing. The mission scripts index drawings by
        #: name and drop a repeated one, so a repeat is numbered.
        self.names: dict[str, int] = {}

    def generate_cps_markers(self) -> None:
        """
        Generate cps as circles
        """
        for cp in self.game.theater.controlpoints:
            if cp.captured.is_blue:
                color = CP_BLUE
            elif cp.captured.is_red:
                color = CP_RED
            else:
                color = CP_NEUTRAL
            shape = self.player_layer.add_circle(
                cp.position,
                TRIGGER_RADIUS_CAPTURE,
                line_thickness=2,
                color=WHITE,
                fill=color,
                line_style=LineStyle.Dot,
            )
            shape.name = cp.name

    def generate_routes(self) -> None:
        """
        Generate routes drawing between cps
        """
        seen = set()
        for cp in self.game.theater.controlpoints:
            seen.add(cp)
            for destination, convoy_route in cp.convoy_routes.items():
                if destination in seen:
                    continue
                else:
                    # Determine path color
                    if cp.captured.is_blue and destination.captured.is_blue:
                        color = BLUE_PATH_COLOR
                    elif cp.captured.is_red and destination.captured.is_red:
                        color = RED_PATH_COLOR
                    else:
                        color = ACTIVE_PATH_COLOR

                    # Add shape to layer
                    shape = self.player_layer.add_line_segments(
                        cp.position,
                        [Point(0, 0, self.game.theater.terrain)]
                        + [p - cp.position for p in convoy_route]
                        + [destination.position - cp.position],
                        line_thickness=6,
                        color=color,
                        line_style=LineStyle.Solid,
                    )
                    shape.name = "path from " + cp.name + " to " + destination.name

    def generate_frontlines_drawing(self) -> None:
        """
        Generate a frontline "line" for each active frontline
        """
        for front_line in self.game.theater.conflicts():
            bounds = FrontLineConflictDescription.frontline_bounds(
                front_line, self.game.theater
            )

            end_point = bounds.left_position.point_from_heading(
                bounds.heading_from_left_to_right.degrees, bounds.length
            )
            shape = self.player_layer.add_line_segment(
                bounds.left_position,
                end_point - bounds.left_position,
                line_thickness=16,
                color=FRONTLINE_COLORS,
                line_style=LineStyle.Triangle,
            )
            shape.name = front_line.name

    def _unique(self, name: str) -> str:
        seen = self.names.get(name, 0) + 1
        self.names[name] = seen
        return name if seen == 1 else f"{name} {seen}"

    def _draw_orbit(
        self, orbit: Orbit, half_width: float, thickness: int, fill: Rgba
    ) -> None:
        """The racetrack, or a circle when both ends are the same point."""
        if orbit.length_m < 1.0:
            shape = self.player_layer.add_circle(
                orbit.start,
                half_width,
                line_thickness=thickness,
                color=ORBIT_LINE,
                fill=fill,
                line_style=LineStyle.Dash,
            )
        else:
            shape = self.player_layer.add_oblong(
                orbit.start,
                orbit.end,
                half_width,
                line_thickness=thickness,
                color=ORBIT_LINE,
                fill=fill,
                line_style=LineStyle.Dash,
            )
        shape.name = self._unique(f"{orbit.flight.callsign} orbit")

    def _label(self, position: Point, text: str, font_size: int) -> None:
        label = self.player_layer.add_text_box(
            position,
            text,
            color=ORBIT_LABEL_TEXT,
            fill=ORBIT_LABEL_FILL,
            font_size=font_size,
        )
        label.name = self._unique(f"{text.splitlines()[0]} label")

    def generate_support_orbits(self) -> None:
        """Each blue tanker and AEW&C racetrack, labelled with its callsign, type,
        frequency and TACAN, so it can be found on the F10 map in flight."""
        if self.mission_data is None:
            return
        radios = {
            info.group_name: info
            for info in [*self.mission_data.tankers, *self.mission_data.awacs]
        }
        for orbit in support_orbits(self.mission_data):
            flight = orbit.flight
            self._draw_orbit(orbit, orbit.half_width, 6, ORBIT_FILL)
            text = f"{flight.callsign}  {flight.aircraft_type.display_name}"
            info = radios.get(flight.group_name)
            if info is not None:
                comms = [str(info.freq)]
                if isinstance(info, TankerInfo) and info.tacan is not None:
                    comms.append(f"TCN {info.tacan}")
                text += "\n" + "  ".join(comms)
            self._label(orbit.start, text, font_size=14)

    def generate_cap_stations(self) -> None:
        """Each blue CAP station once, thinner than the support orbits and unfilled."""
        if self.mission_data is None:
            return
        for station in cap_stations(self.mission_data):
            self._draw_orbit(station, MIN_HALF_WIDTH_M, 3, NO_FILL)
            kind = (
                "TARCAP" if station.flight.flight_type is FlightType.TARCAP else "CAP"
            )
            self._label(station.start, f"{kind} {station.flight.callsign}", 12)

    def generate(self) -> None:
        self.generate_frontlines_drawing()
        self.generate_routes()
        self.generate_cps_markers()
        self.generate_cap_stations()
        self.generate_support_orbits()
