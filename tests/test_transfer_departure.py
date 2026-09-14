"""Units leave their base when a transport turns up, not when the order is written.

A transfer waiting for a lift it does not have used to debit its origin anyway. The
units were then in limbo: absent from the books, so the ground war was resolved without
them, while the mission still put them on the map. They stay at the origin now until
something can actually carry them.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from game.theater.controlpoint import ControlPoint, GroundUnitAllocations
from game.sim import GameUpdateEvents
from game.transfers import TransferOrder, PendingTransfers


def _transfer(
    origin: Any, destination: Any, units: dict[Any, int], departed: bool
) -> Any:
    return SimpleNamespace(
        origin=origin,
        destination=destination,
        units=units,
        departed=departed,
        transport=None,
    )


def test_a_transfer_that_never_left_gives_nothing_back() -> None:
    """Cancelling it must not commission units that were never debited."""
    origin = MagicMock()
    orders = PendingTransfers.__new__(PendingTransfers)
    transfer = _transfer(origin, MagicMock(), {MagicMock(): 12}, departed=False)
    orders.pending_transfers = [transfer]

    # Events passed in, so nothing is published to the stream from a unit test.
    orders.cancel_transfer(transfer, GameUpdateEvents())

    origin.base.commission_units.assert_not_called()
    assert orders.pending_transfers == []


def test_a_transfer_that_left_is_given_back_on_cancel() -> None:
    origin = MagicMock()
    orders = PendingTransfers.__new__(PendingTransfers)
    units = {MagicMock(): 12}
    transfer = _transfer(origin, MagicMock(), units, departed=True)
    orders.pending_transfers = [transfer]

    # Events passed in, so nothing is published to the stream from a unit test.
    orders.cancel_transfer(transfer, GameUpdateEvents())

    origin.base.commission_units.assert_called_once_with(units)


def test_arriving_units_are_only_handed_over_if_they_travelled() -> None:
    """disband_at is the arrival hand-off; an undeparted transfer would duplicate."""
    order = TransferOrder.__new__(TransferOrder)
    order.units = {MagicMock(): 5}
    order.departed = False
    location = MagicMock()

    order.disband_at(location)

    location.base.commission_units.assert_not_called()
    assert order.units == {}


def test_a_base_reports_what_it_is_still_holding_and_what_has_left() -> None:
    unit = MagicMock()
    cp = SimpleNamespace(
        ground_unit_orders=SimpleNamespace(units={}),
        base=SimpleNamespace(armor={unit: 37}),
    )
    stuck = _transfer(cp, MagicMock(), {unit: 25}, departed=False)
    moving = _transfer(cp, MagicMock(), {unit: 12}, departed=True)

    allocations = ControlPoint.allocated_ground_units(cp, [stuck, moving])  # type: ignore[arg-type]

    assert isinstance(allocations, GroundUnitAllocations)
    assert allocations.total_pending_transfer == 25
    assert allocations.total_transferring_out == 12
    # The stuck ones are still on the books; the moving ones already left them.
    assert allocations.present == {unit: 37}
