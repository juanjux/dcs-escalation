"""How high the ground is, looked up rather than typed.

DCS answers only from inside a running mission, so the height comes from the open
elevation model AWS hosts. It is the real world's rather than DCS's: close, and very
much closer than the zero it replaces.

Nothing here reaches the network. The tile decoder is what can be got wrong, so that
is what is pinned, with a PNG built here.
"""

from __future__ import annotations

import struct
import zlib
from typing import Any

import pytest

from game import elevation


def _png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """A minimal 8-bit RGB PNG, every scanline unfiltered."""
    height, width = len(pixels), len(pixels[0])
    raw = b"".join(
        bytes([0]) + bytes(channel for pixel in row for channel in pixel)
        for row in pixels
    )

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _terrarium(metres: float) -> tuple[int, int, int]:
    """The colour that encodes this height, which is what the tiles carry."""
    value = round((metres + 32768) * 256)
    return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF


def _answer(monkeypatch: Any, png: bytes | None) -> None:
    elevation._TILES.clear()
    monkeypatch.setattr(elevation, "_fetch", lambda z, x, y: png)


def test_a_height_is_read_back_out_of_a_tile(monkeypatch: Any) -> None:
    _answer(monkeypatch, _png([[_terrarium(1234.0)] * 256] * 256))

    assert elevation.elevation_m(42.0, 42.0) == pytest.approx(1234.0, abs=0.01)


def test_below_sea_level_is_read_as_such(monkeypatch: Any) -> None:
    """The Dead Sea and the sea floor are both real answers."""
    _answer(monkeypatch, _png([[_terrarium(-412.0)] * 256] * 256))

    assert elevation.elevation_m(31.5, 35.5) == pytest.approx(-412.0, abs=0.01)


def test_feet_never_go_below_zero(monkeypatch: Any) -> None:
    """A point on the ground is not aimed at from under the water, and a negative
    elevation in a cockpit is a typo waiting to be reported."""
    _answer(monkeypatch, _png([[_terrarium(-3413.0)] * 256] * 256))

    assert elevation.elevation_ft(30.0, -40.0) == 0


def test_metres_become_feet(monkeypatch: Any) -> None:
    _answer(monkeypatch, _png([[_terrarium(1000.0)] * 256] * 256))

    assert elevation.elevation_ft(42.0, 42.0) == 3281


def test_no_tile_means_no_answer_rather_than_a_wrong_one(monkeypatch: Any) -> None:
    """No network, an unreachable host, a tile that does not decode: the player types
    the number in as before."""
    _answer(monkeypatch, None)

    assert elevation.elevation_m(42.0, 42.0) is None
    assert elevation.elevation_ft(42.0, 42.0) is None


def test_something_that_is_not_a_png_is_not_read(monkeypatch: Any) -> None:
    _answer(monkeypatch, b"<html>404</html>")

    assert elevation.elevation_m(42.0, 42.0) is None


def test_the_right_pixel_of_the_tile_is_read(monkeypatch: Any) -> None:
    """Every row is filtered against the one above it, so reading row 200 means
    undoing the two hundred before it."""
    rows = [[_terrarium(float(row))] * 256 for row in range(256)]
    _answer(monkeypatch, _png(rows))
    _, _, _, py = elevation._tile_of(42.0, 42.0)

    assert elevation.elevation_m(42.0, 42.0) == pytest.approx(float(py), abs=0.01)


def test_a_position_lands_in_the_tile_that_holds_it() -> None:
    """Greenwich at the equator is the middle of the world, which is the middle of
    the tile grid."""
    x, y, _, _ = elevation._tile_of(0.0, 0.0, zoom=1)

    assert (x, y) == (1, 1)
