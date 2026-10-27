"""Reviewed mobility data reaches planning, saves and generated detachments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.dispatch import dispatch_armor
from game.groundmovement.mobility import GroundMobility, MobilityMode
from game.groundmovement.planning import armor_movement_options, preview_armor_movement
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.test_armor_movement_dispatch import native, prepare
from tests.test_armor_movement_planning import world  # noqa: F401

CATALOG = {
    path.stem: yaml.safe_load(path.read_text("utf-8"))
    for path in Path("resources/units/ground_units").glob("*.yaml")
}


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_catalog_mobility_fields_are_valid(name: str) -> None:
    data = CATALOG[name]
    mobility = GroundMobility.from_data(data.get("ground_mobility"))
    if data.get("class") in {"Tank", "APC", "IFV", "ATGM", "Recon"}:
        assert mobility.mode is not MobilityMode.UNKNOWN, name
    for variant, overrides in data.get("variants", {}).items():
        if overrides and "ground_mobility" in overrides:
            GroundMobility.from_data(overrides["ground_mobility"])


@pytest.mark.parametrize(
    "name",
    [
        "M1045 HMMWV (BGM-71 TOW)",
        "M48 Chaparral",
        "M1097 Heavy HMMWV Avenger",
        "ZSU-23-4 Shilka",
        "M109A6 Paladin",
    ],
)
def test_armed_vehicles_need_no_tractor_and_are_not_spare_tractors(name: str) -> None:
    unit = GroundUnitType.named(name)
    assert unit.ground_mobility == GroundMobility(MobilityMode.SELF_PROPELLED)


@pytest.mark.parametrize("name", ["M1045 HMMWV (BGM-71 TOW)", "M48 Chaparral"])
def test_old_save_unknown_mobility_refreshes_from_catalog(name: str) -> None:
    unit = GroundUnitType.named(name)
    state = dict(unit.__dict__)
    state["ground_mobility"] = GroundMobility()
    restored = GroundUnitType.__new__(GroundUnitType)
    restored.__setstate__(state)
    assert restored.ground_mobility.mode is MobilityMode.SELF_PROPELLED


@pytest.mark.parametrize(
    "name,mode,can_tow",
    [
        ("CH_M777LTH_M795", MobilityMode.TOWED, False),
        ("CH_M777LTH_M982", MobilityMode.TOWED, False),
        ("CH_M777LTH_MTVR_M795", MobilityMode.SELF_PROPELLED, False),
        ("CH_M777LTH_MTVR_M982", MobilityMode.SELF_PROPELLED, False),
        ("CH_Centurion_C_RAM", MobilityMode.SELF_PROPELLED, False),
        ("CH_LD3000", MobilityMode.SELF_PROPELLED, False),
        ("CH_LD3000_stationary", MobilityMode.FIXED, False),
        ("CH_HX81", MobilityMode.SELF_PROPELLED, False),
        ("CH_HX81_Tractor", MobilityMode.SELF_PROPELLED, True),
        ("CH_HEMTT_M983", MobilityMode.SELF_PROPELLED, True),
        ("Ural-4320-31", MobilityMode.SELF_PROPELLED, True),
        ("ERO_ZU23_Toyota", MobilityMode.SELF_PROPELLED, False),
        ("ERO_ZU23_Insurgent", MobilityMode.TOWED, False),
        ("vap_type63_mlrs", MobilityMode.TOWED, False),
        ("SK_C_28_naval_gun", MobilityMode.FIXED, False),
        ("VABH", MobilityMode.SELF_PROPELLED, False),
        ("VAB_MORTIER", MobilityMode.SELF_PROPELLED, False),
    ],
)
def test_vehicle_and_deployed_mod_variants_remain_distinct(
    name: str, mode: MobilityMode, can_tow: bool
) -> None:
    assert GroundMobility.from_data(
        CATALOG[name].get("ground_mobility")
    ) == GroundMobility(mode, can_tow)


def test_missing_metadata_still_does_not_infer_self_propulsion_from_class() -> None:
    vehicle = GroundUnitType.named("M1045 HMMWV (BGM-71 TOW)").dcs_unit_type
    unknown = GroundUnitType._variant_from_dict(
        vehicle, "unreviewed vehicle", {"class": "ATGM"}
    )
    assert unknown.ground_mobility == GroundMobility()


def test_six_humvees_and_two_chaparrals_can_dispatch_without_trucks(world: Any) -> None:
    prepare(world)
    humvee = GroundUnitType.named("M1045 HMMWV (BGM-71 TOW)")
    chaparral = GroundUnitType.named("M48 Chaparral")
    identities = list(world.source.units)
    for index, unit in enumerate(identities):
        unit.type = (humvee if index < 6 else chaparral).dcs_unit_type
        unit.alive = True
    options = armor_movement_options(world.game, world.source.id, Player.BLUE)
    assert len(options.units) == 8 and all(unit.selectable for unit in options.units)
    assert (
        not options.warnings and options.available_tractors == options.towed_pieces == 0
    )
    selected = [unit.id for unit in identities]
    preview = preview_armor_movement(
        world.game, world.source.id, Player.BLUE, selected, world.destination
    )
    assert not preview.manifest.towing and not preview.remaining_unit_ids
    assert set(preview.manifest.unit_ids) == set(selected)
    transit = dispatch_armor(
        world.game,
        world.source.id,
        Player.BLUE,
        selected,
        world.destination,
        GameUpdateEvents(),
    )
    moving = world.game.db.tgos.get(transit.detachment_id)
    assert all(unit is original for unit, original in zip(moving.units, identities))
    group, unit_map = native(world, transit)
    assert len(group.units) == 8 and not unit_map.ground_transport_cargo
    assert [unit.type for unit in group.units].count(humvee.dcs_id) == 6
    assert [unit.type for unit in group.units].count(chaparral.dcs_id) == 2
    assert len(group.points) > 1 and group.points[0].speed > 0
