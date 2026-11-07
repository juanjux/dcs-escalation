"""Campaign GPS points shared by player aircraft, with legacy-save migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Any, Iterable, Optional
from uuid import UUID, uuid4

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
    id: UUID = field(default_factory=uuid4, compare=False)


@dataclass
class SavedDrawing:
    """A player-authored line or area in DCS world coordinates."""

    name: str
    points: list[tuple[float, float]]
    closed: bool = False
    id: UUID = field(default_factory=uuid4, compare=False)


MAX_DRAWINGS = 50
MAX_DRAWING_VERTICES = 64


def drawings_of(flight: Flight) -> list[SavedDrawing]:
    """Share drawings across the squadron and retain them when flights change."""
    drawings = getattr(flight.squadron, "saved_drawings", None)
    if drawings is None:
        drawings = []
        flight.squadron.saved_drawings = drawings
    for drawing in drawings:
        if not hasattr(drawing, "id"):
            drawing.id = uuid4()
    return drawings


def add_drawing(flight: Flight, drawing: SavedDrawing) -> bool:
    required = 3 if drawing.closed else 2
    if (
        not required <= len(drawing.points) <= MAX_DRAWING_VERTICES
        or len(set(drawing.points)) < required
        or not all(isfinite(v) for point in drawing.points for v in point)
        or len(drawings_of(flight)) >= MAX_DRAWINGS
    ):
        return False
    drawings_of(flight).append(drawing)
    return True


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
#: (``NavigationComputer_param.lua``).
#: Super Hornet (the CJS mod): the same cartridge the Hornet has, section for section.
#:
#: The markpoint column is all zeroes, and not for want of markpoints: every one of
#: these aircraft has them. None of them can be handed one. The Hornet's cartridge has
#: no markpoint section at all, and the A-10's DTS database is waypoints only -- its
#: ``Waypoint_Types`` are airfields, beacons and ``WPT_UNK``, with nothing for the
#: lettered marks, which are made in the cockpit.
CAPACITY: dict[str, Capacity] = {
    "FA-18C_hornet": Capacity(waypoints=57, markpoints=0),
    "FA-18E": Capacity(waypoints=57, markpoints=0),
    "FA-18F": Capacity(waypoints=57, markpoints=0),
    "EA-18G": Capacity(waypoints=57, markpoints=0),
    "FA-18ET": Capacity(waypoints=57, markpoints=0),
    "FA-18FT": Capacity(waypoints=57, markpoints=0),
    "F-16C_50": Capacity(waypoints=24, markpoints=0),
    "A-10C": Capacity(waypoints=2050, markpoints=0),
    "A-10C_2": Capacity(waypoints=2050, markpoints=0),
}


def capacity_for(dcs_id: str) -> Capacity:
    return CAPACITY.get(dcs_id, UNMEASURED)


def campaign_points(coalition: Any) -> list[SavedPoint]:
    """Shared campaign points for one side; merge legacy squadron/flight lists."""
    points: list[SavedPoint] | None = getattr(coalition, "saved_points", None)
    if points is None:
        points = []
        coalition.saved_points = points

    def merge(legacy: list[SavedPoint]) -> None:
        if legacy is points:
            return
        identities = {point.id for point in points if hasattr(point, "id")}
        for point in legacy:
            if not hasattr(point, "id"):
                point.id = uuid4()
            if point.id not in identities and point not in points:
                points.append(point)
                identities.add(point.id)

    wing = getattr(coalition, "air_wing", None)
    if wing is not None:
        for squadron in wing.iter_squadrons():
            merge(getattr(squadron, "saved_points", []))
            squadron.saved_points = points
    ato = getattr(coalition, "ato", None)
    if ato is not None:
        for package in ato.packages:
            for flight in package.flights:
                merge(flight.__dict__.pop("saved_points", None) or [])
    for point in points:
        if not hasattr(point, "id"):
            point.id = uuid4()
    return points


def points_of(flight: Flight) -> list[SavedPoint]:
    """Campaign points shared by all flights, regardless of aircraft or pilot."""
    squadron = flight.squadron
    coalition = getattr(squadron, "coalition", None)
    # Standalone legacy flights may not yet be attached to a campaign.
    points = campaign_points(coalition if coalition is not None else squadron)
    legacy = getattr(squadron, "saved_points", None)
    pending = [] if legacy is points else list(legacy or [])
    pending.extend(flight.__dict__.pop("saved_points", None) or [])
    identities = {point.id for point in points}
    for point in pending:
        if not hasattr(point, "id"):
            point.id = uuid4()
        if point.id not in identities and point not in points:
            points.append(point)
            identities.add(point.id)
    squadron.saved_points = points
    return points


def kinds_for(dcs_id: str) -> list[PointKind]:
    """The kinds this airframe can be handed, most useful first.

    Only what will actually reach the aircraft. Offering a markpoint to a Hornet and
    then explaining in a dialog that it will only reach the kneeboard is a question
    the player should never have been asked: the answer is in the airframe, and the
    control can just not offer it.

    An airframe nobody has measured is offered nothing, which is the truth about it.
    """
    return [kind for kind in PointKind if reaches_the_aircraft(dcs_id, kind)]


def reaches_the_aircraft(dcs_id: str, kind: PointKind) -> bool:
    """Whether the airframe's own cartridge or database carries this kind.

    False for an airframe nobody has measured as well: a point that cannot be shown
    to go in is one to say so about. Either way the point is still written down --
    the kneeboard takes both kinds -- it just does not reach the cockpit by itself.
    """
    return capacity_for(dcs_id).of(kind) > 0


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
    """Save globally; avionics capacity limits apply during export, not storage."""
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
