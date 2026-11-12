import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from dcs.payloads import PayloadDirectories
from dcs.unittype import FlyingType

from game import persistency
from game.ato import FlightType
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon
from game.dcs.aircrafttype import AircraftType
from game.factions.faction import Faction
from game.settings import Settings
from game.squadrons import Squadron
from game.squadrons.squadrondef import SquadronDef
from game.squadrons.squadrondefloader import SquadronDefLoader

PRESETS = Path("resources/squadrons")


@pytest.fixture(autouse=True)
def setup(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16885)


def test_stock_presets_load_with_distinct_liveries() -> None:
    presets = dict(SquadronDefLoader.load_squadrons_from(PRESETS))
    assert presets.keys() == set(PRESETS.glob("*/*.yaml"))
    for path, preset in presets.items():
        assert len({name.casefold() for name in preset.livery_set}) == len(
            preset.livery_set
        ), path


def test_preset_with_only_a_livery_set_uses_it_for_new_squadrons() -> None:
    preset = SquadronDef.from_yaml(
        PRESETS / "Mirage-F1CR/Escadron de Reconnaissance 2-33 Savoie.yaml"
    )
    game: Any = MagicMock(settings=Settings())
    squadron = Squadron.create_from(
        preset, FlightType.BAI, 4, MagicMock(), MagicMock(game=game), game
    )

    assert preset.livery is None
    assert squadron.use_livery_set
    assert squadron.livery_set == preset.livery_set
    assert squadron.livery_set is not preset.livery_set


def test_mirage_f1cr_is_usable_in_french_factions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aircraft = AircraftType.named("Mirage-F1CR")
    assert not aircraft.dcs_unit_type.flyable
    for year in (1985, 1995, 2005):
        data = Path(f"resources/factions/france_{year}.json").read_text(
            encoding="utf-8"
        )
        assert aircraft in Faction.from_dict(json.loads(data)).aircraft

    payloads = Path("resources/customized_payloads")
    monkeypatch.setattr(
        PayloadDirectories, "payload_dirs", classmethod(lambda cls: iter([payloads]))
    )
    monkeypatch.setattr(FlyingType, "_payload_cache", None)
    monkeypatch.setattr(aircraft.dcs_unit_type, "payloads", None)
    for task in aircraft.iter_task_capabilities():
        loadout = Loadout.default_for_task_and_aircraft(task, aircraft.dcs_unit_type)
        assert loadout.pylons
        for number, weapon in loadout.pylons.items():
            assert weapon is not None and Pylon.for_aircraft(
                aircraft, number
            ).can_equip(weapon)
