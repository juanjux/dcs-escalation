"""Paying the prizes of the High Command's orders, and spending tickets."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.highcommand import prizes
from game.highcommand.orders import Closed, HighCommand, Order, Outcome, Ticket
from game.highcommand.prizes import KINDS, Prize, Step, kind_of
from game.squadrons.morale import MORALE_MAX
from game.squadrons.pilot import Pilot, PilotStatus
from game.data.groups import GroupTask
from game.theater import Airfield, Player
from game.theater.controlpoint import RunwayStatus
from tests.highcommand.stubs import Base, launcher, sam


def _give(game: Any, prize: Prize) -> str:
    kind = kind_of(prize)
    assert kind is not None and kind.give is not None
    return kind.give(game, prize, ())


def _steps(prize: Prize) -> tuple[Step, ...]:
    kind = kind_of(prize)
    assert kind is not None
    return kind.steps


def _order(prize: Prize) -> Order:
    return Order("DEPOT", 0, ordered_on=10, expires_on=14, prize=prize)


def _wounded(name: str, turns: int) -> Pilot:
    pilot = Pilot(name)
    pilot.wound(turns, turn=9)
    return pilot


def _game(**parts: Any) -> Any:
    squadron = SimpleNamespace(
        name="VF-11", aircraft="F-14B", current_roster=parts.get("pilots", [])
    )
    wing = SimpleNamespace(iter_squadrons=lambda: [squadron])
    coalition = SimpleNamespace(
        air_wing=wing,
        budget=parts.get("budget", 0.0),
    )
    coalition.adjust_budget = lambda amount: setattr(
        coalition, "budget", coalition.budget + amount
    )
    return SimpleNamespace(
        turn=12,
        coalition_for=lambda player: coalition,
        theater=SimpleNamespace(controlpoints=parts.get("bases", [])),
        blue=coalition,
    )


def _airfield(name: str, side: Player = Player.BLUE, damaged: bool = True) -> Any:
    field: Any = Airfield.__new__(Airfield)
    field.name = name
    field.position = f"{name} position"
    field._coalition = SimpleNamespace(player=side)
    field._runway_status = RunwayStatus(damaged=damaged)
    return field


@pytest.fixture
def income(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prizes, "Income", lambda game, player: SimpleNamespace(total=80.0)
    )


def test_an_achieved_order_pays_its_prize_and_a_ticket_is_kept(income: None) -> None:
    cash = Prize("cash", 5, False, "Cash.", (("income_share", 1.0),))
    runway = Prize("runway", 9, True, "A ticket for a runway repair.")
    lapsed = Prize("cash", 3, False, "Cash.", (("income_share", 0.6),))
    game = _game(budget=10.0)
    command = HighCommand()

    lines = command.pay(
        game,
        [
            Closed(_order(cash), Outcome.ACHIEVED),
            Closed(_order(runway), Outcome.ACHIEVED),
            Closed(_order(lapsed), Outcome.EXPIRED),
        ],
    )

    assert game.blue.budget == pytest.approx(90.0)
    assert [ticket.prize for ticket in command.tickets] == [runway]
    assert command.tickets[0].earned_on == 12
    assert len(lines) == 2
    assert [(e.outcome, e.line) for e in command.history][1:] == [
        ("achieved", "A ticket for a runway repair.")
    ]
    assert [e.outcome for e in command.history] == ["achieved", "achieved"]


def test_cash_is_a_share_of_the_income_when_it_is_paid(income: None) -> None:
    game = _game(budget=10.0)
    prize = Prize("cash", 5, False, "Cash.", (("income_share", 1.4),))

    line = _give(game, prize)

    assert game.blue.budget == pytest.approx(10.0 + 112.0)
    assert line == "$112M added to our budget."


def test_morale_rises_for_every_pilot_as_far_as_it_goes() -> None:
    cheerful, gloomy = Pilot("Cheerful"), Pilot("Gloomy")
    cheerful.morale = MORALE_MAX - 3
    gloomy.morale = 10
    prize = Prize("morale", 6, False, "Morale.", (("points", 12),))

    _give(_game(pilots=[cheerful, gloomy]), prize)

    assert (cheerful.morale, gloomy.morale) == (MORALE_MAX, 22)


def test_the_wounded_leave_hospital_early() -> None:
    nearly, badly = _wounded("Nearly", 1), _wounded("Badly", 4)
    prize = Prize("hospital", 5, False, "Hospital.", (("turns", 2),))

    _give(_game(pilots=[nearly, badly]), prize)

    assert nearly.status is PilotStatus.Active
    assert (badly.status, badly.wounded_turns) == (PilotStatus.Wounded, 2)


def test_with_nobody_in_hospital_there_is_nobody_to_send_home() -> None:
    prize = Prize("hospital", 5, False, "Hospital.", (("turns", 2),))

    assert _give(_game(pilots=[Pilot("Fine")]), prize) == (
        "None of our pilots was in hospital."
    )


def test_a_runway_ticket_is_spent_on_one_of_our_broken_runways() -> None:
    broken, whole, theirs = (
        _airfield("Kutaisi"),
        _airfield("Senaki", damaged=False),
        _airfield("Sukhumi", side=Player.RED),
    )
    game = _game(bases=[broken, whole, theirs])
    prize = Prize("runway", 9, True, "A ticket for a runway repair.")
    command = HighCommand(tickets=[Ticket(prize, "DEPOT", 11)])
    (step,) = _steps(prize)

    options = step.options(game, prize, ())
    line = command.spend(game, command.tickets[0], (options[0].key,))

    assert [choice.label for choice in options] == ["Kutaisi"]
    assert not broken.runway_status.damaged
    assert command.tickets == []
    assert line == "The runway at Kutaisi is repaired."
    assert [(e.outcome, e.line) for e in command.history] == [("spent", line)]


def test_with_no_broken_runway_there_is_nothing_to_spend_it_on() -> None:
    prize = Prize("runway", 9, True, "A ticket for a runway repair.")
    (step,) = _steps(prize)

    assert (
        step.options(_game(bases=[_airfield("Kutaisi", damaged=False)]), prize, ())
        == []
    )


def test_a_healing_ticket_puts_the_pilot_picked_back_on_duty() -> None:
    hurt, fine = _wounded("Hurt", 3), Pilot("Fine")
    game = _game(pilots=[hurt, fine])
    prize = Prize("heal", 7, True, "A ticket to heal a pilot.")
    command = HighCommand(tickets=[Ticket(prize, "DEPOT", 11)])
    (step,) = _steps(prize)

    (choice,) = step.options(game, prize, ())
    command.spend(game, command.tickets[0], (choice.key,))

    assert choice.label == "Hurt"
    assert "VF-11" in choice.detail
    assert hurt.status is PilotStatus.Active


def test_what_asks_for_a_choice_is_a_ticket() -> None:
    for kind in KINDS:
        if kind.steps:
            assert kind.ticket, kind.key
            assert kind.give is not None, kind.key


def _sites_game(*sites: Any, groups: tuple[Any, ...] = ()) -> Any:
    game = _game()
    game.theater.ground_objects = list(sites)
    game.blue.armed_forces = SimpleNamespace(
        groups_for_task=lambda task: [g for g in groups if task in g.tasks]
    )
    return game


def test_a_sam_ticket_offers_every_air_defence_site_of_ours() -> None:
    home, away = Base("Batumi", side=Player.BLUE), Base("Sukhumi")
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40)], base=home)
    wreck = sam("WRECK", 0, [launcher("SAM SA-10 LN", 40)], base=home)
    for unit_ in wreck.units:
        unit_.alive = False
    empty = sam("EMPTY", 0, [], base=home)
    empty.groups = []
    theirs = sam("THEIRS", 0, [launcher("SAM SA-10 LN", 40)], base=away)
    prize = Prize("sam", 6, True, "A ticket for a SAM.", (("band", "MERAD"),))
    where, _ = _steps(prize)

    options = where.options(_sites_game(battery, wreck, empty, theirs), prize, ())

    assert [(o.label, o.detail) for o in options] == [
        ("EMPTY", "Empty, at Batumi"),
        ("GRUMBLE", "SA-10, at Batumi"),
        ("WRECK", "Destroyed, at Batumi"),
    ]


def test_a_sam_ticket_offers_the_systems_of_its_band_and_picks_a_lone_one() -> None:
    hawk = SimpleNamespace(
        name="Hawk", tasks=[GroupTask.MERAD], units=["Hawk ln", "Hawk sr"]
    )
    patriot = SimpleNamespace(name="Patriot", tasks=[GroupTask.LORAD], units=[])
    prize = Prize("sam", 6, True, "A ticket for a SAM.", (("band", "MERAD"),))
    _, which = _steps(prize)

    options = which.options(_sites_game(groups=(hawk, patriot)), prize, ())

    assert [(o.label, o.detail) for o in options] == [("Hawk", "Hawk ln and Hawk sr")]
    assert which.auto


def test_a_sam_ticket_places_the_system_picked_where_it_was_picked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.highcommand import placing
    from game.server import EventStream

    home = Base("Batumi", side=Player.BLUE)
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40)], base=home)
    hawk = SimpleNamespace(name="Hawk", tasks=[GroupTask.MERAD])
    placed: list[tuple[Any, Any]] = []
    monkeypatch.setattr(
        placing, "place", lambda game, site, group: placed.append((site, group))
    )
    monkeypatch.setattr(EventStream, "put_nowait", lambda events: None)
    prize = Prize("sam", 6, True, "A ticket for a SAM.", (("band", "MERAD"),))
    command = HighCommand(tickets=[Ticket(prize, "DEPOT", 11)])

    line = command.spend(
        _sites_game(battery, groups=(hawk,)),
        command.tickets[0],
        (str(battery.id), "Hawk"),
    )

    assert placed == [(battery, hawk)]
    assert line == "Hawk set up at GRUMBLE."


def test_a_prize_drawn_for_the_enemy_is_given_to_the_enemy(income: None) -> None:
    red = SimpleNamespace(budget=5.0)
    red.adjust_budget = lambda amount: setattr(red, "budget", red.budget + amount)
    blue = SimpleNamespace(budget=5.0)
    game: Any = SimpleNamespace(
        coalition_for=lambda player: red if player is Player.RED else blue
    )
    prize = Prize("cash", 5, False, "Cash.", (("income_share", 0.5),), Player.RED)

    _give(game, prize)

    assert red.budget == pytest.approx(45.0)
    assert blue.budget == 5.0


def test_prizes_are_drawn_for_the_side_asked() -> None:
    from game.highcommand.prizes import Prizes

    settings = SimpleNamespace(live_pilots_enabled=False, morale_enabled=False)
    faction: Any = SimpleNamespace(
        aircraft=[], awacs=[], tankers=[], frontline_units=[]
    )
    drawn = Prizes(settings, faction, 80.0, None, Player.RED).draw(5, "seed")

    assert drawn is not None and drawn.side is Player.RED


def test_the_places_a_ticket_offers_can_be_shown_on_the_map() -> None:
    home = Base("Batumi", side=Player.BLUE)
    battery = sam("GRUMBLE", 0, [launcher("SAM SA-10 LN", 40)], base=home)
    sam_prize = Prize("sam", 6, True, "A ticket for a SAM.", (("band", "MERAD"),))
    runway_prize = Prize("runway", 9, True, "A ticket for a runway repair.")
    where, _ = _steps(sam_prize)
    (runway,) = _steps(runway_prize)

    [site] = where.options(_sites_game(battery), sam_prize, ())
    [field] = runway.options(_game(bases=[_airfield("Kutaisi")]), runway_prize, ())

    assert site.position == battery.position
    assert field.position == "Kutaisi position"
