from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Iterator, Optional, TYPE_CHECKING

from game.debriefing import Debriefing
from game.squadrons.pilot import KilledBy
from game.squadrons.experience import (
    PilotDeath,
    PilotPromotion,
    MoraleShift,
    PilotWound,
    WOUNDED_TURNS,
    XP_AIR_KILL,
    XP_DAMAGE_SHARE,
    XP_GROUND_KILL,
    XP_MISSION_COMPLETE,
    XP_SHIP_KILL,
    XP_UNKNOWN_KILL,
    XP_WOUNDED,
    building_xp,
    turns_phrase,
    survival_chance,
)
from game.dcs.skills import one_promotion_at_most
from game.ground_forces.combat_stance import CombatStance
from game.dcs.skills import SKILL_LADDER
from game.squadrons import friendship
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot
from game.squadrons.xplog import XpLog
from game.profiling import logged_duration
from game.theater import ControlPoint
from .gameupdateevents import GameUpdateEvents
from ..ato.airtaaskingorder import AirTaskingOrder

if TYPE_CHECKING:
    from ..game import Game
    from ..coalition import Coalition
    from ..ato.flight import Flight
    from ..dcs.aircrafttype import AircraftType
    from ..theater.missiontarget import MissionTarget


MINOR_DEFEAT_INFLUENCE = 0.1
DEFEAT_INFLUENCE = 0.3
STRONG_DEFEAT_INFLUENCE = 0.5


#: What a destroyed thing was, in the terms both the XP table and a pilot's record
#: care about. Strings rather than an enum: one of them is a building category that
#: comes from the campaign's own data.
AIR = "air"
SHIP = "ship"
VEHICLE = "vehicle"
BUILDING = "building"
UNKNOWN = "unknown"
NOTHING = "nothing"


#: How a pilot would group what he destroyed on the ground -- coarser than the unit
#: table's classes, which split armour four ways and are for buying rather than for
#: telling somebody what happened.
AIR_DEFENCE = "Air defence"
ARMOUR = "Armour"
ARTILLERY = "Artillery"
SOFT_VEHICLES = "Soft vehicles"
STRUCTURES = "Structures"
SHIPS = "Ships"


def ground_class_of(unit_class: Any) -> str:
    """Which of those a unit belongs to."""
    from game.data.units import UnitClass

    if unit_class in {
        UnitClass.AAA,
        UnitClass.SHORAD,
        UnitClass.MANPAD,
        UnitClass.TELAR,
        UnitClass.MISSILE,
        UnitClass.LAUNCHER,
        UnitClass.SEARCH_RADAR,
        UnitClass.TRACK_RADAR,
        UnitClass.SEARCH_TRACK_RADAR,
        UnitClass.OPTICAL_TRACKER,
        UnitClass.SEARCH_LIGHT,
        UnitClass.EARLY_WARNING_RADAR,
    }:
        return AIR_DEFENCE
    if unit_class in {UnitClass.TANK, UnitClass.IFV, UnitClass.APC}:
        return ARMOUR
    if unit_class in {UnitClass.ARTILLERY, UnitClass.ATGM}:
        return ARTILLERY
    return SOFT_VEHICLES


@dataclass(frozen=True)
class Victim:
    """What was destroyed, and what it was called."""

    kind: str
    name: str = ""
    #: For a building, the campaign's own category for it, which is what it is paid by.
    building_category: Optional[str] = None
    #: How a pilot would group it when telling somebody. Empty for an air kill, which
    #: is grouped by the aircraft's own name.
    ground_class: str = ""


def _named(unit_type: Any) -> str:
    """What to call it in a pilot's record, or nothing if it cannot be named."""
    if unit_type is None:
        return ""
    return str(getattr(unit_type, "display_name", None) or unit_type)


def _ground_class(unit_type: Any) -> str:
    """What a pilot would call the sort of thing it was."""
    unit_class = getattr(unit_type, "unit_class", None)
    return SOFT_VEHICLES if unit_class is None else ground_class_of(unit_class)


def killer_sentence(parts: KilledBy) -> str:
    """ "Capt Ortega (F-15C) with AIM-120C", from the pieces.

    One place, so the debriefing line and anything else that says who did it agree.
    """
    said = parts.pilot_name
    if parts.aircraft and parts.aircraft != said:
        said = f"{said} ({parts.aircraft})"
    if parts.weapon and parts.weapon != parts.aircraft:
        said = f"{said} with {parts.weapon}"
    return said


class MissionResultsProcessor:
    def __init__(self, game: Game) -> None:
        self.game = game
        # TEMPORARY: see game.squadrons.xplog. Remove with the rest of it.
        self._xp_log: Optional[XpLog] = None
        #: Morale movements collected during the pass, applied once it is over.
        self._morale_events: dict[int, list[Any]] = {}
        #: ``id()`` of the men the medics took this turn. A pilot does not mourn his
        #: own wound, the way the dead do not mourn themselves.
        self._wounded_this_turn: set[int] = set()
        #: What the turn's flying earned each directed pair, by (id(a), id(b)).
        #: Collected rather than applied on the spot: the multiplier a sortie pays has
        #: to be worked out from what the men thought of each other *before* it, or
        #: what a man earns depends on where he happens to sit in the loop.
        self._friendship_gains: dict[tuple[int, int], tuple[Any, Any, float]] = {}
        #: And what somebody did to be thought less of. Never summed: a man in both the
        #: shooter's flight and the victim's squadron takes the larger of the two.
        self._friendship_penalties: dict[tuple[int, int], tuple[Any, Any, float]] = {}
        #: The men who did not come home, by squadron, so the squadron's share of the
        #: grief can be weighed by what each survivor thought of each of them. The
        #: debriefing carries names; this carries the pilots.
        self._dead_this_turn: dict[str, list[Any]] = {}

    def _note_morale(self, pilot: Any, event: Any, times: int = 1) -> None:
        """Record that something happened to a pilot; it is applied at the end.

        Collected rather than applied immediately because the experience multiplier
        reads the morale the pilot flew the sortie with, not the morale it left him
        with.

        """
        if times > 0:
            self._morale_events.setdefault(id(pilot), []).extend([event] * times)

    def _note_friendship(self, pilot: Any, other: Any, amount: float) -> None:
        """He saw a bit more of this man today. Spent at the end of the pass."""
        if pilot is other or not amount:
            return
        amount = hardening.feels(pilot, amount, self.game.settings)
        if not amount:
            return
        key = (id(pilot), id(other))
        running = self._friendship_gains.get(key)
        total = amount if running is None else running[2] + amount
        self._friendship_gains[key] = (pilot, other, total)

    def _note_friendly_fire(self, mourner: Any, shooter: Any, amount: float) -> None:
        """The friendship penalty one witness applies to the pilot responsible.

        The worst applicable penalty rather than their sum, so being both in the
        shooter's flight and in the victim's squadron is not counted twice.

        """
        if mourner is shooter or not amount:
            return
        # A thick skin is thick both ways: he is slower to hold this against him too.
        amount = hardening.feels(mourner, amount, self.game.settings)
        if not amount:
            return
        key = (id(mourner), id(shooter))
        running = self._friendship_penalties.get(key)
        worst = amount if running is None else min(running[2], amount)
        self._friendship_penalties[key] = (mourner, shooter, worst)

    def _commit_friendship(self) -> None:
        """Apply the turn's collected friendship changes.

        Gains are capped per pair, so repeated sorties with the same crew cannot reach
        in one turn a band meant to take a campaign.

        """
        settings = self.game.settings
        if friendship.in_play(settings):
            cap = friendship.max_gain_per_turn(settings)
            for pilot, other, amount in self._friendship_gains.values():
                friendship.move(pilot, other, min(amount, cap))
            for mourner, shooter, amount in self._friendship_penalties.values():
                friendship.move(mourner, shooter, amount)
        self._friendship_gains = {}
        self._friendship_penalties = {}

    def _commit_morale(self, debriefing: Debriefing) -> None:
        """Spend the tally, once the experience has been paid at the old morale."""
        if not self.game.settings.live_pilots_enabled:
            return
        if not getattr(self.game.settings, "morale_enabled", True):
            return
        for coalition in (self.game.blue, self.game.red):
            for squadron in coalition.air_wing.iter_squadrons():
                for pilot in squadron.current_roster:
                    events = self._morale_events.get(id(pilot))
                    if not events:
                        continue
                    before = pilot.morale
                    for event in events:
                        pilot.move_morale(
                            event,
                            squadron.pilot_skill(pilot),
                            self.game.settings,
                            self.game.turn,
                        )
                    if pilot.morale != before:
                        reasons = [e.reason for e in events]
                        self.xp_log.morale(
                            pilot, squadron, before, pilot.morale, reasons
                        )
                        if morale_rules.worth_reporting(
                            before, pilot.morale, self.game.settings
                        ):
                            debriefing.pilot_outcomes.morale_shifts.append(
                                MoraleShift(
                                    pilot_name=pilot.name,
                                    squadron=str(squadron),
                                    aircraft=str(squadron.aircraft),
                                    rank=self._short_rank(squadron, pilot),
                                    level=self._rank_level(squadron, pilot),
                                    blue=squadron.player.is_blue,
                                    before=before,
                                    after=pilot.morale,
                                    before_state=morale_rules.morale_state(
                                        before, self.game.settings
                                    ).name,
                                    after_state=morale_rules.morale_state(
                                        pilot.morale, self.game.settings
                                    ).name,
                                    reasons=sorted(set(reasons)),
                                )
                            )
        self._morale_events = {}
        self._wounded_this_turn = set()
        self._dead_this_turn = {}

    def _note_shared_morale(self, debriefing: Debriefing) -> None:
        """What the whole squadron or the whole coalition felt.

        A death is felt by everyone who flew with the man, and a base changing hands is
        felt by everyone on that side.
        """
        dead_by_squadron: dict[str, int] = {}
        for death in debriefing.pilot_outcomes.deaths:
            dead_by_squadron[death.squadron] = (
                dead_by_squadron.get(death.squadron, 0) + 1
            )
        # A wound is counted by how long it keeps him, capped so it never weighs as
        # much as a grave.
        wounds_by_squadron: dict[str, int] = {}
        for wound in debriefing.pilot_outcomes.wounded:
            wounds_by_squadron[wound.squadron] = wounds_by_squadron.get(
                wound.squadron, 0
            ) + morale_rules.wound_is_felt_for(wound.turns)

        for coalition in (self.game.blue, self.game.red):
            lost = sum(
                1
                for capture in debriefing.base_captures
                if capture.captured_by_player.is_blue != coalition.player.is_blue
            )
            for squadron in coalition.air_wing.iter_squadrons():
                deaths = dead_by_squadron.get(str(squadron), 0)
                wounds = wounds_by_squadron.get(str(squadron), 0)
                for pilot in squadron.current_roster:
                    if not pilot.alive:
                        continue
                    # A man does not mourn himself. The dead are already out of the
                    # living roster by the time this runs; the wounded are not, so
                    # their own wound is taken off their share.
                    his_own = (
                        morale_rules.wound_is_felt_for(hurt.turns)
                        for hurt in debriefing.pilot_outcomes.wounded
                        if id(pilot) in self._wounded_this_turn
                        and hurt.pilot_name == pilot.name
                        and hurt.squadron == str(squadron)
                    )
                    # Per man rather than per count, so each death is weighed by
                    # what this pilot thought of him. Anything the pass did not see
                    # die -- it should see all of them -- still counts once.
                    known = self._dead_this_turn.get(str(squadron), [])
                    for casualty in known:
                        self._note_morale(
                            pilot,
                            morale_rules.SQUADRON_DEATH,
                            self._grief_times(pilot, casualty),
                        )
                    self._note_morale(
                        pilot, morale_rules.SQUADRON_DEATH, deaths - len(known)
                    )
                    self._note_morale(
                        pilot, morale_rules.SQUADRON_WOUND, wounds - sum(his_own)
                    )
                    self._note_morale(pilot, morale_rules.BASE_LOST, lost)

    @property
    def xp_log(self) -> XpLog:
        """TEMPORARY: the turn's experience ledger, written out at the end of it."""
        if self._xp_log is None:
            self._xp_log = XpLog(getattr(self.game, "turn", "?"))
        return self._xp_log

    def commit(self, debriefing: Debriefing, events: GameUpdateEvents) -> None:
        with logged_duration("Committing mission results"):
            with logged_duration("commit_air_losses"):
                self.commit_air_losses(debriefing)
            with logged_duration("commit_pilot_experience"):
                self.commit_pilot_experience(debriefing)
            with logged_duration("commit_front_line_losses"):
                self.commit_front_line_losses(debriefing)
            with logged_duration("commit_motorpool_losses"):
                self.commit_motorpool_losses(debriefing, events)
            with logged_duration("commit_convoy_losses"):
                self.commit_convoy_losses(debriefing)
            with logged_duration("commit_cargo_ship_losses"):
                self.commit_cargo_ship_losses(debriefing)
            with logged_duration("commit_airlift_losses"):
                self.commit_airlift_losses(debriefing)
            with logged_duration("commit_ground_losses"):
                self.commit_ground_losses(debriefing, events)
            with logged_duration("commit_damaged_runways"):
                self.commit_damaged_runways(debriefing)
            with logged_duration("commit_cruise_missiles"):
                self.commit_cruise_missiles(debriefing)
            with logged_duration("commit_naval_magazines"):
                self.commit_naval_magazines(debriefing)
            # Score the front line before capturing bases: casualty_count
            # attributes a dead front-line unit to its origin CP regardless of
            # side, so a base's defenders (origin == that base) would be
            # miscounted as the new owner's casualties once a capture flips
            # ownership, turning a win into a defeat.
            with logged_duration("commit_front_line_battle_impact"):
                self.commit_front_line_battle_impact(debriefing, events)
            with logged_duration("commit_captures"):
                self.commit_captures(debriefing, events)
            # After captures: base ownership is final, so we can tell whether a
            # "remain at destination" assault reached a base we now hold.
            with logged_duration("commit_air_assault_remain"):
                self.commit_air_assault_remain(debriefing)
            with logged_duration("record_carcasses"):
                self.record_carcasses(debriefing)
            self.game.record_debrief(debriefing)

    def commit_air_losses(self, debriefing: Debriefing) -> None:
        for loss in debriefing.air_losses.losses:
            if self.game.settings.ignore_non_combat_air_losses and (
                debriefing.is_non_combat_loss(loss)
            ):
                # Campaign doctrine: a non-combat write-off (crash/collision/no
                # credited shooter) does not deplete the squadron or kill the pilot.
                logging.info(
                    f"Ignoring non-combat loss of {loss.flight.unit_type} from "
                    f"{loss.flight.squadron}"
                )
                continue
            if getattr(loss.flight, "parked_reserve", False):
                # An aircraft caught on the ramp. It is still an airframe lost, and
                # the count below takes it, but there was nobody in the cockpit --
                # every reserve on the apron is assigned a pilot so the debriefing
                # can account for it, and an attack on the parking used to kill them
                # all.
                logging.info(
                    f"{loss.flight.unit_type} destroyed on the ground at "
                    f"{loss.flight.squadron}; its pilot was not in it"
                )
            elif loss.pilot is not None:
                if loss.pilot.player and self.game.settings.invulnerable_player_pilots:
                    # Invulnerability is about his life, not about the sortie. He
                    # walks away, but he did not bring the aircraft home, and the
                    # mission-complete award is paid to whoever landed -- skipping
                    # this whole branch paid a shot-down player as though he had.
                    debriefing.pilot_outcomes.lost_aircraft.add(id(loss.pilot))
                else:
                    self._resolve_pilot_fate(loss, debriefing)
            squadron = loss.flight.squadron
            aircraft = loss.flight.unit_type
            available = squadron.owned_aircraft
            if available <= 0:
                logging.error(
                    f"Found killed {aircraft} from {squadron} but that airbase has "
                    "none available."
                )
                continue

            logging.info(f"{aircraft} destroyed from {squadron}")
            squadron.owned_aircraft -= 1
            squadron.destroyed_aircraft += 1

    def commit_air_assault_remain(self, debriefing: Debriefing) -> None:
        """Resolve helo air-assault flights flagged to remain at the objective.

        A remain flight is committed forward and never flies home, so its origin loses
        the whole flight however the sim classified each airframe. Holding the objective
        after captures are resolved turns those aircraft into a parked reserve at the
        captured base instead.

        """
        for coalition in self.game.coalitions:
            for package in coalition.ato.packages:
                for flight in package.flights:
                    if not getattr(flight, "remain_at_destination", False):
                        continue
                    if not flight.is_helo:
                        continue
                    origin = flight.squadron
                    # Take the whole flight off the origin. commit_air_losses already
                    # removed the losses it counts, so subtract only the remainder --
                    # otherwise a non-combat "crash" write-back silently keeps a
                    # committed helo that should be gone.
                    to_remove = flight.count - self._depleting_air_losses(
                        debriefing, flight
                    )
                    if to_remove > 0:
                        origin.owned_aircraft = max(
                            0, origin.owned_aircraft - to_remove
                        )
                    objective = self._objective_control_point(flight.package.target)
                    if objective is not None and objective.captured == coalition.player:
                        arrived = debriefing.air_losses.surviving_flight_members(flight)
                        if arrived > 0:
                            self._ferry_to_captured_base(
                                flight.unit_type, arrived, objective, coalition
                            )
                            logging.info(
                                f"{arrived} {flight.unit_type} remained at captured "
                                f"{objective} (from {origin})"
                            )
                    else:
                        where = objective.name if objective is not None else "objective"
                        logging.info(
                            f"Remain flight of {flight.unit_type} from {origin} lost: "
                            f"{where} not captured"
                        )

    def _depleting_air_losses(self, debriefing: Debriefing, flight: Flight) -> int:
        """This flight's air losses that commit_air_losses removed from the squadron,
        skipping the non-combat write-offs it forgives (so survivor math lines up)."""
        count = 0
        for loss in debriefing.air_losses.losses:
            if loss.flight != flight:
                continue
            if self.game.settings.ignore_non_combat_air_losses and (
                debriefing.is_non_combat_loss(loss)
            ):
                continue
            count += 1
        return count

    @staticmethod
    def _objective_control_point(target: MissionTarget) -> ControlPoint | None:
        if isinstance(target, ControlPoint):
            return target
        control_point = getattr(target, "control_point", None)
        return control_point if isinstance(control_point, ControlPoint) else None

    def _ferry_to_captured_base(
        self,
        aircraft: AircraftType,
        count: int,
        base: ControlPoint,
        coalition: Coalition,
    ) -> None:
        # Reinforce an existing squadron of the type already at the base...
        for squadron in base.squadrons:
            if squadron.aircraft == aircraft:
                squadron.owned_aircraft += count
                return
        # ...otherwise stand up a new squadron for the ferried aircraft.
        from ..ato import FlightType
        from ..squadrons.squadron import Squadron

        squadron_def = coalition.air_wing.squadron_def_generator.generate_for_aircraft(
            aircraft
        )
        squadron = Squadron.create_from(
            squadron_def,
            FlightType.AIR_ASSAULT,
            count,
            base,
            coalition,
            self.game,
        )
        squadron.owned_aircraft = count
        coalition.air_wing.add_squadron(squadron)

    def _resolve_pilot_fate(self, loss: Any, debriefing: Debriefing) -> None:
        """Decide whether the pilot dies, is saved by rank, or is saved by the medics.

        Two rolls in that order. The first needs Live Pilots and the rank survival
        setting; the second needs only Live Pilots, so a wound can still spare a pilot
        in a campaign that does not want the rank roll.

        """
        settings = self.game.settings
        pilot = loss.pilot
        squadron = loss.flight.squadron
        record = self._describe_loss(loss, debriefing)
        # However this ends for him, he did not bring the aircraft home.
        debriefing.pilot_outcomes.lost_aircraft.add(id(pilot))
        pilot.record.aircraft_lost += 1
        # What the men who were up there with him think of *him*: the half of
        # friendship that decides how hard anybody looks. Positive only -- being
        # disliked does not make somebody slower to reach a burning cockpit -- and read
        # before this turn's sorties are paid in, so today's flight cannot rescue him.
        mates = [
            other
            for other in loss.flight.roster.iter_pilots()
            if other is not None and other is not pilot
        ]
        rescue = (
            friendship.survival_bonus(
                friendship.mean_from(pilot, mates, squadron.leader_of(mates), settings),
                settings,
            )
            if friendship.in_play(settings)
            else 0.0
        )
        # And what he has been through himself, which is the half nobody else is
        # needed for: he has done this before and knows when to stop trying to save
        # the aircraft.
        rescue += hardening.survival_bonus(pilot.hardened, settings)
        rolls = settings.live_pilots_enabled and settings.live_pilots_rank_survival
        chance = (
            survival_chance(squadron.pilot_skill(pilot), settings) if rolls else 0.0
        )
        if rolls and getattr(settings, "morale_enabled", True) and pilot.has_morale:
            # The steady man gets out of the aircraft; the hollow one does not.
            chance = max(
                0.0, min(1.0, chance + morale_rules.survival_modifier(pilot.morale))
            )
        if rolls and rescue:
            chance = max(0.0, min(1.0, chance + rescue))
        survived = rolls and random.random() < chance

        def note(outcome: str) -> None:
            """One line per loss, written once both rolls are settled.

            Recording the first roll on its own said "died" about pilots the medics
            then saved two lines later.
            """
            if rolls or settings.live_pilots_enabled:
                self.xp_log.fate(
                    pilot,
                    squadron,
                    loss.flight.unit_type,
                    squadron.pilot_rank(pilot),
                    chance,
                    outcome,
                )

        if survived:
            pilot.record.survived_losses += 1
            note("walked away")
            debriefing.pilot_outcomes.survivors.append(record)
            logging.info(f"{pilot.name} survived the loss of his aircraft")
            return

        if settings.live_pilots_enabled and (
            random.random() < settings.live_pilots_wounded_chance / 100 + rescue
        ):
            turns = random.randint(*WOUNDED_TURNS)
            if getattr(settings, "morale_enabled", True):
                turns = morale_rules.recovery_turns(turns, pilot.morale, settings)
            pilot.wound(turns, self.game.turn)
            pilot.record.survived_losses += 1
            pilot.record.wounds += 1
            pilot.record.turns_in_hospital += turns
            pilot.record.last_wound_turn = self.game.turn
            pilot.record.last_wound_turns = turns
            self._wounded_this_turn.add(id(pilot))
            self._note_flight_morale(
                loss.flight, pilot, morale_rules.FLIGHT_WOUND, turns
            )
            debriefing.pilot_outcomes.wounded.append(
                PilotWound(
                    pilot.name,
                    str(squadron),
                    turns,
                    aircraft=str(loss.flight.unit_type),
                    rank=self._short_rank(squadron, pilot),
                    level=self._rank_level(squadron, pilot),
                    # The same attribution the dead get: who put him there is the
                    # interesting half, not that the medics reached him.
                    killed_by=record.killed_by,
                    friendly_fire=record.friendly_fire,
                    blue=squadron.player.is_blue,
                )
            )
            note(f"wounded, out for {turns_phrase(turns)}")
            logging.info(
                f"{pilot.name} was wounded and is out for {turns_phrase(turns)}"
            )
            return

        note("died")
        pilot.record.killed_by = self._killer_parts(
            debriefing.kill_info_by_unit_id.get(id(loss)),
            debriefing,
            squadron.player.is_blue,
            self.game.turn,
        )
        pilot.kill()
        self._dead_this_turn.setdefault(str(squadron), []).append(pilot)
        self._note_flight_morale(loss.flight, pilot, morale_rules.FLIGHT_DEATH)
        debriefing.pilot_outcomes.deaths.append(record)

    @staticmethod
    def _short_rank(squadron: Any, pilot: Any) -> str:
        rank = squadron.pilot_rank(pilot)
        return "" if rank is None else rank.abbreviation

    @staticmethod
    def _rank_level(squadron: Any, pilot: Any) -> int:
        """Which of the five rungs he stands on, for the stars beside his name."""
        return morale_rules.rank_level(squadron.pilot_skill(pilot))

    def _note_flight_morale(
        self, flight: Any, casualty: Any, event: Any, turns: int = 1
    ) -> None:
        """Apply the death to the pilots who were in his flight.

        The flight only, not the package: the rest of the package was not there to see
        it.

        """
        if not getattr(self.game.settings, "morale_enabled", True):
            return
        base = morale_rules.wound_is_felt_for(turns) if turns > 1 else 1
        for mate in flight.roster.iter_pilots():
            if mate is None or mate is casualty or not mate.alive:
                continue
            self._note_morale(mate, event, base * self._grief_times(mate, casualty))

    def _grief_times(self, mourner: Any, casualty: Any) -> int:
        """How many times a death is applied to one survivor.

        Scaled by what the survivor thought of him, and never below once.

        """
        settings = self.game.settings
        if not friendship.in_play(settings):
            return 1
        return friendship.grief_times(
            1, friendship.feeling(mourner, casualty), settings
        )

    def _describe_loss(self, loss: Any, debriefing: Debriefing) -> PilotDeath:
        squadron = loss.flight.squadron
        detail = debriefing.kill_info_by_unit_id.get(id(loss))
        killer, friendly = self._describe_killer(
            detail, debriefing, squadron.player.is_blue
        )
        return PilotDeath(
            pilot_name=loss.pilot.name if loss.pilot is not None else "Unknown pilot",
            squadron=str(squadron),
            aircraft=str(loss.flight.unit_type),
            killed_by=killer,
            friendly_fire=friendly,
            rank=(
                self._short_rank(squadron, loss.pilot) if loss.pilot is not None else ""
            ),
            level=(
                self._rank_level(squadron, loss.pilot) if loss.pilot is not None else 0
            ),
            blue=squadron.player.is_blue,
        )

    def _killer_parts(
        self,
        detail: Optional[dict[str, Any]],
        debriefing: Debriefing,
        victim_is_blue: bool,
        turn: int = 0,
    ) -> Optional[KilledBy]:
        """Who made the kill, with what, and on which side.

        DCS credits exactly one initiator per kill and has no notion of an assist, so
        this is whoever landed the killing blow. In order of preference: the roster
        pilot flying the killing aircraft, the human player's name, then the airframe or
        vehicle type.

        """
        if not detail:
            return None

        name = ""
        squadron = ""
        friendly = False
        initiator = detail.get("initiator")
        if initiator:
            killer = debriefing.unit_map.flight(str(initiator))
            if killer is not None:
                friendly = killer.flight.squadron.player.is_blue == victim_is_blue
                squadron = str(killer.flight.squadron)
                if killer.pilot is not None:
                    name = killer.pilot.name

        if not name:
            name = detail.get("initiator_player") or detail.get("initiator_type") or ""

        return KilledBy(
            pilot_name=name,
            squadron=squadron,
            aircraft=str(detail.get("initiator_type") or ""),
            weapon=str(detail.get("weapon") or ""),
            friendly_fire=friendly,
            turn=turn,
        )

    def _describe_killer(
        self,
        detail: Optional[dict[str, Any]],
        debriefing: Debriefing,
        victim_is_blue: bool,
    ) -> tuple[Optional[str], bool]:
        """The same thing as one line, for the debriefing."""
        if not detail:
            return "a crash", False
        parts = self._killer_parts(detail, debriefing, victim_is_blue)
        if parts is None or not parts.pilot_name:
            return None, parts.friendly_fire if parts is not None else False
        return killer_sentence(parts), parts.friendly_fire

    def _victim_is_blue(self, victim: Any) -> Optional[bool]:
        """Which side the destroyed thing belonged to, where that can be established."""
        flight = getattr(victim, "flight", None)
        if flight is not None:
            return bool(flight.squadron.player.is_blue)
        for attr in ("origin", "airfield"):
            origin = getattr(victim, attr, None)
            if origin is not None and hasattr(origin, "captured"):
                return bool(origin.captured.is_blue)
        for attr in ("theater_unit", "ground_unit"):
            unit = getattr(victim, attr, None)
            tgo = getattr(unit, "ground_object", None)
            if tgo is not None:
                return bool(tgo.control_point.captured.is_blue)
        convoy = getattr(victim, "convoy", None)
        if convoy is not None:
            return bool(convoy.player_owned.is_blue)
        return None

    @staticmethod
    def _victim_kind(victim: Any) -> Victim:
        """What was destroyed: its class and its name.

        One walk over the object rather than two, so the XP table and the pilot's tally
        cannot disagree about it.

        """
        if victim is None:
            return Victim(NOTHING)

        flight = getattr(victim, "flight", None)
        if flight is not None:
            return Victim(AIR, _named(getattr(flight, "unit_type", None)))

        convoy = getattr(victim, "convoy", None)
        if convoy is not None:
            unit_type = getattr(victim, "unit_type", None)
            return Victim(
                VEHICLE, _named(unit_type), ground_class=_ground_class(unit_type)
            )

        if hasattr(victim, "unit_type") and getattr(victim, "origin", None) is not None:
            # Front line and motorpool vehicles.
            return Victim(
                VEHICLE,
                _named(victim.unit_type),
                ground_class=_ground_class(victim.unit_type),
            )

        unit = getattr(victim, "theater_unit", None) or getattr(
            victim, "ground_unit", None
        )
        if unit is None:
            return Victim(NOTHING)

        unit_type = getattr(unit, "unit_type", None)
        if unit_type is not None:
            from game.dcs.shipunittype import ShipUnitType

            if isinstance(unit_type, ShipUnitType):
                return Victim(SHIP, _named(unit_type), ground_class=SHIPS)
            return Victim(
                VEHICLE, _named(unit_type), ground_class=_ground_class(unit_type)
            )

        # No unit type: a static or a scenery objective, named by what it is part of.
        tgo = getattr(unit, "ground_object", None)
        if tgo is None:
            return Victim(UNKNOWN)
        category = getattr(tgo, "category", None)
        return Victim(
            BUILDING, str(tgo), building_category=category, ground_class=STRUCTURES
        )

    def _kill_xp(self, victim: Any) -> int:
        """The experience destroying this was worth.

        Proportionality comes from the pieces: a refinery is several platforms with a
        death each, so destroying two of them pays for two. DCS reports no damage
        magnitude, so nothing is divided any finer.

        """
        victim_kind = self._victim_kind(victim)
        if victim_kind.kind == AIR:
            return XP_AIR_KILL
        if victim_kind.kind == SHIP:
            return XP_SHIP_KILL
        if victim_kind.kind == VEHICLE:
            return XP_GROUND_KILL
        if victim_kind.kind == BUILDING:
            return building_xp(victim_kind.building_category)
        if victim_kind.kind == UNKNOWN:
            return XP_UNKNOWN_KILL
        return 0

    def _credited_events(
        self, details: Any, debriefing: Debriefing, note_friendly_fire: bool = False
    ) -> Iterator[tuple[Pilot, str, Any, Any, str]]:
        """(pilot, target name, target, the killer's flight, the weapon) per credited record.

        Shared by kills and hits, which the plugin writes in the same shape. Records
        that cannot be resolved to a roster pilot are dropped, as is friendly fire.

        """
        for detail in details:
            if not isinstance(detail, dict):
                continue
            initiator = detail.get("initiator")
            target = detail.get("target")
            if not initiator or not target:
                continue
            killer = debriefing.unit_map.flight(str(initiator))
            if killer is None or killer.pilot is None:
                continue
            victim = debriefing.resolve_killed_object(str(target))
            victim_blue = self._victim_is_blue(victim)
            if victim_blue is not None and (
                victim_blue == killer.flight.squadron.player.is_blue
            ):
                # Nobody is paid for shooting his own side -- but from here on it is
                # not free either. Only off the kills: a scratch is not the same story
                # as a burning wingman, and the hits are the same events again.
                if note_friendly_fire:
                    self._note_friendly_fire_event(killer, victim)
                continue
            yield killer.pilot, str(target), victim, killer.flight, str(
                detail.get("weapon") or ""
            )

    def _experience_from_kills(
        self, debriefing: Debriefing
    ) -> tuple[dict[int, int], set[tuple[int, str]]]:
        """Experience earned per pilot, keyed by pilot identity.

        Also returns the (pilot, target) pairs it paid for, so the damage pass does not
        pay again for the hit that finished the job.

        """
        earned: dict[int, int] = {}
        credited: set[tuple[int, str]] = set()
        for pilot, target, victim, flight, weapon in self._credited_events(
            debriefing.state_data.kill_details, debriefing, note_friendly_fire=True
        ):
            credited.add((id(pilot), target))
            kind = self._victim_kind(victim)
            xp = self._kill_xp(victim)
            if xp:
                earned[id(pilot)] = earned.get(id(pilot), 0) + xp
                self.xp_log.award(pilot, xp, "destroyed", victim, target)
            # His own tally, which the campaign never reads and the pilot dialog is
            # the whole reason for. Kept only for what has a name: "one of something
            # unrecognised" is not worth a row.
            if kind.kind == AIR:
                pilot.record.note_kill(
                    air=True, what=kind.name, turn=self.game.turn, weapon=weapon
                )
                self._note_morale(pilot, morale_rules.AIR_KILL)
            else:
                pilot.record.note_kill(
                    air=False,
                    what=kind.name,
                    kill_class=kind.ground_class,
                    turn=self.game.turn,
                    weapon=weapon,
                )
                if not self._was_the_assigned_target(victim, flight):
                    self._note_morale(pilot, morale_rules.UNPLANNED_KILL)
        return earned, credited

    @staticmethod
    def _was_the_assigned_target(victim: Any, flight: Any) -> bool:
        """Whether this target is what the package was sent for.

        Anything else counts as a target of opportunity, which is worth less. The engine
        cannot distinguish a pilot's own initiative from an order given on the F10 map,
        so both read the same here.

        """
        target = getattr(getattr(flight, "package", None), "target", None)
        if target is None:
            return True  # nothing to compare against; assume he did as he was told
        unit = getattr(victim, "theater_unit", None) or getattr(
            victim, "ground_unit", None
        )
        objective = getattr(unit, "ground_object", None)
        if objective is None:
            return True
        return getattr(objective, "name", None) == getattr(target, "name", None)

    def _experience_from_damage(
        self, debriefing: Debriefing, credited: set[tuple[int, str]]
    ) -> dict[int, int]:
        """A share of the kill for damaging something without destroying it.

        DCS names the shooter on every hit and the plugin records the first one each
        aircraft lands on each target, so a pilot is paid once per target he damaged.

        """
        earned: dict[int, int] = {}
        for pilot, target, victim, _flight, _weapon in self._credited_events(
            debriefing.state_data.hit_details, debriefing
        ):
            if (id(pilot), target) in credited:
                continue
            xp = int(self._kill_xp(victim) * XP_DAMAGE_SHARE)
            if xp:
                earned[id(pilot)] = earned.get(id(pilot), 0) + xp
                self.xp_log.award(pilot, xp, "damaged", victim, target)
        return earned

    def _commit_pilot_experience(
        self, ato: AirTaskingOrder, debriefing: Debriefing, earned: dict[int, int]
    ) -> None:
        for package in ato.packages:
            for flight in package.flights:
                squadron = flight.squadron
                for idx, pilot in enumerate(flight.roster.iter_pilots()):
                    if pilot is None:
                        logging.error(
                            f"Cannot award experience to pilot #{idx} of {flight} "
                            "because no pilot is assigned"
                        )
                        continue
                    pilot.record.missions_flown += 1
                    pilot.note_sortie(self.game.turn)
                    self._note_flying_together(package, flight, pilot)
                    self._note_mission_morale(
                        flight, squadron, pilot, debriefing, earned
                    )
                    if not pilot.alive:
                        # Losses are committed before this runs. He earned it and did
                        # not live to collect it.
                        self.xp_log.uncollected(
                            pilot,
                            squadron,
                            flight.unit_type,
                            earned.get(id(pilot), 0),
                        )
                        continue

                    before = squadron.pilot_rank(pilot)
                    before_level = self._rank_level(squadron, pilot)
                    had = pilot.record.xp
                    # A pilot who lost the aircraft did not complete the mission. If
                    # the medics reached him, the wound is his consolation -- smaller
                    # than the sortie, so being shot down is never the better outcome.
                    extras = []
                    if id(pilot) not in debriefing.pilot_outcomes.lost_aircraft:
                        pilot.record.missions_completed += 1
                        extras.append(
                            ("returned", "mission complete", XP_MISSION_COMPLETE)
                        )
                    if pilot.wounded:
                        extras.append(
                            (
                                "wounded",
                                f"out for {turns_phrase(pilot.wounded_turns)}",
                                XP_WOUNDED,
                            )
                        )
                    # The same floor pilot_skill measures against, or the rungs
                    # would be counted from the difficulty setting Live Pilots
                    # replaces.
                    multiplier = self._xp_multiplier(flight, squadron, pilot)
                    paid = round(
                        (earned.get(id(pilot), 0) + sum(x for _, _, x in extras))
                        * multiplier
                    )
                    if multiplier != 1.0:
                        extras.append(
                            (
                                "x%.1f" % multiplier,
                                "morale and the company he flew in",
                                paid
                                - earned.get(id(pilot), 0)
                                - sum(x for _, _, x in extras),
                            )
                        )
                    raw = had + paid
                    pilot.record.xp = one_promotion_at_most(
                        had, raw, squadron.base_skill, self.game.settings
                    )
                    if pilot.record.xp < raw:
                        extras.append(
                            (
                                "forfeit",
                                "no more than one promotion a mission",
                                pilot.record.xp - raw,
                            )
                        )
                    after = squadron.pilot_rank(pilot)
                    promotion = None
                    if before is not None and after is not None and after != before:
                        promotion = f"{before.abbreviation} -> {after.abbreviation}"
                        self._note_morale(pilot, morale_rules.PROMOTED)
                        debriefing.pilot_outcomes.promotions.append(
                            PilotPromotion(
                                pilot_name=pilot.name,
                                squadron=str(squadron),
                                from_rank=before.abbreviation,
                                to_rank=after.abbreviation,
                                to_rank_full=after.name,
                                player=pilot.player,
                                aircraft=str(squadron.aircraft),
                                from_level=before_level,
                                to_level=self._rank_level(squadron, pilot),
                                blue=squadron.player.is_blue,
                            )
                        )
                    self.xp_log.collected(
                        pilot,
                        squadron,
                        flight.unit_type,
                        had,
                        pilot.record.xp,
                        extras,
                        promotion,
                    )

    def _note_flying_together(self, package: Any, flight: Any, pilot: Any) -> None:
        """Apply the sortie's friendship gain for this pilot, in his own direction only.

        The opposite direction is moved when that pilot's own turn through the loop
        comes round, so each directed pair is touched exactly once.

        """
        settings = self.game.settings
        if not friendship.in_play(settings):
            return
        wing = friendship.flew_together(settings)
        rest_of_package = friendship.same_package(settings)
        for other in flight.roster.iter_pilots():
            if other is not None:
                self._note_friendship(pilot, other, wing)
        for other_flight in package.flights:
            if other_flight is flight:
                continue
            for other in other_flight.roster.iter_pilots():
                if other is not None:
                    self._note_friendship(pilot, other, rest_of_package)

    def _note_friendly_fire_event(self, killer: Any, victim: Any) -> None:
        """Apply the friendly-fire penalty to what the witnesses think of the pilot.

        His own flight, who saw it, and the victim's squadron, who hear about it.

        """
        settings = self.game.settings
        if not friendship.in_play(settings):
            return
        shooter = killer.pilot
        if shooter is None:
            return
        air_flight, air_squadron, ground = friendship.friendly_fire_penalties(settings)
        victim_flight = getattr(victim, "flight", None)
        for mourner in killer.flight.roster.iter_pilots():
            if mourner is not None:
                self._note_friendly_fire(
                    mourner, shooter, air_flight if victim_flight else ground
                )
        if victim_flight is None:
            return  # a truck has no squadron to hear about it
        squadron = getattr(victim_flight, "squadron", None)
        for mourner in getattr(squadron, "current_roster", []):
            self._note_friendly_fire(mourner, shooter, air_squadron)

    def _xp_multiplier(self, flight: Any, squadron: Any, pilot: Any) -> float:
        """The experience multiplier for this pilot's sortie.

        Three things move it: his morale, the best pilot in the formation (who teaches
        the ones below him and gains nothing himself), and what he thinks of the crew he
        flew with.

        """
        settings = self.game.settings
        if not settings.live_pilots_enabled:
            return 1.0
        morale_on = getattr(settings, "morale_enabled", True)
        best = squadron.pilot_skill(pilot)
        # The same man twice over: the one who teaches, and the one the formation is
        # measured through. He starts as the pilot himself, so a man who is the senior
        # one in his flight weighs everybody equally -- from where he sits there is
        # nobody in front.
        leader = pilot
        mates = []
        for other in flight.roster.iter_pilots():
            if other is None:
                continue
            if other is not pilot:
                mates.append(other)
            skill = (
                other.squadron.pilot_skill(other)
                if hasattr(other, "squadron")
                else (squadron.pilot_skill(other))
            )
            if SKILL_LADDER.index(skill) > SKILL_LADDER.index(best):
                best = skill
                leader = other
        # The player has no morale to be worth more or less for; flying with someone
        # better than you is not morale, so he keeps that half of it.
        state = (
            morale_rules.xp_multiplier(pilot.morale)
            if morale_on and pilot.has_morale
            else 1.0
        )
        learning = (
            morale_rules.learning_bonus(squadron.pilot_skill(pilot), best)
            if morale_on
            else 0.0
        )
        company = (
            friendship.xp_bonus(
                friendship.mean_towards(pilot, mates, leader, settings), settings
            )
            if friendship.in_play(settings)
            else 0.0
        )
        return max(0.0, state + learning + company)

    def _note_mission_morale(
        self,
        flight: Any,
        squadron: Any,
        pilot: Any,
        debriefing: Debriefing,
        earned: dict[int, int],
    ) -> None:
        """What his own sortie did to him."""
        outcomes = debriefing.pilot_outcomes
        if id(pilot) in outcomes.lost_aircraft:
            if pilot.alive:
                self._note_morale(pilot, morale_rules.LOST_AIRCRAFT)
            return
        self._note_morale(pilot, morale_rules.MISSION_COMPLETE)
        if flight.flight_type.name in morale_rules.STRIKE_TASKS and not earned.get(
            id(pilot)
        ):
            # He was sent to destroy something and destroyed nothing. A CAP that saw
            # nobody has not failed at anything, so those are left out of it.
            self._note_morale(pilot, morale_rules.ACHIEVED_NOTHING)

    def commit_pilot_experience(self, debriefing: Debriefing) -> None:
        earned, credited = self._experience_from_kills(debriefing)
        for pilot_id, xp in self._experience_from_damage(debriefing, credited).items():
            earned[pilot_id] = earned.get(pilot_id, 0) + xp
        self._commit_pilot_experience(self.game.blue.ato, debriefing, earned)
        self._commit_pilot_experience(self.game.red.ato, debriefing, earned)
        self._note_shared_morale(debriefing)
        self._commit_morale(debriefing)
        self._commit_friendship()
        self.xp_log.write()
        self._xp_log = None

    @staticmethod
    def commit_front_line_losses(debriefing: Debriefing) -> None:
        for loss in debriefing.front_line_losses:
            unit_type = loss.unit_type
            control_point = loss.origin
            available = control_point.base.total_units_of_type(unit_type)
            if available <= 0:
                logging.error(
                    f"Found killed {unit_type} from {control_point} but that "
                    "airbase has none available."
                )
                continue

            logging.info(f"{unit_type} destroyed from {control_point}")
            control_point.base.armor[unit_type] -= 1

    @staticmethod
    def commit_motorpool_losses(
        debriefing: Debriefing, events: GameUpdateEvents
    ) -> None:
        for loss in debriefing.motorpool_losses:
            unit_type = loss.unit_type
            control_point = loss.origin
            available = control_point.base.total_units_of_type(unit_type)
            if available <= 0:
                logging.error(
                    f"Found killed motorpool {unit_type} from {control_point} but "
                    "that base has none available."
                )
                continue
            logging.info(f"Motorpool {unit_type} destroyed from {control_point}")
            control_point.base.armor[unit_type] -= 1
            # Refresh the motorpool projection so the depleted TGO is republished
            # in the operation's single accumulator.
            events.update_motorpools_at(control_point)

    @staticmethod
    def commit_convoy_losses(debriefing: Debriefing) -> None:
        for loss in debriefing.convoy_losses:
            unit_type = loss.unit_type
            convoy = loss.convoy
            available = loss.convoy.units.get(unit_type, 0)
            convoy_name = f"convoy from {convoy.origin} to {convoy.destination}"
            if available <= 0:
                logging.error(
                    f"Found killed {unit_type} in {convoy_name} but that convoy has "
                    "none available."
                )
                continue

            logging.info(f"{unit_type} destroyed in {convoy_name}")
            convoy.kill_unit(unit_type)

    @staticmethod
    def commit_cargo_ship_losses(debriefing: Debriefing) -> None:
        for ship in debriefing.cargo_ship_losses:
            logging.info(
                f"All units destroyed in cargo ship from {ship.origin} to "
                f"{ship.destination}."
            )
            ship.kill_all()

    @staticmethod
    def commit_airlift_losses(debriefing: Debriefing) -> None:
        for loss in debriefing.airlift_losses:
            transfer = loss.transfer
            airlift_name = f"airlift from {transfer.origin} to {transfer.destination}"
            for unit_type in loss.cargo:
                try:
                    transfer.kill_unit(unit_type)
                    logging.info(f"{unit_type} destroyed in {airlift_name}")
                except KeyError:
                    logging.exception(
                        f"Found killed {unit_type} in {airlift_name} but that airlift "
                        "has none available."
                    )

    @staticmethod
    def commit_ground_losses(debriefing: Debriefing, events: GameUpdateEvents) -> None:
        for ground_object_loss in debriefing.ground_object_losses:
            ground_object_loss.theater_unit.kill(events)
        for scenery_object_loss in debriefing.scenery_object_losses:
            scenery_object_loss.ground_unit.kill(events)

    @staticmethod
    def commit_damaged_runways(debriefing: Debriefing) -> None:
        for damaged_runway in debriefing.damaged_runways:
            damaged_runway.damage_runway()

    def commit_cruise_missiles(self, debriefing: Debriefing) -> None:
        # Debit each launching ship group's campaign magazine by what the cruisemissiles
        # plugin reported fired. The only debit site in the feature, which is what makes
        # regenerating a mission free of charge. No-op when nothing was reported.
        from game.cruise_raids import reconcile_cruise_missiles

        reconcile_cruise_missiles(self.game, debriefing)

    def commit_naval_magazines(self, debriefing: Debriefing) -> None:
        # Debit each naval group's persisted anti-ship magazine by what the
        # navalmagazines plugin reported fired. The only debit site, so re-generating
        # a mission never double-counts, and the weapon set is disjoint from the
        # cruise-missile magazine's so a shot is never charged twice. No-op when
        # nothing was reported.
        from game.naval_magazines import reconcile_naval_magazines

        reconcile_naval_magazines(self.game, debriefing)

    def commit_captures(self, debriefing: Debriefing, events: GameUpdateEvents) -> None:
        for captured in debriefing.base_captures:
            try:
                if captured.captured_by_player.is_blue:
                    self.game.message(
                        f"{captured.control_point} captured!",
                        f"We took control of {captured.control_point}.",
                    )
                else:
                    self.game.message(
                        f"{captured.control_point} lost!",
                        f"The enemy took control of {captured.control_point}.",
                    )

                captured.control_point.capture(
                    self.game, events, captured.captured_by_player
                )
            except Exception:
                logging.exception(f"Could not process base capture {captured}")

        for captured in debriefing.base_captures:
            logging.info(f"Will run redeploy for {captured.control_point}")
            self.redeploy_units(captured.control_point)

    def record_carcasses(self, debriefing: Debriefing) -> None:
        for destroyed_unit in debriefing.state_data.destroyed_statics:
            self.game.add_destroyed_units(destroyed_unit)

    def commit_front_line_battle_impact(
        self, debriefing: Debriefing, events: GameUpdateEvents
    ) -> None:
        for cp in self.game.theater.player_points():
            enemy_cps = [e for e in cp.connected_points if e.captured.is_red]
            for enemy_cp in enemy_cps:
                front_line = cp.front_line_with(enemy_cp)
                front_line.update_position()
                events.update_front_line(front_line)

                print(
                    "Compute frontline progression for : "
                    + cp.name
                    + " to "
                    + enemy_cp.name
                )

                delta = 0.0
                player_won = True
                status_msg: str = ""
                ally_casualties = debriefing.casualty_count(cp)
                enemy_casualties = debriefing.casualty_count(enemy_cp)
                ally_units_alive = cp.base.total_armor
                enemy_units_alive = enemy_cp.base.total_armor

                print(f"Remaining allied units: {ally_units_alive}")
                print(f"Remaining enemy units: {enemy_units_alive}")
                print(f"Allied casualties {ally_casualties}")
                print(f"Enemy casualties {enemy_casualties}")

                ratio = (1.0 + enemy_casualties) / (1.0 + ally_casualties)

                player_aggresive = cp.stances[enemy_cp.id] in [
                    CombatStance.AGGRESSIVE,
                    CombatStance.ELIMINATION,
                    CombatStance.BREAKTHROUGH,
                ]

                if ally_units_alive == 0:
                    player_won = False
                    delta = STRONG_DEFEAT_INFLUENCE
                    status_msg = f"No allied units alive at {cp.name}-{enemy_cp.name} frontline.  Allied ground forces suffer a strong defeat."
                elif enemy_units_alive == 0:
                    player_won = True
                    delta = STRONG_DEFEAT_INFLUENCE
                    status_msg = f"No enemy units alive at {cp.name}-{enemy_cp.name} frontline.  Allied ground forces win a strong victory."
                elif cp.stances[enemy_cp.id] == CombatStance.RETREAT:
                    player_won = False
                    delta = STRONG_DEFEAT_INFLUENCE
                    status_msg = f"Allied forces are retreating along the {cp.name}-{enemy_cp.name} frontline, suffering a strong defeat."
                else:
                    if enemy_casualties > ally_casualties:
                        player_won = True
                        if cp.stances[enemy_cp.id] == CombatStance.BREAKTHROUGH:
                            delta = STRONG_DEFEAT_INFLUENCE
                            status_msg = f"Allied forces break through the {cp.name}-{enemy_cp.name} frontline, winning a strong victory"
                        else:
                            if ratio > 3:
                                delta = STRONG_DEFEAT_INFLUENCE
                                status_msg = f"Enemy casualties massively outnumber allied casualties along the {cp.name}-{enemy_cp.name} frontline.  Allied forces win a strong victory."
                            elif ratio < 1.5:
                                delta = MINOR_DEFEAT_INFLUENCE
                                status_msg = f"Enemy casualties minorly outnumber allied casualties along the {cp.name}-{enemy_cp.name} frontline.  Allied forces win a minor victory."
                            else:
                                delta = DEFEAT_INFLUENCE
                                status_msg = f"Enemy casualties outnumber allied casualties along the {cp.name}-{enemy_cp.name} frontline.  Allied forces claim a victory."
                    elif ally_casualties > enemy_casualties:
                        if (
                            ally_units_alive > 2 * enemy_units_alive
                            and player_aggresive
                        ):
                            # Even with casualties if the enemy is overwhelmed, they are going to lose ground
                            player_won = True
                            delta = MINOR_DEFEAT_INFLUENCE
                            status_msg = f"Despite suffering losses, allied forces still outnumber enemy forces along the {cp.name}-{enemy_cp.name} frontline.  Due to allied force's aggressive posture, allied forces claim a minor victory."
                        elif (
                            ally_units_alive > 3 * enemy_units_alive
                            and player_aggresive
                        ):
                            player_won = True
                            delta = STRONG_DEFEAT_INFLUENCE
                            status_msg = f"Despite suffering losses, allied forces still heavily outnumber enemy forces along the {cp.name}-{enemy_cp.name} frontline.  Due to allied force's aggressive posture, allied forces claim a major victory."
                        else:
                            # But if the enemy is not outnumbered, we lose
                            player_won = False
                            if cp.stances[enemy_cp.id] == CombatStance.BREAKTHROUGH:
                                delta = STRONG_DEFEAT_INFLUENCE
                                status_msg = f"Allied casualties outnumber enemy casualties along the {cp.name}-{enemy_cp.name} frontline.  Allied forces have overextended themselves, suffering a major defeat."
                            else:
                                delta = DEFEAT_INFLUENCE
                                status_msg = f"Allied casualties outnumber enemy casualties along the {cp.name}-{enemy_cp.name} frontline.  Allied forces suffer a defeat."

                    # No progress with defensive strategies
                    if player_won and cp.stances[enemy_cp.id] in [
                        CombatStance.DEFENSIVE,
                        CombatStance.AMBUSH,
                    ]:
                        print(
                            f"Allied forces have adopted a defensive stance along the {cp.name}-{enemy_cp.name} "
                            f"frontline, making only limited progress."
                        )
                        delta = MINOR_DEFEAT_INFLUENCE

                # Handle the case where there are no casualties at all on either side but both sides still have units
                if delta == 0.0:
                    print(status_msg)
                    self.game.message(
                        "Frontline Report",
                        f"Our ground forces from {cp.name} reached a stalemate with enemy forces from {enemy_cp.name}.",
                    )
                else:
                    if player_won:
                        print(status_msg)
                        cp.base.affect_strength(delta)
                        enemy_cp.base.affect_strength(-delta)
                        self.game.message(
                            "Frontline Report",
                            f"Our ground forces from {cp.name} are making progress toward {enemy_cp.name}. {status_msg}",
                        )
                    else:
                        print(status_msg)
                        enemy_cp.base.affect_strength(delta)
                        cp.base.affect_strength(-delta)
                        self.game.message(
                            "Frontline Report",
                            f"Our ground forces from {cp.name} are losing ground against the enemy forces from "
                            f"{enemy_cp.name}. {status_msg}",
                        )

    def redeploy_units(self, cp: ControlPoint) -> None:
        """ "
        Auto redeploy units to newly captured base
        """
        enemy_connected_cps = [
            ocp for ocp in cp.connected_points if cp.captured != ocp.captured
        ]

        # If the newly captured cp does not have enemy connected cp,
        # then it is not necessary to redeploy frontline units there.
        if len(enemy_connected_cps) == 0:
            return

        ally_connected_cps = [
            ocp
            for ocp in cp.transitive_connected_friendly_destinations()
            if cp.captured == ocp.captured and ocp.base.total_armor
        ]

        settings = cp.coalition.game.settings
        factor = (
            settings.frontline_reserves_factor
            if cp.captured.is_blue
            else settings.frontline_reserves_factor_red
        )

        # From each ally cp, send reinforcements
        for ally_cp in sorted(
            ally_connected_cps,
            key=lambda x: len(
                [cp for cp in x.connected_points if x.captured != cp.captured]
            ),
        ):
            self.redeploy_between(cp, ally_cp)
            if cp.base.total_armor > factor * cp.deployable_front_line_units:
                break

    def redeploy_between(self, destination: ControlPoint, source: ControlPoint) -> None:
        total_units_redeployed = 0
        moved_units = {}

        settings = source.coalition.game.settings
        reserves = max(
            1,
            (
                settings.reserves_procurement_target
                if source.captured.is_blue
                else settings.reserves_procurement_target_red
            ),
        )
        total_units = source.base.total_armor
        reserves_factor = (reserves - 1) / total_units  # slight underestimation

        source_frontline_count = len(
            [cp for cp in source.connected_points if not source.is_friendly_to(cp)]
        )

        move_factor = max(0.0, 1 / (source_frontline_count + 1) - reserves_factor)

        for frontline_unit, count in source.base.armor.items():
            moved_count = int(count * move_factor)
            moved_units[frontline_unit] = moved_count
            total_units_redeployed += moved_count

        destination.base.commission_units(moved_units)
        source.base.commit_losses(moved_units)

        # Also transfer pending deliveries.
        for unit_type, count in list(source.ground_unit_orders.units.items()):
            move_count = int(count * move_factor)
            source.ground_unit_orders.sell({unit_type: move_count})
            destination.ground_unit_orders.order({unit_type: move_count})
            total_units_redeployed += move_count

        if total_units_redeployed > 0:
            self.game.message(
                "Units redeployed",
                f"{total_units_redeployed}  units have been redeployed from "
                f"{source.name} to {destination.name}",
            )
