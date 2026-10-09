"""New owners get one full turn to reinforce a captured base."""

import pickle
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from dcs import Mission, Point
from dcs.lua import loads
from dcs.terrain import Caucasus

from game.debriefing import Debriefing
from game.missiongenerator.triggergenerator import TriggerGenerator
from game.sim.gameupdateevents import GameUpdateEvents
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.theater.controlpoint import Airfield, ControlPoint, Fob, Player
from game.transfers import TransferOrder


def _base(owner: Player = Player.BLUE) -> Fob:
    cp = Fob("Test Base", Point(0, 0, Caucasus()), cast(Any, None), owner)
    cp._coalition = cast(Any, SimpleNamespace(player=owner))
    return cp


def _debrief(cp: ControlPoint, turn: int, owners: list[Player]) -> Debriefing:
    result = Debriefing.__new__(Debriefing)
    result.game = cast(
        Any,
        SimpleNamespace(
            turn=turn,
            theater=SimpleNamespace(find_control_point_by_id=lambda _: cp),
        ),
    )
    result.state_data = cast(
        Any,
        SimpleNamespace(
            base_capture_events=[
                f"{cp.id}||{2 if owner.is_blue else 1}||{cp.full_name}"
                for owner in owners
            ]
        ),
    )
    return result


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("offset,protected", [(0, True), (1, True), (2, False)])
def test_capture_records_turn_and_grace_expires(
    owner: Player, offset: int, protected: bool, monkeypatch: Any
) -> None:
    cp = _base(owner.opponent)
    game = MagicMock(turn=5)
    game.coalition_for.return_value = SimpleNamespace(player=owner)
    for method in (
        "retreat_ground_units",
        "retreat_air_units",
        "_clear_front_lines",
        "_create_missing_front_lines",
    ):
        monkeypatch.setattr(cp, method, MagicMock())
    monkeypatch.setattr(
        "game.missiongenerator.motorpoolpopulator.MotorpoolPopulator._rehome_motorpools",
        MagicMock(),
    )

    cp.capture(game, GameUpdateEvents(), owner)

    assert cp.captured == owner
    assert cp.last_capture_turn == 5
    assert cp.is_capture_protected(5 + offset) is protected
    assert cp.base.total_armor == 0  # protection does not grant a free garrison


@pytest.mark.parametrize("legacy", [False, True])
def test_uncaptured_and_legacy_bases_are_not_protected(legacy: bool) -> None:
    cp = _base()
    if legacy:
        del cp.last_capture_turn
    for turn in (0, 1, 5, 6):
        assert not cp.is_capture_protected(turn)


def test_capture_timestamp_survives_save_reload() -> None:
    cp = Fob.__new__(Fob)
    cp.last_capture_turn = 5
    restored = pickle.loads(pickle.dumps(cp))
    assert restored.is_capture_protected(6)
    assert not restored.is_capture_protected(7)


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("turn,expected", [(6, 0), (7, 1)])
def test_debrief_rejects_protected_captures_before_processing_losses(
    owner: Player, turn: int, expected: int
) -> None:
    cp = _base(owner)
    cp.last_capture_turn = 5
    debrief = _debrief(cp, turn, [owner.opponent])
    assert len(debrief.base_capture_events()) == expected
    assert cp.captured == owner
    assert cp.last_capture_turn == 5  # rejected attempts do not extend protection


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_first_capture_and_same_mission_reversal_are_unchanged(owner: Player) -> None:
    cp = _base(owner)
    assert len(_debrief(cp, 5, [owner.opponent]).base_capture_events()) == 1
    assert _debrief(cp, 5, [owner.opponent, owner]).base_capture_events() == []


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED, Player.NEUTRAL])
@pytest.mark.parametrize("cp_type", [Fob, Airfield])
@pytest.mark.parametrize("turn", [6, 7])
def test_generated_mission_omits_protected_capture_triggers(
    owner: Player, cp_type: type[ControlPoint], turn: int
) -> None:
    # Use the same base state with each capture-zone class, without needing an
    # airport database; only identity, position and ownership are read here.
    cp = cp_type.__new__(cp_type)
    cp.__dict__.update(_base(owner).__dict__)
    cp.last_capture_turn = 5 if not owner.is_neutral else None
    game = SimpleNamespace(turn=turn, theater=SimpleNamespace(controlpoints=[cp]))
    mission = Mission(Caucasus())

    TriggerGenerator(mission, cast(Any, game))._generate_capture_triggers()

    count = 4 if owner.is_neutral else (0 if turn == 6 else 2)
    assert len(mission.triggerrules.triggers) == count
    assert len(mission.triggers.zones()) == (1 if count else 0)


def test_protected_base_can_receive_purchases_and_transfers(monkeypatch: Any) -> None:
    cp = _base()
    cp.last_capture_turn = 5
    unit = MagicMock()
    game = MagicMock(turn=6)
    events = GameUpdateEvents()
    monkeypatch.setattr(cp.ground_unit_orders, "find_ground_unit_source", lambda _: cp)

    cp.ground_unit_orders.order({unit: 2})
    cp.ground_unit_orders.process(game, datetime(2026, 1, 1), events)
    transfer = TransferOrder(_base(), cp, {unit: 3}, player=Player.BLUE)
    transfer.transport = cast(Any, SimpleNamespace(destination=cp))
    transfer.proceed()

    assert cp.base.total_armor == 5
    assert cp.is_capture_protected(6)
    assert not cp.is_capture_protected(7)
    assert transfer.completed


@pytest.mark.parametrize("turn,expected", [(6, 0), (7, 2)])
def test_exported_miz_resumes_capture_after_grace(
    tmp_path: Path, turn: int, expected: int
) -> None:
    cp = _base()
    cp.last_capture_turn = 5
    game = SimpleNamespace(turn=turn, theater=SimpleNamespace(controlpoints=[cp]))
    mission = Mission(Caucasus())
    TriggerGenerator(mission, cast(Any, game))._generate_capture_triggers()
    path = tmp_path / f"capture-turn-{turn}.miz"
    mission.save(str(path))

    with ZipFile(path) as archive:
        exported = loads(archive.read("mission").decode("utf-8"))["mission"]
    assert len(exported["trigrules"]) == expected


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize(
    "captured_turn,turn,defenders,expected",
    [
        (5, 6, 0, True),
        (5, 6, 2, False),
        (5, 7, 0, False),
        (5, 5, 0, False),
        (None, 6, 0, False),
    ],
)
def test_event_log_explains_empty_base_protection_without_capture_events(
    owner: Player,
    captured_turn: int | None,
    turn: int,
    defenders: int,
    expected: bool,
) -> None:
    cp = _base(owner)
    cp.last_capture_turn = captured_turn
    if defenders:
        cp.base.commission_units({MagicMock(): defenders})
    game = MagicMock(turn=turn)
    game.theater.controlpoints = [cp]
    processor = MissionResultsProcessor(game)

    processor.commit_captures(
        cast(Any, SimpleNamespace(base_captures=[])), GameUpdateEvents()
    )

    if expected:
        game.message.assert_called_once()
        title, text = game.message.call_args.args
        assert cp.name in title
        assert "was not recaptured despite having no ground forces" in text
        assert "first-turn protection" in text
        assert "expires next turn" in text
    else:
        game.message.assert_not_called()
    assert cp.captured == owner
