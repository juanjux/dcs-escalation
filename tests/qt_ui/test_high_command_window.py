"""The High Command window: what each order row and the detail pane are handed, and
the window and command bar cell built from them."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.highcommand.campaign import Task
from game.highcommand.importance import Reason
from game.highcommand.orders import HighCommand, Order, Ticket
from game.highcommand.prizes import Prize
from qt_ui.windows.highcommand import model as data

TURN = 14


def _order(
    objective: str,
    tier: int,
    expires_on: int,
    *,
    task: Task | None = None,
    base: str = "",
    ticket: bool = False,
    importance: int = 3,
) -> Order:
    return Order(
        objective=objective,
        tier=tier,
        ordered_on=TURN - 1,
        expires_on=expires_on,
        prize=Prize("cash", 5, ticket, f"The prize of {objective}.", ()),
        kind="Airfield" if task else "AA Defense Site",
        difficulty=4,
        importance=importance,
        justification=f"Why {objective}.",
        task=task,
        base=base,
    )


class _At:
    def latlng(self) -> str:
        return "here"


def _site(name: str, base: str, units: int) -> Any:
    return SimpleNamespace(
        name=name,
        control_point=SimpleNamespace(name=base),
        position=_At(),
        units=[SimpleNamespace(alive=index > 0) for index in range(units + 1)],
    )


def _game(*orders: Order, enabled: bool = True, tickets: int = 0) -> Any:
    prize = Prize("runway", 8, True, "A ticket.", ())
    return SimpleNamespace(
        turn=TURN,
        settings=SimpleNamespace(high_command_orders=3, high_command_enabled=enabled),
        high_command=HighCommand(
            orders=list(orders),
            tickets=[Ticket(prize, "WOLF", TURN - 1) for _ in range(tickets)],
        ),
        theater=SimpleNamespace(
            ground_objects=[_site("TURKEY", "Ushuaia", 15)],
            controlpoints=[SimpleNamespace(name="Punta Arenas", position=_At())],
        ),
    )


@pytest.fixture
def objectives(monkeypatch: Any) -> None:
    turkey = SimpleNamespace(
        name="TURKEY",
        hazards=("its own SA-20B", "236 nm from Mount Pleasant"),
        reasons=(
            Reason("cover", 1164, "covers"),
            Reason("rebuild", 393, "rebuild"),
            Reason("threat", 0, "nothing"),
        ),
    )
    monkeypatch.setattr(data, "_objectives", lambda game: [turkey])


def test_three_tiers_are_named_and_any_other_count_is_numbered() -> None:
    assert [data.tier_chip(tier, 3) for tier in (2, 1, 0)] == ["HIGH", "MEDIUM", "LOW"]
    assert data.tier_chip(5, 6) == "6/6"
    assert data.tier_words(1, 3) == "medium tier"
    assert data.tier_words(3, 6) == "tier 4 of 6"


def test_the_top_and_bottom_tiers_get_their_own_colours() -> None:
    assert [data.tier_colour(tier, 6) for tier in (5, 3, 0)] == [
        "high",
        "medium",
        "low",
    ]


def test_the_headline_counts_the_orders_in_their_last_turn() -> None:
    game = _game(_order("TURKEY", 2, TURN + 3), _order("HERRING", 0, TURN + 1))

    figures = data.headline(game)

    assert (figures.orders, figures.last_turn, figures.soonest) == (2, 1, 1)


def test_a_ground_object_order_carries_the_objective_s_hazards_and_worth(
    objectives: None,
) -> None:
    [order] = data.order_views(_game(_order("TURKEY", 2, TURN + 3, ticket=True)))

    assert (order.name, order.base, order.tier_chip) == ("TURKEY", "Ushuaia", "HIGH")
    assert order.asked == "Destroy every unit"
    assert order.taken_detail.startswith("15 units")
    assert order.hazards == ("its own SA-20B", "236 nm from Mount Pleasant")
    assert order.worth == (("cover", "$1164M"), ("rebuild", "$393M"))
    assert order.ticket and order.turns_left == 3 and not order.last_turn


def test_a_base_order_is_named_after_the_base_and_asks_its_task(
    objectives: None,
) -> None:
    order = _order(
        "Punta Arenas (OCA/Runway)",
        1,
        TURN + 1,
        task=Task.RUNWAY,
        base="Punta Arenas",
    )

    [view] = data.order_views(_game(order))

    assert (view.name, view.kind) == ("Punta Arenas", "Airfield")
    assert view.asked == "OCA/Runway — crater the runway"
    assert view.taken_title == "The runway cratered"
    assert view.last_turn and view.position is not None


def test_a_motorpool_is_taken_by_one_vehicle() -> None:
    order = _order("HERRING", 0, TURN + 2)

    assert data.asked(order, motorpool=True) == "Destroy one of its vehicles"
    assert data.taken_when(order, True, 10, "Rio Grande")[0] == (
        "One vehicle destroyed"
    )


def test_the_least_important_orders_read_as_comical(objectives: None) -> None:
    [order] = data.order_views(_game(_order("TURKEY", 0, TURN + 2, importance=1)))

    assert order.comical


@pytest.fixture
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

    app = QApplication.instance() or QApplication([])
    if GameUpdateSignal.get_instance() is None:
        GameUpdateSignal()
    return app


def test_the_window_opens_on_the_order_asked_for(qt_app: Any, objectives: None) -> None:
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    game = _game(
        _order("TURKEY", 2, TURN + 3),
        _order(
            "Punta Arenas (OCA/Runway)",
            1,
            TURN + 1,
            task=Task.RUNWAY,
            base="Punta Arenas",
        ),
    )
    window = HighCommandWindow(SimpleNamespace(game=game))

    assert window.orders.model.rowCount() == 2
    first = window.orders.selected
    assert first is not None and first.name == "TURKEY"
    window.open_order("Punta Arenas (OCA/Runway)")
    opened = window.orders.selected
    assert opened is not None and opened.name == "Punta Arenas"
    assert window.orders.detail.name.text() == "Punta Arenas"
    assert not window.headline.last_turn.isHidden()


def test_show_on_map_moves_the_map(
    qt_app: Any, objectives: None, monkeypatch: Any
) -> None:
    from game.server import EventStream
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    sent: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    window = HighCommandWindow(
        SimpleNamespace(game=_game(_order("TURKEY", 2, TURN + 3)))
    )

    window.orders.detail.map_button.click()

    assert [events.fly_to for events in sent] == ["here"]


def test_with_the_high_command_off_the_window_says_so(qt_app: Any) -> None:
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    window = HighCommandWindow(SimpleNamespace(game=_game(enabled=False)))

    assert window.orders.stack.currentWidget() is window.orders.message
    assert window.orders.message.title.text() == "The High Command is off"


def test_the_command_bar_cell_shows_the_last_turn_or_when_the_next_ends(
    qt_app: Any,
) -> None:
    from qt_ui.widgets.commandbar import HighCommandCell

    cell = HighCommandCell(lambda: None)

    cell.set_state(3, 1, 1, 4)
    assert not cell.last_turn.isHidden() and cell.next_ends.isHidden()
    assert cell.tickets_words.text() == "tickets to spend"

    cell.set_state(3, 0, 2, 0)
    assert cell.last_turn.isHidden() and cell.next_ends.text() == "· next ends in 2"
    assert cell.tickets.isHidden() and cell.tickets_words.text() == "no tickets"


class _Aircraft:
    dcs_unit_type = SimpleNamespace(id="FA-18C_hornet")

    def __str__(self) -> str:
        return "F/A-18C Hornet (Lot 20)"


def _loan(name: str, until: int) -> Any:
    from game.highcommand.loans import Loan

    squadron: Any = SimpleNamespace(
        name=name,
        aircraft=_Aircraft(),
        owned_aircraft=12,
        location=SimpleNamespace(name="Mount Pleasant"),
    )
    return Loan(squadron, until)


def test_the_loans_go_back_soonest_first() -> None:
    game = _game()
    game.high_command.loans = [_loan("VFA-2", TURN + 3), _loan("VAW-1", TURN + 1)]

    loans = data.loan_views(game)

    assert [(loan.squadron, loan.turns_left) for loan in loans] == [
        ("VAW-1", 1),
        ("VFA-2", 3),
    ]
    assert loans[0].last_turn and loans[0].dcs_id == "FA-18C_hornet"


def test_the_on_loan_tab_lists_them_or_says_there_are_none(qt_app: Any) -> None:
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    game = _game()
    game.high_command.loans = [_loan("VAW-1", TURN + 1)]
    window = HighCommandWindow(SimpleNamespace(game=game))

    assert window.loans.rows.count() == 1 and window.loans.empty.isHidden()
    game.high_command.loans = []
    window.reload()
    assert window.loans.list.isHidden() and not window.loans.empty.isHidden()


def test_the_history_lists_the_newest_first(qt_app: Any) -> None:
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    game = _game()
    window = HighCommandWindow(SimpleNamespace(game=game))
    assert window.history.list.isHidden() and not window.history.empty.isHidden()

    game.high_command.note(12, "gone", "SEALION", "no longer an objective")
    game.high_command.note(13, "spent", "Ticket spent", "Hawk set up at BEETLE.")
    window.reload()

    assert [entry.name for entry in window.history.model.entries] == [
        "Ticket spent",
        "SEALION",
    ]


def test_the_active_effects_tab_lists_them_soonest_first(qt_app: Any) -> None:
    from game.highcommand.orders import Effect
    from qt_ui.windows.highcommand.dialog import HighCommandWindow

    game = _game()
    window = HighCommandWindow(SimpleNamespace(game=game))
    assert window.effects.list.isHidden() and not window.effects.empty.isHidden()

    game.high_command.effects = [
        Effect("enemy-income", "The enemy's income cut by 45%", "GORILLA", TURN + 2),
        Effect("discount", "42% off SAM batteries", "WOLF", TURN + 1),
    ]
    window.reload()

    labels = [effect.label for effect in data.effect_views(game)]
    assert labels == ["42% off SAM batteries", "The enemy's income cut by 45%"]
    assert window.effects.rows.count() == 2
    assert window.tabs.counts[window.EFFECTS] == 2
