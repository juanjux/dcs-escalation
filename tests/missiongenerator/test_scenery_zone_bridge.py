"""Generated scenery tables must be readable by the Lua scoring script."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from dcs import Mission

from game.missiongenerator.luagenerator import LuaGenerator
from game.theater.theatergroup import SceneryUnit


def generated_mission() -> Mission:
    generator: Any = object.__new__(LuaGenerator)
    units = [
        Mock(spec=SceneryUnit, alive=True, position=SimpleNamespace(x=100, y=200)),
        Mock(spec=SceneryUnit, alive=False, position=SimpleNamespace(x=500, y=200)),
    ]
    units[0].name, units[1].name = "alive", "dead"
    generator.game = SimpleNamespace(
        theater=SimpleNamespace(
            ground_objects=[
                SimpleNamespace(name="Factory", category="factory", units=units)
            ]
        )
    )
    generator.mission = Mission()
    generator._seed_scenery_objectives()
    return generator.mission


def runtime() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        logger={info=function() end}; dead_events={}; kill_details={}
        function object_at(x, z)
            return {getPoint=function() return {x=x,z=z} end}
        end
    """)
    source = Path("resources/plugins/base/dcs_retribution.lua").read_text(
        encoding="utf-8"
    )
    section = source[
        source.index("SCENERY_MATCH_RADIUS =") : source.index(
            "-- Scenery that can never die"
        )
    ]
    lua.execute(section + "\ncredit_test = credit_scenery_zone")
    return lua


@pytest.mark.parametrize("legacy", [False, True])
def test_generated_miz_matches_and_credits_once(tmp_path: Path, legacy: bool) -> None:
    mission = generated_mission()
    path = tmp_path / "scenery.miz"
    mission.save(str(path))
    lua = runtime()
    # The script can load before the generated data.
    assert lua.eval("scenery_zone_for(object_at(100, 200))") == (None, None)
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode("utf-8"))
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))
    lua.execute("""
        function getValueDictByKey(key) return dictionary[key] or key end
        function a_do_script(code) assert(loadstring(code))() end
    """)
    lua.execute(lua.globals().mission.trig.actions[1])
    if legacy:
        lua.execute(
            "RETRIBUTION_SCENERY_ZONES=ESCALATION_SCENERY_ZONES; ESCALATION_SCENERY_ZONES=nil"
        )
    zone, distance = lua.eval("scenery_zone_for(object_at(100, 200))")
    assert (zone.name, zone.objective, distance) == ("alive", "Factory", 0)
    assert lua.eval("credit_test(object_at(131, 200))") is False
    assert lua.eval("credit_test(object_at(100, 200))") is True
    assert lua.eval("credit_test(object_at(100, 200))") is False
    assert lua.eval("credit_test(object_at(500, 200))") is False
    assert list(lua.globals().dead_events.values()) == ["alive"]


def test_current_table_takes_precedence_even_when_empty() -> None:
    lua = runtime()
    lua.execute(
        "ESCALATION_SCENERY_ZONES={}; RETRIBUTION_SCENERY_ZONES={{name='old',x=0,y=0}}"
    )
    assert lua.eval("scenery_zone_for(object_at(0, 0))") == (None, None)
