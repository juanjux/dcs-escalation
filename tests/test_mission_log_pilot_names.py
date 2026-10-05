"""Exercise generated pilot data with the mission log's real Lua event handler."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from game.missiongenerator.luagenerator import LuaGenerator


def pilot_preamble(enabled: bool, empty: bool = False) -> str:
    generator = object.__new__(LuaGenerator)
    fake: Any = generator
    fake.game = SimpleNamespace(settings=SimpleNamespace(live_pilots_enabled=enabled))
    fake.mission = SimpleNamespace(triggerrules=SimpleNamespace(triggers=[]))
    flying_unit = SimpleNamespace(
        pilot=SimpleNamespace(name='Alex "Viper" Smith'),
        flight=SimpleNamespace(
            squadron=SimpleNamespace(
                pilot_rank=lambda pilot: SimpleNamespace(abbreviation="Capt.")
            )
        ),
    )
    fake.unit_map = SimpleNamespace(aircraft={} if empty else {"blue": flying_unit})
    with patch(
        "game.missiongenerator.luagenerator.LuaPluginManager.plugins",
        return_value=[SimpleNamespace(identifier="missionlog", enabled=True)],
    ):
        generator._seed_pilot_roster()
    return str(fake.mission.triggerrules.triggers[0].actions[0].text.id)


def mission_log(enabled: bool, empty: bool = False) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        messages, logs = {}, {}
        timer = {getTime=function() return 10 end, scheduleFunction=function() end}
        trigger = {action={outTextForCoalition=function(side, text)
            messages[#messages+1]={side=side, text=text}
        end}}
        mist = {Logger={new=function() return {info=function(_, text)
            logs[#logs+1]=text
        end} end}}
        Unit = {Category={AIRPLANE=0, HELICOPTER=1}}
        world = {event={S_EVENT_SHOT=1, S_EVENT_KILL=2},
                 addEventHandler=function(h) handler=h end}
        function aircraft(name, side)
            return {getName=function() return name end,
                    getTypeName=function() return 'F/A-18E' end,
                    getPlayerName=function() return nil end,
                    getCoalition=function() return side end,
                    getDesc=function() return {category=0} end}
        end
        blue, red = aircraft('blue', 2), aircraft('red', 1)
        function shot(shooter, target)
            handler:onEvent({id=world.event.S_EVENT_SHOT, initiator=shooter,
                weapon={getTarget=function() return target end,
                        getTypeName=function() return 'AIM_120' end}})
        end
        function kill(shooter, target)
            handler:onEvent({id=world.event.S_EVENT_KILL,
                            initiator=shooter, target=target})
        end
        """)
    lua.execute(pilot_preamble(enabled, empty))
    script = Path("resources/plugins/missionlog/missionlog.lua")
    lua.execute(script.read_text(encoding="utf-8"))
    return lua


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    ("event", "phrase"),
    [
        ("shot(red, blue)", "is defending"),
        ("shot(blue, red)", "is engaging"),
        ("kill(blue, red)", "SHOT DOWN"),
        ("kill(red, blue)", "was SHOT DOWN"),
    ],
)
def test_friendly_events_respect_live_pilots(
    enabled: bool, event: str, phrase: str
) -> None:
    lua = mission_log(enabled)
    lua.execute(event)
    messages = [m.text for m in lua.globals().messages.values() if m.side == 2]
    assert len(messages) == 1
    assert phrase in messages[0]
    assert ("Capt. Alex 'Viper' Smith" in messages[0]) is enabled
    # Hiding names must not remove pilot attribution from debriefing data.
    events = list(lua.globals().mission_log_events.values())
    assert any(
        e.actor_pilot == "Capt. Alex 'Viper' Smith"
        or e.target_pilot == "Capt. Alex 'Viper' Smith"
        for e in events
    )
    assert "roster of 1 pilots" in lua.globals().logs[1]


@pytest.mark.parametrize("enabled", [True, False])
def test_empty_roster_falls_back_to_aircraft(enabled: bool) -> None:
    lua = mission_log(enabled, empty=True)
    lua.execute("kill(red, blue)")
    text = next(m.text for m in lua.globals().messages.values() if m.side == 2)
    assert "the F/A-18E was SHOT DOWN" in text
    assert "flown by" not in text
    assert lua.globals().ESCALATION_SHOW_PILOT_NAMES is enabled


def test_pilot_roster_survives_miz_export(tmp_path: Path) -> None:
    from dcs import Mission
    from dcs.action import DoScript
    from dcs.translation import String
    from dcs.triggers import TriggerStart

    mission = Mission()
    trigger = TriggerStart(comment="Mission Log (pilot roster)")
    trigger.add_action(DoScript(String(pilot_preamble(True))))
    mission.triggerrules.triggers.append(trigger)
    path = tmp_path / "pilot_names.miz"
    mission.save(str(path))
    lua = mission_log(False, empty=True)
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode("utf-8"))
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))
    lua.execute("""
        function getValueDictByKey(key) return dictionary[key] or key end
        function a_do_script(code) assert(loadstring(code))() end
        """)
    lua.execute(lua.globals().mission.trig.actions[1])
    lua.execute("kill(red, blue)")
    assert lua.globals().ESCALATION_SHOW_PILOT_NAMES is True
    text = next(m.text for m in lua.globals().messages.values() if m.side == 2)
    assert "Capt. Alex 'Viper' Smith was SHOT DOWN" in text
