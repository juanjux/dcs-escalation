"""A save names its ground units by display name, so a retired name has to migrate.

`GroundUnitType.__setstate__` resolves by `variant_id`, which is the name on screen.
A unit dropped from a mod without an entry here raises KeyError on load, and the game
reports an incompatible save.
"""

from __future__ import annotations

import io
import pickle
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest


@pytest.fixture(autouse=True)
def _init_persistency(tmp_path_factory: pytest.TempPathFactory) -> None:
    from game import persistency

    persistency.setup(str(tmp_path_factory.mktemp("saved_games")), False, 16897)


def _migrations() -> list[tuple[str, str]]:
    from game.dcs.groundunittype import GroundUnitType

    return sorted(GroundUnitType._migrator().items())


def test_there_are_migrations_to_check() -> None:
    assert _migrations()


def test_every_retired_name_resolves() -> None:
    from game.dcs.groundunittype import GroundUnitType

    for old, new in _migrations():
        assert GroundUnitType.named(old).variant_id == new, old


@pytest.mark.parametrize(
    "old,dcs_id",
    [
        ("[CH] Scimitar CRV", "CHAP_FV107"),
        ("[CH] Scorpion LT", "CHAP_FV101"),
    ],
)
def test_the_uk_pack_units_dcs_took_over(old: str, dcs_id: str) -> None:
    """UK pack 1.5.0 dropped both as redundant with the units ED shipped."""
    from game.dcs.groundunittype import GroundUnitType

    assert GroundUnitType.named(old).dcs_unit_type.id == dcs_id


@pytest.mark.parametrize(
    "old,dcs_id",
    [
        ("[CH] T-64BV MBT", "CHAP_T64BV"),
        ("[CH] T-84 Oplot-M MBT", "CHAP_T84OplotM"),
    ],
)
def test_the_ukraine_pack_units_dcs_took_over(old: str, dcs_id: str) -> None:
    """Ukraine pack 2.0.0 dropped both as duplicates of the units ED shipped."""
    from game.dcs.groundunittype import GroundUnitType

    assert GroundUnitType.named(old).dcs_unit_type.id == dcs_id


def test_the_unpickler_maps_the_retired_uk_classes() -> None:
    from game.persistency import MigrationUnpickler

    unpickler = MigrationUnpickler.__new__(MigrationUnpickler)
    module = "pydcs_extensions.ukmilitaryassetspack.ukmilitaryassetspack"
    assert unpickler._handle_ch_uk_assets(module, "CH_Scimitar").id == "CHAP_FV107"
    assert unpickler._handle_ch_uk_assets(module, "CH_Scorpion").id == "CHAP_FV101"
    assert unpickler._handle_ch_uk_assets(module, "CH_Ajax") is None


def test_the_unpickler_maps_the_retired_ukraine_classes() -> None:
    from game.persistency import MigrationUnpickler

    unpickler = MigrationUnpickler.__new__(MigrationUnpickler)
    module = "pydcs_extensions.ukrainemilitaryassetspack.ukrainemilitaryassetspack"
    assert unpickler._handle_ch_ukraine_assets(module, "CH_T64BV").id == "CHAP_T64BV"
    got = unpickler._handle_ch_ukraine_assets(module, "T84_OplotM")
    assert got.id == "CHAP_T84OplotM"
    assert unpickler._handle_ch_ukraine_assets(module, "BTR_4") is None


@pytest.mark.parametrize(
    "old,class_name,dcs_id",
    [
        ("AAA SON-9 Fire Can", "AAA_SON_9_Fire_Can", "SON_9"),
        (
            "SAM SA-10 (5V55RUD) S-300PS LN 5P85CE",
            "SAM_SA_10__5V55RUD__S_300PS_LN_5P85CE",
            "S-300PS 5P85C ln",
        ),
    ],
)
def test_retired_highdigitsams_pickle_preserves_unit_state(
    old: str, class_name: str, dcs_id: str
) -> None:
    from dcs.terrain import Caucasus
    from dcs.vehicles import vehicle_map

    from game.dcs.groundunittype import GroundUnitType
    from game.persistency import MigrationUnpickler
    from game.point_with_heading import PointWithHeading
    from game.theater.theatergroup import TheaterGroup, TheaterUnit
    from game.utils import Heading
    from pydcs_extensions.highdigitsams import highdigitsams

    legacy_class = getattr(highdigitsams, class_name)
    assert legacy_class.id not in vehicle_map
    current = GroundUnitType.named(old)
    assert current.dcs_id == dcs_id
    legacy_descriptor = replace(
        current,
        dcs_unit_type=legacy_class,
        variant_id=old,
        display_name=old,
    )
    position = PointWithHeading(123.0, 456.0, Heading.from_degrees(37), Caucasus())
    go = SimpleNamespace(groups=[])
    units = [
        TheaterUnit(
            id=101 + index,
            name=f"Original unit {index}",
            type=legacy_class,
            position=position,
            ground_object=cast(Any, go),
            fixed_pos=True,
            fixed_hdg=True,
            alive=alive,
            repair_turns_remaining=2,
            health=0.37,
            transported_by_id=42,
            ground_unit_variant=old,
            repair_cost_paid=3.5,
        )
        for index, alive in enumerate((True, False))
    ]
    group = TheaterGroup(51, "Original group", position, units, cast(Any, go))
    go.groups.append(group)
    saved = SimpleNamespace(group=group, descriptor=legacy_descriptor)

    restored = MigrationUnpickler(io.BytesIO(pickle.dumps(saved))).load()

    assert restored.descriptor.dcs_unit_type is vehicle_map[dcs_id]
    assert restored.descriptor.variant_id == current.variant_id
    assert restored.group.id == group.id
    assert restored.group.name == group.name
    assert len(restored.group.units) == len(units)
    assert restored.group.ground_object.groups == [restored.group]
    for original, unit in zip(units, restored.group.units):
        assert unit.type is vehicle_map[dcs_id]
        assert unit.unit_type.dcs_id == dcs_id
        assert unit.id == original.id
        assert unit.name == original.name
        assert unit.alive is original.alive
        assert unit.health == original.health
        assert unit.repair_turns_remaining == original.repair_turns_remaining
        assert unit.repair_cost_paid == original.repair_cost_paid
        assert unit.transported_by_id == original.transported_by_id
        assert unit.ground_unit_variant == original.ground_unit_variant
        assert unit.fixed_pos is original.fixed_pos
        assert unit.fixed_hdg is original.fixed_hdg
        assert unit.position.x == original.position.x
        assert unit.position.y == original.position.y
        assert unit.position.heading == original.position.heading
        assert unit.ground_object is restored.group.ground_object


def test_retired_highdigitsams_handler_is_exact() -> None:
    from game.persistency import MigrationUnpickler

    unpickler = MigrationUnpickler.__new__(MigrationUnpickler)
    handler = unpickler._handle_retired_highdigitsams
    assert handler("other.module", "AAA_SON_9_Fire_Can") is None
    assert (
        handler(
            "pydcs_extensions.highdigitsams.highdigitsams",
            "SAM_SA_20_S_300PMU1_LN_5P85CE",
        )
        is None
    )
