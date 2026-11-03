"""Refund accounting for pending building repairs."""

from __future__ import annotations

from game.theater.theatergroundobject import BuildingGroundObject
from game.theater.theatergroup import TheaterUnit


def pending_buildings(site: BuildingGroundObject) -> list[TheaterUnit]:
    return [
        unit
        for unit in site.statics
        if not unit.alive and unit.repair_turns_remaining is not None
    ]


def repair_refunds(site: BuildingGroundObject) -> dict[int, float]:
    """Return receipts, with a conservative fallback for unrecorded legacy work.

    Old API batches charged once per site, unlike UI/automatic repairs. The save
    cannot distinguish them, so unrecorded repairs share one site's repair price.
    New repairs always carry their actual payment, including zero-cost work.
    """
    pending = pending_buildings(site)
    legacy = [
        unit for unit in pending if getattr(unit, "repair_cost_paid", None) is None
    ]
    fallback = site.repair_cost() / len(legacy) if legacy else 0.0
    refunds: dict[int, float] = {}
    for unit in pending:
        receipt = getattr(unit, "repair_cost_paid", None)
        refunds[unit.id] = receipt if receipt is not None else fallback
    return refunds


def cancel_building_repairs(
    site: BuildingGroundObject, units: list[TheaterUnit]
) -> float:
    """Cancel selected pending work once; leave the buildings destroyed."""
    pending = pending_buildings(site)
    if not units or any(not any(unit is item for item in pending) for unit in units):
        raise ValueError("select buildings with pending repairs")
    if len({unit.id for unit in units}) != len(units):
        raise ValueError("duplicate building IDs")
    refunds = repair_refunds(site)
    # Preserve legacy allocations when only part of an old batch is cancelled.
    for unit in pending:
        unit.repair_cost_paid = refunds[unit.id]
    refund = sum(refunds[unit.id] for unit in units)
    for unit in units:
        unit.repair_turns_remaining = None
        unit.repair_cost_paid = None
    return refund
