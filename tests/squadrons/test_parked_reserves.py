"""Aircraft caught on the ramp cost airframes, not aircrew.

Every reserve parked on the apron is given a stand-in flight, and that flight claims a
real pilot so the debriefing can account for the airframe. Nobody is sitting in one, so
an attack on the parking used to kill the whole reserve roster.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons.pilot import Pilot, PilotStatus


class _Squadron:
    owned_aircraft = 4
    destroyed_aircraft = 0
    player = SimpleNamespace(is_blue=True)

    def pilot_skill(self, pilot: Pilot) -> Any:
        return CADET_SKILL

    def leader_of(self, crew: Any) -> Any:
        """Everybody here holds the same rank, so it is the first man in the list."""
        return next((pilot for pilot in crew if pilot is not None), None)

    def pilot_rank(self, pilot: Pilot) -> Any:
        return None

    def __str__(self) -> str:
        return "Squadron 009"


def _commit(parked: bool) -> tuple[Pilot, _Squadron]:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.live_pilots_rank_survival = False
    settings.live_pilots_wounded_chance = 0
    settings.ignore_non_combat_air_losses = False

    pilot = Pilot("2ndLt David Johnson")
    squadron = _Squadron()
    flight = SimpleNamespace(
        squadron=squadron,
        unit_type="JF-17 Thunder",
        parked_reserve=parked,
        roster=SimpleNamespace(iter_pilots=lambda: []),
    )
    loss = SimpleNamespace(pilot=pilot, flight=flight)

    game = MagicMock()
    game.settings = settings
    debriefing: Any = SimpleNamespace(
        air_losses=SimpleNamespace(losses=[loss]),
        is_non_combat_loss=lambda _: False,
        pilot_outcomes=__import__(
            "game.squadrons.experience", fromlist=["PilotOutcomes"]
        ).PilotOutcomes(),
        kill_info_by_unit_id={},
        unit_map=SimpleNamespace(flight=lambda name: None),
    )
    MissionResultsProcessor(game).commit_air_losses(debriefing)
    return pilot, squadron


def test_the_ramp_costs_the_airframe_and_not_the_pilot() -> None:
    pilot, squadron = _commit(parked=True)
    assert pilot.status is PilotStatus.Active
    assert squadron.owned_aircraft == 3
    assert squadron.destroyed_aircraft == 1


def test_a_pilot_who_actually_flew_still_dies() -> None:
    pilot, squadron = _commit(parked=False)
    assert pilot.status is PilotStatus.Dead
    assert squadron.owned_aircraft == 3
