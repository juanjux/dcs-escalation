"""Coordinate formatting, in the formats DCS offers.

The reference values are Creech AFB's runway threshold read off the DCS F10 map.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from dcs.mapping import LatLng

from game.coordinates import (
    CoordinateFormat,
    all_formats,
    coordinate_format,
    format_dd,
    format_ddm,
    format_dms,
    format_latlng,
    format_mgrs,
)

# 36°35'19"N 115°40'25"W, north-west of Las Vegas.
CREECH = LatLng(36.5886, -115.6736)
# The other three quadrants, to check the hemisphere letters and the zero padding.
SOUTH_EAST = LatLng(-33.9249, 18.4241)
NEAR_ZERO = LatLng(0.5, -0.5)


def test_degrees_minutes_seconds() -> None:
    assert format_dms(CREECH) == "N36°35'19\" W115°40'25\""


def test_degrees_minutes_seconds_with_decimals() -> None:
    assert format_dms(CREECH, decimals=2) == "N36°35'18.96\" W115°40'24.96\""


def test_degrees_decimal_minutes() -> None:
    assert format_ddm(CREECH) == "N36°35.316' W115°40.416'"


def test_decimal_degrees() -> None:
    assert format_dd(CREECH) == "N36.58860° W115.67360°"


def test_mgrs_is_grouped_for_reading() -> None:
    assert format_mgrs(CREECH) == "11S PA 18653 50054"


def test_the_southern_and_eastern_hemispheres() -> None:
    assert format_ddm(SOUTH_EAST) == "S33°55.494' E018°25.446'"


def test_degrees_are_padded_to_the_usual_width() -> None:
    """Two digits for latitude, three for longitude, as every aircraft expects."""
    assert format_ddm(NEAR_ZERO) == "N00°30.000' W000°30.000'"


@pytest.mark.parametrize("fmt", list(CoordinateFormat))
def test_every_format_produces_something(fmt: CoordinateFormat) -> None:
    assert format_latlng(CREECH, fmt)


def test_all_formats_covers_the_whole_enum() -> None:
    position = SimpleNamespace(latlng=lambda: CREECH)
    assert set(all_formats(position)) == {fmt.name for fmt in CoordinateFormat}  # type: ignore[arg-type]


def test_a_campaign_with_no_setting_reads_as_decimal_minutes() -> None:
    """Which is what a save written before the setting existed has."""
    assert coordinate_format(SimpleNamespace()) is CoordinateFormat.DDM
    assert coordinate_format(None) is CoordinateFormat.DDM


def test_the_campaign_setting_is_what_decides() -> None:
    settings = SimpleNamespace(coordinate_format=CoordinateFormat.MGRS)

    assert coordinate_format(settings) is CoordinateFormat.MGRS
