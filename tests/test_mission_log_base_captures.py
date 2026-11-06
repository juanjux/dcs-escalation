"""Campaign capture triggers announce ownership changes through the real Lua log."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zipfile import ZipFile

import pytest
from dcs.action import DoScript
from dcs.mission import Mission
from dcs.terrain import Caucasus
from dcs.triggers import TriggerCondition

from game.missiongenerator.triggergenerator import TriggerGenerator
from game.theater import ControlPoint
from game.theater.player import Player
from tests.test_mission_log_pilot_names import mission_log


def capture_trigger(
    initial: Player,
    side: int,
    name: str = "Test Base",
    base_id: str = "cp-1",
) -> TriggerCondition:
    cp = cast(
        ControlPoint,
        SimpleNamespace(id=base_id, full_name=name, captured=initial),
    )
    return object.__new__(TriggerGenerator)._create_capture_trigger(
        1, 600, "blue" if side == 2 else "red", "red" if side == 2 else "blue", side, cp
    )


def capture(lua: Any, initial: Player, side: int, **kwargs: str) -> None:
    trigger = capture_trigger(initial, side, **kwargs)
    action = trigger.actions[-1]
    assert isinstance(action, DoScript)
    lua.execute(str(action.text.id))


@pytest.fixture
def log() -> Any:
    lua = mission_log(False)
    lua.execute("base_capture_events = {}; dirty_state = false")
    return lua


@pytest.mark.parametrize("side", [1, 2])
def test_capture_and_recapture_are_news_for_both_sides(log: Any, side: int) -> None:
    owner = Player.RED if side == 2 else Player.BLUE
    capture(log, owner, side)
    assert [(m.side, m.text) for m in log.globals().messages.values()] == [
        (side, "YEAH! We CAPTURED Test Base"),
        (3 - side, "OH NO! We LOST Test Base"),
    ]
    # An identical trigger firing is not another ownership change.
    capture(log, owner, side)
    assert len(log.globals().messages) == 2
    capture(log, owner, 3 - side)
    messages = list(log.globals().messages.values())
    assert [(m.side, m.text) for m in messages[2:]] == [
        (3 - side, "YEAH! We CAPTURED Test Base"),
        (side, "OH NO! We LOST Test Base"),
    ]
    events = list(log.globals().mission_log_events.values())
    assert len(events) == 2
    assert events[0].kind == "base_capture"
    assert events[0].base_id == "cp-1"
    assert events[0].place == "Test Base"
    assert events[0].side == side and events[0].previous_side == 3 - side
    assert events[1].side == 3 - side and events[1].previous_side == side
    assert log.globals().dirty_state is True
    assert log.globals().base_capture_events[1] == f"cp-1||{side}||Test Base"


@pytest.mark.parametrize("side", [1, 2])
def test_neutral_base_capture_does_not_report_an_enemy_loss(
    log: Any, side: int
) -> None:
    capture(log, Player.NEUTRAL, side)
    messages = list(log.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == side
    assert log.globals().mission_log_events[1].previous_side == 0
    # Later transitions use the current owner, not the mission's initial neutral.
    capture(log, Player.NEUTRAL, 3 - side)
    assert len(log.globals().messages) == 3
    assert log.globals().mission_log_events[2].previous_side == side


def test_base_owners_are_tracked_independently(log: Any) -> None:
    capture(log, Player.BLUE, 1, base_id="cp-1")
    capture(log, Player.NEUTRAL, 1, base_id="cp-2")
    assert len(log.globals().messages) == 3
    assert len(log.globals().mission_log_events) == 2


def test_disabled_capture_messages_still_update_ownership_and_records(log: Any) -> None:
    log.execute("dcsRetribution = {plugins={missionlog={basecaptures=false}}}")
    capture(log, Player.BLUE, 1)
    assert len(log.globals().messages) == 0
    assert len(log.globals().logs) == 3  # Startup and both coalition messages.
    assert len(log.globals().mission_log_events) == 1
    log.globals().dcsRetribution.plugins.missionlog.basecaptures = True
    capture(log, Player.BLUE, 2)
    assert len(log.globals().messages) == 2


def test_capture_messages_respect_budget_and_configured_prefixes(log: Any) -> None:
    log.execute("""
        dcsRetribution = {plugins={missionlog={maxmessages=1,goodnews='',badnews='Lost:'}}}
        """)
    capture(log, Player.BLUE, 1)
    capture(log, Player.BLUE, 2)
    assert [m.text for m in log.globals().messages.values()] == [
        "We CAPTURED Test Base",
        "Lost: We LOST Test Base",
    ]
    assert len(log.globals().mission_log_events) == 2
    assert len(log.globals().logs) == 5


@pytest.mark.parametrize("callback", ["nil", "false"])
def test_capture_trigger_works_without_mission_log(log: Any, callback: str) -> None:
    log.execute(f"MISSION_LOG_BASE_CAPTURED = {callback}")
    capture(log, Player.BLUE, 1)
    assert log.globals().base_capture_events[1] == "cp-1||1||Test Base"
    assert log.globals().dirty_state is True
    assert len(log.globals().messages) == 0


def test_native_airbase_capture_does_not_duplicate_campaign_trigger(log: Any) -> None:
    log.execute("""
        world.event.S_EVENT_BASE_CAPTURED = 10
        handler:onEvent({id=10,place={getName=function()return 'Test Base'end}})
        """)
    assert len(log.globals().messages) == 0
    capture(log, Player.BLUE, 1)
    assert len(log.globals().messages) == 2


def test_saved_mission_capture_trigger_preserves_names(
    log: Any, tmp_path: Path
) -> None:
    name = 'FOB "Águila" \\ North\nLanding zone'
    mission = Mission(Caucasus())
    mission.triggerrules.triggers.append(capture_trigger(Player.RED, 2, name))
    path = tmp_path / "base_capture.miz"
    mission.save(str(path))
    with ZipFile(path) as archive:
        log.execute(archive.read("mission").decode("utf-8"))
        log.execute(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))
    log.execute("""
        function getValueDictByKey(key) return dictionary[key] or key end
        function a_do_script(code) assert(loadstring(code))() end
        function a_set_flag() end
        """)
    log.execute(log.globals().mission.trig.actions[1])
    assert log.globals().base_capture_events[1] == f"cp-1||2||{name}"
    assert log.globals().mission_log_events[1].place == name
    assert log.globals().messages[1].text == f"YEAH! We CAPTURED {name}"


def test_plugin_and_lua_defaults_enable_base_capture_messages(log: Any) -> None:
    definition = json.loads(
        Path("resources/plugins/missionlog/plugin.json").read_text(encoding="utf-8")
    )
    option = next(
        option
        for option in definition["specificOptions"]
        if option["mnemonic"] == "basecaptures"
    )
    assert option["defaultValue"] is True
    assert log.globals().MISSION_LOG_DEFAULTS.basecaptures is True
