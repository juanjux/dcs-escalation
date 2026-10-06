"""Experience, promotion, and what a sortie is worth.

Rank used to be a count of missions flown, which ticked for every pilot in the ATO
whether he flew, fought, or died on the ramp. It is earned now.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from dcs.unit import Skill

from game.dcs.skills import (
    CADET_SKILL,
    SKILL_LADDER,
    SKILL_XP_THRESHOLDS,
    experience_for_skill,
    skill_for_experience,
)
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.ato import FlightType
from game.settings import Settings
from game.squadrons.experience import (
    SURVIVAL_BY_SKILL,
    SURVIVAL_CADET,
    SURVIVAL_SETTINGS,
    XP_AIR_KILL,
    XP_DAMAGE_SHARE,
    XP_GROUND_KILL,
    XP_SHIP_KILL,
    building_xp,
    survival_chance,
)
from game.squadrons.pilot import Pilot, PilotRecord

# --- the ladder -------------------------------------------------------------


def test_a_rung_costs_what_it_says() -> None:
    assert SKILL_XP_THRESHOLDS == (0, 1500, 4000, 8000, 16000)
    assert len(SKILL_XP_THRESHOLDS) == len(SKILL_LADDER)


@pytest.mark.parametrize(
    "xp,expected",
    [
        (0, CADET_SKILL),
        (1499, CADET_SKILL),
        (1500, Skill.Average),
        (3999, Skill.Average),
        (4000, Skill.Good),
        (7999, Skill.Good),
        (8000, Skill.High),
        (15999, Skill.High),
        (16000, Skill.Excellent),
        (99999, Skill.Excellent),
    ],
)
def test_the_threshold_is_the_boundary(xp: int, expected: Skill) -> None:
    """One point short is one rank short."""
    assert skill_for_experience(xp, CADET_SKILL) is expected


def test_the_coalition_setting_is_a_floor_not_a_start() -> None:
    """Raising the difficulty lifts the wing; it never demotes a veteran."""
    assert skill_for_experience(0, Skill.High) is Skill.High
    assert skill_for_experience(16000, Skill.High) is Skill.Excellent


def test_seeding_a_veteran_costs_what_his_rank_costs() -> None:
    for skill, threshold in zip(SKILL_LADDER, SKILL_XP_THRESHOLDS):
        assert experience_for_skill(skill) == threshold


def test_a_skill_that_is_not_a_rung_seeds_nothing() -> None:
    assert experience_for_skill(Skill.Random) == 0


# --- persistence ------------------------------------------------------------


def test_a_pilot_from_an_older_save_starts_at_zero() -> None:
    """PilotRecord predates experience; unpickling one must not raise."""
    record = PilotRecord.__new__(PilotRecord)
    record.__setstate__({"missions_flown": 12})
    assert record.missions_flown == 12
    assert record.xp == 0


# --- what things are worth --------------------------------------------------


@pytest.mark.parametrize(
    "category,xp",
    [("oil", 500), ("derrick", 400), ("factory", 125), ("ammo", 100), ("farp", 50)],
)
def test_a_building_is_paid_by_what_it_is_worth(category: str, xp: int) -> None:
    assert building_xp(category) == xp


def test_an_unpriced_category_still_pays_something() -> None:
    """Power plants and command centres earn nothing per turn but are worth bombing."""
    assert building_xp("power") > 0
    assert building_xp(None) > 0


def test_the_better_pilot_is_likelier_to_walk_away() -> None:
    chances = [survival_chance(skill) for skill in SKILL_LADDER]
    assert chances == sorted(chances)
    assert chances[0] < chances[-1]


def test_the_settings_ship_the_documented_odds() -> None:
    """The table in the module and the boxes on the settings page must not drift."""
    settings = Settings()
    for skill, name in zip(SKILL_LADDER, SURVIVAL_SETTINGS):
        documented = SURVIVAL_BY_SKILL.get(skill, SURVIVAL_CADET)
        assert getattr(settings, name) / 100 == pytest.approx(documented)


def test_the_player_can_tune_the_odds() -> None:
    settings = Settings()
    settings.live_pilots_survival_cadet = 5
    settings.live_pilots_survival_excellent = 95
    assert survival_chance(CADET_SKILL, settings) == pytest.approx(0.05)
    assert survival_chance(Skill.Excellent, settings) == pytest.approx(0.95)


def test_a_pilot_flying_at_a_skill_that_is_not_a_rung_gets_the_bottom_odds() -> None:
    """Random and Player are skills to DCS but not rungs of anything."""
    settings = Settings()
    assert survival_chance(Skill.Random, settings) == pytest.approx(
        settings.live_pilots_survival_cadet / 100
    )


# --- crediting a kill -------------------------------------------------------


def _processor() -> MissionResultsProcessor:
    return MissionResultsProcessor(MagicMock())


def _victim_flight() -> Any:
    return SimpleNamespace(flight=MagicMock(), pilot=MagicMock())


def _victim_theater_unit(unit_type: Any, category: str = "oil") -> Any:
    tgo = SimpleNamespace(category=category, control_point=MagicMock())
    return SimpleNamespace(
        theater_unit=SimpleNamespace(unit_type=unit_type, ground_object=tgo)
    )


def test_an_aircraft_is_worth_an_air_kill() -> None:
    assert _processor()._kill_xp(_victim_flight()) == XP_AIR_KILL


def test_a_building_is_worth_its_category() -> None:
    # Statics carry no unit type at all, which is exactly how a building is recognised.
    assert _processor()._kill_xp(_victim_theater_unit(None, "oil")) == building_xp(
        "oil"
    )


def test_a_hull_is_worth_a_flat_rate() -> None:
    from game.dcs.shipunittype import ShipUnitType

    ship = MagicMock(spec=ShipUnitType)
    assert _processor()._kill_xp(_victim_theater_unit(ship)) == XP_SHIP_KILL


def test_a_vehicle_is_worth_a_ground_kill() -> None:
    from game.dcs.groundunittype import GroundUnitType

    vehicle = MagicMock(spec=GroundUnitType)
    assert _processor()._kill_xp(_victim_theater_unit(vehicle)) == XP_GROUND_KILL


def test_nothing_destroyed_is_worth_nothing() -> None:
    assert _processor()._kill_xp(None) == 0


# --- naming the killer ------------------------------------------------------


def _debriefing_with(killer_pilot_name: str | None, killer_is_blue: bool) -> Any:
    if killer_pilot_name is None:
        killer = None
    else:
        killer = SimpleNamespace(
            pilot=SimpleNamespace(name=killer_pilot_name),
            flight=SimpleNamespace(
                squadron=SimpleNamespace(player=SimpleNamespace(is_blue=killer_is_blue))
            ),
        )
    return SimpleNamespace(unit_map=SimpleNamespace(flight=lambda name: killer))


def test_nobody_credited_reads_as_a_crash() -> None:
    text, friendly = _processor()._describe_killer(None, MagicMock(), True)
    assert text == "a crash"
    assert friendly is False


def test_the_roster_pilot_is_named_when_he_can_be_resolved() -> None:
    detail = {
        "initiator": "STAG|2|1|F-15C|",
        "initiator_type": "F-15C",
        "weapon": "AIM-120C",
    }
    text, friendly = _processor()._describe_killer(
        detail, _debriefing_with("Capt Ortega", killer_is_blue=False), True
    )
    assert text == "Capt Ortega (F-15C) with AIM-120C"
    assert friendly is False


def test_an_unresolvable_killer_falls_back_to_the_airframe() -> None:
    detail = {"initiator": "unknown", "initiator_type": "SA-11 Buk LN"}
    text, _ = _processor()._describe_killer(
        detail, _debriefing_with(None, killer_is_blue=False), True
    )
    assert text == "SA-11 Buk LN"


def test_a_killer_on_our_own_side_is_flagged() -> None:
    detail = {"initiator": "STAG|2|1|F-15C|", "initiator_type": "F-15C"}
    _, friendly = _processor()._describe_killer(
        detail, _debriefing_with("Maj Ruiz", killer_is_blue=True), True
    )
    assert friendly is True


# --- who is listed first ----------------------------------------------------


def _ranked_squadron(settings: Settings) -> Any:
    """A squadron thin enough to ask about rank without building a campaign."""
    from game.squadrons.squadron import Squadron

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.coalition = SimpleNamespace(player=SimpleNamespace(is_blue=True))
    squadron.country = None
    return squadron


def _pilot(name: str, xp: int) -> Pilot:
    return Pilot(name, record=PilotRecord(xp=xp))


def _live_settings() -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = CADET_SKILL.value
    return settings


def test_the_air_wing_lists_the_senior_pilot_first() -> None:
    squadron = _ranked_squadron(_live_settings())
    pilots = [_pilot("Cadet", 0), _pilot("Ace", 16000), _pilot("Captain", 4000)]
    assert [p.name for p in sorted(pilots, key=squadron.rank_order)] == [
        "Ace",
        "Captain",
        "Cadet",
    ]


def test_pilots_of_one_rank_are_sorted_by_what_they_have_flown() -> None:
    squadron = _ranked_squadron(_live_settings())
    pilots = [_pilot("Junior", 4000), _pilot("Senior", 7999)]
    assert [p.name for p in sorted(pilots, key=squadron.rank_order)] == [
        "Senior",
        "Junior",
    ]


def test_with_the_feature_off_the_roster_keeps_its_own_order() -> None:
    """No rank is shown then, so nothing may reshuffle the list behind the player."""
    squadron = _ranked_squadron(Settings())
    pilots = [_pilot("First", 0), _pilot("Second", 8000)]
    assert [p.name for p in sorted(pilots, key=squadron.rank_order)] == [
        "First",
        "Second",
    ]


# --- crediting an assist ----------------------------------------------------

ATTACKER = "STAG|1|1|F-18C|"


def _killer(is_blue: bool = True, name: str = "Capt Ortega") -> Any:
    return SimpleNamespace(
        pilot=Pilot(name),
        flight=SimpleNamespace(
            squadron=SimpleNamespace(player=SimpleNamespace(is_blue=is_blue))
        ),
    )


def _ship(is_blue: bool) -> Any:
    from game.dcs.shipunittype import ShipUnitType

    return SimpleNamespace(
        theater_unit=SimpleNamespace(
            unit_type=MagicMock(spec=ShipUnitType),
            ground_object=SimpleNamespace(
                category="ship",
                control_point=SimpleNamespace(
                    captured=SimpleNamespace(is_blue=is_blue)
                ),
            ),
        )
    )


def _events(killer: Any, victim: Any, hits: Any, kills: Any = ()) -> Any:
    return SimpleNamespace(
        state_data=SimpleNamespace(hit_details=list(hits), kill_details=list(kills)),
        unit_map=SimpleNamespace(
            flight=lambda name: killer if name == ATTACKER else None
        ),
        resolve_killed_object=lambda name: victim if name == "DESTROYER" else None,
    )


def test_a_hull_left_burning_pays_a_share_of_the_hull() -> None:
    killer = _killer(is_blue=True)
    debriefing = _events(
        killer, _ship(is_blue=False), [{"initiator": ATTACKER, "target": "DESTROYER"}]
    )
    assert _processor()._experience_from_damage(debriefing, set()) == {
        id(killer.pilot): int(XP_SHIP_KILL * XP_DAMAGE_SHARE)
    }


def test_the_pilot_who_sank_her_is_not_paid_twice() -> None:
    """His own hit is in the log too; the kill already covered it."""
    killer = _killer(is_blue=True)
    event = [{"initiator": ATTACKER, "target": "DESTROYER"}]
    debriefing = _events(killer, _ship(is_blue=False), event, event)
    processor = _processor()
    earned, credited = processor._experience_from_kills(debriefing)
    assert earned == {id(killer.pilot): XP_SHIP_KILL}
    assert processor._experience_from_damage(debriefing, credited) == {}


def test_hitting_our_own_ship_pays_nothing() -> None:
    killer = _killer(is_blue=True)
    debriefing = _events(
        killer, _ship(is_blue=True), [{"initiator": ATTACKER, "target": "DESTROYER"}]
    )
    assert _processor()._experience_from_damage(debriefing, set()) == {}


def test_a_hit_by_something_that_is_not_a_roster_aircraft_pays_nobody() -> None:
    debriefing = _events(
        None, _ship(is_blue=False), [{"initiator": "SAM SA-11", "target": "DESTROYER"}]
    )
    assert _processor()._experience_from_damage(debriefing, set()) == {}


def test_an_older_save_carries_no_hits_at_all() -> None:
    """hit_details postdates the feature; a state.json without it must not raise."""
    from game.debriefing import StateData

    assert StateData.from_json({}, MagicMock()).hit_details == []


# --- switching the feature on -----------------------------------------------


def test_the_floor_drops_to_cadet_without_touching_the_difficulty_page() -> None:
    """The reset used to be written into the settings, and leaked from there.

    A campaign started afterwards inherited player_skill=Cadet, so the next time the
    feature was switched on it seeded that wing from Cadet -- zero -- while the other
    coalition, still at its own skill, kept its rank.
    """
    settings = Settings()
    settings.player_skill = Skill.High.value
    squadron = _ranked_squadron(settings)

    assert squadron.base_skill is Skill.High
    settings.live_pilots_enabled = True
    assert squadron.base_skill is CADET_SKILL
    assert squadron.difficulty_skill is Skill.High
    assert settings.player_skill == Skill.High.value


def test_the_wing_is_seeded_with_the_rank_it_was_flying_at() -> None:
    settings = _live_settings()
    settings.player_skill = Skill.High.value
    squadron = _ranked_squadron(settings)
    pilot = _pilot("Veteran", 0)

    pilot.record.xp = max(
        pilot.record.xp, experience_for_skill(squadron.difficulty_skill)
    )
    assert squadron.pilot_skill(pilot) is Skill.High


# --- the temporary ledger ---------------------------------------------------


def test_the_ledger_shows_what_was_paid_and_what_it_left_him_with(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from game.squadrons import xplog

    pilot = SimpleNamespace(name="Capt Ortega")
    log = xplog.XpLog(6)
    log.award(pilot, 500, "destroyed", object(), "RED 3-1")
    log.collected(
        pilot,
        "VFA-2",
        "F/A-18C",
        1200,
        2200,
        [("returned", "mission complete", 500)],
        "Capt -> Maj",
    )

    written = tmp_path / "live_pilots_xp.log"
    original, xplog.LOG_PATH = xplog.LOG_PATH, written
    try:
        log.write()
    finally:
        xplog.LOG_PATH = original

    text = written.read_text(encoding="utf-8")
    assert "turn 6" in text
    assert "Capt Ortega (VFA-2, F/A-18C): 1200 -> 2200 (+1000)" in text
    assert '+500   destroyed object "RED 3-1"' in text
    assert "+500   returned  mission complete" in text
    assert "promoted: Capt -> Maj" in text


def test_a_quiet_turn_writes_nothing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from game.squadrons import xplog

    written = tmp_path / "live_pilots_xp.log"
    original, xplog.LOG_PATH = xplog.LOG_PATH, written
    try:
        xplog.XpLog(6).write()
    finally:
        xplog.LOG_PATH = original
    assert not written.exists()


# --- telling the player -----------------------------------------------------


class _RankStub:
    def __init__(self, abbreviation: str, name: str) -> None:
        self.abbreviation = abbreviation
        self.name = name

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, _RankStub) and other.abbreviation == self.abbreviation


class _PromotingSquadron:
    """Promotes at 2000, which is the Captain rung."""

    base_skill = CADET_SKILL
    aircraft = "F/A-18C"
    # The debriefing records which side a pilot flew for, so it can choose not to
    # report the other one's aircrew.
    player = SimpleNamespace(is_blue=True)

    def pilot_skill(self, pilot: Pilot) -> Any:
        return CADET_SKILL

    def pilot_rank(self, pilot: Pilot) -> Any:
        if pilot.record.xp >= 2000:
            return _RankStub("Capt", "Captain")
        return _RankStub("1stLt", "First Lieutenant")

    def __str__(self) -> str:
        return "VFA-2"


def _promote(pilot: Pilot) -> Any:
    from game.squadrons.experience import PilotOutcomes

    flight = SimpleNamespace(
        squadron=_PromotingSquadron(),
        unit_type="F/A-18C",
        flight_type=FlightType.BARCAP,
        package=SimpleNamespace(target=SimpleNamespace(name="somewhere")),
        roster=SimpleNamespace(iter_pilots=lambda: [pilot]),
    )
    ato: Any = SimpleNamespace(packages=[SimpleNamespace(flights=[flight])])
    debriefing: Any = SimpleNamespace(pilot_outcomes=PilotOutcomes())
    _processor()._commit_pilot_experience(ato, debriefing, {})
    return debriefing.pilot_outcomes.promotions


def test_the_promotion_says_whose_it_is_and_spells_the_rank_out() -> None:
    """The popup congratulates the human by name; the AI does not get a parade."""
    pilot = _pilot("Lt Vega", 1500)
    pilot.player = True

    (promotion,) = _promote(pilot)

    assert promotion.player is True
    assert promotion.to_rank == "Capt"
    assert promotion.to_rank_full == "Captain"
    assert promotion.pilot_name == "Lt Vega"


def test_an_ai_promotion_is_recorded_but_not_the_players() -> None:
    (promotion,) = _promote(_pilot("Lt Vega", 1500))
    assert promotion.player is False


# --- one promotion a mission ------------------------------------------------


@pytest.mark.parametrize(
    "before,after,expected,why",
    [
        (0, 5000, 1500, "a cadet who earns two rungs makes one, and holds its price"),
        (0, 900, 900, "experience that promotes nobody is kept in full"),
        (0, 2500, 1500, "promotion leaves nothing banked towards the next rung"),
        (1500, 1700, 1700, "no promotion, no cap"),
        (1500, 17000, 4000, "from Average, one rung is Good however good the sortie"),
        (16000, 20000, 20000, "the top rung cannot be jumped past"),
    ],
)
def test_a_pilot_climbs_one_rung_a_mission(
    before: int, after: int, expected: int, why: str
) -> None:
    from game.dcs.skills import one_promotion_at_most

    assert one_promotion_at_most(before, after, CADET_SKILL) == expected, why


def test_the_ledger_shows_what_the_cap_took_away() -> None:
    from game.squadrons import xplog

    pilot = SimpleNamespace(name="Lt Vega")
    log = xplog.XpLog(6)
    log.collected(
        pilot,
        "VFA-2",
        "F/A-18C",
        0,
        1000,
        [
            ("destroyed", "a whole SAM site", 2000),
            ("returned", "mission complete", 500),
            ("forfeit", "no more than one promotion a mission", -1500),
        ],
        "2ndLt -> 1stLt",
    )
    text = "\n".join(log._lines)
    assert "-1500  forfeit" in text
    assert "0 -> 1000 (+1000)" in text
