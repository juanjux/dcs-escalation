"""How high the ground is at a position.

DCS does not tell the application: the terrain height is inside the simulator and only
answerable from a running mission, which is no use when the point is being written
down in the planner. So it is looked up from a public elevation model instead -- the
one AWS hosts as open data, which needs no key and no account.

That is the real world's height rather than DCS's, and the two are not identical: the
terrain is modelled from the same survey data but simplified, so a ridge line can be a
few metres out and a cliff edge more. It is close enough for what the number is for --
a weapon aimed at a point on the ground, which misses by the error in its elevation --
and very much closer than the zero it replaces.

Nothing here is required: no network, an unreachable host or a tile that does not
decode all answer None, and the player types the number in as before.
"""

from __future__ import annotations

import logging
import math
import struct
import urllib.error
import urllib.request
import zlib
from typing import Optional

#: Mapzen's terrarium tiles, hosted by AWS as open data. PNG, one metre per unit,
#: height encoded in the three colour channels.
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

#: Zoom 12 is about 30 m a pixel at the equator, which is the resolution of the survey
#: underneath it; asking for more detail would invent it.
ZOOM = 12

#: A tile is 256 px square.
SIDE = 256

#: Long enough that a slow answer does not hold up the dialog that asked.
TIMEOUT = 6.0

#: The tiles already fetched this session, by (z, x, y). One is 100 kB or so and a
#: campaign works over a handful of them, so they are simply kept.
_TILES: dict[tuple[int, int, int], Optional[bytes]] = {}


def _tile_of(lat: float, lng: float, zoom: int = ZOOM) -> tuple[int, int, int, int]:
    """The tile this position is in, and where in it: (x, y, px, py)."""
    count = 2**zoom
    radians = math.radians(lat)
    fx = (lng + 180.0) / 360.0 * count
    fy = (
        (1.0 - math.log(math.tan(radians) + 1.0 / math.cos(radians)) / math.pi)
        / 2.0
        * count
    )
    x, y = int(fx), int(fy)
    return x, y, int((fx - x) * SIDE), int((fy - y) * SIDE)


def _fetch(z: int, x: int, y: int) -> Optional[bytes]:
    key = (z, x, y)
    if key in _TILES:
        return _TILES[key]
    url = TILES.format(z=z, x=x, y=y)
    data: Optional[bytes]
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as answer:
            data = bytes(answer.read())
    except (urllib.error.URLError, OSError, ValueError) as error:
        logging.info("No elevation tile for %s: %s", url, error)
        data = None
    _TILES[key] = data
    return data


def _pixel(png: bytes, px: int, py: int) -> Optional[tuple[int, int, int]]:
    """One pixel out of a PNG, without asking for an image library.

    The tiles are 8-bit RGB or RGBA and not interlaced, which is the one case this
    has to read; anything else answers None and the caller falls back.
    """
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width = height = 0
    depth = colour = interlace = -1
    pixels = bytearray()
    at = 8
    while at + 8 <= len(png):
        length, kind = struct.unpack(">I4s", png[at : at + 8])
        body = png[at + 8 : at + 8 + length]
        at += 12 + length
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(
                ">IIBBBBB", body
            )
        elif kind == b"IDAT":
            pixels += body
        elif kind == b"IEND":
            break
    if depth != 8 or colour not in (2, 6) or interlace != 0:
        return None
    channels = 3 if colour == 2 else 4
    if not (0 <= px < width and 0 <= py < height):
        return None

    try:
        raw = zlib.decompress(bytes(pixels))
    except zlib.error:
        return None

    stride = width * channels
    if len(raw) < (stride + 1) * height:
        return None
    # Each scanline carries a filter byte, and filters refer to the line above, so
    # every line up to the one wanted has to be undone.
    previous = bytearray(stride)
    line = bytearray(stride)
    for row in range(py + 1):
        start = row * (stride + 1)
        filter_type = raw[start]
        line = bytearray(raw[start + 1 : start + 1 + stride])
        _unfilter(line, previous, filter_type, channels)
        previous = line
    at = px * channels
    return line[at], line[at + 1], line[at + 2]


def _unfilter(line: bytearray, previous: bytearray, kind: int, channels: int) -> None:
    """Undo one PNG scanline filter in place. The five of them, as the spec has it."""
    if kind == 0:
        return
    for i in range(len(line)):
        left = line[i - channels] if i >= channels else 0
        up = previous[i]
        upleft = previous[i - channels] if i >= channels else 0
        if kind == 1:
            line[i] = (line[i] + left) & 0xFF
        elif kind == 2:
            line[i] = (line[i] + up) & 0xFF
        elif kind == 3:
            line[i] = (line[i] + (left + up) // 2) & 0xFF
        elif kind == 4:
            estimate = left + up - upleft
            da, db, dc = (
                abs(estimate - left),
                abs(estimate - up),
                abs(estimate - upleft),
            )
            nearest = left if (da <= db and da <= dc) else (up if db <= dc else upleft)
            line[i] = (line[i] + nearest) & 0xFF
        else:
            return


def elevation_m(lat: float, lng: float) -> Optional[float]:
    """Metres above sea level, or None when it could not be looked up."""
    x, y, px, py = _tile_of(lat, lng)
    png = _fetch(ZOOM, x, y)
    if png is None:
        return None
    rgb = _pixel(png, px, py)
    if rgb is None:
        logging.info("Elevation tile %d/%d/%d did not decode", ZOOM, x, y)
        return None
    red, green, blue = rgb
    # The terrarium encoding, which is what these tiles are.
    return (red * 256 + green + blue / 256) - 32768


def elevation_ft(lat: float, lng: float) -> Optional[int]:
    """The same in the feet a saved point is kept in, or None.

    Below sea level reads as zero: a point on the ground is never aimed at from under
    the water, and a negative elevation in a cockpit is a typo waiting to be reported.
    """
    metres = elevation_m(lat, lng)
    if metres is None:
        return None
    return max(0, round(metres / 0.3048))
