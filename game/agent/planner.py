"""Write path for the OPFOR-AI feature.

Turns the LLM's intents into real game state by reusing the engine — the same
PackageFulfiller/PackageBuilder the scripted commander uses (see
game/commander/tasks/packageplanningtask.py), so flight planning, squadron
selection, escorts, loadouts and budgeting come for free. Every op returns a
structured per-item result so partial failures are reported, not raised.
"""

from __future__ import annotations

import contextlib
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Iterable, TYPE_CHECKING, Union
from uuid import UUID

from game.ato.flighttype import FlightType
from game.commander.missionproposals import EscortType, ProposedFlight, ProposedMission
from game.commander.packagefulfiller import PackageFulfiller
from game.profiling import MultiEventTracer

from game.agent import schemas, views
from game.dcs.skills import SKILL_LADDER
from game.squadrons import friendship
from game.sim.missionresultsprocessor import killer_sentence
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.utils import meters, nautical_miles

if TYPE_CHECKING:
    from game import Game
    from game.theater import MissionTarget


_ESCORTS = {
    "air": EscortType.AirToAir,
    "airtoair": EscortType.AirToAir,
    "cap": EscortType.AirToAir,
    "escort": EscortType.AirToAir,
    "sead": EscortType.Sead,
    "dead": EscortType.Sead,
    "refuel": EscortType.Refuel,
    "tanker": EscortType.Refuel,
}


_TASK_ALIASES = {
    # Names the LLM naturally reaches for that aren't FlightType members. A bare "CAP"
    # means area/base/fleet combat air patrol -> BARCAP (TARCAP is tied to a strike
    # package). Keep these in sync with the task list in docs/howtoplay.md.
    "CAP": FlightType.BARCAP,
    "COMBAT_AIR_PATROL": FlightType.BARCAP,
}


def _flight_type(name: str) -> FlightType:
    raw = name.strip()
    key = raw.upper().replace(" ", "_").replace("-", "_")
    try:
        return FlightType[key]
    except KeyError:
        pass
    if key in _TASK_ALIASES:
        return _TASK_ALIASES[key]
    for ft in FlightType:
        if str(getattr(ft, "value", "")).upper() == raw.upper():
            return ft
    raise ValueError(f"unknown task {name!r}")


def _escort_type(name: str | None) -> EscortType | None:
    if not name:
        return None
    key = name.strip().lower().replace(" ", "").replace("-", "")
    try:
        return _ESCORTS[key]
    except KeyError:
        raise ValueError(f"unknown escort type {name!r}")


def _preferred_aircraft(game: Game, side: str, squadron_id: str | None):
    """AircraftType to bias the squadron picker toward (None = let the engine pick)."""
    if not squadron_id:
        return None
    return _resolve_squadron(game, side, squadron_id).aircraft


def _preferred_squadron(game: Game, side: str, squadron_id: str | None):
    """The squadron itself, when one was named.

    The aircraft type alone was never enough: two squadrons flying the same airframe
    both pass that filter and the planner takes whichever is nearer the target, so a
    package asked for one of them and spent the other's aircraft -- and the flights
    already counted against that other squadron were scrubbed later for having none
    left. An id is an answer, not a hint."""
    if not squadron_id:
        return None
    try:
        return _resolve_squadron(game, side, squadron_id)
    except Exception:
        # A bad id is reported by the pre-check; nothing is pinned here.
        return None


def _free_aircraft_for(game: Game, side: str, flight_spec) -> int:
    """Most untasked aircraft a single squadron has free for this flight — the pinned
    squadron if `squadron_id` is set, else the best among squadrons capable of the task.
    0 means none free (leave the count alone; the planner reports the shortage)."""
    squadron_id = getattr(flight_spec, "squadron_id", None)
    if squadron_id:
        try:
            return _resolve_squadron(game, side, squadron_id).untasked_aircraft
        except Exception:
            return 0
    try:
        task = _flight_type(flight_spec.task)
    except ValueError:
        return 0

    def _capable(sq) -> bool:
        try:
            return bool(sq.capable_of(task))
        except Exception:
            return False

    squadrons = views.coalition_for_side(game, side).air_wing.iter_squadrons()
    return max((sq.untasked_aircraft for sq in squadrons if _capable(sq)), default=0)


def _clamped_count(game: Game, side: str, flight_spec) -> int:
    """Cap the requested count at the airframe's max_group_size AND at the aircraft
    actually free — the SAME `min(available, aircraft.max_group_size)` the player's
    flight creator enforces. The max_group_size cap stops an over-large flight (e.g. 24
    H-6J, whose max is 4) silently generating only max_group_size units and losing the
    rest; the availability cap auto-trims an over-ask (request 4, only 3 free -> plan 3)
    into a partial flight instead of rejecting it. For a bigger raid than one squadron
    can field the LLM still creates several flights, exactly like the human."""
    count = int(getattr(flight_spec, "count", 2))
    aircraft = None
    squadron_id = getattr(flight_spec, "squadron_id", None)
    if squadron_id:
        try:
            aircraft = _resolve_squadron(game, side, squadron_id).aircraft
        except Exception:
            aircraft = None
    if aircraft is None:
        from game.dcs.aircrafttype import AircraftType

        candidates = AircraftType.priority_list_for_task(_flight_type(flight_spec.task))
        aircraft = candidates[0] if candidates else None
    if aircraft is not None:
        count = min(count, aircraft.max_group_size)
    available = _free_aircraft_for(game, side, flight_spec)
    if available > 0:
        count = min(count, available)
    return max(1, count)


@contextlib.contextmanager
def _forced_task_assign(game: Game, side: str, specs):
    """Temporarily let the LLM-chosen squadrons be auto-assigned to their flight's task,
    so the engine picks a squadron it otherwise would not auto-assign — exactly what the
    player does assigning a flight by hand. Physical limits (range/fuel/availability)
    still apply; only the auto-assign toggle is bypassed. Restored on exit."""
    added: list = []
    for spec in specs:
        for flight in getattr(spec, "flights", []):
            squadron_id = getattr(flight, "squadron_id", None)
            if not squadron_id:
                continue
            try:
                squadron = _resolve_squadron(game, side, squadron_id)
                task = _flight_type(flight.task)
            except Exception:
                # Bad squadron_id / unknown task: skip forcing it (the real plan or the
                # pre-check will report the real problem). Skipping keeps this context
                # non-raising so a later valid flight's forced task is still restored.
                continue
            if task not in squadron.auto_assignable_mission_types:
                squadron.auto_assignable_mission_types.add(task)
                added.append((squadron, task))
    try:
        yield
    finally:
        for squadron, task in added:
            squadron.auto_assignable_mission_types.discard(task)


def _build_loadout(aircraft, task: FlightType, spec):
    """Build a Loadout from a FlightSpec.loadout: a named loadout or {pylon: clsid} map."""
    from game.ato.loadouts import Loadout
    from game.data.weapons import Weapon

    if isinstance(spec, dict):
        pylons = {int(num): Weapon.with_clsid(clsid) for num, clsid in spec.items()}
        return Loadout("Custom (AI)", pylons, date=None, is_custom=True)
    payload = aircraft.dcs_unit_type.loadout_by_name(str(spec))
    if payload is None:
        raise ValueError(f"no loadout named {spec!r} for {aircraft.display_name}")
    return Loadout(
        str(spec),
        {i: Weapon.with_clsid(d["clsid"]) for i, d in payload},
        date=None,
    )


def _apply_loadouts(package, flight_specs) -> None:
    """Set each spec'd loadout on the matching package flight (by task, first unused)."""
    used: set[int] = set()
    for flight_spec in flight_specs:
        loadout_spec = getattr(flight_spec, "loadout", None)
        if not loadout_spec:
            continue
        task = _flight_type(flight_spec.task)
        for flight in package.flights:
            if id(flight) in used or flight.flight_type != task:
                continue
            loadout = _build_loadout(flight.unit_type, task, loadout_spec)
            for member in flight.iter_members():
                member.loadout = loadout
                member.use_custom_loadout = True
            used.add(id(flight))
            break


def _apply_tot_offsets(package, flight_specs) -> None:
    """Give each spec'd flight its own time over target relative to the package's."""
    used: set[int] = set()
    for flight_spec in flight_specs:
        minutes = getattr(flight_spec, "tot_offset_min", None)
        if minutes is None:
            continue
        task = _flight_type(flight_spec.task)
        for flight in package.flights:
            if id(flight) in used or flight.flight_type != task:
                continue
            apply_tot_offset(flight, minutes)
            used.add(id(flight))
            break


def _apply_remain(package, flight_specs) -> None:
    """Flag matching helo AIR_ASSAULT flights to remain at the objective (land + stay,
    no return leg) and rebuild the plan so the return leg is dropped -- the player's
    "Remain at the assault destination" checkbox. Ignored for non-helo / non-air-assault
    flights (only helos can be one-way assaulted)."""
    used: set[int] = set()
    for flight_spec in flight_specs:
        if not getattr(flight_spec, "remain", False):
            continue
        if _flight_type(flight_spec.task) != FlightType.AIR_ASSAULT:
            continue
        for flight in package.flights:
            if (
                id(flight) in used
                or flight.flight_type != FlightType.AIR_ASSAULT
                or not flight.is_helo
            ):
                continue
            flight.remain_at_destination = True
            flight.recreate_flight_plan()
            used.add(id(flight))
            break


def earliest_tot_duration(package) -> tuple[timedelta, str] | None:
    """How long before this package CAN be over its target, exactly, plus the base that
    sets the limit — the slowest flight's startup, taxi, takeoff and transit
    (``FlightPlan.minimum_duration_from_start_to_tot``). This is the same quantity
    ``TotEstimator.earliest_tot`` uses for an ASAP package, so an ASAP TOT sits exactly
    on it. Compare against it in full precision: rounding both sides to minutes made
    every ASAP package with a fractional minimum look a minute late.

    Asking for less is not merely optimistic, it damages the mission. Flight plans are
    built backwards from the TOT, so an unreachable one puts the push time before the
    mission starts; the hold point then emits a release timer of (push time - start),
    which goes negative, and DCS never fires a trigger scheduled for a negative time.
    Returns None when nothing in the package can be measured.
    """
    worst: timedelta | None = None
    where = ""
    for flight in package.flights:
        try:
            need = (
                flight.flight_plan.minimum_duration_from_start_to_tot()
                - flight.flight_plan.tot_offset
            )
        except Exception:
            continue
        if worst is None or need > worst:
            worst = need
            where = getattr(flight.departure, "name", "") or ""
    if worst is None:
        return None
    return worst, where


def earliest_tot_minutes(package, now: datetime) -> tuple[int, str] | None:
    """``earliest_tot_duration`` as whole minutes, rounded UP — the smallest integer
    ``tot_minutes`` that is actually reachable. For reporting and for clamping an
    explicit request; never for deciding whether an existing TOT is late."""
    duration = earliest_tot_duration(package)
    if duration is None:
        return None
    return math.ceil(duration[0].total_seconds() / 60), duration[1]


def tot_shortfall(
    package, now: datetime, tot: datetime | None
) -> tuple[int, str] | None:
    """(earliest whole minute, limiting base) when the package cannot make ``tot``, else
    None.

    Compared in full precision on purpose. Rounding both sides to minutes reported every
    ASAP package with a fractional minimum as a minute late -- ``round(28.2) = 28``
    against ``ceil(28.2) = 29`` -- and an ASAP TOT sits EXACTLY on the minimum by
    construction (``TotEstimator.earliest_tot`` is the same computation). The half-minute
    grace absorbs a plan rebuilt since the TOT was set; a TOT that is genuinely too early
    is short by minutes, not by seconds.
    """
    duration = earliest_tot_duration(package)
    if duration is None or tot is None:
        return None
    needed, where = duration
    if tot + timedelta(seconds=30) >= now + needed:
        return None
    return math.ceil(needed.total_seconds() / 60), where


def _apply_tot(package, spec, now: datetime) -> None:
    """Set the package's Time-On-Target from the spec: a manual TOT (``tot_minutes`` into
    the mission) when given, else ASAP. Mirrors the player's set_tot/set_asap — flight-plan
    TOTs derive from ``package.time_over_target``, so setting it is enough. An unreachable
    TOT is raised to the earliest one the package can actually make."""
    tot_minutes = getattr(spec, "tot_minutes", None)
    if tot_minutes is not None:
        package.auto_asap = False
        floor = earliest_tot_minutes(package, now)
        if floor is not None and tot_minutes < floor[0]:
            tot_minutes = floor[0]
        package.time_over_target = now + timedelta(minutes=tot_minutes)
    else:
        package.set_tot_asap(now)


def _mission_window_min(game: Game) -> int:
    """The player's desired mission duration in whole minutes (the TOT window).

    Settings stores it as a ``timedelta`` named ``desired_player_mission_duration``;
    an earlier ``..._min`` attribute lookup never matched and silently fell back to 60,
    so a non-default window (e.g. 80) was ignored by evaluate/validate."""
    dur = getattr(game.settings, "desired_player_mission_duration", None)
    if dur is None:
        return 60
    try:
        return int(dur.total_seconds() // 60)
    except AttributeError:
        return int(dur)  # tolerate a plain-number setting


def _new_map_events():
    """A GameUpdateEvents to collect live-map changes for an OPFOR-AI write."""
    from game.sim.gameupdateevents import GameUpdateEvents

    return GameUpdateEvents()


def _push_map_events(events) -> None:
    """Send collected changes to the live web map so an OPFOR-AI write shows immediately
    (the player's UI does the same). No-op when the server isn't running (headless tests).
    """
    try:
        from game.server import EventStream

        EventStream.put_nowait(events)
    except Exception:
        pass


def resolve_target(game: Game, target_id: str) -> MissionTarget:
    """Resolve a target id to a control point or ground object."""
    try:
        uid: UUID | None = UUID(str(target_id))
    except (ValueError, AttributeError, TypeError):
        uid = None
    if uid is not None:
        try:
            cp = game.theater.find_control_point_by_id(uid)
        except Exception:
            cp = None  # raises (not returns None) when the id is not a control point
        if cp is not None:
            return cp
    for cp in game.theater.controlpoints:
        for tgo in cp.ground_objects:
            if str(tgo.id) == str(target_id):
                return tgo
    for front in game.theater.conflicts():
        if str(front.id) == str(target_id):
            return front
    # Convoys and cargo ships carry no id of their own, so they are addressed by the
    # generated name turn_context reports -- the same handle the player's "Departing
    # Convoys" Attack button acts on.
    for coalition in (game.blue, game.red):
        for transports in (
            coalition.transfers.convoys,
            coalition.transfers.cargo_ships,
        ):
            for transport in transports:
                if transport.name == str(target_id):
                    return transport
    raise ValueError(f"no target with id {target_id!r}")


def _coerce(spec: Union[schemas.PackageSpec, dict]) -> schemas.PackageSpec:
    return (
        spec if isinstance(spec, schemas.PackageSpec) else schemas.PackageSpec(**spec)
    )


def _flight_label(f) -> str:
    """Short human id for a flight spec (task + squadron + escort), for error/dropped reports."""
    parts = [str(getattr(f, "task", "?")).upper()]
    sq = getattr(f, "squadron_id", None)
    if sq:
        parts.append(f"from {sq}")
    esc = getattr(f, "escort", None)
    if esc:
        parts.append(f"(escort {esc})")
    return " ".join(parts)


def _diagnose_flights(
    game: Game, side: str, spec: schemas.PackageSpec, flights: list
) -> list[tuple[int, str, str | None]]:
    """Per-flight satisfiability check. For each flight returns ``(pos, label, problem)`` where
    ``problem`` is a short reason it can't be filled — capability (the faction has no airframe
    for the role), availability (no capable squadron has enough untasked aircraft, COUNTING
    earlier flights that draw from the same squadron), out-of-range, or an escort with no strike
    parent — or ``None`` if it looks individually fillable. Fully guarded (degrades to 'no
    problem' rather than raising). Reused by the failure message AND the partial-fulfilment
    pre-filter."""
    from collections import defaultdict

    def _try(fn, *a):
        try:
            return fn(*a)
        except Exception:
            return None

    try:
        squadrons = list(views.coalition_for_side(game, side).air_wing.iter_squadrons())
    except Exception:
        return [(i, _flight_label(f), None) for i, f in enumerate(flights)]
    target = _try(resolve_target, game, spec.target_id)
    used: dict[int, int] = defaultdict(
        int
    )  # squadron -> aircraft reserved by earlier flights

    def _over_the_limit(squadron, task, count) -> str | None:
        """How far past the auto-planner's limit this squadron is, or None if the
        limit is not what stopped it. Told apart by asking again with it lifted."""
        if target is None:
            return None
        if not _try(
            squadron.can_auto_assign_mission, target, task, count, False, True, True
        ):
            return None
        away = _try(
            lambda: meters(target.distance_to(squadron.location)).nautical_miles
        )
        limit = _try(
            lambda: max(
                squadron.aircraft.max_mission_range,
                nautical_miles(game.settings.max_mission_range_planes),
            ).nautical_miles
        )
        if away is None or limit is None:
            return ""
        return f" ({away:.0f} NM to the target, limit {limit:.0f} NM)"

    def _why_not_assignable(f, candidates, free, task, count) -> str:
        """Why no squadron would take this flight, and what would change that.

        Range and role both used to report "out of the auto-planner's range" and both
        suggested passing squadron_id, which the caller may already have passed and
        which does not affect the range in any case.
        """
        over = next(
            (
                d
                for d in (_over_the_limit(s, task, count) for s in free)
                if d is not None
            ),
            None,
        )
        if over is None:
            # It fails with the limit lifted, so the limit is not the cause.
            if f.squadron_id:
                name = _try(lambda: candidates[0].name) or f.squadron_id
                return (
                    f"{name} is capable and free, but the planner will not assign it "
                    "this mission — its base, or the crews it can put up this turn"
                )
            role = _try(lambda: task.value) or str(f.task).upper()
            return (
                f"no squadron auto-assigns {role} (role, base or crews) — pass "
                "squadron_id to force a capable one, as a human assigns by hand"
            )
        also = "" if f.squadron_id else ", or squadron_id to pick the squadron yourself"
        return (
            f"capable and free, but out of the auto-planner's range{over}"
            f" — add ignore_range:true to send it anyway{also}"
        )

    out: list[tuple[int, str, str | None]] = []
    for i, f in enumerate(flights):
        label = _flight_label(f)
        try:
            task = _flight_type(f.task)
        except ValueError:
            out.append((i, label, "unknown task"))
            continue
        count = _try(_clamped_count, game, side, f) or int(getattr(f, "count", 2))
        capable = [s for s in squadrons if _try(s.capable_of, task)]
        if not capable:
            out.append((i, label, "your faction has no airframe able to fly this role"))
            continue
        if f.squadron_id:
            sq = _try(_resolve_squadron, game, side, f.squadron_id)
            if sq is None:
                out.append((i, label, f"no squadron with id {f.squadron_id!r}"))
                continue
            if not _try(sq.capable_of, task):
                out.append((i, label, f"{sq.name} can't fly {f.task.upper()}"))
                continue
            candidates = [sq]
        else:
            candidates = capable
        free = [s for s in candidates if (s.untasked_aircraft - used[id(s)]) >= count]
        if not free:
            most = max(
                (s.untasked_aircraft - used[id(s)] for s in candidates), default=0
            )
            if any(used[id(s)] for s in candidates):
                after = " (after earlier flights in this package took theirs)"
            elif most <= 0 and any(
                _try(lambda s: s.owned_aircraft, s) for s in candidates
            ):
                # The squadron shows aircraft on hand, so "0 free" looks like a
                # contradiction unless we say where they went.
                after = " — its aircraft are already tasked in other packages"
            else:
                after = ""
            out.append(
                (
                    i,
                    label,
                    f"needs {count} aircraft but the most any candidate squadron has free is {most}{after}",
                )
            )
            continue
        assignable = None
        for s in free:
            if target is None or _try(
                s.can_auto_assign_mission,
                target,
                task,
                count,
                False,
                True,
                spec.ignore_range,
            ):
                assignable = s
                break
        if assignable is None:
            if f.escort:
                out.append(
                    (
                        i,
                        label,
                        "escort — attaches to the strike flights; fails if those weren't "
                        "planned or it can't reach them",
                    )
                )
            else:
                out.append(
                    (i, label, _why_not_assignable(f, candidates, free, task, count))
                )
            continue
        used[id(assignable)] += count  # this flight is fine on its own — reserve it
        out.append((i, label, None))
    return out


def _unfulfilled_reason(game: Game, side: str, spec: schemas.PackageSpec) -> str:
    """Human string of why a package (or the flights of one) couldn't be planned."""
    # Same forced-assign wrapper as the pre-check/plan, so the reason matches what would
    # actually happen (a squadron_id'd flight isn't reported "out of range" for a task
    # outside its auto-assign defaults).
    with _forced_task_assign(game, side, [spec]):
        diag = _diagnose_flights(game, side, spec, list(spec.flights))
    probs = [f"{label}: {p}" for _, label, p in diag if p]
    return "; ".join(probs) if probs else "no capable aircraft were free and in range"


def create_packages(
    game: Game, side: str, specs: list[Union[schemas.PackageSpec, dict]]
) -> list[schemas.CreateResult]:
    """Plan one package per spec, reusing PackageFulfiller, and add it to the ATO. PARTIAL by
    default: each spec's flights are pre-checked (``_diagnose_flights``) and only the fillable
    ones are planned; the rest are returned in ``CreateResult.dropped`` instead of scrubbing the
    whole package. Only if nothing is fillable is the package a failure."""
    coalition = views.coalition_for_side(game, side)
    now = game.conditions.start_time
    results: list[schemas.CreateResult] = []
    with MultiEventTracer() as tracer:
        for raw in specs:
            spec = _coerce(raw)
            target_name = spec.target_id
            try:
                target = resolve_target(game, spec.target_id)
                target_name = getattr(target, "name", spec.target_id)
                # Partial by default: pre-check each flight and keep only the fillable ones,
                # so one unfillable flight (no free aircraft / out of range / escort w/o
                # parent) doesn't discard the whole package — it's dropped + reported instead.
                # Diagnose under the SAME forced-assign the real plan uses (below), so a flight
                # that names a squadron_id isn't scrubbed as "out of range" for a task that
                # merely isn't in that squadron's auto-assign defaults (e.g. FC-1 flying BARCAP).
                with _forced_task_assign(game, side, [spec]):
                    diag = _diagnose_flights(game, side, spec, list(spec.flights))
                keep = [
                    f for f, (_i, _l, prob) in zip(spec.flights, diag) if prob is None
                ]
                dropped = [
                    schemas.DroppedFlight(flight=label, reason=prob)
                    for _i, label, prob in diag
                    if prob
                ]
                if not keep:
                    reason = "; ".join(
                        f"{d.flight}: {d.reason}" for d in dropped
                    ) or _unfulfilled_reason(game, side, spec)
                    results.append(
                        schemas.CreateResult(
                            ok=False,
                            target=target_name,
                            error="could not fulfil — " + reason,
                        )
                    )
                    continue
                proposed = [
                    ProposedFlight(
                        _flight_type(f.task),
                        _clamped_count(game, side, f),
                        _escort_type(f.escort),
                        preferred_type=_preferred_aircraft(game, side, f.squadron_id),
                        preferred_squadron=_preferred_squadron(
                            game, side, f.squadron_id
                        ),
                    )
                    for f in keep
                ]
                fulfiller = PackageFulfiller(
                    coalition, game.theater, game.db.flights, game.settings
                )
                with _forced_task_assign(game, side, [spec]):
                    package = fulfiller.plan_mission(
                        ProposedMission(target, proposed, asap=spec.asap),
                        1,
                        now,
                        tracer,
                        ignore_range=spec.ignore_range,
                    )
                if package is None or not package.flights:
                    # the planner disagreed with the pre-check (rare) — report the diagnosis
                    results.append(
                        schemas.CreateResult(
                            ok=False,
                            target=target_name,
                            error="could not fulfil — "
                            + _unfulfilled_reason(game, side, spec),
                        )
                    )
                    continue
                coalition.ato.add_package(package)
                try:
                    _apply_loadouts(package, keep)
                    _apply_tot_offsets(package, keep)
                    _apply_remain(package, keep)
                    _apply_tot(package, spec, now)
                    if spec.rationale:
                        package.custom_name = spec.rationale
                    index = len(coalition.ato.packages) - 1
                    result = schemas.CreateResult(
                        ok=True,
                        target=target_name,
                        package=views.build_package(index, package),
                        dropped=dropped or None,
                        idle_flyable_remaining=views.idle_flyable_total(game, side),
                    )
                except Exception:
                    # plan_mission has already claimed the aircraft and the pilots, and
                    # the package is in the ATO by now, so reporting the error without
                    # this left the caller a package it had been told did not exist:
                    # no TOT, no rationale, the crews unavailable to try again.
                    # remove_package hands both back, the same way evaluate_package
                    # rolls back its dry run. Building the answer is inside the same
                    # guard so that "an error came back" always means "nothing was
                    # added", whichever step failed.
                    coalition.ato.remove_package(package)
                    raise
                results.append(result)
            except Exception as exc:  # report, don't abort the whole batch
                results.append(
                    schemas.CreateResult(ok=False, target=target_name, error=str(exc))
                )
    return results


def evaluate_package(
    game: Game, side: str, spec: Union[schemas.PackageSpec, dict]
) -> schemas.EvaluateResult:
    """Dry-run a package: plan it, compute its time-over-target, and report whether the
    TOT fits the player's mission window — WITHOUT committing it (the plan is rolled
    back). Lets the LLM check feasibility + timing before deciding to create it."""
    coalition = views.coalition_for_side(game, side)
    now = game.conditions.start_time
    spec = _coerce(spec)
    target_name = spec.target_id
    try:
        target = resolve_target(game, spec.target_id)
        target_name = getattr(target, "name", spec.target_id)
        proposed = [
            ProposedFlight(
                _flight_type(f.task),
                _clamped_count(game, side, f),
                _escort_type(f.escort),
                preferred_type=_preferred_aircraft(game, side, f.squadron_id),
                preferred_squadron=_preferred_squadron(game, side, f.squadron_id),
            )
            for f in spec.flights
        ]
        with MultiEventTracer() as tracer, _forced_task_assign(game, side, [spec]):
            fulfiller = PackageFulfiller(
                coalition, game.theater, game.db.flights, game.settings
            )
            package = fulfiller.plan_mission(
                ProposedMission(target, proposed, asap=spec.asap),
                1,
                now,
                tracer,
                ignore_range=spec.ignore_range,
            )
        if package is None or not package.flights:
            return schemas.EvaluateResult(
                ok=False,
                target=target_name,
                error="could not fulfil — " + _unfulfilled_reason(game, side, spec),
            )
        # plan_mission already CLAIMS the aircraft; add then remove so they are released
        # again (a package's aircraft are returned when it leaves the ATO) — net-zero.
        coalition.ato.add_package(package)
        try:
            _apply_loadouts(package, spec.flights)
            _apply_remain(package, spec.flights)
            _apply_tot(package, spec, now)
            view = views.build_package(-1, package)
            tot = package.time_over_target
            window = _mission_window_min(game)
            tot_min = round((tot - now).total_seconds() / 60) if tot else None
            return schemas.EvaluateResult(
                ok=True,
                target=target_name,
                package=view,
                tot_minutes_into_mission=tot_min,
                mission_window_min=window,
                within_window=_within_window(tot_min, window),
            )
        finally:
            coalition.ato.remove_package(package)
    except Exception as exc:
        return schemas.EvaluateResult(ok=False, target=target_name, error=str(exc))


def flight_for_side(game, side: str, flight_id):
    """The flight with this id, but only if it belongs to ``side``.

    game.db.flights is a GLOBAL registry keyed by uuid, so looking a flight up by id
    alone reaches the human player's flights too. Reading their route would be a fog
    breach; editing their waypoints would be sabotage of the plan they are flying.
    Returns None when the id is unknown OR belongs to the other coalition -- the two
    are deliberately indistinguishable, so this cannot be used to probe for ids.
    """
    from uuid import UUID

    from game.agent.views import player_for_side

    try:
        flight = game.db.flights.get(UUID(str(flight_id)))
    except Exception:
        return None
    if flight is None:
        return None
    if flight.coalition.player is not player_for_side(side):
        return None
    return flight


def edit_waypoint(
    game: Game,
    side: str,
    flight_id: str,
    waypoint_idx: int,
    lat: float | None = None,
    lng: float | None = None,
    alt_m: float | None = None,
) -> schemas.OpResult:
    """Move/adjust an existing flight waypoint (position and/or altitude), like the
    player dragging it on the map. Waypoint 0 (takeoff) is immovable, and waypoints can
    NEVER be deleted — a deleted waypoint breaks the AI flight plan and crashes DCS, so
    this only edits one that already exists."""
    from dcs.mapping import LatLng, Point
    from game.server import GameContext
    from game.server.waypoints.routes import (
        update_package_waypoints_if_primary_flight,
    )
    from game.utils import meters

    flight = flight_for_side(game, side, flight_id)
    if flight is None:
        return schemas.OpResult(ok=False, error=f"no flight with id {flight_id!r}")
    try:
        if waypoint_idx <= 0:
            return schemas.OpResult(
                ok=False, error="waypoint 0 (takeoff) can't be moved"
            )
        waypoints = flight.flight_plan.waypoints
        if waypoint_idx > len(waypoints):
            return schemas.OpResult(
                ok=False, error=f"flight has no waypoint {waypoint_idx}"
            )
        waypoint = waypoints[waypoint_idx - 1]
        if lat is not None and lng is not None:
            waypoint.position = Point.from_latlng(
                LatLng(lat, lng), game.theater.terrain
            )
        warning = ""
        if alt_m is not None:
            waypoint.alt = meters(alt_m)
            warning = _too_high_to_attack(flight, alt_m)
        events = _new_map_events()
        update_package_waypoints_if_primary_flight(waypoint, flight, events)
        try:  # recalc TOT via the Qt model when available (no-op headless)
            model = GameContext.get_model()
            package_model = model.ato_model_for(
                flight.blue
            ).find_matching_package_model(flight.package)
            if package_model is not None:
                package_model.update_tot()
        except Exception:
            pass
        events.update_flight(flight)
        _push_map_events(events)
        return schemas.OpResult(
            ok=True, detail=f"waypoint {waypoint_idx} updated{warning}"
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def _too_high_to_attack(flight: Any, alt_m: float) -> str:
    """Warn when a ground attack flight is sent above the height it plans to fight at.

    Some aircraft simply do not attack from up there, and no rule says which: it is a
    property of the airframe and of the pilot, found by flying it. What is known is
    each aircraft's own combat altitude, so that is the reference -- above it, the
    caller is outside what the planner would ever choose.

    Only a warning. The altitude is set either way, because there are reasons to fly
    high and the caller may have one.
    """
    from game.ato import FlightType
    from game.utils import meters

    if flight.flight_type not in (FlightType.CAS, FlightType.BAI):
        return ""
    planned = flight.unit_type.preferred_combat_altitude
    if meters(alt_m) <= planned:
        return ""
    return (
        f" -- WARNING: {alt_m:.0f} m is above the {planned.meters:.0f} m this "
        f"{flight.unit_type} is planned to fight from. Some aircraft fly over the "
        "target without firing when sent higher than that, and how much higher is too "
        "much varies by airframe and by how experienced the pilot is. Lower it unless "
        "you have a reason."
    )


def set_flight_loadout(
    game: Game, side: str, flight_id: str, loadout: str | dict[int, str]
) -> schemas.OpResult:
    """Re-arm a flight that already exists, the way the player uses the Payload tab.

    ``/packages`` arms the flights it creates, but the engine also creates flights on
    its own, and not all of them are armed: a squadron relocation launches its ferry
    flights with the "Empty" loadout, because no airframe ships a payload named for
    the Ferry task and that task has no fallback. Without this the LLM could not fix
    that, while the player can.
    """
    flight = flight_for_side(game, side, flight_id)
    if flight is None:
        return schemas.OpResult(ok=False, error=f"no flight with id {flight_id!r}")
    try:
        if isinstance(loadout, dict):
            built = _build_loadout(flight.unit_type, flight.flight_type, loadout)
        else:
            # Resolve against the same list /aircraft/loadouts offers. iter_for drops
            # payloads carrying clsids the installed mods do not declare, which
            # loadout_by_name does not -- and DCS discards those stores in silence.
            from game.ato.loadouts import Loadout

            name = str(loadout)
            built = next(
                (lo for lo in Loadout.iter_for(flight) if lo.name == name), None
            )
            if built is None:
                raise ValueError(
                    f"no loadout named {name!r} for "
                    f"{flight.unit_type.display_name} -- see /aircraft/loadouts"
                )
        for member in flight.iter_members():
            member.loadout = built
            member.use_custom_loadout = built.is_custom
        events = _new_map_events()
        events.update_flight(flight)
        _push_map_events(events)
        return schemas.OpResult(
            ok=True,
            detail=f"{flight.flight_type.value} / "
            f"{flight.unit_type.display_name}: {built.name}",
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def _within_window(tot_minutes: int | None, window: int) -> bool:
    """A TOT lands in the mission window only if it is inside BOTH ends of it.

    Testing the late end alone read a package timed before the mission starts -- which
    comes out as a large negative number of minutes -- as comfortably early.
    """
    return tot_minutes is not None and 0 <= tot_minutes <= window


def validate_plan(game: Game, side: str) -> schemas.ValidateResult:
    """Health-check the whole committed plan (no changes): every package's TOT vs the
    mission window and whether any flight is uncrewed (not enough pilots)."""
    coalition = views.coalition_for_side(game, side)
    window = _mission_window_min(game)
    now = game.conditions.start_time
    checks: list[schemas.PackageCheck] = []
    issues: list[str] = []
    for i, pkg in enumerate(coalition.ato.packages):
        view = views.build_package(i, pkg)
        tot = pkg.time_over_target
        tot_min = round((tot - now).total_seconds() / 60) if tot else None
        within = _within_window(tot_min, window)
        uncrewed = sum((f.uncrewed or 0) for f in view.flights)
        if not view.flights:
            issues.append(f"#{i} {view.target}: no flights (empty package)")
        if uncrewed:
            issues.append(
                f"#{i} {view.target}: {uncrewed} uncrewed flight slot(s) — not enough pilots"
            )
        if tot_min is not None and not within:
            issues.append(
                f"#{i} {view.target}: TOT is {abs(tot_min)} min BEFORE the mission starts"
                if tot_min < 0
                else f"#{i} {view.target}: TOT {tot_min} min is past the"
                f" {window}-min window"
            )
        shortfall = tot_shortfall(pkg, now, tot)
        earliest = shortfall[0] if shortfall else None
        if shortfall is not None:
            issues.append(
                f"#{i} {view.target}: TOT +{tot_min} min is unreachable"
                + (f" from {shortfall[1]}" if shortfall[1] else "")
                + f" (needs +{earliest}) — the flights cannot be there in time and "
                "the hold release is computed from it"
            )
        checks.append(
            schemas.PackageCheck(
                index=i,
                target=view.target,
                tot=view.tot,
                tot_minutes_into_mission=tot_min,
                within_window=within,
                uncrewed=uncrewed or None,
                earliest_tot_minutes=earliest,
            )
        )
    hard = list(
        issues
    )  # only crewing/window/empty flip ok; idle aircraft is a soft warning
    idle = views.idle_flyable_total(game, side)
    if idle:
        issues.append(
            f"{idle} flyable aircraft left idle — task them (reinforce or extend a BARCAP, add "
            f"a probe, more saturation) or hold them on purpose; don't leave force on the ramp"
        )
    return schemas.ValidateResult(
        ok=not hard,
        mission_window_min=window,
        packages=checks,
        issues=issues or None,
    )


def _resolve_squadron(game: Game, side: str, squadron_id: str):
    coalition = views.coalition_for_side(game, side)
    for squadron in coalition.air_wing.iter_squadrons():
        if str(squadron.id) == str(squadron_id):
            return squadron
    raise ValueError(f"no squadron with id {squadron_id!r}")


def _resolve_cp(game: Game, cp_id: str):
    try:
        uid = UUID(str(cp_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"invalid control point id {cp_id!r}")
    try:
        cp = game.theater.find_control_point_by_id(uid)
    except Exception:
        cp = None
    if cp is None:
        raise ValueError(f"no control point with id {cp_id!r}")
    return cp


def set_package_tot(
    game: Game, side: str, index: int, tot_minutes: int | None
) -> schemas.OpResult:
    """Set or clear a committed package's Time-On-Target. ``tot_minutes`` = minutes into the
    mission (0 = mission start); ``None`` resets to ASAP. Mirrors the player's TOT/ASAP
    controls — use it to stagger or synchronise packages (deconflict a multi-axis strike,
    avoid self-collisions)."""
    try:
        ato = views.coalition_for_side(game, side).ato
        if index < 0 or index >= len(ato.packages):
            raise ValueError(f"no package at index {index}")
        pkg = ato.packages[index]
        now = game.conditions.start_time
        if tot_minutes is None:
            pkg.auto_asap = True
            pkg.set_tot_asap(now)
            return schemas.OpResult(
                ok=True, detail=f"package {index} TOT reset to ASAP"
            )
        pkg.auto_asap = False
        floor = earliest_tot_minutes(pkg, now)
        if floor is not None and tot_minutes < floor[0]:
            earliest, where = floor
            pkg.time_over_target = now + timedelta(minutes=earliest)
            _push_map_events(_new_map_events())
            return schemas.OpResult(
                ok=True,
                detail=(
                    f"package {index}: TOT +{tot_minutes} min is unreachable"
                    + (f" from {where}" if where else "")
                    + f" — set to the earliest it can make, +{earliest} min"
                ),
            )
        pkg.time_over_target = now + timedelta(minutes=tot_minutes)
        return schemas.OpResult(
            ok=True, detail=f"package {index} TOT set to +{tot_minutes} min"
        )
    except ValueError as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def delete_package(game: Game, side: str, index: int) -> schemas.OpResult:
    """Remove a package (by its turn_context index). Frees its aircraft/pilots."""
    try:
        coalition = views.coalition_for_side(game, side)
        ato = coalition.ato
        if index < 0 or index >= len(ato.packages):
            raise ValueError(f"no package at index {index}")
        pkg = ato.packages[index]
        target = getattr(pkg.target, "name", "?")
        ferrying = _ferrying([pkg])
        ato.remove_package(pkg)
        detail = f"removed package {index} ({target})"
        return schemas.OpResult(
            ok=True, detail=detail + _cancel_relocations(coalition, ferrying)
        )
    except ValueError as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def clear_packages(game: Game, side: str) -> schemas.OpResult:
    """Remove all of ``side``'s packages (start the turn over)."""
    coalition = views.coalition_for_side(game, side)
    ato = coalition.ato
    n = len(ato.packages)
    ferrying = _ferrying(ato.packages)
    ato.clear()
    return schemas.OpResult(
        ok=True,
        detail=f"cleared {n} packages" + _cancel_relocations(coalition, ferrying),
    )


def _ferrying(packages: Iterable[Any]) -> set[Any]:
    """The squadrons with a ferry flight in these packages."""
    return {
        flight.squadron
        for package in packages
        for flight in package.flights
        if flight.flight_type is FlightType.FERRY
    }


def _cancel_relocations(coalition: Any, squadrons: set[Any]) -> str:
    """Cancel the relocations whose ferry flights went with the deleted packages.

    A relocation completes at the end of the turn, so with its ferries gone the
    squadron would still arrive, having flown nothing; and ordering it again was
    ignored as a relocation already under way. Relocate again to plan new ferries.
    """
    still = _ferrying(coalition.ato.packages)
    cancelled = []
    for squadron in squadrons:
        if squadron.destination is not None and squadron not in still:
            squadron.destination = None
            cancelled.append(str(squadron))
    if not cancelled:
        return ""
    return (
        f"; cancelled the relocation of {', '.join(sorted(cancelled))}: its ferry "
        "flights were deleted (relocate again to plan new ones)"
    )


def _purchase_limits(game: Game, side: str, squadron) -> str:
    """Why a buy was refused: parking, the squadron cap, or the budget.

    Parking is per BASE and shared by every squadron on it, and an order reserves its
    slot the moment it is placed -- so a base can read full while its aircraft are all
    still `pending`.
    """
    cp = squadron.location
    parts = []
    try:
        from game.theater.controlpoint import ParkingType

        parking_type = ParkingType().from_squadron(squadron)
        free = cp.unclaimed_parking(parking_type)
        total = cp.total_aircraft_parking(parking_type)
        parts.append(
            f"{cp.name} parking {free} free of {total} (shared by all its squadrons)"
        )
    except Exception:  # pragma: no cover - carriers count parking differently
        pass
    try:
        cap = squadron.max_size
        if cap:
            parts.append(
                f"squadron {squadron.owned_aircraft}+{squadron.pending_deliveries} of max {cap}"
            )
    except Exception:  # pragma: no cover
        pass
    try:
        budget = round(views.coalition_for_side(game, side).budget)
        parts.append(
            f"budget {budget}, this airframe costs {round(squadron.aircraft.price)} each"
        )
    except Exception:  # pragma: no cover
        pass
    return "; ".join(parts) or "no further detail available"


def buy_aircraft(
    game: Game, side: str, squadron_id: str, quantity: int = 1
) -> schemas.OpResult:
    """Order ``quantity`` aircraft into a squadron (arrive next turn)."""
    from game.purchaseadapter import AircraftPurchaseAdapter, TransactionError

    try:
        squadron = _resolve_squadron(game, side, squadron_id)
        if squadron.location.captured != views.player_for_side(side):
            raise ValueError(
                f"can't reinforce {squadron} — its base {squadron.location.name} is "
                f"enemy-held (you can only buy into squadrons at your own bases)"
            )
        try:
            AircraftPurchaseAdapter(squadron.location).buy(squadron, quantity)
        except TransactionError as exc:
            # The engine only says "Cannot buy more X". Which of the three limits was
            # hit is the whole question, and the planner cannot see it from here.
            raise TransactionError(f"{exc} — {_purchase_limits(game, side, squadron)}")
        budget = round(views.coalition_for_side(game, side).budget)
        return schemas.OpResult(
            ok=True,
            detail=f"ordered {quantity} {squadron.aircraft.display_name} for "
            f"{squadron} ({squadron.location.name}); budget now {budget}",
        )
    except (TransactionError, ValueError) as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def sell_aircraft(
    game: Game, side: str, squadron_id: str, quantity: int = 1
) -> schemas.OpResult:
    """Sell ``quantity`` untasked aircraft from a squadron (refunds budget)."""
    from game.purchaseadapter import AircraftPurchaseAdapter, TransactionError

    try:
        squadron = _resolve_squadron(game, side, squadron_id)
        AircraftPurchaseAdapter(squadron.location).sell(squadron, quantity)
        budget = round(views.coalition_for_side(game, side).budget)
        return schemas.OpResult(
            ok=True,
            detail=f"sold {quantity} {squadron.aircraft.display_name} from "
            f"{squadron}; budget now {budget}",
        )
    except (TransactionError, ValueError) as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def buy_ground(
    game: Game, side: str, cp_id: str, unit_name: str, quantity: int = 1
) -> schemas.OpResult:
    """Order ``quantity`` ground units of a type at one of ``side``'s bases."""
    from game.purchaseadapter import GroundUnitPurchaseAdapter, TransactionError

    coalition = views.coalition_for_side(game, side)
    try:
        cp = _resolve_cp(game, cp_id)
        if cp.captured != views.player_for_side(side):
            raise ValueError(f"{cp.name} is not yours")
        buyable = coalition.faction.frontline_units | coalition.faction.artillery_units
        unit = next(
            (u for u in buyable if unit_name in (u.display_name, u.variant_id)),
            None,
        )
        if unit is None:
            raise ValueError(f"{unit_name!r} is not a ground unit this faction can buy")
        if not cp.has_ground_unit_source(game):
            raise ValueError(
                f"{cp.name} can't recruit ground units (needs a factory/front nearby)"
            )
        GroundUnitPurchaseAdapter(cp, coalition, game, commands_the_coalition=True).buy(
            unit, quantity
        )
        return schemas.OpResult(
            ok=True,
            detail=f"ordered {quantity} {unit.display_name} at {cp.name}; "
            f"budget now {round(coalition.budget)}",
        )
    except (TransactionError, ValueError) as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def _resolve_naval(game: Game, naval_id: str):
    """Resolve a turn_context.naval id to a movable object: a ShipGroundObject (a tgo
    id) or a carrier/LHA naval control point (a control-point id). Returns the object or
    None. Both expose ownership, position, max_move_distance, target_position the same.
    """
    from game.theater.theatergroundobject import ShipGroundObject

    try:
        uid = UUID(str(naval_id))
    except (ValueError, AttributeError, TypeError):
        return None
    try:
        tgo = game.db.tgos.get(uid)
    except KeyError:
        tgo = None
    if isinstance(tgo, ShipGroundObject) and tgo.moveable:
        return tgo
    try:
        cp = game.theater.find_control_point_by_id(uid)
    except Exception:
        cp = None
    if cp is not None and getattr(cp, "moveable", False):
        return cp
    return None


def _naval_is_dead(mover) -> bool:
    """True if a naval mover has nothing left alive to reposition — a ship group whose
    units are all destroyed, or a fleet control point with EVERY hull sunk. A dead
    flagship alone doesn't beach the survivors: ``runway_is_operational`` only gates
    aviation, and the map UI still lets the player drag such a fleet (parity)."""
    if getattr(mover, "is_dead", False):  # ShipGroundObject
        return True
    if hasattr(mover, "ground_objects"):  # fleet control point
        return not views._fleet_has_living_hull(mover)
    return False


def move_ship(
    game: Game,
    side: str,
    ship_id: str,
    lat: float | None = None,
    lng: float | None = None,
) -> schemas.OpResult:
    """Reposition one of ``side``'s own movable naval groups — a combatant ship group or
    a carrier/LHA (the player's movable-naval feature, opened to the AI). Validates
    ownership, the per-turn range cap, and an all-water route — the same checks the map
    UI enforces. The move applies at turn processing. Omit lat+lng to cancel a pending
    reposition."""
    from dcs import Point
    from dcs.mapping import LatLng

    from game.theater.theatergroundobject import ShipGroundObject
    from game.utils import meters

    def _refresh(obj) -> None:
        events = _new_map_events()
        if isinstance(obj, ShipGroundObject):
            events.update_tgo(obj)
        else:
            events.update_control_point(obj)
        _push_map_events(events)

    player = views.player_for_side(side)
    try:
        mover = _resolve_naval(game, ship_id)
        if mover is None:
            raise ValueError(
                f"no movable ship group or carrier with id {ship_id!r} "
                f"(use an id from turn_context.naval)"
            )
        # ship groups carry their owner on their control_point; carriers ARE the cp
        owner = getattr(getattr(mover, "control_point", mover), "captured", None)
        if owner != player:
            raise ValueError(f"{mover.name} is not yours to move")
        if _naval_is_dead(mover):
            raise ValueError(f"{mover.name} is destroyed and can't be repositioned")
        if lat is None or lng is None:
            mover.target_position = None
            _refresh(mover)
            return schemas.OpResult(
                ok=True, detail=f"{mover.name}: pending move cancelled (holds position)"
            )
        point = Point.from_latlng(LatLng(float(lat), float(lng)), game.theater.terrain)
        moved_nm = round(meters(mover.position.distance_to_point(point)).nautical_miles)
        if not mover.destination_in_range(point):
            raise ValueError(
                f"destination is {moved_nm}nm away — {mover.name} can move at most "
                f"{int(mover.max_move_distance.nautical_miles)}nm per turn"
            )
        landmap = game.theater.landmap
        if landmap is not None and (
            not game.theater.is_in_sea(point)
            or landmap.land_inbetween(mover.position, point)
        ):
            raise ValueError(
                f"can't move {mover.name} over land or out of the sea — "
                f"pick an all-water destination"
            )
        mover.target_position = point
        _refresh(mover)
        return schemas.OpResult(
            ok=True,
            detail=f"{mover.name} repositioning {moved_nm}nm (applies at turn end)",
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def repair(game: Game, side: str, asset_id: str) -> schemas.OpResult:
    """Pay to repair one of ``side``'s own damaged assets — dead SAM/EWR/armor units, a
    building, or a cratered runway (the player's manual-repair feature, opened to the AI).
    Mirrors the map UI: validates ownership and budget, repairs instantly or schedules it
    over the campaign's repair turns, and debits the coalition budget."""
    from game.config import RUNWAY_REPAIR_COST
    from game.theater.theatergroundobject import BuildingGroundObject

    coalition = views.coalition_for_side(game, side)
    player = views.player_for_side(side)
    try:
        try:
            uid = UUID(str(asset_id))
        except (ValueError, AttributeError, TypeError):
            raise ValueError(f"invalid id {asset_id!r}")

        # 1) runway? (a control-point id)
        cp = None
        try:
            cp = game.theater.find_control_point_by_id(uid)
        except Exception:
            cp = None
        if cp is not None:
            if cp.captured != player:
                raise ValueError(f"{cp.name} is not yours")
            if not getattr(cp, "runway_can_be_repaired", False):
                raise ValueError(
                    f"{cp.name}'s runway isn't damaged (or can't be repaired)"
                )
            cost = int(RUNWAY_REPAIR_COST)
            if coalition.budget < cost:
                raise ValueError(
                    f"need {cost}M to repair the runway, have {round(coalition.budget)}M"
                )
            cp.begin_runway_repair()
            coalition.budget -= cost
            events = _new_map_events()
            events.update_control_point(cp)
            _push_map_events(events)
            return schemas.OpResult(
                ok=True,
                detail=f"runway repair started at {cp.name} "
                f"(-{cost}M; budget {round(coalition.budget)}M)",
            )

        # 2) ground object / building (a tgo id)
        try:
            tgo = game.db.tgos.get(uid)
        except KeyError:
            tgo = None
        if tgo is None:
            raise ValueError(
                f"no repairable asset with id {asset_id!r} "
                f"(use an id from turn_context.repairs)"
            )
        if tgo.control_point.captured != player:
            raise ValueError(f"{tgo.name} is not yours")
        is_building = isinstance(tgo, BuildingGroundObject)
        repair_turns = (
            game.settings.building_repair_turns
            if is_building
            else game.settings.ground_object_repair_turns
        )
        if repair_turns < 0:
            raise ValueError("repairs are disabled in this campaign")
        _, candidates = views._tgo_repairables(tgo)
        if not candidates:
            raise ValueError(
                f"nothing to repair at {tgo.name} "
                f"(no dead repairable units, or already under repair)"
            )
        events = _new_map_events()
        revived = scheduled = spent = 0
        for unit, cost in candidates:
            if coalition.budget < cost:
                break
            coalition.budget -= cost
            spent += cost
            if repair_turns == 0:
                unit.repair_turns_remaining = None
                try:
                    unit.revive(events)  # recomputes threat poly + re-registers IADS
                except Exception:
                    unit.alive = True
                revived += 1
            else:
                unit.repair_turns_remaining = repair_turns
                scheduled += 1
        if not revived and not scheduled:
            raise ValueError(
                f"can't afford to repair {tgo.name} "
                f"(have {round(coalition.budget)}M)"
            )
        events.update_tgo(tgo)
        _push_map_events(events)
        if repair_turns == 0:
            detail = (
                f"repaired {revived} unit(s) at {tgo.name} "
                f"(-{spent}M; budget {round(coalition.budget)}M)"
            )
        else:
            detail = (
                f"scheduled repair of {scheduled} unit(s) at {tgo.name} over "
                f"{repair_turns} turns (-{spent}M; budget {round(coalition.budget)}M)"
            )
        return schemas.OpResult(ok=True, detail=detail)
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def set_stance(
    game: Game, side: str, friendly_cp_id: str, enemy_cp_id: str, stance: str
) -> schemas.OpResult:
    """Set ``side``'s ground posture at the front between two control points."""
    from game.ground_forces.combat_stance import CombatStance

    aliases = {
        "defend": CombatStance.DEFENSIVE,
        "defensive": CombatStance.DEFENSIVE,
        "hold": CombatStance.DEFENSIVE,
        "aggressive": CombatStance.AGGRESSIVE,
        "push": CombatStance.AGGRESSIVE,
        "breakthrough": CombatStance.BREAKTHROUGH,
        "eliminate": CombatStance.ELIMINATION,
        "elimination": CombatStance.ELIMINATION,
        "retreat": CombatStance.RETREAT,
        "ambush": CombatStance.AMBUSH,
    }
    try:
        friendly = _resolve_cp(game, friendly_cp_id)
        enemy = _resolve_cp(game, enemy_cp_id)
        key = stance.strip().lower()
        chosen = aliases.get(key)
        if chosen is None:
            try:
                chosen = CombatStance[stance.strip().upper()]
            except KeyError:
                raise ValueError(f"unknown stance {stance!r}")
        friendly.stances[enemy.id] = chosen
        return schemas.OpResult(
            ok=True, detail=f"{friendly.name} -> {enemy.name}: {chosen.name}"
        )
    except ValueError as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def relocate_squadron(
    game: Game, side: str, squadron_id: str, dest_cp_id: str
) -> schemas.OpResult:
    """Order a squadron to relocate to another of your bases (arrives over time)."""
    try:
        squadron = _resolve_squadron(game, side, squadron_id)
        dest = _resolve_cp(game, dest_cp_id)
        if dest.captured != views.player_for_side(side):
            raise ValueError(f"{dest.name} is not yours — can't relocate there")
        if dest == squadron.location:
            raise ValueError(f"{squadron} is already at {dest.name}")
        origin = squadron.location.name
        squadron.plan_relocation(dest, game.conditions.start_time)
        ferries = sum(
            1
            for package in squadron.coalition.ato.packages
            for flight in package.flights
            if flight.squadron is squadron and flight.flight_type is FlightType.FERRY
        )
        planned = f"{ferries} ferry flight{'' if ferries == 1 else 's'} planned"
        if not ferries and squadron.owned_aircraft:
            planned += ": every one of its aircraft is already tasked this turn"
        return schemas.OpResult(
            ok=True, detail=f"{squadron} relocating {origin} -> {dest.name}; {planned}"
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def transfer_ground(
    game: Game,
    side: str,
    origin_cp_id: str,
    dest_cp_id: str,
    unit_name: str,
    quantity: int = 1,
    by_air: bool = False,
) -> schemas.OpResult:
    """Transfer existing ground units between two of your bases (land or air)."""
    from game.transfers import TransferOrder

    coalition = views.coalition_for_side(game, side)
    player = views.player_for_side(side)
    try:
        origin = _resolve_cp(game, origin_cp_id)
        dest = _resolve_cp(game, dest_cp_id)
        if origin.captured != player or dest.captured != player:
            raise ValueError("both the origin and destination base must be yours")
        if origin == dest:
            raise ValueError("origin and destination are the same base")
        armor = origin.base.armor
        unit = next(
            (
                u
                for u in armor
                if unit_name in (u.display_name, getattr(u, "variant_id", None))
            ),
            None,
        )
        if unit is None or armor.get(unit, 0) <= 0:
            have = (
                ", ".join(f"{u.display_name} x{n}" for u, n in armor.items()) or "none"
            )
            raise ValueError(
                f"{origin.name} has no {unit_name!r} to move (it has: {have})"
            )
        qty = max(1, min(quantity, armor[unit]))
        order = TransferOrder(
            origin, dest, {unit: qty}, coalition.player, request_airflift=by_air
        )
        # Validate the route BEFORE new_transfer — new_transfer debits the origin base
        # up front, so an unreachable destination would otherwise lose the units.
        if not order.is_completable(coalition.transfers.network_for(origin)):
            raise ValueError(
                f"no route from {origin.name} to {dest.name} for a ground transfer "
                f"(the destination isn't reachable over the supply network)"
            )
        coalition.transfers.new_transfer(order, game.conditions.start_time)
        mode = "by air" if by_air else "by land"
        return schemas.OpResult(
            ok=True,
            detail=f"transferring {qty} {unit.display_name} {origin.name} -> "
            f"{dest.name} {mode} (arrives over the next turns)",
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def rebuild_ground_object(
    game: Game,
    side: str,
    tgo_id: str,
    force_group: str,
    layout: str,
    groups=None,
) -> schemas.OpResult:
    """Replace/upgrade a ground object (SAM/EWR/armor/ship/missile/coastal) with a chosen
    force-group + layout, mirroring the player's Buy-ground-object dialog. Optional per-group
    overrides set the unit type and count. Refunds the old group's value, charges the net,
    respects repair-delay."""
    coalition = views.coalition_for_side(game, side)
    player = views.player_for_side(side)
    try:
        tgo = views._resolve_tgo(game, tgo_id, side)
        tasks = views.ground_object_role_tasks(tgo)

        available_groups = coalition.armed_forces.groups_for_tasks(tasks)
        fg = next((g for g in available_groups if g.name == force_group), None)
        if fg is None:
            valid = ", ".join(g.name for g in available_groups) or "none"
            raise ValueError(
                f"no force group {force_group!r} for {tgo.name} (valid: {valid})"
            )
        tgo_layout = next((l for l in fg.layouts if l.name == layout), None)
        if tgo_layout is None:
            valid = ", ".join(l.name for l in fg.layouts) or "none"
            raise ValueError(f"no layout {layout!r} in {force_group} (valid: {valid})")

        overrides = {
            spec.group_name: spec for spec in (_rebuild_specs(groups) if groups else [])
        }

        # Build the concrete selection (mirror QTgoLayoutGroupRow defaults + overrides).
        selections: list[tuple] = []  # (unit_group, group_name, dcs_unit_type, count)
        for tgo_group in tgo_layout.groups:
            for unit_group in tgo_group.unit_groups:
                unit_types = list(fg.unit_types_for_group(unit_group))
                statics = list(fg.statics_for_group(unit_group))
                if not unit_types and not statics:
                    continue  # unusable by this faction (LayoutException parity)
                override = overrides.get(tgo_group.group_name)
                # Optional groups can be turned off; required ones are always on.
                enabled = (
                    (override.enabled if override is not None else True)
                    if unit_group.optional
                    else True
                )
                if not enabled:
                    continue
                # Unit type: an override's named type (validated against this group), else
                # the first available unit type, else the first static (price 0).
                if override is not None and override.unit_type:
                    dcs_unit_type = None
                    unit_price = 0
                    for ut in unit_types:
                        if ut.display_name == override.unit_type:
                            dcs_unit_type = ut.dcs_unit_type
                            unit_price = int(ut.price)
                            break
                    if dcs_unit_type is None:
                        valid = (
                            ", ".join(ut.display_name for ut in unit_types) or "none"
                        )
                        raise ValueError(
                            f"{override.unit_type!r} is not available for group "
                            f"{tgo_group.group_name!r} (valid: {valid})"
                        )
                elif unit_types:
                    dcs_unit_type = unit_types[0].dcs_unit_type
                    unit_price = int(unit_types[0].price)
                else:
                    dcs_unit_type = statics[0]
                    unit_price = 0
                requested = (
                    override.count
                    if override is not None and override.count is not None
                    else unit_group.group_size
                )
                count = max(1, min(int(requested), unit_group.max_size))
                selections.append(
                    (unit_group, tgo_group.group_name, dcs_unit_type, count, unit_price)
                )

        if not selections:
            raise ValueError(
                f"no usable groups for {force_group}/{layout} at {tgo.name}"
            )

        price = sum(count * unit_price for *_, count, unit_price in selections)
        refund = int(tgo.value)
        cost = price - refund
        if cost > coalition.budget:
            raise ValueError(
                f"need {int(cost)}M, have {round(coalition.budget)}M "
                f"(price {int(price)}M - refund {refund}M)"
            )

        # Apply (mirror QGroundObjectTemplateLayout.buy_group).
        tgo.heading = game.theater.heading_to_conflict_from(tgo.position) or tgo.heading
        coalition.budget -= cost
        tgo.groups = []
        for unit_group, group_name, dcs_unit_type, count, _price in selections:
            fg.create_theater_group_for_tgo(
                tgo,
                unit_group,
                f"{tgo.name} ({group_name})",
                game,
                dcs_unit_type,
                count,
            )
        repair_turns = game.settings.ground_object_repair_turns
        if game.turn and repair_turns > 0:
            # Player purchases respect repair delays like AI repairs.
            for unit in tgo.units:
                if not getattr(unit, "repairable", False):
                    continue
                unit.alive = False
                unit.repair_turns_remaining = repair_turns

        events = _new_map_events()
        events.update_tgo(tgo)
        _push_map_events(events)
        sign = "-" if cost >= 0 else "+"
        return schemas.OpResult(
            ok=True,
            detail=(
                f"rebuilt {tgo.name} as {force_group}/{layout} "
                f"(net {sign}{abs(int(cost))}M; budget {round(coalition.budget)}M)"
            ),
        )
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))


def _rebuild_specs(groups):
    """Coerce the ``groups`` argument (RebuildGroupSpec objects OR dicts) to
    RebuildGroupSpec, so both transports (REST models, MCP dicts) work."""
    out = []
    for g in groups:
        out.append(
            g
            if isinstance(g, schemas.RebuildGroupSpec)
            else schemas.RebuildGroupSpec(**g)
        )
    return out


def apply_tot_offset(flight, minutes: float) -> None:
    """Shift one flight's time over target relative to its package's.

    Mirrors the Edit Flight dialog: negative is "ahead of package", which is how you
    put the escort over the target before the strikers.
    """
    from datetime import timedelta

    flight.flight_plan.tot_offset = timedelta(minutes=float(minutes))


def set_flight_tot_offset(
    game: Game, side: str, flight_id: str, minutes: float
) -> schemas.OpResult:
    """Set a flight's TOT offset from its package's TOT, in minutes (negative = ahead)."""
    flight = flight_for_side(game, side, flight_id)
    if flight is None:
        return schemas.OpResult(ok=False, error=f"no flight with id {flight_id!r}")
    try:
        apply_tot_offset(flight, minutes)
        package = package_of(game, side, flight)
        if package is not None and getattr(package, "auto_asap", False):
            package.set_tot_asap(game.conditions.start_time)
    except Exception as exc:
        return schemas.OpResult(ok=False, error=str(exc))
    where = "ahead of" if minutes < 0 else "after"
    return schemas.OpResult(
        ok=True,
        detail=f"{flight} now arrives {abs(minutes):g} min {where} its package TOT",
    )


def package_of(game: Game, side: str, flight):
    for package in views.coalition_for_side(game, side).ato.packages:
        if flight in package.flights:
            return package
    return None


#: How many bonds a pilot's view carries. Enough to crew around, and short of a dump
#: of everybody he has ever shared a base with.
RELATIONSHIP_LIMIT = 12


def _rungs_between(before: Any, after: Any) -> int:
    try:
        return SKILL_LADDER.index(after) - SKILL_LADDER.index(before)
    except ValueError:
        return 0


def _relationship_views(
    pilot: Any, index: dict[Any, Any], settings: Any = None
) -> list[dict[str, Any]]:
    """Every bond worth mentioning, in both directions and across squadrons.

    Both signs, because a man he cannot stand is exactly as actionable as a friend --
    what you do about either is not put them in the same flight. And across squadrons,
    because a package is crewed out of more than one of them.
    """
    others = set(pilot.friendships)
    for other_id, (_, other) in index.items():
        if other_id != pilot.id and pilot.id in other.friendships:
            others.add(other_id)

    bonds: list[tuple[float, dict[str, Any]]] = []
    for other_id in others:
        found = index.get(other_id)
        if found is None:
            continue  # dead, thrown out, or transferred out of the wing
        other_squadron, other = found
        towards = friendship.feeling(pilot, other)
        from_him = friendship.feeling(other, pilot)
        strength = max(
            abs(friendship.points(towards)), abs(friendship.points(from_him))
        )
        if not strength:
            continue
        bonds.append(
            (
                strength,
                {
                    "id": str(other.id),
                    "name": other.name,
                    "squadron": str(other_squadron),
                    "band": friendship.band_name(towards, settings),
                    "towards": round(towards, 1),
                    "from": round(from_him, 1),
                },
            )
        )
    bonds.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [view for _, view in bonds[:RELATIONSHIP_LIMIT]]


def _skill_breakdown(squadron: Any, pilot: Any, flight: Any) -> dict[str, Any]:
    """What made the rung he will fly at: his rank, his week and his company.

    The answer is already in ``flies_at``; this is the working, so a crew worth keeping
    together can be told from one that is merely senior.
    """
    morale_shift = 0
    if getattr(squadron, "morale_in_play", False) and pilot.has_morale:
        morale_shift = morale_rules.skill_shift(pilot.morale, squadron.settings)
    return {
        "rank": squadron.pilot_skill(pilot).value,
        "morale": morale_shift,
        "friendship": _rungs_between(
            squadron.mission_skill(pilot), squadron.mission_skill(pilot, flight)
        ),
    }


def _wing_index(squadron: Any) -> dict[Any, Any]:
    """The whole wing by pilot id, or nothing when there is no friendship to resolve."""
    if not getattr(squadron, "friendship_in_play", False):
        return {}
    coalition = getattr(squadron, "coalition", None)
    air_wing = getattr(coalition, "air_wing", None)
    return air_wing.pilot_index() if air_wing is not None else {}


def _record_figures(record: Any) -> dict[str, Any]:
    """The pilot's record as counts, leaving out whatever has not happened to him."""
    figures: dict[str, Any] = {}
    for name, value in (
        ("missions_completed", record.missions_completed),
        ("air_kills", record.total_air_kills),
        ("ground_kills", record.total_ground_kills),
        ("aircraft_lost", record.aircraft_lost),
        ("survived_losses", record.survived_losses),
        ("wounds", record.wounds),
        ("leaves_taken", record.leaves_taken),
    ):
        if value:
            figures[name] = value
    if record.killed_by is not None:
        figures["killed_by"] = killer_sentence(record.killed_by) or "unknown"
        if record.killed_by.turn:
            figures["killed_on_turn"] = record.killed_by.turn
    return figures


def _pilots_matching(candidates: Iterable[Any], token: str) -> list[Any]:
    """The pilots `token` picks out, by id or by name.

    An id wins outright and can only ever match one man. A name is good enough only
    while it picks out exactly one: two pilots called the same thing are two people,
    and the generator does hand out the same name twice, so taking the first match
    silently crews the wrong man. Every roster view carries the id for this reason.
    """
    by_id = [p for p in candidates if str(p.id) == token]
    if by_id:
        return by_id
    return [p for p in candidates if p.name == token]


def _ambiguous_pilot(matches: list[Any], token: str) -> str:
    ids = ", ".join(sorted(str(p.id) for p in matches))
    return (
        f"{len(matches)} pilots are called {token}; say which one by passing "
        f"his id instead of his name: {ids}"
    )


def pilot_record(
    game: Game, side: str, squadron_id: str, pilot_name: str
) -> dict[str, Any]:
    """Everything the campaign remembers about one man.

    The roster gives figures; this is what they are made of -- every kill with the
    turn and the weapon, what he has survived, how he died and who did it, everything
    that has moved his morale, and what he thinks of the men around him. It is the
    pilot dialog, in other words, and it is a call of its own because it is far too
    much to carry for every pilot of every squadron on every turn.
    """
    for coalition in (game.blue, game.red):
        if (coalition.player.name.lower() == "blue") != (side.lower() == "blue"):
            continue
        for squadron in coalition.air_wing.iter_squadrons():
            if str(squadron.id) != squadron_id and squadron.name != squadron_id:
                continue
            matches = _pilots_matching(squadron.current_roster, pilot_name)
            if len(matches) > 1:
                raise ValueError(_ambiguous_pilot(matches, pilot_name))
            if matches:
                return _pilot_record_view(squadron, matches[0])
            known = ", ".join(sorted(p.name for p in squadron.current_roster))
            raise ValueError(f"{squadron} has no {pilot_name} (roster: {known})")
    raise ValueError(f"No squadron {squadron_id} on {side}")


def _pilot_record_view(squadron: Any, pilot: Any) -> dict[str, Any]:
    """The dossier itself, built on top of the roster's own view of him."""
    record = pilot.record
    view = _pilot_view(squadron, pilot)
    view["squadron"] = str(squadron)
    view["aircraft"] = str(squadron.aircraft)
    view["base"] = squadron.location.name

    view["kills"] = {
        "air_by_type": dict(record.air_kills),
        "ground_by_type": dict(record.ground_kills),
        "ground_by_class": record.ground_kills_by_class(),
        # Each one, most recent last, capped at what the record keeps.
        "log": [
            {
                "what": kill.what,
                "turn": kill.turn,
                "weapon": kill.weapon,
                "air": kill.air,
                "class": kill.kill_class,
            }
            for kill in record.kills
        ],
    }

    survival: dict[str, Any] = {
        "missions_flown": record.missions_flown,
        "missions_completed": record.missions_completed,
        "aircraft_lost": record.aircraft_lost,
        "survived_losses": record.survived_losses,
        "wounds": record.wounds,
        "turns_in_hospital": record.turns_in_hospital,
        "leaves_taken": record.leaves_taken,
        "leave_turns_total": record.leave_turns_total,
    }
    if record.last_wound_turn:
        survival["last_wound_turn"] = record.last_wound_turn
        survival["last_wound_turns"] = record.last_wound_turns
    view["survival"] = survival

    if record.killed_by is not None:
        killed = record.killed_by
        view["killed_by_detail"] = {
            "pilot": killed.pilot_name,
            "squadron": killed.squadron,
            "aircraft": killed.aircraft,
            "weapon": killed.weapon,
            "friendly_fire": killed.friendly_fire,
            "turn": killed.turn,
        }

    if pilot.has_morale and getattr(squadron, "morale_in_play", False):
        view["morale_state"] = morale_rules.morale_state(
            pilot.morale, squadron.settings
        ).name
        view["morale_last_turn"] = pilot.morale_last_turn
        view["morale_log"] = [
            {
                "turn": entry.turn,
                "amount": entry.amount,
                "reason": entry.reason,
                "morale_after": entry.morale_after,
            }
            for entry in pilot.morale_log
        ]
    elif pilot.player:
        view["morale_note"] = (
            "The player's own pilot has no morale: he is never grounded, sent on"
            " leave or made to desert by it."
        )

    view["turns_since_leave"] = pilot.turns_since_leave
    if pilot.wants_leave:
        view["leave_turns_requested"] = pilot.leave_turns_requested
    return view


def _pilot_view(
    squadron: Any, pilot: Any, index: Any = None, flight: Any = None
) -> dict[str, Any]:
    """One pilot as the Air Wing shows him."""
    rank = squadron.pilot_rank(pilot)
    view: dict[str, Any] = {
        "name": pilot.name,
        "skill": squadron.pilot_skill(pilot).value,
        "missions_flown": pilot.record.missions_flown,
        "xp": pilot.record.xp,
        "status": pilot.status.value,
    }
    if rank is not None:
        view["rank"] = rank.abbreviation
        view["rank_full"] = rank.name
    if pilot.wounded:
        view["wounded_turns_remaining"] = pilot.wounded_turns
    if pilot.player:
        view["player"] = True
    # What he has done and been through, as figures. Only what is not zero: this is
    # built for every pilot of every squadron on every turn, and a roster of thirty
    # men carrying eight zeroes each is a page of nothing.
    view.update(_record_figures(pilot.record))

    settings = getattr(squadron, "settings", None)
    if settings is not None and getattr(settings, "morale_enabled", True):
        view["morale"] = pilot.morale
        # What he will actually fly at, which morale moves and his rank does not.
        view["flies_at"] = squadron.mission_skill(pilot).value
        if pilot.wants_leave:
            view["asking_for_leave"] = True
        if pilot.on_leave and pilot.leave_turns:
            view["leave_turns_remaining"] = pilot.leave_turns
        if pilot.hardened and hardening.in_play(settings):
            # What the bad weeks left behind. It never comes off, so a high figure on a
            # man whose morale is fine is a man who has already been through it.
            view["hardened"] = pilot.hardened
            view["hardened_of"] = hardening.ceiling(settings)

    if getattr(squadron, "friendship_in_play", False):
        # The id, because two men of the same name are two men, and a relationship has
        # to be able to name one of them.
        view["id"] = str(pilot.id)
        bonds = _relationship_views(
            pilot,
            _wing_index(squadron) if index is None else index,
            getattr(squadron, "settings", None),
        )
        if bonds:
            view["relationships"] = bonds
        if flight is not None:
            view["flies_at"] = squadron.mission_skill(pilot, flight).value
            view["skill_breakdown"] = _skill_breakdown(squadron, pilot, flight)
    return view


def answer_leave_request(
    game: Game,
    side: str,
    squadron_id: str,
    pilot_name: str,
    grant: bool,
    turns: int = 0,
) -> schemas.OpResult:
    """Say yes or no to a pilot who asked for leave.

    Granted, he is off the roster for the turns you allow -- at most what he asked for --
    and comes back steadier. Refused, he takes it badly and does not ask again for a
    while. Leaving the request unanswered is the same as refusing it, so it is worth
    doing on purpose: a squadron of shaken men who are all told no will keep sliding.
    """
    from game.squadrons.morale import LEAVE_REFUSED, MAX_LEAVE_TURNS, apply

    for coalition in (game.blue, game.red):
        if (coalition.player.name.lower() == "blue") != (side.lower() == "blue"):
            continue
        for squadron in coalition.air_wing.iter_squadrons():
            if str(squadron.id) != squadron_id and squadron.name != squadron_id:
                continue
            asking = list(squadron.pilots_asking_for_leave())
            matches = _pilots_matching(asking, pilot_name)
            if len(matches) > 1:
                return schemas.OpResult(
                    ok=False, error=_ambiguous_pilot(matches, pilot_name)
                )
            pilot = matches[0] if matches else None
            if pilot is None:
                return schemas.OpResult(
                    ok=False,
                    error=f"{pilot_name} is not asking {squadron} for leave"
                    f" (asking: {', '.join(sorted(p.name for p in asking)) or 'nobody'})",
                )
            if not grant:
                pilot.wants_leave = False
                pilot.leave_turns_requested = 0
                pilot.move_morale(
                    LEAVE_REFUSED,
                    squadron.pilot_skill(pilot),
                    game.settings,
                    game.turn,
                )
                return schemas.OpResult(
                    ok=True, detail=f"{pilot_name} was refused leave"
                )

            asked = pilot.leave_turns_requested or 1
            granted = max(1, min(turns or asked, asked, MAX_LEAVE_TURNS))
            try:
                squadron.send_on_leave(pilot, granted, game.turn)
            except RuntimeError as exc:
                return schemas.OpResult(ok=False, error=str(exc))
            spare = squadron.spare_pilots()
            return schemas.OpResult(
                ok=True,
                detail=f"{pilot_name} is on leave for {granted} of the {asked} turns "
                f"he asked for; {squadron} has {spare} pilots left for "
                f"{squadron.owned_aircraft} aircraft",
            )
    return schemas.OpResult(ok=False, error=f"no squadron with id {squadron_id!r}")


def set_pilot_leave(
    game: Game,
    side: str,
    squadron_id: str,
    pilot_name: str,
    on_leave: bool = True,
    turns: int = 0,
) -> schemas.PilotLeaveResult:
    """Rest a pilot who never asked, or call one back early -- the Air Wing leave button.

    ``answer_leave_request`` only reaches a man who put his hand up, and the ones worth
    resting are often the ones who do not: a pilot at rock bottom can sit there flying
    while nobody offers. The player can press this on anybody on the roster, so this
    does too, with the squadron applying the same rules -- only an active pilot can go,
    and a squadron with no room cannot take one back.

    ``turns`` of zero is open-ended leave: he stays out until he is called back. Any
    other number runs down on its own like a wound. Calling him back early costs him
    morale; leave that ran out on its own does not.
    """
    from game.squadrons.morale import MAX_LEAVE_TURNS

    for coalition in (game.blue, game.red):
        if (coalition.player.name.lower() == "blue") != (side.lower() == "blue"):
            continue
        for squadron in coalition.air_wing.iter_squadrons():
            if str(squadron.id) != squadron_id and squadron.name != squadron_id:
                continue
            matches = _pilots_matching(squadron.current_roster, pilot_name)
            if len(matches) > 1:
                return schemas.PilotLeaveResult(
                    ok=False, error=_ambiguous_pilot(matches, pilot_name)
                )
            pilot = matches[0] if matches else None
            if pilot is None:
                return schemas.PilotLeaveResult(
                    ok=False, error=f"{squadron} has nobody called {pilot_name}"
                )
            try:
                if on_leave:
                    squadron.send_on_leave(
                        pilot, max(0, min(turns, MAX_LEAVE_TURNS)), game.turn
                    )
                else:
                    squadron.cancel_leave(pilot)
            except RuntimeError as exc:
                return schemas.PilotLeaveResult(
                    ok=False,
                    error=str(exc),
                    status=pilot.status.value,
                    leave_turns_remaining=pilot.leave_turns,
                )
            if pilot.on_leave:
                spell = (
                    f"for {pilot.leave_turns} more turn(s)"
                    if pilot.leave_turns
                    else "open-ended, until you call him back"
                )
                detail = (
                    f"{pilot_name} is on leave {spell}; {squadron} has "
                    f"{squadron.spare_pilots()} pilots left for "
                    f"{squadron.owned_aircraft} aircraft"
                )
            else:
                detail = (
                    f"{pilot_name} is back on {squadron}'s roster; being called back "
                    "early cost him morale"
                )
            return schemas.PilotLeaveResult(
                ok=True,
                detail=detail,
                status=pilot.status.value,
                leave_turns_remaining=pilot.leave_turns,
            )
    return schemas.PilotLeaveResult(
        ok=False, error=f"no squadron with id {squadron_id!r}"
    )


def _reconcile_pool(game: Game, side: str) -> None:
    """Cross-check the squadron pools before answering anything about crews.

    A pilot who has fallen off his squadron's available list with nothing holding him
    reads as free in the roster and is refused a seat, which from outside is a dead end
    -- the API can only say he is dead, wounded, on leave or flying, and he is none of
    them. Checking the list against the roster turns that into a log line.

    Best effort: this is hygiene, not the answer. A caller with a stand-in game still
    gets its answer.
    """
    try:
        views.coalition_for_side(game, side).reconcile_pilot_pools()
    except Exception:
        logging.debug("Could not reconcile the pilot pools", exc_info=True)


def squadron_pilots(game: Game, side: str, squadron_id: str) -> dict[str, Any]:
    """Every pilot on a squadron's books, and where each one is.

    The Air Wing dialog's roster, in other words: rank, experience, what he is flying at,
    and whether he is dead, on leave, in hospital or ready. ``assigned_to`` names the
    flight he is already crewing, so the free ones are the entries without it.
    """
    _reconcile_pool(game, side)

    from game.ato import FlightType  # noqa: F401  (kept for symmetry with callers)

    for coalition in (game.blue, game.red):
        if (coalition.player.name.lower() == "blue") != (side.lower() == "blue"):
            continue
        for squadron in coalition.air_wing.iter_squadrons():
            if str(squadron.id) != squadron_id and squadron.name != squadron_id:
                continue
            flying = {}
            for package in coalition.ato.packages:
                for flight in package.flights:
                    for pilot in flight.roster.iter_pilots():
                        if pilot is not None:
                            flying[id(pilot)] = (
                                f"{flight.flight_type.value} on "
                                f"{flight.package.target.name}"
                            )
            pilots = []
            index = _wing_index(squadron)
            for pilot in squadron.current_roster:
                view = _pilot_view(squadron, pilot, index)
                if id(pilot) in flying:
                    view["assigned_to"] = flying[id(pilot)]
                pilots.append(view)
            # Senior first, the same order the Air Wing lists them in.
            pilots.sort(key=lambda v: (-v.get("xp", 0), v["name"]))
            roster: dict[str, Any] = {
                "squadron": str(squadron),
                "aircraft": str(squadron.aircraft),
                "base": squadron.location.name,
                "pilots": pilots,
            }
            cohesion = (
                squadron.cohesion
                if getattr(squadron, "friendship_in_play", False)
                else None
            )
            if cohesion is not None:
                roster["cohesion"] = {
                    "value": round(cohesion, 1),
                    "band": friendship.band_name(cohesion, squadron.settings),
                }
            return roster
    return {"error": f"no squadron {squadron_id!r} on {side}"}


def flight_crew(game: Game, side: str, flight_id: str) -> dict[str, Any]:
    """Who is in each seat of a flight, and who else could be.

    ``seats`` is indexed the way ``set_flight_crew`` expects. ``available`` lists the
    squadron's pilots who are not flying anything yet, most senior first.
    """
    _reconcile_pool(game, side)
    flight = flight_for_side(game, side, flight_id)
    if flight is None:
        return {"error": f"no flight with id {flight_id!r}"}
    squadron = flight.squadron
    index = _wing_index(squadron)
    seats = []
    for idx, pilot in enumerate(flight.roster.iter_pilots()):
        seat: dict[str, Any] = {"seat": idx}
        if pilot is None:
            seat["empty"] = True
        else:
            seat.update(_pilot_view(squadron, pilot, index, flight))
        seats.append(seat)
    available = [_pilot_view(squadron, p, index) for p in squadron.available_pilots]
    available.sort(key=lambda v: (-v.get("xp", 0), v["name"]))
    crew: dict[str, Any] = {
        "flight_id": str(flight.id),
        "squadron": str(squadron),
        "seats": seats,
        "available": available,
    }
    synergy = None
    if getattr(squadron, "friendship_in_play", False):
        synergy = squadron.formation_synergy(list(flight.roster.iter_pilots()))
    if synergy is not None:
        # A planner that can see the number can crew for it, which is the point of
        # having it.
        crew["synergy"] = {
            "value": round(synergy, 1),
            "band": friendship.band_name(synergy, squadron.settings),
            "flies_a_rung_better": friendship.flies_a_rung_better(
                synergy, squadron.settings
            ),
        }
    return crew


def set_flight_crew(
    game: Game, side: str, flight_id: str, seat: int, pilot_name: str | None
) -> schemas.OpResult:
    """Put a named pilot in a seat, or empty it with a null name.

    The same move as the dropdown in Edit Flight. A pilot who is dead, in hospital, on
    leave or already crewing something else is refused, because the squadron only counts
    him once and the alternative is the same man flying two missions at once.
    """
    _reconcile_pool(game, side)
    flight = flight_for_side(game, side, flight_id)
    if flight is None:
        return schemas.OpResult(ok=False, error=f"no flight with id {flight_id!r}")
    squadron = flight.squadron
    if not 0 <= seat < flight.roster.max_size:
        return schemas.OpResult(
            ok=False,
            error=f"seat {seat} does not exist; this flight has "
            f"{flight.roster.max_size}",
        )
    if pilot_name is None:
        current = flight.roster.pilot_at(seat)
        flight.roster.set_pilot(seat, None)
        who = current.name if current is not None else "nobody"
        return schemas.OpResult(ok=True, detail=f"seat {seat} emptied (was {who})")

    seated = flight.roster.pilot_at(seat)
    if seated is not None and _pilots_matching([seated], pilot_name):
        return schemas.OpResult(ok=True, detail=f"{pilot_name} already has seat {seat}")

    matches = _pilots_matching(squadron.available_pilots, pilot_name)
    if len(matches) > 1:
        return schemas.OpResult(ok=False, error=_ambiguous_pilot(matches, pilot_name))
    if not matches:
        known = bool(_pilots_matching(squadron.current_roster, pilot_name))
        reason = (
            "he is dead, wounded, on leave or already flying something else"
            if known
            else f"nobody of that name is on {squadron}'s books"
        )
        return schemas.OpResult(
            ok=False, error=f"cannot put {pilot_name} in seat {seat}: {reason}"
        )
    try:
        flight.roster.set_pilot(seat, matches[0])
    except ValueError as exc:
        return schemas.OpResult(ok=False, error=str(exc))
    return schemas.OpResult(ok=True, detail=f"{pilot_name} takes seat {seat}")
