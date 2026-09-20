"""Position formatting, in the formats DCS itself offers.

One place decides how a coordinate is written, so the objective dialog, the map picker
and anything added later agree. Which format is used comes from the campaign's
``coordinate_format`` setting.
"""

from __future__ import annotations

import logging
import re
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


# ---------------------------------------------------------------- reading one back

#: What a hemisphere letter means for the sign, whichever end of the number it is on.
_HEMISPHERES = {"N": 1, "S": -1, "E": 1, "W": -1}

_MGRS = re.compile(
    r"^\s*(\d{1,2}\s*[C-HJ-NP-X])\s*([A-HJ-NP-Z]{2})\s*(\d+)\s*(\d+)?\s*$",
    re.IGNORECASE,
)


def _sign_of(letters: str, negative: bool, pair: str) -> Optional[float]:
    """Which way the number points: from its hemisphere letter, or from a minus.

    Both at once is one of them too many, and so is a letter from the other pair --
    a latitude does not go east.
    """
    found = [c for c in letters if c in pair]
    if len(found) > 1 or (found and negative):
        return None
    if found:
        return float(_HEMISPHERES[found[0]])
    return -1.0 if negative else 1.0


def _degrees(numbers: list[float], sign: float) -> Optional[float]:
    """Degrees; degrees and decimal minutes; degrees, minutes and seconds.

    Which it is comes from how many numbers there are, so nothing has to say which
    format was typed.
    """
    if any(part >= 60 for part in numbers[1:]):
        return None
    value = numbers[0]
    for place, part in enumerate(numbers[1:], start=1):
        value += part / (60.0**place)
    return sign * value


def parse_latlng(text: str) -> Optional[LatLng]:
    """A position a player typed or pasted, in any format this module writes.

    Degrees, decimal minutes, seconds and MGRS are all read, and which one it is comes
    from the shape of what was typed rather than from the campaign's setting: what is
    on the clipboard was not necessarily written by this campaign. None when it cannot
    be read, which is what the caller tells the player.

    The halves are told apart by counting -- two numbers, four or six, split down the
    middle -- rather than by looking for a separator, because the separator is a comma
    here, a space there, and nothing at all in "N40 26.767 W079 58.933".
    """
    if not text or not text.strip():
        return None
    cleaned = text.strip().upper()

    mgrs_match = _MGRS.match(cleaned)
    if mgrs_match and mgrs_match.group(4) is not None:
        return _from_mgrs(mgrs_match)

    numbers = [
        (part.startswith("-"), abs(float(part.replace(",", "."))))
        for part in re.findall(r"-?\d+(?:[.,]\d+)?", cleaned.replace(",", "."))
    ]
    if len(numbers) not in (2, 4, 6):
        return None
    half = len(numbers) // 2
    letters = [c for c in cleaned if c in _HEMISPHERES]
    if len(letters) > 2:
        return None
    # A letter before the first number belongs to the latitude either way, and one
    # after the last belongs to the longitude; anything else is read by its pair.
    latitude_sign = _sign_of("".join(letters), numbers[0][0], "NS")
    longitude_sign = _sign_of("".join(letters), numbers[half][0], "EW")
    if latitude_sign is None or longitude_sign is None:
        return None
    if any(negative for negative, _ in numbers[1:half] + numbers[half + 1 :]):
        return None

    latitude = _degrees([value for _, value in numbers[:half]], latitude_sign)
    longitude = _degrees([value for _, value in numbers[half:]], longitude_sign)
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return LatLng(latitude, longitude)


def _from_mgrs(match: "re.Match[str]") -> Optional[LatLng]:
    import mgrs as mgrs_lib

    easting, northing = match.group(3), match.group(4)
    if len(easting) != len(northing) or not 1 <= len(easting) <= 5:
        return None
    grid = (
        f"{match.group(1).replace(' ', '')}{match.group(2)}{easting}{northing}".upper()
    )
    try:
        latitude, longitude = mgrs_lib.MGRS().toLatLon(grid)
    except Exception:
        return None
    return LatLng(float(latitude), float(longitude))
