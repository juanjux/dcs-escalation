"""Points the player puts in his own aircraft.

A spot on the map is worth writing down long before it is worth a flight plan: the
smoke somebody called in, the ship that was not there yesterday, the field the convoy
turns at. The coordinate picker can read any point; this is where one goes once it has
been read, and it goes to one aircraft -- the player's -- rather than into the flight
plan everyone else has to fly.

Two kinds, because the aircraft make the distinction: a **waypoint** is part of the
navigation set and the aircraft flies to it, a **markpoint** is a spot marked for
reference. How many of each an airframe holds is its own business, and the numbers
below are read off DCS rather than remembered: a Hornet's cartridge holds 59
waypoints, and its markpoints are made in the cockpit, not loaded.

Nothing here reaches the aircraft on its own. The points ride on the kneeboard, on a
page of their own so the route page stays the route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from game.ato.flight import Flight


class PointKind(Enum):
    """The values are the save format: renaming one breaks a campaign in progress."""

    WAYPOINT = "waypoint"
    MARKPOINT = "markpoint"

    @property
    def label(self) -> str:
        return "Waypoint" if self is PointKind.WAYPOINT else "Markpoint"


@dataclass
class SavedPoint:
    """One point, as the player wrote it down."""

    kind: PointKind
    name: str
    #: DCS world coordinates, the frame everything else in the campaign uses.
    x: float
    y: float
    altitude_ft: int = 0


@dataclass(frozen=True)
class Capacity:
    """How many of each kind an airframe will take.

    Zero is not "unsupported": a point with nowhere to go still goes on the
    kneeboard, which is where the player reads it off and enters it himself. It is
    the number the aircraft can be *given*.
    """

    waypoints: int
    markpoints: int

    def of(self, kind: PointKind) -> int:
        return self.waypoints if kind is PointKind.WAYPOINT else self.markpoints


#: Read off DCS's own data-cartridge definitions in CoreMods/aircraft/<type>/DTC.
#: The Hornet's WYPT_NAV.lua caps the navigation set at 59, and two of those are
#: spoken for -- 58 is HOME and 59 the bullseye -- so 57 are free. Nothing in its
#: cartridge carries a markpoint: those are made in the cockpit.
CAPACITY: dict[str, Capacity] = {
    "FA-18C_hornet": Capacity(waypoints=57, markpoints=0),
}

#: An airframe nobody has measured. Its points ride on the kneeboard like everyone
#: else's; what it will not do is claim a number it cannot keep.
UNMEASURED = Capacity(waypoints=0, markpoints=0)

#: However many an aircraft holds, this is as many as one flight may write down. A
#: kneeboard page holds about this many rows, and a list longer than a page is a list
#: nobody reads in the air.
PAGE_FULL = 24


def capacity_for(dcs_id: str) -> Capacity:
    return CAPACITY.get(dcs_id, UNMEASURED)


def points_of(flight: Flight) -> list[SavedPoint]:
    """This flight's points, on a save that predates the feature as well."""
    points = getattr(flight, "saved_points", None)
    if points is None:
        points = []
        flight.saved_points = points
    return points


def kinds_for(dcs_id: str) -> list[PointKind]:
    """The kinds this airframe is offered, most useful first.

    A kind its cartridge cannot carry is still offered -- the kneeboard takes both,
    and a markpoint written down is a markpoint the player can punch in -- so this
    is about order and about what the dialog says, not about refusing.
    """
    capacity = capacity_for(dcs_id)
    if capacity.markpoints and not capacity.waypoints:
        return [PointKind.MARKPOINT, PointKind.WAYPOINT]
    return [PointKind.WAYPOINT, PointKind.MARKPOINT]


def room_for(flight: Flight, kind: PointKind) -> int:
    """How many more of this kind the flight will take."""
    held = sum(1 for point in points_of(flight) if point.kind is kind)
    aircraft = capacity_for(flight.unit_type.dcs_unit_type.id).of(kind)
    # The page is the tighter of the two whenever the aircraft says nothing useful.
    ceiling = min(aircraft, PAGE_FULL) if aircraft else PAGE_FULL
    return max(ceiling - held, 0)


def add_point(flight: Flight, point: SavedPoint) -> bool:
    """Write one down, unless there is no room left for its kind."""
    if room_for(flight, point.kind) <= 0:
        return False
    points_of(flight).append(point)
    return True


def remove_point(flight: Flight, index: int) -> bool:
    points = points_of(flight)
    if not 0 <= index < len(points):
        return False
    del points[index]
    return True


def receivers(coalition: Any) -> Iterable[Flight]:
    """Every flight the player is actually flying, which is the only kind that can
    be handed a point: an AI aircraft has nobody in it to read one."""
    for package in coalition.ato.packages:
        for flight in package.flights:
            if flight.client_count > 0:
                yield flight
