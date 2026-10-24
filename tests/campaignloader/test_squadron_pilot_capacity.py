"""Campaign squadron templates size pilots independently of saved squadrons."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from game.campaignloader.campaignairwingconfig import SquadronConfig
from game.squadrons.squadron import Squadron


@pytest.mark.parametrize("size", [0, 2, 4, 12, 16, 24])
def test_explicit_capacity_defaults_to_four_spare_pilots(size: int) -> None:
    config = SquadronConfig.from_data({"primary": "CAS", "size": size})
    assert config.pilot_limit == size + 4


def test_unspecified_capacity_keeps_global_pilot_policy() -> None:
    assert SquadronConfig.from_data({"primary": "CAS"}).pilot_limit is None


def test_custom_campaign_may_explicitly_override_pilot_capacity() -> None:
    config = SquadronConfig.from_data({"primary": "CAS", "size": 4, "pilots": 12})
    assert config.pilot_limit == 12


@pytest.mark.parametrize("start_full", [False, True])
def test_initial_roster_uses_squadron_capacity_not_global_limit(
    start_full: bool,
) -> None:
    counts: list[int] = []
    squadron: Any = SimpleNamespace(
        pilot_pool=[],
        pilot_limit=20,
        settings=SimpleNamespace(squadron_pilot_limit=50),
        _recruit_pilots=counts.append,
        max_size=16,
        owned_aircraft=0,
        aircraft=SimpleNamespace(
            helicopter=False,
            lha_capable=False,
            flyable=True,
            dcs_unit_type=SimpleNamespace(id="FA-18C_hornet"),
        ),
        location=SimpleNamespace(unclaimed_parking=lambda _: 16),
        coalition=SimpleNamespace(
            game=SimpleNamespace(settings=SimpleNamespace(ground_start_ai_planes=False))
        ),
    )
    Squadron.populate_for_turn_0(squadron, start_full)
    assert counts == [20]
    assert squadron.initial_aircraft == (16 if start_full else 0)


def test_old_squadron_migration_keeps_its_global_policy() -> None:
    squadron = Squadron.__new__(Squadron)
    squadron.__setstate__(
        {
            "owned_aircraft": 4,
            "max_size": 16,
            "settings": SimpleNamespace(squadron_pilot_limit=30),
        }
    )
    assert squadron.pilot_limit_override is None
    assert squadron.pilot_limit == 30


@pytest.mark.parametrize(
    "path", sorted(Path("resources/campaigns").glob("*.yaml")), ids=lambda p: p.stem
)
def test_bundled_templates_declare_capacity_plus_four(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for squadrons in data.get("squadrons", {}).values():
        for squadron in squadrons:
            if "size" in squadron:
                assert squadron["pilots"] == squadron["size"] + 4
