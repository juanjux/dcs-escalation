"""The optional F10 projection conceals only explicitly tagged enemy front groups."""

from datetime import timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock, patch
from itertools import count

import pytest
from dcs import Mission
from dcs.mapping import Point
from dcs.vehicles import Unarmed

from game.missiongenerator.missiondata import MissionData
from game.missiongenerator.realisticcascampaign import prepare_campaign
from game.missiongenerator.realisticcasf10 import collect_frontline_map_groups
from game.plugins.luaplugin import LuaPlugin


def scenario() -> Any:
    mission = Mission()
    red, blue = mission.country("Russia"), mission.country("USA")
    point = Point(0, 0, mission.terrain)
    front = mission.vehicle_group(red, "FRONT", Unarmed.Ural_375, point)
    support = mission.vehicle_group(red, "SUPPORT", Unarmed.Ural_375, point)
    base = mission.vehicle_group(red, "BASE", Unarmed.Ural_375, point)
    friend = mission.vehicle_group(blue, "FRIEND", Unarmed.Ural_375, point)
    data = MissionData()
    data.frontline_visibility_groups = {front.name, support.name, friend.name}
    generator = NS(
        mission=mission,
        mission_data=data,
        unit_map=NS(theater_objects={}),
        game=NS(
            theater=NS(
                timezone=timezone(timedelta(hours=4)),
                reference_position=NS(lat=41.9, lng=41.86),
            )
        ),
    )
    plugin = LuaPlugin.from_json(
        "realisticcas", Path("resources/plugins/realisticcas/plugin.json")
    )
    assert plugin is not None
    plugin.set_value(True)
    return NS(
        m=mission,
        data=data,
        g=generator,
        plugin=plugin,
        front=front,
        support=support,
        base=base,
        friend=friend,
    )


def test_map_option_default_off_and_frontline_only_projection() -> None:
    s = scenario()
    config = prepare_campaign(s.g, [s.plugin])
    assert config is not None and config["f10FrontlineContacts"] is False
    assert not any(g.hidden for g in (s.front, s.support, s.base, s.friend))
    assert s.m.forced_options.user_marks is None
    option = next(
        o
        for o in s.plugin.options
        if o.identifier == "realisticcas.f10FrontlineContacts"
    )
    option.set_value(True)
    map_view = s.m.forced_options.options_view
    config = prepare_campaign(s.g, [s.plugin])
    assert config is not None
    assert {g["name"] for g in config["frontlineMapGroups"]} == {"FRONT", "SUPPORT"}
    assert (
        s.front.hidden
        and s.support.hidden
        and not s.base.hidden
        and not s.friend.hidden
    )
    assert getattr(s.m.forced_options, "user_marks") is True
    assert s.m.forced_options.options_view == map_view


def test_visibility_owned_and_unregistered_groups_stay_outside_f10_scope() -> None:
    s = scenario()
    registry: dict[str, Any] = {
        "groups": [{"name": "SUPPORT"}, {"name": "BASE"}, {"name": "FRIEND"}]
    }
    groups = collect_frontline_map_groups(s.m, s.data, registry)
    assert [g["name"] for g in groups] == ["SUPPORT"]
    assert all(not g.hidden for g in (s.front, s.support, s.base, s.friend))


def test_enabled_f10_is_serialized_and_its_scripts_compile(tmp_path: Path) -> None:
    from zipfile import ZipFile
    from dcs.lua import loads
    from game.missiongenerator.luagenerator import LuaGenerator
    from game.missiongenerator.realisticcascampaign import inject_campaign

    s = scenario()
    next(
        o
        for o in s.plugin.options
        if o.identifier == "realisticcas.f10FrontlineContacts"
    ).set_value(True)
    generator = LuaGenerator(s.g.game, s.m, s.data, s.g.unit_map)
    config = prepare_campaign(generator, [s.plugin])
    inject_campaign(generator, config)
    output = tmp_path / "f10.miz"
    s.m.save(output)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        mission = loads(archive.read("mission").decode())["mission"]
        assert mission["forcedOptions"]["userMarks"] is True
        groups = {
            g["name"]: g["hidden"]
            for c in mission["coalition"]["red"]["country"].values()
            for g in c.get("vehicle", {}).get("group", {}).values()
        }
        assert groups == {"FRONT": True, "SUPPORT": True, "BASE": False}
        assert any(name.endswith("f10-contacts.lua") for name in archive.namelist())
        for name in archive.namelist():
            if name == "mission" or name.endswith(".lua"):
                lua.compile(archive.read(name).decode())
        lua.execute(archive.read("mission").decode())
        for _, action in lua.globals().mission.trig.actions.items():
            lua.compile(action)


@pytest.mark.parametrize("infantry", [False, True])
def test_support_infantry_and_manpads_are_tagged_without_jtac_or_inventory_maps(
    infantry: bool,
) -> None:
    from game.missiongenerator.flotgenerator import FlotGenerator
    from game.theater.player import Player
    from game.utils import Heading

    mission = Mission()
    side = mission.country("USA")
    p = Point(0, 0, mission.terrain)
    parent = mission.vehicle_group(side, "PARENT", Unarmed.Ural_375, p)
    u = MagicMock(dcs_unit_type=Unarmed.Ural_375, spawn_weight=1)
    faction = NS(infantry_with_class=lambda _: [u])
    data = MissionData()
    generator: Any = NS(
        mission=mission,
        mission_data=data,
        conflict=NS(find_ground_position=lambda *args: p, theater=mission.terrain),
        game=NS(
            settings=NS(perf_infantry=infantry, manpads=True),
            faction_for=lambda _: faction,
        ),
    )
    sequence = count()
    with patch("game.missiongenerator.flotgenerator.GroundForcePainter"), patch(
        "game.missiongenerator.flotgenerator.namegen.next_infantry_name",
        side_effect=lambda *args: f"SUPPORT{next(sequence)}",
    ), patch("game.missiongenerator.flotgenerator.random.choice", return_value=True):
        FlotGenerator.gen_infantry_group_for_group(
            generator, parent, Player.BLUE, side, Heading.from_degrees(0)
        )
    support = {g.name for g in side.vehicle_group if g is not parent}
    assert support and support == data.frontline_visibility_groups
