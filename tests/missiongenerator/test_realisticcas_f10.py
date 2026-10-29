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


@pytest.mark.parametrize("include_armor", [False, True])
def test_campaign_scope_preserves_known_armor_threats_and_front_only_f10(
    include_armor: bool,
) -> None:
    s = scenario()
    # Campaign membership, not vehicle type or proximity, selects armor groups.
    s.base.units[0].type = "SA-18 Igla-S manpad"
    s.g.unit_map.theater_objects[s.base.units[0].name] = NS(
        theater_unit=NS(ground_object=NS(category="armor", name="ARMOR"))
    )
    blue_armor = s.m.vehicle_group(
        s.m.country("USA"), "BLUE ARMOR", Unarmed.Ural_375, Point(2000, 0, s.m.terrain)
    )
    other = s.m.vehicle_group(
        s.m.country("Russia"), "OTHER", Unarmed.Ural_375, Point(3000, 0, s.m.terrain)
    )
    s.g.unit_map.theater_objects[blue_armor.units[0].name] = NS(
        theater_unit=NS(ground_object=NS(category="armor", name="BLUE ARMOR"))
    )
    for name, value in (
        ("includeArmorGroups", include_armor),
        ("f10FrontlineContacts", True),
    ):
        next(
            o for o in s.plugin.options if o.identifier.endswith("." + name)
        ).set_value(value)
    config = prepare_campaign(s.g, [s.plugin])
    assert config is not None
    registry = config["registry"]
    concealed = {g["name"] for g in registry["groups"]}
    assert concealed == {"FRONT", "SUPPORT", "FRIEND"} | (
        {"BASE", "BLUE ARMOR"} if include_armor else set()
    )
    threat = next(
        t for t in registry["airDefenseThreats"] if t["name"] == s.base.units[0].name
    )
    assert threat["known"] is not include_armor
    assert ("initialPoint" in threat) is not include_armor
    assert {t["name"] for t in registry["afacKnownTargets"]} == (
        {other.units[0].name}
        if include_armor
        else {s.base.units[0].name, blue_armor.units[0].name, other.units[0].name}
    )
    assert {g["name"] for g in config["frontlineMapGroups"]} == {"FRONT", "SUPPORT"}
    assert not s.base.hidden


def test_missing_scope_defaults_to_front_only_and_rejects_invalid_values() -> None:
    s = scenario()
    option = next(
        o for o in s.plugin.options if o.identifier == "realisticcas.includeArmorGroups"
    )
    assert option.get_value is False
    # Missing saved keys follow the same default as a newly loaded manifest.
    s.plugin.options.remove(option)
    config = prepare_campaign(s.g, [s.plugin])
    assert config is not None
    assert "BASE" not in {g["name"] for g in config["registry"]["groups"]}
    s.plugin.options.append(option)
    option.set_value(1)
    with pytest.raises(ValueError, match="armor group discovery must be boolean"):
        prepare_campaign(s.g, [s.plugin])


@pytest.mark.parametrize("include_armor", [False, True])
def test_enabled_f10_is_serialized_and_its_scripts_compile(
    tmp_path: Path, include_armor: bool
) -> None:
    from zipfile import ZipFile
    from dcs.lua import loads
    from game.missiongenerator.luagenerator import LuaGenerator
    from game.missiongenerator.realisticcascampaign import inject_campaign

    s = scenario()
    s.g.unit_map.theater_objects[s.base.units[0].name] = NS(
        theater_unit=NS(ground_object=NS(category="armor", name="ARMOR"))
    )
    next(
        o for o in s.plugin.options if o.identifier == "realisticcas.includeArmorGroups"
    ).set_value(include_armor)
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
        # Inspect the startup payload actually written into the generated MIZ.
        lua.execute("RealisticCAS={startMission=function(c) captured=c;return {} end}")
        for trigger in mission["trigrules"].values():
            for action in trigger["actions"].values():
                source = action.get("text", "")
                if source.startswith(
                    "do local ok, instance, why = pcall(RealisticCAS.startMission"
                ):
                    lua.execute(source)
        exported = lua.globals().captured.registry
        assert ("BASE" in {g.name for g in exported.groups.values()}) is include_armor
        assert (
            "BASE" in {g.name for g in exported.knownGroundGroups.values()}
        ) is not include_armor


def test_support_infantry_and_manpads_are_tagged_without_jtac_or_inventory_maps() -> (
    None
):
    from game.missiongenerator.flotgenerator import FlotGenerator
    from game.theater.player import Player
    from game.utils import Heading

    mission = Mission()
    side = mission.country("USA")
    p = Point(0, 0, mission.terrain)
    u = MagicMock(dcs_unit_type=Unarmed.Ural_375, spawn_weight=1)
    faction: Any = NS(infantry_with_class=lambda _: [u])
    data = MissionData()
    generator: Any = NS(
        mission=mission,
        mission_data=data,
        conflict=NS(find_ground_position=lambda *args: p, theater=mission.terrain),
        game=NS(
            settings=NS(player_skill="High"),
            faction_for=lambda _: faction,
        ),
    )
    sequence = count()
    with patch("game.missiongenerator.flotgenerator.GroundForcePainter"), patch(
        "game.missiongenerator.flotgenerator.namegen.next_infantry_name",
        side_effect=lambda *args: f"SUPPORT{next(sequence)}",
    ):
        FlotGenerator._generate_support_soldier(
            generator,
            u,
            p,
            side,
            faction,
            Player.BLUE,
            Heading.from_degrees(0),
        )
    support = {g.name for g in side.vehicle_group}
    assert support and support == data.frontline_visibility_groups
