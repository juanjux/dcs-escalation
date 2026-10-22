"""Availability and shared defaults for Realistic CAS AFAC missions."""

from typing import Any


def enabled(settings: Any) -> bool:
    return (
        settings.plugins.get("realisticcas") is True
        and settings.plugins.get("realisticcas.afacEnabled") is True
    )


def station_minutes(settings: Any) -> int:
    value = settings.plugins.get("realisticcas.afacStationMinutes", 60)
    if type(value) is not int or not 1 <= value <= 240:
        raise ValueError("AFAC on-station time must be 1..240 minutes")
    return value
