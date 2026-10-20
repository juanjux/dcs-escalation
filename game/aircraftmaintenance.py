"""Persistent aircraft repairs, shared base mechanics and explicit damaged sales."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing
    from game.squadrons import Squadron
    from game.theater import ControlPoint


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
        place = number(entry.get("landing_place"))
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
    losses = {id(loss) for loss in debriefing.air_losses.losses}
    for name, report in state.aircraft_damage.items():
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
            if not returned_to_fleet and (friendly == math.inf or friendly >= enemy):
                continue
        # Recovered airframes return to their squadron's workshop. No damaged
        # airframe can fly away from a base captured during the mission.
        if squadron.location.sunk or squadron.location.captured != squadron.player:
            continue
        admit(game, squadron, f"{mission_id}:{name}", value)


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
    price = game.settings.aircraft_mechanic_price
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
        # Each mechanic handles one aircraft per turn. Completing a small repair
        # does not also repair the next queued aircraft at the same boundary.
        for squadron, job in jobs[: mechanics(game, base)]:
            if game.turn <= job.admitted_turn + 1:
                continue
            if job.damage is not None:
                job.damage = max(0, job.damage - repair_rate(game))
            if job.damage is None or job.damage <= 1e-9:
                squadron.aircraft_repairs.remove(job)
                _notify(
                    game, squadron, f"{squadron}: one aircraft repaired at {base.name}."
                )


def workshop_view(game: Game, base: ControlPoint) -> dict[str, Any]:
    count = mechanics(game, base)
    jobs = base_jobs(game, base) if game.settings.aircraft_maintenance_enabled else []
    # Forecast by assigning each queued job to the first mechanic that becomes
    # free. Ongoing jobs retain their mechanic; all durations use the same rate.
    availability = [0] * count
    entries = []
    for index, (squadron, job) in enumerate(jobs):
        mechanic = min(range(count), key=availability.__getitem__)
        wait = availability[mechanic]
        duration = job.working_turns(repair_rate(game))
        admission_delay = max(0, job.admitted_turn + 1 - game.turn)
        ready = max(wait, admission_delay) + duration
        availability[mechanic] = ready
        entries.append(
            {
                "id": job.id,
                "squadron_id": str(squadron.id),
                "squadron": str(squadron),
                "aircraft": squadron.aircraft.display_name,
                "health_percent": None if job.health is None else job.health * 100,
                "status": "repairing" if index < count else "queued",
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
        "busy": min(count, len(jobs)),
        "free": max(0, count - len(jobs)),
        "mechanic_price_m": game.settings.aircraft_mechanic_price,
        "repair_percent_per_turn": game.settings.aircraft_repair_percent,
        "aircraft": entries,
    }
