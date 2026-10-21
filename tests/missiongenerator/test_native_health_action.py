"""Native trigger actions run outside the mission-sandbox scripting context."""

from pathlib import Path
from zipfile import ZipFile

import pytest
from dcs import Mission
from dcs.action import DoScript, DoScriptFile
from dcs.translation import String
from dcs.triggers import TriggerStart

from game.missiongenerator.persistenthealth import SetUnitHealth


@pytest.mark.parametrize("health", [0.35, 0.65, 0.9821209716796899, 1.0])
def test_native_action_uses_percent_units(health: float) -> None:
    action = SetUnitHealth(249, health)
    assert action.dict() == {
        "predicate": "a_unit_set_life_percentage",
        "unit": 249,
        "life_percents": health * 100,
    }


@pytest.mark.parametrize("value", [0, -1, 2, float("nan"), float("inf")])
def test_invalid_health_cannot_generate_destructive_actions(value: float) -> None:
    with pytest.raises(ValueError):
        SetUnitHealth(249, value)


def test_probe_generates_real_native_actions_for_both_object_types(
    tmp_path: Path,
) -> None:
    from dcs.lua import loads
    from tools.persistent_damage_probe import build_mission

    path = tmp_path / "probe.miz"
    mission = build_mission()
    mission.save(path)
    with ZipFile(path) as archive:
        data = loads(archive.read("mission").decode())["mission"]
    rules = list(data["trigrules"].values())
    actions = rules[0]["actions"]
    assert len(actions) == 6
    assert {a["predicate"] for a in actions.values()} == {"a_unit_set_life_percentage"}
    assert sorted(a["life_percents"] for a in actions.values()) == pytest.approx(
        [35, 35, 65, 65, 98.21209716796899, 98.21209716796899]
    )
    assert len({a["unit"] for a in actions.values()}) == 6
    assert "a_unit_set_life_percentage" in data["trig"]["actions"][1]


def test_compiled_mission_restores_without_net_or_a_sandbox_setter(
    tmp_path: Path,
) -> None:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    mission = Mission()
    trigger = TriggerStart(comment="Native health")
    trigger.add_action(
        DoScript(
            String(
                'ESCALATION_PERSISTENT_DAMAGE={{name="building",health=.65,native=true}}'
            )
        )
    )
    trigger.add_action(
        DoScriptFile(
            mission.map_resource.add_resource_file(
                "resources/plugins/base/persistent_damage.lua"
            )
        )
    )
    trigger.add_action(SetUnitHealth(249, 0.65))
    mission.triggerrules.triggers.append(trigger)
    path = tmp_path / "native.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode())
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode())
        lua.globals().runtime_source = archive.read(
            "l10n/DEFAULT/persistent_damage.lua"
        ).decode()
    lua.execute("""
        -- Separate environments share only the object, not native APIs.
        object={life=1000}
        object.getLife=function() return object.life end
        object.getLife0=function() return 1000 end
        object.isExist=function() return true end
        sandbox={env={warning=error},
            Unit={getByName=function() return object end},
            StaticObject={getByName=function() end},
            trigger={action={outText=error}},
            timer={getTime=function() return 0 end,
                scheduleFunction=function(fn) scheduled=fn end}}
        for _,key in ipairs({'math','string','type','tostring','pcall','ipairs','pairs'}) do
            sandbox[key]=_G[key]
        end
        function getValueDictByKey(key) return dictionary[key] or key end
        function getValueResourceByKey(key) return key end
        function a_do_script(code) setfenv(assert(loadstring(code)),sandbox)() end
        function a_do_script_file() a_do_script(runtime_source) end
        function a_unit_set_life_percentage(id,percent)
            assert(id==249 and percent==65)
            object.life=1000*percent/100
        end
    """)
    lua.execute(lua.globals().mission.trig.actions[1])
    lua.execute("scheduled(nil,1)")
    assert lua.eval("sandbox.net") is None
    assert lua.eval("sandbox.a_unit_set_life_percentage") is None
    assert lua.eval("sandbox.escalationPersistentDamage.snapshot().building") == 0.65
    lua.execute("object.life=400; scheduled(nil,2)")
    assert lua.eval("sandbox.escalationPersistentDamage.snapshot().building") == 0.4
