"""The debriefing as data that outlives the mission it came from.

A `Debriefing` is assembled from the mission's state file and its unit map, and it holds
references to the flights, control points and theater objects of a mission that is over.
It was never stored anywhere: the window built from it was the only place that report
lived, so closing Escalation lost it, and there was nothing to reopen.

This is the same report reduced to what the window actually reads -- counts, names and
the pilot records, all of them plain -- which is small enough to ride in the save and
carries nothing belonging to the finished mission. The row building lives here rather
than in the window because it is arithmetic over that data, and because both the fresh
report and a restored one have to come out the same.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Dict,
    Optional,
    Sequence,
    TypeVar,
)

from game.debriefing import SideLossCounts
from game.squadrons.experience import PilotOutcomes, SaveCompatible
from game.theater.player import Player

if TYPE_CHECKING:
    from game.debriefing import Debriefing

T = TypeVar("T")

#: What a side that lost nothing looks like, for a report saved before a field existed.
_NOTHING_LOST = SideLossCounts(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

#: name, how many, and a note when there is something to say about the count.
LossRow = tuple[str, int, str]


@dataclass
class MissionState:
    """The one thing the window asks of the mission's state file."""

    mission_ended: bool = True


@dataclass
class Named:
    """A place, reduced to the only thing the report says about it."""

    name: str


@dataclass
class BaseCapture:
    """A base that changed hands, and who took it."""

    name: str
    captured_by_blue: bool

    @property
    def captured_by_player(self) -> Player:
        return Player.BLUE if self.captured_by_blue else Player.RED

    @property
    def control_point(self) -> Named:
        # The window reads capture.control_point.name; a live Debriefing hands it a
        # whole ControlPoint, and the name is all that was ever wanted from it.
        return Named(self.name)


@dataclass
class RequestAchieved(SaveCompatible):
    """A High Command request the mission achieved, what it asked, and what it
    pays."""

    objective: str
    #: The ticket kept, or what an instant prize gave.
    prize: str
    ticket: bool
    #: Whose request it was.
    blue: bool = True
    #: Its tier, what the objective was and what achieving it took, worded as the High
    #: Command window words them. Empty in a report saved before they were kept.
    tier: str = ""
    kind: str = ""
    taken: str = ""


def requests_achieved(
    closed: Sequence[Any],
    history: Sequence[Any],
    turn: int,
    blue: bool,
    motorpools: Collection[str] = (),
    tiers: int = 3,
) -> list[RequestAchieved]:
    """The requests among ``closed`` that were achieved, with what the history says
    each paid on ``turn``. ``motorpools`` names the objectives that are motor pools,
    whose requests ask for one vehicle; ``tiers`` is how many requests the campaign
    makes, which is how a tier is worded."""
    from game.highcommand.describe import taken_when, tier_words
    from game.highcommand.orders import Outcome

    paid = {
        entry.name: entry.line
        for entry in history
        if entry.turn == turn and entry.outcome == Outcome.ACHIEVED.value
    }
    return [
        RequestAchieved(
            done.order.objective,
            paid.get(done.order.objective, "no prize"),
            done.order.prize is not None and done.order.prize.ticket,
            blue,
            tier=tier_words(done.order.tier, tiers),
            kind=done.order.kind,
            taken=taken_when(
                done.order, done.order.objective in motorpools, 0, done.order.base
            )[0],
        )
        for done in closed
        if done.outcome is Outcome.ACHIEVED
    ]


@dataclass
class DebriefingReport:
    """Everything the debriefing window shows, and nothing else."""

    #: The turn the mission was flown in. Note the turn has already been advanced by
    #: the time the window opens -- results are processed, then the turn is passed, then
    #: the debriefing is sent -- so this is one less than the turn being planned.
    turn: int = 0
    player_country: str = ""
    enemy_country: str = ""
    state_data: MissionState = field(default_factory=MissionState)
    pilot_outcomes: PilotOutcomes = field(default_factory=PilotOutcomes)
    base_captures: list[BaseCapture] = field(default_factory=list)
    damaged_runway_names: list[str] = field(default_factory=list)
    #: Keyed by "is this the blue side", which is what survives a save unambiguously.
    losses: Dict[bool, SideLossCounts] = field(default_factory=dict)
    air: Dict[bool, list[LossRow]] = field(default_factory=dict)
    ground: Dict[bool, list[LossRow]] = field(default_factory=dict)
    #: (group, fired, remaining) for the cruise missiles, worked out while the turn
    #: boundary was fresh -- "remaining" means what sailed into the next turn.
    missile_rows: list[tuple[str, int, Optional[int]]] = field(default_factory=list)
    #: The High Command requests the mission achieved. Filled when the turn is passed,
    #: after the report was kept, because that is when they are counted.
    high_command: list[RequestAchieved] = field(default_factory=list)
    #: The live game, hung here so the window can read settings and ask who is waiting
    #: for leave. Not part of the report and never saved with it.
    game: Any = field(default=None, repr=False, compare=False)

    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        state["game"] = None
        return state

    def loss_counts(self, player: Player) -> SideLossCounts:
        return self.losses.get(player.is_blue, _NOTHING_LOST)

    def air_rows(self, player: Player) -> list[LossRow]:
        return self.air.get(player.is_blue, [])

    def ground_rows(self, player: Player) -> list[LossRow]:
        return self.ground.get(player.is_blue, [])

    @property
    def damaged_runways(self) -> list[Named]:
        # The window reads airfield.name off each of these.
        return [Named(name) for name in self.damaged_runway_names]

    @classmethod
    def from_debriefing(cls, debriefing: Debriefing, turn: int) -> DebriefingReport:
        report = cls(
            turn=turn,
            player_country=debriefing.player_country,
            enemy_country=debriefing.enemy_country,
            state_data=MissionState(bool(debriefing.state_data.mission_ended)),
            pilot_outcomes=debriefing.pilot_outcomes,
            base_captures=[
                BaseCapture(
                    capture.control_point.name, capture.captured_by_player.is_blue
                )
                for capture in debriefing.base_captures
            ],
            damaged_runway_names=[
                airfield.name for airfield in debriefing.damaged_runways
            ],
        )
        for player in (Player.BLUE, Player.RED):
            report.losses[player.is_blue] = debriefing.loss_counts(player)
            report.air[player.is_blue] = air_rows(debriefing, player)
            report.ground[player.is_blue] = ground_rows(debriefing, player)
        report.missile_rows = missile_rows(debriefing)
        return report


def air_rows(debriefing: Debriefing, player: Player) -> list[LossRow]:
    """What was lost in the air, by airframe.

    Under the crashed-do-not-count doctrine the write-offs are subtracted from the
    figure and said out loud, rather than quietly left in.
    """
    doctrine_on = bool(
        getattr(debriefing.game.settings, "ignore_non_combat_air_losses", False)
    )
    losses = (
        debriefing.air_losses.player if player.is_blue else debriefing.air_losses.enemy
    )
    not_counted: Dict[object, int] = {}
    if doctrine_on:
        for loss in losses:
            if debriefing.is_non_combat_loss(loss):
                unit_type = loss.flight.unit_type
                not_counted[unit_type] = not_counted.get(unit_type, 0) + 1
    rows: list[LossRow] = []
    for unit_type, count in debriefing.air_losses.by_type(player).items():
        nc = not_counted.get(unit_type, 0)
        # A live Debriefing keys these by AircraftType; older ones and the mod paths
        # can hand over something that only carries an id, or a bare string.
        name = (
            getattr(unit_type, "display_name", None)
            or getattr(unit_type, "id", None)
            or str(unit_type)
        )
        note = f"{nc} not counted — crashed-do-not-count" if nc else ""
        rows.append((name, count - nc, note))
    return rows


def ground_rows(debriefing: Debriefing, player: Player) -> list[LossRow]:
    """What was lost on the ground and at sea, said with where it was going."""
    rows: list[LossRow] = []

    def collect(losses: Dict[T, int], make_name: Callable[[T], str]) -> None:
        for unit_type, count in losses.items():
            try:
                name = make_name(unit_type)
            except AttributeError:
                logging.exception(f"Could not make unit name for {unit_type}")
                name = str(getattr(unit_type, "id", unit_type))
            rows.append((name, count, ""))

    collect(debriefing.front_line_losses_by_type(player), lambda u: str(u))
    collect(
        debriefing.motorpool_losses_by_type(player), lambda u: f"{u} from motorpool"
    )
    collect(debriefing.convoy_losses_by_type(player), lambda u: f"{u} from convoy")
    collect(
        debriefing.cargo_ship_losses_by_type(player), lambda u: f"{u} from cargo ship"
    )
    collect(debriefing.airlift_losses_by_type(player), lambda u: f"{u} from airlift")
    collect(debriefing.ground_object_losses_by_type(player), lambda u: str(u))
    collect(debriefing.scenery_losses_by_type(player), lambda u: str(u))
    return rows


def missile_rows(debriefing: Debriefing) -> list[tuple[str, int, Optional[int]]]:
    """Cruise missiles fired, and what is left aboard.

    Worked out now rather than on reopening: "remaining" is read off the magazines as
    they stood at the turn boundary, and a shooter that has since sailed on, been sunk
    or been rearmed would answer differently later.
    """
    from game.cruise_raids import debrief_expenditures

    try:
        return debrief_expenditures(debriefing.game, debriefing)
    except Exception:
        logging.exception("Could not read the cruise missile expenditures")
        return []
