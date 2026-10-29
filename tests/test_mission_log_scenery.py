"""Scenery news follows campaign ownership, not the native object's missing side."""

from pathlib import Path
from typing import Any

import pytest

from game.theater.player import Player
from tests.missiongenerator.test_scenery_zone_bridge import scenery_preamble
from tests.test_mission_log_pilot_names import mission_log


def scenery_log(owner: Player | None) -> Any:
    lua = mission_log(False)
    lua.execute("""
        logger=mist.Logger:new('SceneryTest','info')
        dead_events={};kill_details={}
        dcsRetribution={plugins={missionlog={maxmessages=60}}}
        function scenery(id)
            return {
                getName=function()return id end,
                getTypeName=function()return 'WAREHOUSE' end,
                getCoalition=function()error('Scenery has no coalition')end,
                getDesc=function()return {category=5}end,
                getPoint=function()return {x=100,y=0,z=200}end,
                getPlayerName=function()return nil end,
            }
        end
        function flush()
            local task=scheduled[#scheduled]
            task.f(task.arg,task.at)
        end
        """)
    source = Path("resources/plugins/base/dcs_retribution.lua").read_text("utf-8")
    lua.execute(
        source[
            source.index("SCENERY_MATCH_RADIUS =") : source.index(
                "-- Scenery that can never die"
            )
        ]
    )
    lua.execute(scenery_preamble(owner or Player.RED))
    if owner is None:
        lua.execute("ESCALATION_SCENERY_ZONES[1].coalition=nil")
    return lua


@pytest.mark.parametrize("owner,shooter", [(Player.RED, 2), (Player.BLUE, 1)])
def test_enemy_scenery_kills_are_good_news_to_attacker_and_losses_to_owner(
    owner: Player,
    shooter: int,
) -> None:
    lua = scenery_log(owner)
    lua.globals().shooter_side = shooter
    lua.execute("""
        attacker=aircraft('attacker',shooter_side)
        kill(attacker,scenery(71000001));kill(attacker,scenery(71000002));flush()
        """)
    messages = list(lua.globals().messages.values())
    success = [m.text for m in messages if m.side == shooter]
    losses = [m.text for m in messages if m.side == 3 - shooter]
    assert len(success) == len(losses) == 1
    assert success[0].startswith("YEAH!")
    assert losses[0].startswith("OH NO!")
    assert "DESTROYED several objects in the factory Factory" in success[0]


@pytest.mark.parametrize("owner,shooter", [(Player.BLUE, 2), (Player.RED, 1)])
def test_friendly_scenery_destruction_is_only_a_loss(
    owner: Player, shooter: int
) -> None:
    lua = scenery_log(owner)
    lua.globals().shooter_side = shooter
    lua.execute("kill(aircraft('attacker',shooter_side),scenery(71000001));flush()")
    messages = list(lua.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == shooter
    assert messages[0].text.startswith("OH NO!")
    assert "YEAH!" not in messages[0].text
    assert list(lua.globals().mission_log_events.values())[0].kind == "losses"


@pytest.mark.parametrize("owner", [Player.NEUTRAL, None])
def test_neutral_or_legacy_unknown_ownership_has_no_cheer(owner: Player | None) -> None:
    lua = scenery_log(owner)
    lua.execute("kill(blue,scenery(71000001));flush()")
    messages = list(lua.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == 2
    assert messages[0].text.startswith("the F/A-18E DESTROYED")
    assert "OH NO!" not in messages[0].text and "YEAH!" not in messages[0].text


@pytest.mark.parametrize("native_side", ["nil", "0", "2", "1"])
def test_campaign_owner_overrides_native_scenery_side(native_side: str) -> None:
    lua = scenery_log(Player.RED)
    lua.execute(
        f"target=scenery(71000001);target.getCoalition=function()return {native_side} end"
    )
    lua.execute("kill(blue,target);flush()")
    assert next(
        m.text for m in lua.globals().messages.values() if m.side == 2
    ).startswith("YEAH!")


def test_friendly_loss_setting_and_groundkill_setting_remain_independent() -> None:
    lua = scenery_log(Player.RED)
    lua.execute(
        "dcsRetribution.plugins.missionlog.groundkills=false;kill(blue,scenery(71000001));flush()"
    )
    messages = list(lua.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == 1
    assert messages[0].text.startswith("OH NO!")


def test_no_owner_does_not_turn_unknown_non_scenery_kill_into_bad_news() -> None:
    lua = scenery_log(None)
    lua.execute("""
        target=scenery('unknown surface unit')
        target.getCoalition=function()return nil end
        target.getDesc=function()return {category=2}end
        kill(blue,target);flush()
        """)
    messages = list(lua.globals().messages.values())
    assert len(messages) == 1
    assert not messages[0].text.startswith(("OH NO!", "YEAH!"))


def test_destroyed_buildings_collapse_damage_and_keep_weapon_attribution() -> None:
    lua = scenery_log(Player.RED)
    lua.execute("""
        target=scenery(71000001)
        world.event.S_EVENT_HIT=5
        handler:onEvent({id=5,initiator=blue,target=target,
            weapon={getTypeName=function()return 'B21_AGM158B_AIR'end}})
        kill(blue,target);flush()
        """)
    messages = list(lua.globals().messages.values())
    success = [m.text for m in messages if m.side == 2]
    assert len(success) == 1 and success[0].startswith("YEAH!")
    assert success[0].endswith("with B21-AGM158B-AIR")
    assert all(
        event.kind != "damage" for event in lua.globals().mission_log_events.values()
    )


def test_scenery_outside_an_objective_remains_unreported() -> None:
    lua = scenery_log(Player.RED)
    lua.execute("ESCALATION_SCENERY_ZONES={};kill(blue,scenery(71000001));flush()")
    assert not list(lua.globals().messages.values())
