"""What a squadron does differently when its pilots get on.

The formation flies a rung better, the man in the next bunk is a reason to stay, a bad
week is shorter in company and a week off is worth more taken with the others. Each of
these is a number nobody sees, so each one is pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.unit import Skill

from game.dcs.skills import SKILL_LADDER
from game.settings import Settings
from game.squadrons import friendship
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot, PilotStatus


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
    squadron.current_roster = []
    return squadron


def _settings(**values: Any) -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value
    for name, value in values.items():
        setattr(settings, name, value)
    return settings


def _flight(*pilots: Pilot, package: Any = None) -> Any:
    return SimpleNamespace(
        roster=SimpleNamespace(iter_pilots=lambda: iter(pilots)), package=package
    )


def _close(*pilots: Pilot) -> None:
    """Everybody Inseparable with everybody, in both directions."""
    for pilot in pilots:
        for other in pilots:
            if other is not pilot:
                friendship.move(pilot, other, 5.0)


def _rung(skill: Skill) -> int:
    return SKILL_LADDER.index(skill)


# --- synergy ---------------------------------------------------------------------


def test_a_flight_that_gets_on_flies_a_rung_better() -> None:
    squadron = _squadron(_settings())
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    for pilot in (lead, wingman):
        pilot.record.xp = 2000
    flight = _flight(lead, wingman)

    assert squadron.mission_skill(lead) is Skill.Good  # on his own merits
    _close(lead, wingman)
    assert _rung(squadron.mission_skill(lead, flight)) == _rung(Skill.Good) + 1


def test_a_formation_of_strangers_flies_at_the_rank_it_holds() -> None:
    squadron = _squadron(_settings())
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    for pilot in (lead, wingman):
        pilot.record.xp = 2000
    assert squadron.mission_skill(lead, _flight(lead, wingman)) is Skill.Good


def test_the_rung_is_earned_once_however_it_was_earned() -> None:
    """Flight and package both Close is still one rung: two steps is a bigger lie than
    the engine should be told about a cadet."""
    squadron = _squadron(_settings())
    lead, wingman, escort = Pilot("Lead"), Pilot("Wingman"), Pilot("Escort")
    for pilot in (lead, wingman, escort):
        pilot.record.xp = 2000
    _close(lead, wingman, escort)
    package: Any = SimpleNamespace(flights=[])
    flight = _flight(lead, wingman, package=package)
    package.flights = [flight, _flight(escort, package=package)]

    assert _rung(squadron.mission_skill(lead, flight)) == _rung(Skill.Good) + 1


def test_a_single_ship_can_still_earn_it_from_its_package() -> None:
    """He is alone in the aircraft but not alone on the mission."""
    squadron = _squadron(_settings())
    alone, escort = Pilot("Alone"), Pilot("Escort")
    for pilot in (alone, escort):
        pilot.record.xp = 2000
    _close(alone, escort)
    package: Any = SimpleNamespace(flights=[])
    flight = _flight(alone, package=package)
    package.flights = [flight, _flight(escort, package=package)]

    assert _rung(squadron.mission_skill(alone, flight)) == _rung(Skill.Good) + 1


def test_it_sits_on_top_of_what_morale_did() -> None:
    """One rung for how he is and one for who he is with, and no more than that."""
    squadron = _squadron(_settings())
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    for pilot in (lead, wingman):
        pilot.record.xp = 2000
        pilot.morale = 95
    _close(lead, wingman)
    assert squadron.mission_skill(lead) is Skill.High  # morale alone
    assert squadron.mission_skill(lead, _flight(lead, wingman)) is Skill.Excellent


def test_asked_about_the_man_alone_it_says_nothing_about_the_formation() -> None:
    """The squadron list and the planner ask without a flight, and must get the same
    answer they always did."""
    squadron = _squadron(_settings())
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    for pilot in (lead, wingman):
        pilot.record.xp = 2000
    _close(lead, wingman)
    assert squadron.mission_skill(lead) is Skill.Good


def test_switched_off_nobody_flies_above_his_rank() -> None:
    squadron = _squadron(_settings(friendship_enabled=False))
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    for pilot in (lead, wingman):
        pilot.record.xp = 2000
    _close(lead, wingman)
    assert squadron.mission_skill(lead, _flight(lead, wingman)) is Skill.Good


# --- desertion -------------------------------------------------------------------


def test_friends_hold_a_man_where_rank_alone_did_not() -> None:
    squadron = _squadron(_settings())
    pilot = Pilot("Vega")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    squadron.current_roster = [pilot] + mates
    alone = squadron._desertion_chance(pilot)

    for mate in mates:
        friendship.move(pilot, mate, 5.0)
    assert squadron._desertion_chance(pilot) == alone * 0.75


def test_a_squadron_he_cannot_stand_does_not_push_him_out_any_faster() -> None:
    """There is no negative half to this one: the chance is rank's, and friendship can
    only take from it."""
    squadron = _squadron(_settings())
    pilot = Pilot("Vega")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    squadron.current_roster = [pilot] + mates
    alone = squadron._desertion_chance(pilot)

    for mate in mates:
        friendship.move(pilot, mate, -5.0)
    assert squadron._desertion_chance(pilot) == alone


# --- the morale drift ------------------------------------------------------------


def test_a_man_in_trouble_comes_home_faster_in_company() -> None:
    squadron = _squadron(_settings())
    pilot = Pilot("Vega")
    pilot.morale = 20
    friends = [Pilot(f"Friend{index}") for index in range(3)]
    squadron.current_roster = [pilot] + friends
    assert squadron._drift_for(pilot) == morale_rules.DRIFT_PER_TURN

    for friend in friends:
        friendship.move(pilot, friend, 5.0)
    assert squadron._drift_for(pilot) > morale_rules.DRIFT_PER_TURN


def test_only_the_ones_he_is_close_to_count() -> None:
    """Friendly is not Close. The band that helps is the one the drift alone cannot
    reach."""
    squadron = _squadron(_settings())
    pilot = Pilot("Vega")
    pilot.morale = 20
    friends = [Pilot(f"Friend{index}") for index in range(3)]
    squadron.current_roster = [pilot] + friends
    for friend in friends:
        friendship.move(pilot, friend, 1.5)  # Friendly, and no further
    assert squadron._drift_for(pilot) == morale_rules.DRIFT_PER_TURN


def test_the_company_cannot_carry_him_more_than_the_cap() -> None:
    squadron = _squadron(_settings(morale_drift_per_turn=10))
    pilot = Pilot("Vega")
    pilot.morale = 0
    friends = [Pilot(f"Friend{index}") for index in range(20)]
    squadron.current_roster = [pilot] + friends
    for friend in friends:
        friendship.move(pilot, friend, 5.0)
    assert squadron._drift_for(pilot) == 13  # 10, and the 30% the cap allows


def test_a_man_flying_high_comes_down_faster_among_people_who_cannot_stand_him() -> (
    None
):
    """The other direction reads the other end of the pair: what they think of him."""
    squadron = _squadron(_settings(morale_drift_per_turn=10))
    pilot = Pilot("Vega")
    pilot.morale = 100
    enemies = [Pilot(f"Enemy{index}") for index in range(3)]
    squadron.current_roster = [pilot] + enemies
    for enemy in enemies:
        friendship.move(enemy, pilot, -5.0)
    assert squadron._drift_for(pilot) == -12  # 10 and the 15% three of them are worth


def test_nobody_is_carried_past_the_middle() -> None:
    """The drift is a step home, not a push past it."""
    squadron = _squadron(_settings())
    pilot = Pilot("Vega")
    pilot.morale = 47
    friends = [Pilot(f"Friend{index}") for index in range(6)]
    squadron.current_roster = [pilot] + friends
    for friend in friends:
        friendship.move(pilot, friend, 5.0)
    assert pilot.morale + squadron._drift_for(pilot) == morale_rules.MORALE_START


# --- leave -----------------------------------------------------------------------


def test_leave_is_worth_more_taken_with_the_others() -> None:
    squadron = _squadron(_settings())
    pilot, mate = Pilot("Vega"), Pilot("Mate")
    friendship.move(pilot, mate, 5.0)
    ordinary = morale_rules.ON_LEAVE.amount(squadron.settings)

    assert squadron._leave_event(pilot, [pilot]).amount(squadron.settings) == ordinary
    together = squadron._leave_event(pilot, [pilot, mate])
    assert together.amount(squadron.settings) == round(ordinary * 1.4)


def test_the_last_week_alone_is_an_ordinary_week() -> None:
    """Worked out again every turn, so the bonus goes as the others come back."""
    squadron = _squadron(_settings())
    pilot, mate = Pilot("Vega"), Pilot("Mate")
    friendship.move(pilot, mate, 5.0)
    mate.status = PilotStatus.Active  # he came back this turn; the other is still away
    assert squadron._leave_event(pilot, [pilot]).amount(squadron.settings) == (
        morale_rules.ON_LEAVE.amount(squadron.settings)
    )


def test_the_company_of_men_he_dislikes_is_worth_no_less_than_his_own() -> None:
    squadron = _squadron(_settings())
    pilot, mate = Pilot("Vega"), Pilot("Mate")
    friendship.move(pilot, mate, -5.0)
    assert squadron._leave_event(pilot, [pilot, mate]).amount(squadron.settings) == (
        morale_rules.ON_LEAVE.amount(squadron.settings)
    )


# --- back from the hospital ------------------------------------------------------


def _recover(squadron: Any, hurt: Pilot, *watchers: Pilot) -> None:
    hurt.wound(1, turn=1)
    squadron.current_roster = [hurt] + list(watchers)
    squadron.tend_the_wounded()


def test_a_man_walking_out_of_hospital_is_felt_most_by_his_friends() -> None:
    squadron = _squadron(_settings())
    hurt = Pilot("Hurt")
    friend, stranger = Pilot("Friend"), Pilot("Stranger")
    friendship.move(friend, hurt, 5.0)

    _recover(squadron, hurt, friend, stranger)

    assert hurt.status is PilotStatus.Active
    assert friend.morale > stranger.morale > morale_rules.MORALE_START


def test_he_does_not_congratulate_himself_on_being_discharged() -> None:
    squadron = _squadron(_settings())
    hurt = Pilot("Hurt")
    _recover(squadron, hurt, Pilot("Stranger"))
    assert hurt.morale == morale_rules.MORALE_START


def test_nobody_notices_while_he_is_still_in_the_bed() -> None:
    squadron = _squadron(_settings())
    hurt, stranger = Pilot("Hurt"), Pilot("Stranger")
    hurt.wound(3, turn=1)
    squadron.current_roster = [hurt, stranger]
    squadron.tend_the_wounded()
    assert hurt.status is PilotStatus.Wounded
    assert stranger.morale == morale_rules.MORALE_START


# --- cohesion --------------------------------------------------------------------


def test_cohesion_is_the_whole_roster_averaged() -> None:
    squadron = _squadron(_settings())
    crew = [Pilot(f"P{index}") for index in range(3)]
    squadron.current_roster = crew
    assert squadron.cohesion == friendship.FRIENDSHIP_START

    _close(*crew)
    squadron._cohesion = None
    assert squadron.cohesion == friendship.FRIENDSHIP_MAX


def test_cohesion_is_worked_out_once_a_turn() -> None:
    """It is O(n^2) in the roster, which is nothing once and wasteful on every repaint
    of the Air Wing list."""
    squadron = _squadron(_settings())
    crew = [Pilot(f"P{index}") for index in range(3)]
    squadron.current_roster = crew
    was = squadron.cohesion

    _close(*crew)
    assert squadron.cohesion == was  # still the answer from earlier in the turn

    squadron.destination = None
    squadron.tend_the_wounded = lambda: None
    squadron.tend_morale = lambda turn: None
    squadron.replenish_lost_pilots = lambda: None
    squadron.deliver_orders = lambda: None
    squadron.end_turn()
    assert squadron.cohesion == friendship.FRIENDSHIP_MAX


def test_a_squadron_with_friendship_off_has_nothing_to_say_about_it() -> None:
    squadron = _squadron(_settings(friendship_enabled=False))
    squadron.current_roster = [Pilot("A"), Pilot("B")]
    assert squadron.cohesion is None
