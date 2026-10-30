"""Player campaign alerts, separate from the chronological information log."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING

from game.ground_forces.ai_ground_planner import deployable_armor
from game.squadrons.morale import morale_state
from game.theater.player import Player
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    MissileSiteGroundObject,
)

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject


@dataclass(frozen=True)
class CampaignNotice:
    id: str
    category: str
    title: str
    detail: str
    turn: int
    target_kind: str
    target_id: str
    recurring: bool = False


@dataclass
class CampaignNotifications:
    events: list[CampaignNotice] = field(default_factory=list)
    read: set[str] = field(default_factory=set)
    owners: dict[str, Player] = field(default_factory=dict)
    buildings: dict[str, tuple[bool, bool, Player]] = field(default_factory=dict)
    initialized: bool = False


def state(game: Game) -> CampaignNotifications:
    result = getattr(game, "campaign_notifications", None)
    if result is None:
        result = CampaignNotifications()
        game.campaign_notifications = result
    return result


def post(game: Game, notice: CampaignNotice) -> None:
    """Idempotent event hook for future notification categories."""
    store = state(game)
    if not any(item.id == notice.id for item in store.events):
        store.events.append(notice)


def building_ready(game: Game, source: TheaterGroundObject) -> None:
    if not isinstance(source, BuildingGroundObject) or not source.is_friendly(
        Player.BLUE
    ):
        return
    post(
        game,
        CampaignNotice(
            f"building:{source.id}:{game.turn}",
            "building_ready",
            f"{source.obj_name} is operational",
            "Building repair or construction completed.",
            game.turn,
            "tgo",
            str(source.id),
        ),
    )


def _events(game: Game, store: CampaignNotifications) -> None:
    owners = {}
    buildings = {}
    seen: set[str] = set()
    for cp in game.theater.controlpoints:
        key = str(cp.id)
        owners[key] = cp.captured
        previous = store.owners.get(key)
        if (
            store.initialized
            and previous is not None
            and previous is not cp.captured
            and Player.BLUE in (previous, cp.captured)
        ):
            gained = cp.captured is Player.BLUE
            post(
                game,
                CampaignNotice(
                    f"base:{cp.id}:{game.turn}:{cp.captured.value}",
                    "base_captured" if gained else "base_lost",
                    f"{cp.name} {'captured' if gained else 'lost'}",
                    "Review its defences, squadrons and supply routes.",
                    game.turn,
                    "base",
                    key,
                ),
            )
        for source in cp.ground_objects:
            if not isinstance(source, BuildingGroundObject) or str(source.id) in seen:
                continue
            seen.add(str(source.id))
            owner = source.control_point.captured
            prior_owner = store.owners.get(str(source.control_point.id))
            info = (source.is_dead, source.has_pending_repairs, owner)
            old = store.buildings.get(str(source.id))
            if store.initialized and owner is Player.BLUE and not source.is_dead:
                if (old is None and prior_owner is Player.BLUE) or (
                    old is not None
                    and old[2] is Player.BLUE
                    and (old[0] or old[1])
                    and not source.has_pending_repairs
                ):
                    building_ready(game, source)
            buildings[str(source.id)] = info
    store.owners = owners
    store.buildings = buildings
    store.initialized = True


def _active(game: Game) -> list[CampaignNotice]:
    alerts = []
    if game.settings.live_pilots_enabled and game.settings.morale_enabled:
        for squadron in game.blue.air_wing.iter_squadrons():
            for pilot in squadron.current_roster:
                if not pilot.alive:
                    continue
                morale = morale_state(pilot.morale, game.settings)
                if morale.name not in ("Shattered", "Broken"):
                    continue
                alerts.append(
                    CampaignNotice(
                        f"morale:{pilot.id}:{game.turn}",
                        "pilot_morale",
                        f"{pilot.name}: very low morale",
                        f"{squadron} · {squadron.aircraft.display_name} · "
                        f"{morale.name} ({pilot.morale}). Consider rest or leave.",
                        game.turn,
                        "pilot",
                        str(pilot.id),
                        True,
                    )
                )
    planners = getattr(game, "ground_planners", {})
    seen_sources: set[str] = set()
    for cp in game.theater.controlpoints:
        if not cp.is_friendly(Player.BLUE):
            continue
        fronts = [other for other in cp.front_lines if other.captured is Player.RED]
        if fronts:
            available = sum(deployable_armor(cp).values())
            planner = planners.get(cp.id)
            allocated = getattr(planner, "units_per_cp", {})
            total = sum(group.size for groups in allocated.values() for group in groups)
            threshold = max(
                3, math.ceil(cp.frontline_unit_count_limit / len(fronts) * 0.25)
            )
            for enemy in fronts:
                count = (
                    sum(group.size for group in allocated.get(enemy.id, []))
                    if total == available and enemy.id in allocated
                    else available // len(fronts)
                )
                if count >= threshold:
                    continue
                alerts.append(
                    CampaignNotice(
                        f"front:{cp.id}:{enemy.id}:{game.turn}",
                        "weak_front",
                        f"Few ground units: {cp.name} / {enemy.name}",
                        f"{count} units available on this front; warning below {threshold}. Reinforce its supporting base.",
                        game.turn,
                        "base",
                        str(cp.id),
                        True,
                    )
                )
        for source in cp.ground_objects:
            if (
                source.is_dead
                or not source.is_friendly(Player.BLUE)
                or str(source.id) in seen_sources
            ):
                continue
            seen_sources.add(str(source.id))
            assignment = getattr(source, "missile_target", None)
            if (
                assignment is not None
                and assignment.owner is Player.BLUE
                and assignment.target_id is None
            ):
                alerts.append(
                    CampaignNotice(
                        f"empty_missile:{source.id}:{game.turn}:{assignment.x:.0f}:{assignment.z:.0f}",
                        "missile_empty_target",
                        f"{source.obj_name}: missile aimed at no known target",
                        "This GPS assignment keeps firing each turn until cancelled. Review the aimpoint or cancel it.",
                        game.turn,
                        "tgo",
                        str(source.id),
                        True,
                    )
                )
            elif isinstance(source, MissileSiteGroundObject) and assignment is None:
                alerts.append(
                    CampaignNotice(
                        f"missile:{source.id}:{game.turn}",
                        "missile_no_target",
                        f"{source.obj_name}: no assigned missile target",
                        "No manual target is defined. Automatic target selection still follows campaign settings.",
                        game.turn,
                        "tgo",
                        str(source.id),
                        True,
                    )
                )
    return alerts


def refresh(game: Game) -> list[CampaignNotice]:
    """Update event snapshots and return unresolved, unread BLUE alerts."""
    store = state(game)
    _events(game, store)
    active = _active(game)
    # Retain recent read events for idempotent event hooks, then discard them.
    # Active conditions recur next turn, with fresh acknowledgement IDs.
    store.events = [
        notice
        for notice in store.events
        if notice.id not in store.read or notice.turn >= game.turn - 1
    ]
    current_ids = {notice.id for notice in active + store.events}
    store.read.intersection_update(current_ids)
    return sorted(
        (notice for notice in active + store.events if notice.id not in store.read),
        key=lambda notice: (-notice.turn, notice.category, notice.title),
    )


def mark_read(game: Game, notices: list[CampaignNotice]) -> None:
    state(game).read.update(notice.id for notice in notices)
