"""Validate explicitly edited MSL heights against the available elevation model."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from game.elevation import elevation_m
from game.utils import Distance, feet

if TYPE_CHECKING:
    from .flightwaypoint import AltitudeReference, FlightWaypoint


def validate_altitude_edit(
    waypoint: FlightWaypoint,
    altitude: Distance | None = None,
    reference: AltitudeReference | None = None,
) -> str | None:
    if (reference or waypoint.alt_type) != "BARO":
        return None
    try:
        where = waypoint.position.latlng()
    except (AttributeError, ValueError):
        # Unprojected planning/test points have no geographical elevation lookup.
        return None
    ground = elevation_m(where.lat, where.lng)
    if ground is None:
        return "Terrain elevation is unavailable. The MSL altitude was accepted but could not be checked against the ground."
    proposed = altitude if altitude is not None else waypoint.alt
    if proposed.meters < ground - 1e-6:
        floor = math.ceil(ground / feet(1).meters)
        raise ValueError(
            f"{waypoint.display_name or waypoint.name}: MSL altitude is below the estimated terrain elevation ({floor:,} ft MSL). "
            "Use AGL for a height above the ground, or choose a higher MSL altitude."
        )
    return None
