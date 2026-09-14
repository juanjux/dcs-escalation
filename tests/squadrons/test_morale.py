"""How a pilot holds up, and what it is worth.

Morale is a number nobody can see deciding what a sortie pays, how steady a flight is
under fire and whether a man keeps turning up. These pin the arithmetic so it can be
tuned later without anyone having to rediscover what it was supposed to do.
"""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.task import OptReactOnThreat
from dcs.unit import Skill

from game.dcs.skills import CADET_SKILL, SKILL_LADDER
from game.settings import Settings
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot, PilotStatus

# --- the number -------------------------------------------------------------


def test_a_pilot_starts_with_nobody_having_an_opinion_about_him() -> None:
    assert Pilot("New").morale == morale_rules.MORALE_START == 50


def test_a_pilot_from_an_older_save_starts_the_same_way() -> None:
    """A campaign in progress must not punish pilots for a rest they could not ask for."""
    pilot = Pilot.__new__(Pilot)
    pilot.__setstate__({"name": "Veteran", "status": PilotStatus.Active})
    assert pilot.morale == 50
    assert pilot.turns_since_leave == 0
    assert pilot.wants_leave is False
    assert pilot.leave_turns == 0


@pytest.mark.parametrize(
    "morale,step", [(0, 5), (1, 5), (20, 5), (50, 0), (80, -5), (100, -5)]
)
def test_he_settles_back_towards_the_middle_from_either_side(
    morale: int, step: int
) -> None:
    assert morale_rules.drift(morale) == step


@pytest.mark.parametrize("morale", [46, 48, 52, 54])
def test_settling_never_overshoots_the_middle(morale: int) -> None:
    """Or a man two points off it would spend the war swinging past it."""
    assert morale + morale_rules.drift(morale) == morale_rules.MORALE_START


def test_even_the_bottom_settles_back() -> None:
    """He climbs out like anyone else; a hard turn is what puts him back."""
    assert morale_rules.drift(morale_rules.MORALE_MIN) == morale_rules.DRIFT_PER_TURN


def test_rank_softens_the_knocks_and_not_the_good_news() -> None:
    """A squadron leader has seen it before. He is not too senior to enjoy a promotion."""
    cadet = morale_rules.apply(50, morale_rules.LOST_AIRCRAFT, CADET_SKILL)
    veteran = morale_rules.apply(50, morale_rules.LOST_AIRCRAFT, Skill.Excellent)
    assert cadet < veteran < 50

    assert morale_rules.apply(50, morale_rules.PROMOTED, CADET_SKILL) == (
        morale_rules.apply(50, morale_rules.PROMOTED, Skill.Excellent)
    )


def test_a_knock_always_costs_something() -> None:
    """However senior he is, being shot down is not free."""
    assert morale_rules.apply(50, morale_rules.NO_LEAVE, Skill.Excellent) < 50


@pytest.mark.parametrize("morale", [-40, -30, 0, 50, 100, 160])
def test_it_never_leaves_its_range(morale: int) -> None:
    """Against the constants, not against 0: the floor moved below zero on purpose."""
    assert (
        morale_rules.MORALE_MIN <= morale_rules.clamp(morale) <= morale_rules.MORALE_MAX
    )


def test_rock_bottom_is_below_zero() -> None:
    """A floor of zero let one quiet turn of drift lift a man straight out of Broken."""
    assert morale_rules.MORALE_MIN < 0
    assert morale_rules.morale_state(morale_rules.MORALE_MIN).name == "Broken"


def test_being_broken_outlasts_a_single_quiet_turn() -> None:
    """The whole point of the negative range: he has to earn his way back up."""
    morale = morale_rules.MORALE_MIN
    turns = 0
    while morale_rules.morale_state(morale).name == "Broken":
        morale = morale_rules.clamp(morale + morale_rules.drift(morale))
        turns += 1
        assert turns < 50, "he never climbs out"
    assert turns > 1, "one turn of drift was enough, which is the bug"


def test_the_campaign_sets_how_fast_he_settles() -> None:
    settings = Settings()
    settings.morale_drift_per_turn = 1
    assert morale_rules.drift(0, settings) == 1
    settings.morale_drift_per_turn = 20
    assert morale_rules.drift(0, settings) == 20


def test_a_drift_of_zero_makes_a_bad_turn_stick() -> None:
    settings = Settings()
    settings.morale_drift_per_turn = 0
    for morale in (morale_rules.MORALE_MIN, 0, 20, 80, 100):
        assert morale_rules.drift(morale, settings) == 0


# --- what a sortie is worth -------------------------------------------------


@pytest.mark.parametrize(
    "morale,multiplier",
    [
        (0, 0.5),
        (9, 0.5),
        (10, 0.8),
        (39, 0.8),
        (40, 1.0),
        (59, 1.0),
        (60, 1.2),
        (80, 1.2),
        (81, 1.5),
        (100, 1.5),
    ],
)
def test_the_bands_are_where_the_notes_put_them(morale: int, multiplier: float) -> None:
    assert morale_rules.xp_multiplier(morale) == pytest.approx(multiplier)


def test_flying_with_your_betters_is_worth_something() -> None:
    """The worked example: a cadet, an average, a high and an excellent in one flight."""
    best = Skill.Excellent
    assert morale_rules.learning_bonus(CADET_SKILL, best) == pytest.approx(0.4)
    assert morale_rules.learning_bonus(Skill.Average, best) == pytest.approx(0.3)
    assert morale_rules.learning_bonus(Skill.High, best) == pytest.approx(0.1)
    assert morale_rules.learning_bonus(Skill.Excellent, best) == pytest.approx(0.0)


def test_nobody_learns_from_somebody_worse_than_them() -> None:
    assert morale_rules.learning_bonus(Skill.Excellent, CADET_SKILL) == 0.0


# --- what the player is told ------------------------------------------------


@pytest.mark.parametrize(
    "morale,name",
    [
        (100, "Triumphant"),
        (85, "Triumphant"),
        (84, "Confident"),
        (60, "Confident"),
        (59, "Normal"),
        (40, "Normal"),
        (39, "Shaken"),
        (15, "Shaken"),
        (14, "Shattered"),
        (1, "Shattered"),
        (0, "Broken"),
    ],
)
def test_the_player_is_told_a_word_and_never_a_number(morale: int, name: str) -> None:
    assert morale_rules.morale_state(morale).name == name


def test_the_warning_the_word_carries() -> None:
    """Shaken is worth an eye; below it the player has to do something."""
    assert morale_rules.morale_state(50).severity == 0
    assert morale_rules.morale_state(20).severity == 1
    assert morale_rules.morale_state(5).severity == 2
    assert morale_rules.morale_state(0).severity == 2


def test_every_point_has_a_word() -> None:
    for morale in range(morale_rules.MORALE_MIN, morale_rules.MORALE_MAX + 1):
        assert morale_rules.morale_state(morale).name


def test_a_campaign_can_move_the_bands() -> None:
    """The words are the game's; where each one starts is the campaign's."""
    settings = Settings()
    settings.morale_state_shaken = 30
    settings.morale_state_normal = 55

    assert morale_rules.morale_state(29, settings).name == "Shattered"
    assert morale_rules.morale_state(30, settings).name == "Shaken"
    assert morale_rules.morale_state(54, settings).name == "Shaken"
    assert morale_rules.morale_state(55, settings).name == "Normal"
    # Nothing was said about the others, so they stand where they were.
    assert morale_rules.morale_state(60, settings).name == "Confident"


def test_the_bottom_band_stays_at_the_bottom() -> None:
    """Broken is the floor of the scale and has no setting of its own."""
    assert [s.key for s in morale_rules.MORALE_STATES][-1] is None
    assert morale_rules.MORALE_STATES[-1].floor == morale_rules.MORALE_MIN


def test_flying_a_rung_better_or_worse_is_the_band_and_not_a_number() -> None:
    """Triumphant flies above his rank; Shattered, and worse, below it."""
    assert morale_rules.skill_shift(85) == 1, "the bottom of Triumphant counts"
    assert morale_rules.skill_shift(84) == 0
    assert morale_rules.skill_shift(15) == 0, "Shaken flies at his rank"
    assert morale_rules.skill_shift(14) == -1, "Shattered"
    assert morale_rules.skill_shift(0) == -1, "and Broken is no steadier"


def test_moving_the_bands_moves_who_flies_better() -> None:
    settings = Settings()
    settings.morale_state_triumphant = 70
    settings.morale_state_shaken = 30

    assert morale_rules.skill_shift(70, settings) == 1
    assert morale_rules.skill_shift(69, settings) == 0
    assert morale_rules.skill_shift(30, settings) == 0
    assert morale_rules.skill_shift(29, settings) == -1


def test_a_movement_is_reported_when_the_word_changes() -> None:
    settings = Settings()
    settings.morale_state_normal = 55

    assert morale_rules.worth_reporting(54, 55, settings), "Shaken -> Normal"
    assert not morale_rules.worth_reporting(39, 45, settings), "both Shaken now"
    assert morale_rules.worth_reporting(39, 45), "though it would be under the defaults"


# --- how he flies -----------------------------------------------------------


def _squadron(settings: Settings) -> Any:
    from game.squadrons.squadron import Squadron

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.coalition = SimpleNamespace(
        player=SimpleNamespace(is_blue=True), game=SimpleNamespace(turn=6)
    )
    squadron.country = None
    squadron.name = "Zero Company"
    squadron.nickname = None
    squadron.available_pilots = []
    return squadron


def _live_settings() -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value
    return settings


def test_morale_moves_what_he_flies_at_and_not_what_he_has_earned() -> None:
    """Or a bad week would demote a Major, and a good one would promote him back."""
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega")
    pilot.record.xp = 2000  # Good, on his own merits

    rank_at_50 = squadron.pilot_rank(pilot).abbreviation
    assert squadron.mission_skill(pilot) is Skill.Good

    pilot.morale = 95
    assert squadron.mission_skill(pilot) is Skill.High
    assert squadron.pilot_rank(pilot).abbreviation == rank_at_50

    pilot.morale = 5
    assert squadron.mission_skill(pilot) is Skill.Average
    assert squadron.pilot_rank(pilot).abbreviation == rank_at_50


def test_the_ladder_is_not_climbed_past_its_ends() -> None:
    assert morale_rules.shifted_skill(Skill.Excellent, 99) is Skill.Excellent
    assert morale_rules.shifted_skill(CADET_SKILL, 1) is CADET_SKILL


@pytest.mark.parametrize(
    "morale,reaction",
    [
        (50, OptReactOnThreat.Values.EvadeFire),
        (20, OptReactOnThreat.Values.EvadeFire),
        (19, OptReactOnThreat.Values.ByPassAndEscape),
        (10, OptReactOnThreat.Values.ByPassAndEscape),
        (9, OptReactOnThreat.Values.AllowAbortMission),
    ],
)
def test_how_much_the_flight_will_put_up_with(
    morale: int, reaction: OptReactOnThreat.Values
) -> None:
    assert morale_rules.threat_reaction(morale) is reaction


def test_a_hollow_man_is_slower_to_mend_and_a_cheerful_one_quicker() -> None:
    assert morale_rules.recovery_turns(3, morale=5) == 4
    assert morale_rules.recovery_turns(3, morale=50) == 3
    assert morale_rules.recovery_turns(3, morale=95) == 2
    assert morale_rules.recovery_turns(1, morale=95) == 1  # never to nothing


def test_the_steady_man_gets_out_of_the_aircraft() -> None:
    assert morale_rules.survival_modifier(100) > 0
    assert morale_rules.survival_modifier(50) == 0
    assert morale_rules.survival_modifier(0) < 0


# --- leave ------------------------------------------------------------------


def test_leave_is_counted_like_a_wound() -> None:
    pilot = Pilot("Vega")
    pilot.send_on_leave(2, turn=5)
    assert pilot.on_leave

    # Compared as tuples so mypy does not pin the property and call the last one dead.
    pilot.serve_a_turn_of_leave(5)  # the turn it was granted in does not count
    assert (pilot.leave_turns, pilot.on_leave) == (2, True)

    pilot.serve_a_turn_of_leave(6)
    assert (pilot.leave_turns, pilot.on_leave) == (1, True)

    pilot.serve_a_turn_of_leave(7)
    assert (pilot.leave_turns, pilot.on_leave) == (0, False)
    assert pilot.turns_since_leave == 0


def test_open_ended_leave_still_waits_for_the_player() -> None:
    """The Air Wing button grants no particular length, and that has to keep working."""
    pilot = Pilot("Vega")
    pilot.send_on_leave()
    for turn in range(20):
        pilot.serve_a_turn_of_leave(turn)
    assert pilot.on_leave


def test_a_worn_out_pilot_asks_more_often_than_a_contented_one() -> None:
    low = morale_rules.leave_request_chance(5, base_percent=8)
    middling = morale_rules.leave_request_chance(50, base_percent=8)
    high = morale_rules.leave_request_chance(95, base_percent=8)
    assert low > middling > high > 0, "even a happy man wants a week off sometimes"


# --- what the squadron feels ------------------------------------------------


def test_a_wound_is_felt_by_how_long_it_keeps_him() -> None:
    """Every turn the medics keep him, with no ceiling: four turns out is four."""
    assert morale_rules.wound_is_felt_for(1) == 1
    assert morale_rules.wound_is_felt_for(3) == 3
    assert morale_rules.wound_is_felt_for(4) == 4
    assert morale_rules.wound_is_felt_for(9) == 9


def test_a_short_wound_weighs_less_than_a_grave() -> None:
    """A long enough one can outweigh it, which is what a long wound is for."""
    wound = abs(morale_rules.SQUADRON_WOUND.default)
    assert wound * morale_rules.wound_is_felt_for(4) < abs(
        morale_rules.SQUADRON_DEATH.default
    )


def test_the_flight_takes_it_harder_than_the_squadron() -> None:
    """The squadron hears about it. The flight watched it happen."""
    assert abs(morale_rules.FLIGHT_DEATH.default) > 0
    assert abs(morale_rules.FLIGHT_WOUND.default) > 0
    assert abs(morale_rules.FLIGHT_DEATH.default) > abs(
        morale_rules.FLIGHT_WOUND.default
    )


# --- how hard he has been worked --------------------------------------------


def test_the_man_who_flies_every_turn_asks_soonest() -> None:
    """Five of five wants a rest more than two of five, which wants one more than none."""
    chances = [morale_rules.leave_request_chance(50, 8, flown) for flown in range(6)]
    assert chances == sorted(chances)
    assert chances[0] < chances[2] < chances[5]
    assert chances[0] > 0, "even a man who has not flown asks now and then"


def test_two_flights_in_one_turn_are_one_hard_day() -> None:
    pilot = Pilot("Vega")
    pilot.note_sortie(7)
    pilot.note_sortie(7)
    pilot.note_sortie(8)
    assert pilot.sorties_in_last(5, current_turn=9) == 2


def test_the_flying_he_did_last_year_does_not_count() -> None:
    pilot = Pilot("Vega")
    for turn in range(1, 4):
        pilot.note_sortie(turn)
    assert pilot.sorties_in_last(5, current_turn=20) == 0


def test_a_man_in_a_hospital_bed_does_not_ask_for_leave() -> None:
    settings = _live_settings()
    settings.morale_leave_request_chance = 100  # he would ask every turn if he could
    squadron = _squadron(settings)
    pilot = Pilot("Vega")
    pilot.wants_leave = True
    pilot.leave_turns_requested = 3
    squadron.current_roster = [pilot]

    pilot.wound(3, turn=1)
    assert not pilot.wants_leave, "being carried out overtakes the request"

    squadron.tend_morale(2)
    assert not pilot.wants_leave


# --- the player is not in this ----------------------------------------------


def test_nothing_moves_the_player() -> None:
    """He was told in the debriefing how he felt about his own turn. He is not."""
    pilot = Pilot("Vega", player=True)
    assert not pilot.has_morale

    moved = pilot.move_morale(morale_rules.PROMOTED, Skill.Good, _live_settings(), 4)

    assert moved == 0
    assert pilot.morale == morale_rules.MORALE_START
    assert pilot.morale_log == [], "and nothing is written down about it"


def test_a_change_made_behind_the_choke_point_is_put_back() -> None:
    """The turn's drift assigns before it reports, so reporting has to undo it."""
    pilot = Pilot("Vega", player=True)
    before = pilot.morale
    pilot.morale = 90

    assert pilot.note_morale_change(before, "time passing", 4) == 0
    assert pilot.morale == before


def test_the_turn_passing_does_nothing_to_him() -> None:
    settings = _live_settings()
    settings.morale_leave_request_chance = 100  # anyone else would ask every turn
    squadron = _squadron(settings)
    pilot = Pilot("Vega", player=True)
    pilot.morale = 20
    squadron.current_roster = [pilot]

    for turn in range(1, 12):
        squadron.tend_morale(turn)

    assert pilot.morale == 20, "no drift"
    assert pilot.turns_since_leave == 0, "and never overdue a rest"
    assert not pilot.wants_leave
    assert pilot.status is PilotStatus.Active, "nor deserting"


def test_but_leave_he_granted_himself_still_runs_out() -> None:
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega", player=True)
    squadron.current_roster = [pilot]
    squadron.available_pilots = [pilot]

    squadron.send_on_leave(pilot, 2, turn=1)
    squadron.tend_morale(2)
    squadron.tend_morale(3)

    assert pilot.status is PilotStatus.Active


def test_he_is_never_refused_by_his_own_state_of_mind() -> None:
    pilot = Pilot("Vega", player=True)
    pilot.morale = morale_rules.MORALE_MIN

    assert not pilot.refuses_to_fly


def test_he_flies_at_the_rank_he_holds() -> None:
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega", player=True)
    pilot.record.xp = 2000

    pilot.morale = 95
    assert squadron.mission_skill(pilot) is squadron.pilot_skill(pilot)
    pilot.morale = 5
    assert squadron.mission_skill(pilot) is squadron.pilot_skill(pilot)


# --- who is on offer --------------------------------------------------------


def test_a_man_sent_on_leave_stops_being_offered_at_once() -> None:
    """The pool is only rebuilt between turns, so taking him off duty has to say so."""
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]
    squadron.available_pilots = [pilot]

    squadron.send_on_leave(pilot, 2, turn=5)

    assert squadron.available_pilots == []


def test_and_he_is_offered_again_the_moment_he_is_back() -> None:
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]
    squadron.available_pilots = [pilot]
    squadron.send_on_leave(pilot, 2, turn=5)

    squadron.return_from_leave(pilot)

    assert [p.name for p in squadron.available_pilots] == ["Vega"]


def test_a_discharged_pilot_is_not_offered() -> None:
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]
    squadron.available_pilots = [pilot]

    squadron.discharge(pilot)

    assert squadron.available_pilots == []


def test_nobody_is_offered_twice() -> None:
    squadron = _squadron(_live_settings())
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]
    squadron.available_pilots = [pilot]

    squadron.joins_the_pool(pilot)

    assert len(squadron.available_pilots) == 1


# --- the end of a pilot -----------------------------------------------------


def test_at_the_bottom_he_will_not_fly() -> None:
    pilot = Pilot("Vega")
    pilot.morale = 0
    assert pilot.refuses_to_fly
    pilot.morale = 1
    assert not pilot.refuses_to_fly


def test_rank_is_what_keeps_a_man_in_his_seat() -> None:
    """Desertion is a roll each turn at the bottom, and the veteran is the last to go."""
    chances = [morale_rules.desertion_chance(s) for s in SKILL_LADDER]
    assert chances == sorted(chances, reverse=True)
    assert all(0 < c < 0.5 for c in chances)


def test_left_at_the_bottom_he_eventually_walks_away() -> None:
    settings = _live_settings()
    settings.morale_leave_request_chance = 0
    squadron = _squadron(settings)
    pilot = Pilot("Vega")
    pilot.morale = 0
    squadron.current_roster = [pilot]

    random.seed(4)  # a run in which the roll comes up
    for turn in range(200):
        # A hard war: something puts him back on the floor every turn, which is the
        # only way anybody stays there now that the drift lifts him.
        pilot.morale = 0
        squadron.tend_morale(turn)
        if pilot.deserted:
            break

    assert pilot.deserted
    assert not pilot.alive, "gone is gone; the squadron has to replace him"
    assert pilot.turns_at_zero > 1, "he did not go on the first turn every time"


def test_a_man_who_is_not_at_the_bottom_never_deserts() -> None:
    settings = _live_settings()
    settings.morale_leave_request_chance = 0
    squadron = _squadron(settings)
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]

    random.seed(1)
    for turn in range(50):
        pilot.morale = 50  # held there against the no-leave penalty
        squadron.tend_morale(turn)

    assert not pilot.deserted


def test_he_asks_for_a_number_of_turns_and_the_worse_he_is_the_longer() -> None:
    """Nobody asks for leave in the abstract: he asks for a morning, a day, a week."""
    steady = morale_rules.requested_leave_turns(50, roll=0.0)
    shaken = morale_rules.requested_leave_turns(20, roll=0.0)
    broken = morale_rules.requested_leave_turns(0, roll=0.0)
    assert steady < shaken < broken
    assert all(
        1 <= morale_rules.requested_leave_turns(m) <= morale_rules.MAX_LEAVE_TURNS
        for m in range(0, 101)
    )


def test_what_moved_him_is_written_down() -> None:
    """The pilot dialog reads this back; nothing in the campaign depends on it."""
    pilot = Pilot("Vega")
    pilot.move_morale(morale_rules.AIR_KILL, CADET_SKILL, turn=3)
    pilot.move_morale(morale_rules.LOST_AIRCRAFT, CADET_SKILL, turn=4)

    assert [e.reason for e in pilot.morale_log] == [
        "shot one down",
        "lost his aircraft",
    ]
    assert [e.turn for e in pilot.morale_log] == [3, 4]
    assert pilot.morale_log[0].amount > 0 and pilot.morale_log[1].amount < 0
    assert pilot.morale_log[-1].morale_after == pilot.morale


def test_a_move_that_changes_nothing_is_not_worth_writing_down() -> None:
    pilot = Pilot("Vega")
    pilot.morale = morale_rules.MORALE_MAX
    pilot.move_morale(morale_rules.AIR_KILL, CADET_SKILL, turn=1)
    assert pilot.morale_log == []


def test_the_log_does_not_grow_without_end() -> None:
    """It rides in every save, so a long campaign must not fill one with a man's week."""
    pilot = Pilot("Vega")
    for turn in range(morale_rules.MORALE_HISTORY_LIMIT * 3):
        pilot.morale = 50
        pilot.move_morale(morale_rules.LOST_AIRCRAFT, CADET_SKILL, turn=turn)
    assert len(pilot.morale_log) == morale_rules.MORALE_HISTORY_LIMIT
    assert pilot.morale_log[-1].turn == morale_rules.MORALE_HISTORY_LIMIT * 3 - 1


def test_going_without_leave_costs_the_same_every_turn() -> None:
    """Counted in what the penalty costs, not in where he ends up.

    The settling drift pulls the other way every turn and is worth more than one of
    these, so measuring his morale would be measuring the two rules against each other
    rather than this one.
    """
    settings = _live_settings()
    settings.morale_leave_request_chance = 0  # keep the dice out of it
    squadron = _squadron(settings)
    pilot = Pilot("Vega")
    squadron.current_roster = [pilot]

    def knocks_this_turn(turn: int) -> int:
        before = len(pilot.morale_log)
        squadron.tend_morale(turn)
        return sum(
            1
            for entry in pilot.morale_log[before:]
            if entry.reason == morale_rules.NO_LEAVE.reason
        )

    for turn in range(morale_rules.TURNS_BEFORE_LEAVE_IS_MISSED):
        assert knocks_this_turn(turn) == 0, "the first turns are free"

    first_overdue = knocks_this_turn(99)
    second_overdue = knocks_this_turn(100)

    assert first_overdue == 1
    assert second_overdue == 1, "the same every turn, not compounding"


# --- what earns a line in the debriefing ------------------------------------


def test_a_move_that_changes_his_state_is_reported() -> None:
    assert morale_rules.worth_reporting(50, 60), "Normal -> Confident"
    assert morale_rules.worth_reporting(59, 39), "Normal -> Shaken"
    assert morale_rules.worth_reporting(40, 39), "one point, but he is Shaken now"


def test_a_move_that_leaves_him_where_he_was_is_not() -> None:
    """The row has nothing to show: it names the state at each end.

    Flying the mission moves every man who came home, which is why the section used
    to be twenty rows of "Normal -> Normal".
    """
    assert not morale_rules.worth_reporting(45, 55)
    assert not morale_rules.worth_reporting(59, 41), "18 points, still Normal"
    assert not morale_rules.worth_reporting(50, 50)
