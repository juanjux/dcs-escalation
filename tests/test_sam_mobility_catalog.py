"""Evidence-backed SAM mobility is shared by catalog loading, API and missions."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from dcs.lua import loads
import pytest
import yaml

from game.agent import groundmovement
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.mobility import GroundMobility, MobilityMode
from game.groundmovement.dispatch import advance_armor
from game.groundmovement.samdefense import transit_defense
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.test_armor_movement_dispatch import native
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_sam_movement import generate_site, make_site, move

AUDIT = json.loads(Path("docs/dev/sam-mobility-audit.json").read_text("utf-8"))
REVIEWED = AUDIT["units"]
CLASSIFIED = [row for row in REVIEWED if row["mode"] != "unknown"]
HQ22 = (
    "[CH] HQ-22 JSG-100 SR",
    "[CH] HQ-22 H-200 STR",
    "[CH] HQ-22 LN",
    "[CH] SX2190 Truck",
)


def red_options(world: Any) -> dict[str, Any]:
    world.a._coalition.player = world.b._coalition.player = Player.RED
    world.enemy._coalition.player = Player.BLUE
    return groundmovement.options(world.game, world.sam.id, "sam")


def test_audit_accounts_for_every_originally_unknown_type() -> None:
    assert len({row["dcs_id"] for row in REVIEWED}) == 108
    assert AUDIT["counts"]["reviewed"] == len(REVIEWED)
    assert dict(Counter(row["mode"] for row in REVIEWED)) == {
        mode: count for mode, count in AUDIT["counts"].items() if mode != "reviewed"
    }
    assert all(row["reason"] for row in REVIEWED)
    assert all(row["sources"] for row in CLASSIFIED)
    assert not any(row["mode"] == "unknown" for row in REVIEWED)
    assert AUDIT["follow_up"]["remaining_unknown"] == 0


def test_all_registered_air_defence_and_auxiliary_types_have_mobility() -> None:
    classes = {
        "AAA",
        "CommandPost",
        "EarlyWarningRadar",
        "Launcher",
        "OpticalTracker",
        "Power",
        "SearchLight",
        "SearchRadar",
        "SearchTrackRadar",
        "SHORAD",
        "SpecializedRadar",
        "TELAR",
        "TrackRadar",
    }
    missing = [
        unit.variant_id
        for vehicle in GroundUnitType.each_dcs_type()
        for unit in GroundUnitType.for_dcs_type(vehicle)
        if unit.unit_class.value in classes
        and unit.ground_mobility.mode is MobilityMode.UNKNOWN
    ]
    assert missing == []


@pytest.mark.parametrize(
    "row",
    [row for row in REVIEWED if row["mode"] == "fixed"],
    ids=lambda row: row["dcs_id"],
)
def test_reviewed_fixed_installations_remain_blocked_even_with_carriers(
    world: Any, row: dict[str, Any]
) -> None:
    name = row["variants"][0]
    unit = GroundUnitType.named(name)
    assert unit.ground_mobility.mode is MobilityMode.FIXED
    make_site(world, (name, "Truck Ural-375"))
    options = red_options(world)
    assert not options["enabled"]
    assert not options["units"][0]["selectable"]
    assert options["warnings"]
    with pytest.raises(ValueError):
        move(world)
    assert not world.game.ground_movements.orders


@pytest.mark.parametrize(
    "names",
    [
        ("SAM SA-10B S-300PS 54K6 CP", "SAM SA-10B S-300PS 5P85SE LN"),
        ("SAM SA-23 S-300VM 9S457ME CP", "SAM SA-23 S-300VM 9A82ME LN"),
        ("SAM SA-21 S-400 CP 55K6", "SAM SA-21 S-400 LN 51P6A (48N6DM)"),
        ("Polyana-D4M1 C2 node", 'MCC-SR Sborka "Dog Ear" SR'),
        ("David's Sling CP", "Iron Dome CP"),
        (
            "[CH] LvS-103 PM 103 STR (HX)",
            "[CH] LvS-103 Lavett 103 Rb103A LN (HX)",
            "[CH] LvS-103 Lavett 103 Rb103B LN (HX)",
            "[CH] LvS-103 Elverk 103 EPP (HX)",
            "[CH] LvS-103 StriE 103 ECS (HX)",
        ),
    ],
)
def test_reviewed_powered_components_export_without_extra_tractors(
    world: Any, names: tuple[str, ...]
) -> None:
    site = make_site(world, names)
    options = red_options(world)
    assert options["enabled"]
    assert options["available_tractors"] == options["towed_pieces"] == 0
    assert all(row["selectable"] for row in options["units"])
    group, mapping = native(world, move(world))
    assert [unit.type for unit in group.units] == [
        GroundUnitType.named(name).dcs_id for name in names
    ]
    assert not mapping.ground_transport_cargo
    assert len(group.points) > 1
    assert transit_defense(unit.type for unit in group.units) is None


@pytest.mark.parametrize(
    "row",
    [row for row in REVIEWED if row["mode"] == "towed" and "reviewed_on" in row],
    ids=lambda row: row["dcs_id"],
)
def test_newly_reviewed_deployed_equipment_moves_only_as_loaded_cargo(
    world: Any, row: dict[str, Any]
) -> None:
    name = row["variants"][0]
    make_site(world, (name,))
    options = red_options(world)
    assert not options["enabled"]
    assert options["towed_pieces"] == 1 and options["available_tractors"] == 0
    with pytest.raises(ValueError, match="only 0"):
        move(world)
    assert not world.game.ground_movements.orders

    site = make_site(world, (name, "Truck Ural-375"))
    options = red_options(world)
    assert options["enabled"]
    assert options["towed_pieces"] == options["available_tractors"] == 1
    group, mapping = native(world, move(world))
    assert [unit.type for unit in group.units] == ["Ural-375"]
    assert len(mapping.ground_transport_cargo) == 1
    assert len(list(site.units)) == 2


def test_skyshield_sensor_and_gun_require_separate_carriers(world: Any) -> None:
    make_site(
        world,
        ("[CH] Skyshield C-RAM STR", "[CH] Skyshield C-RAM Gun", "Truck Ural-375"),
    )
    options = red_options(world)
    assert not options["enabled"]
    assert options["towed_pieces"] == 2 and options["available_tractors"] == 1
    with pytest.raises(ValueError, match="only 1"):
        move(world)
    assert not world.game.ground_movements.orders


@pytest.mark.parametrize("row", REVIEWED, ids=lambda row: row["dcs_id"])
def test_catalog_and_all_aliases_match_the_reviewed_mode(row: dict[str, Any]) -> None:
    for name in row["variants"]:
        unit = GroundUnitType.named(name)
        assert unit.dcs_id == row.get("replacement_dcs_id", row["dcs_id"])
        assert unit.ground_mobility == GroundMobility(MobilityMode(row["mode"]))


def test_powered_models_without_native_drivers_require_carrier_transport() -> None:
    rows = [
        row
        for row in REVIEWED
        if row.get("physical_mode") == "self_propelled" and row.get("carrier_assisted")
    ]
    assert len(rows) == 15  # Six HDS radars, eight SAMP/T trucks and native 1L13.
    assert all(row["mode"] == "towed" for row in rows)
    assert all(row["geometry_evidence"]["sha256"] for row in rows)


@pytest.mark.parametrize("row", REVIEWED, ids=lambda row: row["dcs_id"])
def test_reviewed_yaml_retains_explicit_mode_including_retired_ids(
    row: dict[str, Any],
) -> None:
    data = yaml.safe_load(
        (Path("resources/units/ground_units") / f"{row['dcs_id']}.yaml").read_text(
            "utf-8"
        )
    )
    assert data["ground_mobility"]["mode"] == row["mode"]


def test_sampt_trucks_without_native_drivers_need_one_carrier_each(world: Any) -> None:
    names = tuple(
        row["variants"][0] for row in REVIEWED if row["dcs_id"].startswith("SAMPT_")
    )
    assert len(names) == 8
    make_site(world, names + ("Truck Ural-375",) * 7)
    options = red_options(world)
    assert not options["enabled"]
    assert options["towed_pieces"] == 8 and options["available_tractors"] == 7
    with pytest.raises(ValueError, match="only 7"):
        move(world)
    assert not world.game.ground_movements.orders

    site = make_site(world, names + ("Truck Ural-375",) * 8)
    originals = list(site.units)
    transit = move(world)
    group, mapping = native(world, transit)
    assert [unit.type for unit in group.units] == ["Ural-375"] * 8
    assert len(mapping.ground_transport_cargo) == 8
    assert len(list(site.units)) == len(originals) == 16
    assert all(unit is original for unit, original in zip(site.units, originals))


@pytest.mark.parametrize(
    "dcs_id",
    ["S-300PMU1 40B6MD sr", "S-400 96L6E mast sr", "P14_SR"],
)
def test_mast_or_trailer_geometry_is_not_promoted_by_inherited_speed(
    dcs_id: str,
) -> None:
    row = next(row for row in REVIEWED if row["dcs_id"] == dcs_id)
    assert row["physical_mode"] == row["mode"] == "towed"
    assert row["geometry_evidence"]["sha256"]


@pytest.mark.parametrize(
    "dcs_ids",
    [
        tuple(row["dcs_id"] for row in REVIEWED if row["dcs_id"].startswith("SAMPT_")),
        ("1L13 EWR", "P14_SR", "S-300V 9S32 tr"),
    ],
)
def test_carrier_assisted_equipment_exports_and_redeploys_as_original_types(
    world: Any, tmp_path: Path, dcs_ids: tuple[str, ...]
) -> None:
    names = tuple(
        next(row["variants"][0] for row in REVIEWED if row["dcs_id"] == dcs_id)
        for dcs_id in dcs_ids
    )
    site = make_site(world, names + ("Truck Ural-375",) * len(names))
    originals = list(site.units)
    original_types = Counter(unit.type.id for unit in originals)
    move(world)
    mission, mapping = generate_site(world)
    output = tmp_path / "carrier-assisted-sam.miz"
    mission.save(output)
    with ZipFile(output) as archive:
        data = loads(archive.read("mission").decode())["mission"]
    groups = [
        group
        for country in data["coalition"]["blue"]["country"].values()
        for group in country.get("vehicle", {}).get("group", {}).values()
    ]
    assert len(groups) == 1
    assert [unit["type"] for unit in groups[0]["units"].values()] == ["Ural-375"] * len(
        names
    )
    assert len(groups[0]["route"]["points"]) > 1
    assert len(mapping.ground_transport_cargo) == len(names)

    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert not site.in_transit
    assert all(unit is old for unit, old in zip(site.units, originals))
    assert all(unit.transported_by_id is None for unit in site.units)
    redeployed, _mapping = generate_site(world)
    assert (
        Counter(
            unit.type
            for group in redeployed.country("USA").vehicle_group
            for unit in group.units
        )
        == original_types
    )


@pytest.mark.parametrize("row", CLASSIFIED, ids=lambda row: row["dcs_id"])
def test_old_save_unknown_mobility_refreshes_from_reviewed_catalog(
    row: dict[str, Any],
) -> None:
    unit = GroundUnitType.named(row["variants"][0])
    state = {**unit.__dict__, "ground_mobility": GroundMobility()}
    restored = GroundUnitType.__new__(GroundUnitType)
    restored.__setstate__(state)
    assert restored.ground_mobility == unit.ground_mobility


def test_hq22_api_options_and_export_preserve_all_vehicles(world: Any) -> None:
    site = make_site(world, HQ22)
    world.a._coalition.player = world.b._coalition.player = Player.RED
    world.enemy._coalition.player = Player.BLUE
    options = groundmovement.options(world.game, site.id, "sam")
    assert options["enabled"]
    assert options["available_tractors"] == options["towed_pieces"] == 0
    assert len(options["units"]) == 4
    assert all(
        row["mobility"] == "self_propelled" and row["selectable"]
        for row in options["units"]
    )
    assert not any("Mobility is not available" in w for w in options["warnings"])
    transit = move(world)
    group, mapping = native(world, transit)
    assert {unit.type for unit in group.units} == {
        GroundUnitType.named(name).dcs_id for name in HQ22
    }
    assert len(group.points) > 1
    assert not mapping.ground_transport_cargo
    assert transit_defense(unit.type for unit in group.units) is None


def test_skyshield_gun_needs_a_carrier_and_is_not_a_second_live_gun(
    world: Any,
) -> None:
    site = make_site(world, ("[CH] Skyshield C-RAM Gun", "Truck Ural-375"))
    transit = move(world)
    group, mapping = native(world, transit)
    assert [unit.type for unit in group.units] == ["Ural-375"]
    assert len(mapping.ground_transport_cargo) == 1
    assert len(list(site.units)) == 2


def test_skyshield_gun_without_carrier_stays_in_place(world: Any) -> None:
    make_site(world, ("[CH] Skyshield C-RAM Gun",))
    with pytest.raises(ValueError, match="only 0"):
        move(world)
    assert not world.game.ground_movements.orders
