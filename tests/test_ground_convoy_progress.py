"""Distance-based convoy progress preserves cargo, ownership and separate cohorts."""

from __future__ import annotations

from datetime import datetime
import math
import pickle
from types import SimpleNamespace
from typing import Any

from dcs import Mission
from dcs.countries import USA
from dcs.mapping import Point
from dcs.terrain import Caucasus
import pytest

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment
from game.groundmovement.orders import GroundPosition
from game.groundmovement.settings import METERS_PER_MILE, set_enabled
from game.missiongenerator.convoygenerator import ConvoyGenerator
from game.settings import Settings
from game.sim import GameUpdateEvents
from game.theater.base import Base
from game.theater.player import Player
from game.theater.transitnetwork import TransitNetwork
from game.transfers import Convoy, ConvoyMap, PendingTransfers, TransferOrder
from game.unitmap import UnitMap


class _CP:
    def __init__(self, game: Any, name: str, x: float) -> None:
        self.game = game
        self.name = name
        self.position = Point(x, 630000, game.theater.terrain)
        self.captured = Player.BLUE
        self.base = Base()
        self.ground_objects: list[Any] = []
        self.convoy_routes: dict[Any, tuple[Point, ...]] = {}
        self.convoy_spawns: dict[Any, tuple[Point, ...]] = {}

    def __str__(self) -> str:
        return self.name

    @property
    def coalition(self) -> Any:
        return self.game.coalition_for(self.captured)

    def is_friendly(self, player: Player) -> bool:
        return self.captured == player

    def convoy_route_to(self, other: Any) -> tuple[Point, ...]:
        return self.convoy_routes[other]

    def convoy_origin_for(self, other: Any) -> Point:
        return self.convoy_route_to(other)[0]


class _Game:
    def __init__(self) -> None:
        self.settings = Settings()
        set_enabled(self.settings, True)
        self.turn = 0
        self.theater = SimpleNamespace(terrain=Caucasus())
        self.network = TransitNetwork()
        self.blue = SimpleNamespace(
            game=self,
            faction=SimpleNamespace(country=USA(), liveries_overrides_ground_forces={}),
        )
        self.red = SimpleNamespace(
            game=self,
            faction=SimpleNamespace(country=USA(), liveries_overrides_ground_forces={}),
        )
        self.blue.opponent, self.red.opponent = self.red, self.blue
        self.blue.transfers = PendingTransfers(self, Player.BLUE)  # type: ignore[arg-type]
        self.red.transfers = PendingTransfers(self, Player.RED)  # type: ignore[arg-type]

    def coalition_for(self, player: Player) -> Any:
        return self.blue if player is Player.BLUE else self.red

    def transit_network_for(self, player: Player) -> TransitNetwork:
        return self.network


@pytest.fixture
def world() -> Any:
    game = _Game()
    a = _CP(game, "A", -318000)
    b = _CP(game, "B", a.position.x + 300 * METERS_PER_MILE)
    a.convoy_routes[b] = (a.position, b.position)
    b.convoy_routes[a] = (b.position, a.position)
    game.network.link_road(a, b)  # type: ignore[arg-type]
    game.theater.controlpoints = [a, b]
    truck = GroundUnitType.named("Truck Ural-375")
    a.base.commission_units({truck: 10})
    return SimpleNamespace(
        game=game, a=a, b=b, truck=truck, pending=game.blue.transfers
    )


def _order(world: Any, count: int = 2) -> TransferOrder:
    order = TransferOrder(world.a, world.b, {world.truck: count}, Player.BLUE)
    world.pending.new_transfer(order, datetime(2026, 1, 1), GameUpdateEvents())
    return order


def _advance(world: Any) -> None:
    world.game.turn += 1
    world.pending.perform_transfers(GameUpdateEvents())


def test_mixed_route_spends_one_shared_turn_and_preview_never_advances() -> None:
    route = GroundRoute(
        (
            GroundSegment(GroundPosition(0, 0), GroundPosition(100, 0)),
            GroundSegment(GroundPosition(100, 0), GroundPosition(100, 30), False),
        )
    )
    journey = GroundJourney(route)
    assert journey.preview(120, 60)[-1].z == pytest.approx(10)
    assert journey.position == GroundPosition(0, 0) and journey.last_advanced_turn == -1
    journey.advance(1, 120, 60)
    assert journey.position.z == pytest.approx(10)
    assert journey.remaining_distance == pytest.approx(20)
    same = pickle.loads(pickle.dumps(journey))
    same.advance(1, 120, 60)
    assert same.position == journey.position
    same.advance(2, 120, 60)
    assert same.completed and same.position == GroundPosition(100, 30)


@pytest.mark.parametrize("budget", [0, -1, True, math.inf, math.nan])
def test_invalid_budget_does_not_mutate_progress(budget: Any) -> None:
    journey = GroundJourney(
        GroundRoute.from_points([GroundPosition(0, 0), GroundPosition(100, 0)])
    )
    with pytest.raises(ValueError):
        journey.advance(1, budget, 60)
    assert journey.last_advanced_turn == -1 and journey.travelled_distance == 0


def test_long_convoy_advances_once_per_turn_and_commissions_once(world: Any) -> None:
    order = _order(world)
    convoy = order.transport
    assert isinstance(convoy, Convoy)
    assert world.a.base.armor[world.truck] == 8
    for turn, miles in ((1, 120), (2, 240)):
        _advance(world)
        assert convoy.position.x == pytest.approx(
            world.a.position.x + miles * METERS_PER_MILE
        )
        assert order.position is world.a and not order.completed
        world.pending.perform_transfers(GameUpdateEvents())
        assert convoy.ground_journey is not None
        assert convoy.ground_journey.travelled_distance == pytest.approx(
            miles * METERS_PER_MILE
        )
        assert not world.b.base.armor
    _advance(world)
    assert order.completed and order.transport is None
    assert world.b.base.armor[world.truck] == 2
    assert not list(world.pending.convoys) and not world.pending.pending_transfers
    world.pending.perform_transfers(GameUpdateEvents())
    assert world.b.base.armor[world.truck] == 2


def test_new_departures_do_not_join_a_convoy_already_on_the_road(world: Any) -> None:
    first = _order(world)
    convoy = first.transport
    _advance(world)
    second = _order(world, 1)
    assert second.transport is not convoy
    assert len(list(world.pending.convoys)) == 2
    _advance(world)
    assert isinstance(convoy, Convoy) and isinstance(second.transport, Convoy)
    assert convoy.position.x - second.transport.position.x == pytest.approx(
        120 * METERS_PER_MILE
    )
    _advance(world)
    assert world.b.base.armor[world.truck] == 2 and not second.completed
    _advance(world)
    assert world.b.base.armor[world.truck] == 3 and world.a.base.armor[world.truck] == 7


def test_orders_at_the_same_start_merge_and_advance_only_once(world: Any) -> None:
    first, second = _order(world), _order(world, 1)
    assert first.transport is second.transport
    _advance(world)
    convoy = first.transport
    assert isinstance(convoy, Convoy) and convoy.ground_journey is not None
    assert convoy.ground_journey.travelled_distance == pytest.approx(
        120 * METERS_PER_MILE
    )
    assert convoy.size == 3


def test_pause_and_save_load_keep_position_and_cargo(world: Any) -> None:
    order = _order(world)
    _advance(world)
    set_enabled(world.game.settings, False)
    saved = pickle.loads(pickle.dumps(world))
    convoy = saved.pending.pending_transfers[0].transport
    before = convoy.position.x
    _advance(saved)
    assert convoy.position.x == before and convoy.size == 2
    assert convoy.movement_info()["status"] == "paused"
    set_enabled(saved.game.settings, True)
    _advance(saved)
    assert convoy.position.x == pytest.approx(before + 120 * METERS_PER_MILE)


def test_casualties_are_removed_before_arrival_and_dead_orders_leave_no_alias(
    world: Any,
) -> None:
    first, second = _order(world), _order(world, 1)
    convoy = first.transport
    assert isinstance(convoy, Convoy)
    convoy.kill_unit(world.truck)
    convoy.kill_unit(world.truck)
    assert first.size == 0 and second.size == 1
    _advance(world)
    assert convoy.transfers == [second] and world.pending.pending_transfers == [second]
    _advance(world)
    _advance(world)
    assert world.b.base.armor[world.truck] == 1


def test_origin_capture_does_not_change_convoy_owner_or_stop_recovery(
    world: Any,
) -> None:
    order = _order(world)
    _advance(world)
    world.a.captured = Player.RED
    convoy = order.transport
    assert isinstance(convoy, Convoy)
    assert convoy.player_owned is Player.BLUE and convoy.is_friendly(Player.BLUE)
    assert convoy.coalition is world.game.blue
    _advance(world)
    _advance(world)
    assert world.b.base.armor[world.truck] == 2


def test_destination_capture_pauses_without_deleting_or_commissioning(
    world: Any,
) -> None:
    order = _order(world)
    _advance(world)
    convoy = order.transport
    assert isinstance(convoy, Convoy)
    before = convoy.position.x
    world.b.captured = Player.RED
    _advance(world)
    assert convoy.position.x == before and convoy.size == 2
    assert "friendly" in convoy.movement_summary()
    assert not world.b.base.armor and world.a.base.armor[world.truck] == 8
    world.b.captured = Player.BLUE
    _advance(world)
    assert convoy.position.x == pytest.approx(before + 120 * METERS_PER_MILE)


def test_midroad_cancel_cannot_teleport_cargo_back_to_origin(world: Any) -> None:
    order = _order(world)
    _advance(world)
    with pytest.raises(ValueError, match="cannot return instantly"):
        world.pending.cancel_transfer(order, GameUpdateEvents())
    assert world.a.base.armor[world.truck] == 8 and order.size == 2


def test_midroad_cancel_warns_without_removing_a_qt_row(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from qt_ui.models import TransferModel

    app = QApplication.instance() or QApplication([])
    order = _order(world)
    _advance(world)
    model = TransferModel(SimpleNamespace(game=world.game))  # type: ignore[arg-type]
    removals: list[int] = []
    warnings: list[str] = []
    model.rowsAboutToBeRemoved.connect(lambda *_args: removals.append(1))
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text)
    )

    model.cancel_transfer(order)

    assert app is not None and model.rowCount() == 1
    assert removals == [] and len(warnings) == 1
    assert "cannot return instantly" in warnings[0]
    assert order in world.pending.pending_transfers


def test_invalid_route_keeps_units_at_origin_and_reports_why(world: Any) -> None:
    world.a.convoy_routes[world.b] = (world.a.position, world.a.position)
    order = _order(world)
    assert not order.departed and order.transport is None
    assert world.a.base.armor[world.truck] == 10
    assert "valid campaign road route" in order.description


def test_disabled_plugin_keeps_legacy_convoy_arrival(world: Any) -> None:
    set_enabled(world.game.settings, False)
    order = _order(world)
    _advance(world)
    assert order.completed and world.b.base.armor[world.truck] == 2


def test_enabling_plugin_adopts_an_existing_convoy_without_advancing_on_plan(
    world: Any,
) -> None:
    set_enabled(world.game.settings, False)
    order = _order(world)
    convoy = order.transport
    assert isinstance(convoy, Convoy) and not convoy.ground_managed
    set_enabled(world.game.settings, True)
    world.pending.plan_transports(datetime(2026, 1, 1), GameUpdateEvents())
    assert convoy.ground_journey is not None
    assert convoy.ground_journey.travelled_distance == 0
    assert world.a.base.armor[world.truck] == 8
    _advance(world)
    assert convoy.ground_journey.travelled_distance == pytest.approx(
        120 * METERS_PER_MILE
    )
    assert not order.completed and not world.b.base.armor


def test_destroyed_convoy_is_removed_without_delivering_or_refunding(
    world: Any,
) -> None:
    order = _order(world)
    _advance(world)
    convoy = order.transport
    assert isinstance(convoy, Convoy)
    convoy.kill_all()
    _advance(world)
    assert not list(world.pending.convoys) and not world.pending.pending_transfers
    assert order.transport is None and order.completed
    assert world.a.base.armor[world.truck] == 8 and not world.b.base.armor


def test_regenerated_mission_uses_saved_position_and_does_not_advance(
    world: Any,
) -> None:
    order = _order(world)
    _advance(world)
    convoy = order.transport
    assert isinstance(convoy, Convoy) and convoy.ground_journey is not None
    before = pickle.dumps(convoy.ground_journey)
    for _ in range(2):
        mission = Mission()
        group = ConvoyGenerator(mission, world.game, UnitMap()).generate_convoy(convoy)
        assert group.units[0].position.x == pytest.approx(convoy.position.x)
        assert group.units[1].position.x == pytest.approx(convoy.position.x - 20)
        assert group.points[-1].position.x <= world.a.position.x + 240 * METERS_PER_MILE
        assert pickle.dumps(convoy.ground_journey) == before
    set_enabled(world.game.settings, False)
    group = ConvoyGenerator(Mission(), world.game, UnitMap()).generate_convoy(convoy)
    assert len(group.points) == 1 and group.points[0].speed == 0


def test_old_convoy_map_save_initializes_empty_transit_list() -> None:
    result = ConvoyMap.__new__(ConvoyMap)
    result.__setstate__({"transports": {}})
    assert result.in_transit == [] and list(result) == []


def test_intermediate_base_remains_a_stop_and_cancel_refunds_there(world: Any) -> None:
    c = _CP(world.game, "C", world.b.position.x + 300 * METERS_PER_MILE)
    world.b.convoy_routes[c] = (world.b.position, c.position)
    c.convoy_routes[world.b] = (c.position, world.b.position)
    world.game.network.link_road(world.b, c)
    order = TransferOrder(world.a, c, {world.truck: 2}, Player.BLUE)  # type: ignore[arg-type]
    world.pending.new_transfer(order, datetime(2026, 1, 1), GameUpdateEvents())
    for _ in range(3):
        _advance(world)
    assert order.position is world.b and not order.completed
    assert order.transport is None and not world.b.base.armor
    world.pending.plan_transports(datetime(2026, 1, 1), GameUpdateEvents())
    convoy = getattr(order, "transport")
    assert isinstance(convoy, Convoy) and convoy.ground_journey is not None
    world.pending.perform_transfers(GameUpdateEvents())
    assert convoy.ground_journey.travelled_distance == 0
    world.pending.cancel_transfer(order, GameUpdateEvents())
    assert world.b.base.armor[world.truck] == 2 and world.a.base.armor[world.truck] == 8


def test_shipping_retains_legacy_one_leg_per_turn(world: Any) -> None:
    world.game.network.link_shipping(world.a, world.b)
    order = _order(world)
    assert not isinstance(order.transport, Convoy)
    _advance(world)
    assert order.completed and world.b.base.armor[world.truck] == 2


def test_supply_routes_include_old_and_new_departures_and_api_reports_progress(
    world: Any,
) -> None:
    from game.agent.views import build_ground_convoys, _build_transport_targets
    from game.server.supplyroutes.models import TransportFinder

    order = _order(world)
    _advance(world)
    _order(world, 1)
    finder = TransportFinder(world.game, world.a, world.b)
    descriptions = finder.describe_active_transports(False)
    assert len(descriptions) == 2
    assert any("40%" in line for line in descriptions)
    own = build_ground_convoys(world.game, "blue")
    assert own is not None and len(own) == 2
    assert {row.movement.progress_percent for row in own} == {0, 40}
    assert build_ground_convoys(world.game, "red") is None
    targets = _build_transport_targets(world.game, Player.RED)
    convoy = order.transport
    assert isinstance(convoy, Convoy)
    moving = next(row for row in targets if row.id == convoy.name)
    assert moving.ground_movement is not None
    assert moving.ground_movement.progress_percent == 40
    assert moving.pos == next(row for row in own if row.name == convoy.name).pos
