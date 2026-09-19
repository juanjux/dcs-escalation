"""The data cartridge the player loads in the cockpit.

An aircraft's displays draw two things the campaign already knows: a ring round every
threat it has been told about, and the forward line of own troops. Neither comes from
the mission. ``hiddenOnMFD`` can take a contact off a display but it cannot put one
on, so with nothing detected there is nothing to hide and the page stays empty. What
puts them there is the **data transfer cartridge**: the .dtc file the DTC page of the
rearm window loads.

The file is JSON, it lives in ``Saved Games/DCS/DTC``, and a partial one is valid --
DCS ships its own defaults as files with a single section -- so this writes only what
it fills.

Every module keeps that data somewhere different, under its own limits, so each is a
:class:`Cartridge` of its own. The campaign works out the threats and the fronts once;
a cartridge says where they go in its aircraft and how many it will take. The shapes,
the names and the limits are all read off DCS's own ``CoreMods/aircraft/<type>/DTC``,
and a test checks them against those files whenever DCS is installed.

Which threats go in is the same question the cockpit displays already answer, so the
same settings decide: a site the campaign will not show is not one the cartridge names
either.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from game.mfd import shows_on_mfd
from game.missiongenerator.frontlineconflictdescription import (
    FrontLineConflictDescription,
)
from game.theater import Player
from game.theater.theatergroundobject import IadsGroundObject, NavalGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater import ConflictTheater, TheaterGroundObject

#: What the displays call each system, keyed by the DCS unit that identifies the site.
#: The names have to be exactly the ones in the module's own threat list -- the Hornet
#: and the Viper ship the same one -- and a site made of anything else is written as a
#: Custom ring, which is drawn just the same.
THREAT_BY_UNIT: dict[str, tuple[str, str]] = {
    "SNR_75V": ("SAM SA-2 'Guideline'", "2"),
    "snr s-125 tr": ("SAM SA-3 'Goa'", "3"),
    "Kub 1S91 str": ("SAM SA-6 'Gainful'", "6"),
    "Osa 9A33 ln": ("SAM SA-8 'Gecko'", "8"),
    "Strela-1 9P31": ("SAM SA-9 'Gaskin'", "9"),
    "S-300PS 40B6M tr": ("SAM SA-10 'Grumble'", "10"),
    "S-300PS 64H6E sr": ("SAM SA-10 'Grumble'", "10"),
    "SA-11 Buk SR 9S18M1": ("SAM SA-11 'Gadfly'", "11"),
    "Strela-10M3": ("SAM SA-13 'Gopher'", "13"),
    "Tor 9A331": ("SAM SA-15 'Gauntlet'", "15"),
    "2S6 Tunguska": ("SAM SA-19 'Grison'", "19"),
    "HQ-7_STR_SP": ("SAM HQ-7", "7"),
    "Patriot str": ("SAM Patriot", "P"),
    "Hawk tr": ("SAM Hawk", "HK"),
    "NASAMS_Radar_MPQ64F1": ("SAM NASAMS", "NS"),
    "Roland Radar": ("SAM Roland", "RO"),
    "rapier_fsa_blindfire_radar": ("SAM Rapier", "RP"),
    "Gepard": ("SPAAA Gepard", "A"),
    "Vulcan": ("SPAAA Vulcan", "A"),
    "ZSU-23-4 Shilka": ("SPAAA ZSU-23-4", "A"),
    "ZSU_57_2": ("SPAAA ZSU-57-2", "A"),
    "SON_9": ("AAA SON-9 - Fire Can", "FC"),
}

CUSTOM = "Custom"


@dataclass(frozen=True)
class Threat:
    """One ring, in the campaign's own terms rather than any aircraft's."""

    name: str
    kind: str
    text: str
    radius_nm: float
    x: float
    y: float


@dataclass(frozen=True)
class Front:
    """One contact line, as the points that draw it."""

    name: str
    points: tuple[tuple[float, float], ...]


class Cartridge(ABC):
    """What one aircraft's cartridge will carry, and where it keeps it."""

    #: The DCS unit type this is the cartridge for.
    aircraft: str

    #: How many the module itself allows. Read off its DTC scripts, not decided here.
    max_threats: int
    max_lines: int
    max_line_points: int

    @abstractmethod
    def sections(
        self, threats: Sequence[Threat], fronts: Sequence[Front]
    ) -> dict[str, Any]:
        """The part of the cartridge's ``data`` tree this aircraft fills."""


class HornetCartridge(Cartridge):
    """F/A-18C: rings and lines live on the SA page.

    Limits from ``FA-18C/DTC/SA``: forty threats, three FLOT lines of seven points.
    """

    aircraft = "FA-18C_hornet"
    max_threats = 40
    max_lines = 3
    max_line_points = 7

    def sections(
        self, threats: Sequence[Threat], fronts: Sequence[Front]
    ) -> dict[str, Any]:
        return {
            "SA": {
                "MEZ_THRTS": [
                    {
                        "id": f"MEZ_THRTS_{number}",
                        "num": number,
                        "x": threat.x,
                        "y": threat.y,
                        "text": threat.text,
                        "threat_type": threat.kind,
                        "threat_ring_radius": round(threat.radius_nm, 1),
                        "threat_level": 1,
                    }
                    for number, threat in enumerate(threats, start=1)
                ],
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
            }
        }


#: The Viper names a threat by its place in its own list as well as by name, and
#: carries a ceiling for it. Both are ED's, from ``F-16C/DTC/MPD/THREAT_PTS_defs.lua``.
VIPER_THREAT_DEFS: dict[str, tuple[int, int]] = {
    CUSTOM: (1, 9144),
    "AAA SON-9 - Fire Can": (2, 14000),
    "SAM Hawk": (6, 20000),
    "SAM HQ-7": (7, 5500),
    "SAM NASAMS": (9, 17000),
    "SAM Patriot": (10, 160000),
    "SAM Rapier": (11, 4000),
    "SAM Roland": (12, 6000),
    "SAM SA-2 'Guideline'": (13, 25000),
    "SAM SA-3 'Goa'": (14, 20000),
    "SAM SA-6 'Gainful'": (16, 14000),
    "SAM SA-8 'Gecko'": (17, 5000),
    "SAM SA-9 'Gaskin'": (18, 5000),
    "SAM SA-10 'Grumble'": (19, 27000),
    "SAM SA-11 'Gadfly'": (20, 22000),
    "SAM SA-13 'Gopher'": (21, 3500),
    "SAM SA-15 'Gauntlet'": (22, 8000),
    "SAM SA-19 'Grison'": (24, 3500),
    "SPAAA Gepard": (26, 3000),
    "SPAAA Vulcan": (27, 5000),
    "SPAAA ZSU-23-4": (28, 2500),
    "SPAAA ZSU-57-2": (29, 7000),
}


class ViperCartridge(Cartridge):
    """F-16C: rings and lines live on the MPD.

    Limits from ``F-16C/DTC/MPD``: fifteen threat points, and twenty-five line points
    shared between four lines rather than a fixed number per line -- which is why the
    points carry a flag saying which line they belong to instead of nesting.
    """

    aircraft = "F-16C_50"
    max_threats = 15
    max_lines = 4
    max_line_points = 25

    def sections(
        self, threats: Sequence[Threat], fronts: Sequence[Front]
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
        return {
            "MPD": {
                "THREAT_PTS": [
                    {
                        "number": number,
                        "id": f"THREAT_PTS{55 + number}",
                        "x": threat.x,
                        "y": threat.y,
                        "threatName": threat.kind,
                        # Metres here, where the Hornet's is in miles. Each module
                        # asks for what it asks for.
                        "radius": round(threat.radius_nm * 1852),
                        "alt": VIPER_THREAT_DEFS.get(
                            threat.kind, VIPER_THREAT_DEFS[CUSTOM]
                        )[1],
                        "elev": 0,
                        "text": threat.text,
                        "ring": True,
                        "def_num": VIPER_THREAT_DEFS.get(
                            threat.kind, VIPER_THREAT_DEFS[CUSTOM]
                        )[0],
                    }
                    for number, threat in enumerate(threats, start=1)
                ],
                "GEO_LINES": points,
            }
        }


#: One per aircraft that can be handed any of this. An airframe missing from here
#: gets no cartridge: it is not that the campaign will not write one, it is that its
#: module has nowhere to put a threat ring or a line.
CARTRIDGES: dict[str, Cartridge] = {
    profile.aircraft: profile for profile in (HornetCartridge(), ViperCartridge())
}


def _identify(tgo: TheaterGroundObject) -> tuple[str, str]:
    """What to call this site, from the units still alive in it.

    Only a group that does most of the shooting may name it. An S-300 battery with a
    Strela parked beside it went on the page as a Strela, which is the one thing the
    ring's radius says it is not; and a system DCS has no entry for -- an HQ-9, a mod
    -- is better drawn as a Custom ring at its measured radius than under a wrong
    name.
    """
    reach = max((g.max_threat_range().meters for g in tgo.groups), default=0.0)
    groups = [g for g in tgo.groups if g.max_threat_range().meters >= reach * 0.8]
    groups.sort(key=lambda g: -g.max_threat_range().meters)
    for group in groups:
        for unit in group.units:
            if not unit.alive or unit.unit_type is None:
                continue
            known = THREAT_BY_UNIT.get(unit.unit_type.dcs_id)
            if known is not None:
                return known
    label = "SH" if isinstance(tgo, NavalGroundObject) else tgo.name[:2].upper()
    return CUSTOM, label


def threats_for(game: Game, player: Player) -> list[Threat]:
    """The enemy air defence the campaign is willing to put on the displays.

    ``shows_on_mfd`` is the same question the mission asks before it decides whether
    to hide a site's units, so the ring and the symbol agree: turn a band off in the
    settings and it leaves both. Biggest first, because a cartridge holds a limited
    number and what should fall off the end is the AAA nobody plans around.
    """
    found: list[Threat] = []
    for control_point in game.theater.controlpoints:
        if control_point.captured == player:
            continue
        for tgo in control_point.ground_objects:
            if not isinstance(tgo, (IadsGroundObject, NavalGroundObject)):
                continue
            if tgo.is_dead or not shows_on_mfd(tgo, game.settings):
                continue
            radius = max(
                (group.max_threat_range().nautical_miles for group in tgo.groups),
                default=0.0,
            )
            if radius <= 0:
                continue
            kind, text = _identify(tgo)
            found.append(
                Threat(tgo.name, kind, text, radius, tgo.position.x, tgo.position.y)
            )
    found.sort(key=lambda threat: (-threat.radius_nm, threat.name))
    return found


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


def _trim(
    profile: Cartridge, threats: Sequence[Threat], fronts: Sequence[Front]
) -> tuple[list[Threat], list[Front]]:
    """As much of it as this aircraft will take, and a word about the rest."""
    if len(threats) > profile.max_threats:
        logging.info(
            "DTC %s: %d threats, carrying the %d largest",
            profile.aircraft,
            len(threats),
            profile.max_threats,
        )
    kept_threats = list(threats[: profile.max_threats])

    kept_fronts: list[Front] = []
    points = 0
    for front in fronts[: profile.max_lines]:
        if points + len(front.points) > profile.max_line_points:
            logging.info("DTC %s: no room left for %s", profile.aircraft, front.name)
            break
        kept_fronts.append(front)
        points += len(front.points)
    if len(kept_fronts) < len(fronts):
        logging.info(
            "DTC %s: %d fronts, carrying %d",
            profile.aircraft,
            len(fronts),
            len(kept_fronts),
        )
    return kept_threats, kept_fronts


def cartridge(game: Game, player: Player, aircraft: str, name: str) -> dict[str, Any]:
    """One aircraft's cartridge, as the file holds it.

    Only the sections its profile fills are written. DCS merges a partial cartridge,
    so nothing here has to invent values for the radios, the countermeasures or the
    RWR.
    """
    profile = CARTRIDGES[aircraft]
    threats, fronts = _trim(profile, threats_for(game, player), fronts_of(game.theater))
    data: dict[str, Any] = {
        "name": name,
        "type": aircraft,
        "terrain": game.theater.terrain.name,
    }
    data.update(profile.sections(threats, fronts))
    return {"name": name, "type": aircraft, "data": data}


def player_aircraft(game: Game) -> set[str]:
    """The DCS types the player will be sitting in and that can take a cartridge."""
    types = set()
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count > 0:
                types.add(flight.unit_type.dcs_unit_type.id)
    return types & set(CARTRIDGES)


def write_cartridges(game: Game, into: Path) -> list[Path]:
    """A cartridge per player airframe, replacing last turn's.

    Named for the campaign rather than the turn: the DTC page lists what is in the
    folder, and a new file per turn would leave a list of dead ones to scroll past.
    """
    written = []
    into.mkdir(parents=True, exist_ok=True)
    for aircraft in sorted(player_aircraft(game)):
        name = f"Escalation {game.campaign_name or 'campaign'}"[:48]
        path = into / f"{name} {aircraft}.dtc"
        try:
            path.write_text(
                json.dumps(cartridge(game, Player.BLUE, aircraft, name), indent=1),
                encoding="utf-8",
            )
        except OSError:
            logging.exception("Could not write the data cartridge %s", path)
            continue
        written.append(path)
        logging.info("Wrote the data cartridge %s", path)
    return written
