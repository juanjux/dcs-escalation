"""The three per-type breakdowns the planner reads out of prev_turns.

Each is an aggregate keyed by type, which is the whole point: they answer "what died"
and "what killed it" without carrying one entry per event.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import NamedTuple
from typing import Any

import pytest

from game.agent.views import TurnForcesView


def _summary(game: Any, debriefing: Any) -> dict[str, Any]:
    """Run the real per-turn recorder over doubles and hand back what it stored."""
    from game.game import Game

    Game.record_debrief(game, debriefing)
    return game.debrief_history[-1]


class _Type(NamedTuple):
    """Stands in for AircraftType, which is used as a dict key so must be hashable."""

    name: str


class _Loss:
    def __init__(self, unit_type_name: str) -> None:
        self.flight = SimpleNamespace(unit_type=_Type(unit_type_name))


@pytest.fixture
def debriefing() -> Any:
    """Two red Su-57 downed by an F-16C and an F-15EX, one blue F-16C downed by a MiG."""
    su57_a, su57_b = _Loss("Su-57"), _Loss("Su-57")
    viper = _Loss("F-16C_50")
    return SimpleNamespace(
        air_losses=SimpleNamespace(
            enemy=[su57_a, su57_b],
            player=[viper],
            by_type=lambda player: (
                {_Type("Su-57"): 2} if player.is_red else {_Type("F-16C_50"): 1}
            ),
        ),
        kill_info_by_unit_id={
            id(su57_a): {"initiator_type": "F-16C_50", "weapon": "AIM-120C"},
            id(su57_b): {"initiator_type": "F15EX", "weapon": "AIM-260"},
            id(viper): {"initiator_type": "MiG-31", "weapon": "R-37M"},
        },
        is_non_combat_loss=lambda unit: False,
        front_line_losses_by_type=lambda player: {},
        ground_object_losses_by_type=lambda player: {},
    )


def test_what_died_is_broken_down_by_airframe(debriefing: Any) -> None:
    game = SimpleNamespace(turn=4, debrief_history=[])
    summary = _summary(game, debriefing)
    assert summary["red_air_lost_by_type"] == {"Su-57": 2}
    assert summary["blue_air_lost_by_type"] == {"F-16C_50": 1}


def test_airframe_writeoffs_count_as_losses_without_inventing_a_killer(
    debriefing: Any,
) -> None:
    from game.aircraftmaintenance import AircraftWriteoff
    from game.theater import Player

    debriefing.aircraft_writeoffs = [
        AircraftWriteoff("unit", "F-16C_50", 20, Player.BLUE, "hostile landing"),
        AircraftWriteoff("unit2", "Su-25", 12, Player.RED, "hostile landing"),
    ]
    game = SimpleNamespace(turn=4, debrief_history=[])
    summary = _summary(game, debriefing)
    assert summary["blue_air_lost"] == 2
    assert summary["red_air_lost"] == 3
    assert summary["blue_air_lost_by_type"] == {"F-16C_50": 2}
    assert summary["red_air_lost_by_type"] == {"Su-57": 2, "Su-25": 1}
    assert summary["blue_air_crashed"] == summary["red_air_crashed"] == 0
    assert summary["red_air_kills_by_weapon"] == {"R-37M": 1}
    assert summary["blue_air_kills_by_weapon"] == {"AIM-120C": 1, "AIM-260": 1}


def test_kills_by_weapon_never_falls_back_to_the_shooter(debriefing: Any) -> None:
    """The whole reason this exists next to *_air_killers: a loadout cannot be judged
    from a dict whose values might be airframes."""
    game = SimpleNamespace(turn=4, debrief_history=[])
    summary = _summary(game, debriefing)
    # A side's kills are read off the OTHER side's losses, so red's are red's own
    # missiles. Reversed, a planner asking which of its weapons work is handed the
    # enemy's -- which is what happened, and what a live OPFOR run reported.
    assert summary["red_air_kills_by_weapon"] == {"R-37M": 1}
    assert summary["blue_air_kills_by_weapon"] == {"AIM-120C": 1, "AIM-260": 1}


def test_the_matchup_table_nests_victim_then_killer(debriefing: Any) -> None:
    game = SimpleNamespace(turn=4, debrief_history=[])
    summary = _summary(game, debriefing)
    # Red killed a blue F-16C with a MiG-31: victim first, then who killed it.
    assert summary["red_air_kills_by_victim"] == {"F-16C_50": {"MiG-31": 1}}


def test_a_loss_with_no_credited_shooter_is_left_out_of_the_matchup() -> None:
    """A crash has no killer, and inventing one would misread as a lost dogfight."""
    crashed = _Loss("Su-25")
    debriefing = SimpleNamespace(
        air_losses=SimpleNamespace(
            enemy=[crashed], player=[], by_type=lambda player: {}
        ),
        kill_info_by_unit_id={},
        is_non_combat_loss=lambda unit: True,
        front_line_losses_by_type=lambda player: {},
        ground_object_losses_by_type=lambda player: {},
    )
    game = SimpleNamespace(turn=4, debrief_history=[])
    summary = _summary(game, debriefing)
    assert summary["red_air_kills_by_victim"] == {}
    assert summary["red_air_kills_by_weapon"] == {}


def test_the_dto_carries_all_three(debriefing: Any) -> None:
    """A field the DTO drops is a field the planner never sees."""
    view = TurnForcesView(
        turn=4,
        blue_aircraft=10,
        blue_vehicles=20,
        red_aircraft=30,
        red_vehicles=40,
        red_air_lost_by_type={"Su-57": 2},
        red_air_kills_by_weapon={"R-37M": 1},
        red_air_kills_by_victim={"F-16C_50": {"MiG-31": 1}},
    )
    dumped = view.model_dump(exclude_none=True)
    assert dumped["red_air_lost_by_type"] == {"Su-57": 2}
    assert dumped["red_air_kills_by_weapon"] == {"R-37M": 1}
    assert dumped["red_air_kills_by_victim"] == {"F-16C_50": {"MiG-31": 1}}
