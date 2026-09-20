"""Points the player puts in his own aircraft.

A spot on the map is worth writing down long before it is worth a flight plan: the
smoke somebody called in, the ship that was not there yesterday, the field the convoy
turns at. The coordinate picker can read any point; this is where one goes once it has
been read, and it goes to one aircraft -- the player's -- rather than into the flight
plan everyone else has to fly.

Two kinds, because the aircraft make the distinction: a **waypoint** is part of the
navigation set and the aircraft flies to it, a **markpoint** is a spot marked for
reference. How many of each an airframe holds is its own business -- a number per
module, read off DCS's own data-cartridge scripts rather than remembered -- and an
airframe nobody has measured claims none.

Nothing here reaches the aircraft on its own. The points ride on the kneeboard, on a
page of their own so the route page stays the route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Optional

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


#: An airframe nobody has measured. It is not refused -- its points ride on the
#: kneeboard like everyone else's -- it simply gets the fallback below rather than a
#: number it cannot keep.
UNMEASURED = Capacity(waypoints=0, markpoints=0)

#: What an unmeasured airframe is allowed. Not a page: the kneeboard paginates, so
#: this is only a guard against a list nobody could use, for an aircraft whose real
#: ceiling nobody has looked up yet.
UNKNOWN_CEILING = 50

#: One row per airframe, from whatever DCS uses for that module: the .dtc scripts in
#: ``CoreMods/aircraft/<type>/DTC``, or the A-10's own DTS database. None of them
#: carries a markpoint -- those are made in the cockpit -- so the markpoint column is
#: where a module that does carry one goes.
#:
#: Hornet: ``WYPT/WYPT_NAV.lua`` caps the navigation set at 59, and two of those are
#: spoken for (58 is HOME, 59 the bullseye), so 57 are free.
#: Viper: ``MPD/NAV_PTS.lua`` stops at 25 steerpoints.
#: A-10C II: its navigation computer indexes waypoints 0 to 2050
#: (``NavigationComputer_param.lua``) and its markpoints are lettered, A to Z.
#: Super Hornet (the CJS mod): the same cartridge the Hornet has, section for section.
CAPACITY: dict[str, Capacity] = {
    "FA-18C_hornet": Capacity(waypoints=57, markpoints=0),
    "FA-18E": Capacity(waypoints=57, markpoints=0),
    "FA-18F": Capacity(waypoints=57, markpoints=0),
    "EA-18G": Capacity(waypoints=57, markpoints=0),
    "F-16C_50": Capacity(waypoints=25, markpoints=0),
    "A-10C": Capacity(waypoints=2050, markpoints=26),
    "A-10C_2": Capacity(waypoints=2050, markpoints=26),
}


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


def reaches_the_aircraft(dcs_id: str, kind: PointKind) -> bool:
    """Whether the airframe's own cartridge or database carries this kind.

    False for an airframe nobody has measured as well: a point that cannot be shown
    to go in is one to say so about. Either way the point is still written down --
    the kneeboard takes both kinds -- it just does not reach the cockpit by itself.
    """
    return capacity_for(dcs_id).of(kind) > 0


def instead_of(dcs_id: str, kind: PointKind) -> Optional[PointKind]:
    """The kind worth offering when the chosen one cannot reach the aircraft.

    None when there is nothing better to offer: the aircraft takes the chosen kind,
    or it takes neither and swapping would gain nothing.
    """
    if reaches_the_aircraft(dcs_id, kind):
        return None
    other = PointKind.WAYPOINT if kind is PointKind.MARKPOINT else PointKind.MARKPOINT
    return other if reaches_the_aircraft(dcs_id, other) else None


def room_for(flight: Flight, kind: PointKind) -> int:
    """How many more of this kind the flight will take.

    The aircraft's own number, not the kneeboard's: an A-10 indexes two thousand
    waypoints and the page paginates to suit. Only an airframe nobody has measured
    falls back to a guard figure.
    """
    held = sum(1 for point in points_of(flight) if point.kind is kind)
    aircraft = capacity_for(flight.unit_type.dcs_unit_type.id).of(kind)
    return max((aircraft or UNKNOWN_CEILING) - held, 0)


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
