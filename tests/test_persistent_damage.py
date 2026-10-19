"""Damage survives debriefing, turn repair, saves and mission generation."""

import pickle
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs import Mission
from dcs.mapping import Point
from dcs.ships import USS_Arleigh_Burke_IIa
from dcs.terrain import Caucasus
from dcs.unittype import StaticType
from dcs.vehicles import Armor

from game.debriefing import StateData
from game.health import HealthStatus
from game.missiongenerator.luagenerator import LuaGenerator
from game.persistentdamage import (
    commit_damage,
    health_report,
    parse_health,
    repair_damage,
    repaired_health,
)
from game.point_with_heading import PointWithHeading
from game.settings import Settings
from game.sim import GameUpdateEvents
from game.theater import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    SamGroundObject,
    ShipGroundObject,
    VehicleGroupGroundObject,
)
from game.theater.theatergroup import SceneryUnit, TheaterGroup, TheaterUnit
from game.unitmap import UnitMap
from game.utils import Heading


class Building(StaticType):
    id = "Test building"
    name = "Test building"


def _ignore(*args: Any) -> None:
    pass


@pytest.fixture
def campaign() -> Any:
    terrain = Caucasus()
    position = Point(0, 0, terrain)
    settings = Settings()
    game = SimpleNamespace(settings=settings)
    cp: Any = SimpleNamespace(
        name="Base", captured=Player.BLUE, coalition=SimpleNamespace(game=game)
    )
    location = PresetLocation("Site", position, Heading(0))
    sites = [
        ShipGroundObject("Ship", location, cp),
        BuildingGroundObject("Building", "factory", location, cp, task=None),
        SamGroundObject("SAM", location, cp, task=None),
        VehicleGroupGroundObject("Armor", location, cp, task=None),
    ]
    types = [USS_Arleigh_Burke_IIa, Building, Armor.M_1_Abrams, Armor.M_1_Abrams]
    units = []
    for i, (site, unit_type) in enumerate(zip(sites, types)):
        unit = TheaterUnit(
            i + 1,
            site.name,
            unit_type,
            PointWithHeading.from_point(position, Heading(0)),
            site,
        )
        site.groups = [TheaterGroup(i + 1, site.name, unit.position, [unit], site)]
        units.append(unit)
    game.theater = SimpleNamespace(
        ground_objects=sites,
        terrain=terrain,
        iads_network=SimpleNamespace(update_tgo=_ignore),
    )
    cp.ground_objects = sites
    um = UnitMap()
    for unit in units:
        um.add_theater_unit_mapping(
            unit, cast(Any, SimpleNamespace(name=unit.unit_name))
        )
    return SimpleNamespace(
        game=game, units=units, sites=sites, um=um, events=GameUpdateEvents()
    )


def test_damage_debrief_repairs_and_survives_save_reload(campaign: Any) -> None:
    ship, building, sam, armor = campaign.units
    state = StateData.from_json(
        {"persistent_health": {unit.unit_name: 0.5 for unit in campaign.units}},
        campaign.um,
    )
    debrief: Any = SimpleNamespace(state_data=state, unit_map=campaign.um)
    commit_damage(campaign.game, debrief, campaign.events)
    assert [unit.health_fraction for unit in campaign.units] == [0.5, 0.5, 1, 1]
    repair_damage(campaign.game, campaign.events)
    assert [unit.health_fraction for unit in campaign.units] == [0.65, 0.65, 1, 1]
    restored = pickle.loads(pickle.dumps(ship))
    assert restored.health_fraction == 0.65
    assert campaign.sites[0] in campaign.events.updated_tgos


@pytest.mark.parametrize("percent,expected", [(0, 0.5), (30, 0.65), (100, 1)])
def test_repair_percent_and_full_recovery(
    campaign: Any, percent: int, expected: float
) -> None:
    campaign.game.settings.persistent_damage_repair_percent = percent
    ship = campaign.units[0]
    ship.health = 0.5
    repair_damage(campaign.game, campaign.events)
    assert ship.health_fraction == expected
    assert repaired_health(0, percent) == 0
    assert repaired_health(0.999, 0) == 0.999
    assert repaired_health(0.994, 30) == 1


def test_dead_units_stay_dead_and_explicit_revival_restores_health(
    campaign: Any,
) -> None:
    unit = campaign.units[1]
    unit.health = 0.2
    unit.kill(campaign.events)
    repair_damage(campaign.game, campaign.events)
    assert unit.health_fraction == 0
    unit.revive(campaign.events)
    assert unit.health_fraction == 1


def test_disabling_restores_survivors_and_legacy_units_start_full(
    campaign: Any,
) -> None:
    unit = campaign.units[0]
    del unit.health
    assert unit.health_fraction == 1
    unit.health = 0.3
    campaign.game.settings.persistent_damage_enabled = False
    repair_damage(campaign.game, campaign.events)
    assert unit.health_fraction == 1


def test_scenery_health_is_resolved_by_objective_not_index(campaign: Any) -> None:
    unit = campaign.units[1]
    scenery = SceneryUnit(
        unit.id, unit.name, Building, unit.position, unit.ground_object
    )
    campaign.um.scenery_objects["Zone"] = SimpleNamespace(ground_unit=scenery)
    debrief: Any = SimpleNamespace(
        state_data=SimpleNamespace(persistent_health={"Zone": 0.3, "untracked": 0.1}),
        unit_map=campaign.um,
    )
    commit_damage(campaign.game, debrief, campaign.events)
    assert scenery.health_fraction == 0.3


def test_snapshot_zero_is_a_loss_and_missing_snapshot_keeps_old_damage(
    campaign: Any,
) -> None:
    unit = campaign.units[0]
    unit.health = 0.7
    empty: Any = SimpleNamespace(
        state_data=StateData.from_json({}, campaign.um), unit_map=campaign.um
    )
    commit_damage(campaign.game, empty, campaign.events)
    assert unit.health_fraction == 0.7
    empty.state_data.persistent_health[unit.unit_name] = 0
    commit_damage(campaign.game, empty, campaign.events)
    assert not unit.alive


def test_api_reports_remaining_health_and_next_turn_gain(campaign: Any) -> None:
    unit = campaign.units[0]
    unit.health = 0.5
    report = HealthStatus(**health_report([unit], campaign.game.settings))
    assert report.health_percent == 50
    assert report.damage_repaired_per_turn_percent == 30
    assert report.repair_next_turn_percent == 15
    assert report.health_next_turn_percent == 65
    assert report.units[0].health_percent == 50
    assert report.units[0].persistent


def test_the_real_turn_boundary_repairs_even_a_skipped_turn(campaign: Any) -> None:
    from game.game import Game

    game = campaign.game
    game.turn = 0
    game.message = _ignore
    game.blue = game.red = SimpleNamespace(end_turn=_ignore)
    game.theater.controlpoints = []
    game.high_command = game.opfor_high_command = SimpleNamespace(
        return_loans=lambda _: [], end_effects=lambda _: []
    )
    campaign.units[0].health = 0.5
    Game.finish_turn(game, campaign.events, skipped=True)
    assert game.turn == 1
    assert campaign.units[0].health_fraction == 0.65


def test_map_and_planner_api_expose_the_same_health(
    campaign: Any, monkeypatch: Any
) -> None:
    from game.agent.views import _build_target
    from game.server.tgos.models import TgoJs

    monkeypatch.setattr(TgoJs, "_jamming_range_of", lambda _: None)
    monkeypatch.setattr("game.agent.views._iads_status", lambda *args: None)

    campaign.units[1].health = 0.5
    site = campaign.sites[1]
    mapped = TgoJs.for_tgo(site)
    planned = _build_target(campaign.game, site, "building", "STRIKE")
    assert mapped.health == planned.health
    assert mapped.health is not None
    assert mapped.health.health_percent == 50
    assert mapped.health.health_next_turn_percent == 65


def test_invalid_health_is_ignored() -> None:
    assert parse_health([]) == {}
    assert parse_health(
        {
            "nan": float("nan"),
            "inf": float("inf"),
            "bool": True,
            "text": "0.5",
            "negative": -0.1,
            "large": 2,
            "ok": 0.4,
        }
    ) == {"ok": 0.4}


def test_generation_embeds_health_and_only_tracks_eligible_units(
    campaign: Any, tmp_path: Any
) -> None:
    from zipfile import ZipFile

    campaign.units[0].health = 0.65
    generator = LuaGenerator(
        campaign.game, Mission(), cast(Any, SimpleNamespace()), campaign.um
    )
    generator._seed_persistent_damage()
    output = tmp_path / "persistent-damage.miz"
    generator.mission.save(str(output))
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(output) as archive:
        lua.execute(archive.read("mission").decode())
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode())
        assert any(
            name.endswith("persistent_damage.lua") for name in archive.namelist()
        )
    lua.execute(
        "function getValueDictByKey(key) return dictionary[key] or key end; function getValueResourceByKey(key) return key end; function a_do_script(code) assert(loadstring(code))() end; function a_do_script_file() end"
    )
    lua.execute(lua.globals().mission.trig.actions[1])
    rows = list(lua.globals().ESCALATION_PERSISTENT_DAMAGE.values())
    assert {row.name for row in rows} == {
        campaign.units[0].unit_name,
        campaign.units[1].unit_name,
    }
    assert rows[0].health == 0.65
    campaign.game.settings.persistent_damage_enabled = False
    other = LuaGenerator(
        campaign.game, Mission(), cast(Any, SimpleNamespace()), campaign.um
    )
    other._seed_persistent_damage()
    assert other.mission.triggerrules.triggers == []
