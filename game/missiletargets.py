"""Persistent, coalition-owned land-attack missile assignments."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, TYPE_CHECKING
from uuid import UUID

from dcs import Point
from dcs.mapping import LatLng

from game.cruise_raids import LACM_SHIP_DCS_IDS, remaining_missiles
from game.data.missile_ranges import MISSILE_SITE_MIN_RANGE_M, USABLE_RANGE_FRACTION
from game.theater.player import Player
from game.theater.theatergroundobject import MissileSiteGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater.theatergroundobject import TheaterGroundObject

# CH launcher distanceMin/distanceMax, not the ships' anti-air threat ranges.
# CH pack Database/Weapons: RGM-109C III, RGM-109E V and 3M14T launchers.
# Vanilla hulls retain the existing conservative 250 NM campaign envelope.
SHIP_MISSILE_RANGES: dict[str, tuple[float, float]] = {
    "USS_Arleigh_Burke_IIa": (0, 250 * 1852),
    "TICONDEROG": (0, 250 * 1852),
    "CH_Arleigh_Burke_IIA": (10000, 1300000),
    "CH_Arleigh_Burke_III": (10000, 1600000),
    "CH_Ticonderoga": (10000, 1300000),
    "CH_Ticonderoga_CMP": (10000, 1600000),
    "CH_Grigorovich_LACM": (20000, 1500000),
    "CH_Karakurt_LACM": (20000, 1500000),
    "CH_Gremyashchiy_LACM": (20000, 1500000),
}


@dataclass(frozen=True)
class MissileTarget:
    owner: Player
    x: float
    z: float
    name: str
    target_id: UUID | None = None
    track_position: bool = False


@dataclass(frozen=True)
class MissileLauncher:
    group_name: str
    unit_type: str
    minimum: float
    maximum: float


def launchers(game: Game, source: TheaterGroundObject) -> list[MissileLauncher]:
    """Only living launchers, with each weapon's own engagement envelope."""
    result = []
    for group in source.groups:
        for unit in group.units:
            if not unit.alive:
                continue
            kind = unit.type.id
            if isinstance(source, MissileSiteGroundObject):
                maximum = (
                    float(getattr(unit.type, "threat_range", 0)) * USABLE_RANGE_FRACTION
                )
                minimum = float(MISSILE_SITE_MIN_RANGE_M.get(kind, 0))
            elif kind in LACM_SHIP_DCS_IDS:
                if remaining_missiles(game, group) <= 0:
                    continue
                minimum, maximum = SHIP_MISSILE_RANGES[kind]
                # Keep the existing configurable campaign launch limit as well.
                cap = game.settings.plugin_option_or(
                    "cruisemissiles.playerRangeNm", 250
                )
                if (
                    isinstance(cap, bool)
                    or not isinstance(cap, (int, float))
                    or not math.isfinite(cap)
                    or cap <= 0
                ):
                    raise ValueError(
                        "Cruise missile range must be a positive number of NM"
                    )
                maximum = min(maximum, float(cap) * 1852)
            else:
                continue
            if maximum > minimum:
                result.append(MissileLauncher(group.group_name, kind, minimum, maximum))
    return result


def source_for(
    game: Game, source_id: UUID, owner: Player, *, operational: bool = True
) -> TheaterGroundObject:
    try:
        source = game.db.tgos.get(source_id)
    except KeyError as exc:
        raise ValueError("Unknown own missile launcher") from exc
    if not source.is_friendly(owner) or (operational and source.is_dead):
        raise ValueError("Unknown own missile launcher")
    if operational and not launchers(game, source):
        raise ValueError(
            "This group has no operational land-attack missile launchers with ammunition"
        )
    return source


def targets(
    game: Game, owner: Player, allowed: set[str] | None = None
) -> list[TheaterGroundObject]:
    result = []
    seen: set[UUID] = set()
    for cp in game.theater.controlpoints:
        if cp.captured is not owner.opponent:
            continue
        for target in cp.ground_objects:
            if target.id in seen or target.is_dead or target.is_control_point:
                continue
            if target.category.lower() in ("ship", "carrier", "lha"):
                continue
            if allowed is not None and str(target.id) not in allowed:
                continue
            seen.add(target.id)
            result.append(target)
    return result


def stored(source: TheaterGroundObject) -> MissileTarget | None:
    return getattr(source, "missile_target", None)


def aimpoint(game: Game, source: TheaterGroundObject) -> Point | None:
    order = stored(source)
    if order is None:
        return None
    if not source.is_friendly(order.owner):
        raise ValueError("The launcher changed coalition")
    if order.target_id is not None:
        try:
            target = game.db.tgos.get(order.target_id)
        except KeyError as exc:
            raise ValueError("The assigned target no longer exists") from exc
        if (
            target.is_dead
            or target.is_friendly(order.owner)
            or target.control_point.captured.is_neutral
        ):
            raise ValueError("The assigned target is destroyed or no longer hostile")
        if order.track_position:
            return target.position
    return Point(order.x, order.z, game.theater.terrain)


def in_range(
    game: Game, source: TheaterGroundObject, point: Point, group_name: str | None = None
) -> bool:
    distance = source.position.distance_to_point(point)
    return any(
        launcher.minimum <= distance < launcher.maximum
        for launcher in launchers(game, source)
        if group_name is None or launcher.group_name == group_name
    )


def preview(
    game: Game,
    source_id: UUID,
    owner: Player,
    *,
    target_id: UUID | None = None,
    target_name: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    allowed: set[str] | None = None,
) -> tuple[MissileTarget, dict[str, Any]]:
    source = source_for(game, source_id, owner)
    modes = sum(
        (target_id is not None, bool(target_name), lat is not None or lng is not None)
    )
    if modes != 1:
        raise ValueError("Choose one enemy target ID, code name, or GPS position")
    candidates = targets(game, owner, allowed)
    target = None
    track = lat is None and lng is None
    if track:
        matches = [
            t
            for t in candidates
            if (
                t.id == target_id
                if target_id is not None
                else str(target_name).strip().casefold()
                in (t.name.casefold(), t.obj_name.casefold())
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                "Unknown or ambiguous enemy target; use an ID from the target list"
            )
        target = matches[0]
        point = target.position
    else:
        if (
            lat is None
            or lng is None
            or not math.isfinite(lat)
            or not math.isfinite(lng)
            or not -90 <= lat <= 90
            or not -180 <= lng <= 180
        ):
            raise ValueError("Provide a valid latitude and longitude")
        point = Point.from_latlng(LatLng(lat, lng), game.theater.terrain)
        # A marker click at the objective centre tracks that objective. Other GPS
        # aimpoints remain exact, but can still be linked to a nearby target's life.
        nearby = sorted(
            (
                (
                    min(
                        [t.position.distance_to_point(point)]
                        + [
                            u.position.distance_to_point(point)
                            for u in t.units
                            if u.alive
                        ]
                    ),
                    t,
                )
                for t in candidates
            ),
            key=lambda item: (item[0], str(item[1].id)),
        )
        if nearby and nearby[0][0] <= 100:
            target = nearby[0][1]
            track = target.position.distance_to_point(point) < 1
    distance = source.position.distance_to_point(point)
    if not in_range(game, source, point):
        raise ValueError(
            f"Target outside the launchers' engagement ranges ({distance / 1000:.1f} km away)"
        )
    name = target.obj_name if target else "GPS position (no known target)"
    order = MissileTarget(
        owner, point.x, point.y, name, target.id if target else None, track
    )
    ll = point.latlng()
    result = {
        "source_id": str(source.id),
        "target_id": str(target.id) if target else None,
        "target_name": name,
        "position": {"lat": ll.lat, "lng": ll.lng},
        "distance_m": round(distance, 1),
        "empty_position": target is None,
        "requires_confirmation": target is None,
        "warning": (
            "No known enemy target here. This order will fire at this position every turn until cancelled."
            if target is None
            else None
        ),
    }
    return order, result


def assign(
    game: Game,
    source_id: UUID,
    owner: Player,
    *,
    confirm_empty: bool = False,
    **selection: Any,
) -> dict[str, Any]:
    order, result = preview(game, source_id, owner, **selection)
    if result["empty_position"] and not confirm_empty:
        raise ValueError(
            "No known enemy target here; confirm_empty is required to keep firing at this GPS position"
        )
    source = source_for(game, source_id, owner)
    source.missile_target = order
    return result


def clear(game: Game, source_id: UUID, owner: Player) -> None:
    # Cancellation must also work with a dry magazine or a disabled plugin.
    try:
        source = game.db.tgos.get(source_id)
    except KeyError as exc:
        raise ValueError("Unknown own missile launcher") from exc
    if not source.is_friendly(owner):
        raise ValueError("Unknown own missile launcher")
    source.missile_target = None


def options(
    game: Game, source_id: UUID, owner: Player, allowed: set[str] | None = None
) -> dict[str, Any]:
    source = source_for(game, source_id, owner, operational=False)
    weapons = launchers(game, source)
    current = stored(source)
    status = None
    if current is not None:
        try:
            point = aimpoint(game, source)
            status = (
                "assigned"
                if point is not None and in_range(game, source, point)
                else "out_of_range"
            )
        except ValueError as exc:
            status = str(exc)
    return {
        "source_id": str(source.id),
        "source_name": source.obj_name,
        "enabled": (
            bool(game.settings.generate_fire_tasks_for_missile_sites)
            if isinstance(source, MissileSiteGroundObject)
            else bool(game.settings.plugin_option_or("cruisemissiles", False))
        ),
        "launchers": [
            {
                "group_name": w.group_name,
                "unit_type": w.unit_type,
                "min_range_m": w.minimum,
                "max_range_m": w.maximum,
            }
            for w in weapons
        ],
        "assignment": (
            {
                "target_id": str(current.target_id) if current.target_id else None,
                "target_name": current.name,
                "empty_position": current.target_id is None,
                "status": status,
                "position": {
                    "lat": Point(current.x, current.z, game.theater.terrain)
                    .latlng()
                    .lat,
                    "lng": Point(current.x, current.z, game.theater.terrain)
                    .latlng()
                    .lng,
                },
            }
            if current
            else None
        ),
        "targets": [
            {
                "id": str(t.id),
                "name": t.obj_name,
                "in_range": in_range(game, source, t.position),
                "distance_m": round(source.position.distance_to_point(t.position), 1),
            }
            for t in targets(game, owner, allowed)
        ],
    }


def remove_invalid(game: Game) -> None:
    """Release destroyed/captured targets at turn end, before repairs can revive them."""
    for cp in game.theater.controlpoints:
        for source in cp.ground_objects:
            if stored(source) is None:
                continue
            try:
                aimpoint(game, source)
            except ValueError:
                source.missile_target = None
