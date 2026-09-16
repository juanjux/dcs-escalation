"""Which air-defence sites the cockpit displays are allowed to show.

DCS paints a threat ring on the Hornet's SA page for every enemy air-defence group it
is not told to hide, whether or not anything has seen it. That is a lot of intelligence
for free, so the campaign decides instead: a site is worth showing when a satellite
would have found it and it is still where it was found.

The two questions that decides it are how far the site shoots and whether it can shoot
from where it drives. An emplaced battery does not move between turns, so knowing where
it is costs nothing; a TELAR does, and yesterday's picture of it may be a picture of an
empty field.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Iterator, Optional

from game.data.units import UnitClass
from game.utils import Distance, meters, nautical_miles

if TYPE_CHECKING:
    from game.settings import Settings
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterUnit


class MfdIntel(Enum):
    """How much the cockpit is told about one band of mobile air defence.

    The values are the save format: renaming one of them breaks a campaign in
    progress, so they are spelled out rather than auto-numbered.
    """

    #: Never on the displays. It has to be found in the air.
    NEVER = "never"

    #: Always on the displays, wherever it is right now.
    CURRENT = "current"

    #: On the displays only where it was at the start of the turn. A site that has
    #: moved, or one that was put up after the picture was taken, is not on it.
    LAST_TURN = "last-turn"


class Band(Enum):
    """How far a site shoots, in the words the rest of the game uses."""

    LONG = "long"
    MEDIUM = "medium"
    SHORT = "short"


#: Where one band ends and the next begins. Read off the game's own preset groups:
#: Patriot and the S-300 families are the only ones the campaigns call long range,
#: and the shortest thing they call medium is a NASAMS at 15 km.
LONG_RANGE_FROM: Distance = nautical_miles(30)
MEDIUM_RANGE_FROM: Distance = nautical_miles(7)


#: Systems that shoot from where they drive: a TELAR, a self-propelled gun or a man
#: with a launcher on his shoulder. Everything else is emplaced or towed, and takes
#: long enough to set up that a satellite picture of it stays true.
#:
#: Keyed by DCS type id. A type that is not listed -- a mod, mostly -- is read off its
#: unit class instead, which gets the TELARs and the SHORADs right.
MOBILE_SYSTEMS = frozenset(
    {
        # Soviet and Russian
        "Kub 2P25 ln",
        "SA-11 Buk LN 9A310M1",
        "Osa 9A33 ln",
        "Tor 9A331",
        "Strela-1 9P31",
        "Strela-10M3",
        "2S6 Tunguska",
        "ZSU-23-4 Shilka",
        "ZSU_57_2",
        "Ural-375 ZU-23",
        "Ural-375 ZU-23 Insurgent",
        "HL_ZU-23",
        "tt_ZU-23",
        "ZU-23 Insurgent",
        "SA-18 Igla manpad",
        "SA-18 Igla-S manpad",
        "Igla manpad INS",
        # Western
        "M48 Chaparral",
        "M6 Linebacker",
        "M1097 Avenger",
        "Vulcan",
        "Gepard",
        "Roland ADS",
        "HEMTT_C-RAM_Phalanx",
        "Soldier stinger",
        "CHAP_IRISTSLM_LN",
        # Chinese
        "HQ-7_LN_SP",
        # Current Hill mods that carry their own radar
        "CHAP_PantsirS1",
        "CHAP_TorM2",
    }
)

#: Unit classes that are mobile whatever the type is, for the mods not named above.
MOBILE_CLASSES = frozenset({UnitClass.TELAR, UnitClass.SHORAD, UnitClass.MANPAD})

#: Guns are short range whatever their ceiling says: a KS-19 reaches 20 km straight up
#: and is still a gun emplacement, not a missile site.
GUN_CLASSES = frozenset({UnitClass.AAA, UnitClass.SEARCH_LIGHT})


def _shooters(ground_object: TheaterGroundObject) -> Iterator[TheaterUnit]:
    for unit in ground_object.units:
        if unit.threat_range.meters > 0 or _class_of(unit) in GUN_CLASSES:
            yield unit


def _class_of(unit: TheaterUnit) -> Optional[UnitClass]:
    unit_type = unit.unit_type
    return getattr(unit_type, "unit_class", None) if unit_type is not None else None


def is_mobile(ground_object: TheaterGroundObject) -> bool:
    """Whether what is parked here can shoot from where it drives.

    Asked of every unit that shoots: a site is only mobile if all of them are, so a
    Hawk battery with a Linebacker guarding it is still an emplaced battery.
    """
    shooters = list(_shooters(ground_object))
    if not shooters:
        return False
    return all(
        unit.type.id in MOBILE_SYSTEMS or _class_of(unit) in MOBILE_CLASSES
        for unit in shooters
    )


def band_of(ground_object: TheaterGroundObject) -> Band:
    """Which of the three bands this site belongs to."""
    shooters = list(_shooters(ground_object))
    if shooters and all(_class_of(unit) in GUN_CLASSES for unit in shooters):
        return Band.SHORT

    reach = max((unit.threat_range for unit in shooters), default=meters(0))
    if reach >= LONG_RANGE_FROM:
        return Band.LONG
    if reach >= MEDIUM_RANGE_FROM:
        return Band.MEDIUM
    return Band.SHORT


def _setting_for(settings: Settings, band: Band, mobile: bool) -> Any:
    if mobile:
        return {
            Band.LONG: settings.mfd_mobile_long,
            Band.MEDIUM: settings.mfd_mobile_medium,
            Band.SHORT: settings.mfd_mobile_short,
        }[band]
    return {
        Band.LONG: settings.mfd_static_long,
        Band.MEDIUM: settings.mfd_static_medium,
        Band.SHORT: settings.mfd_static_short,
    }[band]


def campaign_shows(ground_object: TheaterGroundObject, settings: Settings) -> bool:
    """What the campaign settings say about this site, before any player choice."""
    mobile = is_mobile(ground_object)
    choice = _setting_for(settings, band_of(ground_object), mobile)
    if isinstance(choice, bool):
        return choice
    if choice is MfdIntel.NEVER:
        return False
    if choice is MfdIntel.CURRENT:
        return True
    # Last turn: only where the picture was taken, and only if it is still true.
    seen = getattr(ground_object, "mfd_seen_at", None)
    if seen is None:
        return False
    return bool(seen.distance_to_point(ground_object.position) < 1)


def shows_on_mfd(ground_object: TheaterGroundObject, settings: Settings) -> bool:
    """Whether this site is drawn on the cockpit displays.

    The player's own choice for the site wins; with no choice made, the campaign
    settings decide, so changing them moves every site that was left alone.
    """
    chosen = getattr(ground_object, "hide_on_mfd", None)
    if chosen is not None:
        return not chosen
    return campaign_shows(ground_object, settings)


def remember_positions(ground_objects: Iterator[TheaterGroundObject]) -> None:
    """Take the satellite picture: where every site is as the turn starts."""
    for ground_object in ground_objects:
        ground_object.mfd_seen_at = ground_object.position
