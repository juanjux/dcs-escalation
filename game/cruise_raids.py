"""Ship-launched cruise missile raids: eligibility, magazines, reconciliation.

Warships with land-attack cruise missiles (the Burke's Tomahawks, the CurrentHill
Kalibr hulls) can strike shore targets through a DCS ``FireAtPoint`` task with the
cruise-missile weapon flag, but nothing in Escalation ever tasked them. This is the
campaign half of the feature; the ``cruisemissiles`` Lua plugin is the in-mission half.

* **Eligibility** — :data:`LACM_SHIP_DCS_IDS`, a hand-curated set of DCS ship types.
  Neither DCS nor pydcs exposes a per-ship weapon taxonomy we could derive it from,
  so the alternative would be tasking hulls that carry no such missile at all.
* **Magazines** — DCS silently reloads every ship every mission, so without campaign
  bookkeeping each turn would hand out a free full salvo. Each launching *group*
  therefore carries a missile stock persisted on the Game
  (``cruise_missile_magazines``, keyed by the stable ``TheaterGroup.group_name``).
  There is no rearm and no resupply: the magazine is the whole war's stock.
* **Auto raids** — :func:`plan_cruise_raids` commits at most one raid per side per
  turn, against the highest-value reachable enemy ground object.

Only :func:`reconcile_cruise_missiles` — which runs at the turn boundary from what
the plugin reported actually leaving the tubes — ever writes a magazine. Everything
else is a pure read, so re-generating a mission (which players do freely) can never
charge for the same salvo twice. A group that has never fired has no stored entry at
all and reads its stock from the hulls still afloat, which is why sinking a launcher
takes its missiles with it.

The missiles are real DCS weapons fired by a real, tracked ship, so kills are recorded
through the ordinary debrief path, point defense gets to intercept them, and sinking
the shooter ends the raids. Symmetric: red Kalibr hulls raid blue exactly the same way.

Gated by the ``cruisemissiles`` plugin (the magazines and its F10 call-for-fire) and
by that plugin's ``autoRaids`` option (the planner).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Optional

from game.utils import nautical_miles

if TYPE_CHECKING:
    from dcs.mapping import Point

    from game import Game
    from game.debriefing import Debriefing
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterGroup, TheaterUnit

#: DCS ship types that carry land-attack cruise missiles: the vanilla Burke/Ticonderoga
#: Tomahawk shooters plus the CurrentHill pack's explicit land-attack hull variants. The
#: pack's anti-ship-only sister hulls (CH_*_AShM) are deliberately absent — hunting ships
#: is the ANTISHIP task's job, and tasking them here would fire the wrong weapon.
LACM_SHIP_DCS_IDS: frozenset[str] = frozenset(
    {
        "USS_Arleigh_Burke_IIa",
        "TICONDEROG",
        "CH_Arleigh_Burke_IIA",
        "CH_Arleigh_Burke_III",
        "CH_Ticonderoga",
        "CH_Ticonderoga_CMP",
        "CH_Grigorovich_LACM",
        "CH_Karakurt_LACM",
        "CH_Gremyashchiy_LACM",
    }
)

#: Campaign missile stock per hull, summed over a group's living launchers. Loosely the
#: real land-attack fits — a Burke's VLS carries a deep TLAM load, the old Tico's armored
#: box launchers eight, a Kalibr corvette a single eight-cell UKSK — but these are balance
#: numbers, not a TO&E.
LACM_MAGAZINE_BY_TYPE: dict[str, int] = {
    "USS_Arleigh_Burke_IIa": 24,
    "TICONDEROG": 8,
    "CH_Arleigh_Burke_IIA": 24,
    "CH_Arleigh_Burke_III": 24,
    "CH_Ticonderoga": 8,
    "CH_Ticonderoga_CMP": 24,
    "CH_Grigorovich_LACM": 8,
    "CH_Karakurt_LACM": 8,
    "CH_Gremyashchiy_LACM": 8,
}

#: Stock for a curated hull with no table row, so adding an id above can never seed a
#: launcher with nothing to launch.
DEFAULT_MAGAZINE_PER_SHIP = 8

#: Auto-raid planning reach, ship to target. Deliberately short of what DCS models for a
#: Tomahawk: the planner picks blind, so it should only ever commit shots it is confident
#: arrive. A player calling fire from the F10 menu may reach further (a plugin option).
MAX_RAID_RANGE_M = nautical_miles(250).meters

#: Missiles per auto raid, capped by what the group has left.
RAID_SALVO = 6

#: What a cruise missile raid is worth spending irreplaceable stock on: fixed, high-value
#: infrastructure that is painful to reach with aircraft. Command and control first, then
#: the economy buildings, then anything else strikeable. Lower sorts first.
_TARGET_CATEGORY_PRIORITY: dict[str, int] = {
    "commandcenter": 0,
    "comms": 1,
    "power": 2,
    "factory": 3,
    "oil": 4,
    "fuel": 5,
    "ware": 6,
    "ammo": 7,
}
_FALLBACK_PRIORITY = 8

#: TGO categories whose groups are warships and can therefore *launch*. A standalone ship
#: object is category "ship", but a Burke's usual home is a carrier or LHA task force
#: ("CARRIER"/"LHA" — theater categories are case-inconsistent, hence the lowercasing).
#: The same categories are excluded as raid *targets*: a FireAtPoint aims at a fixed
#: point on the ground and cannot lead a moving hull, which is the ANTISHIP task's job.
_NAVAL_TGO_CATEGORIES = frozenset({"ship", "carrier", "lha"})


def _is_naval_tgo(tgo: TheaterGroundObject) -> bool:
    return tgo.category.lower() in _NAVAL_TGO_CATEGORIES


@dataclass(frozen=True)
class LacmShip:
    """One live launching group: a naval TGO group holding at least one living hull that
    carries land-attack cruise missiles."""

    group_name: str
    coalition: str  # "blue" | "red" — the key the plugin and the emitter share
    position: Point
    remaining: int


@dataclass(frozen=True)
class CruiseRaid:
    """One planned auto raid: *missiles* cruise missiles from *group_name* onto the
    target's position, fired at a random moment inside the plugin's launch window."""

    group_name: str
    coalition: str
    target_name: str
    target_x: float
    target_y: float
    missiles: int


def magazines(game: Game) -> dict[str, int]:
    """The persisted per-group stock. Only groups that have actually fired appear here;
    see :func:`remaining_missiles` for the stock of a group that never has."""
    mags: Optional[dict[str, int]] = getattr(game, "cruise_missile_magazines", None)
    if mags is None:
        mags = {}
        game.cruise_missile_magazines = mags
    return mags


def remaining_missiles(game: Game, group: TheaterGroup) -> int:
    """What *group* has left. A group with no stored entry has never fired, so its stock
    is simply what its living launchers carry — which is also why losing a hull before it
    shoots costs you its missiles. Once a group fires, its entry is fixed at the first
    debit and only ever falls: repairing or replacing a launcher does not restock it.
    """
    stored = magazines(game).get(group.group_name)
    if stored is not None:
        return stored
    return _group_capacity(group)


def lacm_ships(game: Game) -> list[LacmShip]:
    """Every live launching group with missiles left, both sides."""
    ships: list[LacmShip] = []
    for tgo, group in _lacm_groups(game):
        remaining = remaining_missiles(game, group)
        if remaining <= 0:
            continue
        ships.append(
            LacmShip(
                group_name=group.group_name,
                coalition="blue" if tgo.control_point.captured.is_blue else "red",
                position=tgo.position,
                remaining=remaining,
            )
        )
    return ships


def plan_cruise_raids(game: Game) -> list[CruiseRaid]:
    """At most one auto raid per side this turn.

    A pure function of game state, so it is safe to call once per mission generation, on
    every briefing render and from the culling pass: the plan is identical every time and
    the magazine does not move until the debrief.
    """
    settings = game.settings
    if not settings.plugin_option_or("cruisemissiles", False):
        return []
    if not settings.plugin_option_or("cruisemissiles.autoRaids", False):
        return []
    raids = []
    for side in ("blue", "red"):
        raid = _plan_side_raid(game, side)
        if raid is not None:
            raids.append(raid)
    return raids


def reconcile_cruise_missiles(game: Game, debriefing: Debriefing) -> None:
    """Debit the magazines by what the plugin reported fired this mission.

    The single write site for the whole feature. Charging here rather than when the
    mission is generated is what makes regenerating a mission free: the plan can be
    recomputed any number of times, but only missiles that actually left the tubes are
    ever paid for. A group missing from the report (mission never flown, plugin
    disabled) costs nothing; one whose launchers all sank without a stored magazine is
    ignored, its stock having gone down with the ship.
    """
    reports = getattr(debriefing.state_data, "cruise_missiles_state", None)
    if not reports:
        return
    mags = magazines(game)
    capacities = {
        group.group_name: _group_capacity(group) for _, group in _lacm_groups(game)
    }
    for group_name, fired in reports:
        fired = int(fired)
        if fired <= 0:
            continue
        stock = mags.get(group_name, capacities.get(group_name))
        if stock is None:
            continue
        mags[group_name] = max(0, stock - fired)


def player_briefing_info(game: Game) -> tuple[list[LacmShip], list[CruiseRaid]]:
    """Blue-side launching ships and this turn's planned blue raid, for the mission
    briefing (which, like the rest of the briefing, is written from the player
    coalition's point of view). Ships are listed even with auto-raids off, because the
    magazine still matters to the F10 call-for-fire."""
    if not game.settings.plugin_option_or("cruisemissiles", False):
        return [], []
    ships = [s for s in lacm_ships(game) if s.coalition == "blue"]
    if not ships:
        return [], []
    raids = [r for r in plan_cruise_raids(game) if r.coalition == "blue"]
    return ships, raids


def tgo_magazines(game: Game, tgo: TheaterGroundObject) -> list[tuple[str, int]]:
    """``(group_name, remaining)`` per launching group of *tgo*, for the ground object
    dialog. The caller owns the friendly-side gate: what the enemy has left in its tubes
    is not intel a click should hand out."""
    if not game.settings.plugin_option_or("cruisemissiles", False):
        return []
    if not _is_naval_tgo(tgo):
        return []
    return [
        (group.group_name, remaining_missiles(game, group))
        for group in tgo.groups
        if any(_is_alive_lacm(u) for u in group.units)
    ]


def debrief_expenditures(
    game: Game, debriefing: Debriefing
) -> list[tuple[str, int, Optional[int]]]:
    """``(group_name, fired, remaining)`` rows for the debrief window.

    Every reported launch is listed — a launch is observable, the other side got a launch
    warning and had to meet the missiles — but ``remaining`` is filled in for the
    player's own groups only. Runs after the turn-boundary debit, so ``remaining`` is
    what sails into the next turn; a sunk blue shooter reports ``None`` as well, its
    leftover stock having gone down with it.
    """
    reports = getattr(debriefing.state_data, "cruise_missiles_state", None)
    if not reports:
        return []
    blue_groups = {
        group.group_name
        for tgo, group in _lacm_groups(game)
        if tgo.control_point.captured.is_blue
    }
    mags = magazines(game)
    rows = []
    for group_name, fired in reports:
        fired = int(fired)
        if fired <= 0:
            continue
        remaining = mags.get(group_name) if group_name in blue_groups else None
        rows.append((group_name, fired, remaining))
    return rows


def _plan_side_raid(game: Game, side: str) -> Optional[CruiseRaid]:
    ships = [s for s in lacm_ships(game) if s.coalition == side]
    if not ships:
        return None

    best: Optional[tuple[int, float, LacmShip, TheaterGroundObject]] = None
    for ship in ships:
        for tgo in _enemy_raid_targets(game, side):
            dist = ship.position.distance_to_point(tgo.position)
            if dist > MAX_RAID_RANGE_M:
                continue
            priority = _TARGET_CATEGORY_PRIORITY.get(tgo.category, _FALLBACK_PRIORITY)
            # Compared on (priority, distance) only: the ship and the target ride along
            # for the winner but must never break the tie, since neither is orderable.
            key = (priority, dist, ship, tgo)
            if best is None or key[:2] < best[:2]:
                best = key
    if best is None:
        return None

    _, _, ship, target = best
    return CruiseRaid(
        group_name=ship.group_name,
        coalition=side,
        target_name=target.name,
        target_x=target.position.x,
        target_y=target.position.y,
        missiles=min(RAID_SALVO, ship.remaining),
    )


def _enemy_raid_targets(game: Game, side: str) -> Iterator[TheaterGroundObject]:
    """Alive, raid-legal enemy ground objects for *side*'s raid this turn."""
    for cp in game.theater.controlpoints:
        owner = cp.captured
        enemy_of_side = owner.is_red if side == "blue" else owner.is_blue
        if not enemy_of_side:
            continue
        for tgo in cp.ground_objects:
            if _is_naval_tgo(tgo):
                continue
            if tgo.is_control_point:
                continue
            if not any(unit.alive for unit in tgo.units):
                continue
            yield tgo


def _lacm_groups(game: Game) -> Iterator[tuple[TheaterGroundObject, TheaterGroup]]:
    """Every naval TGO group holding a living land-attack hull, both sides — standalone
    ship objects and carrier/LHA task forces alike. The carrier generator stamps
    ``TheaterGroup.group_name`` onto the .miz group exactly like the ship generator does,
    so ``FireAtPoint`` resolves an escorting Burke the same way either side of that."""
    for cp in game.theater.controlpoints:
        for tgo in cp.ground_objects:
            if not _is_naval_tgo(tgo):
                continue
            for group in tgo.groups:
                if any(_is_alive_lacm(u) for u in group.units):
                    yield tgo, group


def _group_capacity(group: TheaterGroup) -> int:
    return sum(
        LACM_MAGAZINE_BY_TYPE.get(u.type.id, DEFAULT_MAGAZINE_PER_SHIP)
        for u in group.units
        if _is_alive_lacm(u)
    )


def _is_alive_lacm(unit: TheaterUnit) -> bool:
    return unit.alive and unit.type.id in LACM_SHIP_DCS_IDS
