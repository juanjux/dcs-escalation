"""What can be bought at a location, what it costs, and buying it.

Kept apart from the dialog: what a faction can field at a site, what a composition adds
up to and what happens when it is bought are answers the dialog asks for, not things it
works out while laying out widgets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional, Sequence, Type

from dcs.unittype import UnitType

from game import Game
from game.armedforces.forcegroup import ForceGroup
from game.data.groups import GroupRole, GroupTask
from game.data.units import UnitClass
from game.layout.layout import LayoutException, TgoLayout, TgoLayoutUnitGroup
from game.theater import TheaterGroundObject
from game.theater.theatergroundobject import (
    CoastalSiteGroundObject,
    EwrGroundObject,
    MissileSiteGroundObject,
    SamGroundObject,
    ShipGroundObject,
    VehicleGroupGroundObject,
)
from game.utils import Distance, meters

#: The headings the presets are grouped under, in the order they are shown.
TASK_SECTIONS: list[tuple[str, tuple[GroupTask, ...]]] = [
    ("Long range SAM", (GroupTask.LORAD,)),
    ("Medium range SAM", (GroupTask.MERAD,)),
    ("Short range", (GroupTask.SHORAD, GroupTask.POINT_DEFENSE)),
    ("Guns", (GroupTask.AAA,)),
    ("Sensors & EW", (GroupTask.EARLY_WARNING_RADAR,)),
    (
        "Ground forces",
        (GroupTask.FRONT_LINE, GroupTask.BASE_DEFENSE, GroupTask.MOTORPOOL),
    ),
    ("Missiles", (GroupTask.MISSILE, GroupTask.COASTAL)),
    (
        "Naval",
        (GroupTask.NAVY, GroupTask.AIRCRAFT_CARRIER, GroupTask.HELICOPTER_CARRIER),
    ),
]


@dataclass
class Option:
    """One unit type a slot can be filled with."""

    name: str
    dcs_type: Type[UnitType]
    price: int
    description: str = ""


@dataclass
class Slot:
    """One slot of a layout, and what is being bought for it."""

    group_name: str
    unit_group: TgoLayoutUnitGroup
    options: list[Option]
    chosen: int = 0
    amount: int = 1
    enabled: bool = True

    @property
    def option(self) -> Option:
        return self.options[self.chosen]

    @property
    def price(self) -> int:
        return self.amount * self.option.price if self.enabled else 0

    @property
    def count(self) -> int:
        return self.amount if self.enabled else 0

    @property
    def optional(self) -> bool:
        return bool(self.unit_group.optional)

    @property
    def max_size(self) -> int:
        return self.unit_group.max_size

    @property
    def fixed(self) -> bool:
        """Nothing to choose: one unit type, and only one of it."""
        return len(self.options) == 1 and self.max_size == 1


class Selection:
    """A layout of a force group, with a choice made for every slot it has."""

    def __init__(self, force_group: ForceGroup, layout: TgoLayout) -> None:
        self.force_group = force_group
        self.layout = layout
        self.slots: list[Slot] = []
        for group in layout.groups:
            for unit_group in group.unit_groups:
                options = list(_options_for(force_group, unit_group))
                if not options:
                    continue
                self.slots.append(
                    Slot(
                        group_name=group.group_name,
                        unit_group=unit_group,
                        options=options,
                        amount=min(unit_group.group_size, unit_group.max_size),
                        enabled=True,
                    )
                )

    @property
    def price(self) -> int:
        return sum(slot.price for slot in self.slots)

    @property
    def units(self) -> int:
        return sum(slot.count for slot in self.slots)

    @property
    def groups(self) -> list[tuple[str, list[Slot]]]:
        """The slots under the DCS group each of them belongs to, in layout order."""
        ordered: list[tuple[str, list[Slot]]] = []
        for slot in self.slots:
            if not ordered or ordered[-1][0] != slot.group_name:
                ordered.append((slot.group_name, []))
            ordered[-1][1].append(slot)
        return ordered


def _options_for(
    force_group: ForceGroup, unit_group: TgoLayoutUnitGroup
) -> Iterator[Option]:
    for unit_type in force_group.unit_types_for_group(unit_group):
        yield Option(
            name=str(unit_type.display_name),
            dcs_type=unit_type.dcs_unit_type,
            price=int(unit_type.price),
            description=str(unit_type.unit_class.description),
        )
    for static_type in force_group.statics_for_group(unit_group):
        yield Option(name=f"{static_type} (static)", dcs_type=static_type, price=0)


def tasks_for(ground_object: TheaterGroundObject) -> list[GroupTask]:
    """What a faction may field where this objective stands."""
    if isinstance(ground_object, (SamGroundObject, EwrGroundObject)):
        # A radar site, a missile battery and a jamming site are interchangeable: any
        # of the three can be bought where any one of them stands.
        return list(GroupRole.AIR_DEFENSE.tasks)
    if isinstance(ground_object, VehicleGroupGroundObject):
        return list(GroupRole.GROUND_FORCE.tasks)
    if isinstance(ground_object, ShipGroundObject):
        return [GroupTask.NAVY]
    if isinstance(ground_object, MissileSiteGroundObject):
        return [GroupTask.MISSILE]
    if isinstance(ground_object, CoastalSiteGroundObject):
        return [GroupTask.COASTAL]
    raise NotImplementedError(f"Unhandled TGO type {ground_object.__class__}")


def offers(ground_object: TheaterGroundObject) -> list[ForceGroup]:
    """The force groups the owning faction can build at this location."""
    coalition = ground_object.coalition
    return list(coalition.armed_forces.groups_for_tasks(tasks_for(ground_object)))


def section_of(force_group: ForceGroup) -> str:
    """The heading a preset is listed under."""
    for name, tasks in TASK_SECTIONS:
        if any(task in force_group.tasks for task in tasks):
            return name
    return "Other"


def reach_of(selection: Selection) -> tuple[str, Distance]:
    """How far the layout shoots, or failing that how far it sees."""
    threat = meters(0)
    detection = meters(0)
    for slot in selection.slots:
        for option in slot.options[:1]:
            threat = max(
                threat, meters(getattr(option.dcs_type, "threat_range", 0) or 0)
            )
            detection = max(
                detection, meters(getattr(option.dcs_type, "detection_range", 0) or 0)
            )
    if threat.meters > 0:
        return "", threat
    return "sees ", detection


def jams_gps(selection: Selection) -> bool:
    return any(
        UnitClass.ELECTRONIC_WARFARE.name
        and slot.option.description == UnitClass.ELECTRONIC_WARFARE.description
        for slot in selection.slots
    )


def here_now(
    ground_object: TheaterGroundObject, groups: Sequence[ForceGroup]
) -> Optional[ForceGroup]:
    """The force group whatever stands here came from, as far as can be told.

    Nothing records which group built a site, so it is read off the unit types parked
    there: the group that could have fielded all of them, and the smallest such group
    when more than one could.
    """
    parked = {unit.type for unit in ground_object.units}
    if not parked:
        return None

    best: Optional[ForceGroup] = None
    best_size = 0
    for group in groups:
        available = _types_of(group)
        if not parked <= available:
            continue
        if best is None or len(available) < best_size:
            best = group
            best_size = len(available)
    return best


def _types_of(force_group: ForceGroup) -> set[Type[UnitType]]:
    types: set[Type[UnitType]] = set()
    for layout in force_group.layouts:
        for group in layout.groups:
            for unit_group in group.unit_groups:
                try:
                    for unit_type in force_group.unit_types_for_group(unit_group):
                        types.add(unit_type.dcs_unit_type)
                    for static in force_group.statics_for_group(unit_group):
                        types.add(static)
                except LayoutException:
                    continue
    return types


def buy(
    selection: Selection,
    ground_object: TheaterGroundObject,
    game: Game,
    refund: int,
) -> None:
    """Replace what stands here with the chosen composition.

    The site faces the front afterwards, and the units arrive under the same repair
    delay an AI repair would take, as they did before.
    """
    ground_object.heading = (
        game.theater.heading_to_conflict_from(ground_object.position)
        or ground_object.heading
    )
    coalition = ground_object.coalition
    coalition.budget -= selection.price - refund
    # Clearing drops the cached threat ring too, which the combat simulation reads.
    ground_object.clear()

    for group_name, slots in selection.groups:
        for slot in slots:
            if not slot.enabled:
                continue
            try:
                selection.force_group.create_theater_group_for_tgo(
                    ground_object,
                    slot.unit_group,
                    f"{ground_object.name} ({group_name})",
                    game,
                    slot.option.dcs_type,
                    slot.amount,
                )
            except LayoutException:
                logging.exception(f"Could not create {slot.option.name}")

    repair_turns = game.settings.ground_object_repair_turns
    if game.turn and repair_turns > 0:
        # Player purchases respect repair delays like AI repairs.
        for unit in ground_object.units:
            if not unit.repairable:
                continue
            unit.alive = False
            unit.repair_turns_remaining = repair_turns
