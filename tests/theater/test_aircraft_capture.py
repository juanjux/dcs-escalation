"""Captured aircraft leave the old inventory without repeated sale proceeds."""

from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest
from dcs import Mission, Point
from dcs.terrain import Caucasus

from game import aircraftmaintenance
from game.missiongenerator.aircraft.aircraftgenerator import AircraftGenerator
from game.migrator import Migrator
from game.purchaseadapter import AircraftPurchaseAdapter
from game.settings import Settings
from game.squadrons.squadron import Squadron
from game.theater.controlpoint import ControlPoint, Fob
from game.theater.player import Player


@pytest.fixture(params=[Player.BLUE, Player.RED])
def capture(request: pytest.FixtureRequest) -> Any:
    owner = request.param
    enemy = Player.RED if owner is Player.BLUE else Player.BLUE
    coalitions = {
        side: SimpleNamespace(
            player=side, budget=100.0, ato=SimpleNamespace(packages=[])
        )
        for side in (owner, enemy)
    }
    game: Any = SimpleNamespace(
        settings=Settings(),
        coalitions=list(coalitions.values()),
        messages=[],
        high_command_for=lambda side: SimpleNamespace(loans=[]),
    )
    game.message = lambda *args: game.messages.append(args)
    game.adjust_budget = lambda value, player: setattr(
        coalitions[player], "budget", coalitions[player].budget + value
    )
    for side, coalition in coalitions.items():
        coalition.game = game
        coalition.adjust_budget = lambda value, side=side: game.adjust_budget(
            value, side
        )
        coalition.air_wing = SimpleNamespace(iter_squadrons=lambda: iter(()))
    base: Any = SimpleNamespace(
        name="Captured base",
        captured=owner,
        last_capture_turn=3,
        coalition=coalitions[owner],
        aircraft_retreat_destination=lambda squadron: None,
    )
    base.is_friendly = lambda side: base.captured is side
    base.capture_aircraft = lambda game, airframe, count: ControlPoint.capture_aircraft(
        base, game, airframe, count
    )
    squadron: Any = SimpleNamespace(
        player=owner,
        coalition=coalitions[owner],
        location=base,
        aircraft=SimpleNamespace(price=5, display_name="Mi-8"),
        aircraft_repairs=[],
        owned_aircraft=2,
        untasked_aircraft=2,
        pending_deliveries=0,
        pending_sale_values=[],
        morale_in_play=False,
        active_pilots=[],
        current_roster=[object(), object()],
    )
    squadron.refund_orders = lambda: Squadron.refund_orders(squadron)
    coalitions[owner].air_wing = SimpleNamespace(
        iter_squadrons=lambda: iter([squadron])
    )
    migrator = Migrator.__new__(Migrator)
    migrator.game = game
    return SimpleNamespace(
        game=game,
        base=base,
        sq=squadron,
        owner=coalitions[owner],
        enemy=coalitions[enemy],
        migrator=migrator,
    )


@pytest.mark.parametrize("pending", [0, 1, -1])
def test_no_retreat_clears_inventory_and_pays_capture_once(
    capture: Any, pending: int
) -> None:
    capture.sq.pending_deliveries = pending
    if pending < 0:
        capture.sq.pending_sale_values = [4.25]
    roster = list(capture.sq.current_roster)
    ControlPoint._retreat_squadron(capture.base, capture.game, capture.sq)
    assert capture.sq.owned_aircraft == capture.sq.untasked_aircraft == 0
    assert capture.sq.pending_deliveries == 0
    assert capture.enemy.budget == pytest.approx(108.5)
    refund = 5 if pending > 0 else -4.25 if pending < 0 else 0
    assert capture.owner.budget == pytest.approx(100 + refund)
    assert capture.sq.current_roster == roster
    assert not AircraftPurchaseAdapter(capture.base).can_sell(capture.sq)
    Squadron.return_all_pilots_and_aircraft(capture.sq)
    assert capture.sq.untasked_aircraft == 0
    ControlPoint._retreat_squadron(capture.base, capture.game, capture.sq)
    assert capture.enemy.budget == pytest.approx(108.5)
    assert len(capture.game.messages) == 1


def test_damaged_aircraft_are_written_off_not_sold_again(capture: Any) -> None:
    capture.sq.aircraft_repairs = [object()]
    ControlPoint._retreat_squadron(capture.base, capture.game, capture.sq)
    assert capture.sq.owned_aircraft == capture.sq.untasked_aircraft == 0
    assert not aircraftmaintenance.repairs(capture.sq)
    assert capture.sq.destroyed_aircraft == 1
    assert capture.enemy.budget == pytest.approx(104.25)
    assert capture.owner.budget == 100


def test_captured_aircraft_are_not_spawned_in_a_test_mission(
    capture: Any, tmp_path: Path
) -> None:
    ControlPoint._retreat_squadron(capture.base, capture.game, capture.sq)
    terrain = Caucasus()
    theater: Any = SimpleNamespace(terrain=terrain)
    capture.sq.location = Fob(
        "Captured base",
        Point(0, 0, terrain),
        theater,
        capture.enemy.player,
    )
    mission = Mission()
    country = mission.country("USA")
    generator: Any = SimpleNamespace(game=capture.game, mission=mission)
    AircraftGenerator._spawn_unused_for(generator, capture.sq, country)
    assert not country.helicopter_group and not country.plane_group
    mission.save(str(tmp_path / "captured-aircraft.miz"))


def test_legacy_captured_inventory_is_removed_without_another_payment(
    capture: Any,
) -> None:
    capture.base.captured = capture.enemy.player
    roster = list(capture.sq.current_roster)
    capture.migrator._remove_captured_aircraft()
    assert capture.sq.owned_aircraft == capture.sq.untasked_aircraft == 0
    assert capture.sq.current_roster == roster
    assert capture.owner.budget == capture.enemy.budget == 100
    assert not capture.game.messages
    capture.migrator._remove_captured_aircraft()
    assert capture.owner.budget == capture.enemy.budget == 100


@pytest.mark.parametrize("pending", [1, -1])
def test_legacy_cleanup_cancels_only_outstanding_orders(
    capture: Any, pending: int
) -> None:
    capture.base.captured = capture.enemy.player
    capture.sq.pending_deliveries = pending
    if pending < 0:
        capture.sq.pending_sale_values = [4.25]
    capture.migrator._remove_captured_aircraft()
    assert capture.sq.pending_deliveries == capture.sq.owned_aircraft == 0
    assert capture.owner.budget == pytest.approx(105 if pending > 0 else 95.75)
    assert capture.enemy.budget == 100
    capture.migrator._remove_captured_aircraft()
    assert capture.owner.budget == pytest.approx(105 if pending > 0 else 95.75)


@pytest.mark.parametrize("reason", ["friendly", "unrecorded", "neutral", "flights"])
def test_legacy_cleanup_preserves_unrelated_or_active_inventory(
    capture: Any, reason: str
) -> None:
    capture.base.captured = capture.enemy.player
    if reason == "friendly":
        capture.base.captured = capture.owner.player
    elif reason == "unrecorded":
        del capture.base.last_capture_turn
    elif reason == "neutral":
        capture.base.captured = Player.NEUTRAL
    else:
        capture.owner.ato.packages = [
            SimpleNamespace(flights=[SimpleNamespace(squadron=capture.sq)])
        ]
    capture.migrator._remove_captured_aircraft()
    assert capture.sq.owned_aircraft == capture.sq.untasked_aircraft == 2
    assert capture.owner.budget == capture.enemy.budget == 100
