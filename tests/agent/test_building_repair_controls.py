"""Building selection and refunds share the UI's per-building prices."""

from types import SimpleNamespace
import pickle
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from game.agent import planner, schemas, service, views
from game.buildingrepair import cancel_building_repairs, repair_refunds
from game.theater.player import Player
from game.theater.theatergroundobject import BuildingGroundObject
from game.theater.theatergroup import TheaterUnit


@pytest.fixture
def state(monkeypatch: Any) -> Any:
    units = [
        Mock(
            spec=TheaterUnit,
            id=i,
            name=f"Generator {i}",
            alive=False,
            repair_turns_remaining=None,
            repair_cost_paid=None,
        )
        for i in range(1, 4)
    ]
    cp = SimpleNamespace(captured=Player.RED, ground_objects=[])
    site = Mock(
        spec=BuildingGroundObject,
        id=uuid4(),
        name="Power",
        category="power",
        control_point=cp,
        statics=units,
        units=units,
        repairable=True,
    )
    site.repair_cost.return_value = 15.5
    site.name = "Power"
    for unit in units:
        unit.name = f"Generator {unit.id}"
    cp.ground_objects = [site]
    coalition = SimpleNamespace(budget=100.0)
    game = SimpleNamespace(
        coalition_for=lambda player: coalition,
        theater=SimpleNamespace(
            find_control_point_by_id=Mock(side_effect=KeyError), controlpoints=[cp]
        ),
        db=SimpleNamespace(tgos={site.id: site}),
        settings=SimpleNamespace(building_repair_turns=4),
    )
    events: list[Any] = []
    monkeypatch.setattr(planner, "_push_map_events", events.append)
    return SimpleNamespace(
        game=game, site=site, units=units, cp=cp, coalition=coalition, events=events
    )


def repair(state: Any, **kwargs: Any) -> Any:
    return planner.repair(state.game, "red", str(state.site.id), **kwargs)


def cancel(state: Any, ids: list[int] | None = None) -> Any:
    return planner.cancel_building_repair(state.game, "red", str(state.site.id), ids)


def test_quantity_repairs_only_one_at_the_full_unit_price(state: Any) -> None:
    assert repair(state, quantity=1).ok
    assert state.coalition.budget == 84.5
    assert [unit.repair_turns_remaining for unit in state.units] == [4, None, None]
    assert state.units[0].repair_cost_paid == 15.5
    assert len(state.events) == 1


def test_explicit_ids_and_default_batch_use_ui_unit_prices(state: Any) -> None:
    assert repair(state, unit_ids=[3]).ok
    assert state.units[2].repair_turns_remaining == 4
    assert repair(state).ok
    assert state.coalition.budget == 53.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": True},
        {"quantity": 4},
        {"unit_ids": []},
        {"unit_ids": [1, 1]},
        {"unit_ids": [1, 999]},
        {"unit_ids": [True]},
        {"quantity": 1, "unit_ids": [1]},
    ],
)
def test_invalid_selection_is_atomic(state: Any, kwargs: Any) -> None:
    assert not repair(state, **kwargs).ok
    assert state.coalition.budget == 100
    assert all(unit.repair_turns_remaining is None for unit in state.units)
    assert not state.events


def test_explicit_selection_requires_the_whole_selected_budget(state: Any) -> None:
    state.coalition.budget = 20
    assert not repair(state, unit_ids=[1, 2]).ok
    assert state.coalition.budget == 20
    assert repair(state).ok  # Legacy callers still repair an affordable subset.
    assert state.coalition.budget == 4.5


def test_exact_budget_is_accepted(state: Any) -> None:
    state.coalition.budget = 15.5
    assert repair(state, quantity=1).ok
    assert state.coalition.budget == 0


def test_cancel_one_then_all_refunds_actual_payments_once(state: Any) -> None:
    assert repair(state).ok
    state.site.repair_cost.return_value = 200  # Later settings do not inflate refunds.
    assert cancel(state, [2]).ok
    assert state.coalition.budget == 69
    assert state.units[1].repair_turns_remaining is None
    assert not state.units[1].alive
    assert not cancel(state, [2]).ok
    assert cancel(state).ok
    assert state.coalition.budget == 100
    assert not cancel(state).ok
    assert state.coalition.budget == 100


@pytest.mark.parametrize("ids", [[], [1, 1], [1, 999], [True]])
def test_invalid_cancellation_does_not_refund_or_modify_work(
    state: Any, ids: Any
) -> None:
    assert repair(state).ok
    assert not cancel(state, ids).ok
    assert state.coalition.budget == 53.5
    assert all(unit.repair_turns_remaining == 4 for unit in state.units)


@pytest.mark.parametrize("owner", [Player.BLUE, Player.NEUTRAL])
def test_other_owners_cannot_be_repaired_or_refunded(state: Any, owner: Any) -> None:
    assert repair(state).ok
    state.cp.captured = owner
    assert not cancel(state).ok
    assert not repair(state).ok
    assert state.coalition.budget == 53.5
    assert views.build_repairs(state.game, "red") == []


def test_completed_work_cannot_be_refunded(state: Any) -> None:
    assert repair(state, quantity=1).ok
    state.units[0].alive = True
    assert not cancel(state, [1]).ok
    assert state.coalition.budget == 84.5


def test_disabled_repairs_can_still_be_cancelled(state: Any) -> None:
    assert repair(state, quantity=1).ok
    state.game.settings.building_repair_turns = -1
    assert not repair(state, quantity=1).ok
    assert cancel(state).ok
    assert state.coalition.budget == 100


def test_instant_repair_has_no_refundable_job(state: Any) -> None:
    state.game.settings.building_repair_turns = 0

    def revive(events: Any) -> None:
        state.units[0].alive = True

    state.units[0].revive.side_effect = revive
    assert repair(state, quantity=1).ok
    assert state.units[0].alive
    assert state.units[0].repair_turns_remaining is None
    assert not cancel(state).ok
    assert state.coalition.budget == 84.5


def test_pending_only_sites_remain_discoverable_with_ids_and_refunds(
    state: Any,
) -> None:
    assert repair(state).ok
    view = views.build_repairs(state.game, "red")[0]
    assert view.cost == 0
    assert view.pending_refund == 46.5
    assert view.buildings is not None
    assert [unit.id for unit in view.buildings] == [1, 2, 3]
    assert all(unit.turns_remaining == 4 for unit in view.buildings)


def test_legacy_batch_never_refunds_more_than_one_site_price(state: Any) -> None:
    for unit in state.units:
        unit.repair_turns_remaining = 2
        del unit.repair_cost_paid
    assert sum(repair_refunds(state.site).values()) == pytest.approx(15.5)
    first = cancel_building_repairs(state.site, [state.units[0]])
    rest = cancel_building_repairs(state.site, state.units[1:])
    assert first + rest == pytest.approx(15.5)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_rest_rejects_invalid_quantity(quantity: Any) -> None:
    with pytest.raises(ValidationError):
        schemas.RepairRequest(id="site", quantity=quantity)


def test_cancel_service_is_red_only() -> None:
    with pytest.raises(service.SideNotAllowedError):
        service.cancel_building_repair("blue", "site")


def test_automatic_repairs_record_refundable_payments(state: Any) -> None:
    from game.procurement import ProcurementAi

    state.game.settings.building_repair_budget_percent = 100
    state.game.get_destroyed_units = lambda: []
    state.game.message = Mock()
    for unit in state.units:
        unit.ground_object = state.site
    ai: Any = SimpleNamespace(
        game=state.game,
        owned_points=[state.cp],
        is_player=Player.RED,
        building_repair_priority=lambda site: 1,
    )
    remaining = ProcurementAi.repair_buildings(ai, 100)
    assert remaining == 53.5
    assert sum(repair_refunds(state.site).values()) == 46.5


def test_rest_transports_forward_building_selection(monkeypatch: Any) -> None:
    from game.server.retributionai import routes

    repair_call = Mock(return_value=schemas.OpResult(ok=True))
    cancel_call = Mock(return_value=schemas.OpResult(ok=True))
    monkeypatch.setattr(service, "repair", repair_call)
    monkeypatch.setattr(service, "cancel_building_repair", cancel_call)
    routes.repair(schemas.RepairRequest(id="site", quantity=1))
    repair_call.assert_called_once_with("red", "site", 1, None)
    routes.cancel_building_repair(
        schemas.CancelBuildingRepairRequest(id="site", unit_ids=[2])
    )
    cancel_call.assert_called_once_with("red", "site", [2])


def test_receipts_survive_save_round_trips_and_old_units_have_a_default() -> None:
    unit = TheaterUnit.__new__(TheaterUnit)
    unit.repair_turns_remaining = 3
    unit.repair_cost_paid = 12.5
    restored = pickle.loads(pickle.dumps(unit))
    assert restored.repair_cost_paid == 12.5
    del unit.repair_cost_paid
    legacy = pickle.loads(pickle.dumps(unit))
    assert legacy.repair_cost_paid is None
