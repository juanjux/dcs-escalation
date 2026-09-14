from __future__ import annotations

import logging
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Union
from typing import Optional, Sequence, TYPE_CHECKING
from uuid import uuid4, UUID

from dcs.country import Country
from dcs.unit import Skill
from faker import Faker

from game.ato import Flight, FlightType, Package
from game.settings import AutoAtoBehavior, Settings
from game.theater import ParkingType
from game.theater.player import Player
from .pilot import Pilot, PilotStatus
from game.dcs.skills import CADET_SKILL, SKILL_LADDER, skill_for_experience
from game.squadrons import friendship
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.morale import TURNS_BEFORE_LEAVE_IS_MISSED, shifted_skill

from .pilotnames import faker_for_country
from .pilotranks import Rank, rank_for_skill, ranks_for
from ..db.database import Database
from ..radio.radios import RadioFrequency
from ..utils import meters, nautical_miles

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.dcs.aircrafttype import AircraftType
    from game.theater import ControlPoint, MissionTarget
    from .operatingbases import OperatingBases
    from .squadrondef import SquadronDef


@dataclass
class Squadron:
    id: UUID = field(init=False, default_factory=uuid4)

    name: str
    nickname: Optional[str]
    country: Country
    role: str
    aircraft: AircraftType
    max_size: int
    livery: Optional[str]
    livery_set: list[str]  # will override livery if not empty
    primary_task: FlightType
    auto_assignable_mission_types: set[FlightType]
    radio_presets: dict[Union[str, int], list[RadioFrequency]]
    operating_bases: OperatingBases
    female_pilot_percentage: int

    #: The pool of pilots that have not yet been assigned to the squadron. This only
    #: happens when a preset squadron defines more preset pilots than the squadron limit
    #: allows. This pool will be consumed before random pilots are generated.
    pilot_pool: list[Pilot]

    current_roster: list[Pilot] = field(default_factory=list, init=False, hash=False)
    available_pilots: list[Pilot] = field(
        default_factory=list, init=False, hash=False, compare=False
    )

    coalition: Coalition = field(hash=False, compare=False)
    flight_db: Database[Flight] = field(hash=False, compare=False)
    settings: Settings = field(hash=False, compare=False)

    location: ControlPoint
    destination: Optional[ControlPoint] = field(
        init=False, hash=False, compare=False, default=None
    )

    #: This squadron's own pilot ceiling, or None to follow the campaign setting.
    #: Defaulted, so a save written before it existed reads as "follow the setting".
    pilot_limit_override: Optional[int] = field(
        init=False, hash=False, compare=False, default=None
    )

    owned_aircraft: int = field(init=False, hash=False, compare=False, default=0)
    untasked_aircraft: int = field(init=False, hash=False, compare=False, default=0)
    pending_deliveries: int = field(init=False, hash=False, compare=False, default=0)

    #: Aircraft the squadron started the campaign with (set at turn 0).
    initial_aircraft: int = field(init=False, hash=False, compare=False, default=0)
    #: Cumulative aircraft lost in combat over the whole campaign.
    destroyed_aircraft: int = field(init=False, hash=False, compare=False, default=0)
    #: Cumulative aircraft purchased and delivered over the whole campaign.
    purchased_aircraft: int = field(init=False, hash=False, compare=False, default=0)

    use_livery_set: bool = False  # if livery-set should be used when present

    #: How well the squadron gets on with itself, worked out once a turn. It is O(n^2)
    #: in a roster of twenty or thirty, which is nothing once and wasteful on every
    #: repaint of the Air Wing list. Defaulted, so a squadron out of a save written
    #: before friendship existed reads "not worked out yet" rather than raising.
    _cohesion: Optional[float] = field(
        init=False, hash=False, compare=False, repr=False, default=None
    )

    def __setstate__(self, state: dict[str, Any]) -> None:
        if "id" not in state:
            state["id"] = uuid4()
        if "use_livery_set" not in state:
            state["use_livery_set"] = len(state.get("livery_set", [])) > 0
        if "initial_aircraft" not in state:
            # Best-effort for campaigns started before this counter existed:
            # approximate the starting force with the current owned count.
            state["initial_aircraft"] = state.get("owned_aircraft", 0)
        if "destroyed_aircraft" not in state:
            state["destroyed_aircraft"] = 0
        if "pilot_limit_override" not in state:
            # A campaign started before squadrons could carry their own ceiling keeps
            # following the campaign setting, which is what it was doing anyway.
            state["pilot_limit_override"] = None
        if "purchased_aircraft" not in state:
            state["purchased_aircraft"] = 0
        self.__dict__.update(state)

    def __str__(self) -> str:
        if self.nickname is None:
            return self.name
        return f'{self.name} "{self.nickname}"'

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Squadron):
            return False
        return self.id == other.id

    def __post_init__(self) -> None:
        self._livery_pool: list[str] = []

    @property
    def player(self) -> Player:
        return self.coalition.player

    @property
    def base_skill(self) -> Skill:
        """The lowest rung this coalition's pilots may fly at.

        Live Pilots puts every wing on the bottom rung, because a rank that starts at
        Veteran has nowhere to climb from. It does that here rather than by writing
        Cadet into the difficulty settings: those belong to the player, they are what
        the wing returns to when the feature is switched off, and overwriting them
        leaked a Cadet air force into the next campaign started from them.
        """
        if self.settings.live_pilots_enabled:
            return CADET_SKILL
        return self.difficulty_skill

    @property
    def difficulty_skill(self) -> Skill:
        """The skill the player set for this coalition on the difficulty page."""
        if self.player.is_blue:
            return Skill(self.settings.player_skill)
        return Skill(self.settings.enemy_skill)

    def pilot_skill(self, pilot: Pilot) -> Skill:
        """The effective DCS skill the pilot flies at.

        Earned, not counted: a pilot flies at the highest rung his experience has paid
        for. The coalition's setting is the floor rather than the starting point, so
        raising the difficulty lifts the whole wing at once and never demotes a veteran.
        Levelling only applies when the ``ai_pilot_levelling`` setting is enabled.
        """
        if not self.settings.ai_pilot_levelling:
            return self.base_skill
        return skill_for_experience(pilot.record.xp, self.base_skill, self.settings)

    def rank_order(self, pilot: Pilot) -> tuple[int, int]:
        """Sort key placing the senior pilot first, the most experienced first within
        a rank.

        Constant while Live Pilots is off: no rank is on display then, so ordering a
        roster by a number nobody can see would look arbitrary.
        """
        if self.pilot_rank(pilot) is None:
            return 0, 0
        try:
            rung = SKILL_LADDER.index(self.pilot_skill(pilot))
        except ValueError:
            rung = 0
        return -rung, -pilot.record.xp

    @property
    def morale_in_play(self) -> bool:
        """Morale rides on Live Pilots and can be switched off on its own.

        Switched off it does nothing at all: no drift, no leave running down, and
        nobody grounded for a figure the player cannot see.
        """
        return self.settings.live_pilots_enabled and getattr(
            self.settings, "morale_enabled", True
        )

    @property
    def cohesion(self) -> Optional[float]:
        """How well the squadron gets on with itself, on the 0-to-10 ruler.

        Every directed pair among the living, averaged: the question the pilot picker
        asks about one crew, asked about the whole roster. It is what answers "which of
        my squadrons is a crew and which is a list of names".

        None while friendship is off, because then there is nothing to say.
        """
        if not self.friendship_in_play:
            return None
        if self._cohesion is None:
            self._cohesion = friendship.synergy(self.living_pilots)
        return self._cohesion

    @property
    def friendship_in_play(self) -> bool:
        """Friendship rides on Live Pilots and can be switched off on its own.

        Switched off nothing reads the graph and nothing writes to it: no drift pass,
        no tint in the picker, and every effect falls back to what it was in Tier III.
        """
        return friendship.in_play(self.settings)

    def mission_skill(self, pilot: Pilot, flight: Optional[Flight] = None) -> Skill:
        """The rung he will actually fly at, once how he is and who he is with count.

        Kept apart from :meth:`pilot_skill` on purpose. Rank is derived from that one,
        so shifting it for morale would demote a Major to Captain on a bad week and
        promote him back on a good one. Only the mission file reads this.

        Without a flight it answers about the man alone, which is what the squadron
        list and the planner want; with one it can see the formation he is in.
        """
        skill = self.pilot_skill(pilot)
        if self.morale_in_play and pilot.has_morale:
            skill = shifted_skill(skill, pilot.morale, self.settings)
        return self._with_synergy(skill, flight)

    def _with_synergy(self, skill: Skill, flight: Optional[Flight]) -> Skill:
        """A rung for a formation that gets on.

        The flight or the package, whichever reaches Close first -- one rung, never
        two, however it was earned. It sits on top of whatever morale did, and that is
        as far as this goes: two steps is a bigger lie than the engine should be told
        about a cadet.
        """
        if flight is None or not self.friendship_in_play:
            return skill
        crews = [list(flight.roster.iter_pilots())]
        package = getattr(flight, "package", None)
        if package is not None:
            crews.append(
                [
                    member
                    for other in package.flights
                    for member in other.roster.iter_pilots()
                ]
            )
        for crew in crews:
            value = self.formation_synergy(crew)
            if value is not None and friendship.flies_a_rung_better(
                value, self.settings
            ):
                return morale_rules.bumped_skill(skill, 1)
        return skill

    def formation_synergy(self, crew: Sequence[Optional[Pilot]]) -> Optional[float]:
        """How well a formation gets on, with its leader weighted heaviest.

        The figure :meth:`mission_skill` reads to decide whether they fly a rung above
        their rank, and the one the planner is shown so it can crew for it. None while
        friendship is off, or for a formation too small to have an opinion.
        """
        members = [member for member in crew if member is not None]
        if not self.friendship_in_play or len(members) < 2:
            return None
        return friendship.synergy(members, self.leader_of(members), self.settings)

    def leader_of(self, crew: Sequence[Optional[Pilot]]) -> Optional[Pilot]:
        """The senior man in a formation, whose own relationships weigh heaviest.

        Ranked rather than seated: spreading senior pilots one to a flight is supposed
        to be worth more than stacking them in one, and that is only true if the man in
        front is the one the formation is measured through. A package reaches across
        squadrons and a pilot does not carry his own, so everyone here is read against
        this squadron's ladder -- near enough to pick a leader by.
        """
        best: Optional[Pilot] = None
        best_rung = -1
        for pilot in crew:
            if pilot is None:
                continue
            try:
                rung = SKILL_LADDER.index(self.pilot_skill(pilot))
            except ValueError:
                rung = 0
            if rung > best_rung:
                best, best_rung = pilot, rung
        return best

    def pilot_rank(self, pilot: Pilot) -> Optional[Rank]:
        """The rank the pilot holds, or None while Live Pilots is switched off.

        A rank is a renaming of the DCS skill level rather than a second ladder:
        competence is the only thing the engine can be told about, so promotion
        and skill have to be the same step.
        """
        if not self.settings.live_pilots_enabled:
            return None
        ladder = ranks_for(
            self.settings.live_pilots_rank_names,
            self.country,
            (
                (
                    self.settings.live_pilots_rank_cadet_short,
                    self.settings.live_pilots_rank_cadet_full,
                ),
                (
                    self.settings.live_pilots_rank_average_short,
                    self.settings.live_pilots_rank_average_full,
                ),
                (
                    self.settings.live_pilots_rank_good_short,
                    self.settings.live_pilots_rank_good_full,
                ),
                (
                    self.settings.live_pilots_rank_high_short,
                    self.settings.live_pilots_rank_high_full,
                ),
                (
                    self.settings.live_pilots_rank_excellent_short,
                    self.settings.live_pilots_rank_excellent_full,
                ),
            ),
        )
        return rank_for_skill(self.pilot_skill(pilot), ladder)

    def assign_to_base(self, base: ControlPoint) -> None:
        self.location = base
        logging.debug(f"Assigned {self} to {base}")

    @property
    def pilot_limits_enabled(self) -> bool:
        return self.settings.enable_squadron_pilot_limits

    def random_round_robin_livery_from_set(self) -> str:
        livery = random.choice(self.livery_set)
        self._livery_pool.append(livery)
        self.livery_set.remove(livery)
        if not self.livery_set:
            self.livery_set = self._livery_pool
            self._livery_pool = []
        return livery

    def set_auto_assignable_mission_types(
        self, mission_types: Iterable[FlightType]
    ) -> None:
        self.auto_assignable_mission_types = {
            t for t in mission_types if self.capable_of(t)
        }

    def claim_new_pilot_if_allowed(self) -> Optional[Pilot]:
        if self.pilot_limits_enabled:
            return None
        self._recruit_pilots(1)
        return self.available_pilots.pop()

    def claim_available_pilot(self, alongside: Sequence[Pilot] = ()) -> Optional[Pilot]:
        """Take a man off the list for a seat.

        ``alongside`` is who he would be flying with, and it only ever orders the men
        who already matched the player's preference about players and AI -- that still
        decides who is eligible. Greedy rather than optimal: the first seat has nobody
        to get on with, so the crew grows around whoever was at the top of the list.
        Trying to group them is what was asked for, not building the best crew that
        could be made out of the squadron.
        """
        if not self.available_pilots:
            return self.claim_new_pilot_if_allowed()

        # For opfor, so player/AI option is irrelevant.
        if self.player != Player.BLUE:
            return self._take(
                self._pick(self.available_pilots, alongside, self.available_pilots[-1])
            )

        preference = self.settings.auto_ato_behavior

        # No preference, so the first pilot is fine.
        if preference is AutoAtoBehavior.Default:
            return self._take(
                self._pick(self.available_pilots, alongside, self.available_pilots[-1])
            )

        prefer_players = preference is AutoAtoBehavior.Prefer
        matching = [p for p in self.available_pilots if p.player == prefer_players]
        if matching:
            return self._take(self._pick(matching, alongside, matching[0]))

        # No pilot was found that matched the user's preference.
        #
        # If they chose to *never* assign players and only players remain in the pool,
        # we cannot fill the slot with the available pilots.
        #
        # If they only *prefer* players and we're out of players, just return an AI
        # pilot.
        if not prefer_players:
            return self.claim_new_pilot_if_allowed()
        return self.available_pilots.pop()

    def _pick(
        self, candidates: Sequence[Pilot], alongside: Sequence[Pilot], default: Pilot
    ) -> Pilot:
        """Who takes this seat: the senior man if it is the first -- seat zero is the
        flight lead -- otherwise whoever the crew already seated gets on with best.

        ``default`` wins every tie, so crewing is unchanged with Live Pilots off.
        """
        if len(candidates) < 2:
            return default
        if not alongside:
            senior = min(candidates, key=self.rank_order)
            if self.rank_order(senior) < self.rank_order(default):
                return senior
            return default
        if not self.friendship_in_play:
            return default
        best = max(
            candidates, key=lambda pilot: friendship.group_affinity(pilot, alongside)
        )
        if friendship.group_affinity(best, alongside) <= friendship.FRIENDSHIP_START:
            return default
        return best

    def _take(self, pilot: Pilot) -> Pilot:
        """Off the list by identity, for the reason :meth:`claim_pilot` explains."""
        for index, candidate in enumerate(self.available_pilots):
            if candidate is pilot:
                del self.available_pilots[index]
                break
        return pilot

    def claim_pilot(self, pilot: Pilot) -> None:
        """Take this man off the list -- this man, not one who looks like him.

        Pilot is a dataclass, so two men with the same name and record compare equal
        and ``list.remove`` takes whichever comes first. leaves_the_pool has always
        compared by identity for that reason; these three did not, so claiming a copy
        of a pilot would strike the original off the list and leave him unassignable
        while his record still read Active and unassigned.
        """
        if not any(p is pilot for p in self.available_pilots):
            raise ValueError(
                f"Cannot assign {pilot} to {self} because they are not available"
            )
        self.available_pilots = [p for p in self.available_pilots if p is not pilot]

    def return_pilot(self, pilot: Pilot) -> None:
        if not any(p is pilot for p in self.available_pilots):
            self.available_pilots.append(pilot)

    def return_pilots(self, pilots: Sequence[Pilot]) -> None:
        # Return in reverse so that returning two pilots and then getting two more
        # results in the same ordering. This happens commonly when resetting rosters in
        # the UI, when we clear the roster because the UI is updating, then end up
        # repopulating the same size flight from the same squadron.
        for pilot in reversed(pilots):
            self.return_pilot(pilot)

    def _recruit_pilots(self, count: int) -> None:
        new_pilots = self.pilot_pool[:count]
        self.pilot_pool = self.pilot_pool[count:]
        count -= len(new_pilots)
        # Resolve the squadron's faker once per batch, not once per pilot: the
        # country/locale is fixed for a squadron's lifetime, so hundreds of
        # identical ``faker_for_country`` lookups per campaign collapse to one.
        faker = self.faker
        for _ in range(count):
            if random.randint(1, 100) > self.female_pilot_percentage:
                new_pilots.append(Pilot(faker.name_male()))
            else:
                new_pilots.append(Pilot(faker.name_female()))
        self.current_roster.extend(new_pilots)
        self.available_pilots.extend(new_pilots)

    def populate_for_turn_0(self, squadrons_start_full: bool) -> None:
        if any(p.status is not PilotStatus.Active for p in self.pilot_pool):
            raise ValueError("Squadrons can only be created with active pilots.")
        self._recruit_pilots(self.settings.squadron_pilot_limit)
        if squadrons_start_full:
            parking_type = ParkingType().from_squadron(self)
            self.owned_aircraft = min(
                self.max_size, self.location.unclaimed_parking(parking_type)
            )
        self.initial_aircraft = self.owned_aircraft

    def end_turn(self) -> None:
        # Everything below moves somebody, and the drift moves everybody: worked out
        # again the next time the Air Wing asks.
        self._cohesion = None
        if self.destination is not None:
            self.relocate_to(self.destination)
        self.tend_the_wounded()
        self.tend_morale(self.coalition.game.turn)
        self.replenish_lost_pilots()
        self.deliver_orders()

    def tend_morale(self, turn: int) -> None:
        """A turn of ordinary life: leave served, drift, and the cost of no rest.

        Everything that happens *to* a pilot in a mission is applied by the results
        processor. This is only what the passage of time does.
        """
        if not self.morale_in_play:
            return
        # Taken before anybody is moved: who is away at the same time as him must not
        # depend on where he happens to sit in the roster.
        away = [pilot for pilot in self.current_roster if pilot.on_leave]
        for pilot in list(self.current_roster):
            if not pilot.alive:
                continue

            # What he had at this point one turn ago, so the next turn can say whether
            # he is sliding. Taken before anything moves him.
            was = pilot.morale
            pilot.morale_last_turn = was

            if pilot.on_leave:
                pilot.move_morale(
                    self._leave_event(pilot, away),
                    self.pilot_skill(pilot),
                    self.settings,
                    turn,
                )
                # Served whether or not morale is his: leave the player granted
                # himself still has to run out, or he never comes back.
                pilot.serve_a_turn_of_leave(turn)
                continue

            if not pilot.has_morale:
                # The player is not worn down by the turn passing, is never overdue a
                # rest he can take whenever he likes, and does not desert.
                continue

            # Judged on the state he arrived in. The drift below lifts a man who is
            # merely low, so asking afterwards would read the wrong number.
            was_at_rock_bottom = was <= morale_rules.REFUSES_TO_FLY_AT

            # And a turn spent down there leaves something behind, on the same
            # reading of the same figure.
            hardening.harden(pilot, was, self.settings)

            pilot.turns_since_leave += 1
            if pilot.turns_since_leave > TURNS_BEFORE_LEAVE_IS_MISSED:
                # The same cost every turn from the sixth on, not a compounding one.
                pilot.move_morale(
                    morale_rules.NO_LEAVE,
                    self.pilot_skill(pilot),
                    self.settings,
                    turn,
                )
            before_drift = pilot.morale
            pilot.morale = morale_rules.clamp(pilot.morale + self._drift_for(pilot))
            pilot.note_morale_change(before_drift, "time passing", turn)

            if was_at_rock_bottom:
                pilot.turns_at_zero += 1
                # A roll, not a countdown: every turn a man is left at the bottom is a
                # turn he might not come back from, and rank is what holds him there.
                if random.random() < self._desertion_chance(pilot):
                    logging.info(
                        f"{pilot.name} has deserted {self} after "
                        f"{pilot.turns_at_zero} turns at rock bottom"
                    )
                    pilot.desert()
                    continue
            else:
                pilot.turns_at_zero = 0

            # A man in a hospital bed does not ask for leave, and how hard he has been
            # worked lately counts as much as how he is holding up.
            flown = pilot.sorties_in_last(morale_rules.RECENT_SORTIE_WINDOW, turn)
            if (
                not pilot.wounded
                and not pilot.wants_leave
                and random.random()
                < (
                    morale_rules.leave_request_chance(
                        pilot.morale,
                        getattr(self.settings, "morale_leave_request_chance", 8),
                        flown,
                    )
                )
            ):
                pilot.wants_leave = True
                pilot.leave_turns_requested = morale_rules.requested_leave_turns(
                    pilot.morale
                )

    def _leave_event(
        self, pilot: Pilot, away: Sequence[Pilot]
    ) -> morale_rules.MoraleEvent:
        """A turn of leave, and what the company of the others away with him is worth.

        Worked out again every turn, which is the whole character of it: three men who
        go together and come back on different turns each lose the bonus as the others
        return, so the last week alone is worth an ordinary week. Nobody's leave is
        lengthened or shortened by it -- only what the company does for him while it
        lasts.
        """
        event = morale_rules.ON_LEAVE
        if not self.friendship_in_play:
            return event
        others = [other for other in away if other is not pilot]
        if not others:
            return event
        return event.scaled_by(
            friendship.leave_multiplier(
                friendship.mean_towards(pilot, others), self.settings
            ),
            self.settings,
        )

    def _drift_for(self, pilot: Pilot) -> int:
        """His step back towards the middle, and what the company does to it.

        A man who is struggling comes home faster for each close friend in the
        squadron; a man who is flying high comes down faster for each one who cannot
        stand him. Only ever faster, and never past the middle: the drift has somewhere
        to be, and friendship decides how quickly he gets there rather than where it
        ends.
        """
        step = morale_rules.drift(pilot.morale, self.settings)
        if not step or not self.friendship_in_play:
            return step
        if pilot.morale < morale_rules.MORALE_START:
            company = sum(
                1
                for other in self.living_pilots
                if other is not pilot
                and friendship.is_close(friendship.feeling(pilot, other), self.settings)
            )
        else:
            company = sum(
                1
                for other in self.living_pilots
                if other is not pilot
                and friendship.is_hostile(
                    friendship.feeling(other, pilot), self.settings
                )
            )
        distance = abs(pilot.morale - morale_rules.MORALE_START)
        moved = round(step * friendship.drift_help(company, self.settings))
        return max(-distance, min(distance, moved))

    def _desertion_chance(self, pilot: Pilot) -> float:
        """How likely he is to walk away this turn.

        Rank is what held him in his seat until now. The man in the next bunk is the
        better half of the story.
        """
        chance = morale_rules.desertion_chance(self.pilot_skill(pilot))
        if not self.friendship_in_play:
            return chance
        return chance * friendship.desertion_modifier(
            friendship.mean_towards(pilot, self.living_pilots), self.settings
        )

    def spare_pilots(self, excluding: Optional[Pilot] = None) -> int:
        """Who would still be available if this man were let go.

        Not the wounded, not the ones already resting, and not the ones who have asked
        and are waiting on the same answer -- granting them all at once is the mistake
        this number is here to prevent.
        """
        return sum(
            1
            for pilot in self.current_roster
            if pilot is not excluding
            and pilot.alive
            and not pilot.wounded
            and not pilot.on_leave
            and not pilot.wants_leave
        )

    def pilots_asking_for_leave(self) -> list[Pilot]:
        """Everyone on the books waiting to be told yes or no, worst off first."""
        asking = [
            pilot
            for pilot in self.current_roster
            if pilot.wants_leave and pilot.status is PilotStatus.Active
        ]
        asking.sort(key=lambda pilot: pilot.morale)
        return asking

    def cancel_leave(self, pilot: Pilot) -> None:
        """Call a man back before his leave is up, and pay for it.

        The cost hangs on this, not on :meth:`Pilot.return_from_leave` -- a pilot whose
        leave simply ran out has had his rest and owes nothing.
        """
        if not pilot.on_leave:
            raise RuntimeError("Only pilots on leave may have it cancelled")
        # Goes through the ordinary return, which refuses when the squadron is full.
        self.return_from_leave(pilot)
        if self.morale_in_play:
            pilot.move_morale(
                morale_rules.LEAVE_CANCELLED,
                self.pilot_skill(pilot),
                self.settings,
                self.coalition.game.turn,
            )

    def unfilled_pilot_slots(self) -> int:
        """How many more men this squadron could hold, or 0 with limits off.

        The campaign setting is a ceiling, and changing it mid-campaign does nothing
        on its own -- nobody is recruited into the room it just made, and nobody is
        removed when it shrinks. This is the number the player needs to see to know
        that, and to act on it.
        """
        if not self.pilot_limits_enabled:
            return 0
        return max(0, self._number_of_unfilled_pilot_slots)

    def discharge(self, pilot: Pilot) -> None:
        """Throw a pilot out. He leaves the roster and joins the roll below it."""
        pilot.discharge()
        self.leaves_the_pool(pilot)
        logging.info(f"{pilot.name} was discharged from {self}")

    def tend_the_wounded(self) -> None:
        """One turn of every wound served; the last one puts the pilot back to work."""
        turn = self.coalition.game.turn
        for pilot in self.wounded_pilots:
            pilot.serve_a_turn_wounded(turn)
            if not pilot.wounded:
                self._note_recovery(pilot, turn)

    def _note_recovery(self, pilot: Pilot, turn: int) -> None:
        """He walked out of the hospital, and the squadron got him back.

        The mirror of the wound, weighted the same way: the men who took his being
        carried out hardest are the ones who are gladdest to see him. The flight he was
        hurt in is long gone by now -- the ATO is cleared between turns -- so this is
        the squadron's, which is who carried the loss of him in the first place.
        """
        if not self.morale_in_play:
            return
        for mate in self.living_pilots:
            if mate is pilot or not mate.has_morale:
                continue
            times = 1
            if self.friendship_in_play:
                times = friendship.grief_times(
                    1, friendship.feeling(mate, pilot), self.settings
                )
            for _ in range(times):
                mate.move_morale(
                    morale_rules.SQUADRON_RECOVERED,
                    self.pilot_skill(mate),
                    self.settings,
                    turn,
                )

    def replenish_lost_pilots(self) -> None:
        if self.pilot_limits_enabled and self.replenish_count > 0:
            self._recruit_pilots(self.replenish_count)

    def reconcile_available_pilots(self, flying: set[int]) -> list[Pilot]:
        """Put back anyone fit, unassigned and missing from the pool.

        The pool is a stored list, rebuilt from the roster only between turns, so a
        claim that goes astray anywhere leaves a man who is Active, unhurt and in
        nobody's flight yet cannot be given a seat -- his record says one thing and
        the list says another, with no way to tell which is wrong from the outside.

        The list is derivable from the roster and the ATO, so it is derived rather
        than trusted. ``flying`` is the identity of every pilot currently sitting in
        some flight; anyone else fit for duty belongs on the list.

        Returns whoever had to be put back, so the caller can say so.
        """
        on_list = {id(p) for p in self.available_pilots}
        restored = []
        for pilot in self.active_pilots:
            if id(pilot) in on_list or id(pilot) in flying:
                continue
            if self.morale_in_play and pilot.refuses_to_fly:
                continue
            self.available_pilots.append(pilot)
            restored.append(pilot)
        return restored

    def return_all_pilots_and_aircraft(self) -> None:
        # A man at rock bottom is not offered, the same way a wounded one is not. He is
        # still on the books and still counts against the squadron's establishment.
        if self.morale_in_play:
            self.available_pilots = [
                p for p in self.active_pilots if not p.refuses_to_fly
            ]
        else:
            self.available_pilots = list(self.active_pilots)
        # Aircraft already sold this turn (negative pending) must not return to the
        # taskable pool; otherwise a turn re-initialisation would let the same units
        # be sold (and flown) again, refunding their price every time.
        self.untasked_aircraft = self.owned_aircraft + min(0, self.pending_deliveries)

    def send_on_leave(self, pilot: Pilot, turns: int = 0, turn: int = -1) -> None:
        """Open-ended from the Air Wing button; for a fixed spell from a granted request."""
        pilot.send_on_leave(turns, turn)
        self.leaves_the_pool(pilot)

    def return_from_leave(self, pilot: Pilot) -> None:
        if not self.has_unfilled_pilot_slots:
            raise RuntimeError(
                f"Cannot return {pilot} from leave because {self} is full"
            )
        pilot.return_from_leave()
        self.joins_the_pool(pilot)

    def leaves_the_pool(self, pilot: Pilot) -> None:
        """He is no longer on offer for a sortie.

        The pool is only rebuilt from the roster between turns, so anything that takes a
        man off duty *during* one has to say so, or he stays on the list until the turn
        ends -- and the men still fit for it go missing from it.

        Compared by identity: Pilot is a dataclass, so two men of the same name and
        record are equal to one another and ``list.remove`` would take the wrong one.
        """
        self.available_pilots = [p for p in self.available_pilots if p is not pilot]

    def joins_the_pool(self, pilot: Pilot) -> None:
        """He is fit and unassigned, so he is on offer again."""
        if pilot.status is not PilotStatus.Active or pilot.refuses_to_fly:
            return
        if not any(p is pilot for p in self.available_pilots):
            self.available_pilots.append(pilot)

    @property
    def faker(self) -> Faker:
        # Name the squadron's pilots in their own nation's convention (the
        # squadron flies under its own DCS country, #627), falling back to a
        # faker built from the faction's locale list for unmapped /
        # multinational countries. See game/squadrons/pilotnames.py.
        return faker_for_country(self.country, self.coalition.faction.locales)

    def _pilots_with_status(self, status: PilotStatus) -> list[Pilot]:
        return [p for p in self.current_roster if p.status == status]

    def _pilots_without_status(self, status: PilotStatus) -> list[Pilot]:
        return [p for p in self.current_roster if p.status != status]

    @property
    def pilot_limit(self) -> int:
        """How many pilots this squadron may hold.

        The campaign setting is the default for every squadron; a squadron may carry
        its own figure instead. There was a setting for the limit and nowhere to set a
        squadron's own, so a wing of sixteen-man squadrons could not have one small
        training unit or one oversized front-line outfit.
        """
        if self.pilot_limit_override is not None:
            return self.pilot_limit_override
        return self.settings.squadron_pilot_limit

    @property
    def expected_pilots_next_turn(self) -> int:
        return len(self.active_pilots) + self.replenish_count

    @property
    def replenish_count(self) -> int:
        # Never negative. A squadron already over its limit recruits nobody and comes
        # back down on its own as men are lost, rather than having anyone taken off it;
        # and expected_pilots_next_turn stays honest for procurement either way.
        return max(
            0,
            min(
                self.settings.squadron_replenishment_rate,
                self._number_of_unfilled_pilot_slots,
            ),
        )

    @property
    def active_pilots(self) -> list[Pilot]:
        return self._pilots_with_status(PilotStatus.Active)

    @property
    def pilots_on_leave(self) -> list[Pilot]:
        return self._pilots_with_status(PilotStatus.OnLeave)

    @property
    def wounded_pilots(self) -> list[Pilot]:
        return self._pilots_with_status(PilotStatus.Wounded)

    @property
    def deserted_pilots(self) -> list[Pilot]:
        return self._pilots_with_status(PilotStatus.Deserted)

    @property
    def number_of_pilots_including_inactive(self) -> int:
        return len(self.current_roster)

    @property
    def living_pilots(self) -> list[Pilot]:
        return [p for p in self.current_roster if p.alive]

    @property
    def dead_pilots(self) -> list[Pilot]:
        """The ones who are not coming back, however they went."""
        return [p for p in self.current_roster if not p.alive]

    @property
    def _number_of_unfilled_pilot_slots(self) -> int:
        """A slot is free only if nobody on the books holds it.

        Not just the men fit to fly today: a wounded pilot and a pilot on leave are
        both coming back, so recruiting into their places puts the squadron over its
        own limit the turn they return. This used to count the active and the wounded
        and forget leave, which is how a squadron limited to sixteen reached
        twenty-four with twelve men resting -- and how one that merely backfilled a
        single absence sat at seventeen the day he came back.
        """
        return self.pilot_limit - len(self.living_pilots)

    @property
    def number_of_available_pilots(self) -> int:
        return len(self.available_pilots)

    @property
    def refusing_pilots(self) -> list[Pilot]:
        """The men at rock bottom, who will not take a seat however free it is."""
        if not self.morale_in_play:
            return []
        return [p for p in self.living_pilots if p.refuses_to_fly]

    @property
    def fit_for_duty(self) -> list[Pilot]:
        """Who could be given a seat if one were free.

        Not the same question as :attr:`available_pilots`, which is the untasked pool
        and so shrinks as you plan. This is what the counts the player reads mean: on
        the books, not hurt, not away, and willing. The three displays that answer it
        each subtracted their own idea of who was out, and the one that forgot the
        refusers said a squadron had seven men for four seats.
        """
        return [
            pilot
            for pilot in self.living_pilots
            if not pilot.wounded and not pilot.on_leave and not pilot.refuses_to_fly
        ]

    def can_provide_pilots(self, count: int) -> bool:
        return not self.pilot_limits_enabled or self.number_of_available_pilots >= count

    @property
    def has_available_pilots(self) -> bool:
        return not self.pilot_limits_enabled or bool(self.available_pilots)

    @property
    def has_unfilled_pilot_slots(self) -> bool:
        return not self.pilot_limits_enabled or self._number_of_unfilled_pilot_slots > 0

    def capable_of(self, task: FlightType) -> bool:
        """Returns True if the squadron is capable of performing the given task.

        A squadron may be capable of performing a task even if it will not be
        automatically assigned to it.
        """
        return self.aircraft.capable_of(task)

    def can_auto_assign(self, task: FlightType) -> bool:
        return task in self.auto_assignable_mission_types

    def can_auto_assign_mission(
        self,
        location: MissionTarget,
        task: FlightType,
        size: int,
        heli: bool,
        this_turn: bool,
        ignore_range: bool = False,
    ) -> bool:
        if (
            self.location.cptype.name in ["FOB", "FARP"]
            and not self.aircraft.helicopter
        ):
            # AI harriers can't handle FOBs/FARPs
            # AI has a hard time taking off and will not land back at FOB/FARP
            # thus, disable auto-planning
            return False
        if not self.can_auto_assign(task):
            return False
        if this_turn and not self.can_fulfill_flight(size):
            return False

        if task in [FlightType.ESCORT, FlightType.SEAD_ESCORT]:
            if heli and not self.aircraft.helicopter and not self.aircraft.lha_capable:
                return False
            if not heli and self.aircraft.helicopter:
                return False

        if heli and task == FlightType.REFUELING:
            return False

        if ignore_range:
            return True

        distance_to_target = meters(location.distance_to(self.location))
        max_plane_dist = nautical_miles(
            self.coalition.game.settings.max_mission_range_planes
        )
        max_heli_dist = nautical_miles(
            self.coalition.game.settings.max_mission_range_helicopters
        )
        if self.aircraft.helicopter:
            return distance_to_target <= max(
                self.aircraft.max_mission_range, max_heli_dist
            )
        return distance_to_target <= max(
            self.aircraft.max_mission_range, max_plane_dist
        )

    def operates_from(self, control_point: ControlPoint) -> bool:
        if not control_point.can_operate(self.aircraft):
            return False
        if control_point.is_carrier:
            return self.operating_bases.carrier
        elif control_point.is_lha:
            return self.operating_bases.lha
        else:
            return self.operating_bases.shore

    def pilot_at_index(self, index: int) -> Pilot:
        return self.current_roster[index]

    def claim_inventory(self, count: int) -> None:
        if self.untasked_aircraft < count:
            raise ValueError(
                f"Cannot remove {count} from {self.name}. Only have "
                f"{self.untasked_aircraft}."
            )
        self.untasked_aircraft -= count

    def can_fulfill_flight(self, count: int) -> bool:
        return self.can_provide_pilots(count) and self.untasked_aircraft >= count

    def refund_orders(self, count: Optional[int] = None) -> None:
        if count is None:
            count = self.pending_deliveries
        self.coalition.adjust_budget(self.aircraft.price * count)
        self.pending_deliveries -= count

    def deliver_orders(self) -> None:
        self.cancel_overflow_orders()
        self.purchased_aircraft += self.pending_deliveries
        self.owned_aircraft += self.pending_deliveries
        self.pending_deliveries = 0

    def relocate_to(self, destination: ControlPoint) -> None:
        if not destination.is_friendly(self.coalition.player):
            logging.warning(
                f"Cannot relocate {self} to {destination.name} - destination is no longer friendly. "
                f"Cancelling relocation order."
            )
            self.destination = None
            return
        self.location = destination
        if self.location == self.destination:
            self.destination = None

    def cancel_overflow_orders(self) -> None:
        from game.theater import ParkingType

        if self.pending_deliveries <= 0:
            return
        parking_type = ParkingType().from_aircraft(
            self.aircraft, self.coalition.game.settings.ground_start_ai_planes
        )
        overflow = -self.location.unclaimed_parking(parking_type)
        if overflow > 0:
            sell_count = min(overflow, self.pending_deliveries)
            logging.debug(
                f"{self.location} is overfull by {overflow} aircraft. Cancelling "
                f"orders for {sell_count} aircraft to make room."
            )
            self.refund_orders(sell_count)

    @property
    def max_fulfillable_aircraft(self) -> int:
        return max(self.number_of_available_pilots, self.untasked_aircraft)

    @property
    def untasked_crewed_aircraft(self) -> int:
        """Untasked aircraft that also have a free pilot to fly them — the real number
        launchable this turn. ``untasked_aircraft`` alone can exceed the pilots on hand;
        this caps it. Equals ``untasked_aircraft`` when pilot limits are disabled."""
        if not self.pilot_limits_enabled:
            return self.untasked_aircraft
        return min(self.untasked_aircraft, self.number_of_available_pilots)

    @property
    def expected_size_next_turn(self) -> int:
        return self.owned_aircraft + self.pending_deliveries

    def has_aircraft_capacity_for(self, n: int) -> bool:
        if not self.settings.enable_squadron_aircraft_limits:
            return True
        remaining = self.max_size - self.owned_aircraft - self.pending_deliveries
        return remaining >= n

    @property
    def arrival(self) -> ControlPoint:
        return self.location if self.destination is None else self.destination

    def plan_relocation(self, destination: ControlPoint, now: datetime) -> None:
        from game.theater import ParkingType

        if destination == self.location:
            logging.warning(
                f"Attempted to plan relocation of {self} to current location "
                f"{destination}. Ignoring."
            )
            return
        if destination == self.destination:
            logging.warning(
                f"Attempted to plan relocation of {self} to current destination "
                f"{destination}. Ignoring."
            )
            return

        parking_type = ParkingType().from_squadron(self)
        if self.expected_size_next_turn > destination.unclaimed_parking(parking_type):
            raise RuntimeError(f"Not enough parking for {self} at {destination}.")
        if not destination.can_operate(self.aircraft):
            raise RuntimeError(f"{self} cannot operate at {destination}.")
        self.destination = destination
        self.replan_ferry_flights(now)

    def cancel_relocation(self) -> None:
        from game.theater import ParkingType

        if self.destination is None:
            logging.warning(
                f"Attempted to cancel relocation of squadron with no transfer order. "
                "Ignoring."
            )
            return

        parking_type = ParkingType().from_squadron(self)
        if self.expected_size_next_turn > self.location.unclaimed_parking(parking_type):
            raise RuntimeError(f"Not enough parking for {self} at {self.location}.")
        self.destination = None
        self.cancel_ferry_flights()

    def replan_ferry_flights(self, now: datetime) -> None:
        self.cancel_ferry_flights()
        self.plan_ferry_flights(now)

    def cancel_ferry_flights(self) -> None:
        # Both lists are copied: removing a package from the one being walked makes
        # Python skip the next, so an emptied package used to leave the one behind it
        # untouched -- with its ferry flights, and the pilots they hold, still claimed.
        for package in list(self.coalition.ato.packages):
            for flight in list(package.flights):
                if flight.squadron == self and flight.flight_type is FlightType.FERRY:
                    package.remove_flight(flight)
            if not package.flights:
                self.coalition.ato.remove_package(package)

    def plan_ferry_flights(self, now: datetime) -> None:
        if self.destination is None:
            raise RuntimeError(
                f"Cannot plan ferry flights for {self} because there is no destination."
            )
        remaining = self.untasked_aircraft
        if not remaining:
            return

        package = Package(self.destination, self.flight_db)
        while remaining:
            size = min(remaining, self.aircraft.max_group_size)
            self.plan_ferry_flight(package, size)
            remaining -= size
        package.set_tot_asap(now)
        self.coalition.ato.add_package(package)

    def plan_ferry_flight(self, package: Package, size: int) -> None:
        start_type = self.location.required_aircraft_start_type
        if start_type is None:
            start_type = self.settings.default_start_type

        flight = Flight(
            package,
            self,
            size,
            FlightType.FERRY,
            start_type,
            divert=None,
        )
        package.add_flight(flight)
        flight.recreate_flight_plan()

    @classmethod
    def create_from(
        cls,
        squadron_def: SquadronDef,
        primary_task: FlightType,
        max_size: int,
        base: ControlPoint,
        coalition: Coalition,
        game: Game,
    ) -> Squadron:
        squadron_def.claimed = True
        return Squadron(
            squadron_def.name,
            squadron_def.nickname,
            squadron_def.country,
            squadron_def.role,
            squadron_def.aircraft,
            max_size,
            squadron_def.livery,
            squadron_def.livery_set,
            primary_task,
            squadron_def.auto_assignable_mission_types,
            squadron_def.radio_presets,
            squadron_def.operating_bases,
            squadron_def.female_pilot_percentage,
            squadron_def.pilot_pool,
            coalition,
            game.db.flights,
            game.settings,
            base,
        )
