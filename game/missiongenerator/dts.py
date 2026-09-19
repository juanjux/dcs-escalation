"""The A-10's data transfer system, which is not a .dtc file at all.

Every module that takes a cartridge takes a different one. The Hornet and the Viper
read a .dtc from ``Saved Games/DCS/DTC``; the A-10C II reads a **Lua database beside
the mission**. Its own default says so, in a comment in
``NavigationComputer/Database/Default_DTS_CDU_DB.lua``: a file named
``<mission>_DTS_CDU_Database.lua`` in the Missions folder next to the .miz replaces
the stock one, and LOAD ALL on the CDU -- the thing the player does in the cold start
-- reads it.

It carries waypoints and nothing else: no threat rings, no lines. So the A-10 gets the
points the player wrote down and none of the air-defence picture, which is a fact
about the aeroplane rather than a gap here.

The numbering starts where DCS's own sample starts, at 51, so nothing collides with
the mission's own route.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from dcs.mapping import Point

from game.ato.savedpoints import PointKind, SavedPoint, points_of

if TYPE_CHECKING:
    from game import Game
    from game.ato.flight import Flight

#: Where DCS's own sample database starts. Below it are the mission's own points.
FIRST_INDEX = 51

#: As long an identifier as the CDU shows. ED's sample uses "CHONGER" and "ELVIS.".
NAME_LENGTH = 12

#: The aircraft that read one of these.
AIRCRAFT = {"A-10C", "A-10C_2"}


def _identifier(point: SavedPoint, number: int) -> str:
    """An identifier the CDU will take: upper case, short, never empty."""
    letters = [c for c in point.name.upper() if c.isalnum() or c in " ._-"]
    name = "".join(letters).strip()[:NAME_LENGTH]
    return name or f"PT{number}"


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


def database(game: Game) -> str:
    """The Lua the CDU loads.

    One database for the whole mission, because that is what the file is -- it is not
    per aircraft -- so a point carries the callsign of the flight it was written for.
    """
    lines = [
        "-- Written by DCS Escalation. Loaded by the A-10's DTS when the CDU is told",
        "-- to LOAD ALL, in place of the stock database.",
        "",
        'dofile(LockOn_Options.script_path.."NavigationComputer/Database/'
        'Database_Common.lua")',
        "",
        "LoadAllAirfields\t= 1",
        "",
        "WP_database = {}",
    ]
    number = FIRST_INDEX
    for flight in flights_with_points(game):
        for point in points_of(flight):
            latlng = Point(point.x, point.y, game.theater.terrain).latlng()
            name = _identifier(point, number)
            note = "markpoint" if point.kind is PointKind.MARKPOINT else "waypoint"
            lines.extend(
                [
                    "",
                    f"-- {flight.callsign} {note}: {point.name}",
                    f"WP_database[{number}] = {{}}",
                    f'WP_database[{number}]["UPDATE"] = WP_UPDATE_NEW.WP_NEW',
                    f'WP_database[{number}]["Identifier"] = "{name}"',
                    f'WP_database[{number}]["Type"] = Waypoint_Types.WPT_UNK',
                    f'WP_database[{number}]["Latitude"] = {latlng.lat:.6f}',
                    f'WP_database[{number}]["Longitude"] = {latlng.lng:.6f}',
                    f'WP_database[{number}]["RefEllipsoid"] = ELLIPSOID.ELL_WGS_84',
                    f'WP_database[{number}]["ElevationPresent"] = 1',
                    f'WP_database[{number}]["Elevation"] = {point.altitude_ft}.0',
                    f'WP_database[{number}]["DTOTPresent"] = 0',
                    f'WP_database[{number}]["Steer_mode"] = '
                    "Waypoint_Steer_mode.WPT_SM_TO_FROM",
                    f'WP_database[{number}]["VNAV_mode"] = '
                    "Waypoint_VNAV_mode.WPT_VNAVM_2D",
                    f'WP_database[{number}]["Angle_3D"] = 0.0',
                    f'WP_database[{number}]["Scale"] = '
                    "Waypoint_Scale.WPT_SCALE_ENROUTE",
                    f'WP_database[{number}]["Divert"] = 0',
                ]
            )
            number += 1
    return "\n".join(lines) + "\n"


def path_beside(mission: Path) -> Path:
    """Where DCS looks for it: the mission's own name, in the mission's own folder."""
    return mission.with_name(f"{mission.stem}_DTS_CDU_Database.lua")


def write_database(game: Game, mission: Path) -> Path | None:
    """Write it beside the mission, or take away last turn's if there is nothing.

    A stale file would keep loading points from a turn nobody is flying any more, so
    a turn with nothing written down removes it rather than leaving it.
    """
    path = path_beside(mission)
    if not any(True for _flight in flights_with_points(game)):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.exception("Could not remove the stale DTS database %s", path)
        return None
    try:
        path.write_text(database(game), encoding="utf-8")
    except OSError:
        logging.exception("Could not write the DTS database %s", path)
        return None
    logging.info("Wrote the A-10 DTS database %s", path)
    return path
