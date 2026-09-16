"""Position formatting, in the formats DCS itself offers.

One place decides how a coordinate is written, so the objective dialog, the map picker
and anything added later agree. Which format is used comes from the campaign's
``coordinate_format`` setting.
"""

from __future__ import annotations

import logging
from enum import Enum, unique
from typing import Any, Callable, Optional

from dcs.mapping import LatLng, Point


@unique
class CoordinateFormat(Enum):
    """The formats DCS shows on the F10 map and in the aircraft."""

    DMS = "Degrees, minutes, seconds"
    DMS_DECIMAL = "Degrees, minutes, seconds with decimals"
    DDM = "Degrees, decimal minutes"
    DD = "Decimal degrees"
    MGRS = "MGRS"


def _dms_parts(value: float) -> tuple[int, int, float]:
    value = abs(value)
    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    if round(seconds, 2) >= 60:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1
    return degrees, minutes, seconds


def format_dms(latlng: LatLng, decimals: int = 0) -> str:
    """``N42°03'12" E042°03'12"``, with optional decimal seconds."""
    parts = []
    for value, hemispheres, width in (
        (latlng.lat, "NS", 2),
        (latlng.lng, "EW", 3),
    ):
        degrees, minutes, seconds = _dms_parts(value)
        hemisphere = hemispheres[0] if value >= 0 else hemispheres[1]
        second_width = 2 if not decimals else 3 + decimals
        parts.append(
            f"{hemisphere}{degrees:0{width}d}°{minutes:02d}'"
            f'{seconds:0{second_width}.{decimals}f}"'
        )
    return " ".join(parts)


def format_ddm(latlng: LatLng, decimals: int = 3) -> str:
    """``N42°03.200' E042°03.200'``: the format most DCS aircraft take."""
    parts = []
    for value, hemispheres, width in (
        (latlng.lat, "NS", 2),
        (latlng.lng, "EW", 3),
    ):
        degrees = int(abs(value))
        minutes = (abs(value) - degrees) * 60
        if round(minutes, decimals) >= 60:
            minutes = 0.0
            degrees += 1
        hemisphere = hemispheres[0] if value >= 0 else hemispheres[1]
        parts.append(
            f"{hemisphere}{degrees:0{width}d}°{minutes:0{3 + decimals}.{decimals}f}'"
        )
    return " ".join(parts)


def format_dd(latlng: LatLng, decimals: int = 5) -> str:
    """``N42.05333° E042.05333°``."""
    parts = []
    for value, hemispheres, width in (
        (latlng.lat, "NS", 2),
        (latlng.lng, "EW", 3),
    ):
        hemisphere = hemispheres[0] if value >= 0 else hemispheres[1]
        parts.append(f"{hemisphere}{abs(value):0{width + 1 + decimals}.{decimals}f}°")
    return " ".join(parts)


def format_mgrs(latlng: LatLng, precision: int = 5) -> str:
    """``38T MM 96228 13049``, at one metre precision."""
    import mgrs as mgrs_lib

    raw = mgrs_lib.MGRS().toMGRS(latlng.lat, latlng.lng, MGRSPrecision=precision)
    digits = raw[5:]
    if len(digits) != 2 * precision:
        logging.warning("Unexpected MGRS output %r; using it as it came", raw)
        return raw
    half = precision
    return f"{raw[:3]} {raw[3:5]} {digits[:half]} {digits[half:]}"


_FORMATTERS: dict[CoordinateFormat, Callable[[LatLng], str]] = {
    CoordinateFormat.DMS: lambda ll: format_dms(ll),
    CoordinateFormat.DMS_DECIMAL: lambda ll: format_dms(ll, decimals=2),
    CoordinateFormat.DDM: lambda ll: format_ddm(ll),
    CoordinateFormat.DD: lambda ll: format_dd(ll),
    CoordinateFormat.MGRS: lambda ll: format_mgrs(ll),
}


def format_latlng(latlng: LatLng, fmt: CoordinateFormat) -> str:
    return _FORMATTERS[fmt](latlng)


def format_for(
    settings: Any, position: Point, fmt: Optional[CoordinateFormat] = None
) -> str:
    """A DCS position in the campaign's chosen format.

    ``settings`` may be None, and a save written before the setting existed does not
    carry it; both fall back to degrees, decimal minutes.
    """
    if fmt is None:
        fmt = coordinate_format(settings)
    try:
        return format_latlng(position.latlng(), fmt)
    except Exception:
        logging.exception("Could not format %s as %s", position, fmt)
        return ""


def coordinate_format(settings: Any) -> CoordinateFormat:
    value = getattr(settings, "coordinate_format", None)
    return value if isinstance(value, CoordinateFormat) else CoordinateFormat.DDM


def all_formats(position: Point) -> dict[str, str]:
    """Every format at once, keyed by the name of the format."""
    latlng = position.latlng()
    return {fmt.name: format_latlng(latlng, fmt) for fmt in CoordinateFormat}
