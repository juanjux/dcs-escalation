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


class Cartridge(ABC):
    """What one aircraft's cartridge will carry, and where it keeps it."""

    #: The DCS unit type this is the cartridge for.
    aircraft: str

    #: How many lines the module itself allows, and of how many points. Read off its
    #: DTC scripts, not decided here.
    max_lines: int
    max_line_points: int

    @abstractmethod
    def sections(self, fronts: Sequence[Front]) -> dict[str, Any]:
        """The part of the cartridge's ``data`` tree this aircraft fills."""


class HornetCartridge(Cartridge):
    """The Hornet family: the SA page.

    Limits from ``FA-18C/DTC/SA``: three FLOT lines of seven points. The CJS Super
    Hornet mod ships the same cartridge, section for section, for the E, the F and
    the Growler, so they are the same profile under another type name.
    """

    aircraft = "FA-18C_hornet"
    max_lines = 3
    max_line_points = 7

    def sections(self, fronts: Sequence[Front]) -> dict[str, Any]:
        return {
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

    def sections(self, fronts: Sequence[Front]) -> dict[str, Any]:
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
        return {
            "MPD": {
                "mirror_THREAT_PTS": True,
                "mirror_GEO_LINES": False,
                "GEO_LINES": points,
            }
        }


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


def cartridge(game: Game, player: Player, aircraft: str, name: str) -> dict[str, Any]:
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
    data.update(profile.sections(_trim(profile, fronts_of(game.theater))))
    return {"name": name, "type": aircraft, "data": data}


def player_aircraft(game: Game) -> set[str]:
    """The DCS types the player will be sitting in and that can take a cartridge."""
    types = set()
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count > 0:
                types.add(flight.unit_type.dcs_unit_type.id)
    return types & set(CARTRIDGES)


def cartridges_for(game: Game, name: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Every cartridge this turn wants, keyed by the airframe it is for.

    ``name`` is what the cartridge calls itself. The one inside the mission is named
    for the mission, which is what a cartridge that works carries; the copy in the
    DTC folder is named for the campaign, which is what makes it findable in a list.
    (The ``terrain`` field is not checked at all -- the working example says Nevada
    inside a Caucasus mission.)
    """
    name = name or f"Escalation {game.campaign_name or 'campaign'}"[:48]
    return {
        aircraft: cartridge(game, Player.BLUE, aircraft, name)
        for aircraft in sorted(player_aircraft(game))
    }


def busiest_airframe(game: Game) -> Optional[str]:
    """The one the most seats are in this turn, for the cartridge that gets the
    mission's own name."""
    seats: dict[str, int] = {}
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count <= 0:
                continue
            aircraft = flight.unit_type.dcs_unit_type.id
            if aircraft in CARTRIDGES:
                seats[aircraft] = seats.get(aircraft, 0) + flight.client_count
    if not seats:
        return None
    return max(sorted(seats), key=lambda aircraft: seats[aircraft])


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


def bind_to_units(mission: Any, name: str) -> int:
    """Give every aircraft that can take a cartridge the name of its own.

    A cartridge in the .miz is only on the shelf; the mission editor writes a ``DTC``
    table onto each unit naming the one it takes, and without it nothing is read. The
    ``dict`` method of a flying unit is where that has to appear, and pydcs has never
    heard of the field, so it is wrapped once -- a unit told which cartridge is its
    own writes it out, every other unit is untouched.
    """
    from dcs.flyingunit import FlyingUnit

    teach_to_write_cartridges(FlyingUnit)

    bound = 0
    for coalition in mission.coalition.values():
        for country in coalition.countries.values():
            for group in list(country.plane_group) + list(country.helicopter_group):
                for unit in group.units:
                    if not unit.is_human():
                        continue
                    if unit.type not in CARTRIDGES:
                        continue
                    setattr(unit, CARTRIDGE_ON_UNIT, name)
                    bound += 1
    return bound


def write_into_mission(game: Game, mission: Path) -> list[str]:
    """Put the cartridges inside the .miz, where the aircraft finds them itself.

    A cartridge the player has to go and load is an errand rather than a feature. The
    entry goes in a ``DTC`` folder inside the .miz and nothing in the mission Lua
    points at it. One is named for the mission itself, which is the shape a working
    example uses, and it is given to whichever airframe has the most seats in it this
    turn; the rest are named for their aircraft beside it. Belt and braces, because
    which of the two rules DCS actually follows is not written down anywhere and a
    spare entry costs a few kilobytes.
    """
    cartridges = cartridges_for(game, name=mission.stem)
    if not cartridges:
        return []
    busiest = busiest_airframe(game)
    entries: dict[str, dict[str, Any]] = {
        f"DTC/{mission.stem} {aircraft}.dtc": card
        for aircraft, card in cartridges.items()
    }
    if busiest is not None:
        entries[f"DTC/{mission.stem}.dtc"] = cartridges[busiest]

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
    for aircraft, card in cartridges_for(game).items():
        path = into / f"{card['name']} {aircraft}.dtc"
        try:
            path.write_text(json.dumps(card, indent=1), encoding="utf-8")
        except OSError:
            logging.exception("Could not write the data cartridge %s", path)
            continue
        written.append(path)
        logging.info("Wrote the data cartridge %s", path)
    return written
