"""Shared resale prices, separate from refunds for unfulfilled orders."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.settings import Settings
    from game.squadrons import Squadron
    from game.theater.theatergroundobject import TheaterGroundObject


def resale_value(settings: Settings, price: float) -> float:
    if not getattr(settings, "resale_depreciation_enabled", True):
        return price
    percent = max(0, min(100, getattr(settings, "resale_value_percent", 85)))
    return price * percent / 100


def ground_object_sale_value(game: Game, site: TheaterGroundObject) -> float:
    if not site.sellable:
        return 0.0
    # Paid repairs/construction have not arrived yet: cancel them at full price.
    pending = sum(
        unit.unit_type.price
        for unit in site.units
        if not unit.alive
        and unit.repair_turns_remaining is not None
        and unit.unit_type is not None
    )
    return resale_value(game.settings, site.value) + pending


def pending_aircraft_sale_values(squadron: Squadron) -> list[float]:
    """Legacy pending sales received full price; new ones retain their receipts."""
    count = max(0, -squadron.pending_deliveries)
    recorded = (
        list(getattr(squadron, "pending_sale_values", []))[-count:] if count else []
    )
    return [float(squadron.aircraft.price)] * (count - len(recorded)) + recorded
