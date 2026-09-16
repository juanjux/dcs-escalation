"""An air-defence site's map symbol follows what is parked there.

A radar site, a missile battery and a jamming site can all be bought where any one of
them stands, so the class the campaign created the site as stopped being an answer to
what it is. The symbol reads the units instead: jamming wins, then a launcher, and a
site with neither is a radar.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from game.data.groups import GroupTask
from game.data.units import UnitClass
from game.sidc import (
    Entity,
    LandEquipmentEntity,
    LandUnitEntity,
    SymbolSet,
)
from game.theater.theatergroundobject import (
    EwrGroundObject,
    IadsGroundObject,
    SamGroundObject,
)


def _site(
    kind: type[IadsGroundObject],
    unit_classes: list[UnitClass],
    jamming: bool = False,
    task: GroupTask | None = None,
) -> IadsGroundObject:
    site: IadsGroundObject = object.__new__(kind)
    units: list[MagicMock] = []
    for unit_class in unit_classes:
        unit = MagicMock()
        unit.unit_type.unit_class = unit_class
        unit.unit_type.gps_jamming = None
        units.append(unit)
    if jamming:
        jammer = MagicMock()
        jammer.unit_type.unit_class = UnitClass.ELECTRONIC_WARFARE
        jammer.unit_type.gps_jamming = MagicMock()
        units.append(jammer)
    group = MagicMock()
    group.units = units
    site.groups = [group] if units else []
    site.task = task
    return site


def _symbol(site: IadsGroundObject) -> tuple[SymbolSet, Entity]:
    return site.symbol_set_and_entity


def test_a_launcher_makes_it_a_missile_battery() -> None:
    site = _site(SamGroundObject, [UnitClass.SEARCH_RADAR, UnitClass.LAUNCHER])
    assert _symbol(site) == (SymbolSet.LAND_UNIT, LandUnitEntity.AIR_DEFENSE)


def test_radars_alone_make_it_a_radar_site() -> None:
    site = _site(SamGroundObject, [UnitClass.EARLY_WARNING_RADAR])
    assert _symbol(site) == (SymbolSet.LAND_EQUIPMENT, LandEquipmentEntity.RADAR)


def test_a_jammer_wins_over_its_own_point_defence() -> None:
    """The security section shoots, but the site is worth telling apart as a jammer."""
    site = _site(EwrGroundObject, [UnitClass.AAA], jamming=True)
    assert _symbol(site) == (
        SymbolSet.LAND_UNIT,
        LandUnitEntity.ELECTRONIC_WARFARE_JAMMING,
    )


def test_the_class_it_was_created_as_does_not_decide() -> None:
    """Buying a battery at a radar marker has to change the icon, and the reverse."""
    bought_a_battery = _site(EwrGroundObject, [UnitClass.LAUNCHER])
    bought_a_radar = _site(SamGroundObject, [UnitClass.SEARCH_RADAR])
    assert _symbol(bought_a_battery) == (
        SymbolSet.LAND_UNIT,
        LandUnitEntity.AIR_DEFENSE,
    )
    assert _symbol(bought_a_radar) == (
        SymbolSet.LAND_EQUIPMENT,
        LandEquipmentEntity.RADAR,
    )


def test_an_emptied_site_keeps_the_slot_it_was_given() -> None:
    """Capturing a site clears it, and a cleared one has no units left to read."""
    gun = _site(SamGroundObject, [], task=GroupTask.AAA)
    radar = _site(SamGroundObject, [], task=GroupTask.EARLY_WARNING_RADAR)

    assert _symbol(gun) == (SymbolSet.LAND_UNIT, LandUnitEntity.AIR_DEFENSE)
    assert _symbol(radar) == (SymbolSet.LAND_EQUIPMENT, LandEquipmentEntity.RADAR)


def test_an_emptied_site_without_a_slot_falls_back_to_its_class() -> None:
    battery = _site(SamGroundObject, [], task=None)
    radar = _site(EwrGroundObject, [], task=None)

    assert _symbol(battery) == (SymbolSet.LAND_UNIT, LandUnitEntity.AIR_DEFENSE)
    assert _symbol(radar) == (SymbolSet.LAND_EQUIPMENT, LandEquipmentEntity.RADAR)


def test_support_trucks_alone_do_not_make_a_battery_a_radar() -> None:
    site = _site(SamGroundObject, [UnitClass.LOGISTICS], task=GroupTask.MERAD)

    assert _symbol(site) == (SymbolSet.LAND_UNIT, LandUnitEntity.AIR_DEFENSE)
