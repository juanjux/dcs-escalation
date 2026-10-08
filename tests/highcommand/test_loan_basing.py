"""Loan base selection and flight decks with surviving escorts."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from dcs.ships import PERRY

from game.ato import FlightType
from game.highcommand.loans import lend, loan_bases
from game.highcommand.orders import HighCommand, Ticket
from game.highcommand.prizes import CannotGive, Prize, kind_of
from game.squadrons.squadron import Squadron
from game.theater.controlpoint import (
    Carrier,
    Essex,
    EssexCarrier,
    Lha,
    LHA_Tarawa,
    Player,
    Stennis,
)
from game.theater.theatergroundobject import GenericCarrierGroundObject
from tests.highcommand.stubs import at


def _fleet(cls: Any = Lha, hull: Any = LHA_Tarawa, alive: bool = False) -> Any:
    cp = cls("Fleet", at(0), None, Player.BLUE)
    tgo = MagicMock(spec=GenericCarrierGroundObject)
    tgo.groups = [
        SimpleNamespace(
            units=[
                SimpleNamespace(type=hull, alive=alive),
                SimpleNamespace(type=PERRY, alive=True),
            ]
        )
    ]
    cp.connected_objectives = [tgo]
    return cp


@pytest.mark.parametrize(
    "cls,hull", [(Carrier, Stennis), (Lha, LHA_Tarawa), (EssexCarrier, Essex)]
)
def test_escorts_cannot_replace_a_sunk_flight_deck(cls: Any, hull: Any) -> None:
    cp = _fleet(cls, hull)
    aircraft = SimpleNamespace(carrier_capable=True, lha_capable=True)
    assert cp.sunk
    assert not cp.can_operate(aircraft)
    cp.find_main_tgo().groups[0].units[0].alive = True
    assert cp.can_operate(aircraft)
    assert not cp.can_operate(SimpleNamespace(carrier_capable=False, lha_capable=False))


@pytest.mark.parametrize("cls", [Carrier, Lha, EssexCarrier])
def test_initial_assignment_still_works_before_ships_are_generated(cls: Any) -> None:
    cp = cls("Fleet", at(0), None, Player.BLUE)
    assert cp.can_operate(SimpleNamespace(carrier_capable=True, lha_capable=True))


def _base(name: str, room: int = 20, operates: bool = True) -> Any:
    return SimpleNamespace(
        id=name,
        name=name,
        position=at(20),
        can_operate=lambda aircraft: operates,
        unclaimed_parking=lambda parking: room,
    )


def _game(side: Player = Player.BLUE, kind: str = "squadron") -> Any:
    aircraft = SimpleNamespace(
        display_name="AH-1W SuperCobra",
        helicopter=True,
        lha_capable=True,
        carrier_capable=True,
        flyable=False,
        task_priorities={FlightType.CAS: 1},
    )
    wreck = _fleet()
    bases = [
        _base("Shore"),
        _base("Carrier"),
        _base("Full", 9 if kind == "squadron" else 0),
        _base("Incompatible", operates=False),
        wreck,
    ]
    # A wreck must be rejected before its parking is consulted.
    wreck.unclaimed_parking = MagicMock(
        side_effect=AssertionError("Wreck parking read")
    )
    enemy = _base("Enemy")
    wing = SimpleNamespace(squadron_def_generator=MagicMock(), add_squadron=MagicMock())
    coalition = SimpleNamespace(
        faction=SimpleNamespace(
            aircraft=[aircraft], awacs=[aircraft], tankers=[aircraft]
        ),
        air_wing=wing,
    )
    command = HighCommand(side=side)
    prize = Prize(
        kind,
        10,
        True,
        "A squadron on loan.",
        (("type", aircraft.display_name), ("aircraft", 10), ("turns", 3)),
        side,
    )
    command.tickets.append(Ticket(prize, "Objective", 9))
    return SimpleNamespace(
        turn=10,
        settings=SimpleNamespace(ground_start_ai_planes=False),
        theater=SimpleNamespace(
            control_points_for=lambda player: bases if player == side else [enemy]
        ),
        coalition_for=lambda player: coalition,
        high_command_for=lambda player: command,
        high_command=command,
        bases=bases,
        aircraft=aircraft,
    )


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_ticket_offers_only_friendly_compatible_bases_with_room(
    side: Player, kind_key: str
) -> None:
    game = _game(side, kind_key)
    ticket = game.high_command.tickets[0]
    kind = kind_of(ticket.prize)
    assert kind is not None
    (step,) = kind.steps
    assert step.question == "Which base?" and not step.auto
    assert [choice.key for choice in step.options(game, ticket.prize, ())] == [
        "Shore",
        "Carrier",
    ]


@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_loan_uses_the_selected_base(monkeypatch: Any, kind_key: str) -> None:
    game = _game(kind=kind_key)
    sq = MagicMock(name="loan")
    sq.name = "Loan squadron"
    sq.owned_aircraft = 10
    sq.location = game.bases[1]
    create = MagicMock(return_value=sq)
    monkeypatch.setattr(Squadron, "create_from", create)
    command = game.high_command
    command.spend(game, command.tickets[0], ("Carrier",))
    assert create.call_args.args[3] is game.bases[1]
    sq.populate_for_turn_0.assert_called_once_with(squadrons_start_full=True)
    sq.return_all_pilots_and_aircraft.assert_called_once_with()
    assert create.call_args.args[2] == (10 if kind_key == "squadron" else 1)
    assert (
        create.call_args.args[1]
        is {
            "squadron": FlightType.CAS,
            "awacs": FlightType.AEWC,
            "tanker": FlightType.REFUELING,
        }[kind_key]
    )
    assert command.tickets == []
    assert command.loans[0].until == 13
    assert command.loans[0].squadron is sq


@pytest.mark.parametrize(
    "task,count",
    [(FlightType.AEWC, 1), (FlightType.REFUELING, 1), (FlightType.CAS, 10)],
)
def test_new_loan_can_fly_in_the_turn_it_is_redeemed(
    monkeypatch: Any, task: FlightType, count: int
) -> None:
    from dcs.countries import USA
    from game.settings import Settings
    from game.squadrons.pilot import Pilot

    game = _game()
    sq = Squadron.__new__(Squadron)
    sq.settings = Settings()
    sq.settings.enable_squadron_pilot_limits = True
    sq.settings.live_pilots_enabled = False
    sq.country = USA()
    sq.pilot_pool = [
        Pilot(f"Pilot {n}") for n in range(sq.settings.squadron_pilot_limit)
    ]
    sq.current_roster = []
    sq.available_pilots = []
    sq.coalition = game.coalition_for(Player.BLUE)
    sq.coalition.game = game
    sq.coalition.faction.locales = ["en_US"]
    sq.aircraft = game.aircraft
    sq.max_size = count
    sq.location = game.bases[0]
    monkeypatch.setattr(Squadron, "create_from", lambda *args: sq)

    loan = lend(game, Player.BLUE, game.aircraft, count, 1, task, False, sq.location)

    assert loan is not None and loan.until == game.turn + 1
    assert sq.owned_aircraft == count
    assert sq.untasked_crewed_aircraft == count
    assert sq.can_fulfill_flight(count)
    sq.claim_inventory(count)
    assert not sq.can_fulfill_flight(1)


@pytest.mark.parametrize(
    "picked", [(), ("Enemy",), ("Full",), ("Incompatible",), ("Shore", "Carrier")]
)
@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_invalid_choice_keeps_the_ticket(
    picked: tuple[str, ...], kind_key: str
) -> None:
    game = _game(kind=kind_key)
    command = game.high_command
    with pytest.raises(CannotGive):
        command.spend(game, command.tickets[0], picked)
    assert len(command.tickets) == 1 and command.loans == []


@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_selected_base_is_rechecked_when_spending(kind_key: str) -> None:
    game = _game(kind=kind_key)
    ticket = game.high_command.tickets[0]
    kind = kind_of(ticket.prize)
    assert kind is not None
    assert kind.steps[0].options(game, ticket.prize, ())
    game.bases[1].can_operate = lambda aircraft: False
    with pytest.raises(CannotGive, match="no longer take"):
        game.high_command.spend(game, ticket, ("Carrier",))
    assert game.high_command.tickets == [ticket]
    assert (
        lend(
            game, Player.BLUE, game.aircraft, 10, 3, FlightType.CAS, True, game.bases[1]
        )
        is None
    )


@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_empty_base_list_blocks_the_ticket(kind_key: str) -> None:
    from game.highcommand.describe import NOT_NOW, ticket_state

    game = _game(kind=kind_key)
    game.bases[:] = game.bases[-1:]
    assert loan_bases(game, Player.BLUE, game.aircraft, 10) == []
    assert ticket_state(game, game.high_command.tickets[0]) == NOT_NOW


@pytest.mark.parametrize("already_planned", [False, True])
def test_relocation_to_a_sunk_flight_deck_is_rejected(already_planned: bool) -> None:
    game = _game()
    wreck = game.bases[-1]
    wreck.unclaimed_parking = lambda parking: 20
    squadron: Any = SimpleNamespace(
        location=SimpleNamespace(runway_is_operational=lambda: True),
        destination=wreck if already_planned else None,
        owned_aircraft=10,
        expected_size_next_turn=10,
        aircraft=game.aircraft,
        coalition=SimpleNamespace(game=game),
        replan_ferry_flights=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="cannot operate"):
        Squadron.plan_relocation(squadron, wreck, datetime(2026, 1, 1))
    assert squadron.destination is (wreck if already_planned else None)
    squadron.replan_ferry_flights.assert_not_called()


def test_transfer_destination_list_excludes_the_wreck() -> None:
    from qt_ui.windows.SquadronDialog import SquadronDestinationComboBox

    game = _game()
    squadron = SimpleNamespace(
        expected_size_next_turn=10,
        aircraft=game.aircraft,
        coalition=SimpleNamespace(game=game),
        player=Player.BLUE,
        location=game.bases[0],
        destination=None,
    )
    game.aircraft.dcs_unit_type = object()
    selector: Any = SimpleNamespace(
        squadron=squadron,
        theater=game.theater,
        calculate_parking_slots=lambda cp, aircraft: 0,
    )
    assert list(SquadronDestinationComboBox.iter_destinations(selector)) == [
        game.bases[1]
    ]


@pytest.mark.parametrize("kind_key", ["squadron", "awacs", "tanker"])
def test_spending_pane_requires_a_base_selection(kind_key: str) -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from qt_ui.windows.highcommand.model import ticket_views
    from qt_ui.windows.highcommand.tickets import ChoiceRow, SpendPane

    app = QApplication.instance() or QApplication([])
    game = _game(kind=kind_key)
    pane = SpendPane(lambda ticket, picked: "given")
    pane.show_ticket(game, ticket_views(game)[0])
    assert not pane.go.isEnabled()
    choices = pane.findChildren(ChoiceRow)
    assert [row.choice.key for row in choices] == ["Shore", "Carrier"]
    pane._pick(choices[1].choice)
    assert pane.go.isEnabled()
    assert "at Carrier" in pane.preview.text()
    pane.close()
    app.processEvents()
