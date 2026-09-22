"""A save names its ground units by display name, so a retired name has to migrate.

`GroundUnitType.__setstate__` resolves by `variant_id`, which is the name on screen.
A unit dropped from a mod without an entry here raises KeyError on load, and the game
reports an incompatible save.
"""

from __future__ import annotations

from typing import Any

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


def test_the_unpickler_maps_the_retired_classes(tmp_path: Any) -> None:
    from game.persistency import MigrationUnpickler

    unpickler = MigrationUnpickler.__new__(MigrationUnpickler)
    module = "pydcs_extensions.ukmilitaryassetspack.ukmilitaryassetspack"
    assert unpickler._handle_ch_uk_assets(module, "CH_Scimitar").id == "CHAP_FV107"
    assert unpickler._handle_ch_uk_assets(module, "CH_Scorpion").id == "CHAP_FV101"
    assert unpickler._handle_ch_uk_assets(module, "CH_Ajax") is None
