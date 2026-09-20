"""Reading a position back out of whatever the player typed or pasted.

The Add button takes a position rather than a spot on the map, and what is on the
clipboard did not necessarily come from this campaign, so the format is worked out
from the shape of what was typed rather than read off the campaign's setting.
"""

from __future__ import annotations

import pytest
from dcs.mapping import LatLng

from game.coordinates import CoordinateFormat, format_latlng, parse_latlng


def _round(latlng: LatLng, places: int = 4) -> tuple[float, float]:
    return round(latlng.lat, places), round(latlng.lng, places)


@pytest.mark.parametrize(
    "text",
    [
        "S53°47.220' W067°44.890'",  # degrees, decimal minutes: what the app writes
        "S53°47'13.20\" W067°44'53.40\"",  # degrees, minutes, seconds
        "-53.78700 -67.74817",  # decimal degrees
        "-53.787, -67.748",  # with a comma between the halves
        "53.787S 67.748W",  # the hemisphere letter trailing
        "  -53.787   -67.748  ",  # and whatever whitespace came with it
    ],
)
def test_every_format_the_campaign_writes_reads_back(text: str) -> None:
    latlng = parse_latlng(text)

    assert latlng is not None
    assert _round(latlng, 2) == (-53.79, -67.75)


def test_the_halves_are_told_apart_by_counting_not_by_a_separator() -> None:
    """ "N40 26.767 W079 58.933" has no separator between the halves at all."""
    latlng = parse_latlng("N40 26.767 W079 58.933")

    assert latlng is not None
    assert _round(latlng) == (40.4461, -79.9822)


def test_mgrs_reads_back() -> None:
    latlng = parse_latlng("19F CF 12345 67890")

    assert latlng is not None
    assert -50 < latlng.lat < -48
    assert -72 < latlng.lng < -71


def test_a_position_survives_being_written_and_read_again() -> None:
    """Which is the case that matters: copy a point, paste it into Add."""
    original = parse_latlng("-53.78700 -67.74817")
    assert original is not None
    for fmt in CoordinateFormat:
        written = format_latlng(original, fmt)
        again = parse_latlng(written)

        assert again is not None, f"{fmt.name}: {written!r}"
        assert _round(again, 2) == (-53.79, -67.75), f"{fmt.name}: {written!r}"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "nonsense",
        "53",  # one number is half a position
        "1 2 3",  # and three is neither one pair nor three
        "S91°00.000' W067°44.890'",  # off the planet
        "S53°00.000' W267°44.890'",
        "S53°61.000' W067°44.890'",  # sixty-one minutes
        "N53 -47.220 W067 44.890",  # a sign inside the minutes
        "S53.787 S67.748",  # two latitudes
        "-53.787 N67.748",  # a sign and a hemisphere, one of them too many
    ],
)
def test_what_cannot_be_read_says_so_rather_than_guessing(text: str) -> None:
    assert parse_latlng(text) is None
