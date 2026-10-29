"""Surface losses reach their owner independently of attacker kill announcements."""

from typing import Any

import pytest

from tests.test_mission_log_pilot_names import mission_log


@pytest.fixture
def log() -> Any:
    lua = mission_log(False)
    lua.execute("""
        function surface(name, side, category)
            local u=aircraft(name, side)
            u.getDesc=function()return {category=category or 2}end
            return u
        end
        function flush()
            local task=scheduled[#scheduled]
            task.f(task.arg, task.at)
        end
        function dead(target)
            handler:onEvent({id=world.event.S_EVENT_DEAD,initiator=target})
        end
        function lost(target)
            handler:onEvent({id=world.event.S_EVENT_UNIT_LOST,initiator=target})
        end
        dcsRetribution={plugins={missionlog={maxmessages=60}}}
        """)
    return lua


@pytest.mark.parametrize("owner", [1, 2])
@pytest.mark.parametrize(
    "name,category", [("M1A2 Abrams", 2), ("Patriot STR", 2), ("CG Ticonderoga", 3)]
)
def test_losses_are_reported_to_surface_owner(
    log: Any, owner: int, name: str, category: int
) -> None:
    log.globals().owner = owner
    log.globals().label = name
    log.globals().category = category
    log.execute("""
        target=surface('0123 | '..label,owner,category)
        shooter=aircraft('attacker',3-owner)
        kill(shooter,target);assert(#messages==0)
        dead(target);lost(target);flush()
        """)
    messages = list(log.globals().messages.values())
    losses = [m.text for m in messages if m.side == owner]
    assert len(losses) == 1 and losses[0].startswith("OH NO!")
    assert name in losses[0] and "the enemy F/A-18E DESTROYED" in losses[0]
    assert len([m for m in messages if m.side == 3 - owner]) == 1
    assert any(
        e.kind == "losses" and e.side == owner
        for e in log.globals().mission_log_events.values()
    )


@pytest.mark.parametrize("losses", [False, True])
@pytest.mark.parametrize("kills", [False, True])
def test_losses_and_groundkills_are_independent_settings(
    log: Any, losses: bool, kills: bool
) -> None:
    options = log.globals().dcsRetribution.plugins.missionlog
    options.losses, options.groundkills = losses, kills
    log.execute("kill(red,surface('0123 | SA-11 Buk',2));flush()")
    messages = list(log.globals().messages.values())
    assert len([m for m in messages if m.side == 2]) == int(losses)
    assert len([m for m in messages if m.side == 1]) == int(kills)
    assert any("[losses]" in text for text in log.globals().logs.values())
    assert any(e.kind == "losses" for e in log.globals().mission_log_events.values())


def test_friendly_fire_is_one_loss_not_a_success(log: Any) -> None:
    log.execute("kill(blue,surface('0123 | HMMWV',2));flush()")
    messages = list(log.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == 2
    assert messages[0].text.startswith("OH NO!") and "YEAH!" not in messages[0].text
    assert "enemy" not in messages[0].text


@pytest.mark.parametrize("event", ["dead(target)", "lost(target)", "kill(nil,target)"])
def test_unattributed_deaths_still_report_a_single_loss(log: Any, event: str) -> None:
    log.execute("target=surface('0123 | M1A2 Abrams',2)")
    log.execute(event)
    log.execute("dead(target);lost(target);flush()")
    messages = list(log.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == 2
    assert messages[0].text == "OH NO! We LOST the M1A2 Abrams"


def test_death_before_kill_does_not_duplicate_owner_message(log: Any) -> None:
    log.execute("""
        target=surface('0123 | SA-11 Buk',2)
        dead(target);kill(red,target);lost(target);flush()
        """)
    assert len([m for m in log.globals().messages.values() if m.side == 2]) == 1


def test_surface_killer_and_multiple_same_type_casualties_are_coalesced(
    log: Any,
) -> None:
    log.execute("""
        shooter=surface('0100 | T-72B',1)
        a=surface('0123 | M1A2 Abrams',2);b=surface('0124 | M1A2 Abrams',2)
        kill(shooter,a);kill(shooter,a);kill(shooter,b);flush()
        """)
    losses = [m.text for m in log.globals().messages.values() if m.side == 2]
    assert losses == ["OH NO! the enemy T-72B DESTROYED 2 M1A2 Abrams"]
    records = [
        e for e in log.globals().mission_log_events.values() if e.kind == "losses"
    ]
    assert len(records) == 1 and records[0].count == 2


def test_death_fallback_does_not_misclassify_aircraft_or_unknown_objects(
    log: Any,
) -> None:
    log.execute("""
        dead(blue);lost(blue)
        unavailable=surface('unavailable',2)
        unavailable.getDesc=function()error('native object unavailable')end
        dead(unavailable)
        dead(surface('neutral',0))
        flush()
        assert(#messages==0)
        """)


def test_remembered_weapon_is_used_for_ground_loss(log: Any) -> None:
    log.execute("""
        target=surface('0123 | Patriot STR',2)
        world.event.S_EVENT_HIT=5
        handler:onEvent({id=5,initiator=red,target=target,
            weapon={getTypeName=function()return 'Kh_31P'end}})
        kill(red,target);flush()
        """)
    losses = [m.text for m in log.globals().messages.values() if m.side == 2]
    assert len(losses) == 1 and losses[0].endswith("with Kh-31P")
