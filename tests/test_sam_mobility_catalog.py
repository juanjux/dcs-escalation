"""Evidence-backed SAM mobility is shared by catalog loading, API and missions."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import pytest

from game.agent import groundmovement
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.mobility import GroundMobility, MobilityMode
from game.groundmovement.samdefense import transit_defense
from game.theater.player import Player
from tests.test_armor_movement_dispatch import native
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_sam_movement import make_site, move

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


@pytest.mark.parametrize(
    "name",
    [
        "SAM SA-20 S-300PMU1 TR 30N6E(truck)",
        "SAM SA-20B S-300PMU2 TR 92H6E(truck)",
        "SAM SA-21 S-400 TR 92N6E (truck)",
        "SAM SA-12 S-300V 9S32 TR",
        "SAM SA-23 S-300VM 9S32ME TR",
        "SAM SA-23 S-300V4 9S32M-1E TR",
        "[CH] LvS-103 Lavett 103 Rb103A LN",
        "[CH] LvS-103 Lavett 103 Rb103B LN",
        "[CH] LvS-103 PM 103 STR",
    ],
)
def test_unverified_chassis_and_deployed_variants_remain_blocked(
    world: Any, name: str
) -> None:
    unit = GroundUnitType.named(name)
    assert unit.ground_mobility == GroundMobility()
    make_site(world, (name,))
    options = red_options(world)
    assert not options["enabled"]
    assert not options["units"][0]["selectable"]
    assert any("Mobility is not available" in w for w in options["warnings"])
    with pytest.raises(ValueError, match="Mobility is not available"):
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
        assert unit.dcs_id == row["dcs_id"]
        assert unit.ground_mobility == GroundMobility(MobilityMode(row["mode"]))


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
