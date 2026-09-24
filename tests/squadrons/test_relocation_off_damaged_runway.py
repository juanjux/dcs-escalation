"""A squadron with aircraft does not relocate off a damaged runway.

The mission leaves out any flight from a damaged runway, ferries included, and the
squadron arrived at its new base at the end of the turn all the same: aircraft trapped
behind a cratered runway walked out of it.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from game.migrator import Migrator
from game.squadrons.squadron import Squadron

NOW = datetime(2026, 9, 21, 20, 0)


class _Base(SimpleNamespace):
    def __str__(self) -> str:
        return str(self.name)


def _base(name: str, operational: bool, sunk: bool = False) -> Any:
    return _Base(
        name=name,
        sunk=sunk,
        runway_is_operational=lambda: operational,
        unclaimed_parking=lambda parking_type: 99,
        can_operate=lambda aircraft: True,
    )


def _squadron(location: Any, aircraft: int) -> Any:
    planned: list[datetime] = []
    return SimpleNamespace(
        location=location,
        destination=None,
        owned_aircraft=aircraft,
        expected_size_next_turn=aircraft,
        aircraft=SimpleNamespace(helicopter=False, lha_capable=False, flyable=False),
        coalition=SimpleNamespace(
            game=SimpleNamespace(settings=SimpleNamespace(ground_start_ai_planes=True))
        ),
        replan_ferry_flights=planned.append,
        planned=planned,
    )


def test_a_squadron_with_aircraft_cannot_leave_a_damaged_runway() -> None:
    squadron = _squadron(_base("Rio Gallegos", operational=False), aircraft=4)

    with pytest.raises(RuntimeError, match="runway is damaged"):
        Squadron.plan_relocation(squadron, _base("Punta Arenas", True), NOW)

    assert squadron.destination is None
    assert squadron.planned == []


def test_an_empty_squadron_can_still_leave_it() -> None:
    """Sell the aircraft and the pilots can go: nothing has to take off."""
    squadron = _squadron(_base("Rio Gallegos", operational=False), aircraft=0)
    destination = _base("Punta Arenas", True)

    Squadron.plan_relocation(squadron, destination, NOW)

    assert squadron.destination is destination
    assert squadron.planned == [NOW]


def test_an_order_already_given_off_a_damaged_runway_is_cancelled_on_load() -> None:
    stranded = _squadron(_base("Rio Gallegos", operational=False), aircraft=4)
    moving = _squadron(_base("Ushuaia", operational=True), aircraft=2)
    emptied = _squadron(_base("Rio Gallegos", operational=False), aircraft=0)
    cancelled: list[Any] = []
    for squadron in (stranded, moving, emptied):
        squadron.destination = _base("Punta Arenas", True)
        squadron.cancel_ferry_flights = lambda s=squadron: cancelled.append(s)
    wing = SimpleNamespace(iter_squadrons=lambda: iter([stranded, moving, emptied]))
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(
        blue=SimpleNamespace(air_wing=wing),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter([]))),
    )

    migrator._cancel_relocations_off_damaged_runways()

    assert cancelled == [stranded]
    assert stranded.destination is None
    assert moving.destination is not None and emptied.destination is not None


def test_a_squadron_left_aboard_a_sunk_ship_with_aircraft_is_told_so() -> None:
    squadron = _squadron(_base("LHA-1 Tarawa", operational=False, sunk=True), 4)

    with pytest.raises(RuntimeError, match="it has sunk"):
        Squadron.plan_relocation(squadron, _base("Mount Pleasant", True), NOW)


def _processor(*squadrons: Any) -> Any:
    messages: list[tuple[str, str]] = []
    wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    game = SimpleNamespace(
        blue=SimpleNamespace(air_wing=wing),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter([]))),
        message=lambda title, text: messages.append((title, text)),
    )
    return SimpleNamespace(game=game, messages=messages)


def _aboard(base: Any, aircraft: int, pending: int = 0) -> Any:
    squadron = _squadron(base, aircraft)
    squadron.pending_deliveries = pending
    squadron.destroyed_aircraft = 1
    squadron.aircraft = _Base(
        name="UH-1H Iroquois", helicopter=True, lha_capable=True, flyable=False
    )

    def refund_orders() -> None:
        squadron.pending_deliveries = 0

    squadron.refund_orders = refund_orders
    return squadron


def test_the_aircraft_aboard_a_ship_that_sinks_go_down_with_it() -> None:
    """Its pilots swim: the squadron stays, empty, and can relocate."""
    from game.sim.missionresultsprocessor import MissionResultsProcessor

    deck = _base("LHA-1 Tarawa", operational=True)
    ashore = _base("Mount Pleasant", operational=True)
    aboard = _aboard(deck, aircraft=6, pending=2)
    inbound = _aboard(ashore, aircraft=4)
    inbound.destination = deck
    stays = _aboard(ashore, aircraft=4)
    processor = _processor(aboard, inbound, stays)
    afloat = [deck, ashore]

    deck.sunk = True
    MissionResultsProcessor.commit_sunk_decks(processor, afloat)

    assert (aboard.owned_aircraft, aboard.destroyed_aircraft) == (0, 7)
    assert aboard.pending_deliveries == 0
    assert inbound.destination is None and inbound.owned_aircraft == 4
    assert stays.owned_aircraft == 4
    assert processor.messages == [
        (
            "LHA-1 Tarawa sunk",
            f"6 UH-1H Iroquois of {aboard} went down with it. Its pilots survived.",
        )
    ]
    Squadron.plan_relocation(aboard, ashore, NOW)
    assert aboard.destination is ashore


def test_a_deck_that_was_never_afloat_does_not_sink_its_squadrons_again() -> None:
    """A carrier DCS cannot launch from reads as sunk from the start. Only what sinks
    during the mission takes its aircraft with it."""
    from game.sim.missionresultsprocessor import MissionResultsProcessor

    wreck = _base("001 Liaoning", operational=False, sunk=True)
    aboard = _aboard(wreck, aircraft=4)
    processor = _processor(aboard)

    MissionResultsProcessor.commit_sunk_decks(processor, [])

    assert aboard.owned_aircraft == 4
    assert processor.messages == []


def test_nothing_is_bought_for_a_ship_that_has_sunk() -> None:
    from game.purchaseadapter import AircraftPurchaseAdapter

    wreck = _base("LHA-1 Tarawa", operational=False, sunk=True)
    wreck.coalition = SimpleNamespace()
    adapter = AircraftPurchaseAdapter(wreck)
    squadron = _aboard(wreck, aircraft=0)

    assert not adapter.can_buy(squadron)
    assert adapter.why_cannot_buy(squadron) == "LHA-1 Tarawa has sunk"
