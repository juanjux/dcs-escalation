"""Persistent aircraft repairs, shared base mechanics and explicit damaged sales."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Iterator
from uuid import uuid4

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing
    from game.squadrons import Squadron
    from game.theater import ControlPoint, Player
    from game.unitmap import FlyingUnit


@dataclass
class AircraftRepair:
    """One owned airframe, unavailable until its repair is complete.

    Unknown numerical damage is represented by None and takes one working turn.
    Admission on turn T cannot finish at the immediately following boundary T+1.
    """

    source: str
    admitted_turn: int
    sequence: int
    damage: float | None
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def health(self) -> float | None:
        return None if self.damage is None else max(0.0, 1.0 - self.damage)

    def working_turns(self, rate: float) -> int:
        if self.damage is None:
            return 1
        return max(1, math.ceil(self.damage / rate - 1e-9))


@dataclass(frozen=True)
class AircraftDamageReport:
    unit: str
    health: float | None
    recovered: bool
    x: float | None
    z: float | None
    ejected: bool
    killed: bool
    crashed: bool
    pre_crash_health: float | None
    hit: bool
    landing_place: int | None = None
    landing_name: str | None = None


@dataclass(frozen=True)
class DamageDisposition:
    unit: str
    flying: FlyingUnit
    health: float | None
    recoverable: bool
    reason: str = ""


@dataclass(frozen=True)
class AircraftWriteoff:
    """An abandoned airframe, not a statement about the pilot's fate."""

    unit: str
    aircraft: str
    price: float
    player: Player
    reason: str


def parse_reports(raw: Any) -> dict[str, AircraftDamageReport]:
    def number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value) if math.isfinite(value) else None

    def health(value: Any) -> float | None:
        result = number(value)
        return result if result is not None and 0 <= result <= 1 else None

    result: dict[str, AircraftDamageReport] = {}
    if not isinstance(raw, list):
        return result
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("unit"), str):
            continue
        unit = entry["unit"]
        if not unit or unit in result:
            continue
        crash_time = number(entry.get("crash_time"))
        damage_time = number(entry.get("first_damage_time"))
        # The collision itself must not qualify as pre-existing damage.
        prior = health(entry.get("pre_crash_health"))
        if crash_time is None or damage_time is None or crash_time - damage_time < 2:
            prior = None
        raw_place = entry.get("landing_place")
        # DCS carrier Airbase.getID() can return a numeric string.
        if (
            isinstance(raw_place, str)
            and len(raw_place) <= 20
            and raw_place.isdecimal()
        ):
            raw_place = int(raw_place)
        place = number(raw_place)
        result[unit] = AircraftDamageReport(
            unit,
            health(entry.get("health")),
            entry.get("recovered") is True,
            number(entry.get("x")),
            number(entry.get("z")),
            entry.get("ejected") is True,
            entry.get("killed") is True,
            crash_time is not None,
            prior,
            entry.get("hit") is True,
            int(place) if place is not None and place.is_integer() else None,
            (
                entry.get("landing_name")
                if isinstance(entry.get("landing_name"), str)
                else None
            ),
        )
    return result


def commit_reports(game: Game, debriefing: Debriefing) -> None:
    if not game.settings.aircraft_maintenance_enabled:
        return
    state = debriefing.state_data
    mission_id = state.aircraft_damage_mission_id
    if not mission_id:
        return
    applied: set[str] = getattr(game, "_aircraft_maintenance_applied", set())
    if mission_id in applied:
        return
    game._aircraft_maintenance_applied = applied
    applied.add(mission_id)
    for result in list(damage_dispositions(game, debriefing)):
        squadron = result.flying.flight.squadron
        if result.recoverable:
            admit(game, squadron, f"{mission_id}:{result.unit}", result.health)
            continue
        if getattr(result.flying.flight, "remain_at_destination", False) and getattr(
            result.flying.flight, "is_helo", False
        ):
            # Air-assault remain has already removed this flight from its origin.
            continue
        # Never subtract existing workshop airframes or duplicate DCS losses.
        if squadron.owned_aircraft <= damaged_count(squadron):
            continue
        squadron.owned_aircraft -= 1
        squadron.destroyed_aircraft = getattr(squadron, "destroyed_aircraft", 0) + 1
        squadron.untasked_aircraft = min(
            squadron.untasked_aircraft,
            max(
                0,
                squadron.owned_aircraft
                + min(0, squadron.pending_deliveries)
                - damaged_count(squadron),
            ),
        )
        if not hasattr(debriefing, "aircraft_writeoffs"):
            debriefing.aircraft_writeoffs = []
        debriefing.aircraft_writeoffs.append(
            AircraftWriteoff(
                result.unit,
                squadron.aircraft.display_name,
                squadron.aircraft.price,
                squadron.player,
                result.reason,
            )
        )
        # TODO(CSAR): aircraft recovery and pilot rescue are separate decisions.
        # A survivor nearer enemy territory may still generate a CSAR objective.
        # Do not send this airframe-only loss through pilot death resolution.
        _notify(
            game,
            squadron,
            f"{squadron}: one damaged aircraft written off — {result.reason}.",
        )


def recoverable_damage(
    game: Game, debriefing: Debriefing
) -> Iterator[tuple[str, FlyingUnit, float | None]]:
    """The same recovered damaged airframes for workshop admission and debriefing."""
    for result in damage_dispositions(game, debriefing):
        if result.recoverable:
            yield result.unit, result.flying, result.health


def damage_dispositions(
    game: Game, debriefing: Debriefing, *, require_workshops: bool = True
) -> Iterator[DamageDisposition]:
    """Classify only confirmed damaged returns, never silence or missing telemetry."""
    if require_workshops and not getattr(
        game.settings, "aircraft_maintenance_enabled", False
    ):
        return
    state = getattr(debriefing, "state_data", None)
    reports = getattr(state, "aircraft_damage", {})
    if not reports:
        return
    losses = {id(loss) for loss in debriefing.air_losses.losses}
    for name, report in reports.items():
        flying = debriefing.unit_map.flight(name)
        if flying is None or report.ejected or report.killed:
            continue
        squadron = flying.flight.squadron
        lost = id(flying) in losses
        ignored_crash = (
            lost
            and game.settings.ignore_non_combat_air_losses
            and debriefing.is_non_combat_loss(flying)
        )
        if lost and not ignored_crash:
            continue
        reason = ""
        value: float | None
        if ignored_crash:
            if not report.crashed or report.pre_crash_health is None:
                continue
            value = report.pre_crash_health
        else:
            if not report.recovered or report.crashed:
                continue
            value = report.health
            if value is None and not report.hit:
                continue
            if report.x is None or report.z is None:
                continue
            friendly, enemy = math.inf, math.inf
            for base in game.theater.controlpoints:
                if base.sunk or base.captured.is_neutral:
                    continue
                distance = (base.position.x - report.x) ** 2 + (
                    base.position.y - report.z
                ) ** 2
                if base.captured == squadron.player:
                    friendly = min(friendly, distance)
                else:
                    enemy = min(enemy, distance)
            arrival = getattr(flying.flight, "arrival", None)
            returned_to_fleet = (
                arrival is not None
                and arrival.is_fleet
                and not arrival.sunk
                and arrival.captured == squadron.player
                and report.landing_place is not None
                and report.landing_place == arrival.airdrome_id_for_landing
            )
            # Runtime airbase IDs need not equal editor unit IDs. Carrier airbase
            # names resolve through the mission's ship mapping instead of comparing
            # those unrelated numeric namespaces or a moving ship's old position.
            if report.landing_name:
                lookup = getattr(debriefing.unit_map, "theater_units", lambda _: None)
                mapping = lookup(report.landing_name)
                if mapping is not None:
                    unit = mapping.theater_unit
                    landed_at = unit.ground_object.control_point
                    returned_to_fleet = (
                        unit.is_ship
                        and unit.alive
                        and landed_at.is_fleet
                        and not landed_at.sunk
                        and landed_at.captured == squadron.player
                    )
            if not returned_to_fleet and (friendly == math.inf or friendly >= enemy):
                reason = "landing is not closer to a friendly base than an enemy base"
        # Recovered airframes return to their squadron's workshop. No damaged
        # airframe can fly away from a base captured during the mission.
        if squadron.location.sunk or squadron.location.captured != squadron.player:
            reason = "the squadron's workshop base was lost"
        if value is not None and (not math.isfinite(value) or not 0 < value < 1):
            continue
        yield DamageDisposition(name, flying, value, not reason, reason)


def repairs(squadron: Squadron) -> list[AircraftRepair]:
    """Old saves have no damaged airframes."""
    return getattr(squadron, "aircraft_repairs", [])


def _notify(game: Game, squadron: Squadron, text: str) -> None:
    if squadron.player.is_blue:
        game.message("Aircraft workshop", text)
    else:
        # The public event log must not reveal hidden enemy base inventories.
        logging.info("Aircraft workshop: %s", text)


def damaged_count(squadron: Squadron) -> int:
    return len(repairs(squadron))


def repair_rate(game: Game) -> float:
    return max(0.01, min(1.0, game.settings.aircraft_repair_percent / 100))


def mechanics(game: Game, base: ControlPoint) -> int:
    from game.theater import ParkingType

    slots = base.total_aircraft_parking(
        ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
    )
    ratio = max(1, game.settings.aircraft_slots_per_mechanic)
    return max(2, math.ceil(slots / ratio)) + getattr(
        base, "extra_aircraft_mechanics", 0
    )


def base_jobs(game: Game, base: ControlPoint) -> list[tuple[Squadron, AircraftRepair]]:
    jobs = [
        (squadron, job)
        for coalition in game.coalitions
        for squadron in coalition.air_wing.iter_squadrons()
        if squadron.location == base
        for job in repairs(squadron)
    ]
    return sorted(jobs, key=lambda item: (item[1].admitted_turn, item[1].sequence))


def admit(game: Game, squadron: Squadron, source: str, health: float | None) -> bool:
    if not game.settings.aircraft_maintenance_enabled:
        return False
    if any(job.source == source for job in repairs(squadron)):
        return False
    if health is not None and (not math.isfinite(health) or not 0 < health < 1):
        return False
    # Pending healthy sales already remove inventory from the next-turn pool.
    if len(repairs(squadron)) >= squadron.owned_aircraft + min(
        0, squadron.pending_deliveries
    ):
        return False
    sequence = getattr(game, "_aircraft_repair_sequence", 0) + 1
    game._aircraft_repair_sequence = sequence
    squadron.aircraft_repairs.append(
        AircraftRepair(
            source, game.turn, sequence, None if health is None else 1 - health
        )
    )
    # Do not reintroduce aircraft already claimed by this mission's flights.
    squadron.untasked_aircraft = min(
        squadron.untasked_aircraft,
        max(
            0,
            squadron.owned_aircraft
            + min(0, squadron.pending_deliveries)
            - len(repairs(squadron)),
        ),
    )
    _notify(
        game,
        squadron,
        f"{squadron}: damaged aircraft recovered for repair at {squadron.location.name}.",
    )
    return True


def sale_value(game: Game, squadron: Squadron) -> float:
    return squadron.aircraft.price * game.settings.damaged_aircraft_sale_percent / 100


def remove_damaged(
    game: Game, squadron: Squadron, *, refund: bool
) -> tuple[int, float]:
    """Sell with explicit consent, or write off immobile airframes on base loss."""
    count = len(repairs(squadron))
    value = count * sale_value(game, squadron) if refund else 0.0
    squadron.aircraft_repairs.clear()
    squadron.owned_aircraft = max(0, squadron.owned_aircraft - count)
    if not refund:
        squadron.destroyed_aircraft = getattr(squadron, "destroyed_aircraft", 0) + count
    if refund and count:
        squadron.coalition.adjust_budget(value)
        squadron.damaged_aircraft_sale_income = (
            getattr(squadron, "damaged_aircraft_sale_income", 0.0) + value
        )
    if count:
        action = "sold" if refund else "lost with their base"
        _notify(game, squadron, f"{squadron}: {count} damaged aircraft {action}.")
    return count, value


def _require_base(game: Game, base: ControlPoint) -> None:
    if not game.settings.aircraft_maintenance_enabled:
        raise ValueError("Aircraft maintenance is disabled")
    if base.sunk:
        raise ValueError("The workshop's ship has sunk")


def hire_mechanic(game: Game, base: ControlPoint) -> None:
    _require_base(game, base)
    coalition = game.coalition_for(base.captured)
    price = game.settings.aircraft_mechanic_cost / 1_000_000
    if coalition.budget < price:
        raise ValueError("Not enough funds to hire a mechanic")
    coalition.adjust_budget(-price)
    base.extra_aircraft_mechanics = getattr(base, "extra_aircraft_mechanics", 0) + 1


def sell_damaged(game: Game, squadron: Squadron, job_id: str) -> float:
    _require_base(game, squadron.location)
    if squadron.location.captured != squadron.player:
        raise ValueError("The squadron's base is no longer friendly")
    job = next((item for item in repairs(squadron) if item.id == job_id), None)
    if job is None:
        raise ValueError("This damaged aircraft is no longer in the workshop")
    value = sale_value(game, squadron)
    squadron.aircraft_repairs.remove(job)
    squadron.owned_aircraft -= 1
    squadron.coalition.adjust_budget(value)
    squadron.damaged_aircraft_sale_income = (
        getattr(squadron, "damaged_aircraft_sale_income", 0.0) + value
    )
    _notify(game, squadron, f"{squadron}: one damaged aircraft sold for ${value:.3f}M.")
    return value


def _assign_mechanics(
    jobs: list[AircraftRepair], count: int, rate: float
) -> dict[str, int]:
    """FIFO first assignments, then share spare staff without wasting repair work.

    Each mechanic works on only one airframe in a turn. Extra staff rotate through
    assigned airframes, capped at the staff needed to finish each repair this turn.
    """
    assigned = {job.id: 0 for job in jobs}
    active = jobs[:count]
    for job in active:
        assigned[job.id] = 1
    spare = count - len(active)
    while spare:
        helpers = [job for job in active if assigned[job.id] < job.working_turns(rate)]
        if not helpers:
            break
        for job in helpers[:spare]:
            assigned[job.id] += 1
            spare -= 1
    return assigned


def _forecast(
    jobs: list[AircraftRepair], count: int, rate: float, turn: int
) -> dict[str, tuple[int, int, int]]:
    """Simulate the same allocation as advance without modifying saved repairs.

    Return working turns, turns before the first working turn, and readiness.
    Reallocation after completion and the admission delay both affect the result.
    """
    pending = [replace(job) for job in jobs]
    first: dict[str, int] = {}
    working = {job.id: 0 for job in jobs}
    result = {}
    step = 0
    while pending:
        step += 1
        eligible = [job for job in pending if turn + step > job.admitted_turn + 1]
        assigned = _assign_mechanics(eligible, count, rate)
        for job in eligible:
            staff = assigned[job.id]
            if not staff:
                continue
            first.setdefault(job.id, step)
            working[job.id] += 1
            if job.damage is not None:
                job.damage = max(0, job.damage - staff * rate)
            if job.damage is None or job.damage <= 1e-9:
                result[job.id] = (working[job.id], first[job.id] - 1, step)
                pending.remove(job)
    return result


def advance(game: Game) -> None:
    """Exactly one repair step per turn; never called by mission regeneration."""
    if getattr(game, "_aircraft_workshop_turn", -1) == game.turn:
        return
    game._aircraft_workshop_turn = game.turn
    for base in game.theater.controlpoints:
        jobs = base_jobs(game, base)
        for squadron, _ in jobs:
            if base.sunk or base.captured != squadron.player:
                remove_damaged(game, squadron, refund=False)
        jobs = base_jobs(game, base)
        if not game.settings.aircraft_maintenance_enabled:
            for squadron, job in jobs:
                squadron.aircraft_repairs.remove(job)
            continue
        eligible = [(sq, job) for sq, job in jobs if game.turn > job.admitted_turn + 1]
        assigned = _assign_mechanics(
            [job for _, job in eligible], mechanics(game, base), repair_rate(game)
        )
        for squadron, job in eligible:
            staff = assigned[job.id]
            if not staff:
                continue
            if job.damage is not None:
                job.damage = max(0, job.damage - staff * repair_rate(game))
            if job.damage is None or job.damage <= 1e-9:
                squadron.aircraft_repairs.remove(job)
                _notify(
                    game, squadron, f"{squadron}: one aircraft repaired at {base.name}."
                )


def workshop_view(game: Game, base: ControlPoint) -> dict[str, Any]:
    count = mechanics(game, base)
    jobs = base_jobs(game, base) if game.settings.aircraft_maintenance_enabled else []
    rate = repair_rate(game)
    airframes = [job for _, job in jobs]
    next_working_turn = max(
        game.turn + 1,
        min((job.admitted_turn + 2 for job in airframes), default=game.turn + 1),
    )
    assigned = _assign_mechanics(
        [job for job in airframes if next_working_turn > job.admitted_turn + 1],
        count,
        rate,
    )
    forecast = _forecast(airframes, count, rate, game.turn)
    busy = sum(assigned.values())
    entries = []
    for squadron, job in jobs:
        staff = assigned.get(job.id, 0)
        duration, wait, ready = forecast[job.id]
        entries.append(
            {
                "id": job.id,
                "squadron_id": str(squadron.id),
                "squadron": str(squadron),
                "aircraft": squadron.aircraft.display_name,
                "health_percent": None if job.health is None else job.health * 100,
                "status": "repairing" if staff else "queued",
                "assigned_mechanics": staff,
                "repair_capacity_percent_per_turn": staff * rate * 100,
                "working_turns_remaining": duration,
                "queue_turns": wait,
                "turns_until_ready": ready,
                "sale_price_m": sale_value(game, squadron),
            }
        )
    return {
        "base_id": str(base.id),
        "base": base.name,
        "enabled": game.settings.aircraft_maintenance_enabled,
        "mechanics": count,
        "busy": busy,
        "free": count - busy,
        "mechanic_cost_dollars": game.settings.aircraft_mechanic_cost,
        "mechanic_price_m": game.settings.aircraft_mechanic_cost / 1_000_000,
        "repair_percent_per_turn": game.settings.aircraft_repair_percent,
        "next_working_turn": next_working_turn if jobs else None,
        "aircraft": entries,
    }
