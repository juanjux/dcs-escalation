"""Damaged returns affect morale only, using confirmed recovery telemetry."""

from types import SimpleNamespace
from typing import Any

import pytest

from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons import morale
from game.squadrons.experience import PilotOutcomes
from game.squadrons.pilot import Pilot
from tests.test_aircraftmaintenance import world, _debrief


@pytest.mark.parametrize("workshops", [False, True])
def test_confirmed_return_gets_one_penalty_without_changing_pilot_fate(
    world: Any, workshops: bool
) -> None:
    world.game.settings.live_pilots_enabled = world.game.settings.morale_enabled = True
    world.game.settings.aircraft_maintenance_enabled = workshops
    debrief = _debrief(world, {"health": 0.7, "recovered": True, "x": 10, "z": 0})
    pilot = Pilot("Returned pilot")
    debrief.unit_map.flight("unit").pilot = pilot
    debrief.pilot_outcomes = PilotOutcomes()
    debrief.state_data.aircraft_damage["duplicate unit report"] = (
        debrief.state_data.aircraft_damage["unit"]
    )
    processor = MissionResultsProcessor(world.game)
    processor._note_damaged_return_morale(debrief)
    assert processor._morale_events == {id(pilot): [morale.DAMAGED_RETURN]}
    assert pilot.alive and not pilot.wounded and pilot.morale == morale.MORALE_START
    assert debrief.pilot_outcomes == PilotOutcomes()
    assert world.sq.owned_aircraft == 6
    assert morale.DAMAGED_RETURN.amount(world.game.settings) == -3
    world.game.settings.morale_damaged_return = -7
    assert morale.DAMAGED_RETURN.amount(world.game.settings) == -7


@pytest.mark.parametrize(
    "entry",
    [
        {"health": 1, "recovered": True, "x": 10, "z": 0},
        {"health": 0.7, "recovered": False, "x": 10, "z": 0},
        {"health": 0.7, "recovered": True, "x": 9990, "z": 0},
        {"health": 0.7, "recovered": True},
        {"health": 0.7, "recovered": True, "x": 10, "z": 0, "ejected": True},
        {"health": 0.7, "recovered": True, "x": 10, "z": 0, "killed": True},
    ],
)
def test_not_a_confirmed_friendly_return_has_no_penalty(
    world: Any, entry: dict[str, Any]
) -> None:
    world.game.settings.live_pilots_enabled = world.game.settings.morale_enabled = True
    debrief = _debrief(world, entry)
    debrief.unit_map.flight("unit").pilot = Pilot("Pilot")
    debrief.pilot_outcomes = PilotOutcomes()
    processor = MissionResultsProcessor(world.game)
    processor._note_damaged_return_morale(debrief)
    assert processor._morale_events == {}


@pytest.mark.parametrize(
    "setting,value",
    [
        ("live_pilots_enabled", False),
        ("morale_enabled", False),
        ("morale_damaged_return", 0),
    ],
)
def test_disabled_penalty_does_not_require_telemetry(
    world: Any, setting: str, value: Any
) -> None:
    world.game.settings.live_pilots_enabled = world.game.settings.morale_enabled = True
    setattr(world.game.settings, setting, value)
    processor = MissionResultsProcessor(world.game)
    empty: Any = SimpleNamespace()
    processor._note_damaged_return_morale(empty)
    assert processor._morale_events == {}
