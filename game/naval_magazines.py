"""Cross-turn naval magazines — the fleet's anti-ship missiles are finite.

Three facts combine into one bad outcome, flown on Marianas 2027 (374 weapon
launches, essentially all inside the opening five minutes):

1. ``TgoGenerator.set_ship_engagement`` spawns every ship weapon-free with a RED
   alarm state, because ship weapons in DCS are OPTION-driven (an
   ``EngageTargets`` task is air-only and crashed the naval AI when tried). So a
   ship shoots the instant anything enters range.
2. Modern anti-ship missiles out-range the theatre (the YJ-18 reaches ~540 km
   against a 205 km Guam–Saipan gap), so "in range" is permanently true from
   t=0 and the whole fleet salvos at once rather than fighting a developing
   battle.
3. A DCS mission is a fresh spawn: loadouts reset every turn, so a fleet
   re-dumps a full magazine *every turn*. Sinking hulls was the only way volume
   ever went down — the naval war had no ammunition dimension at all.

Two independently-gated tiers answer that, mirroring  proven shape:

* **N1, staggered release** (``naval_weapon_release_stagger``) — ships generate
  ``ReturnFire`` instead of ``WeaponFree`` and the plugin releases each group to
  weapons-free at its own moment inside a window, and immediately whatever its
  moment once the other side fires an anti-ship missile. ``ReturnFire`` rather
  than ``WeaponHold`` deliberately: the point is to delay *initiation*, not to
  disarm anybody — but ``ReturnFire`` does not leave a ship able to defend
  itself either, because shooting an incoming missile is not returning fire at
  whoever launched it, so being shot at has to end the wait. Runtime only, no
  persisted state.
* **N2, the magazine** (``naval_magazines``) — each naval group carries a
  persisted anti-ship missile stock (:data:`ASHM_MAGAZINE_BY_TYPE`, summed over
  the group's alive hulls at first sight), emitted as this mission's hard cap.
  The plugin counts real ``S_EVENT_SHOT`` releases of anti-ship weapons and
  drops a spent group back to ``ReturnFire`` — winchester, not disarmed. What
  actually fired is mirrored into the ``naval_magazines_state`` debrief channel
  and debited at the turn boundary; **generation never debits**, so
  re-generating a mission is free.

**No double count with .** The land-attack cruise missiles  meters
(Tomahawk, the 3M14 Kalibr) are absent from :data:`ASHM_WEAPON_PATTERNS` by
construction — the two magazines meter disjoint weapon sets, so a  raid
never spends anti-ship stock and vice versa. Keep it that way when extending
the pattern list: never add a land-attack family here.

Keyed by :attr:`TheaterGroup.group_name`, the same stable
``"<id> | <name>"`` string  magazines use — the ``TheaterGroup`` lives in
the campaign save, so the key survives regeneration.

Symmetric: blue's Burkes are bound by exactly the same rule as red's Type 055s.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterGroup

#: Anti-ship missile stock per hull, per *unit*, summed over a group's alive
#: ships at first sight. Curated by hand (neither DCS nor
#: pydcs exposes a per-ship weapon taxonomy to derive it from), and loosely the
#: real anti-ship fit: a Burke's Harpoon canisters, a Slava's P-500 tubes, the
#: PLAN destroyers' share of their UVLS. Balance numbers, not TO&E.
#:
#: A hull that is absent uses :data:`DEFAULT_MAGAZINE_PER_SHIP`; a hull that
#: carries no anti-ship missile at all simply never fires one, so its magazine
#: never depletes and the default costs nothing.
ASHM_MAGAZINE_BY_TYPE: dict[str, int] = {
    # United States
    "USS_Arleigh_Burke_IIa": 8,
    "TICONDEROG": 8,
    "PERRY": 4,
    # Russia / Soviet
    "MOSCOW": 16,  # Slava, P-500 Bazalt
    "PIOTR": 20,  # Kirov, P-700 Granit
    "MOLNIYA": 4,  # Tarantul, Kh-35
    # China (vanilla + the CurrentHill pack Marianas 2027 fields)
    "Type_052B": 16,
    "Type_052C": 8,
    "Type_054A": 8,
    "Type052D": 16,
    "Type055": 32,
    "CH_Type054B": 8,
    # Europe
    "La_Combattante_II": 4,  # Exocet
    # --- mod hulls -------------------------------------------------------------
    # Same curation as LACM_MAGAZINE_BY_TYPE in cruise_raids: hand-written from the
    # real fit, balance numbers rather than TO&E. A hull that carries no anti-ship
    # missile never fires one, so a row it does not need costs nothing.
    # Spanish Navy Pack
    "F100": 8,  # Alvaro de Bazan, 2x4 Harpoon canisters
    "F105": 8,  # Cristobal Colon, same class
    # CurrentHill USA
    "CH_Arleigh_Burke_IIA": 8,
    "CH_Arleigh_Burke_III": 8,
    "CH_Ticonderoga": 8,
    "CH_Ticonderoga_CMP": 8,
    "CH_Constellation": 16,  # NSM
    # CurrentHill Russia
    "CH_Admiral_Gorshkov": 16,  # 2x8 UKSK, Oniks/Zircon
    "CH_Gremyashchiy_AShM": 8,  # 1x8 UKSK
    "CH_Grigorovich_AShM": 8,
    "CH_Karakurt_AShM": 8,
    "CH_Steregushchiy": 8,  # 2x4 Kh-35 Uran
    # CurrentHill China
    "CH_Type022": 8,  # Houbei, YJ-83
    "CH_Type056A": 4,  # Jiangdao corvette
    # CurrentHill UK
    "CH_Type26": 8,  # NSM
}
DEFAULT_MAGAZINE_PER_SHIP = 8

#: Substring patterns (case-insensitive, plain — never Lua patterns, the
#: lesson) matched against a fired weapon's DCS ``typeName`` to decide whether
#: it spent anti-ship stock. Deliberately family-level rather than exact ids so
#: a mod's hull variant is covered without a data edit.
#:
#: **Land-attack families are excluded on purpose** so  cruise-missile
#: magazine and this one can never both meter the same shot: no ``BGM_109``, no
#: ``3M14``, and nothing as loose as ``Kalibr`` (which would catch the
#: land-attack 3M14 alongside the anti-ship 3M54).
ASHM_WEAPON_PATTERNS: tuple[str, ...] = (
    "HARPOON",
    "RGM_84",
    "AGM_84",  # ship-launched Harpoon variants
    "EXOCET",
    "MM_38",
    "MM_40",
    "YJ",  # YJ-83 / YJ-18 / YJ-62 / YJ-12
    "C_802",
    "C_602",
    "P_500",
    "P_700",
    "P_270",
    "P_1000",
    "KH_35",
    "3M24",  # Uran
    "3M54",  # the anti-ship Kalibr (NOT the 3M14 land-attack sibling)
    "SS_N",
    "NSM",
    "RBS15",
    "OTOMAT",
)


@dataclass(frozen=True)
class NavalGroupMagazine:
    """One live naval group's emitted state for this mission."""

    group_name: str
    coalition: str  # "blue" | "red" — the emitter/plugin side key
    remaining: int


def magazines(game: "Game") -> dict[str, int]:
    """The persisted per-group anti-ship stock (getattr-guarded for old saves)."""
    mags: Optional[dict[str, int]] = getattr(game, "naval_magazines", None)
    if mags is None:
        mags = {}
        game.naval_magazines = mags
    return mags


def ensure_magazines(game: "Game") -> None:
    """Lazily seed a magazine for any naval group not yet tracked.

    Idempotent — an existing entry is never re-upped, so expenditure persists
    across turns; capacity counts the group's *alive* hulls at first sight.
    """
    mags = magazines(game)
    for _tgo, group in _naval_groups(game):
        name = group.group_name
        if name not in mags:
            mags[name] = _group_capacity(group)


def naval_group_magazines(game: "Game") -> list[NavalGroupMagazine]:
    """Every live naval group and its remaining anti-ship stock, both sides.

    A group with an empty magazine is still listed (with ``remaining`` 0) so the
    plugin knows to hold it at ``ReturnFire`` from mission start rather than
    letting a spent fleet fight on as if freshly loaded.
    """
    ensure_magazines(game)
    mags = magazines(game)
    found = [
        NavalGroupMagazine(
            group_name=group.group_name,
            coalition="blue" if tgo.control_point.captured.is_blue else "red",
            remaining=max(0, mags.get(group.group_name, 0)),
        )
        for tgo, group in _naval_groups(game)
    ]
    return _by_turns(found)


def _by_turns(groups: list[NavalGroupMagazine]) -> list[NavalGroupMagazine]:
    """The two sides alternating, because the plugin releases them in this order.

    The stagger spreads the releases evenly across its window by position in this
    list, and the list came out in objective order -- which in a campaign that
    numbers one side's objectives before the other's is the same as sorting by
    coalition. On Gran Polvorin that handed red every slot from two minutes to eight
    and blue every slot from ten to fifteen: red opened fire with blue still on
    ReturnFire, which is not a stagger, it is a head start.

    Alternating gives neither side one. A side with more groups than the other keeps
    the tail, which is unavoidable and is not a bias: it is the same fleet either way.
    """
    sides: dict[str, list[NavalGroupMagazine]] = {"blue": [], "red": []}
    for group in groups:
        sides[group.coalition].append(group)
    ordered: list[NavalGroupMagazine] = []
    for blue, red in zip_longest(sides["blue"], sides["red"]):
        # Red first only because something has to be, and it is the same every turn.
        for group in (red, blue):
            if group is not None:
                ordered.append(group)
    return ordered


def reconcile_naval_magazines(game: "Game", debriefing: "Debriefing") -> None:
    """Debit the magazines by what the plugin reported fired this mission.

    The report is the only debit site (regeneration-safe); an unreported group
    (mission never flown, plugin or feature off) costs nothing, and an unknown
    group name (stale save) is ignored.
    """
    reports = getattr(debriefing.state_data, "naval_magazines_state", None)
    if not reports:
        return
    mags = magazines(game)
    for group_name, fired in reports:
        fired = int(fired)
        if fired <= 0:
            continue
        if group_name in mags:
            mags[group_name] = max(0, mags[group_name] - fired)


def tgo_magazines(game: "Game", tgo: "TheaterGroundObject") -> list[tuple[str, int]]:
    """``(group_name, remaining)`` per naval group of *tgo*, for the ground
    object dialog. Empty when the feature is off. Seeds unseen groups first,
    like every other magazine read. The caller owns the friendly-side gate —
    enemy stock is not a click away, by design.
    """
    if not game.settings.plugin_option_or("navalmagazines", False):
        return []
    if not _is_naval_tgo(tgo):
        return []
    ensure_magazines(game)
    mags = magazines(game)
    rows = []
    for group in getattr(tgo, "groups", []):
        name = getattr(group, "group_name", None)
        if name and any(_is_alive_ship(u) for u in getattr(group, "units", [])):
            rows.append((name, mags.get(name, 0)))
    return rows


def winchester_lines(game: "Game", debriefing: "Debriefing") -> list[str]:
    """SITREP lines for blue groups that went winchester this mission.

    Without a surface the player reads a quiet turn as a bug, so a group that
    emptied its tubes says so. Blue only — enemy residual stock stays hidden,
    like every other magazine readout.
    """
    if not game.settings.plugin_option_or("navalmagazines", False):
        return []
    reports = getattr(debriefing.state_data, "naval_magazines_state", None)
    if not reports:
        return []
    blue = {
        group.group_name
        for tgo, group in _naval_groups(game)
        if tgo.control_point.captured.is_blue
    }
    mags = magazines(game)
    lines = []
    for group_name, fired in reports:
        if int(fired) <= 0 or group_name not in blue:
            continue
        remaining = mags.get(group_name, 0)
        if remaining <= 0:
            lines.append(
                f"{group_name}: WINCHESTER anti-ship — {fired} fired, no rearm"
            )
        else:
            lines.append(
                f"{group_name}: {fired} anti-ship missile(s) fired, {remaining} left"
            )
    return lines


#: TGO categories whose groups are warships. Theater categories are
#: case-inconsistent, so membership is checked lowercased (the  helper).
_NAVAL_TGO_CATEGORIES = frozenset({"ship", "carrier", "lha"})


def _is_naval_tgo(tgo: object) -> bool:
    category = getattr(tgo, "category", None)
    return isinstance(category, str) and category.lower() in _NAVAL_TGO_CATEGORIES


def _naval_groups(
    game: "Game",
) -> Iterator[tuple["TheaterGroundObject", "TheaterGroup"]]:
    """Every naval TGO group holding at least one alive hull, both sides —
    standalone ship objects and carrier/LHA task forces alike."""
    for cp in game.theater.controlpoints:
        for tgo in cp.ground_objects:
            if not _is_naval_tgo(tgo):
                continue
            for group in getattr(tgo, "groups", []):
                if not getattr(group, "group_name", None):
                    continue
                if any(_is_alive_ship(u) for u in getattr(group, "units", [])):
                    yield tgo, group


def _group_capacity(group: "TheaterGroup") -> int:
    return sum(
        ASHM_MAGAZINE_BY_TYPE.get(_dcs_id(u) or "", DEFAULT_MAGAZINE_PER_SHIP)
        for u in getattr(group, "units", [])
        if _is_alive_ship(u)
    )


def _is_alive_ship(unit: object) -> bool:
    return bool(getattr(unit, "alive", False)) and _dcs_id(unit) is not None


def _dcs_id(unit: object) -> Optional[str]:
    unit_type = getattr(unit, "type", None)
    return getattr(unit_type, "id", None)
