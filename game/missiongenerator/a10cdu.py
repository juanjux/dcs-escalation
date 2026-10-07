"""The A-10's navigation computer, written into the mission.

The A-10 has no data cartridge: it does not appear in DCS's own DTC editor, and the
``<mission>_DTS_CDU_Database.lua`` its default database mentions is a CSV read only
when the player goes to the DTS page and uploads it by hand.

What it does have is the state "Prepare Mission" saves. Flying a mission and saving it
writes the whole cockpit into the .miz, one file per subsystem, and the navigation
computer's is ``Avionics/<type>/<unit id>/CDU/SETTINGS.lua``. Written from outside it
is read exactly the same, which gives the saved points everything they need:

* they go in the **waypoint database** rather than on the flight plan, so the mission
  route is untouched and the MSN flight plan draws no line to them;
* they get a **flight plan of their own**, so stepping through them is a switch;
* elevations are stored explicitly, without depending on the CDU's terrain ranging.

Terrain ranging is not always available at cockpit initialization. Enabling DTSAS
alone can leave every point at ``EL: *****``, making the steerpoint an invalid SPI.
Route points use ground elevations; saved points keep their entered MSL elevations.

Measured against DCS's own output rather than guessed: elevations are metres, the
number a waypoint ends up with is its position in the table rather than the
``wpt_num`` written beside it, and the aerodromes DCS loads itself occupy 51 to 71.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from dcs.mapping import Point

from game.ato.savedpoints import SavedPoint, points_of
from game.elevation import elevation_m

if TYPE_CHECKING:
    from game import Game
    from game.ato.flight import Flight
    from game.missiongenerator.aircraft.flightdata import FlightData

#: The aircraft whose cockpit keeps its navigation computer here.
AIRCRAFT = {"A-10C", "A-10C_2"}

#: As long an identifier as the CDU shows.
NAME_LENGTH = 12

#: ``Waypoint_Types.WPT_UNK`` in the module's own table.
UNKNOWN = 20

#: Whatever ellipsoid code 67 is, it is what DCS writes for every point it saves.
ELLIPSOID = 67

#: The flight plan the saved points get. 1 is the mission's own, built from the route
#: and not ours to change -- writing it makes no difference, which was measured.
EXTRA_PLAN = 2
EXTRA_PLAN_NAME = "EXTRA"

TAB = "\t"


def flights_with_points(game: Game) -> Iterable[Flight]:
    """Every A-10 the player is flying that has something written down for it."""
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count <= 0:
                continue
            if flight.unit_type.dcs_unit_type.id not in AIRCRAFT:
                continue
            if points_of(flight):
                yield flight


def numbers_for(route_length: int, count: int) -> list[int]:
    """The numbers the saved points end up with in the cockpit.

    The aircraft numbers a waypoint by where it sits in the table, not by the
    ``wpt_num`` beside it, so the route fills the first places and the saved points
    follow. Table slots start at 1; CDU point 0 is the aircraft's initial position.
    """
    first = route_length + 1
    return list(range(first, first + count))


def uses_custom_cdu(flight: FlightData) -> bool:
    """Whether this flight receives a replacement CDU waypoint database."""
    return bool(
        flight.client_units
        and flight.aircraft_type.dcs_unit_type.id in AIRCRAFT
        and flight.saved_points
    )


def route_numbers(flight: FlightData) -> range:
    """Cockpit route numbers, including the custom CDU's one-based table slots."""
    first = 1 if uses_custom_cdu(flight) else 0
    return range(first, first + len(flight.waypoints))


def _identifier(point: SavedPoint, number: int) -> str:
    """A name the CDU will take: upper case, short, never empty."""
    letters = [c for c in point.name.upper() if c.isalnum() or c in " ._-"]
    return "".join(letters).strip()[:NAME_LENGTH] or f"PT{number}"


def _attributes(depth: int) -> list[str]:
    pad = TAB * depth
    return [
        f'{pad}["wpt_attributes"]=',
        pad + "{",
        f'{pad}{TAB}["attr_steer"]=0,',
        f'{pad}{TAB}["attr_angle3d"]=0,',
        f'{pad}{TAB}["attr_scale"]=0,',
        f'{pad}{TAB}["attr_vnav"]=0,',
        f'{pad}{TAB}["attr_vangle"]=1,',
        pad + "},",
    ]


def _position(latlng: Any) -> list[str]:
    """One ``wpt_pos``: degrees and the MGRS grid for the same spot."""
    import mgrs as mgrs_lib

    grid = mgrs_lib.MGRS().toMGRS(latlng.lat, latlng.lng, MGRSPrecision=5)
    pad = TAB * 3
    return [
        f'{pad}["wpt_pos"]=',
        pad + "{",
        f'{pad}{TAB}["pos_zone"]="{grid[:3]}",',
        f'{pad}{TAB}["pos_long"]={latlng.lng:.12f},',
        f'{pad}{TAB}["pos_digraph"]="{grid[3:5]}",',
        f'{pad}{TAB}["pos_lat"]={latlng.lat:.12f},',
        f'{pad}{TAB}["pos_easting"]={int(grid[5:10])},',
        f'{pad}{TAB}["pos_present"]=1,',
        f'{pad}{TAB}["pos_northing"]={int(grid[10:15])},',
        f'{pad}{TAB}["pos_ell"]={ELLIPSOID},',
        pad + "},",
    ]


def _waypoint(slot: int, name: str, latlng: Any, elevation: float | None) -> list[str]:
    """One CDU entry, with an explicit MSL elevation in metres when available."""
    return (
        [
            f"{TAB * 2}[{slot}]=",
            TAB * 2 + "{",
            f'{TAB * 3}["wpt_cr"]={int(elevation is None)},',
            f'{TAB * 3}["wpt_elev_present"]={int(elevation is not None)},',
            f'{TAB * 3}["wpt_num"]={slot},',
            f'{TAB * 3}["wpt_dtot_present"]=0,',
            f'{TAB * 3}["div_present"]=0,',
            f'{TAB * 3}["wpt_id"]="{name}",',
        ]
        + ([f'{TAB * 3}["wpt_elev"]={elevation:.6f},'] if elevation is not None else [])
        + _attributes(3)
        + _position(latlng)
        + [f'{TAB * 3}["wpt_type"]={UNKNOWN},', TAB * 2 + "},"]
    )


def _flight_plan(numbers: Sequence[int]) -> list[str]:
    lines = [
        f'{TAB}["flight_plans"]=',
        TAB + "{",
        f"{TAB * 2}[{EXTRA_PLAN}]=",
        TAB * 2 + "{",
        f'{TAB * 3}["fp_name"]="{EXTRA_PLAN_NAME}",',
        f'{TAB * 3}["waypoints"]=',
        TAB * 3 + "{",
    ]
    for place, number in enumerate(numbers, start=1):
        lines += (
            [
                f"{TAB * 4}[{place}]=",
                TAB * 4 + "{",
                f'{TAB * 5}["wpt_number"]={number},',
            ]
            + _attributes(5)
            + [TAB * 4 + "},"]
        )
    return lines + [TAB * 3 + "},", TAB * 2 + "},", TAB + "},"]


def settings(flight: Any, terrain: Any) -> str:
    """The navigation computer for one aircraft, as its SETTINGS.lua."""
    route = list(flight.waypoints)
    saved = list(flight.saved_points)
    numbers = numbers_for(len(route), len(saved))

    entries: list[str] = []
    for slot, waypoint in enumerate(route, start=1):
        name = "INIT POSIT" if slot == 1 else str(waypoint.display_name)
        latlng = Point(waypoint.position.x, waypoint.position.y, terrain).latlng()
        elevation = elevation_m(latlng.lat, latlng.lng)
        if elevation is None:
            logging.warning("No ground elevation for A-10 CDU waypoint %s", slot)
        entries += _waypoint(
            slot,
            name.upper()[:NAME_LENGTH],
            latlng,
            max(0.0, elevation) if elevation is not None else None,
        )
    for place, (number, point) in enumerate(zip(numbers, saved)):
        entries += _waypoint(
            len(route) + place + 1,
            _identifier(point, number),
            Point(point.x, point.y, terrain).latlng(),
            point.altitude_ft * 0.3048,
        )

    return "\n".join(
        [
            "settings=",
            "{",
            f'{TAB}["coords_format"]=0,',
            f'{TAB}["initial_number"]=0,',
            "\t-- Keep terrain ranging available for points edited in the cockpit.",
            f'{TAB}["dtsas_func"]=1,',
            f'{TAB}["dtsas_cr"]=1,',
            f'{TAB}["dtsas_owc"]=100,',
            f'{TAB}["steer_number"]=0,',
        ]
        + (_flight_plan(numbers) if numbers else [])
        + [f'{TAB}["waypoints"]=', TAB + "{"]
        + entries
        + [TAB + "},", "}", ""]
    )


def inside_mission(flight: Any) -> str:
    """Where in the .miz this aircraft's navigation computer lives."""
    aircraft = flight.aircraft_type.dcs_unit_type.id
    return f"Avionics/{aircraft}/{flight.units[0].id}/CDU/SETTINGS.lua"


def write_into_mission(game: Game, mission_data: Any, mission: Path) -> list[str]:
    """One navigation computer per A-10 the player is flying with points written down."""
    entries: dict[str, str] = {}
    for flight in getattr(mission_data, "flights", []):
        if not uses_custom_cdu(flight):
            continue
        entries[inside_mission(flight)] = settings(flight, game.theater.terrain)
    if not entries:
        return []

    try:
        with zipfile.ZipFile(mission, "a", zipfile.ZIP_DEFLATED) as archive:
            for path, body in entries.items():
                archive.writestr(path, body)
    except OSError:
        logging.exception(
            "Could not write the A-10 navigation computer into %s", mission
        )
        return []
    logging.info(
        "Wrote %d A-10 navigation computer(s) into %s", len(entries), mission.name
    )
    return sorted(entries)
