"""How the High Command's lines name things: systems, units, lists and money."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, Sequence

from game.data.units import UnitClass
from game.mfd import GUN_CLASSES

if TYPE_CHECKING:
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterUnit

#: How many names a line gives before it counts the rest.
NAMES_SHOWN = 2

#: The designations the unit names carry, SA-10 or HQ-7 or SS-N-2.
_DESIGNATION = re.compile(r"\b(SA-\d+[A-Z]?|HQ-\d+[A-Z]?|SS-[NC]-\d+)\b")

#: Systems known by name rather than by designation, as the unit names spell them.
_SYSTEMS = (
    "Patriot",
    "Hawk",
    "NASAMS",
    "Roland",
    "Rapier",
    "IRIS-T",
    "Crotale",
    "Chaparral",
    "Avenger",
    "Gepard",
    "Tunguska",
    "Pantsir",
    "SAMP/T",
    "Skyshield",
    "Silkworm",
    "Stinger",
    "Igla",
    "Vulcan",
    "Shilka",
    "ZSU-57",
    "ZU-23",
    "Bofors",
)

#: What a launcher that fires at ships or ground targets is, for the sites whose
#: point is not their anti-aircraft guns.
LAUNCHER_CLASSES = (UnitClass.ANTISHIP_MISSILE, UnitClass.MISSILE)


def system_name(tgo: TheaterGroundObject) -> str:
    """What the site's main weapon is called: its designation when it has one."""
    units = alive([tgo])
    if not units:
        return "site"
    main = max(units, key=lambda unit: unit.threat_range.meters)
    if main.threat_range.meters <= 0:
        # Nothing here shoots at aircraft; a coastal battery's launcher is what it
        # is about.
        main = next(
            (unit for unit in units if unit_class(unit) in LAUNCHER_CLASSES), main
        )
    return unit_system(main)


def site_name(tgo: TheaterGroundObject) -> str:
    """What the site is. A GPS jammer is what its site is for, while it stands, and
    never what shoots there: naming the site after its main weapon calls it after the
    guns guarding it."""
    if any(getattr(unit.unit_type, "gps_jamming", None) for unit in alive([tgo])):
        return "GPS jammer"
    return system_name(tgo)


def unit_system(unit: TheaterUnit) -> str:
    """What one unit's system is called."""
    label = unit_label(unit)
    found = _DESIGNATION.search(label)
    if found:
        return found.group(1)
    for system in _SYSTEMS:
        if system in label:
            return system
    if unit_class(unit) in GUN_CLASSES:
        return "guns"
    return label


def unit_class(unit: TheaterUnit) -> UnitClass | None:
    return getattr(unit.unit_type, "unit_class", None)


def unit_label(unit: TheaterUnit) -> str:
    return str(unit.unit_type) if unit.unit_type is not None else unit.type.id


def short(label: str) -> str:
    """A unit's name without the other designation some carry in brackets."""
    return re.sub(r"\s*\(.*\)$", "", label)


def alive(tgos: Iterable[TheaterGroundObject]) -> list[TheaterUnit]:
    return [unit for tgo in tgos for unit in tgo.units if unit.alive]


def joined(items: Sequence[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def counted(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def listed(names: Sequence[str], most: int = NAMES_SHOWN) -> str:
    """Up to ``most`` names, and how many more there are."""
    if len(names) <= most:
        return joined(names)
    return f"{', '.join(names[:most])} and {len(names) - most} more"


def sites(names: Sequence[str], they: str, it: str) -> str:
    """The air defence sites something holds up, and what they do without it."""
    if len(names) == 1:
        return f"the air defence site {names[0]}, which {it} without it"
    return (
        f"{counted(len(names), 'air defence site')} ({listed(names)}), which {they} "
        "without it"
    )


def money(millions: float) -> str:
    """Millions the way the game writes them: $40M, $2.5M."""
    return f"${round(millions, 1):g}M" if millions < 10 else f"${millions:.0f}M"
