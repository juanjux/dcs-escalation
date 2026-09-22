"""A save names its ground units by display name, so a retired name has to migrate.

`GroundUnitType.__setstate__` resolves by `variant_id`, which is the name on screen.
A unit dropped from a mod without an entry here raises KeyError on load, and the game
reports an incompatible save.
"""

from __future__ import annotations

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
        ("[CH] T-64BV MBT", "CHAP_T64BV"),
        ("[CH] T-84 Oplot-M MBT", "CHAP_T84OplotM"),
    ],
)
def test_the_ukraine_pack_units_dcs_took_over(old: str, dcs_id: str) -> None:
    """Ukraine pack 2.0.0 dropped both as duplicates of the units ED shipped."""
    from game.dcs.groundunittype import GroundUnitType

    assert GroundUnitType.named(old).dcs_unit_type.id == dcs_id


def test_the_unpickler_maps_the_retired_classes() -> None:
    from game.persistency import MigrationUnpickler

    unpickler = MigrationUnpickler.__new__(MigrationUnpickler)
    module = "pydcs_extensions.ukrainemilitaryassetspack.ukrainemilitaryassetspack"
    assert unpickler._handle_ch_ukraine_assets(module, "CH_T64BV").id == "CHAP_T64BV"
    got = unpickler._handle_ch_ukraine_assets(module, "T84_OplotM")
    assert got.id == "CHAP_T84OplotM"
    assert unpickler._handle_ch_ukraine_assets(module, "BTR_4") is None
