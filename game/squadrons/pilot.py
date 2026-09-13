from __future__ import annotations

from dataclasses import dataclass, field
from enum import unique, Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from faker import Faker

from dcs.unit import Skill

from game.squadrons import hardening
from game.squadrons.morale import (
    MORALE_HISTORY_LIMIT,
    SORTIE_HISTORY_LIMIT,
    MORALE_START,
    REFUSES_TO_FLY_AT,
    MoraleEvent,
    MoraleLogEntry,
    apply as apply_morale,
)

#: What a pilot's kill log holds at most. Capped exactly as the morale log is: a
#: campaign can run long enough for a good pilot to pass a hundred, the dialog shows
#: the recent ones under a class, and a save should not carry every shot of a year.
KILL_HISTORY_LIMIT = 150


@dataclass(frozen=True)
class Kill:
    """One thing destroyed: what it was, when, and with what.

    The counts in :attr:`PilotRecord.air_kills` are the summary; this is what a row
    opens into. Kept as a list because the interesting part is the detail -- a Tor
    killed with a HARM reads differently from one killed with a bomb.
    """

    what: str
    #: "Air defence", "Armour", "Structures"... What the dialog groups ground kills
    #: by. Empty for an air kill, which is grouped by the aircraft's own name.
    kill_class: str = ""
    turn: int = 0
    weapon: str = ""
    air: bool = False


@dataclass(frozen=True)
class KilledBy:
    """Who ended it, with what, and when.

    Kept in pieces rather than as the sentence the debriefing prints, because the
    pilot dialog lays them out and a sentence would have to be taken apart again.
    """

    pilot_name: str = ""
    squadron: str = ""
    aircraft: str = ""
    weapon: str = ""
    friendly_fire: bool = False
    turn: int = 0


@dataclass
class PilotRecord:
    """Everything a campaign remembers about what one pilot did.

    Every field defaults, and :meth:`__setstate__` fills in the ones a save written
    before them does not carry. A dataclass keeps a plain default as a class
    attribute, so those read through even without the setdefault; the mutable ones
    need a factory and so genuinely need it.
    """

    missions_flown: int = field(default=0)

    #: What the pilot has earned in the air, which is what decides his rank. A plain
    #: default rather than a factory: dataclasses keep the former as a class attribute,
    #: so a pilot unpickled from a save written before this field reads 0 instead of
    #: raising.
    xp: int = field(default=0)

    #: Sorties he came home from. Not the same as flown: the difference is how often
    #: he was shot down, which is the more interesting of the two numbers.
    missions_completed: int = field(default=0)

    #: What he has shot down, by aircraft type, and what he has destroyed on the
    #: ground, by what it was. Grouped rather than listed: a campaign can run to
    #: hundreds of kills and the dialog asks for counts.
    air_kills: dict[str, int] = field(default_factory=dict)
    ground_kills: dict[str, int] = field(default_factory=dict)

    #: How many aircraft he has lost, and how many of those he walked or was carried
    #: away from. DCS reports no ejection of its own, so the first is every loss and
    #: the second is every loss he was alive after.
    aircraft_lost: int = field(default=0)
    survived_losses: int = field(default=0)

    #: Wounds taken and the turns they cost him, and the last one on its own: "one
    #: wound, three turns" and "wounded last on turn nine" are different questions.
    wounds: int = field(default=0)
    turns_in_hospital: int = field(default=0)
    last_wound_turn: int = field(default=0)
    last_wound_turns: int = field(default=0)

    #: Leave granted, and the turns of it. Open-ended leave is granted with no length
    #: at all, so the count is the honest figure and the turns are what is known.
    leaves_taken: int = field(default=0)
    leave_turns_total: int = field(default=0)

    #: Set once, when it is over.
    killed_by: Optional[KilledBy] = field(default=None)

    #: Every kill, most recent last, capped. The counts above are what is read at a
    #: glance; this is what one of them opens into.
    kills: list[Kill] = field(default_factory=list)

    def __setstate__(self, state: dict[str, Any]) -> None:
        for name, default in (
            ("xp", 0),
            ("missions_completed", 0),
            ("aircraft_lost", 0),
            ("survived_losses", 0),
            ("wounds", 0),
            ("turns_in_hospital", 0),
            ("last_wound_turn", 0),
            ("last_wound_turns", 0),
            ("leaves_taken", 0),
            ("leave_turns_total", 0),
            ("killed_by", None),
        ):
            state.setdefault(name, default)
        for name in ("air_kills", "ground_kills"):
            state.setdefault(name, {})
        state.setdefault("kills", [])
        self.__dict__.update(state)

    def note_kill(
        self,
        air: bool,
        what: str,
        kill_class: str = "",
        turn: int = 0,
        weapon: str = "",
    ) -> None:
        """One more of these: counted, and written down.

        The count is what the dialog reads at a glance and is never trimmed. The
        entry is what a row opens into, and the oldest go when there are too many:
        the last hundred and fifty is the story, and the first of four hundred is
        not.
        """
        if not what:
            return
        tally = self.air_kills if air else self.ground_kills
        tally[what] = tally.get(what, 0) + 1

        self.kills.append(Kill(what, kill_class, turn, weapon, air))
        if len(self.kills) > KILL_HISTORY_LIMIT:
            del self.kills[: len(self.kills) - KILL_HISTORY_LIMIT]

    def kills_of(self, what: str) -> list[Kill]:
        """The individual kills behind one row of the summary."""
        return [kill for kill in self.kills if kill.what == what]

    def kills_in(self, kill_class: str) -> list[Kill]:
        """The individual kills behind one ground class."""
        return [kill for kill in self.kills if kill.kill_class == kill_class]

    def ground_kills_by_class(self) -> dict[str, int]:
        """How many of each class, which is how the dialog groups the ground ones."""
        counts: dict[str, int] = {}
        for kill in self.kills:
            if kill.air or not kill.kill_class:
                continue
            counts[kill.kill_class] = counts.get(kill.kill_class, 0) + 1
        return counts

    @property
    def total_air_kills(self) -> int:
        return sum(self.air_kills.values())

    @property
    def total_ground_kills(self) -> int:
        return sum(self.ground_kills.values())


@unique
class PilotStatus(Enum):
    Active = "Active"
    OnLeave = "On leave"
    Dead = "Dead"
    #: Pulled out of the wreckage. Out of the roster until he has served his turns,
    #: which is the same unavailability as leave and needs no separate plumbing.
    Wounded = "Wounded"
    #: He has had enough and walked away. Counted with the dead rather than the living:
    #: gone is gone, and the squadron has to replace him either way.
    Deserted = "Deserted"
    #: Thrown out by the player. The value is the save format: never rename one of
    #: these, only add.
    Discharged = "Discharged"


@dataclass
class Pilot:
    name: str
    player: bool = field(default=False)
    status: PilotStatus = field(default=PilotStatus.Active)
    record: PilotRecord = field(default_factory=PilotRecord)

    #: Turns left in hospital. A plain default, so a pilot unpickled from a save
    #: written before wounds existed reads 0 from the class rather than raising.
    wounded_turns: int = field(default=0)

    #: The turn the wound was dealt in, which does not count towards serving it.
    wounded_on_turn: int = field(default=-1)

    #: How he is holding up, 0 to 100. A campaign that has done nothing to him yet has
    #: no opinion about him, which is what 50 means -- and it is what a pilot from a
    #: save written before morale existed reads from the class.
    morale: int = field(default=MORALE_START)

    #: What the bad weeks left behind, 0 upwards and never down. Earned a point or
    #: three per turn spent Shaken or worse, and read by everything that decides how
    #: hard the next one lands. A plain default, so a pilot from a save written before
    #: it reads 0 from the class.
    hardened: int = field(default=0)

    #: Turns of leave left, counted exactly like a wound.
    leave_turns: int = field(default=0)

    #: The turn leave was granted in, which does not count towards serving it.
    leave_on_turn: int = field(default=-1)

    #: Turns since he last had any. Starts at zero for everyone, including the pilots
    #: of a campaign that predates this, so nobody is punished for a rest they were
    #: never able to ask for.
    turns_since_leave: int = field(default=0)

    #: He has asked, and is waiting to be told yes or no.
    wants_leave: bool = field(default=False)

    #: Turns he has spent at rock bottom. Nothing depends on it any more -- desertion
    #: is a roll now -- but it is worth showing a player who left a man there.
    turns_at_zero: int = field(default=0)

    #: How many turns of leave he asked for. Nobody asks in the abstract: he asks for a
    #: morning, a day, a week, and the player may grant him less.
    leave_turns_requested: int = field(default=0)

    #: What his morale was a turn ago, so "he is sliding" can be said at all.
    morale_last_turn: int = field(default=MORALE_START)

    #: Everything that has moved him, most recent last. Read by the pilot dialog; the
    #: campaign never depends on it.
    morale_log: list[MoraleLogEntry] = field(default_factory=list)

    #: The turns he flew in, most recent last. Only the tail matters -- how hard he has
    #: been worked lately is what decides whether he asks for a rest.
    sorties_by_turn: list[int] = field(default_factory=list)

    #: Who he is, for the things that have to survive a save. Everything inside one
    #: pass keys on id(pilot) and should go on doing so; this exists because a
    #: friendship outlives the process.
    #:
    #: compare=False is not optional. Pilot is an eq=True dataclass with no __eq__ of
    #: its own, so a comparing field would quietly turn value-equality into
    #: identity-equality everywhere -- and Squadron.claim_pilot exists precisely
    #: because value-equality bites. repr=False because the repr is interpolated into
    #: that method's error message and is long enough already.
    id: UUID = field(init=False, default_factory=uuid4, compare=False, repr=False)

    #: What he thinks of the other pilots, by their id, 0 to 10 and starting at 5.
    #: Directional: this is his opinion of them, not theirs of him. An edge that lands
    #: back exactly on Neutral is deleted, so a man who has met nobody carries nothing.
    friendships: dict[UUID, float] = field(
        init=False, default_factory=dict, compare=False, repr=False
    )

    def __setstate__(self, state: dict[str, Any]) -> None:
        state.setdefault("hardened", 0)
        state.setdefault("wounded_turns", 0)
        state.setdefault("wounded_on_turn", -1)
        state.setdefault("morale", MORALE_START)
        state.setdefault("leave_turns", 0)
        state.setdefault("leave_on_turn", -1)
        state.setdefault("turns_since_leave", 0)
        state.setdefault("wants_leave", False)
        state.setdefault("turns_at_zero", 0)
        state.setdefault("leave_turns_requested", 0)
        state.setdefault("morale_last_turn", MORALE_START)
        state.setdefault("morale_log", [])
        state.setdefault("sorties_by_turn", [])
        state.setdefault("friendships", {})
        if "id" not in state:
            # A plain if rather than setdefault: a default_factory field has no class
            # attribute to fall back on, and setdefault would build a UUID on every
            # unpickle only to throw it away.
            state["id"] = uuid4()
        self.__dict__.update(state)

    @property
    def alive(self) -> bool:
        return self.status not in (
            PilotStatus.Dead,
            PilotStatus.Deserted,
            PilotStatus.Discharged,
        )

    @property
    def deserted(self) -> bool:
        return self.status is PilotStatus.Deserted

    @property
    def has_morale(self) -> bool:
        """Whether the morale rules are about this man at all.

        They are not about the player. He decides for himself whether he is up to a
        sortie, so a figure moved behind his back can only get in the way: it cannot
        ground him, hand him a week off or make him walk away, and the debriefing
        telling him how he feels about his own turn reads as a joke.
        """
        return not self.player

    @property
    def refuses_to_fly(self) -> bool:
        """Rock bottom. He is not offered for a sortie, the way a wounded man is not."""
        return self.has_morale and self.morale <= REFUSES_TO_FLY_AT

    @property
    def on_leave(self) -> bool:
        return self.status is PilotStatus.OnLeave

    @property
    def wounded(self) -> bool:
        return self.status is PilotStatus.Wounded

    def note_sortie(self, turn: int) -> None:
        """He flew this turn. Only the recent tail is kept."""
        self.sorties_by_turn.append(turn)
        if len(self.sorties_by_turn) > SORTIE_HISTORY_LIMIT:
            del self.sorties_by_turn[:-SORTIE_HISTORY_LIMIT]

    def sorties_in_last(self, turns: int, current_turn: int) -> int:
        """How many of the last ``turns`` turns he flew in.

        Counted by turn rather than by sortie: two flights in one turn is one hard day,
        not two.
        """
        floor = current_turn - turns
        return len({t for t in self.sorties_by_turn if t > floor})

    def move_morale(
        self,
        event: MoraleEvent,
        skill: Skill,
        settings: Any = None,
        turn: int = -1,
    ) -> int:
        """Apply one event to him and remember it. Returns how far he moved.

        Every morale change goes through here so that nothing can move a pilot without
        it being written down -- the log is what the pilot dialog reads back.
        """
        if not self.has_morale:
            return 0
        before = self.morale
        self.morale = apply_morale(
            before,
            event,
            skill,
            settings,
            relief=hardening.morale_relief(self.hardened, settings),
        )
        return self.note_morale_change(before, event.reason, turn)

    def note_morale_change(self, before: int, reason: str, turn: int = -1) -> int:
        """Write down a change already made to :attr:`morale`."""
        if not self.has_morale:
            self.morale = before
            return 0
        moved = self.morale - before
        if not moved:
            return 0
        self.morale_log.append(
            MoraleLogEntry(
                turn=turn, amount=moved, reason=reason, morale_after=self.morale
            )
        )
        if len(self.morale_log) > MORALE_HISTORY_LIMIT:
            del self.morale_log[:-MORALE_HISTORY_LIMIT]
        return moved

    def send_on_leave(self, turns: int = 0, turn: int = -1) -> None:
        """Grant leave, for ``turns`` of them or open-ended when that is zero.

        Open-ended is how leave has always worked and how the Air Wing button still
        grants it: he stays out until the player fetches him. A granted request carries
        a length, and then it runs down on its own like a wound.
        """
        if self.status is not PilotStatus.Active:
            raise RuntimeError("Only active pilots may be sent on leave")
        self.status = PilotStatus.OnLeave
        self.leave_turns = turns
        self.leave_on_turn = turn
        self.record.leaves_taken += 1
        self.record.leave_turns_total += turns
        self.wants_leave = False
        self.leave_turns_requested = 0

    def serve_a_turn_of_leave(self, turn: int) -> None:
        """One turn of leave used up. Open-ended leave never runs out on its own."""
        if not self.leave_turns or turn == self.leave_on_turn:
            return
        self.leave_turns -= 1
        if self.leave_turns <= 0:
            self.return_from_leave()

    def return_from_leave(self) -> None:
        if self.status is not PilotStatus.OnLeave:
            raise RuntimeError("Only pilots on leave may be returned from leave")
        self.status = PilotStatus.Active
        self.leave_turns = 0
        self.leave_on_turn = -1
        self.turns_since_leave = 0

    def wound(self, turns: int, turn: int) -> None:
        """He was going to die. Instead he is out for the next ``turns`` of them."""
        self.status = PilotStatus.Wounded
        self.wounded_turns = turns
        self.wounded_on_turn = turn
        # He is already off the roster, in a bed. Asking for leave on top of it is
        # nonsense, and any request he had made is overtaken by events.
        self.wants_leave = False
        self.leave_turns_requested = 0

    def serve_a_turn_wounded(self, turn: int) -> None:
        """One turn of the wound served. The last one puts him back on the roster.

        Not the turn he was hurt in. Wounds are dealt while a turn is being closed and
        the squadron serves them at that same close, so counting it would have him back
        a turn early -- the debriefing said four turns and the Air Wing showed three.
        """
        if turn == self.wounded_on_turn:
            return
        self.wounded_turns -= 1
        if self.wounded_turns <= 0:
            self.wounded_turns = 0
            self.wounded_on_turn = -1
            self.status = PilotStatus.Active

    def kill(self) -> None:
        self.status = PilotStatus.Dead
        self.wounded_turns = 0
        self.wounded_on_turn = -1

    def discharge(self) -> None:
        """Thrown out. He keeps his place in the roll below, and nothing else."""
        self.status = PilotStatus.Discharged
        self.wants_leave = False
        self.leave_turns = 0
        self.leave_turns_requested = 0

    def desert(self) -> None:
        """He has had enough."""
        self.status = PilotStatus.Deserted
        self.wounded_turns = 0
        self.wounded_on_turn = -1
        self.leave_turns = 0
        self.wants_leave = False

    @classmethod
    def random(cls, faker: Faker) -> Pilot:
        return Pilot(faker.name())
