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


def test_audit_accounts_for_every_originally_unknown_type() -> None:
    assert len({row["dcs_id"] for row in REVIEWED}) == 107
    assert dict(Counter(row["mode"] for row in REVIEWED)) == {
        mode: count for mode, count in AUDIT["counts"].items() if mode != "reviewed"
    }
    assert all(row["reason"] for row in REVIEWED)
    assert all(row["sources"] for row in CLASSIFIED)


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
