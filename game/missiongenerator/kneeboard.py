"""Generates kneeboard pages relevant to the player's mission.

The player kneeboard includes the following information:

* Airfield (departure, arrival, divert) info.
* Flight plan (waypoint numbers, names, altitudes).
* Comm channels.
* AWACS info.
* Tanker info.
* JTAC info.

Things we should add:

* Flight plan ToT and fuel ladder (current have neither available).
* Support for planning an arrival/divert airfield separate from departure.
* Mission package infrastructure to include information about the larger
  mission, i.e. information about the escort flight for a strike package.
* Target information. Steerpoints, preplanned objectives, ToT, etc.

For multiplayer missions, a kneeboard will be generated per flight.
https://forums.eagle.ru/showthread.php?t=206360 claims that kneeboard pages can
only be added per airframe, so PvP missions where each side have the same
aircraft will be able to see the enemy's kneeboard for the same airframe.
"""

import datetime
import math
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, TYPE_CHECKING, Tuple

from PIL import Image, ImageDraw, ImageFont
from dcs.mapping import Point as DcsPoint
from dcs.mission import Mission
from dcs.planes import F_15ESE
from suntime import Sun, SunTimeException  # type: ignore
from tabulate import tabulate

from game.ato.flighttype import FlightType
from game.ato.savedpoints import PointKind, SavedPoint
from game.missiongenerator.dtc import steerpoint_numbers
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.coordinates import CoordinateFormat, format_latlng
from game.data.alic import AlicCodes
from game.dcs.aircrafttype import AircraftType
from game.radio.radios import RadioFrequency
from game.runways import RunwayData
from game.theater import ConflictTheater, TheaterGroundObject, TheaterUnit
from game.theater.bullseye import Bullseye
from game.utils import Distance, UnitSystem, meters, mps, pounds
from game.weather.weather import Weather
from .aircraft.flightdata import FlightData
from .briefinggenerator import CommInfo, JtacInfo, MissionInfoGenerator
from .kneeboard_page import KneeboardPage
from .kneeboard_recon import airport_imagery as _airport_imagery
from .kneeboard_recon import generate_recon_pages
from .kneeboard_recon.atis import (
    THUNDERSTORM_PRESSURE_DROP_INHG,
    compute_qfe_inhg,
    has_thunderstorm_cells,
    wind_from_deg,
)
from .missiondata import AwacsInfo, TankerInfo
from ..persistency import kneeboards_dir

if TYPE_CHECKING:
    from dcs.terrain.terrain import Terrain
    from game import Game
    from game.theater.conflicttheater import ConflictTheater


class KneeboardPageWriter:
    """Creates kneeboard images."""

    def __init__(
        self, page_margin: int = 24, line_spacing: int = 12, dark_theme: bool = False
    ) -> None:
        if dark_theme:
            self.foreground_fill = (215, 200, 200)
            self.background_fill = (10, 5, 5)
        else:
            self.foreground_fill = (15, 15, 15)
            # Light grey rather than near-white: avoids glare under HDR / Auto-HDR
            # while staying perfectly readable in daylight.
            self.background_fill = (210, 210, 210)
        self.image_size = (960, 1080)
        self.image = Image.new("RGB", self.image_size, self.background_fill)
        # These font sizes create a relatively full page for current sorties. If
        # we start generating more complicated flight plans, or start including
        # more information in the comm ladder (the latter of which we should
        # probably do), we'll need to split some of this information off into a
        # second page.
        self.title_font = ImageFont.truetype(
            "courbd.ttf", 32, layout_engine=ImageFont.Layout.BASIC
        )
        self.heading_font = ImageFont.truetype(
            "courbd.ttf", 24, layout_engine=ImageFont.Layout.BASIC
        )
        self.content_font = ImageFont.truetype(
            "courbd.ttf", 16, layout_engine=ImageFont.Layout.BASIC
        )
        self.table_font = ImageFont.truetype(
            "courbd.ttf", 20, layout_engine=ImageFont.Layout.BASIC
        )
        self.draw = ImageDraw.Draw(self.image)
        self.page_margin = page_margin
        self.x = page_margin
        self.y = page_margin
        # Lowest y a drawn block may reach before it runs off the page. Used by
        # pages that paginate themselves (e.g. SupportPage) to decide when a
        # section no longer fits and must spill onto the next page.
        self.max_content_y = self.image_size[1] - self.page_margin
        self.line_spacing = line_spacing
        self.text_buffer: List[str] = []

    @property
    def position(self) -> Tuple[int, int]:
        return self.x, self.y

    def text(
        self,
        text: str,
        font: Optional[ImageFont.FreeTypeFont] = None,
        fill: Optional[Tuple[int, int, int]] = None,
        wrap: bool = False,
    ) -> None:
        if font is None:
            font = self.content_font
        if fill is None:
            fill = self.foreground_fill

        if wrap:
            text = "\n".join(
                self.wrap_line_with_font(
                    line, self.image_size[0] - self.page_margin - self.x, font
                )
                for line in text.splitlines()
            )

        self.draw.text(self.position, text, font=font, fill=fill)
        box = self.draw.textbbox(self.position, text, font=font)
        height = abs(box[1] - box[3])  # abs(top - bottom) => offset
        self.y += height + self.line_spacing
        self.text_buffer.append(text)

    def flush_text_buffer(self) -> None:
        self.text_buffer = []

    def get_text_string(self) -> str:
        return "\n".join(x for x in self.text_buffer)

    def title(self, title: str) -> None:
        self.text(title, font=self.title_font, fill=self.foreground_fill)

    def heading(self, text: str) -> None:
        self.text(text, font=self.heading_font, fill=self.foreground_fill)

    def table(
        self,
        cells: List[List[str]],
        headers: Optional[List[str]] = None,
        font: Optional[ImageFont.FreeTypeFont] = None,
    ) -> None:
        if headers is None:
            headers = []
        if font is None:
            font = self.table_font
        table = tabulate(cells, headers=headers, numalign="right")
        self.text(table, font, fill=self.foreground_fill)

    def write(self, path: Path) -> None:
        self.image.save(path)
        path.with_suffix(".txt").write_text(self.get_text_string(), "utf8")

    @staticmethod
    def measure(render_fn: "Callable[[KneeboardPageWriter], None]") -> int:
        """Returns the pixel height a block consumes, without committing it.

        Builds a throwaway writer, runs ``render_fn`` against it, and reports how
        far down the page the cursor moved (``y`` advance from the top margin).
        A fresh 960x1080 image per call is wasteful in the abstract but kneeboard
        generation is not perf-critical, and this keeps the measurement using the
        exact same drawing/wrapping code paths the real render will use.
        """
        writer = KneeboardPageWriter()
        render_fn(writer)
        return writer.y - writer.page_margin

    @staticmethod
    def wrap_line(inputstr: str, max_length: int) -> str:
        if len(inputstr) <= max_length:
            return inputstr
        tokens = inputstr.split(" ")
        output = ""
        segments = []
        for token in tokens:
            combo = output + " " + token
            if len(combo) > max_length:
                combo = output + "\n" + token
                segments.append(combo)
                output = ""
            else:
                output = combo
        return "".join(segments + [output]).strip()

    @staticmethod
    def wrap_line_with_font(
        inputstr: str, max_width: int, font: ImageFont.FreeTypeFont
    ) -> str:
        if font.getlength(inputstr) <= max_width:
            return inputstr
        tokens = inputstr.split(" ")
        output = ""
        segments = []
        for token in tokens:
            combo = output + " " + token
            if font.getlength(combo) > max_width:
                segments.append(output + "\n")
                output = token
            else:
                output = combo
        return "".join(segments + [output]).strip()


def cloud_type_name(ui_name: str) -> str:
    """The cloud type alone: no variant number, no pack tag.

    "Scattered 5" and "Low level stratus 3 [ATMOS-X]" both name a type and a variant,
    and the kneeboard only has room for the type.
    """
    return re.sub(r"\s+\d+$", "", re.sub(r"\s*\[[^\]]*\]\s*$", "", ui_name)).strip()


@dataclass(frozen=True)
class NumberedWaypoint:
    number: int
    waypoint: FlightWaypoint


class FlightPlanBuilder:
    WAYPOINT_DESC_MAX_LEN = 25

    def __init__(self, start_time: datetime.datetime, units: UnitSystem) -> None:
        self.start_time = start_time
        self.rows: List[List[str]] = []
        self.target_points: List[NumberedWaypoint] = []
        self.last_waypoint: Optional[FlightWaypoint] = None
        self.units = units

    def add_waypoint(self, waypoint_num: int, waypoint: FlightWaypoint) -> None:
        if waypoint.waypoint_type == FlightWaypointType.TARGET_POINT:
            self.target_points.append(NumberedWaypoint(waypoint_num, waypoint))
            return

        if self.target_points:
            self.coalesce_target_points()
            self.target_points = []

        self.add_waypoint_row(NumberedWaypoint(waypoint_num, waypoint))
        self.last_waypoint = waypoint

    def coalesce_target_points(self) -> None:
        if len(self.target_points) <= 4:
            for steerpoint in self.target_points:
                self.add_waypoint_row(steerpoint)
            if self.target_points:
                self.last_waypoint = self.target_points[-1].waypoint
            return

        first_waypoint_num = self.target_points[0].number
        last_waypoint_num = self.target_points[-1].number

        self.rows.append(
            [
                f"{first_waypoint_num}-{last_waypoint_num}",
                "Target points",
                "0",
                self._waypoint_distance(self.target_points[0].waypoint),
                self._ground_speed(self.target_points[0].waypoint),
                self._format_time(self.target_points[0].waypoint.tot),
                self._format_time(self.target_points[0].waypoint.departure_time),
                self._format_min_fuel(self.target_points[0].waypoint.min_fuel),
            ]
        )
        self.last_waypoint = self.target_points[-1].waypoint

    def add_waypoint_row(self, waypoint: NumberedWaypoint) -> None:
        self.rows.append(
            [
                str(waypoint.number),
                KneeboardPageWriter.wrap_line(
                    waypoint.waypoint.display_name,
                    FlightPlanBuilder.WAYPOINT_DESC_MAX_LEN,
                ),
                self._format_alt(waypoint.waypoint.alt),
                self._waypoint_distance(waypoint.waypoint),
                self._waypoint_bearing(waypoint.waypoint),
                self._ground_speed(waypoint.waypoint),
                self._format_time(waypoint.waypoint.tot),
                self._format_time(waypoint.waypoint.departure_time),
                self._format_min_fuel(waypoint.waypoint.min_fuel),
            ]
        )

    @staticmethod
    def _format_time(time: datetime.datetime | None) -> str:
        if time is None:
            return ""
        return f"{time.strftime('%H:%M:%S')}{'Z' if time.tzinfo is not None else ''}"

    def _format_alt(self, alt: Distance) -> str:
        return f"{self.units.distance_short(alt):.0f}"

    def _waypoint_distance(self, waypoint: FlightWaypoint) -> str:
        if self.last_waypoint is None:
            return "-"

        distance = meters(
            self.last_waypoint.position.distance_to_point(waypoint.position)
        )

        return f"{self.units.distance_long(distance):.1f}"

    def _waypoint_bearing(self, waypoint: FlightWaypoint) -> str:
        if self.last_waypoint is None:
            return "-"
        bearing = self.last_waypoint.position.heading_between_point(waypoint.position)

        return f"{(bearing):.0f}"

    def _ground_speed(self, waypoint: FlightWaypoint) -> str:
        if self.last_waypoint is None:
            return "-"

        if waypoint.tot is None:
            return "-"

        if self.last_waypoint.departure_time is not None:
            last_time = self.last_waypoint.departure_time
        elif self.last_waypoint.tot is not None:
            last_time = self.last_waypoint.tot
        else:
            return "-"

        if (waypoint.tot - last_time).total_seconds() == 0.0:
            return "-"

        speed = mps(
            self.last_waypoint.position.distance_to_point(waypoint.position)
            / (waypoint.tot - last_time).total_seconds()
        )

        return f"{self.units.speed(speed):.0f}"

    def _format_min_fuel(self, min_fuel: Optional[float]) -> str:
        if min_fuel is None:
            return ""

        mass = pounds(min_fuel)
        return f"{math.ceil(self.units.mass(mass) / 100) * 100:.0f}"

    def build(self) -> List[List[str]]:
        if self.target_points:
            self.coalesce_target_points()
            self.target_points = []
        return self.rows


class BriefingPage(KneeboardPage):
    """A kneeboard page containing briefing information."""

    def __init__(
        self,
        flight: FlightData,
        bullseye: Bullseye,
        weather: Weather,
        start_time: datetime.datetime,
        dark_kneeboard: bool,
        theater: Optional["ConflictTheater"] = None,
    ) -> None:
        self.flight = flight
        self.bullseye = bullseye
        self.weather = weather
        self.start_time = start_time
        self.dark_kneeboard = dark_kneeboard
        self.theater = theater
        self.flight_plan_font = ImageFont.truetype(
            "courbd.ttf",
            16,
            layout_engine=ImageFont.Layout.BASIC,
        )

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        if self.flight.custom_name:
            custom_name_title = ' ("{}")'.format(self.flight.custom_name)
        else:
            custom_name_title = ""
        writer.title(f"{self.flight.callsign} Mission Info{custom_name_title}")

        # TODO: Handle carriers.
        writer.heading("Airfield Info")
        writer.table(
            [
                self.airfield_info_row("Departure", self.flight.departure),
                self.airfield_info_row("Arrival", self.flight.arrival),
                self.airfield_info_row("Divert", self.flight.divert),
            ],
            headers=["", "Airbase", "ATC", "TCN", "I(C)LS", "RWY"],
        )

        writer.heading(
            f"Flight Plan ({self.flight.squadron.aircraft.variant_id} - "
            f"{self.flight.flight_type.value})"
        )

        units = self.flight.aircraft_type.kneeboard_units

        flight_plan_builder = FlightPlanBuilder(self.start_time, units)
        for num, waypoint in enumerate(self.flight.waypoints):
            flight_plan_builder.add_waypoint(num, waypoint)

        uom_row = [
            [
                "",
                "",
                units.distance_short_uom,
                units.distance_long_uom,
                "T",
                units.speed_uom,
                "",
                "",
                units.mass_uom,
            ]
        ]

        writer.table(
            flight_plan_builder.build() + uom_row,
            headers=[
                "#",
                "Action",
                "Alt",
                "Dist",
                "Brg",
                "GSPD",
                "Time",
                "Departure",
                "Min fuel",
            ],
            font=self.flight_plan_font,
        )

        writer.text(f"Bullseye: {self.bullseye.position.latlng().format_dms()}")

        qnh_in_hg = f"{self.weather.atmospheric.qnh.inches_hg:.2f}"
        qnh_mm_hg = f"{self.weather.atmospheric.qnh.mm_hg:.1f}"
        qnh_hpa = f"{self.weather.atmospheric.qnh.hecto_pascals:.1f}"
        writer.text(
            f"Temperature: {round(self.weather.atmospheric.temperature_celsius)} °C at sea level"
        )
        writer.text(f"QNH: {qnh_in_hg} inHg / {qnh_mm_hg} mmHg / {qnh_hpa} hPa")
        qfe_line = self._format_departure_qfe()
        if qfe_line is not None:
            writer.text(qfe_line)
        writer.text(
            f"Turbulence: {round(self.weather.atmospheric.turbulence_per_10cm)} per 10cm at ground level."
        )
        writer.text(
            f"Wind: {wind_from_deg(self.weather.wind.at_0m.direction)}°"
            f" / {round(mps(self.weather.wind.at_0m.speed).knots)}kts (0ft)"
            f" ; {wind_from_deg(self.weather.wind.at_2000m.direction)}°"
            f" / {round(mps(self.weather.wind.at_2000m.speed).knots)}kts (~6500ft)"
            f" ; {wind_from_deg(self.weather.wind.at_8000m.direction)}°"
            f" / {round(mps(self.weather.wind.at_8000m.speed).knots)}kts (~26000ft)"
        )
        c = self.weather.clouds
        writer.text(
            f'Cloud base: {f"{int(round(meters(c.base).feet, -2))}ft" if c else "CAVOK"}'
            f'{f", {cloud_type_name(c.preset.ui_name)}" if c and c.preset else ""}'
        )

        fl = self.flight

        start_pos = fl.waypoints[0].position.latlng()
        sun = Sun(start_pos.lat, start_pos.lng)

        date = fl.squadron.coalition.game.date
        dt = datetime.datetime(date.year, date.month, date.day)
        tz = fl.squadron.coalition.game.theater.timezone

        # Get today's sunrise and sunset in UTC
        try:
            rise_utc = sun.get_sunrise_time(dt)
            rise = rise_utc + tz.utcoffset(sun.get_sunrise_time(dt))
        except SunTimeException:
            rise_utc = None
            rise = None

        try:
            set_utc = sun.get_sunset_time(dt)
            sunset = set_utc + tz.utcoffset(sun.get_sunset_time(dt))
        except SunTimeException:
            set_utc = None
            sunset = None

        writer.text(
            f"Sunrise - Sunset: {rise.strftime('%H:%M') if rise else 'N/A'} - {sunset.strftime('%H:%M') if sunset else 'N/A'}"
            f" ({rise_utc.strftime('%H:%M') if rise_utc else 'N/A'} - {set_utc.strftime('%H:%M') if set_utc else 'N/A'} UTC)"
        )

        if fl.bingo_fuel and fl.joker_fuel:
            writer.table(
                [
                    [
                        f"{units.mass(pounds(fl.bingo_fuel)):.0f} {units.mass_uom}",
                        f"{units.mass(pounds(fl.joker_fuel)):.0f} {units.mass_uom}",
                    ]
                ],
                ["Bingo", "Joker"],
            )

        if any(self.flight.laser_codes):
            codes: list[list[str]] = []
            for idx, code in enumerate(self.flight.laser_codes, start=1):
                codes.append([str(idx), "" if code is None else str(code)])
            writer.table(codes, ["#", "Laser Code"])

        writer.write(path)

    def _format_departure_qfe(self) -> Optional[str]:
        """Return "QFE: ..." line for the departure field, or None.

        Looks up the departure airport via the theater's controlpoints
        (matched by airfield name), reads the OSM/DEM-derived elevation
        from ``resources/airport_imagery/<terrain>.json``, and reduces
        QNH to QFE via the ISA barometric formula. Returns None when no
        theater was provided, no matching control point exists, or no
        elevation was shipped for the airport.
        """
        if self.theater is None:
            return None
        dep = self.flight.departure
        airport = None
        for cp in self.theater.controlpoints:
            dcs_ap = getattr(cp, "dcs_airport", None)
            if dcs_ap is None:
                continue
            if cp.full_name == dep.airfield_name or dcs_ap.name == dep.airfield_name:
                airport = dcs_ap
                break
        if airport is None:
            return None
        # Shared helper with the recon ATIS pipeline so both consumers walk
        # the same lookup chain (load → for_airport → elevation_m). When
        # this lookup changes (alt source for elevation, new key for
        # matching airports), both surfaces update together.
        elevation_m = _airport_imagery.field_elevation_for_airport(
            self.theater.terrain, airport
        )
        if elevation_m is None:
            return None

        qnh_inhg = self.weather.atmospheric.qnh.inches_hg
        qfe_inhg = compute_qfe_inhg(qnh_inhg, elevation_m)
        qfe_hpa = qfe_inhg * 33.86389
        elev_ft = elevation_m * 3.28084
        line = (
            f"QFE ({dep.airfield_name}, field elev {elev_ft:.0f} ft): "
            f"{qfe_inhg:.2f} inHg / {qfe_hpa:.1f} hPa"
        )
        if has_thunderstorm_cells(self.weather.clouds):
            qfe_low = compute_qfe_inhg(
                qnh_inhg - THUNDERSTORM_PRESSURE_DROP_INHG, elevation_m
            )
            line += (
                f" (~{qfe_low:.2f} in CB cells — local QNH may drop "
                "~3 mb inside storm cores)"
            )
        return line

    def airfield_info_row(
        self, row_title: str, runway: Optional[RunwayData]
    ) -> List[str]:
        """Creates a table row for a given airfield.

        Args:
            row_title: Purpose of the airfield. e.g. "Departure", "Arrival" or
                "Divert".
            runway: The runway described by this row.

        Returns:
            A list of strings to be used as a row of the airfield table.
        """
        if runway is None:
            return [row_title, "", "", "", "", ""]

        atc = ""
        if runway.atc is not None:
            atc = self.format_frequency(runway.atc)
        if runway.tacan is None:
            tacan = ""
        else:
            tacan = str(runway.tacan)
        if runway.ils is not None:
            ils = str(runway.ils)
        elif runway.icls is not None:
            ils = str(runway.icls)
        else:
            ils = ""
        return [
            row_title,
            "\n".join(textwrap.wrap(runway.airfield_name, width=17)),
            atc,
            tacan,
            ils,
            runway.runway_name,
        ]

    def format_frequency(self, frequency: RadioFrequency) -> str:
        channels = self.flight.channels_for(frequency)
        if not channels:
            return str(frequency)

        names = " / ".join(
            self.flight.aircraft_type.channel_name(c.radio_id, c.channel)
            for c in channels
        )
        return f"{names}\n{frequency}"


def _no_title(writer: "KneeboardPageWriter") -> None:
    """A ``title_render`` that draws nothing.

    Used for the continuation chunks of a section whose rows are split across
    pages: the leading heading/FREQ/TOT is drawn only on the first of those pages.
    """


@dataclass
class _SupportSection:
    """One titled block of the Support page: a non-splittable leading part
    (heading, and for the package also FREQ/TOT lines) plus a splittable table.

    ``title_render`` draws the leading part; it is emitted once, on the first
    page the section appears on. ``rows`` may be split across pages, with
    ``headers`` re-drawn on each page the section's rows continue onto.
    """

    title_render: Callable[["KneeboardPageWriter"], None]
    headers: List[str]
    rows: List[List[str]]


class SupportPage(KneeboardPage):
    """A kneeboard page containing information about support units.

    Rendered across as many pages as needed: the flights comm-ladder can be long
    enough on its own to push the AEW&C / Tankers / JTAC tables off the bottom of
    a single fixed-height page, so the content is measured and paginated instead
    of being cut off. Build instances via :meth:`paginate`, not the constructor.
    """

    JTAC_REGION_MAX_LEN = 25

    def __init__(
        self,
        flight: FlightData,
        sections: List[_SupportSection],
        dark_kneeboard: bool,
        page_no: int = 1,
        total_pages: int = 1,
    ) -> None:
        self.flight = flight
        self.sections = sections
        self.dark_kneeboard = dark_kneeboard
        self.page_no = page_no
        self.total_pages = total_pages

    @classmethod
    def paginate(
        cls,
        flight: FlightData,
        package_flights: List[FlightData],
        comms: List[CommInfo],
        awacs: List[AwacsInfo],
        tankers: List[TankerInfo],
        jtacs: List[JtacInfo],
        start_time: datetime.datetime,
        dark_kneeboard: bool,
    ) -> List["SupportPage"]:
        """Builds the Support section(s) and packs them onto measured pages.

        When everything fits, returns a single page that renders identically to
        the pre-pagination layout (no ``(1/1)`` suffix). Otherwise splits the
        sections greedily by pixel height, and if a single section's table is
        taller than an empty page, splits that section's rows across pages
        (re-emitting the table header, but the section's leading part only on the
        first of its pages).
        """
        sections = cls._build_sections(
            flight, package_flights, comms, awacs, tankers, jtacs, start_time
        )

        # Height budget for section content on a page = usable content height
        # minus the title (drawn once at the top of every page).
        def render_title(w: "KneeboardPageWriter") -> None:
            w.title(f"{flight.callsign} Support Info")

        writer = KneeboardPageWriter(dark_theme=dark_kneeboard)
        budget = writer.max_content_y - writer.page_margin
        budget -= KneeboardPageWriter.measure(render_title)

        pages_sections: List[List[_SupportSection]] = [[]]
        used = 0

        def start_new_page() -> None:
            nonlocal used
            pages_sections.append([])
            used = 0

        def measure_section(section: _SupportSection) -> int:
            def render(w: KneeboardPageWriter) -> None:
                cls._render_section(w, section, with_title=True)

            return KneeboardPageWriter.measure(render)

        for section in sections:
            section_height = measure_section(section)
            if section_height <= budget - used:
                # Fits whole on the current page.
                pages_sections[-1].append(section)
                used += section_height
                continue

            if section_height <= budget:
                # Fits whole, but not in what's left: move to a fresh page (if the
                # current one already has content).
                if pages_sections[-1]:
                    start_new_page()
                pages_sections[-1].append(section)
                used += section_height
                continue

            # Taller than a whole empty page: split its rows across pages.
            if pages_sections[-1]:
                start_new_page()
            remaining = section.rows
            first_chunk = True
            while remaining:
                available = budget - used
                take = cls._rows_that_fit(
                    section, remaining, with_title=first_chunk, available=available
                )
                if take == 0 and not pages_sections[-1]:
                    # Nothing fits even on an empty page: force at least one row so
                    # we make progress rather than loop forever. (Extreme edge case;
                    # a single row taller than a page can't be avoided.)
                    take = 1
                if take == 0:
                    start_new_page()
                    continue
                chunk = _SupportSection(
                    title_render=(section.title_render if first_chunk else _no_title),
                    headers=section.headers,
                    rows=remaining[:take],
                )
                pages_sections[-1].append(chunk)
                used += measure_section(chunk)
                remaining = remaining[take:]
                first_chunk = False
                if remaining:
                    start_new_page()

        total = len(pages_sections)
        return [
            cls(
                flight,
                page_sections,
                dark_kneeboard,
                page_no=index + 1,
                total_pages=total,
            )
            for index, page_sections in enumerate(pages_sections)
        ]

    @classmethod
    def _build_sections(
        cls,
        flight: FlightData,
        package_flights: List[FlightData],
        comms: List[CommInfo],
        awacs: List[AwacsInfo],
        tankers: List[TankerInfo],
        jtacs: List[JtacInfo],
        start_time: datetime.datetime,
    ) -> List[_SupportSection]:
        """Builds the four Support sections (Package, AEW&C, Tankers, JTAC).

        Row contents are exactly what the single-page layout produced; only the
        splitting across pages is new.
        """
        comms = list(comms)
        flight_name = flight.custom_name if flight.custom_name else "Flight"
        comms.append(CommInfo(flight_name, flight.intra_flight_channel))

        sections: List[_SupportSection] = []

        # Package Section
        package = flight.package
        custom = f' "{package.custom_name}"' if package.custom_name else ""
        package_freq = cls._format_frequency(flight, package.frequency).replace(
            "\n", " - "
        )
        package_tot = cls._format_time(package.time_over_target)

        def package_title(w: "KneeboardPageWriter") -> None:
            w.heading(f"{package.package_description} Package{custom}")
            w.text(f"  FREQ: {package_freq}", font=w.table_font)
            w.text(f"  TOT: {package_tot}", font=w.table_font)

        comm_ladder = []
        for comm in comms:
            comm_ladder.append(
                [
                    comm.name,
                    str(flight.flight_type),
                    KneeboardPageWriter.wrap_line(str(flight.aircraft_type), 23),
                    str(len(flight.units)),
                    cls._format_frequency(flight, comm.freq, stack=True),
                ]
            )
        for f in package_flights:
            callsign = f.callsign
            if f.custom_name:
                callsign = f"{callsign}\n({f.custom_name})"
            comm_ladder.append(
                [
                    callsign,
                    str(f.flight_type),
                    KneeboardPageWriter.wrap_line(str(f.aircraft_type), 23),
                    str(len(f.units)),
                    cls._format_frequency(flight, f.intra_flight_channel, stack=True),
                ]
            )
        # "#" not "#A/C": the count is a single digit, so the wider header padded
        # the column and pushed the FREQ column off the right edge of the page.
        sections.append(
            _SupportSection(
                package_title,
                ["Callsign", "Task", "Type", "#", "FREQ"],
                comm_ladder,
            )
        )

        # AEW&C
        aewc_ladder = []
        for single_aewc in awacs:
            if single_aewc.depature_location is None:
                tot = "-"
                tos = "-"
            else:
                tot = cls._format_time(single_aewc.start_time)
                tos = cls._format_duration(
                    single_aewc.end_time - single_aewc.start_time
                )

            aewc_ladder.append(
                [
                    str(single_aewc.callsign),
                    cls._format_frequency(flight, single_aewc.freq, stack=True),
                    str(single_aewc.depature_location),
                    "TOT: " + tot + "\n" + "TOS: " + tos,
                ]
            )
        sections.append(
            _SupportSection(
                lambda w: w.heading("AEW&C"),
                ["Callsign", "FREQ", "Departure", "TOT / TOS"],
                aewc_ladder,
            )
        )

        # Tankers
        tanker_ladder = []
        for tanker in tankers:
            tot = cls._format_time(tanker.start_time)
            tos = cls._format_duration(tanker.end_time - tanker.start_time)
            tanker_ladder.append(
                [
                    tanker.callsign,
                    KneeboardPageWriter.wrap_line(tanker.variant, 21),
                    str(tanker.tacan) if tanker.tacan else "N/A",
                    cls._format_frequency(flight, tanker.freq, stack=True),
                    "TOT: " + tot + "\n" + "TOS: " + tos,
                ]
            )
        sections.append(
            _SupportSection(
                lambda w: w.heading("Tankers"),
                # Drop the "Task" column (always "Tanker" in this table) and
                # shorten TACAN to TCN (3-char code), so the wider FREQ column
                # (now COMM1 + COMM2) and TOT/TOS no longer run off the page edge.
                ["Callsign", "Type", "TCN", "FREQ", "TOT / TOS"],
                tanker_ladder,
            )
        )

        # JTAC
        jtac_rows = []
        for jtac in jtacs:
            jtac_rows.append(
                [
                    jtac.callsign,
                    KneeboardPageWriter.wrap_line(
                        jtac.region,
                        cls.JTAC_REGION_MAX_LEN,
                    ),
                    jtac.code,
                    cls._format_frequency(flight, jtac.freq),
                ]
            )
        # "Laser" instead of "Laser Code": the code is 4 digits, so the longer
        # header padded the column and pushed the FREQ column off the page.
        sections.append(
            _SupportSection(
                lambda w: w.heading("JTAC"),
                ["Callsign", "Region", "Laser", "FREQ"],
                jtac_rows,
            )
        )

        return sections

    @staticmethod
    def _render_section(
        writer: "KneeboardPageWriter",
        section: _SupportSection,
        with_title: bool,
    ) -> None:
        """Draws a section (optionally its leading part) then its table."""
        if with_title:
            section.title_render(writer)
        writer.table(section.rows, headers=section.headers)

    @classmethod
    def _rows_that_fit(
        cls,
        section: _SupportSection,
        rows: List[List[str]],
        with_title: bool,
        available: int,
    ) -> int:
        """How many leading rows of a section fit in ``available`` pixels.

        Renders the section's leading part (if any) plus the table header, then
        grows the row count until the measured height would exceed ``available``.
        Measuring the real table each time keeps column widths / wrapping exact,
        which a per-row estimate could not, and the table is small.
        """
        fits = 0
        for count in range(1, len(rows) + 1):
            trial = _SupportSection(
                title_render=(section.title_render if with_title else _no_title),
                headers=section.headers,
                rows=rows[:count],
            )

            def render(w: KneeboardPageWriter, t: _SupportSection = trial) -> None:
                cls._render_section(w, t, with_title=True)

            height = KneeboardPageWriter.measure(render)
            if height > available:
                break
            fits = count
        return fits

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        if self.flight.custom_name:
            custom_name_title = ' ("{}")'.format(self.flight.custom_name)
        else:
            custom_name_title = ""
        suffix = f" ({self.page_no}/{self.total_pages})" if self.total_pages > 1 else ""
        writer.title(f"{self.flight.callsign} Support Info{custom_name_title}{suffix}")
        for section in self.sections:
            section.title_render(writer)
            writer.table(section.rows, headers=section.headers)
        writer.write(path)

    def format_frequency(
        self, frequency: Optional[RadioFrequency], stack: bool = False
    ) -> str:
        return self._format_frequency(self.flight, frequency, stack)

    @staticmethod
    def _format_frequency(
        flight: FlightData,
        frequency: Optional[RadioFrequency],
        stack: bool = False,
    ) -> str:
        if frequency is None:
            return ""
        channels = flight.channels_for(frequency)
        if not channels:
            return str(frequency)

        # In tables, stack COMM1/COMM2 on separate lines so the FREQ column stays
        # narrow. Since a frequency now mirrors onto both radios, joining them inline
        # ("COMM1 Ch 3 / COMM2 Ch 4") widened the column and clipped COMM2 off the
        # right edge of the page. The full-width package-header line still uses inline.
        sep = "\n" if stack else " / "
        names = sep.join(
            flight.aircraft_type.channel_name(c.radio_id, c.channel) for c in channels
        )
        return f"{names}\n{frequency}"

    @staticmethod
    def _format_time(time: datetime.datetime | None) -> str:
        if time is None:
            return ""
        return f"{time.strftime('%H:%M:%S')}{'Z' if time.tzinfo is not None else ''}"

    @staticmethod
    def _format_duration(time: Optional[datetime.timedelta]) -> str:
        if time is None:
            return ""
        time -= datetime.timedelta(microseconds=time.microseconds)
        return f"{time}"


class SeadTaskPage(KneeboardPage):
    """A kneeboard page containing SEAD/DEAD target information."""

    def __init__(self, flight: FlightData, dark_kneeboard: bool) -> None:
        self.flight = flight
        self.dark_kneeboard = dark_kneeboard

    @property
    def target_units(self) -> Iterator[TheaterUnit]:
        if isinstance(self.flight.package.target, TheaterGroundObject):
            yield from self.flight.package.target.strike_targets

    def _waypoint_number_by_position(self) -> Dict[Tuple[float, float], int]:
        """STPT number of each per-target waypoint, keyed by its position.

        DEAD/SEAD flights get one TARGET_POINT waypoint per target, built at the
        target's position, so each listed target can show its assigned waypoint
        number — the same "STPT" the strike task page shows. The number is the
        index into the flight's waypoint list, matching the flight-plan page.
        Targets without a matching waypoint (e.g. an old flight plan generated
        before per-target waypoints existed) simply show a blank STPT.
        """
        numbers: Dict[Tuple[float, float], int] = {}
        for idx, waypoint in enumerate(self.flight.waypoints):
            if waypoint.waypoint_type == FlightWaypointType.TARGET_POINT:
                numbers.setdefault((waypoint.position.x, waypoint.position.y), idx)
        return numbers

    @staticmethod
    def alic_for(unit: TheaterUnit) -> str:
        try:
            return str(AlicCodes.code_for(unit))
        except KeyError:
            return ""

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        if self.flight.custom_name:
            custom_name_title = ' ("{}")'.format(self.flight.custom_name)
        else:
            custom_name_title = ""
        task = "DEAD" if self.flight.flight_type == FlightType.DEAD else "SEAD"
        writer.title(f"{self.flight.callsign} {task} Target Info{custom_name_title}")

        waypoint_numbers = self._waypoint_number_by_position()
        # Smaller table font + 1-char "#" header keep the full DMS Location
        # on-page; at size 20 the longest SAM names (e.g. S-300 Big Bird SR)
        # clipped the coordinates off the right edge.
        table_font = ImageFont.truetype(
            "courbd.ttf", 18, layout_engine=ImageFont.Layout.BASIC
        )
        writer.table(
            [self.target_info_row(t, waypoint_numbers) for t in self.target_units],
            headers=["#", "Description", "ALIC", "Location"],
            font=table_font,
        )

        writer.write(path)

    def target_info_row(
        self, unit: TheaterUnit, waypoint_numbers: Dict[Tuple[float, float], int]
    ) -> List[str]:
        ll = unit.position.latlng()
        unit_type = unit.type
        name = unit.name if unit_type is None else unit_type.name
        number = waypoint_numbers.get((unit.position.x, unit.position.y))
        return [
            "" if number is None else str(number),
            name,
            self.alic_for(unit),
            ll.format_dms(include_decimal_seconds=True),
        ]


class StrikeTaskPage(KneeboardPage):
    """A kneeboard page containing strike target information."""

    WAYPOINT_DESC_MAX_LEN = 35

    def __init__(self, flight: FlightData, dark_kneeboard: bool) -> None:
        self.flight = flight
        self.dark_kneeboard = dark_kneeboard

    @property
    def targets(self) -> Iterator[NumberedWaypoint]:
        for idx, waypoint in enumerate(self.flight.waypoints):
            if waypoint.waypoint_type == FlightWaypointType.TARGET_POINT:
                yield NumberedWaypoint(idx, waypoint)

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        if self.flight.custom_name:
            custom_name_title = ' ("{}")'.format(self.flight.custom_name)
        else:
            custom_name_title = ""
        writer.title(f"{self.flight.callsign} Strike Task Info{custom_name_title}")

        is_f15e = self.flight.units[0].unit_type == F_15ESE
        writer.table(
            [
                [
                    str(target.number),
                    writer.wrap_line(
                        self._target_description(
                            target.waypoint.display_name, i, is_f15e
                        ),
                        self.WAYPOINT_DESC_MAX_LEN,
                    ),
                    target.waypoint.position.latlng().format_dms(
                        include_decimal_seconds=True
                    ),
                ]
                for i, target in enumerate(self.targets)
            ],
            headers=["STPT", "Description", "Location"],
        )

        writer.write(path)

    @staticmethod
    def _target_description(display_name: str, index: int, is_f15e: bool) -> str:
        """The Strike Task 'Description' cell for one target.

        Built from the waypoint's display_name so a player's rename shows here too, and
        NOT written back to the waypoint: the F15E DTC data-cartridge slot reference stays
        confined to this page. (The previous code mutated pretty_name in place, which both
        leaked the DTC tag into the list / flight-plan kneeboard and, once renames moved to
        custom_name, regressed this page to the long auto name.)
        """
        if is_f15e:
            # Slot math must match the CDU data-cartridge programming in
            # PydcsWaypointBuilder.register_special_strike_points ("M{i//8+1}.{i%8+1}")
            # so the kneeboard label points at the slot the jet was actually programmed
            # with -- 8 minor slots per major group.
            return f"{display_name} (DTC M{(index // 8) + 1}.{index % 8 + 1})"
        return display_name


class NotesPage(KneeboardPage):
    """A kneeboard page containing the campaign owner's notes."""

    def __init__(
        self,
        notes: str,
        dark_kneeboard: bool,
    ) -> None:
        self.notes = notes
        self.dark_kneeboard = dark_kneeboard

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        writer.title(f"Notes")
        writer.text(self.notes, wrap=True)
        writer.write(path)


def _abbreviated_target_name(name: str) -> str:
    """Shorten verbose target prefixes so long names fit the kneeboard tables.

    Front-line objectives are named "Front line <CP A>/<CP B>", wide enough to
    overflow the packages list and crowd the map labels; "Front" is
    unambiguous in context.
    """
    return name.replace("Front line ", "Front ")


class SavedPointsPage(KneeboardPage):
    """The points the player wrote down for this aircraft.

    Its own page rather than extra rows on the route: these are not part of the
    flight plan and reading the route should not mean reading past them.

    The numbers are the aircraft's own. They go in after the flight plan, so on a
    Hornet whose route is nine points the first extra is 9 -- and a page that called
    it 1 was a page the player could not read off against the cockpit.

    An aircraft holds far more of them than a page does -- an A-10's navigation
    database runs to thousands -- so the list is paginated rather than capped: the
    aeroplane's limit is the aeroplane's, and the kneeboard's is how many rows fit.
    """

    #: How many rows fit under the title with room to read them.
    ROWS_PER_PAGE = 22

    def __init__(
        self,
        callsign: str,
        points: list[SavedPoint],
        theater: ConflictTheater,
        coordinate_format: CoordinateFormat,
        dark_kneeboard: bool,
        numbers: Optional[list[int]] = None,
        page: int = 1,
        total_pages: int = 1,
    ) -> None:
        self.callsign = callsign
        self.points = points
        self.numbers = (
            numbers if numbers is not None else list(range(1, len(points) + 1))
        )
        self.theater = theater
        self.coordinate_format = coordinate_format
        self.dark_kneeboard = dark_kneeboard
        self.page = page
        self.total_pages = total_pages

    @classmethod
    def paginate(
        cls,
        callsign: str,
        points: list[SavedPoint],
        theater: ConflictTheater,
        coordinate_format: CoordinateFormat,
        dark_kneeboard: bool,
        numbers: Optional[list[int]] = None,
    ) -> List["SavedPointsPage"]:
        """One page while they fit, as many as it takes when they do not.

        A single page carries no "(1/1)", so a handful of points reads exactly as it
        did before there was more than one page of them.
        """
        if numbers is None:
            numbers = list(range(1, len(points) + 1))
        starts = list(range(0, max(len(points), 1), cls.ROWS_PER_PAGE))
        chunks = [points[start : start + cls.ROWS_PER_PAGE] for start in starts]
        return [
            cls(
                callsign,
                chunk,
                theater,
                coordinate_format,
                dark_kneeboard,
                numbers=numbers[start : start + cls.ROWS_PER_PAGE],
                page=index + 1,
                total_pages=len(chunks),
            )
            for index, (start, chunk) in enumerate(zip(starts, chunks))
        ]

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        counted = f" ({self.page}/{self.total_pages})" if self.total_pages > 1 else ""
        writer.title(f"{self.callsign} extra points{counted}")
        rows = []
        for number, point in zip(self.numbers, self.points):
            at = DcsPoint(point.x, point.y, self.theater.terrain)
            # The kind rides on the number rather than taking a column of its own:
            # the page was running off the edge of the kneeboard, and "MK3" says the
            # same thing as a column headed Kind.
            mark = "MK" if point.kind is PointKind.MARKPOINT else ""
            rows.append(
                [
                    f"{mark}{number}",
                    point.name,
                    format_latlng(at.latlng(), self.coordinate_format),
                    f"{point.altitude_ft} ft" if point.altitude_ft else "",
                ]
            )
        writer.table(rows, headers=["STPT", "Name", "Position", "Elev"])
        writer.write(path)


class AllPackagesPage(KneeboardPage):
    """Lists every friendly package with its timing, for cross-package coordination.

    Strike-type packages show their target and TOT; CAP / tanker / AWACS packages
    show their patrol window instead. Rendered in a smaller font and split across
    several pages when there are more packages than fit on one.
    """

    HEADERS = ["Task", "Target", "TOT / Window"]

    def __init__(
        self,
        rows: List[List[str]],
        page_no: int,
        total_pages: int,
        dark_kneeboard: bool,
    ) -> None:
        self.rows = rows
        self.page_no = page_no
        self.total_pages = total_pages
        self.dark_kneeboard = dark_kneeboard

    def write(self, path: Path) -> None:
        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        suffix = f" ({self.page_no}/{self.total_pages})" if self.total_pages > 1 else ""
        writer.title(f"Friendly Packages{suffix}")
        # A little smaller than the default table font so more packages fit.
        font = ImageFont.truetype(
            "courbd.ttf", 18, layout_engine=ImageFont.Layout.BASIC
        )
        writer.table(self.rows, headers=self.HEADERS, font=font)
        writer.write(path)


class PackagesMapPage(KneeboardPage):
    """A theater map with each attack package's target labelled.

    Draws the theater coastline (filled land over sea, from the recon module's
    landmap) so the pilot can see where the attack packages on the previous
    page are headed. Control points are marked for orientation: airfields,
    carriers and LHAs get a distinct shape (square / diamond / triangle) and a
    haloed name label, while FOBs and other points stay as plain dots. All are
    coloured by side (blue friendly, red enemy). Overlapping labels are stacked
    downward (and flipped left near the right edge).
    """

    FRIENDLY = (40, 90, 200)
    ENEMY = (200, 45, 45)
    NEUTRAL = (110, 110, 110)
    TARGET = (255, 140, 0)

    def __init__(
        self,
        targets: List[Tuple[str, float, float]],
        control_points: List[Tuple[float, float, str, str, str]],
        terrain: "Terrain",
        dark_kneeboard: bool,
    ) -> None:
        self.targets = targets
        self.control_points = control_points
        self.terrain = terrain
        self.dark_kneeboard = dark_kneeboard

    def write(self, path: Path) -> None:
        from dcs.mapping import Point as DcsPoint
        from .kneeboard_recon.basemap import render_landmap_basemap
        from .kneeboard_recon.extent import MapExtent, aspect_correct
        from .kneeboard_recon.projection import Projector

        writer = KneeboardPageWriter(dark_theme=self.dark_kneeboard)
        writer.title("Package Targets Map")
        label_font = ImageFont.truetype(
            "courbd.ttf", 13, layout_engine=ImageFont.Layout.BASIC
        )
        writer.text(
            "Orange = package targets; airfields, carriers & LHAs are named "
            "(blue = friendly, red = enemy).",
            font=label_font,
        )

        points = [(x, y) for _, x, y in self.targets]
        points += [(x, y) for x, y, *_ in self.control_points]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        margin = writer.page_margin
        top = writer.y + 8
        avail_w = writer.image_size[0] - 2 * margin
        avail_h = writer.image_size[1] - top - margin

        # World bounding box of everything shown, plus an 8% margin.
        pad = 0.08 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        extent = MapExtent(
            min_x=min(xs) - pad,
            max_x=max(xs) + pad,
            min_y=min(ys) - pad,
            max_y=max(ys) + pad,
            terrain=self.terrain,
        )

        # Size the rendered map to the area-of-operations aspect rather than
        # stretching it to fill the near-square page. A wide, short theater
        # (carriers far offshore + inland targets) would otherwise be aspect-
        # padded with ~half a page of empty sea above and below, squashing the
        # actual front into the middle. Fit to the binding axis, then centre the
        # strip so it reads as a deliberate map rather than a cut-off frame.
        # Page-x (width) <- DCS y (east); page-y (height) <- DCS x (north).
        content_ew = max(extent.span_y_m, 1.0)
        content_ns = max(extent.span_x_m, 1.0)
        map_w = avail_w
        map_h = round(map_w * content_ns / content_ew)
        if map_h > avail_h:
            map_h = avail_h
            map_w = round(map_h * content_ew / content_ns)
        off_x = margin + (avail_w - map_w) // 2
        off_y = top + (avail_h - map_h) // 2

        extent = aspect_correct(extent, map_w, map_h)
        writer.image.paste(
            render_landmap_basemap(extent, map_w, map_h, dark=self.dark_kneeboard),
            (off_x, off_y),
        )

        projector = Projector(extent=extent, pixel_width=map_w, pixel_height=map_h)

        def to_px(x: float, y: float) -> Tuple[int, int]:
            px, py = projector.project(DcsPoint(x, y, self.terrain))
            return off_x + px, off_y + py

        draw = writer.draw
        base_labels: List[Tuple[str, int, int, Tuple[int, int, int]]] = []
        for x, y, side, kind, name in self.control_points:
            px, py = to_px(x, y)
            color = (
                self.FRIENDLY
                if side == "friendly"
                else self.ENEMY if side == "enemy" else self.NEUTRAL
            )
            if kind == "airbase":
                draw.rectangle(
                    (px - 4, py - 4, px + 4, py + 4), fill=color, outline=(0, 0, 0)
                )
            elif kind == "carrier":
                draw.polygon(
                    [(px, py - 5), (px + 5, py), (px, py + 5), (px - 5, py)],
                    fill=color,
                    outline=(0, 0, 0),
                )
            elif kind == "lha":
                draw.polygon(
                    [(px, py - 5), (px + 5, py + 4), (px - 5, py + 4)],
                    fill=color,
                    outline=(0, 0, 0),
                )
            else:
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=color)
                continue
            base_labels.append((name, px, py, color))

        placed: List[Tuple[float, float, float, float]] = []

        def overlaps(box: Tuple[float, float, float, float]) -> bool:
            ax0, ay0, ax1, ay1 = box
            return any(
                ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1
                for bx0, by0, bx1, by1 in placed
            )

        label_h = 15
        right_edge = off_x + map_w
        bottom_edge = off_y + map_h - label_h
        for name, x, y in self.targets:
            px, py = to_px(x, y)
            draw.ellipse(
                [px - 5, py - 5, px + 5, py + 5], fill=self.TARGET, outline=(0, 0, 0)
            )
            tw = label_font.getlength(name)
            lx = px - 8 - tw if px + 8 + tw > right_edge else px + 8
            ly = py - 7
            # Stack overlapping labels downward so clustered targets stay legible.
            while overlaps((lx, ly, lx + tw, ly + label_h)) and ly < bottom_edge:
                ly += label_h
            placed.append((lx, ly, lx + tw, ly + label_h))
            # White plate behind the label so it reads against the map.
            draw.rectangle(
                (lx - 1, ly, lx + tw + 1, ly + label_h), fill=(255, 255, 255)
            )
            draw.text((lx, ly), name, font=label_font, fill=(0, 0, 0))

        # Base names: a white halo instead of a solid plate, in the base's side
        # colour, so they read apart from the boxed black-on-white target labels.
        base_font = ImageFont.truetype(
            "courbd.ttf", 12, layout_engine=ImageFont.Layout.BASIC
        )
        for name, px, py, color in base_labels:
            tw = base_font.getlength(name)
            lx = px - 8 - tw if px + 8 + tw > right_edge else px + 8
            ly = py - 6
            while overlaps((lx, ly, lx + tw, ly + label_h)) and ly < bottom_edge:
                ly += label_h
            placed.append((lx, ly, lx + tw, ly + label_h))
            draw.text(
                (lx, ly),
                name,
                font=base_font,
                fill=color,
                stroke_width=2,
                stroke_fill=(255, 255, 255),
            )

        writer.write(path)


class KneeboardGenerator(MissionInfoGenerator):
    """Creates kneeboard pages for each client flight in the mission."""

    #: Tasks shown with a patrol window (start - end) instead of a single TOT.
    PATROL_TASKS = frozenset(
        {
            FlightType.BARCAP,
            FlightType.TARCAP,
            FlightType.REFUELING,
            FlightType.AEWC,
        }
    )
    #: Rows-per-page for the packages list. Tuned to fill the 1080px-tall
    #: kneeboard at the 18px table font: ~50 rows reach the bottom margin, so 46
    #: leaves a small safety gap while wasting far less space than the old 30.
    PACKAGES_PER_PAGE = 46

    def __init__(self, mission: Mission, game: "Game") -> None:
        super().__init__(mission, game)
        self.dark_kneeboard = self.game.settings.generate_dark_kneeboard and (
            self.mission.start_time.hour > 19 or self.mission.start_time.hour < 7
        )

    def generate(self) -> None:
        """Generates a kneeboard per client flight."""
        temp_dir = Path("kneeboards")
        temp_dir.mkdir(exist_ok=True)
        for aircraft, pages in self.pages_by_airframe().items():
            aircraft_dir = temp_dir / aircraft.dcs_unit_type.id
            aircraft_dir.mkdir(exist_ok=True)
            for idx, page in enumerate(pages):
                page_path = aircraft_dir / f"page{idx:02}.png"
                page.write(page_path)
                self.mission.add_aircraft_kneeboard(aircraft.dcs_unit_type, page_path)
        for type in kneeboards_dir().iterdir():
            if type.is_dir():
                for kneeboard in type.iterdir():
                    self.mission.custom_kneeboards[type.name].append(kneeboard)
            else:
                self.mission.custom_kneeboards[""].append(type)

    def pages_by_airframe(self) -> Dict[AircraftType, List[KneeboardPage]]:
        """Returns a list of kneeboard pages per airframe in the mission.

        Only client flights will be included, but because DCS does not support
        group-specific kneeboard pages, flights (possibly from opposing sides)
        will be able to see the kneeboards of all aircraft of the same type.

        Returns:
            A dict mapping aircraft types to the list of kneeboard pages for
            that aircraft.
        """
        all_flights: Dict[AircraftType, List[KneeboardPage]] = defaultdict(list)
        for flight in self.flights:
            if not flight.client_units:
                continue
            package_flights = [
                f
                for f in self.flights
                if f.package is flight.package and f is not flight
            ]
            all_flights[flight.aircraft_type].extend(
                self.generate_flight_kneeboard(flight, package_flights)
            )
        return all_flights

    def generate_task_page(self, flight: FlightData) -> Optional[KneeboardPage]:
        if flight.flight_type in (FlightType.DEAD, FlightType.SEAD):
            return SeadTaskPage(flight, self.dark_kneeboard)
        elif flight.flight_type is FlightType.STRIKE:
            return StrikeTaskPage(flight, self.dark_kneeboard)
        return None

    def generate_flight_kneeboard(
        self, flight: FlightData, package_flights: List[FlightData]
    ) -> List[KneeboardPage]:
        """Returns a list of kneeboard pages for the given flight."""

        if flight.aircraft_type.utc_kneeboard:
            zoned_time = self.game.conditions.start_time.replace(
                tzinfo=self.game.theater.timezone
            ).astimezone(datetime.timezone.utc)
        else:
            zoned_time = self.game.conditions.start_time

        pages: List[KneeboardPage] = [
            BriefingPage(
                flight,
                self.game.coalition_for(flight.friendly).bullseye,
                self.game.conditions.weather,
                zoned_time,
                self.dark_kneeboard,
                theater=self.game.theater,
            ),
        ]
        pages.extend(
            SupportPage.paginate(
                flight,
                package_flights,
                self.comms,
                self.awacs,
                self.tankers,
                self.jtacs,
                zoned_time,
                self.dark_kneeboard,
            )
        )

        # Only create the notes page if there are notes to show.
        if notes := self.game.notes:
            pages.append(NotesPage(notes, self.dark_kneeboard))

        if (target_page := self.generate_task_page(flight)) is not None:
            pages.append(target_page)

        # Only when the player wrote something down for this aircraft.
        if flight.saved_points:
            pages.extend(
                SavedPointsPage.paginate(
                    flight.callsign,
                    flight.saved_points,
                    self.game.theater,
                    getattr(
                        self.game.settings, "coordinate_format", CoordinateFormat.DDM
                    ),
                    self.dark_kneeboard,
                    numbers=steerpoint_numbers(
                        flight.aircraft_type.dcs_unit_type.id,
                        len(flight.waypoints),
                        len(flight.saved_points),
                    ),
                )
            )

        # Recon overview + detail + airfield-departure pages (gated by settings).
        if self.game.settings.generate_target_recon_kneeboard:
            extra_radius_m = (
                self.game.settings.target_recon_extra_threat_search_nmi * 1852.0
            )
            pages.extend(
                generate_recon_pages(
                    flight=flight,
                    game=self.game,
                    weather=self.game.conditions.weather,
                    extra_threat_search_m=extra_radius_m,
                    dark=self.dark_kneeboard,
                )
            )

        # Friendly-packages coordination list, then the target map, go last (in
        # that order), gated by settings.
        if self.game.settings.generate_all_packages_kneeboard:
            pages.extend(self.generate_all_packages_pages(flight))
            pages.extend(self.generate_packages_map_page(flight))

        return pages

    def _to_kneeboard_time(
        self, time: Optional[datetime.datetime], utc: bool
    ) -> Optional[datetime.datetime]:
        """Apply the same UTC/local convention the rest of the kneeboard uses."""
        if time is None:
            return None
        if utc:
            return time.replace(tzinfo=self.game.theater.timezone).astimezone(
                datetime.timezone.utc
            )
        return time

    def generate_all_packages_pages(self, flight: FlightData) -> List[KneeboardPage]:
        """One row per friendly package (target + TOT, or patrol window), paginated."""
        utc = flight.aircraft_type.utc_kneeboard
        ato = self.game.coalition_for(flight.friendly).ato
        entries: List[Tuple[datetime.datetime, List[str]]] = []
        for package in ato.packages:
            if not package.flights:
                continue
            target = (
                _abbreviated_target_name(package.target.name)[:40]
                if package.target is not None
                else ""
            )
            primary = package.primary_flight
            flight_plan = primary.flight_plan if primary is not None else None
            start = getattr(flight_plan, "patrol_start_time", None)
            end = getattr(flight_plan, "patrol_end_time", None)
            if package.primary_task in self.PATROL_TASKS and start and end:
                timing = (
                    f"{SupportPage._format_time(self._to_kneeboard_time(start, utc))}"
                    f" - {SupportPage._format_time(self._to_kneeboard_time(end, utc))}"
                )
                sort_key = start
            else:
                tot = package.time_over_target
                if tot is not None and tot != datetime.datetime.min:
                    timing = SupportPage._format_time(self._to_kneeboard_time(tot, utc))
                    sort_key = tot
                else:
                    timing = ""
                    sort_key = datetime.datetime.max
            entries.append((sort_key, [package.package_description, target, timing]))

        entries.sort(key=lambda entry: entry[0])
        rows = [row for _, row in entries]
        if not rows:
            return []

        chunks = [
            rows[i : i + self.PACKAGES_PER_PAGE]
            for i in range(0, len(rows), self.PACKAGES_PER_PAGE)
        ]
        return [
            AllPackagesPage(chunk, index + 1, len(chunks), self.dark_kneeboard)
            for index, chunk in enumerate(chunks)
        ]

    def generate_packages_map_page(self, flight: FlightData) -> List[KneeboardPage]:
        """A schematic theater map labelling where each friendly package is headed."""
        player = flight.friendly
        ato = self.game.coalition_for(player).ato
        targets: List[Tuple[str, float, float]] = []
        seen: set[str] = set()
        for package in ato.packages:
            if not package.flights or package.target is None:
                continue
            # Attack packages only -- skip the support patrols (CAP, AWACS,
            # tankers) that loiter rather than head to a target. Strike, CAS,
            # DEAD/SEAD, BAI, anti-ship, OCA, air assault and recon all show.
            if package.primary_task in self.PATROL_TASKS:
                continue
            if package.target.name in seen:
                continue
            seen.add(package.target.name)
            pos = package.target.position
            targets.append(
                (_abbreviated_target_name(package.target.name)[:40], pos.x, pos.y)
            )
        if not targets:
            return []

        control_points: List[Tuple[float, float, str, str, str]] = []
        for cp in self.game.theater.controlpoints:
            if cp.captured == player:
                side = "friendly"
            elif cp.captured.is_neutral:
                side = "neutral"
            else:
                side = "enemy"
            # Fixed bases that can host aircraft get a distinct icon + name;
            # FOBs and off-map spawns stay anonymous dots to avoid clutter.
            if cp.is_carrier:
                kind = "carrier"
            elif cp.is_lha:
                kind = "lha"
            elif cp.category == "airfield":
                kind = "airbase"
            else:
                kind = "dot"
            name = cp.name[:24] if kind != "dot" else ""
            control_points.append((cp.position.x, cp.position.y, side, kind, name))

        return [
            PackagesMapPage(
                targets,
                control_points,
                self.game.theater.terrain,
                self.dark_kneeboard,
            )
        ]
