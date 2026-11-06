"""Bundled campaigns provide faction-compatible AFACs with stock fallbacks."""

from collections import defaultdict
from copy import deepcopy
from dataclasses import fields
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
from game.factions import FACTIONS
from game.settings import Settings
from game.theater.player import Player
from game.theater.start_generator import ModSettings

ROOT = Path("resources/campaigns")
MANIFEST = json.loads(
    Path(__file__).with_name("afac_campaigns.json").read_text("utf-8")
)
AFAC = {FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE}


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

    for stock_only in (False, True):
        mods = ModSettings(
            **{
                field.name: not stock_only
                and bool(campaign.settings.get(field.name, False))
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
            base._coalition = coalition
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
            assert all(aircraft.capable_of(task) for task in AFAC)
            assert capabilities_for(aircraft.dcs_id) is not None
            assert aircraft.variant_id != "Yak-52"
            if row["rotary"]:
                assert aircraft.helicopter
            if campaign.recommended_start_date:
                year = campaign.recommended_start_date.year
                if year < 2007:
                    assert aircraft.dcs_id != "MQ-9 Reaper"
                if year < 2010:
                    assert aircraft.dcs_id != "WingLoong-I"
                if year < 2014:
                    assert aircraft.dcs_id != "TB-2 UCAV"
