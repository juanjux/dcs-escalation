"""An invulnerable player still loses the aircraft.

"Invulnerable player pilots" is about his life. The rest of the debriefing reads
``lost_aircraft`` to decide who completed the mission, so skipping the whole branch
paid a player who was shot down the mission-complete award -- and being shot down
became the better outcome, which is the one thing Live Pilots II set out to stop.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.sim.missionresultsprocessor import MissionResultsProcessor


def _debriefing(loss: Any) -> Any:
    return SimpleNamespace(
        air_losses=SimpleNamespace(losses=[loss]),
        pilot_outcomes=SimpleNamespace(lost_aircraft=set()),
        is_non_combat_loss=lambda _loss: False,
    )


def _loss(player: bool) -> Any:
    pilot = SimpleNamespace(player=player, alive=True, name="El Jefe")
    squadron = SimpleNamespace(owned_aircraft=4, destroyed_aircraft=0, name="VMFA-251")
    flight = SimpleNamespace(
        squadron=squadron, unit_type="F/A-18C", parked_reserve=False
    )
    return SimpleNamespace(pilot=pilot, flight=flight)


def _processor(invulnerable: bool) -> Any:
    processor = MissionResultsProcessor.__new__(MissionResultsProcessor)
    processor.game = SimpleNamespace(  # type: ignore[assignment]
        settings=SimpleNamespace(
            ignore_non_combat_air_losses=False,
            invulnerable_player_pilots=invulnerable,
        )
    )
    return processor


def test_an_invulnerable_player_is_still_recorded_as_having_lost_the_aircraft() -> None:
    processor = _processor(invulnerable=True)
    loss = _loss(player=True)
    debriefing = _debriefing(loss)
    fates: list[Any] = []
    processor._resolve_pilot_fate = lambda *a: fates.append(a)

    processor.commit_air_losses(debriefing)

    assert id(loss.pilot) in debriefing.pilot_outcomes.lost_aircraft
    # And his life is still spared: the fate roll never runs for him.
    assert fates == []
    assert loss.flight.squadron.owned_aircraft == 3


def test_a_vulnerable_player_goes_through_the_ordinary_fate_roll() -> None:
    processor = _processor(invulnerable=False)
    loss = _loss(player=True)
    debriefing = _debriefing(loss)
    fates: list[Any] = []
    processor._resolve_pilot_fate = lambda *a: fates.append(a)

    processor.commit_air_losses(debriefing)

    assert len(fates) == 1


def test_an_ai_pilot_is_unaffected_by_the_setting() -> None:
    processor = _processor(invulnerable=True)
    loss = _loss(player=False)
    debriefing = _debriefing(loss)
    fates: list[Any] = []
    processor._resolve_pilot_fate = lambda *a: fates.append(a)

    processor.commit_air_losses(debriefing)

    assert len(fates) == 1
