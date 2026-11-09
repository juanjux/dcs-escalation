"""Confirmed collisions remain non-combat losses even when a pilot ejects."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from game.ato.starttype import StartType
from game.debriefing import Debriefing
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.theater.player import Player


def _collision(target: str, initiator: str) -> dict[str, str]:
    return {
        "target": target,
        "initiator": initiator,
        "initiator_type": "FA-18C_hornet",
        "weapon": "FA-18C_hornet",
    }


def _weapon_kill(target: str) -> dict[str, str]:
    return {
        "target": target,
        "initiator": "Enemy fighter",
        "initiator_type": "JF-17",
        "weapon": "SD-10",
    }


def _world(
    raw: dict[str, Any],
    side: Player = Player.BLUE,
    ignore_crashes: bool = True,
) -> Any:
    squadron = SimpleNamespace(owned_aircraft=8, destroyed_aircraft=0, player=side)
    flight = SimpleNamespace(
        departure=SimpleNamespace(captured=side),
        start_type=StartType.IN_FLIGHT,
        squadron=squadron,
        unit_type="F/A-18C",
    )
    losses = {
        name: SimpleNamespace(
            flight=flight,
            pilot=SimpleNamespace(name=name, player=False, alive=True),
        )
        for name in raw["unit_lost_events"]
    }
    game = SimpleNamespace(
        blue=SimpleNamespace(
            faction=SimpleNamespace(country=SimpleNamespace(name="USA"))
        ),
        red=SimpleNamespace(
            faction=SimpleNamespace(country=SimpleNamespace(name="China"))
        ),
        settings=SimpleNamespace(
            ignore_non_combat_air_losses=ignore_crashes,
            invulnerable_player_pilots=False,
        ),
    )
    mapping = SimpleNamespace(flight=losses.get, airlift_unit=lambda name: None)
    debriefing = Debriefing(raw, game, mapping)  # type: ignore[arg-type]
    processor: Any = MissionResultsProcessor.__new__(MissionResultsProcessor)
    processor.game = game
    processor._resolve_pilot_fate = Mock()
    return SimpleNamespace(
        debriefing=debriefing,
        processor=processor,
        squadron=squadron,
        losses=losses,
        side=side,
    )


def _pair(ejected: str | None = "Lead") -> dict[str, Any]:
    return {
        "unit_lost_events": ["Lead", "Wingman"],
        "crash_events": ["Lead", "Wingman"],
        "kill_events": ["Wingman", "Lead"],
        "kill_details": [_collision("Wingman", "Lead"), _collision("Lead", "Wingman")],
        "death_time": {"Lead": 362.18, "Wingman": 361.16},
        "aircraft_damage_state": [
            {"unit": "Lead", "ejected": ejected == "Lead", "crash_time": 362.18},
            {"unit": "Wingman", "ejected": ejected == "Wingman", "crash_time": 361.16},
        ],
    }


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("ejected", [None, "Lead", "Wingman"])
@pytest.mark.parametrize("ignore_crashes", [False, True])
def test_both_collision_losses_obey_the_crash_setting(
    side: Player, ejected: str | None, ignore_crashes: bool
) -> None:
    world = _world(_pair(ejected), side, ignore_crashes)
    debriefing = world.debriefing

    assert all(debriefing.is_non_combat_loss(loss) for loss in world.losses.values())
    assert not any(debriefing.is_indirect_kill(loss) for loss in world.losses.values())
    assert debriefing.loss_counts(side).aircraft == (0 if ignore_crashes else 2)

    world.processor.commit_air_losses(debriefing)

    assert world.squadron.owned_aircraft == (8 if ignore_crashes else 6)
    assert world.squadron.destroyed_aircraft == (0 if ignore_crashes else 2)
    assert world.processor._resolve_pilot_fate.call_count == (
        0 if ignore_crashes else 2
    )


def test_collision_without_optional_damage_telemetry_remains_ignored() -> None:
    raw = _pair()
    del raw["aircraft_damage_state"]
    world = _world(raw)
    assert all(
        world.debriefing.is_non_combat_loss(loss) for loss in world.losses.values()
    )
    world.processor.commit_air_losses(world.debriefing)
    assert world.squadron.owned_aircraft == 8


@pytest.mark.parametrize("reverse", [False, True])
def test_a_nearby_combat_loss_does_not_reclassify_confirmed_collisions(
    reverse: bool,
) -> None:
    raw = _pair()
    raw["unit_lost_events"].append("Combat casualty")
    raw["kill_details"].append(_weapon_kill("Combat casualty"))
    raw["death_time"]["Combat casualty"] = 361.5
    if reverse:
        raw["unit_lost_events"].reverse()
        raw["kill_details"].reverse()
    world = _world(raw)
    debriefing = world.debriefing

    for name in ("Lead", "Wingman"):
        assert debriefing.is_non_combat_loss(world.losses[name])
        assert not debriefing.is_indirect_kill(world.losses[name])
    assert not debriefing.is_non_combat_loss(world.losses["Combat casualty"])
    world.processor.commit_air_losses(debriefing)
    assert world.squadron.owned_aircraft == 7


@pytest.mark.parametrize("collision_first", [False, True])
def test_a_confirmed_weapon_kill_is_not_erased_by_a_later_collision(
    collision_first: bool,
) -> None:
    raw = _pair()
    combat = _weapon_kill("Lead")
    raw["kill_details"].insert(
        0 if not collision_first else len(raw["kill_details"]), combat
    )
    world = _world(raw)

    assert not world.debriefing.is_non_combat_loss(world.losses["Lead"])
    assert world.debriefing.is_non_combat_loss(world.losses["Wingman"])
    world.processor.commit_air_losses(world.debriefing)
    assert world.squadron.owned_aircraft == 7


@pytest.mark.parametrize("terminal", ["ejected", "killed"])
def test_ejection_or_kill_without_collision_evidence_still_counts(
    terminal: str,
) -> None:
    raw = {
        "unit_lost_events": ["Lead"],
        "aircraft_damage_state": [{"unit": "Lead", terminal: True}],
    }
    world = _world(raw)
    assert not world.debriefing.is_non_combat_loss(world.losses["Lead"])
    world.processor.commit_air_losses(world.debriefing)
    assert world.squadron.owned_aircraft == 7


def test_unattributed_loss_near_a_real_kill_remains_an_indirect_combat_loss() -> None:
    raw = {
        "unit_lost_events": ["Lead", "Wingman"],
        "kill_details": [_weapon_kill("Lead")],
        "death_time": {"Lead": 361.16, "Wingman": 362.18},
    }
    world = _world(raw)
    assert not world.debriefing.is_non_combat_loss(world.losses["Wingman"])
    assert world.debriefing.is_indirect_kill(world.losses["Wingman"])


def test_simulated_combat_loss_is_not_refunded_as_a_collision() -> None:
    world = _world(_pair())
    world.debriefing._sim_loss_ids.add(id(world.losses["Lead"]))
    assert not world.debriefing.is_non_combat_loss(world.losses["Lead"])
