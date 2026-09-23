"""Ground objects, bases and campaigns for the High Command's tests.

The ground objects are the game's own classes; their units and bases carry only what
the High Command reads.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from types import SimpleNamespace
from typing import Any, Callable, Optional, Sequence

from dcs import Point
from dcs.terrain import Caucasus

from game.data.units import UnitClass
from game.highcommand.approach import Approach, Release
from game.highcommand.campaign import DIRECT_RELEASE, Campaign
from game.theater import Player
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    IadsBuildingGroundObject,
    SamGroundObject,
    ShipGroundObject,
    TheaterGroundObject,
    VehicleGroupGroundObject,
)
from game.theater.theatergroup import IadsGroundGroup, TheaterGroup
from game.utils import meters, nautical_miles

TERRAIN = Caucasus()
NM = nautical_miles(1).meters


def at(x_nm: float, y_nm: float = 0.0) -> Point:
    return Point(x_nm * NM, y_nm * NM, TERRAIN)


class UnitType:
    """A unit type as much as the High Command reads it."""

    def __init__(self, label: str, unit_class: Optional[UnitClass], price: int) -> None:
        self.label = label
        self.unit_class = unit_class
        self.price = price

    def __str__(self) -> str:
        return self.label


def unit(
    label: str,
    *,
    price: int = 10,
    unit_class: Optional[UnitClass] = UnitClass.TANK,
    reach_nm: float = 0.0,
    sees_nm: float = 0.0,
    anti_air: bool = False,
    ship: bool = False,
) -> Any:
    reach = reach_nm * NM
    return SimpleNamespace(
        alive=True,
        is_anti_air=anti_air,
        is_ship=ship,
        is_vehicle=not ship,
        is_static=False,
        threat_range=meters(reach),
        detection_range=meters(sees_nm * NM),
        type=type(label, (), {"id": label, "threat_range": reach}),
        unit_type=UnitType(label, unit_class, price),
    )


def launcher(label: str, reach_nm: float, price: int = 10) -> Any:
    return unit(
        label,
        price=price,
        unit_class=UnitClass.LAUNCHER,
        reach_nm=reach_nm,
        sees_nm=reach_nm,
        anti_air=True,
    )


def structure(alive: bool = True) -> Any:
    """One building of a site: no unit type, no price of its own."""
    return SimpleNamespace(
        alive=alive,
        is_anti_air=False,
        is_ship=False,
        is_vehicle=False,
        is_static=True,
        threat_range=meters(0),
        detection_range=meters(0),
        type=type("Structure", (), {"id": "Structure"}),
        unit_type=None,
    )


class Base:
    """A control point, hashable like the real one, since counters key on it."""

    def __init__(
        self,
        name: str,
        x_nm: float = 0.0,
        side: Player = Player.RED,
        fleet: bool = False,
        y_nm: float = 0.0,
    ) -> None:
        self.name = name
        self.position = at(x_nm, y_nm)
        self.captured = side
        self.is_fleet = fleet
        self.front_lines: dict[Any, Any] = {}
        self.base = SimpleNamespace(armor={})


def _placed(
    make: Callable[[PresetLocation, Any], TheaterGroundObject],
    name: str,
    x_nm: float,
    units: Sequence[Any],
    base: Any,
    y_nm: float,
    role: Optional[IadsRole],
) -> Any:
    location = PresetLocation(name, at(x_nm, y_nm))
    tgo = make(location, base or Base(f"{name} base", x_nm, y_nm=y_nm))
    group: TheaterGroup
    if role is None:
        group = TheaterGroup(1, name, location, list(units), tgo)
    else:
        group = IadsGroundGroup(1, name, location, list(units), tgo)
        group.iads_role = role
    tgo.groups = [group]
    return tgo


def sam(
    name: str,
    x_nm: float,
    units: Sequence[Any],
    base: Any = None,
    y_nm: float = 0.0,
    role: Optional[IadsRole] = None,
) -> Any:
    return _placed(
        lambda location, cp: SamGroundObject(name, location, cp, None),
        name,
        x_nm,
        units,
        base,
        y_nm,
        role,
    )


def armour(name: str, x_nm: float, units: Sequence[Any], base: Any = None) -> Any:
    return _placed(
        lambda location, cp: VehicleGroupGroundObject(name, location, cp, None),
        name,
        x_nm,
        units,
        base,
        0.0,
        None,
    )


def ships(name: str, x_nm: float, units: Sequence[Any], base: Any = None) -> Any:
    return _placed(
        lambda location, cp: ShipGroundObject(name, location, cp),
        name,
        x_nm,
        units,
        base,
        0.0,
        None,
    )


def building(
    name: str,
    category: str,
    x_nm: float,
    standing: int,
    fallen: int = 0,
    role: Optional[IadsRole] = None,
) -> Any:
    cls = BuildingGroundObject if role is None else IadsBuildingGroundObject
    parts = [structure() for _ in range(standing)] + [
        structure(alive=False) for _ in range(fallen)
    ]
    return _placed(
        lambda location, cp: cls(name, category, location, cp, None),
        name,
        x_nm,
        parts,
        None,
        0.0,
        role,
    )


def campaign(**parts: Any) -> Any:
    """The measuring context without a game behind it.

    ``points`` are where objectives will be measured, for the approach grid to reach.
    """
    made: Any = Campaign.__new__(Campaign)
    made.player = Player.BLUE
    made.enemy = Player.RED
    made.game = SimpleNamespace(
        theater=SimpleNamespace(
            controlpoints=parts.pop("enemy_bases", []),
            ground_objects=parts.pop("ground_objects", []),
        ),
        settings=SimpleNamespace(
            motorpool_enabled=False,
            motorpool_spawn_cap=0,
            plugin_option=lambda name: False,
        ),
    )
    made.groups = parts.pop("groups", {})
    made.rings = parts.pop("rings", [])
    made.our_bases = parts.pop("our_bases", [])
    made.our_aircraft_worth = defaultdict(float, parts.pop("our_aircraft_worth", {}))
    made.land_releases = [Release(DIRECT_RELEASE.meters)]
    made.sea_releases = [Release(DIRECT_RELEASE.meters)]
    made.aircraft = Counter(parts.pop("aircraft", {}))
    made.fighters = Counter(parts.pop("fighters", {}))
    made.squadrons = Counter(parts.pop("squadrons", {}))
    made.aircraft_worth = defaultdict(float, parts.pop("aircraft_worth", {}))
    made.enemy_income = parts.pop("enemy_income", 100.0)
    made.income_multiplier = 1.0
    made.network = parts.pop("network", None)
    made.skynet = made.network is not None
    made.advanced = made.skynet
    points = parts.pop("points", [])
    made.approach = (
        Approach(made.rings, [(b, b.position) for b in made.our_bases], points)
        if made.our_bases
        else None
    )
    assert not parts, parts
    return made
