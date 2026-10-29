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
from game.purchaseadapter import AircraftPurchaseAdapter
from game.theater.controlpoint import NavalControlPoint
from game.squadrons.squadron import Squadron
from game.theater import Player
from game.utils import nautical_miles

NOW = datetime(2026, 9, 21, 20, 0)


class _Base(SimpleNamespace):
    def __str__(self) -> str:
        return str(self.name)


class _Squadron(SimpleNamespace):
    expected_size_next_turn = Squadron.expected_size_next_turn


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
    return _Squadron(
        player=Player.BLUE,
        location=location,
        destination=None,
        owned_aircraft=aircraft,
        untasked_aircraft=aircraft,
        pending_deliveries=0,
        aircraft=SimpleNamespace(
            helicopter=False, lha_capable=False, flyable=False, price=10
        ),
        coalition=SimpleNamespace(
            game=SimpleNamespace(
                settings=SimpleNamespace(ground_start_ai_planes=True),
                high_command_for=lambda side: SimpleNamespace(loans=[]),
            )
        ),
        replan_ferry_flights=planned.append,
        planned=planned,
    )


def _sell(squadron: Any, quantity: int) -> AircraftPurchaseAdapter:
    coalition = squadron.coalition
    coalition.budget = 0
    coalition.adjust_budget = lambda amount: setattr(
        coalition, "budget", coalition.budget + amount
    )
    squadron.location.coalition = coalition
    adapter = AircraftPurchaseAdapter(squadron.location)
    adapter.sell(squadron, quantity)
    return adapter


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


def test_selling_all_aircraft_allows_relocation_without_ferries() -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=4)
    _sell(squadron, 4)
    squadron.cancel_ferry_flights = lambda: None
    squadron.plan_ferry_flights = lambda now: Squadron.plan_ferry_flights(squadron, now)
    squadron.replan_ferry_flights = lambda now: Squadron.replan_ferry_flights(
        squadron, now
    )
    destination = _base("Destination", operational=True)

    Squadron.plan_relocation(squadron, destination, NOW)

    assert squadron.destination is destination
    assert squadron.owned_aircraft == 4
    assert squadron.pending_deliveries == -4
    assert squadron.untasked_aircraft == 0
    assert squadron.coalition.budget == 40


@pytest.mark.parametrize("sold", [0, 1, 3])
def test_partial_sales_do_not_allow_relocation_off_a_damaged_runway(sold: int) -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=4)
    _sell(squadron, sold)

    with pytest.raises(RuntimeError, match="runway is damaged"):
        Squadron.plan_relocation(squadron, _base("Destination", True), NOW)

    assert squadron.destination is None
    assert squadron.planned == []


def test_buying_back_a_sold_aircraft_blocks_relocation_again() -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=4)
    adapter = _sell(squadron, 4)
    adapter.buy(squadron, 1)

    with pytest.raises(RuntimeError, match="runway is damaged"):
        Squadron.plan_relocation(squadron, _base("Destination", True), NOW)

    assert squadron.pending_deliveries == -3
    assert squadron.untasked_aircraft == 1
    assert squadron.coalition.budget == 30


def test_pending_purchases_do_not_need_a_runway_to_relocate() -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=0)
    squadron.pending_deliveries = 2
    destination = _base("Destination", True)

    Squadron.plan_relocation(squadron, destination, NOW)

    assert squadron.destination is destination


def test_existing_flights_do_not_make_a_squadron_empty() -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=4)
    squadron.untasked_aircraft = 0

    with pytest.raises(RuntimeError, match="runway is damaged"):
        Squadron.plan_relocation(squadron, _base("Destination", True), NOW)


def test_loading_preserves_an_empty_relocation_after_pending_sales() -> None:
    squadron = _squadron(_base("Origin", operational=False), aircraft=4)
    _sell(squadron, 4)
    destination = _base("Destination", True)
    squadron.destination = destination
    cancelled: list[Any] = []
    squadron.cancel_ferry_flights = lambda: cancelled.append(squadron)
    wing = SimpleNamespace(iter_squadrons=lambda: iter([squadron]))
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(
        blue=SimpleNamespace(air_wing=wing),
        red=SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter([]))),
    )

    migrator._cancel_relocations_off_damaged_runways()

    assert squadron.destination is destination
    assert cancelled == []


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


class _Ship(_Base):
    """A carrier or LHA, with the real code for what sinking does."""

    sink = NavalControlPoint.sink
    _divert = NavalControlPoint._divert


def _theater(*squadrons: Any, bases: tuple[Any, ...] = ()) -> Any:
    messages: list[tuple[str, str]] = []
    wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    game = SimpleNamespace(
        theater=SimpleNamespace(controlpoints=list(bases)),
        message=lambda title, text: messages.append((title, text)),
    )
    return SimpleNamespace(game=game, air_wing=wing, messages=messages)


def _ship(coalition: Any) -> Any:
    return _Ship(name="LHA-1 Tarawa", sunk=True, captured="blue", coalition=coalition)


def _ashore(name: str, nm: float, room: int, side: str = "blue") -> Any:
    base = _base(name, operational=True)
    base.captured = side
    base.distance_to = lambda other: nm * 1852
    base.unclaimed_parking = lambda parking_type: room
    return base


def _embarked(ship: Any, aircraft: int, tasked: int) -> Any:
    squadron = _squadron(ship, aircraft)
    squadron.untasked_aircraft = aircraft - tasked
    squadron.pending_deliveries = 0
    squadron.destroyed_aircraft = 0
    squadron.aircraft = _Base(
        name="UH-1H Iroquois",
        helicopter=True,
        lha_capable=True,
        flyable=False,
        max_mission_range=nautical_miles(100),
    )
    squadron.refund_orders = lambda: None

    def relocate_to(base: Any) -> None:
        squadron.location = base

    squadron.relocate_to = relocate_to
    return squadron


EVENTS: Any = SimpleNamespace(update_control_point=lambda cp: None)


def test_a_ship_that_sinks_takes_down_only_what_no_package_had() -> None:
    """The rest were in the air: they land ashore, and the squadron moves there."""
    coalition = _theater()
    ship = _ship(coalition)
    near = _ashore("Mount Pleasant", nm=60, room=10)
    far = _ashore("Rio Gallegos", nm=150, room=10)
    theirs = _ashore("Stanley", nm=20, room=10, side="red")
    coalition.game.theater.controlpoints = [ship, theirs, far, near]
    squadron = _embarked(ship, aircraft=6, tasked=2)
    inbound = _embarked(near, aircraft=4, tasked=0)
    inbound.destination = ship
    coalition.air_wing = SimpleNamespace(iter_squadrons=lambda: iter([inbound]))
    ship.squadrons = [squadron]

    ship.sink(EVENTS)

    assert (squadron.owned_aircraft, squadron.destroyed_aircraft) == (2, 4)
    assert squadron.location is near
    assert inbound.destination is None
    assert coalition.messages == [
        (
            "LHA-1 Tarawa sunk",
            f"{squadron} (UH-1H Iroquois): 4 went down with it; 2 in the air landed"
            " at Mount Pleasant. Its pilots survived.",
        )
    ]


def test_with_nowhere_to_land_the_ones_in_the_air_ditch() -> None:
    coalition = _theater()
    ship = _ship(coalition)
    ship.squadrons = [squadron := _embarked(ship, aircraft=3, tasked=3)]
    coalition.game.theater.controlpoints = [ship, _ashore("Far", nm=500, room=10)]

    ship.sink(EVENTS)

    assert (squadron.owned_aircraft, squadron.destroyed_aircraft) == (0, 3)
    assert squadron.location is ship
    # Empty, with its pilots: it can relocate.
    Squadron.plan_relocation(squadron, _base("Mount Pleasant", True), NOW)


def test_the_squadron_is_not_disbanded_when_its_carrier_is_killed() -> None:
    """The ship dying sinks the deck once; an escort dying after it does not."""
    from game.theater.theatergroup import TheaterUnit

    class _Deck:
        def __init__(self) -> None:
            self.sank: list[Any] = []

        @property
        def sunk(self) -> bool:
            return not carrier.alive

        def sink(self, events: Any) -> None:
            self.sank.append(events)

    deck = _Deck()
    group: Any = SimpleNamespace(
        is_naval_control_point=True,
        control_point=deck,
        is_iads=False,
        invalidate_threat_poly=lambda: None,
    )
    carrier: Any = SimpleNamespace(alive=True, ground_object=group)
    escort: Any = SimpleNamespace(alive=True, ground_object=group)
    events: Any = SimpleNamespace(update_tgo=lambda tgo: None)

    TheaterUnit.kill(carrier, events)
    TheaterUnit.kill(escort, events)

    assert deck.sank == [events]


def test_nothing_is_bought_for_a_ship_that_has_sunk() -> None:
    from game.purchaseadapter import AircraftPurchaseAdapter

    wreck = _base("LHA-1 Tarawa", operational=False, sunk=True)
    wreck.coalition = SimpleNamespace()
    adapter = AircraftPurchaseAdapter(wreck)
    squadron = _embarked(wreck, aircraft=0, tasked=0)

    assert not adapter.can_buy(squadron)
    assert adapter.why_cannot_buy(squadron) == "LHA-1 Tarawa has sunk"
