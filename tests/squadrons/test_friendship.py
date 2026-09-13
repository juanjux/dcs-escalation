"""What a pilot thinks of the man next to him, and how it moves.

The rules are tested rather than the implementation, because every one of them is a
place the obvious code is wrong: friendship has a direction and moving one end must not
move the other, and the bands that pay for anything have to be out of reach of the drift
that costs nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from game.squadrons import friendship
from game.squadrons.pilot import Pilot


def _pilot(name: str = "Someone") -> Pilot:
    return Pilot(name)


def _settings(**values: Any) -> Any:
    return SimpleNamespace(**values)


# --- the ruler ------------------------------------------------------------------


def test_two_men_who_have_never_met_are_neutral() -> None:
    a, b = _pilot("A"), _pilot("B")
    assert friendship.feeling(a, b) == friendship.FRIENDSHIP_START
    assert a.friendships == {}


def test_points_are_measured_from_neutral() -> None:
    assert friendship.points(5.0) == 0
    assert friendship.points(10.0) == 5
    assert friendship.points(0.0) == -5


def test_every_band_is_reachable_and_named() -> None:
    assert friendship.band_name(10.0) == "Inseparable"
    assert friendship.band_name(7.1) == "Close"
    assert friendship.band_name(7.0) == "Friendly"
    assert friendship.band_name(5.0) == "Neutral"
    assert friendship.band_name(3.0) == "Frosty"
    assert friendship.band_name(2.0) == "Hostile"
    assert friendship.band_name(0.0) == "Bad blood"


def test_neutral_is_symmetric_about_where_every_pair_starts() -> None:
    """Drift moves a pair by a whole point, so one quiet turn leaves it on four or
    on six. Neutral held six and not four, so an even walk painted every pair that
    had drifted down once as going cold and every pair that had drifted up once as
    nothing at all -- and a campaign came out looking like nobody got on with
    anybody.
    """
    assert friendship.band_name(4.0) == "Neutral"
    assert friendship.band_name(6.0) == "Neutral"

    # And two steps is a relationship, either way.
    assert friendship.band_name(3.0) == "Frosty"
    assert friendship.band_name(7.0) == "Friendly"


# --- direction ------------------------------------------------------------------


def test_moving_one_direction_leaves_the_other_alone() -> None:
    """The whole reason for the extra state: he can think the world of a man who
    cannot stand him."""
    a, b = _pilot("A"), _pilot("B")
    friendship.move(a, b, 3.0)
    assert friendship.feeling(a, b) == 8.0
    assert friendship.feeling(b, a) == friendship.FRIENDSHIP_START
    assert b.friendships == {}


def test_a_man_has_no_opinion_of_himself() -> None:
    a = _pilot("A")
    assert friendship.move(a, a, 3.0) == 0.0
    assert a.friendships == {}


def test_it_clamps_at_both_ends() -> None:
    a, b = _pilot("A"), _pilot("B")
    friendship.move(a, b, 99)
    assert friendship.feeling(a, b) == friendship.FRIENDSHIP_MAX
    assert friendship.move(a, b, 5) == 0.0
    friendship.move(a, b, -99)
    assert friendship.feeling(a, b) == friendship.FRIENDSHIP_MIN
    assert friendship.move(a, b, -5) == 0.0


def test_coming_back_to_neutral_carries_nothing() -> None:
    """A graph of every pair at every base is a lot of dictionary; a pair with no
    opinion should cost nothing to have."""
    a, b = _pilot("A"), _pilot("B")
    friendship.move(a, b, 2.0)
    assert b.id in a.friendships
    friendship.move(a, b, -2.0)
    assert a.friendships == {}


# --- the drift ------------------------------------------------------------------


def _drift(roll: float, same_squadron: bool = True, current: float = 5.0) -> float:
    with patch("game.squadrons.friendship.random.random", return_value=roll / 100):
        return friendship.drift_step(same_squadron, current)


def test_a_squadron_mate_warms_more_often_than_he_cools() -> None:
    """35 warm, 20 cool, and the 45 that are left do nothing."""
    assert _drift(10.0) == 1.0
    assert _drift(40.0) == -1.0
    assert _drift(90.0) == 0.0


def test_the_squadron_across_the_ramp_moves_less() -> None:
    """Same roll, different answer: 22 warm and 10 cool rather than 35 and 20.

    A turn that warms him to the men he flies with can cool him to the ones he only
    queues behind, which is the whole reason the two tables are separate.
    """
    assert _drift(25.0, same_squadron=True) == 1.0  # his own squadron warms
    assert _drift(25.0, same_squadron=False) == -1.0  # the other one cools
    assert _drift(33.0, same_squadron=True) == 1.0
    assert _drift(33.0, same_squadron=False) == 0.0  # past the 32 that move at all


def test_the_drift_cannot_make_close_friends() -> None:
    """Anything above Friendly is earned in the air. A quiet turn at a base cannot buy
    the bands that pay for synergy or for being looked for."""
    assert _drift(10.0, current=6.5) == 0.5  # up to the ceiling, not past it
    assert _drift(10.0, current=7.0) == 0.0
    assert _drift(10.0, current=9.0) == 0.0


def test_falling_out_has_no_floor() -> None:
    """Losing touch with somebody needs nothing but time, which is the asymmetry."""
    assert _drift(40.0, current=2.0) == -1.0
    assert _drift(40.0, current=0.5) == -1.0


# --- what a group is worth ------------------------------------------------------


def test_synergy_of_a_formation_that_has_never_met_is_neutral() -> None:
    crew = [_pilot("A"), _pilot("B"), _pilot("C")]
    assert friendship.synergy(crew) == friendship.FRIENDSHIP_START


def test_synergy_of_one_man_is_neutral() -> None:
    assert friendship.synergy([_pilot("A")]) == friendship.FRIENDSHIP_START
    assert friendship.synergy([]) == friendship.FRIENDSHIP_START


def test_the_leader_carries_more_of_the_answer() -> None:
    """Spreading senior pilots one to a flight has to be worth more than stacking
    them, which is only true if the leader's own relationships weigh heaviest."""
    lead, a, b = _pilot("Lead"), _pilot("A"), _pilot("B")
    # The lead is adored, and the other two cannot stand each other.
    for other in (a, b):
        friendship.move(lead, other, 4.0)
        friendship.move(other, lead, 4.0)
    friendship.move(a, b, -4.0)
    friendship.move(b, a, -4.0)

    plain = friendship.synergy([lead, a, b])
    weighted = friendship.synergy([lead, a, b], leader=lead)
    assert weighted > plain


def test_a_leader_who_is_not_in_the_formation_is_ignored() -> None:
    crew = [_pilot("A"), _pilot("B")]
    stranger = _pilot("Stranger")
    assert friendship.synergy(crew, leader=stranger) == friendship.synergy(crew)


def test_group_affinity_reads_both_directions() -> None:
    """What the picker paints: the question there is whether they would get on, not
    what one of them thinks."""
    a, b = _pilot("A"), _pilot("B")
    friendship.move(a, b, 4.0)  # he thinks the world of her; she is indifferent
    assert friendship.mean_towards(a, [b]) == 9.0
    assert friendship.mean_from(a, [b]) == 5.0
    assert friendship.group_affinity(a, [b]) == 7.0


def test_the_means_of_nobody_are_neutral() -> None:
    a = _pilot("A")
    assert friendship.mean_towards(a, []) == friendship.FRIENDSHIP_START
    assert friendship.mean_from(a, []) == friendship.FRIENDSHIP_START
    assert friendship.group_affinity(a, []) == friendship.FRIENDSHIP_START


# --- what it is worth -----------------------------------------------------------


def test_the_experience_bonus_is_signed() -> None:
    """A formation he cannot stand is worth less than flying alone, and that is the
    point of it. The floor belongs on the multiplier, not here."""
    assert friendship.xp_bonus(10.0) == 0.25
    assert friendship.xp_bonus(5.0) == 0.0
    assert friendship.xp_bonus(0.0) == -0.25


def test_the_experience_bonus_rounds_to_whole_points() -> None:
    """And rounds halves to EVEN, which is Python's rule: round(2.5) is 2, not 3. It
    reads like a bug to whoever finds it next, so it is written down here."""
    assert friendship.xp_bonus(5.0 + 0.667) == 0.05  # 0.667 points -> 1
    assert friendship.xp_bonus(5.0 + 3.75) == 0.20  # 3.75 points -> 4
    assert friendship.xp_bonus(5.0 + 2.5) == 0.10  # 2.5 points -> 2, not 3


def test_being_disliked_does_not_slow_anybody_to_a_burning_cockpit() -> None:
    assert friendship.survival_bonus(0.0) == 0.0
    assert friendship.survival_bonus(5.0) == 0.0
    assert friendship.survival_bonus(10.0) > 0.0


def test_the_survival_bonus_is_a_nudge_not_a_rewrite() -> None:
    """Five points is the ceiling on this ruler, so three per point is fifteen."""
    assert round(friendship.survival_bonus(10.0), 6) == 0.15


def test_friends_hold_a_man_where_rank_alone_did_not() -> None:
    assert friendship.desertion_modifier(5.0) == 1.0
    assert friendship.desertion_modifier(10.0) == 0.75
    assert friendship.desertion_modifier(0.0) == 1.0  # enemies do not push him out


def test_leave_is_worth_more_taken_with_the_others() -> None:
    assert friendship.leave_multiplier(5.0) == 1.0
    assert round(friendship.leave_multiplier(10.0), 6) == 1.4


def test_grief_is_a_whole_number_and_never_less_than_once() -> None:
    """times repeats a list, so it has to be an integer -- and a man he hated dying in
    front of him is still a man dying in front of him."""
    assert friendship.grief_times(1, 10.0) > 1
    assert friendship.grief_times(1, 5.0) == 1
    assert friendship.grief_times(1, 0.0) == 1
    assert isinstance(friendship.grief_times(3, 8.0), int)


def test_a_formation_flies_a_rung_better_only_from_close() -> None:
    assert friendship.flies_a_rung_better(7.1)
    assert not friendship.flies_a_rung_better(7.0)


# --- housekeeping ---------------------------------------------------------------


def test_a_pilot_keeps_only_the_opinions_he_holds_most_strongly() -> None:
    a = _pilot("A")
    others = [_pilot(f"P{index}") for index in range(10)]
    for index, other in enumerate(others):
        friendship.move(a, other, (index + 1) * 0.1)
    friendship.trim(a, _settings(friendship_limit=3))
    assert len(a.friendships) == 3
    assert {others[-1].id, others[-2].id, others[-3].id} == set(a.friendships)


def test_the_men_who_are_gone_are_forgotten() -> None:
    a, here, gone = _pilot("A"), _pilot("Here"), _pilot("Gone")
    friendship.move(a, here, 2.0)
    friendship.move(a, gone, 2.0)
    friendship.prune(a, {here.id})
    assert set(a.friendships) == {here.id}


# --- save compatibility ---------------------------------------------------------


def test_a_pilot_from_a_save_without_friendship_reads_an_empty_graph() -> None:
    """Every field added since the original format is back-filled in __setstate__, and
    the graph is no different -- except that the id has to be built, because a
    default_factory field has no class attribute to fall back on."""
    pilot = Pilot.__new__(Pilot)
    pilot.__setstate__({"name": "Old Hand", "player": False})
    assert pilot.friendships == {}
    assert pilot.id is not None


def test_two_pilots_from_an_old_save_are_not_the_same_man() -> None:
    first, second = Pilot.__new__(Pilot), Pilot.__new__(Pilot)
    first.__setstate__({"name": "Twin"})
    second.__setstate__({"name": "Twin"})
    assert first.id != second.id


def test_the_id_does_not_change_what_equals_means() -> None:
    """Half the app compares pilots with ==, and Squadron.claim_pilot exists because
    two men of the same name already compare equal. Giving every pilot an id must not
    quietly turn that into identity."""
    assert _pilot("Twin") == _pilot("Twin")


# --- the man in front -------------------------------------------------------------


def _four_ship() -> tuple[Pilot, Pilot, Pilot, Pilot]:
    return _pilot("Lead"), _pilot("Two"), _pilot("Three"), _pilot("Four")


def test_the_leader_is_half_of_what_a_wingman_makes_of_a_four_ship() -> None:
    """Two for the man in front against one each for the wingmen: two of the four
    weights, so half of it."""
    lead, two, three, four = _four_ship()
    friendship.move(two, lead, 4.0)  # 9.0 towards the leader, 5.0 to the others
    assert friendship.mean_towards(two, [lead, three, four], lead) == 7.0


def test_how_much_the_man_in_front_counts_for_is_a_setting() -> None:
    """At three it is three of five weights, which is sixty per cent of it."""
    lead, two, three, four = _four_ship()
    friendship.move(two, lead, 4.0)
    settings = _settings(friendship_leader_spoke_weight=3.0)
    assert friendship.mean_towards(two, [lead, three, four], lead, settings) == 7.4


def test_from_where_the_leader_sits_there_is_nobody_in_front() -> None:
    """His own three weigh the same. He is not his own leader."""
    lead, two, three, four = _four_ship()
    friendship.move(lead, two, 4.0)
    crew = [two, three, four]
    assert friendship.mean_towards(lead, crew, lead) == friendship.mean_towards(
        lead, crew
    )


def test_in_a_pair_only_the_other_man_matters() -> None:
    a, b = _pilot("A"), _pilot("B")
    friendship.move(a, b, 3.0)
    assert friendship.mean_towards(a, [b], b) == 8.0
    assert friendship.mean_towards(a, [b]) == 8.0


def test_the_men_who_look_for_him_are_weighted_the_same_way() -> None:
    """The other direction, because the man running the formation decides how hard
    anybody looks."""
    lead, two, three, four = _four_ship()
    friendship.move(lead, two, 4.0)  # the leader thinks the world of him
    assert friendship.mean_from(two, [lead, three, four], lead) == 7.0


def test_a_formation_is_what_the_men_in_it_experience() -> None:
    """Each man's own weighted mean, averaged -- so a crew that would follow its lead
    reads better than the plain mean of every pair would say."""
    lead, two, three, four = _four_ship()
    for wingman in (two, three, four):
        friendship.move(wingman, lead, 4.0)
    # Each wingman: (2*9 + 5 + 5) / 4 = 7.0. The lead, unweighted: 5.0.
    assert friendship.synergy([lead, two, three, four], lead) == (7.0 * 3 + 5.0) / 4


def test_a_campaign_that_never_moved_the_bands_gets_the_straight_ones() -> None:
    """The floors are settings, so they live in the save: a campaign under way would
    have kept the lopsided pair for ever."""
    from game.settings import Settings

    state = {"friendship_band_neutral": 4.1, "friendship_band_frosty": 3.1}
    Settings._migrate_lopsided_friendship_bands(state)
    assert state == {"friendship_band_neutral": 4.0, "friendship_band_frosty": 3.0}


def test_a_campaign_that_set_its_own_bands_keeps_them() -> None:
    """Only the floors that shipped are corrected. Anything else was chosen."""
    from game.settings import Settings

    state = {"friendship_band_neutral": 4.5, "friendship_band_frosty": 2.0}
    Settings._migrate_lopsided_friendship_bands(state)
    assert state == {"friendship_band_neutral": 4.5, "friendship_band_frosty": 2.0}
