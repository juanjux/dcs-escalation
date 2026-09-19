"""The data cartridge the player loads in the cockpit.

The Hornet's SA page draws two things the map already knows: a ring round every threat
it has been told about, and the forward line of own troops. Neither comes from the
mission -- ``hiddenOnMFD`` decides whether a unit's own symbol is drawn, and nothing
else in a .miz reaches that page. Both come from the aircraft's **data transfer
cartridge**, the .dtc file the DTC page in the rearm window loads, so a campaign that
wants them on the page has to write one.

The file is JSON, it lives in ``Saved Games/DCS/DTC``, and a partial one is valid: DCS
merges what it finds, so this writes only the two sections it fills. The shapes below
are read off DCS's own ``CoreMods/aircraft/FA-18C/DTC``, including the limits -- forty
threats, three lines of seven points -- which are the module's, not ours.

Which threats go in is the same question the cockpit displays already answer, so the
same settings decide: a site the campaign will not show on the SA page is not one the
cartridge names either.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

from game.mfd import shows_on_mfd
from game.missiongenerator.frontlineconflictdescription import (
    FrontLineConflictDescription,
)
from game.theater import Player
from game.theater.theatergroundobject import IadsGroundObject, NavalGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater import ConflictTheater, TheaterGroundObject

#: DCS's own ceilings, from SA/MEZ_THRTS.lua and SA/FAOR_FLOT.lua.
MAX_THREATS = 40
MAX_FLOT_LINES = 3
MAX_LINE_POINTS = 7

#: What the SA page calls each system, keyed by the DCS unit that identifies the site.
#: The names have to be exactly the ones in ``SA/MEZ_THRTS_defs.lua``; a site made of
#: anything else is written as a Custom ring, which is drawn just the same.
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

#: Aircraft whose cartridge this knows how to write. The sections are per-module: the
#: Viper's cartridge has no SA page in it, so it needs its own profile rather than a
#: copy of this one.
SUPPORTED_AIRCRAFT = {"FA-18C_hornet"}


@dataclass(frozen=True)
class Threat:
    """One ring on the SA page."""

    name: str
    kind: str
    text: str
    radius_nm: float
    x: float
    y: float

    def as_dtc(self, number: int) -> dict[str, object]:
        return {
            "id": f"MEZ_THRTS_{number}",
            "num": number,
            "x": self.x,
            "y": self.y,
            "text": self.text,
            "threat_type": self.kind,
            "threat_ring_radius": round(self.radius_nm, 1),
            "threat_level": 1,
        }


def _identify(tgo: TheaterGroundObject) -> tuple[str, str]:
    """What to call this site, from the units still alive in it.

    Longest-reaching group first, because that is the ring being drawn: an S-300
    battery with a Strela parked beside it went on the page as a Strela, which is
    the one thing the ring's radius says it is not.
    """
    reach = max((g.max_threat_range().meters for g in tgo.groups), default=0.0)
    # Only a group that does most of the shooting may name the site. An S-300
    # battery with a Strela parked beside it went on the page as a Strela, which is
    # the one thing the ring's radius says it is not; and a system DCS has no entry
    # for -- an HQ-9, a mod -- is better drawn as a Custom ring at its real radius
    # than as whatever short-range escort happens to be recognised.
    groups = [g for g in tgo.groups if g.max_threat_range().meters >= reach * 0.8]
    groups.sort(key=lambda g: -g.max_threat_range().meters)
    for group in groups:
        for unit in group.units:
            if not unit.alive or unit.unit_type is None:
                continue
            known = THREAT_BY_UNIT.get(unit.unit_type.dcs_id)
            if known is not None:
                return known
    # Anything unrecognised -- a mod, a ship, a type DCS has no entry for -- still
    # gets its ring, drawn at the radius the campaign measured.
    label = "SH" if isinstance(tgo, NavalGroundObject) else tgo.name[:2].upper()
    return "Custom", label


def _radius_nm(tgo: TheaterGroundObject) -> float:
    ranges = [group.max_threat_range().nautical_miles for group in tgo.groups]
    return max(ranges, default=0.0)


def threats_for(game: Game, player: Player) -> list[Threat]:
    """The enemy air defence the campaign is willing to put on the SA page.

    ``shows_on_mfd`` is the same question the mission asks before it decides whether
    to hide a site's units, so the ring and the symbol agree: turn a band off in the
    settings and it leaves both.
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
            radius = _radius_nm(tgo)
            if radius <= 0:
                continue
            kind, text = _identify(tgo)
            found.append(
                Threat(tgo.name, kind, text, radius, tgo.position.x, tgo.position.y)
            )
    # Biggest first: the forty the cartridge holds should be the forty that matter,
    # and what falls off the end is the AAA nobody plans around.
    found.sort(key=lambda threat: (-threat.radius_nm, threat.name))
    if len(found) > MAX_THREATS:
        logging.info(
            "DTC: %d threats found, writing the %d largest",
            len(found),
            MAX_THREATS,
        )
    return found[:MAX_THREATS]


def flot_lines(theater: ConflictTheater) -> list[dict[str, object]]:
    """Each front as a line, in the cartridge's own shape.

    Two points is all a front needs -- it is drawn as a straight contact line on the
    map already -- and the cartridge holds three lines, so a theatre with more fronts
    than that sends the longest.
    """
    fronts = []
    for front_line in theater.conflicts():
        bounds = FrontLineConflictDescription.frontline_bounds(front_line, theater)
        end = bounds.left_position.point_from_heading(
            bounds.heading_from_left_to_right.degrees, bounds.length
        )
        fronts.append((bounds.length, front_line.name, bounds.left_position, end))
    fronts.sort(key=lambda front: -front[0])
    if len(fronts) > MAX_FLOT_LINES:
        logging.info(
            "DTC: %d fronts, writing the %d longest", len(fronts), MAX_FLOT_LINES
        )

    lines = []
    for number, (_length, name, left, right) in enumerate(
        fronts[:MAX_FLOT_LINES], start=1
    ):
        lines.append(
            {
                "id": f"FLOT_{number}",
                "num": number,
                "note": name[:24],
                "points": [
                    {"id": f"FLOT_{number}_PT_1", "x": left.x, "y": left.y},
                    {"id": f"FLOT_{number}_PT_2", "x": right.x, "y": right.y},
                ],
            }
        )
    return lines


def cartridge(
    game: Game, player: Player, aircraft: str, name: str
) -> dict[str, object]:
    """One aircraft's cartridge, as the file holds it.

    Only the sections this fills are written. DCS merges a partial cartridge -- its
    own defaults ship as files with a single section -- so nothing here has to invent
    values for the radios, the countermeasures or the RWR.
    """
    threats = [
        threat.as_dtc(number)
        for number, threat in enumerate(threats_for(game, player), start=1)
    ]
    return {
        "name": name,
        "type": aircraft,
        "data": {
            "name": name,
            "type": aircraft,
            "terrain": game.theater.terrain.name,
            "SA": {
                "MEZ_THRTS": threats,
                "FAOR_FLOT": {"FAOR": [], "FLOT": flot_lines(game.theater)},
            },
        },
    }


def player_aircraft(game: Game) -> set[str]:
    """The DCS types the player will actually be sitting in this turn."""
    types = set()
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if flight.client_count > 0:
                types.add(flight.unit_type.dcs_unit_type.id)
    return types & SUPPORTED_AIRCRAFT


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
