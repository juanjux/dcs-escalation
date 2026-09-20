"""The data cartridge the player loads in the cockpit.

An aircraft's displays draw two things the campaign already knows: a ring round every
air-defence site it has been told about, and the forward line of own troops.

Until DCS 2.9.29 the rings came straight from the mission -- a unit not flagged
``hiddenOnMFD`` appeared on the Hornet's SA page, statically, with no radar or
datalink involved, as ED said when the feature shipped. 2.9.29 moved it behind the
**data transfer cartridge**, and a Hornet with no cartridge loaded now draws nothing
at all however its units are flagged. (The Viper never lost it.) That is what the
forums reported as the SA page losing its threats, and it is why a campaign that
wants rings has to write a cartridge.

What the cartridge says is one word: **mirror**. With ``mirror_MEZ_THRTS`` on, the
aircraft derives the rings from the mission exactly as it used to, ``hiddenOnMFD`` and
all -- measured on probe missions: a site flagged hidden stays off the page while its
neighbours show. So the campaign's existing MFD settings go on deciding which sites
the player may see, and the rings are DCS's own yellow dashed ones rather than circles
we drew. Listing them by hand also works, and looks wrong: they come out as plain
white rings, and every threat name has to be mapped to one DCS knows or it is dropped.

The fronts are the other half, and no mirror can invent those: the FLOT lines are
written out. Each module keeps both somewhere different, under its own limits, so
each is a :class:`Cartridge` of its own.

The file is JSON and a partial one is valid -- DCS ships its own defaults as files
with a single section. It goes two places: into a ``DTC`` folder inside the .miz, and
into ``Saved Games/DCS/DTC`` where it can be loaded by hand.

Putting it in the .miz only puts it on the shelf. **Each aircraft has to name the one
it takes**, in a ``DTC`` table of its own -- ``{AutoLoad, Cartridges:[{name,
default}]}`` -- which is what the mission editor writes when a cartridge is added to a
unit, and what a probe mission that draws the rings carries. Without it the file sits
in the mission and nothing reads it, which is exactly what happened: a complete,
correctly named cartridge in a mission that drew no rings at all.
"""

from __future__ import annotations

import json
import logging
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

from game.missiongenerator.frontlineconflictdescription import (
    FrontLineConflictDescription,
)
from game.theater import Player

if TYPE_CHECKING:
    from game import Game
    from game.theater import ConflictTheater

#: What DCS's own lists spell NONE. The FLOT line starts there, so a cartridge that
#: says nothing about it carries a line nobody is shown.
NONE = 4


@dataclass(frozen=True)
class Front:
    """One contact line, as the points that draw it."""

    name: str
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class NavPoint:
    """One numbered point of the aircraft's navigation set."""

    number: int
    name: str
    x: float
    y: float
    alt_m: float
    #: Where it comes in its own sequence, counted from 1.
    sequence_order: int
    #: Part of the flight plan, as opposed to written down by the player.
    on_route: bool


class Cartridge(ABC):
    """What one aircraft's cartridge will carry, and where it keeps it."""

    #: The DCS unit type this is the cartridge for.
    aircraft: str

    #: How many lines the module itself allows, and of how many points. Read off its
    #: DTC scripts, not decided here.
    max_lines: int
    max_line_points: int

    #: The numbers the module gives its steerpoints, first and last inclusive. Also
    #: read off its scripts.
    first_point: int
    last_point: int

    @abstractmethod
    def sections(
        self, fronts: Sequence[Front], navigation: Sequence[NavPoint]
    ) -> dict[str, Any]:
        """The part of the cartridge's ``data`` tree this aircraft fills.

        ``navigation`` is empty when there is nothing to add to the flight plan, and
        then no navigation section is written at all: the mission's own route is what
        the aircraft starts with, and rewriting it to say the same thing is risk for
        nothing.
        """


class HornetCartridge(Cartridge):
    """The Hornet family: the SA page.

    Limits from ``FA-18C/DTC/SA``: three FLOT lines of seven points. The CJS Super
    Hornet mod ships the same cartridge, section for section, for the E, the F and
    the Growler, so they are the same profile under another type name.
    """

    aircraft = "FA-18C_hornet"
    max_lines = 3
    max_line_points = 7
    # ``WYPT/WYPT_NAV.lua`` numbers the navigation set from 0 and caps it at 59. The
    # last two are left alone: 58 is where HOME goes and 59 is the bullseye.
    first_point = 0
    last_point = 57

    def navigation(self, points: Sequence[NavPoint]) -> dict[str, Any]:
        """The WYPT section.

        ``mirror_NAV_PTS`` off is what makes the list the aircraft's navigation set;
        on, the module takes the mission's route and this is ignored. So the route is
        written out with it, point for point, and the saved points follow it.

        ``NAV_ROUTE`` is left empty: the module builds a route's entries from the
        points that claim it, which is what ``R1`` does.
        """
        return {
            "WYPT": {
                "NAV_PTS": [self._nav_point(point) for point in points],
                "NAV_ROUTE": {},
                "NAV_SETTINGS": {},
                "terrain": "",
                "mirror_NAV_PTS": False,
            }
        }

    @staticmethod
    def _nav_point(point: NavPoint) -> dict[str, Any]:
        """Every field ``WYPT_NAV.lua`` writes when it adds one by hand."""
        number = point.number
        return {
            "id": f"STPT{number}",
            "idOA": f"OA{number}",
            "idOA_Line": f"OA{number}Line",
            "wypt_num": number,
            "x": point.x,
            "y": point.y,
            "alt": point.alt_m,
            "note": "",
            "text_note": point.name[:24],
            # Sequence 1 is the flight plan, in the order it is flown. The points the
            # player wrote down take the next sequence along rather than none at all:
            # a point in no sequence can only be reached by typing its number into the
            # HSI, and one sequence over is a switch.
            "R1": point.on_route,
            "R1_order": number + 1 if point.on_route else None,
            "R2": not point.on_route,
            "R2_order": None if point.on_route else point.sequence_order,
            "R3": False,
            "altitudeType": 1,
            "velocityType": 3,
            "isOA": False,
            "OA_Range": 0.0,
            "OA_Bearing": 0.0,
            "OA_X": 0.0,
            "OA_Y": 0.0,
            "OA_Alt": 0.0,
            "OA_DeltaX": 0.0,
            "OA_DeltaY": 0.0,
            "OA_Bearing_Units": 1,
            "OA_Range_Units": 1,
            "OA_Elevation_Units": 1,
        }

    def sections(
        self, fronts: Sequence[Front], navigation: Sequence[NavPoint]
    ) -> dict[str, Any]:
        written: dict[str, Any] = {
            "SA": {
                # Every key the module's own skeleton declares, not only the ones
                # filled. A cartridge that draws the rings carries a complete section;
                # one that names three keys out of eleven is a shape the loader has
                # never been handed, and the SA page is not the place to find out.
                # Everything untouched is written empty, or at the NONE its own list
                # starts on -- CAP is 10, corridors 8, the rest 4, ED's numbers.
                "CAP_PTS": [],
                "CORRIDORS": [],
                "MEZ_THRTS": [],
                "SETTINGS": {},
                "Default_CAP_Point": 10,
                "Default_CORRIDORS_Point": 8,
                "Default_FAOR_Line": NONE,
                "Default_MEZ_THRTS_Level": NONE,
                # The whole point. Off, the page is blank; on, it is the pre-2.9.29
                # behaviour back, filtered by hiddenOnMFD as it always was. The
                # Super Hornet mod defaults to it already, and loads the Hornet's own
                # SA scripts to do it, so the E, the F and the G behave as the C does.
                #
                # The level above stays at NONE on purpose: the cartridge this was
                # measured against leaves it there and draws the rings anyway,
                # because a mirrored ring never goes through that list.
                "mirror_MEZ_THRTS": True,
                "FAOR_FLOT": {
                    "FAOR": [],
                    "FLOT": [
                        {
                            "id": f"FLOT_{number}",
                            "num": number,
                            "note": front.name[:24],
                            "points": [
                                {
                                    "id": f"FLOT_{number}_PT_{n}",
                                    "x": point[0],
                                    "y": point[1],
                                }
                                for n, point in enumerate(front.points, start=1)
                            ],
                        }
                        for number, front in enumerate(fronts, start=1)
                    ],
                },
                # The lines do go through a list, so this one has to be said.
                "Default_FLOT_Line": 1 if fronts else NONE,
            }
        }
        if navigation:
            written.update(self.navigation(navigation))
        return written


class ViperCartridge(Cartridge):
    """F-16C: the MPD.

    Its rings never stopped working, so mirroring them only keeps the page as it
    already is. The lines are what this is really for. Limits from
    ``F-16C/DTC/MPD``: twenty-five line points shared between four lines rather than
    a fixed number per line -- which is why the points carry a flag saying which line
    they belong to instead of nesting.
    """

    aircraft = "F-16C_50"
    max_lines = 4
    max_line_points = 25
    # ``MPD/NAV_PTS.lua`` numbers its steerpoints from 1 and refuses a twenty-sixth.
    first_point = 1
    last_point = 25

    @staticmethod
    def _nav_point(point: NavPoint) -> dict[str, Any]:
        """Every field ``MPD/NAV_PTS.lua`` writes when it adds one by hand."""
        number = point.number
        return {
            "number": number,
            "id": f"STPT{number}",
            "idOA1": f"OA1{number}",
            "idOA2": f"OA2{number}",
            "idOA1_Line": f"OA1{number}Line",
            "idOA2_Line": f"OA2{number}Line",
            "x": point.x,
            "y": point.y,
            "alt": point.alt_m,
            "routeAltitude": 2000,
            "speed": 790,
            "note": point.name[:24],
            # Same rule as the Hornet: the flight plan is sequence 1 and what the
            # player wrote down is sequence 2.
            "R1": point.on_route,
            "R2": not point.on_route,
            "R3": False,
            "TOS": -1,
            "isTOSEnabled": False,
            "FIX_Time": False,
            "altitudeType": 1,
            "velocityType": 3,
            "type": "STPT",
        }

    def sections(
        self, fronts: Sequence[Front], navigation: Sequence[NavPoint]
    ) -> dict[str, Any]:
        points: list[dict[str, Any]] = []
        for line, front in enumerate(fronts, start=1):
            for point in front.points:
                number = len(points) + 1
                points.append(
                    {
                        "number": number,
                        "id": f"GEO_LINES{30 + number}",
                        "x": point[0],
                        "y": point[1],
                        "alt": 0,
                        "L1": line == 1,
                        "L2": line == 2,
                        "L3": line == 3,
                        "L4": line == 4,
                        "note": front.name[:24],
                    }
                )
        mpd: dict[str, Any] = {
            "mirror_THREAT_PTS": True,
            "mirror_GEO_LINES": False,
            "GEO_LINES": points,
        }
        if navigation:
            # Same rule as the Hornet: with the mirror off the list is the navigation
            # set, so the route goes in it too.
            mpd["mirror_NAV_PTS"] = False
            mpd["NAV_PTS"] = [self._nav_point(point) for point in navigation]
        return {"MPD": mpd}


class SuperHornetCartridge(HornetCartridge):
    """The CJS mod's E/F/G, whose cartridge is the Hornet's with another type on it."""

    def __init__(self, aircraft: str) -> None:
        self.aircraft = aircraft


#: One per aircraft that can be handed any of this. An airframe missing from here
#: gets no cartridge, and the reason is always the module rather than the campaign.
#: Of everything that has a DTC -- the Hornet, the Viper, the Tomcat, the Apache, the
#: Chinook, the full-cockpit Fulcrum, and the CJS Super Hornets -- only the Hornet
#: family and the Viper keep a threat ring and a map line at all: the Tomcat and the
#: Apache carry lines but no rings, the Fulcrum and the Chinook neither. The A-10 has
#: no .dtc of any kind; its DTS database is a Lua file beside the mission
#: (``game/missiongenerator/dts.py``) and carries waypoints only. The JF-17's
#: cartridge is Deka's own, loaded from the special options tab, not one of these.
CARTRIDGES: dict[str, Cartridge] = {
    profile.aircraft: profile
    for profile in (
        HornetCartridge(),
        ViperCartridge(),
        SuperHornetCartridge("FA-18E"),
        SuperHornetCartridge("FA-18F"),
        SuperHornetCartridge("EA-18G"),
        # The mod's tanker variants are units of their own, and DCS's own DTC editor
        # lists them, so they read a cartridge like the E and the F they are.
        SuperHornetCartridge("FA-18ET"),
        SuperHornetCartridge("FA-18FT"),
    )
}


def fronts_of(theater: ConflictTheater) -> list[Front]:
    """Each front as the points that draw it, longest first.

    Two points is all a front needs: it is a straight contact line on the map already.
    Longest first because a cartridge takes a few and the one worth carrying is the
    one the fighting is on.
    """
    found: list[tuple[float, Front]] = []
    for front_line in theater.conflicts():
        bounds = FrontLineConflictDescription.frontline_bounds(front_line, theater)
        end = bounds.left_position.point_from_heading(
            bounds.heading_from_left_to_right.degrees, bounds.length
        )
        found.append(
            (
                bounds.length,
                Front(
                    front_line.name,
                    (
                        (bounds.left_position.x, bounds.left_position.y),
                        (end.x, end.y),
                    ),
                ),
            )
        )
    found.sort(key=lambda pair: -pair[0])
    return [front for _length, front in found]


def _trim(profile: Cartridge, fronts: Sequence[Front]) -> list[Front]:
    """As many fronts as this aircraft will take, and a word about the rest."""
    kept: list[Front] = []
    points = 0
    for front in fronts[: profile.max_lines]:
        if points + len(front.points) > profile.max_line_points:
            logging.info("DTC %s: no room left for %s", profile.aircraft, front.name)
            break
        kept.append(front)
        points += len(front.points)
    if len(kept) < len(fronts):
        logging.info(
            "DTC %s: %d fronts, carrying %d", profile.aircraft, len(fronts), len(kept)
        )
    return kept


def steerpoint_numbers(aircraft: str, route_length: int, count: int) -> list[int]:
    """The numbers these saved points will carry in the aircraft.

    They go in after the flight plan, so the first one is not 1: on a Hornet whose
    route is nine points it is 9, and a kneeboard that calls it 1 is a kneeboard the
    player cannot read off. An airframe with no cartridge at all is numbered as if it
    counted from 1, which is what the A-10's own database does.
    """
    profile = CARTRIDGES.get(aircraft)
    first = profile.first_point if profile is not None else 1
    last = profile.last_point if profile is not None else first + route_length + count
    numbers = list(range(first + route_length, last + 1))
    return numbers[:count]


def navigation_set(
    profile: Cartridge, route: Sequence[Any], saved: Sequence[Any]
) -> list[NavPoint]:
    """The aircraft's whole navigation set: the flight plan, then what was written
    down for it.

    Empty when there is nothing written down, and empty when the flight plan alone
    fills the module -- a truncated route is worse than the mirror this replaces, and
    a cartridge with no navigation section leaves the mirror where it was.
    """
    if not saved:
        return []
    numbers = range(profile.first_point, profile.last_point + 1)
    if len(route) > len(numbers):
        logging.info(
            "DTC %s: %d flight plan points, room for %d -- leaving navigation alone",
            profile.aircraft,
            len(route),
            len(numbers),
        )
        return []

    points = [
        NavPoint(
            number=number,
            name=waypoint.display_name,
            x=waypoint.position.x,
            y=waypoint.position.y,
            alt_m=waypoint.alt.meters,
            on_route=True,
            sequence_order=order,
        )
        for order, (number, waypoint) in enumerate(zip(numbers, route), start=1)
    ]
    free = numbers[len(route) :]
    if len(saved) > len(free):
        logging.info(
            "DTC %s: %d points written down, room for %d",
            profile.aircraft,
            len(saved),
            len(free),
        )
    for order, (number, point) in enumerate(zip(free, saved), start=1):
        points.append(
            NavPoint(
                number=number,
                name=point.name,
                x=point.x,
                y=point.y,
                alt_m=point.altitude_ft * 0.3048,
                on_route=False,
                sequence_order=order,
            )
        )
    return points


def cartridge(
    game: Game,
    player: Player,
    aircraft: str,
    name: str,
    navigation: Sequence[NavPoint] = (),
) -> dict[str, Any]:
    """One aircraft's cartridge, as the file holds it.

    Only the sections its profile fills are written. DCS merges a partial cartridge,
    so nothing here has to invent values for the radios, the countermeasures or the
    RWR.
    """
    profile = CARTRIDGES[aircraft]
    data: dict[str, Any] = {
        "name": name,
        "type": aircraft,
        "terrain": game.theater.terrain.name,
    }
    data.update(profile.sections(_trim(profile, fronts_of(game.theater)), navigation))
    return {"name": name, "type": aircraft, "data": data}


def player_aircraft(game: Game) -> set[str]:
    """The DCS types the player will be sitting in and that can take a cartridge."""
    types = set()
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count > 0:
                types.add(flight.unit_type.dcs_unit_type.id)
    return types & set(CARTRIDGES)


def cartridge_name(prefix: str, whose: str) -> str:
    """What one cartridge calls itself, which is also its file name and what the
    aircraft asks for. All three are the same string on purpose: a unit names the
    cartridge it takes, and two cartridges answering to one name is a coin toss.

    ``whose`` is the flight's callsign for the cartridges inside a mission, and the
    airframe for the copies in the DTC folder, which are per airframe because nothing
    out there knows which flight will load them.
    """
    return f"{prefix} {whose}"


def cartridges_for(game: Game, name: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Every cartridge this turn wants, keyed by the airframe it is for.

    ``name`` is the half of the name the cartridges share: the mission's own for the
    ones inside it, the campaign's for the copies in the DTC folder, which is what
    makes those findable in a list. (The ``terrain`` field is not checked at all --
    the working example says Nevada inside a Caucasus mission.)
    """
    name = name or f"Escalation {game.campaign_name or 'campaign'}"[:48]
    return {
        aircraft: cartridge(game, Player.BLUE, aircraft, cartridge_name(name, aircraft))
        for aircraft in sorted(player_aircraft(game))
    }


#: What a unit carries to say which cartridge is its own. pydcs does not serialise
#: this, so ``bind_to_units`` patches the one method that writes a flying unit out.
CARTRIDGE_ON_UNIT = "escalation_dtc_cartridge"


def teach_to_write_cartridges(unit_class: Any) -> None:
    """Make a unit class write its cartridge out, once.

    pydcs has never heard of the field, and the mission is generated over and over in
    one session, so the wrap is idempotent: a second call finds its own mark and
    leaves the class alone rather than nesting another layer on it.
    """
    if getattr(unit_class.dict, "writes_cartridges", False):
        return
    original = unit_class.dict

    def dict_with_cartridge(self: Any) -> Any:
        written = original(self)
        name = getattr(self, CARTRIDGE_ON_UNIT, None)
        if name:
            written["DTC"] = {
                "AutoLoad": True,
                "Cartridges": [{"name": name, "default": True}],
            }
        return written

    dict_with_cartridge.writes_cartridges = True  # type: ignore[attr-defined]
    unit_class.dict = dict_with_cartridge


def cartridges_of(mission_data: Any) -> list[Any]:
    """The flights that get a cartridge: crewed, and of an airframe that takes one.

    One per flight rather than one per airframe, because what goes in it is the
    flight's own -- its route, and the points written down for it.
    """
    found = []
    for flight in getattr(mission_data, "flights", []):
        if not flight.client_units:
            continue
        if flight.aircraft_type.dcs_unit_type.id not in CARTRIDGES:
            continue
        found.append(flight)
    return found


def bind_to_units(mission_data: Any, prefix: str) -> int:
    """Give every crewed aircraft the name of its own cartridge.

    A cartridge in the .miz is only on the shelf; the mission editor writes a ``DTC``
    table onto each unit naming the one it takes, and without it nothing is read. The
    ``dict`` method of a flying unit is where that has to appear, and pydcs has never
    heard of the field, so it is wrapped once -- a unit told which cartridge is its
    own writes it out, every other unit is untouched.
    """
    from dcs.flyingunit import FlyingUnit

    teach_to_write_cartridges(FlyingUnit)

    bound = 0
    for flight in cartridges_of(mission_data):
        name = cartridge_name(prefix, flight.callsign)
        for unit in flight.client_units:
            setattr(unit, CARTRIDGE_ON_UNIT, name)
            bound += 1
    return bound


def write_into_mission(game: Game, mission_data: Any, mission: Path) -> list[str]:
    """Put the cartridges inside the .miz, where the aircraft finds them itself.

    A cartridge the player has to go and load is an errand rather than a feature. The
    entries go in a ``DTC`` folder inside the .miz, one per crewed flight, each under
    the name its units were bound to by ``bind_to_units``.
    """
    entries: dict[str, dict[str, Any]] = {}
    for flight in cartridges_of(mission_data):
        aircraft = flight.aircraft_type.dcs_unit_type.id
        name = cartridge_name(mission.stem, flight.callsign)
        card = cartridge(
            game,
            Player.BLUE,
            aircraft,
            name,
            navigation_set(CARTRIDGES[aircraft], flight.waypoints, flight.saved_points),
        )
        entries[f"DTC/{name}.dtc"] = card
    if not entries:
        return []

    try:
        with zipfile.ZipFile(mission, "a", zipfile.ZIP_DEFLATED) as archive:
            for path, card in entries.items():
                archive.writestr(path, json.dumps(card, indent=1))
    except OSError:
        logging.exception("Could not put the cartridges in %s", mission)
        return []
    logging.info("Put %d cartridge(s) in %s", len(entries), mission.name)
    return sorted(entries)


def write_cartridges(game: Game, into: Path) -> list[Path]:
    """A copy per player airframe in the DTC folder, replacing last turn's.

    The mission carries its own; this is the one the player can load by hand, named
    for the campaign rather than the turn so the DTC page does not fill with dead
    ones.
    """
    written = []
    into.mkdir(parents=True, exist_ok=True)
    for card in cartridges_for(game).values():
        path = into / f"{card['name']}.dtc"
        try:
            path.write_text(json.dumps(card, indent=1), encoding="utf-8")
        except OSError:
            logging.exception("Could not write the data cartridge %s", path)
            continue
        written.append(path)
        logging.info("Wrote the data cartridge %s", path)
    return written
