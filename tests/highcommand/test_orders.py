"""The objectives the High Command orders taken."""

from __future__ import annotations

import logging
import pickle
import random
from types import SimpleNamespace
from typing import Any

import pytest

from game.game import Game, TurnState
from game.highcommand import objectives as listing
from game.highcommand.campaign import Task
from game.highcommand.objectives import Effort, Objective
from game.highcommand.orders import (
    HighCommand,
    Order,
    Outcome,
    _order,
    tiers,
)
from game.highcommand.prizes import Prize
from game.theater.player import Player
from tests.highcommand.stubs import Base, motorpool


def _objective(name: str, score: int) -> Objective:
    difficulty = min(5, score - 1)
    return Objective(
        name=name,
        kind="Factory",
        targets=(),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        difficulty=difficulty,
        importance=score - difficulty,
        justification=f"{name} earns.",
        prize=Prize("cash", score, False, f"Cash for {name}."),
    )


#: Three low, three middling and three high, by score.
BOARD = [
    _objective(name, score)
    for name, score in (
        ("L1", 2),
        ("L2", 3),
        ("L3", 3),
        ("M1", 5),
        ("M2", 6),
        ("M3", 6),
        ("H1", 8),
        ("H2", 9),
        ("H3", 10),
    )
]


ENEMY_BASE = SimpleNamespace(captured=Player.RED)


def _settings(orders: int = 3, shortest: int = 2, longest: int = 5) -> Any:
    return SimpleNamespace(
        high_command_enabled=True,
        high_command_orders=orders,
        high_command_shortest_order=shortest,
        high_command_longest_order=longest,
    )


def _game(
    turn: int,
    dead: tuple[str, ...] = (),
    bases: tuple[Any, ...] = (),
    ground_objects: tuple[Any, ...] = (),
    settings: Any = None,
) -> Any:
    return SimpleNamespace(
        turn=turn,
        settings=settings or _settings(),
        theater=SimpleNamespace(
            ground_objects=[
                SimpleNamespace(name=name, is_dead=True, control_point=ENEMY_BASE)
                for name in dead
            ]
            + list(ground_objects),
            controlpoints=list(bases),
        ),
    )


@pytest.fixture
def board(monkeypatch: pytest.MonkeyPatch) -> list[Objective]:
    standing = list(BOARD)
    monkeypatch.setattr(listing, "enemy_objectives", lambda game: list(standing))
    return standing


def test_the_objectives_split_into_tiers_of_score() -> None:
    split = tiers(BOARD, 3)

    assert [[o.name for o in tier] for tier in split] == [
        ["L1", "L2", "L3"],
        ["M1", "M2", "M3"],
        ["H1", "H2", "H3"],
    ]
    assert [len(tier) for tier in tiers(BOARD[:8], 3)] == [2, 3, 3]


def test_one_order_for_each_tier_with_its_prize_and_a_lifetime(
    board: list[Objective],
) -> None:
    command = HighCommand()

    closed = command.refresh(_game(10), random.Random(1))

    assert closed == []
    assert [order.tier for order in command.orders] == [2, 1, 0]
    for order in command.orders:
        assert order.objective[0] == "LMH"[order.tier]
        assert 2 <= order.expires_on - 10 <= 5
        assert order.prize == Prize(
            "cash", order.score, False, f"Cash for {order.objective}."
        )
        assert order.justification == f"{order.objective} earns."


def test_an_open_order_stays_as_it_is(board: list[Objective]) -> None:
    command = HighCommand()
    command.refresh(_game(10), random.Random(1))
    before = list(command.orders)

    command.refresh(_game(11), random.Random(2))

    assert command.orders == before


def _single(tier: int, objective: str, expires_on: int) -> HighCommand:
    order = Order(objective, tier, ordered_on=10, expires_on=expires_on, prize=None)
    return HighCommand(orders=[order])


def test_a_lapsed_order_gives_way_to_another_from_its_tier(
    board: list[Objective],
) -> None:
    command = _single(0, "L1", expires_on=12)

    closed = command.refresh(_game(12), random.Random(3))

    assert [(c.order.objective, c.outcome) for c in closed] == [("L1", Outcome.EXPIRED)]
    low = next(order for order in command.orders if order.tier == 0)
    assert low.objective in {"L2", "L3"}
    assert [(e.turn, e.outcome, e.name, e.line) for e in command.history] == [
        (12, "expired", "L1", "ran out after 2 turns")
    ]


def test_destroying_the_objective_closes_it_even_on_its_last_turn(
    board: list[Objective],
) -> None:
    board.remove(next(o for o in board if o.name == "H1"))
    command = _single(2, "H1", expires_on=12)

    closed = command.refresh(_game(12, dead=("H1",)), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.ACHIEVED]


def test_an_objective_that_is_no_longer_there_closes_its_order(
    board: list[Objective],
) -> None:
    board.remove(next(o for o in board if o.name == "M1"))
    command = _single(1, "M1", expires_on=14)

    closed = command.refresh(_game(12), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.GONE]


def test_orders_come_back_from_a_save_written_before_a_field_was() -> None:
    order = Order("L1", 0, ordered_on=10, expires_on=12, prize=None)
    state = dict(order.__dict__)
    del state["justification"]
    prize = Prize("cash", 5, False, "Cash.")
    prize_state = dict(prize.__dict__)
    del prize_state["terms"]

    restored: Any = Order.__new__(Order)
    restored.__setstate__(state)
    restored_prize: Any = Prize.__new__(Prize)
    restored_prize.__setstate__(prize_state)

    assert restored.justification == ""
    assert restored_prize.terms == ()
    assert pickle.loads(pickle.dumps(HighCommand([order]))) == HighCommand([order])


def test_a_fault_in_the_orders_does_not_stop_the_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(game: Any) -> None:
        raise RuntimeError("broken")

    game: Any = SimpleNamespace(
        check_win_loss=lambda: TurnState.CONTINUE,
        high_command=SimpleNamespace(refresh=fail),
        settings=_settings(),
    )

    with caplog.at_level(logging.ERROR):
        Game.refresh_high_command(game)

    assert "High Command" in caplog.text


def test_an_order_on_a_base_keeps_what_is_asked_of_it() -> None:
    field = SimpleNamespace(name="Kutaisi")
    runway = Objective(
        name="Kutaisi (OCA/Runway)",
        kind="Airfield",
        targets=(field,),  # type: ignore[arg-type]
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        task=Task.RUNWAY,
    )

    order = _order(runway, tier=2, turn=10, lifetime=3)

    assert (order.objective, order.task, order.base) == (
        "Kutaisi (OCA/Runway)",
        Task.RUNWAY,
        "Kutaisi",
    )


def _base_order(task: Task, base: str = "Kutaisi", expires_on: int = 14) -> Order:
    return Order(
        f"{base} ({task.value})",
        2,
        ordered_on=10,
        expires_on=expires_on,
        prize=None,
        task=task,
        base=base,
    )


def _field(captured: Player = Player.RED, runway: bool = True) -> Any:
    return SimpleNamespace(
        name="Kutaisi",
        captured=captured,
        runway_is_operational=lambda: runway,
    )


@pytest.mark.parametrize(
    ("task", "outcome"),
    [
        (Task.CAPTURE, Outcome.ACHIEVED),
        (Task.AIRCRAFT, Outcome.GONE),
        (Task.RUNWAY, Outcome.GONE),
    ],
)
def test_taking_a_base_achieves_only_an_order_to_take_it(
    board: list[Objective], task: Task, outcome: Outcome
) -> None:
    command = HighCommand([_base_order(task)])

    closed = command.refresh(
        _game(12, bases=(_field(captured=Player.BLUE),)), random.Random(3)
    )

    assert [c.outcome for c in closed] == [outcome]


def test_a_cratered_runway_achieves_its_order(board: list[Objective]) -> None:
    command = HighCommand([_base_order(Task.RUNWAY)])

    closed = command.refresh(_game(12, bases=(_field(runway=False),)), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.ACHIEVED]


def test_a_site_cleared_by_taking_its_base_was_not_destroyed(
    board: list[Objective],
) -> None:
    board.remove(next(o for o in board if o.name == "H1"))
    cleared = SimpleNamespace(
        name="H1", is_dead=True, control_point=SimpleNamespace(captured=Player.BLUE)
    )
    command = _single(2, "H1", expires_on=14)

    closed = command.refresh(_game(12, ground_objects=(cleared,)), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.GONE]


def _debriefing(**parts: Any) -> Any:
    return SimpleNamespace(
        air_losses=SimpleNamespace(enemy=parts.get("aircraft", [])),
        ground_losses=SimpleNamespace(enemy_motorpool=parts.get("vehicles", [])),
        state_data=SimpleNamespace(killed_ground_units=parts.get("names", [])),
        died_on_the_ground=lambda loss: loss.parked,
    )


def _aircraft_loss(base: str, parked: bool) -> Any:
    return SimpleNamespace(
        flight=SimpleNamespace(departure=SimpleNamespace(name=base)), parked=parked
    )


def test_an_aircraft_destroyed_on_the_ground_achieves_the_order_on_its_base() -> None:
    command = HighCommand([_base_order(Task.AIRCRAFT)])
    game = _game(12)

    command.note_results(game, _debriefing(aircraft=[_aircraft_loss("Kutaisi", False)]))
    assert command.orders[0].achieved_on is None
    command.note_results(game, _debriefing(aircraft=[_aircraft_loss("Senaki", True)]))
    assert command.orders[0].achieved_on is None
    command.note_results(game, _debriefing(aircraft=[_aircraft_loss("Kutaisi", True)]))
    assert command.orders[0].achieved_on == 12


def test_a_vehicle_destroyed_in_a_motorpool_achieves_its_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.missiongenerator import motorpoolpopulator

    home = Base("Kutaisi")
    depot = motorpool("HERRING", base=home)
    monkeypatch.setattr(motorpoolpopulator, "motorpools_at", lambda base: [depot])
    command = _single(0, "HERRING", expires_on=14)
    game = _game(12, ground_objects=(depot,))

    command.note_results(game, _debriefing())
    assert command.orders[0].achieved_on is None
    lost = SimpleNamespace(origin=home)
    command.note_results(game, _debriefing(vehicles=[lost]))
    assert command.orders[0].achieved_on == 12


def test_an_aircraft_lost_before_take_off_died_on_the_ground() -> None:
    from game.ato.starttype import StartType
    from game.debriefing import Debriefing

    def loss(start: StartType, parked: bool = False) -> Any:
        return SimpleNamespace(
            flight=SimpleNamespace(start_type=start, parked_reserve=parked)
        )

    parked, cold, airborne, spawned = (
        loss(StartType.COLD, parked=True),
        loss(StartType.COLD),
        loss(StartType.COLD),
        loss(StartType.IN_FLIGHT),
    )
    debriefing: Any = SimpleNamespace(
        _loss_name_by_id={
            id(cold): "Cold 1",
            id(airborne): "Airborne 1",
            id(spawned): "Spawned 1",
        },
        state_data=SimpleNamespace(took_off=["Airborne 1"]),
    )

    assert Debriefing.died_on_the_ground(debriefing, parked)
    assert Debriefing.died_on_the_ground(debriefing, cold)
    assert not Debriefing.died_on_the_ground(debriefing, airborne)
    assert not Debriefing.died_on_the_ground(debriefing, spawned)


def test_fewer_orders_set_closes_the_tiers_past_them(board: list[Objective]) -> None:
    command = HighCommand()
    command.refresh(_game(10), random.Random(1))

    closed = command.refresh(_game(11, settings=_settings(orders=2)), random.Random(2))

    assert [(c.order.tier, c.outcome) for c in closed] == [(2, Outcome.GONE)]
    assert sorted(order.tier for order in command.orders) == [0, 1]


def test_a_lifetime_range_set_backwards_still_works(board: list[Objective]) -> None:
    command = HighCommand()

    command.refresh(
        _game(10, settings=_settings(shortest=4, longest=3)), random.Random(1)
    )

    assert all(3 <= order.expires_on - 10 <= 4 for order in command.orders)


def test_a_high_command_switched_off_gives_no_orders() -> None:
    refreshed: list[Any] = []
    settings = _settings()
    settings.high_command_enabled = False
    game: Any = SimpleNamespace(
        check_win_loss=lambda: TurnState.CONTINUE,
        high_command=SimpleNamespace(refresh=lambda game: refreshed.append(game)),
        settings=settings,
    )

    Game.refresh_high_command(game)

    assert refreshed == []


def test_the_history_keeps_the_latest_entries() -> None:
    from game.highcommand.orders import HISTORY_KEPT

    command = HighCommand()
    for turn in range(HISTORY_KEPT + 5):
        command.note(turn, "expired", f"O{turn}", "ran out")

    assert len(command.history) == HISTORY_KEPT
    assert command.history[0].turn == 5


def test_a_save_written_before_the_history_has_an_empty_one() -> None:
    import pickle

    command = HighCommand()
    del command.__dict__["history"]

    assert pickle.loads(pickle.dumps(command)).history == []
