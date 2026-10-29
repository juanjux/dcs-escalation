"""Confirmed victories lift surviving squadron mates without changing personal XP."""

import pickle
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from dcs.unit import Skill

from game.data.units import UnitClass
from game.dcs.shipunittype import ShipUnitType
from game.settings import Settings
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons import morale
from game.squadrons.experience import (
    PilotOutcomes,
    XP_AIR_KILL,
    XP_GROUND_KILL,
    XP_SHIP_KILL,
)
from game.squadrons.pilot import Pilot, PilotStatus
from game.theater.player import Player


@pytest.fixture
def battle() -> Any:
    settings = Settings()
    settings.live_pilots_enabled = settings.morale_enabled = True
    shooter, mate = Pilot("Shooter"), Pilot("Squadron mate")
    squadron = SimpleNamespace(
        player=Player.BLUE,
        current_roster=[shooter, mate],
        aircraft="F/A-18C",
        pilot_skill=lambda pilot: Skill.Good,
        pilot_rank=lambda pilot: None,
    )
    outsider = Pilot("Other squadron")
    other = SimpleNamespace(current_roster=[outsider])
    game: Any = SimpleNamespace(
        settings=settings,
        turn=3,
        blue=SimpleNamespace(
            air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron, other])
        ),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: [])),
    )
    processor = MissionResultsProcessor(game)
    processor._xp_log = Mock()
    flight = SimpleNamespace(squadron=squadron)
    flying = SimpleNamespace(pilot=shooter, flight=flight)

    def victim(kind: str = "air", owner: Player = Player.RED) -> Any:
        if kind == "air":
            return SimpleNamespace(
                flight=SimpleNamespace(
                    squadron=SimpleNamespace(player=owner),
                    unit_type=SimpleNamespace(display_name="Enemy aircraft"),
                )
            )
        if kind == "unresolved":
            return None
        unit_type = SimpleNamespace(
            display_name="Enemy tank", unit_class=UnitClass.TANK
        )
        if kind == "ship":
            unit_type = Mock(spec=ShipUnitType, display_name="Enemy ship")
        tgo = SimpleNamespace(
            name="Target",
            category="factory",
            control_point=SimpleNamespace(captured=owner),
        )
        return SimpleNamespace(
            theater_unit=SimpleNamespace(
                unit_type=None if kind == "building" else unit_type,
                ground_object=tgo,
            )
        )

    def debrief(
        targets: dict[str, Any], kills: list[dict[str, str]] | None = None
    ) -> Any:
        return SimpleNamespace(
            state_data=SimpleNamespace(
                kill_details=(
                    kills
                    if kills is not None
                    else [{"initiator": "shooter", "target": name} for name in targets]
                )
            ),
            unit_map=SimpleNamespace(
                flight=lambda name: flying if name == "shooter" else None
            ),
            resolve_killed_object=targets.get,
            pilot_outcomes=PilotOutcomes(),
        )

    return SimpleNamespace(
        settings=settings,
        shooter=shooter,
        mate=mate,
        outsider=outsider,
        squadron=squadron,
        game=game,
        processor=processor,
        flight=flight,
        flying=flying,
        victim=victim,
        debrief=debrief,
    )


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize(
    "kind,event,xp",
    [
        ("air", morale.SQUADRON_AIR_KILL, XP_AIR_KILL),
        ("ground", morale.SQUADRON_GROUND_KILL, XP_GROUND_KILL),
        ("ship", morale.SQUADRON_GROUND_KILL, XP_SHIP_KILL),
        ("building", morale.SQUADRON_GROUND_KILL, None),
    ],
)
def test_victory_reaches_only_squadron_mates_and_preserves_personal_awards(
    battle: Any, side: Player, kind: str, event: Any, xp: int | None
) -> None:
    b = battle
    b.squadron.player = side
    earned, credited = b.processor._experience_from_kills(
        b.debrief({"target": b.victim(kind, side.opponent)})
    )
    assert b.processor._morale_events[id(b.mate)] == [event]
    assert id(b.outsider) not in b.processor._morale_events
    assert event not in b.processor._morale_events.get(id(b.shooter), [])
    assert set(earned) == {id(b.shooter)}
    if xp is not None:
        assert earned[id(b.shooter)] == xp
    assert credited == {(id(b.shooter), "target")}
    if kind == "air":
        assert b.processor._morale_events[id(b.shooter)] == [morale.AIR_KILL]


@pytest.mark.parametrize(
    "status", [PilotStatus.Active, PilotStatus.OnLeave, PilotStatus.Wounded]
)
def test_non_flying_mates_also_receive_the_bonus(
    battle: Any, status: PilotStatus
) -> None:
    b = battle
    b.mate.status = status
    b.processor._experience_from_kills(b.debrief({"target": b.victim()}))
    assert b.processor._morale_events[id(b.mate)] == [morale.SQUADRON_AIR_KILL]


@pytest.mark.parametrize(
    "status", [PilotStatus.Dead, PilotStatus.Deserted, PilotStatus.Discharged]
)
def test_departed_pilots_do_not_receive_shared_morale(
    battle: Any, status: PilotStatus
) -> None:
    b = battle
    b.mate.status = status
    b.processor._experience_from_kills(b.debrief({"target": b.victim()}))
    assert id(b.mate) not in b.processor._morale_events


def test_player_victories_help_mates_but_player_has_no_morale(battle: Any) -> None:
    b = battle
    b.shooter.player = True
    b.processor._experience_from_kills(b.debrief({"target": b.victim()}))
    assert b.processor._morale_events[id(b.mate)] == [morale.SQUADRON_AIR_KILL]
    b.processor._morale_events.clear()
    b.mate.player = True
    b.processor._experience_from_kills(b.debrief({"target": b.victim()}))
    assert id(b.mate) not in b.processor._morale_events


@pytest.mark.parametrize(
    "setting", ["live_pilots_enabled", "morale_enabled", "morale_squadron_air_kill"]
)
def test_bonus_can_be_disabled_without_changing_personal_credit(
    battle: Any, setting: str
) -> None:
    b = battle
    setattr(b.settings, setting, 0 if setting.endswith("air_kill") else False)
    earned, _ = b.processor._experience_from_kills(b.debrief({"target": b.victim()}))
    assert id(b.mate) not in b.processor._morale_events
    assert earned == {id(b.shooter): XP_AIR_KILL}


@pytest.mark.parametrize("kind", ["air", "ground", "building"])
@pytest.mark.parametrize("owner", [Player.BLUE, Player.NEUTRAL])
def test_friendly_and_neutral_targets_give_no_shared_morale(
    battle: Any, kind: str, owner: Player
) -> None:
    b = battle
    b.processor._note_friendly_fire_event = Mock()
    b.processor._experience_from_kills(b.debrief({"target": b.victim(kind, owner)}))
    assert id(b.mate) not in b.processor._morale_events


def test_duplicates_are_counted_once_but_distinct_targets_stack(battle: Any) -> None:
    b = battle
    kills = [
        {"initiator": "shooter", "target": target}
        for target in ("one", "one", "two", "two")
    ]
    b.processor._experience_from_kills(
        b.debrief({"one": b.victim(), "two": b.victim()}, kills)
    )
    assert b.processor._morale_events[id(b.mate)] == [morale.SQUADRON_AIR_KILL] * 2


def test_unknown_targets_or_non_pilot_killers_give_no_shared_morale(
    battle: Any,
) -> None:
    b = battle
    b.processor._experience_from_kills(b.debrief({"target": None}))
    b.processor._experience_from_kills(
        b.debrief({"target": b.victim()}, [{"initiator": "SAM", "target": "target"}])
    )
    assert id(b.mate) not in b.processor._morale_events


def test_shared_gains_use_settings_and_reach_pilot_history_and_debrief(
    battle: Any,
) -> None:
    b = battle
    b.settings.morale_squadron_air_kill = 4
    b.settings.morale_squadron_ground_kill = 3
    b.mate.morale = 14
    b.shooter.morale = 50
    debrief = b.debrief({"air": b.victim(), "ground": b.victim("ground")})
    b.processor._experience_from_kills(debrief)
    assert b.mate.morale == 14  # XP is calculated before morale is committed.
    b.processor._commit_morale(debrief)
    assert b.mate.morale == 21
    assert [(e.reason, e.amount) for e in b.mate.morale_log] == [
        (morale.SQUADRON_AIR_KILL.reason, 4),
        (morale.SQUADRON_GROUND_KILL.reason, 3),
    ]
    [shift] = [
        s for s in debrief.pilot_outcomes.morale_shifts if s.pilot_name == b.mate.name
    ]
    assert sum(shift.amounts.values()) == 7


def test_new_settings_have_defaults_in_old_saves_and_keep_saved_overrides() -> None:
    restored = Settings.__new__(Settings)
    restored.__setstate__({"morale_air_kill": 23})
    assert restored.morale_squadron_air_kill == 2
    assert restored.morale_squadron_ground_kill == 1
    restored.morale_squadron_air_kill = 0
    restored.morale_squadron_ground_kill = 5
    copied = pickle.loads(pickle.dumps(restored))
    assert (
        copied.morale_squadron_air_kill == 0 and copied.morale_squadron_ground_kill == 5
    )
    assert copied.morale_air_kill == 23
