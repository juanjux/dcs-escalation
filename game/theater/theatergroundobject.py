from __future__ import annotations

import itertools
import uuid
from abc import ABC
from typing import Any, Iterator, List, Optional, TYPE_CHECKING

from dcs.mapping import Point
from shapely.geometry import Point as ShapelyPoint

from game.config import IADS_REPAIR_COST, REWARDS
from game.data.units import UnitClass
from game.ground_forces.ai_ground_planner import reserve_armor_for
from game.sidc import (
    Entity,
    LandEquipmentEntity,
    LandInstallationEntity,
    LandUnitEntity,
    SeaSurfaceEntity,
    SidcDescribable,
    StandardIdentity,
    Status,
    SymbolSet,
)
from game.theater.presetlocation import PresetLocation
from .missiontarget import MissionTarget
from .player import Player
from enum import Enum

from ..data.groups import GroupTask
from ..utils import Distance, Heading, meters, nautical_miles

if TYPE_CHECKING:
    from game.ato.flighttype import FlightType
    from game.dcs.groundunittype import GroundUnitType
    from game.threatzones import ThreatPoly
    from .theatergroup import TheaterUnit, TheaterGroup
    from .controlpoint import ControlPoint, Coalition


def _select_capped(
    reserve: dict[GroundUnitType, int], cap: int
) -> dict[GroundUnitType, int]:
    """Proportionally reduce ``reserve`` to at most ``cap`` units."""
    total = sum(reserve.values())
    if total <= cap:
        return {ut: n for ut, n in reserve.items() if n > 0}
    exact = {ut: count * cap / total for ut, count in reserve.items()}
    floors = {ut: int(v) for ut, v in exact.items()}
    remaining = cap - sum(floors.values())
    if remaining > 0:
        by_frac = sorted(
            ((ut, exact[ut] - floors[ut]) for ut in reserve),
            key=lambda kv: kv[1],
            reverse=True,
        )
        for ut, _frac in by_frac[:remaining]:
            floors[ut] += 1
    return {ut: n for ut, n in floors.items() if n > 0}


def motorpool_projected_counts(
    motorpools: list[MotorpoolGroundObject], cap: int
) -> list[dict[GroundUnitType, int]]:
    """Project one shared reserve pool across a CP's motorpool locations."""
    reserve = reserve_armor_for(motorpools[0].control_point)
    selected = _select_capped(reserve, cap)
    per_tgo: list[dict[GroundUnitType, int]] = [{} for _ in motorpools]
    slot = 0
    for unit_type, count in selected.items():
        for _ in range(count):
            bucket = per_tgo[slot % len(motorpools)]
            bucket[unit_type] = bucket.get(unit_type, 0) + 1
            slot += 1
    return per_tgo


def motorpool_rendered_unit_count(
    tgo: MotorpoolGroundObject, motorpool_enabled: bool, spawn_cap: int
) -> int:
    """Return the alive units in the current or next motorpool snapshot."""
    if not motorpool_enabled or spawn_cap <= 0:
        return 0
    motorpools = [
        candidate
        for candidate in tgo.control_point.ground_objects
        if isinstance(candidate, MotorpoolGroundObject)
    ]
    if tgo not in motorpools:
        return 0
    projected_count = sum(
        motorpool_projected_counts(motorpools, spawn_cap)[
            motorpools.index(tgo)
        ].values()
    )
    if tgo.groups:
        # Groups are ephemeral and may outlive a reserve decrement from the prior
        # mission. Never plan more units than the next current snapshot can render.
        return min(tgo.alive_unit_count, projected_count)
    return projected_count


NAME_BY_CATEGORY = {
    "ewr": "Early Warning Radar",
    "aa": "AA Defense Site",
    "allycamp": "Camp",
    "ammo": "Ammo depot",
    "armor": "Armor group",
    "coastal": "Coastal defense",
    "commandcenter": "Command Center",
    "comms": "Communications tower",
    "derrick": "Derrick",
    "factory": "Factory",
    "farp": "FARP",
    "fob": "FOB",
    "fuel": "Fuel depot",
    "missile": "Missile site",
    "motorpool": "Motorpool",
    "oil": "Oil platform",
    "power": "Power plant",
    "ship": "Ship",
    "village": "Village",
    "ware": "Warehouse",
    "ww2bunker": "Bunker",
}


class TheaterGroundObject(MissionTarget, SidcDescribable, ABC):
    def __init__(
        self,
        name: str,
        category: str,
        location: PresetLocation,
        control_point: ControlPoint,
        sea_object: bool,
        task: Optional[GroupTask],
        hide_on_mfd: Optional[bool] = None,
    ) -> None:
        super().__init__(name, location)
        self.id = uuid.uuid4()
        self.category = category
        self.heading = location.heading
        self.control_point = control_point
        self.sea_object = sea_object
        self.groups: List[TheaterGroup] = []
        self.original_name = location.original_name
        self._threat_poly: ThreatPoly | None = None
        self.task = task
        #: The player's own answer for this site, or None to follow the campaign
        #: settings. A site nobody has touched moves with them.
        self.hide_on_mfd = hide_on_mfd

        #: Where this site was when the turn began, for the settings that only show
        #: what a picture taken then would have found.
        self.mfd_seen_at: Optional[Point] = None
        self.required_unit_classes: set[UnitClass] = set()

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        del state["_threat_poly"]
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        state["_threat_poly"] = None
        self.__dict__.update(state)

    @property
    def sidc_status(self) -> Status:
        # Health-bar contract (the map bar is milsymbol's condition bar, driven by
        # this digit): intact -> FULLY_CAPABLE (green), any dead unit -> DAMAGED
        # (yellow), all dead unrepaired -> DESTROYED (red). "Repairing" is shown
        # ORANGE by the client, which recolours the yellow bar when the TGO's
        # `repairing` flag is set (see client tgos/shared.tsx) -- the digit itself
        # stays DAMAGED for both.
        if self.control_point.captured.is_neutral:
            return Status.PRESENT
        if self.is_dead:
            if self.has_pending_repairs:
                return Status.PRESENT_DAMAGED
            return Status.PRESENT_DESTROYED
        elif self.dead_units:
            return Status.PRESENT_DAMAGED
        else:
            return Status.PRESENT_FULLY_CAPABLE

    @property
    def has_pending_repairs(self) -> bool:
        for unit in self.units:
            if unit.alive:
                continue
            if unit.repair_turns_remaining is None:
                continue
            return True
        return False

    @property
    def standard_identity(self) -> StandardIdentity:
        if self.control_point.captured.is_blue:
            return StandardIdentity.FRIEND
        elif self.control_point.captured.is_neutral:
            return StandardIdentity.UNKNOWN
        else:
            return StandardIdentity.HOSTILE_FAKER

    @property
    def is_dead(self) -> bool:
        return self.alive_unit_count == 0

    @property
    def units(self) -> Iterator[TheaterUnit]:
        """
        :return: all the units at this location
        """
        yield from itertools.chain.from_iterable([g.units for g in self.groups])

    @property
    def statics(self) -> Iterator[TheaterUnit]:
        for group in self.groups:
            for unit in group.units:
                if unit.is_static:
                    yield unit

    @property
    def dead_units(self) -> list[TheaterUnit]:
        """
        :return: all the dead units at this location
        """
        return [unit for unit in self.units if not unit.alive]

    @property
    def group_name(self) -> str:
        """The name of the unit group."""
        return f"{self.category}|{self.name}"

    @property
    def display_name(self) -> str:
        """The display name of the tgo which will be shown on the map."""
        return self.group_name

    @property
    def waypoint_name(self) -> str:
        return f"[{self.name}] {self.category}"

    def __str__(self) -> str:
        return NAME_BY_CATEGORY[self.category]

    @property
    def obj_name(self) -> str:
        return self.name

    @property
    def faction_color(self) -> str:
        return "BLUE" if self.control_point.captured else "RED"

    def is_friendly(self, to_player: Player) -> bool:
        if self.control_point.captured.is_neutral:
            return False
        return self.control_point.is_friendly(to_player)

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if self.is_friendly(for_player):
            yield from [
                # TODO: FlightType.LOGISTICS
                # TODO: FlightType.TROOP_TRANSPORT
            ]
        else:
            yield from [
                FlightType.STRIKE,
                FlightType.REFUELING,
            ]
        yield from super().mission_types(for_player)

    @property
    def unit_count(self) -> int:
        return sum(g.unit_count for g in self.groups)

    @property
    def alive_unit_count(self) -> int:
        return sum(g.alive_units for g in self.groups)

    @property
    def has_aa(self) -> bool:
        """Returns True if the ground object contains a working anti air unit"""
        return any(u.alive and u.is_anti_air for u in self.units)

    @property
    def has_live_radar_sam(self) -> bool:
        """Returns True if the ground object contains a unit with working radar SAM."""
        return any(g.max_threat_range(radar_only=True) for g in self.groups)

    def max_detection_range(self) -> Distance:
        """Calculate the maximum detection range of the ground object"""
        return max((g.max_detection_range() for g in self.groups), default=meters(0))

    def max_threat_range(self) -> Distance:
        """Calculate the maximum threat range of the ground object"""
        return max((g.max_threat_range() for g in self.groups), default=meters(0))

    def threat_poly(self) -> ThreatPoly | None:
        if self._threat_poly is None:
            self._threat_poly = self._make_threat_poly()
        return self._threat_poly

    def invalidate_threat_poly(self) -> None:
        self._threat_poly = None

    def _make_threat_poly(self) -> ThreatPoly | None:
        threat_range = self.max_threat_range()
        if not threat_range:
            return None

        point = ShapelyPoint(self.position.x, self.position.y)
        return point.buffer(threat_range.meters)

    @property
    def is_ammo_depot(self) -> bool:
        return self.category == "ammo"

    @property
    def is_factory(self) -> bool:
        return self.category == "factory"

    @property
    def is_control_point(self) -> bool:
        """True if this TGO is the group for the control point itself (CVs and FOBs)."""
        return False

    @property
    def strike_targets(self) -> list[TheaterUnit]:
        return [unit for unit in self.units if unit.alive]

    @property
    def mark_locations(self) -> Iterator[Point]:
        yield self.position

    def clear(self) -> None:
        self.invalidate_threat_poly()
        self.groups = []

    @property
    def capturable(self) -> bool:
        raise NotImplementedError

    @property
    def purchasable(self) -> bool:
        raise NotImplementedError

    @property
    def repairable(self) -> bool:
        """Whether a destroyed group can be rebuilt or repaired, so the map should
        not treat it as a permanent loss. Re-purchasable groups (SAM/EWR/armor)
        qualify; BuildingGroundObject overrides this for the building-repair
        feature (buildings are not purchasable)."""
        return self.purchasable

    @property
    def value(self) -> int:
        """The value of all units of the Ground Objects"""
        return sum(u.unit_type.price for u in self.units if u.unit_type and u.alive)

    def group_by_name(self, name: str) -> Optional[TheaterGroup]:
        for group in self.groups:
            if group.name == name:
                return group
        return None

    def rotate(self, heading: Heading) -> None:
        """Rotate the whole TGO clockwise to the new heading"""
        rotation = heading - self.heading
        if rotation.degrees < 0:
            rotation = Heading.from_degrees(rotation.degrees + 360)

        self.heading = heading
        # Rotate the whole TGO to match the new heading
        for unit in self.units:
            unit.rotate_heading_clockwise(rotation)
            unit.rotate_position_clockwise(self.position, rotation)

    @property
    def should_head_to_conflict(self) -> bool:
        """Should this TGO head towards the closest conflict to work properly?"""
        return False

    @property
    def is_iads(self) -> bool:
        return False

    @property
    def coalition(self) -> Coalition:
        return self.control_point.coalition

    @property
    def is_naval_control_point(self) -> bool:
        return False


class BuildingGroundObject(TheaterGroundObject):
    def __init__(
        self,
        name: str,
        category: str,
        location: PresetLocation,
        control_point: ControlPoint,
        task: Optional[GroupTask],
        is_fob_structure: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            category=category,
            location=location,
            control_point=control_point,
            sea_object=False,
            task=task,
        )
        self.is_fob_structure = is_fob_structure

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        if self.category == "allycamp":
            entity = LandInstallationEntity.TENTED_CAMP
        elif self.category == "ammo":
            entity = LandInstallationEntity.AMMUNITION_CACHE
        elif self.category == "commandcenter":
            entity = LandInstallationEntity.MILITARY_INFRASTRUCTURE
        elif self.category == "comms":
            entity = LandInstallationEntity.TELECOMMUNICATIONS_TOWER
        elif self.category == "derrick":
            entity = LandInstallationEntity.PETROLEUM_FACILITY
        elif self.category == "factory":
            # A shed with two chimneys, which is what this symbol draws, is a better
            # picture of a factory than the wrench APP-6 keeps for a maintenance depot.
            # The map letters it FTRY, so it is not confused with the other stores that
            # share the symbol.
            entity = LandInstallationEntity.WAREHOUSE_STORAGE_FACILITY
        elif self.category == "farp":
            entity = LandInstallationEntity.HELICOPTER_LANDING_SITE
        elif self.category == "fuel":
            entity = LandInstallationEntity.WAREHOUSE_STORAGE_FACILITY
        elif self.category == "oil":
            entity = LandInstallationEntity.PETROLEUM_FACILITY
        elif self.category == "power":
            entity = LandInstallationEntity.GENERATION_STATION
        elif self.category == "village":
            entity = LandInstallationEntity.PUBLIC_VENUES_INFRASTRUCTURE
        elif self.category == "ware":
            entity = LandInstallationEntity.WAREHOUSE_STORAGE_FACILITY
        elif self.category == "ww2bunker":
            entity = LandInstallationEntity.MILITARY_BASE
        else:
            raise ValueError(f"Unhandled building category: {self.category}")
        return SymbolSet.LAND_INSTALLATIONS, entity

    @property
    def mark_locations(self) -> Iterator[Point]:
        # Special handling to mark all buildings of the TGO
        for unit in self.strike_targets:
            yield unit.position

    @property
    def is_control_point(self) -> bool:
        return self.is_fob_structure

    @property
    def capturable(self) -> bool:
        return True

    @property
    def purchasable(self) -> bool:
        return False

    @property
    def repairable(self) -> bool:
        # Buildings aren't purchasable, but the building-repair feature lets the
        # player rebuild income buildings (those with a repair cost). Repair is
        # available manually whenever the building has a repair cost -- it does
        # not require the (auto-repair) automate_building_repairs setting -- so
        # the map should not treat such a destroyed building as a permanent loss.
        return self.repair_cost() > 0

    def repair_cost(self) -> float:
        # IADS infrastructure is priced directly rather than off income, which it does
        # not have. The multipliers and bonuses below are all income-shaped, so they do
        # not apply.
        flat_cost = IADS_REPAIR_COST.get(self.category)
        if flat_cost is not None:
            return flat_cost
        income = REWARDS.get(self.category, 0.0)
        if income <= 0:
            return 0.0
        settings = self.control_point.coalition.game.settings
        cost = income * settings.building_repair_income_multiplier
        if self.is_ammo_depot:
            cost += settings.building_repair_ammo_bonus
        if self.is_factory:
            cost += settings.building_repair_factory_bonus
        return cost


class NavalGroundObject(TheaterGroundObject, ABC):
    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield from [
                FlightType.ANTISHIP,
                FlightType.SEAD,
            ]
        yield from super().mission_types(for_player)

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return self.control_point.coalition.game.turn == 0

    @property
    def is_iads(self) -> bool:
        return True


class GenericCarrierGroundObject(NavalGroundObject, ABC):
    @property
    def is_control_point(self) -> bool:
        return True

    @property
    def is_naval_control_point(self) -> bool:
        return True


# TODO: Why is this both a CP and a TGO?
class CarrierGroundObject(GenericCarrierGroundObject):
    def __init__(
        self, name: str, location: PresetLocation, control_point: ControlPoint
    ) -> None:
        super().__init__(
            name=name,
            category="CARRIER",
            location=location,
            control_point=control_point,
            sea_object=True,
            task=GroupTask.AIRCRAFT_CARRIER,
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return SymbolSet.SEA_SURFACE, SeaSurfaceEntity.CARRIER

    def __str__(self) -> str:
        return f"CV {self.name}"


# TODO: Why is this both a CP and a TGO?
class LhaGroundObject(GenericCarrierGroundObject):
    def __init__(
        self, name: str, location: PresetLocation, control_point: ControlPoint
    ) -> None:
        super().__init__(
            name=name,
            category="LHA",
            location=location,
            control_point=control_point,
            sea_object=True,
            task=GroupTask.HELICOPTER_CARRIER,
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return SymbolSet.SEA_SURFACE, SeaSurfaceEntity.AMPHIBIOUS_ASSAULT_SHIP_GENERAL

    def __str__(self) -> str:
        return f"LHA {self.name}"


class MissileSiteGroundObject(TheaterGroundObject):
    def __init__(
        self, name: str, location: PresetLocation, control_point: ControlPoint
    ) -> None:
        super().__init__(
            name=name,
            category="missile",
            location=location,
            control_point=control_point,
            sea_object=False,
            task=GroupTask.MISSILE,
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return SymbolSet.LAND_UNIT, LandUnitEntity.MISSILE

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return self.control_point.coalition.game.turn == 0

    @property
    def should_head_to_conflict(self) -> bool:
        return True

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.BAI
        for mission_type in super().mission_types(for_player):
            yield mission_type


class CoastalSiteGroundObject(TheaterGroundObject):
    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
    ) -> None:
        super().__init__(
            name=name,
            category="coastal",
            location=location,
            control_point=control_point,
            sea_object=False,
            task=GroupTask.COASTAL,
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return SymbolSet.LAND_UNIT, LandUnitEntity.MISSILE

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return self.control_point.coalition.game.turn == 0

    @property
    def should_head_to_conflict(self) -> bool:
        return True

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.BAI
        for mission_type in super().mission_types(for_player):
            yield mission_type


#: What makes a site read as a missile battery rather than a bare radar. TELAR and
#: SHORAD carry their own launcher; MANPAD and AAA are what a point-defence-only site
#: fields, and both still shoot.
LAUNCHER_CLASSES = frozenset(
    {
        UnitClass.LAUNCHER,
        UnitClass.TELAR,
        UnitClass.SHORAD,
        UnitClass.MANPAD,
        UnitClass.AAA,
    }
)


#: What counts as having something to look with, for a site with nothing that shoots.
RADAR_CLASSES = frozenset(
    {
        UnitClass.EARLY_WARNING_RADAR,
        UnitClass.SEARCH_RADAR,
        UnitClass.SEARCH_TRACK_RADAR,
        UnitClass.SPECIALIZED_RADAR,
        UnitClass.TRACK_RADAR,
    }
)

#: The slots a campaign puts a missile battery or a gun in.
AIR_DEFENCE_TASKS = frozenset(
    {
        GroupTask.AAA,
        GroupTask.LORAD,
        GroupTask.MERAD,
        GroupTask.POINT_DEFENSE,
        GroupTask.SHORAD,
    }
)


class AirDefenceKind(Enum):
    """The three things an air-defence site can be, whatever it was created as."""

    #: Denies GPS. Has no radar and cues nobody.
    JAMMER = "jammer"

    #: Shoots: a missile battery or a gun.
    BATTERY = "battery"

    #: Looks: an early-warning or search radar.
    RADAR = "radar"


class IadsGroundObject(TheaterGroundObject, ABC):
    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
        task: Optional[GroupTask],
        category: str = "aa",
    ) -> None:
        super().__init__(
            name=name,
            category=category,
            location=location,
            control_point=control_point,
            sea_object=False,
            task=task,
        )

    @property
    def carries_gps_jammer(self) -> bool:
        """Whether this site jams GPS, whatever slot the campaign put it in.

        Read off the units rather than off the class, the same way the map symbol is:
        a radar site, a missile battery and a jamming site are interchangeable now.
        """
        return any(
            unit.unit_type is not None and getattr(unit.unit_type, "gps_jamming", None)
            for group in self.groups
            for unit in group.units
        )

    @property
    def air_defence_kind(self) -> AirDefenceKind:
        """What this site is, read off what is parked there.

        A radar site, a missile battery and a jamming site are interchangeable on the
        map -- any of the three can be bought where any one of them stands -- so the
        class the campaign created the site as does not answer the question. A jammer
        wins over everything (it is the thing worth telling apart), then a launcher,
        then a radar.

        An emptied site has nothing to read: a captured or disbanded one keeps no
        units at all. What is left is the slot the campaign gave it, which is what it
        will be again the moment something is bought there.
        """
        if self.carries_gps_jammer:
            return AirDefenceKind.JAMMER

        shoots = False
        sees = False
        for group in self.groups:
            for unit in group.units:
                unit_type = unit.unit_type
                if unit_type is not None and getattr(unit_type, "gps_jamming", None):
                    continue
                unit_class = getattr(unit_type, "unit_class", None)
                if unit_class in LAUNCHER_CLASSES:
                    shoots = True
                elif unit_class in RADAR_CLASSES:
                    sees = True
        if shoots:
            return AirDefenceKind.BATTERY
        if sees:
            return AirDefenceKind.RADAR

        if self.task is GroupTask.EARLY_WARNING_RADAR:
            return AirDefenceKind.RADAR
        if self.task in AIR_DEFENCE_TASKS:
            return AirDefenceKind.BATTERY
        return (
            AirDefenceKind.RADAR
            if isinstance(self, EwrGroundObject)
            else AirDefenceKind.BATTERY
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        kind = self.air_defence_kind
        if kind is AirDefenceKind.JAMMER:
            return SymbolSet.LAND_UNIT, LandUnitEntity.ELECTRONIC_WARFARE_JAMMING
        if kind is AirDefenceKind.BATTERY:
            return SymbolSet.LAND_UNIT, LandUnitEntity.AIR_DEFENSE
        return SymbolSet.LAND_EQUIPMENT, LandEquipmentEntity.RADAR

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.DEAD
        yield from super().mission_types(for_player)

    @property
    def should_head_to_conflict(self) -> bool:
        return True

    @property
    def is_iads(self) -> bool:
        return True


# The SamGroundObject represents all type of AA
# The TGO can have multiple types of units (AAA,SAM,Support...)
# Differentiation can be made during generation with the airdefensegroupgenerator
class SamGroundObject(IadsGroundObject):
    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
        task: Optional[GroupTask],
    ) -> None:
        super().__init__(
            name=name,
            category="aa",
            location=location,
            control_point=control_point,
            task=task,
        )

    # sidc_status: no override. A SAM used to report PRESENT (no bar) when damaged
    # but still projecting a threat ring, hiding real damage from the map; the base
    # green/yellow/red contract applies now, and the ring already tells whether the
    # site still threatens.

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.DEAD
            yield FlightType.SEAD
        for mission_type in super().mission_types(for_player):
            # We yielded this ourselves to move it to the top of the list. Don't yield
            # it twice.
            if mission_type is not FlightType.DEAD:
                yield mission_type

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return True


class VehicleGroupGroundObject(TheaterGroundObject):
    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
        task: Optional[GroupTask],
    ) -> None:
        super().__init__(
            name=name,
            category="armor",
            location=location,
            control_point=control_point,
            sea_object=False,
            task=task,
        )

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return (
            SymbolSet.LAND_UNIT,
            LandUnitEntity.ARMOR_ARMORED_MECHANIZED_SELF_PROPELLED_TRACKED,
        )

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return True

    @property
    def should_head_to_conflict(self) -> bool:
        return True

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.BAI
        yield from super().mission_types(for_player)


class MotorpoolGroundObject(TheaterGroundObject):
    """A control point's not-deployed reserve armor, rendered as a stationary,
    strikeable vehicle park. Its groups and projection keys are a persisted cache
    reconciled from the current reserve slice by MotorpoolPopulator."""

    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
        task: Optional[GroupTask],
    ) -> None:
        super().__init__(
            name=name,
            category="motorpool",
            location=location,
            control_point=control_point,
            sea_object=False,
            task=task,
        )
        # group-id -> the exact GroundUnitType variant that group represents, so
        # the renderer decrements the right base.armor key.
        self.motorpool_unit_types: dict[int, GroundUnitType] = {}
        # unit-id -> stable desired-projection key. Persisted with groups so an
        # unchanged reconciliation preserves object identity and campaign IDs.
        self.motorpool_projection_keys: dict[int, tuple[uuid.UUID, str, int]] = {}

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        # Reserve vehicles are rendered per mission from the current base reserve;
        # never persist their generated groups or the renderer's lookup map.
        state["groups"] = []
        state["motorpool_unit_types"] = {}
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        state["groups"] = []
        state["motorpool_unit_types"] = {}
        super().__setstate__(state)

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        # Maintenance-facility installation symbol: visually distinct from the
        # armor-group symbol so the motorpool reads as a depot, not a fighting unit.
        return (
            SymbolSet.LAND_INSTALLATIONS,
            LandInstallationEntity.MAINTENANCE_FACILITY,
        )

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        # Not individually bought; reflects the reserve pool.
        return False

    @property
    def repairable(self) -> bool:
        # The base default ties this to purchasable, which is wrong here: the
        # motorpool is a view of the reserve, so buying ground units refills it.
        # A flattened one is never a permanent loss.
        return True

    @property
    def should_head_to_conflict(self) -> bool:
        # Parked/unmanned: never advances to the front.
        return False

    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield FlightType.BAI
        yield from super().mission_types(for_player)

    @property
    def sidc_status(self) -> Status:
        # A motorpool is a live reserve projection: empty is a valid disabled or
        # zero-reserve state, not destruction. Always render as a present depot —
        # never damaged/destroyed.
        # is_dead is deliberately left intact so AI target-selection, capture, and
        # IADS logic (which read is_dead, not sidc_status) are unaffected.
        return Status.PRESENT

    def clear(self) -> None:
        # Keep persisted projection metadata in lockstep with groups so a wiped
        # motorpool (e.g. on capture) leaves no dangling keys behind.
        super().clear()
        self.motorpool_unit_types = {}
        self.motorpool_projection_keys = {}


class EwrGroundObject(IadsGroundObject):
    def __init__(
        self,
        name: str,
        location: PresetLocation,
        control_point: ControlPoint,
    ) -> None:
        super().__init__(
            name=name,
            location=location,
            control_point=control_point,
            category="ewr",
            task=GroupTask.EARLY_WARNING_RADAR,
        )

    @property
    def capturable(self) -> bool:
        return False

    @property
    def purchasable(self) -> bool:
        return True


class ShipGroundObject(NavalGroundObject):
    def __init__(
        self, name: str, location: PresetLocation, control_point: ControlPoint
    ) -> None:
        super().__init__(
            name=name,
            category="ship",
            location=location,
            control_point=control_point,
            sea_object=True,
            task=GroupTask.NAVY,
        )
        # Movement state (mirrors NavalControlPoint). Blue ownership is enforced
        # at the API/serialization layer, not here.
        self.target_position: Optional[Point] = None

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return SymbolSet.SEA_SURFACE, SeaSurfaceEntity.SURFACE_COMBATANT_LINE

    @property
    def moveable(self) -> bool:
        return True

    @property
    def max_move_distance(self) -> Distance:
        return nautical_miles(80)

    def destination_in_range(self, destination: Point) -> bool:
        distance = meters(destination.distance_to_point(self.position))
        return distance <= self.max_move_distance


class IadsBuildingGroundObject(BuildingGroundObject):
    def mission_types(self, for_player: Player) -> Iterator[FlightType]:
        from game.ato import FlightType

        if not self.is_friendly(for_player):
            yield from [FlightType.STRIKE, FlightType.DEAD]
        skippers = [FlightType.STRIKE]  # prevent yielding twice
        for mission_type in super().mission_types(for_player):
            if mission_type not in skippers:
                yield mission_type

    @property
    def is_iads(self) -> bool:
        return True
