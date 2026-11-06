"""Bundled campaigns provide faction-compatible AFACs with stock fallbacks."""

from collections import defaultdict
from copy import deepcopy
from dataclasses import fields
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from game import persistency
from game.ato import FlightType
from game.campaignloader.campaign import Campaign
from game.campaignloader.defaultsquadronassigner import DefaultSquadronAssigner
from game.campaignloader.squadrondefgenerator import SquadronDefGenerator
from game.dcs.afaccapabilities import capabilities_for
from game.dcs.aircrafttype import AircraftType
from game.factions import FACTIONS
from game.settings import Settings
from game.theater.player import Player
from game.theater.start_generator import ModSettings
from game.utils import nautical_miles

ROOT = Path("resources/campaigns")
MANIFEST = json.loads(
    Path(__file__).with_name("afac_campaigns.json").read_text("utf-8")
)
AFAC = {FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE}
# The stock Wing Loong represents comparable reconnaissance UAVs in fictional
# modern scenarios. Keep this balance allowance out of historical Cold War sides.
UAV_PROXY_FACTIONS = {
    "Russia 1990",
    "Russia 2010",
    "Redfor (Russia) 2020",
    "Private Military Company - Russian (Hard)",
    "Redfor Current",
    "China 2010",
    "Redfor (China) 2020",
    "China/Argentina Falklands Occupation Force",
    "Iran 2015",
    "Syria 2011",
}
UAV_QUALITY = {
    "MQ-9 Reaper": 3,
    "TB-2 UCAV": 2,
    "WingLoong-I": 2,
    "RQ-1A Predator": 1,
}


def uav_available_in_period(type_id: str, start: date, faction: str) -> bool:
    if type_id == "MQ-9 Reaper":
        return start >= date(2007, 10, 1) and (
            not faction.startswith("Spain") or start.year >= 2020
        )
    if type_id == "RQ-1A Predator":
        return start.year >= 1995
    if type_id == "WingLoong-I":
        return start.year >= 2010 or (
            start.year >= 1995 and faction in UAV_PROXY_FACTIONS
        )
    if type_id == "TB-2 UCAV":
        return start.year >= 2014
    return False


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), False, 0)


def test_review_covers_every_bundled_campaign() -> None:
    assert set(MANIFEST) == {path.name for path in ROOT.glob("*.yaml")}


@pytest.mark.parametrize("filename", MANIFEST)
def test_both_sides_have_reviewed_afac_aircraft_with_and_without_mods(
    filename: str,
) -> None:
    row = MANIFEST[filename]
    campaign = Campaign.from_file(ROOT / filename)
    theater = campaign.load_theater(campaign.advanced_iads)
    wing = campaign.load_air_wing_config(theater)
    settings = Settings()
    settings.__dict__.update(Settings.deserialize_state_dict(campaign.settings))
    settings.plugins.update({"realisticcas": True, "realisticcas.afacEnabled": True})

    for mode in ("recommended", "stock", "all"):
        mods = ModSettings(
            **{
                field.name: mode == "all"
                or (
                    mode == "recommended"
                    and bool(campaign.settings.get(field.name, False))
                )
                for field in fields(ModSettings)
            }
        )
        for name, expected in row["sides"].items():
            side = Player[name]
            faction = deepcopy(FACTIONS[expected["faction"]])
            faction.apply_mod_settings(mods)
            base_key = expected["base"]
            base = (
                theater.find_control_point_by_airport_id(base_key)
                if isinstance(base_key, int)
                else theater.control_point_named(base_key)
            )
            assert base is not None and base.starting_coalition is side
            config = next(
                c
                for c in wing.by_location[base]
                if c.primary.is_afac and AFAC <= c.auto_assignable
            )
            assert config.max_size >= 2
            assert config.pilot_limit == config.max_size + 4
            game: Any = SimpleNamespace(settings=settings)
            air_wing = SimpleNamespace(
                squadron_defs=defaultdict(list),
                squadron_def_generator=SquadronDefGenerator(faction),
            )
            coalition: Any = SimpleNamespace(
                game=game, faction=faction, air_wing=air_wing
            )
            for cp in theater.controlpoints:
                if cp.starting_coalition is side:
                    cp._coalition = coalition
            definition = DefaultSquadronAssigner(
                wing, game, coalition
            ).find_squadron_for(config, base)
            assert definition is not None
            aircraft = definition.aircraft
            available = {a.variant_id for a in faction.all_aircrafts}
            expected_aircraft = next(
                candidate
                for candidate in expected["preferred"]
                if candidate in available
            )
            assert aircraft.variant_id == expected_aircraft
            assert aircraft in faction.all_aircrafts and base.can_operate(aircraft)
            if not aircraft.helicopter:
                airport = base.dcs_airport
                if airport is not None:
                    assert airport.runways
                    assert "heliport" not in airport.name.lower()
                    assert sum(slot.airplanes for slot in airport.parking_slots) >= 2
            assert all(aircraft.capable_of(task) for task in AFAC)
            assert capabilities_for(aircraft.dcs_id) is not None
            assert aircraft.variant_id != "Yak-52"
            if row["rotary"]:
                assert aircraft.helicopter
            start = campaign.recommended_start_date or date(2020, 1, 1)
            if aircraft.dcs_id in UAV_QUALITY:
                assert uav_available_in_period(aircraft.dcs_id, start, faction.name)
                nearest_target = min(
                    (
                        cp
                        for cp in theater.controlpoints
                        if cp.starting_coalition is not side and not cp.is_offmap
                    ),
                    key=base.distance_to,
                )
                assert (
                    base.distance_to(nearest_target)
                    <= max(
                        aircraft.max_mission_range,
                        nautical_miles(settings.max_mission_range_planes),
                    ).meters
                ), (filename, aircraft.variant_id, base.full_name)

            # Matching the manifest alone would preserve an inferior allocation.
            # Independently check every available UAV and starting operating base.
            viable_uavs = [
                candidate
                for candidate in faction.all_aircrafts
                if isinstance(candidate, AircraftType)
                and candidate.dcs_id in UAV_QUALITY
                and uav_available_in_period(candidate.dcs_id, start, faction.name)
                and all(candidate.capable_of(task) for task in AFAC)
                and any(
                    cp.starting_coalition is side and cp.can_operate(candidate)
                    for cp in theater.controlpoints
                )
            ]
            if viable_uavs and not row["rotary"]:
                profile = capabilities_for(aircraft.dcs_id)
                assert profile is not None and profile.remote_operator, (
                    filename,
                    faction.name,
                    mode,
                    aircraft.variant_id,
                    [a.variant_id for a in viable_uavs],
                )
                assert UAV_QUALITY[aircraft.dcs_id] == max(
                    UAV_QUALITY[candidate.dcs_id] for candidate in viable_uavs
                )


def test_georgia_multi_part_uses_the_same_2008_era() -> None:
    campaigns = [
        Campaign.from_file(ROOT / filename)
        for filename in (
            "Caucasus_Multi_Full.yaml",
            "Caucasus_Multi_Georgia.yaml",
            "Caucasus_Multi_Russia.yaml",
        )
    ]
    assert {c.recommended_start_date for c in campaigns} == {date(2008, 8, 1)}


def test_predator_is_not_delayed_until_reaper_service() -> None:
    assert uav_available_in_period("RQ-1A Predator", date(1997, 1, 1), "Bluefor Modern")
    assert not uav_available_in_period(
        "MQ-9 Reaper", date(1997, 1, 1), "Bluefor Modern"
    )


@pytest.mark.parametrize("faction", ["Russia 1975", "Russia 1980", "Germany 1944"])
def test_modern_uav_allowance_does_not_leak_into_historical_forces(
    faction: str,
) -> None:
    assert not uav_available_in_period("WingLoong-I", date(1988, 1, 1), faction)
