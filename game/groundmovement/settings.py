"""Ground Movement settings and its Motor Pool dependency."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.settings import Settings

PLUGIN = "groundmovement"
METERS_PER_MILE = 1609.344


def requested(settings: Settings) -> bool:
    return settings.plugin_option_or(PLUGIN, False) is True


def enabled(settings: Settings) -> bool:
    return requested(settings) and settings.motorpool_enabled


def set_enabled(
    settings: Settings, value: bool, *, enable_motorpool: bool = False
) -> None:
    if value and not settings.motorpool_enabled:
        if not enable_motorpool:
            raise ValueError("Ground Movement requires Motor Pool")
        settings.motorpool_enabled = True
    settings.set_plugin_option(PLUGIN, value)


def disable_motorpool(settings: Settings) -> None:
    settings.set_plugin_option(PLUGIN, False)
    settings.motorpool_enabled = False


def reconcile(settings: Settings) -> None:
    """Invalid imported combinations disable movement, preserving saved orders."""
    if requested(settings) and not settings.motorpool_enabled:
        settings.set_plugin_option(PLUGIN, False)


def distance_per_turn(settings: Settings, *, on_road: bool) -> float:
    key, default = ("roadMilesPerTurn", 120) if on_road else ("offRoadMilesPerTurn", 60)
    value = settings.plugin_option_or(f"{PLUGIN}.{key}", default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 1 <= value <= 1000
    ):
        raise ValueError("Ground movement distance must be between 1 and 1000 miles")
    return float(value) * METERS_PER_MILE
