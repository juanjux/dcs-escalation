"""AFAC aircraft use normal faction availability and squadron inventories."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from game import persistency
from game.ato import FlightType
from game.campaignloader.squadrondefgenerator import SquadronDefGenerator
from game.dcs.afaccapabilities import capabilities_for
from game.dcs.aircrafttype import AircraftType
from game.factions.faction import Faction
from game.settings import Settings
from game.squadrons.squadron import Squadron
from game.theater.start_generator import ModSettings

FACTIONS = Path("resources/factions")
DRONES = ("MQ-9 Reaper", "RQ-1A Predator", "WingLoong-I", "[CH] TB-2 UCAV")


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), False, 0)


def faction_from_file(filename: str) -> Faction:
    return Faction.from_dict(json.loads((FACTIONS / filename).read_text("utf-8")))


@pytest.mark.parametrize("path", sorted(FACTIONS.glob("*.json")), ids=lambda p: p.stem)
def test_every_faction_retains_afac_aircraft_without_mods(path: Path) -> None:
    faction = faction_from_file(path.name)
    assert any(capabilities_for(a.dcs_id) for a in faction.aircraft)
    faction.apply_mod_settings(ModSettings())
    assert any(capabilities_for(a.dcs_id) for a in faction.aircraft)
    restored = Faction.from_dict(faction.to_dict())
    assert restored.aircraft == faction.aircraft


@pytest.mark.parametrize(
    "filename,required",
    [
        ("usa_2020.json", ("MQ-9 Reaper", "RQ-1A Predator")),
        ("usn_1985.json", ("OH-58D(R) Kiowa Warrior",)),
        ("usn_2005.json", ("OH-58D(R) Kiowa Warrior",)),
        ("usn_2009.json", ("OH-58D(R) Kiowa Warrior",)),
        ("Morocco 2000 onwards.json", ("RQ-1A Predator",)),
        ("Morocco 2030.json", ("MQ-9 Reaper", "RQ-1A Predator")),
        ("israel_2000.json", ("RQ-1A Predator",)),
        ("israel_2011_ODS.json", ("MQ-9 Reaper", "RQ-1A Predator")),
        ("israel_2012.json", ("MQ-9 Reaper", "RQ-1A Predator")),
        ("israel_2017.json", ("MQ-9 Reaper", "RQ-1A Predator")),
        ("turkey_2005.json", ("[CH] TB-2 UCAV",)),
        ("russia_2010.json", ("WingLoong-I",)),
        ("russia_2020.json", ("WingLoong-I",)),
        ("CH_russia_2020.json", ("WingLoong-I",)),
        ("redfor_russia_2010.json", ("WingLoong-I",)),
        ("redfor_russia_2020.json", ("WingLoong-I",)),
        ("iran_2015.json", ("WingLoong-I",)),
        ("CH_iran_2020.json", ("WingLoong-I",)),
        ("libya_2011.json", ("WingLoong-I",)),
        ("syria_2011.json", ("WingLoong-I",)),
        ("syria_2012.json", ("WingLoong-I",)),
        ("pmc_russian.json", ("WingLoong-I",)),
        ("pmc_russian_hard.json", ("WingLoong-I",)),
        ("insurgents.json", ("WingLoong-I",)),
        ("insurgents_hard.json", ("WingLoong-I",)),
    ],
)
def test_reviewed_allocations(filename: str, required: tuple[str, ...]) -> None:
    available = {a.variant_id for a in faction_from_file(filename).aircraft}
    assert set(required) <= available


@pytest.mark.parametrize(
    "filename",
    [
        "allies_1940.json",
        "allies_1944.json",
        "allies_1944_free.json",
        "germany_1940.json",
        "germany_1942.json",
        "germany_1944.json",
        "germany_1944_free.json",
        "soviet_union_1943.json",
        "japan_1944.json",
        "uk_1944.json",
        "usa_1944.json",
        "usa_1945.json",
        "israel_1948.json",
        "syria_1948.json",
        "dprk_1950_fictional.json",
    ],
)
def test_early_factions_use_the_visual_yak_fallback(filename: str) -> None:
    aircraft = faction_from_file(filename).aircraft
    assert any(a.variant_id == "Yak-52" for a in aircraft)
    assert not any(a.helicopter for a in aircraft)
    assert not any(a.variant_id in DRONES for a in aircraft)


@pytest.mark.parametrize("variant", DRONES)
def test_drones_have_normal_rosters_and_aircraft_orders(variant: str) -> None:
    aircraft = AircraftType.named(variant)
    faction = faction_from_file("usa_2020.json")
    definition = SquadronDefGenerator(faction).generate_for_aircraft(aircraft)
    settings = Settings()
    settings.squadron_pilot_limit = 2
    game: Any = MagicMock(settings=settings)
    coalition: Any = MagicMock(game=game, faction=faction)
    base: Any = MagicMock()
    base.unclaimed_parking.return_value = 10
    squadron = Squadron.create_from(
        definition, FlightType.CAS, 2, base, coalition, game
    )
    squadron.populate_for_turn_0(True)
    squadron.return_all_pilots_and_aircraft()
    assert squadron.owned_aircraft == squadron.untasked_aircraft == 2
    assert squadron.number_of_available_pilots == 2
    pilot = squadron.claim_available_pilot()
    assert pilot is not None
    squadron.return_pilot(pilot)
    squadron.pending_deliveries = -1
    squadron.deliver_orders()
    assert squadron.owned_aircraft == 1
    squadron.pending_deliveries = 1
    squadron.deliver_orders()
    assert squadron.owned_aircraft == 2
    assert len(squadron.current_roster) == 2
    assert pilot in squadron.current_roster


def test_mod_aircraft_still_obey_mod_settings() -> None:
    faction = faction_from_file("turkey_2005.json")
    assert AircraftType.named("[CH] TB-2 UCAV") in faction.aircraft
    faction.apply_mod_settings(ModSettings())
    assert AircraftType.named("[CH] TB-2 UCAV") not in faction.aircraft


def test_standard_reaper_has_not_become_carrier_capable() -> None:
    aircraft = AircraftType.named("MQ-9 Reaper")
    assert not aircraft.carrier_capable
    assert not aircraft.lha_capable
