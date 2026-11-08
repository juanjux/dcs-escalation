"""Verify resource identity and startup after serializing both plugins together."""

from pathlib import Path
from zipfile import ZipFile

import pytest
from dcs.lua import loads

from game.missiongenerator import imac
from game.missiongenerator.realisticcascampaign import inject_campaign
from game.missiongenerator.realisticcasluadata import SCRIPT_ORDER
from .test_imac_generation import scenario


@pytest.mark.parametrize("cas_first", [True, False])
def test_saved_miz_keeps_both_adapters_and_starts_both_plugins(
    tmp_path: Path, cas_first: bool
) -> None:
    s = scenario()
    s.game.settings.set_plugin_option("realisticcas", True)
    s.game.settings.set_plugin_option("imac", True)
    cas = {
        "enabled": True,
        "acquisitionSeconds": 0,
        "registry": {
            "schemaVersion": 1,
            "groups": [],
            "targets": [],
            "observers": [],
            "knownAirDefenseGroups": [],
            "warnings": [],
        },
        "environment": {
            "defaultCover": "grassland",
            "startTime": 43200,
            "sunrise": 21600,
            "sunset": 64800,
            "weather": 1,
            "visibility": 100000,
        },
    }
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    if cas_first:
        inject_campaign(s.generator, cas)
        imac.inject(s.generator, data)
    else:
        imac.inject(s.generator, data)
        inject_campaign(s.generator, cas)
    path = tmp_path / "imac-and-realistic-cas.miz"
    s.mission.save(path)

    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        env={info=function()end,warning=function()end,error=function(text)error(text)end}
        timer={getTime=function()return 0 end,scheduleFunction=function()return 1 end}
        world={event={S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=23,S_EVENT_BIRTH=15,S_EVENT_MISSION_END=99},
          addEventHandler=function()end,removeEventHandler=function()end}
        Group={Category={AIRPLANE=0,GROUND=2,SHIP=3},getByName=function()end}
        Unit={getByName=function()end};StaticObject={getByName=function()end}
        Controller={Detection={VISUAL=1,OPTIC=2,RADAR=4,IRST=8,RWR=16,DLINK=32}}
        trigger={action={outText=function()end,outTextForCoalition=function()end}}
        land={getHeight=function()return 0 end,isVisible=function()return true end}
    """)
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        mission = loads(archive.read("mission").decode())["mission"]
        resources = loads(archive.read("l10n/DEFAULT/mapResource").decode())[
            "mapResource"
        ]
        triggers = mission["trigrules"]
        adapters = {}
        for trigger in triggers.values():
            if trigger["comment"] in ("Load realisticcas-dcs.lua", "Load imac-dcs.lua"):
                key = trigger["actions"][1]["file"]
                adapters[trigger["comment"]] = resources[key]
        cas_file = adapters["Load realisticcas-dcs.lua"]
        imac_file = adapters["Load imac-dcs.lua"]
        assert (
            cas_file != imac_file
        ), "Plugin adapters alias the same serialized resource"
        assert (
            archive.read("l10n/DEFAULT/" + cas_file)
            == Path("resources/plugins/realisticcas/dcs.lua").read_bytes()
        )
        assert (
            archive.read("l10n/DEFAULT/" + imac_file)
            == Path("resources/plugins/imac", imac.SCRIPTS[-1]).read_bytes()
        )
        scripts = [name for name in archive.namelist() if name.endswith(".lua")]
        assert len(scripts) == len(SCRIPT_ORDER) + len(imac.SCRIPTS)
        # Follow the saved trigger-to-mapResource references, not injector calls
        # or the original source paths: this is the path DCS actually loads.
        for trigger in triggers.values():
            for action in trigger["actions"].values():
                if action["predicate"] == "a_do_script_file":
                    lua.execute(
                        archive.read(
                            "l10n/DEFAULT/" + resources[action["file"]]
                        ).decode()
                    )
                elif action["predicate"] == "a_do_script":
                    lua.execute(action["text"])

    assert lua.eval("type(RealisticCAS.start)=='function'") is True
    assert lua.eval("type(EscalationIMAC.start)=='function'") is True
    assert lua.eval("type(EscalationIMAC.reached)=='function'") is True
    assert (
        lua.eval("RealisticCAS.mission.active and EscalationIMAC.instance.active")
        is True
    )
    cap = next(
        group
        for country in mission["coalition"]["blue"]["country"].values()
        for group in country.get("plane", {}).get("group", {}).values()
        if group["name"] == s.group.name
    )
    task = cap["route"]["points"][2]["task"]["params"]["tasks"][1]
    lua.execute(task["params"]["action"]["params"]["command"])
    assert lua.eval("EscalationIMAC.instance.states.CAP.index") == 2
