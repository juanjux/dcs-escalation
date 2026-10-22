"""Losing a remotely operated aircraft never creates an aircrew casualty."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from game import persistency
from game.ato import FlightType
from game.dcs.aircrafttype import AircraftType
from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.sim import missionresultsprocessor
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons.experience import PilotOutcomes, XP_GROUND_KILL
from game.squadrons.pilot import Pilot, PilotStatus


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), False, 0)


def scenario(variant: str, *, live: bool, wounded: int, blue: bool) -> Any:
    settings = Settings()
    settings.live_pilots_enabled = live
    settings.live_pilots_rank_survival = False
    settings.live_pilots_wounded_chance = wounded
    settings.ignore_non_combat_air_losses = False
    settings.morale_enabled = False
    settings.friendship_enabled = False
    pilot = Pilot("Remote operator")
    aircraft = AircraftType.named(variant)
    squadron = SimpleNamespace(
        player=SimpleNamespace(is_blue=blue),
        aircraft=aircraft,
        owned_aircraft=2,
        destroyed_aircraft=0,
        base_skill=CADET_SKILL,
        pilot_rank=lambda _: None,
        pilot_skill=lambda _: CADET_SKILL,
        leader_of=lambda crew: next(iter(crew), None),
    )
    flight = SimpleNamespace(
        squadron=squadron,
        unit_type=aircraft,
        flight_type=FlightType.CAS,
        parked_reserve=False,
        roster=SimpleNamespace(iter_pilots=lambda: [pilot]),
    )
    loss = SimpleNamespace(flight=flight, pilot=pilot)
    debriefing = SimpleNamespace(
        air_losses=SimpleNamespace(losses=[loss]),
        is_non_combat_loss=lambda _: False,
        pilot_outcomes=PilotOutcomes(),
        kill_info_by_unit_id={},
        unit_map=SimpleNamespace(flight=lambda _: None),
    )
    game = MagicMock(settings=settings, turn=2)
    return SimpleNamespace(
        processor=MissionResultsProcessor(game),
        debriefing=debriefing,
        pilot=pilot,
        squadron=squadron,
        flight=flight,
        settings=settings,
    )


@pytest.mark.parametrize(
    "variant", ["MQ-9 Reaper", "RQ-1A Predator", "WingLoong-I", "[CH] TB-2 UCAV"]
)
@pytest.mark.parametrize("live,wounded", [(False, 0), (True, 0), (True, 100)])
@pytest.mark.parametrize("blue", [False, True])
@pytest.mark.parametrize("rank_survival", [False, True])
def test_remote_operator_is_not_subject_to_casualty_rolls(
    variant: str,
    live: bool,
    wounded: int,
    blue: bool,
    rank_survival: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = scenario(variant, live=live, wounded=wounded, blue=blue)
    s.settings.live_pilots_rank_survival = rank_survival
    monkeypatch.setattr(
        missionresultsprocessor.random,
        "random",
        lambda: pytest.fail("Remote operators must not roll for survival"),
    )
    s.processor.commit_air_losses(s.debriefing)
    outcomes = s.debriefing.pilot_outcomes
    assert s.pilot.status is PilotStatus.Active
    assert s.pilot.record.aircraft_lost == 1
    assert s.squadron.owned_aircraft == 1
    assert s.squadron.destroyed_aircraft == 1
    assert outcomes.lost_aircraft == {id(s.pilot)}
    assert not outcomes.deaths and not outcomes.wounded and not outcomes.survivors
    assert s.pilot.record.survived_losses == 0
    assert s.pilot.record.wounds == 0 and s.pilot.hardened == 0
    assert not s.processor._dead_this_turn and not s.processor._wounded_this_turn


@pytest.mark.parametrize("live", [False, True])
def test_operator_keeps_earned_xp_but_not_mission_completion_after_a_loss(
    live: bool,
) -> None:
    s = scenario("MQ-9 Reaper", live=live, wounded=100, blue=True)
    s.processor.commit_air_losses(s.debriefing)
    ato: Any = SimpleNamespace(packages=[SimpleNamespace(flights=[s.flight])])
    s.processor._commit_pilot_experience(
        ato, s.debriefing, {id(s.pilot): XP_GROUND_KILL}
    )
    assert s.pilot.record.xp == XP_GROUND_KILL
    assert s.pilot.record.missions_flown == 1
    assert s.pilot.record.missions_completed == 0


def test_ignored_noncombat_drone_losses_do_not_remove_an_airframe() -> None:
    s = scenario("WingLoong-I", live=True, wounded=0, blue=False)
    s.settings.ignore_non_combat_air_losses = True
    s.debriefing.is_non_combat_loss = lambda _: True
    s.processor.commit_air_losses(s.debriefing)
    assert s.squadron.owned_aircraft == 2
    assert s.squadron.destroyed_aircraft == 0
    assert s.pilot.record.aircraft_lost == 0
    assert not s.debriefing.pilot_outcomes.lost_aircraft


def test_parked_drone_is_not_an_operator_sortie_loss() -> None:
    s = scenario("RQ-1A Predator", live=True, wounded=0, blue=True)
    s.flight.parked_reserve = True
    s.processor.commit_air_losses(s.debriefing)
    assert s.squadron.owned_aircraft == 1
    assert s.pilot.record.aircraft_lost == 0
    assert not s.debriefing.pilot_outcomes.lost_aircraft


def test_manned_afac_aircraft_are_not_protected() -> None:
    s = scenario("OH-58D(R) Kiowa Warrior", live=False, wounded=0, blue=True)
    s.processor.commit_air_losses(s.debriefing)
    assert s.pilot.status is PilotStatus.Dead
    assert len(s.debriefing.pilot_outcomes.deaths) == 1
