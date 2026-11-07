"""Run the production Skynet engine and relay graph against controlled DCS objects."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

from dcs import Mission
import pytest

from game.missiongenerator.luagenerator import LuaGenerator, LuaValue
from game.missiongenerator.missiondata import MissionData
from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.player import Player
from tests.test_iads_relay_connectivity import chain, node


@pytest.fixture
def vm() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("env={info=function() end}; mist={utils={}}")
    for script in ["skynet-iads-compiled.lua", "skynet-topology.lua"]:
        lua.execute(
            Path("resources/plugins/skynetiads", script).read_text(encoding="utf-8")
        )
    lua.execute("""
        Object={Category={UNIT=1,WEAPON=2}}
        world={event={S_EVENT_BIRTH=1,S_EVENT_DEAD=2,S_EVENT_SHOT=3}}
        Unit={Category={GROUND_UNIT=2,SHIP=3,STRUCTURE=4}}
        Weapon={Category={SHELL=0}}
        function createNetwork(data, side)
            objects={}; elements={}
            Group={getByName=function(name) return objects[name] end}
            Unit.getByName=function(name) return objects[name] end
            StaticObject={getByName=function(name)
                return objects[string.gsub(name,' object$','')]
            end}
            local iads=setmetatable({
                earlyWarningRadars={},samSites={},commandCenters={},contacts={},
                maxTargetAge=32,
                eventObjectSubscribers={},eventGroupSubscribers={},eventElements={},
                logger={debugOutput={},printSystemStatus=function() end},
            },SkynetIADS)
            function iads:getEarlyWarningRadars() return self.earlyWarningRadars end
            function iads:getSAMSites() return self.samSites end
            iads.harmDetection=SkynetIADSHARMDetection:create(iads)
            for role, rows in pairs(data) do
                for _, row in ipairs(rows) do
                    local name=row.dcsGroupName
                    local object={live=true,side=side}
                    function object:isExist() return self.live end
                    function object:getLife() return self.live and 100 or 0 end
                    function object:getCoalition() return self.side end
                    if role=='Sam' or role=='SamAsEwr' then
                        function object:getUnits() return {self} end
                    end
                    objects[name]=object
                    local kind, collection
                    if role=='Sam' or role=='SamAsEwr' then
                        kind=SkynetIADSSamSite; collection=iads.samSites
                    elseif role=='Ewr' then
                        kind=SkynetIADSEWRadar; collection=iads.earlyWarningRadars
                    elseif role=='CommandCenter' then
                        kind=SkynetIADSCommandCenter; collection=iads.commandCenters
                    end
                    if kind then
                        kind.__index=kind
                        local element=setmetatable({
                            iads=iads,dcsName=(role=='CommandCenter' and name..' object' or name),
                            parentRadars={},childRadars={},
                            connectionNodes={},powerSources={},inbox={},harms={},detected={},
                            actAsEW=(role=='Ewr' or role=='SamAsEwr'),active=false,
                            isAutonomous=false,
                            autonomousBehaviour=SkynetIADSAbstractRadarElement.AUTONOMOUS_STATE_DCS_AI,
                        },kind)
                        function element:isDestroyed() return not object.live end
                        function element:goLive() self.active=self:hasWorkingPowerSource() end
                        function element:goDark() self.active=false end
                        function element:isActive() return self.active end
                        function element:getDetectedTargets() return self.detected end
                        function element:informOfContact(contact)
                            self.inbox[#self.inbox+1]=contact:getName()
                        end
                        function element:informOfHARM(contact)
                            self.harms[#self.harms+1]=contact:getName()
                        end
                        function element:informChildrenOfStateChange() end
                        elements[name]=element
                        table.insert(collection,element)
                    end
                end
            end
            iads.topology=EscalationIadsTopology:create(iads,data,side)
            return iads
        end
        function cover(parent,child)
            table.insert(parent.childRadars,child)
            table.insert(child.parentRadars,parent)
            child:setToCorrectAutonomousState()
        end
        function contact(name,source)
            local c={name=name,radars={source},harm=0}
            function c:getName() return self.name end
            function c:getAge() return 0 end
            function c:refresh() end
            function c:getDesc() return {category=0} end
            function c:getDCSRepresentation() return {getCategory=function() return 1 end} end
            function c:getHARMState() return self.harm end
            function c:setHARMState(state) self.harm=state end
            function c:getAbstractRadarElementsDetected() return self.radars end
            function c:addAbstractRadarElementDetected(radar) self.radars[#self.radars+1]=radar end
            function c:getGroundSpeedInKnots() return 0 end
            return c
        end
    """)
    return lua


def start(vm: Any, data: dict[str, list[dict[str, Any]]], side: int = 1) -> None:
    vm.globals().data = vm.table_from(data, recursive=True)
    vm.globals().iads = vm.globals().createNetwork(vm.globals().data, side)


def relay_data() -> dict[str, list[dict[str, Any]]]:
    return {
        "CommandCenter": [{"dcsGroupName": "CC", "ConnectionNode": ["A"]}],
        "ConnectionNode": [
            {"dcsGroupName": "A", "CommandCenter": ["CC"], "ConnectionNode": ["B"]},
            {"dcsGroupName": "B", "ConnectionNode": ["A"]},
        ],
        "Sam": [{"dcsGroupName": "SAM", "ConnectionNode": ["B"]}],
        "Ewr": [{"dcsGroupName": "EWR", "ConnectionNode": ["B"]}],
    }


@pytest.mark.parametrize("side", [1, 2])
def test_remote_loss_and_repair_change_native_autonomy(vm: Any, side: int) -> None:
    start(vm, relay_data(), side)
    vm.execute("""
        cover(elements.EWR,elements.SAM)
        assert(not elements.SAM:getAutonomousState())
        objects.A.live=false
        iads:evaluateContacts()
        assert(elements.SAM:getAutonomousState())
        assert(elements.SAM:isActive()) -- Still powered, defends itself.
        objects.A.live=true
        iads:evaluateContacts()
        assert(not elements.SAM:getAutonomousState())
        assert(not elements.SAM:isActive()) -- Networked and waiting for a cue.
    """)


def test_redundant_chain_and_cycles_survive_one_failure(vm: Any) -> None:
    data = relay_data()
    data["ConnectionNode"].append({"dcsGroupName": "BACKUP", "CommandCenter": ["CC"]})
    data["ConnectionNode"][1]["ConnectionNode"].append("BACKUP")
    start(vm, data)
    vm.execute("""
        objects.A.live=false
        iads.topology:beginCycle()
        assert(elements.SAM:hasActiveConnectionNode())
        objects.BACKUP.live=false
        iads.topology:beginCycle()
        assert(not elements.SAM:hasActiveConnectionNode())
    """)


@pytest.mark.parametrize("missing", [True, False])
def test_remote_power_loss_and_missing_dependencies_fail_closed(
    vm: Any, missing: bool
) -> None:
    data = relay_data()
    data["PowerSource"] = [{"dcsGroupName": "POWER"}]
    data["ConnectionNode"][0]["PowerSource"] = ["POWER"]
    data["Sam"][0]["PowerSource"] = ["POWER"]
    start(vm, data)
    vm.execute("cover(elements.EWR,elements.SAM)")
    vm.execute("objects.POWER=nil" if missing else "objects.POWER.live=false")
    vm.execute("""
        iads:evaluateContacts()
        assert(not elements.SAM:hasActiveConnectionNode())
        assert(not elements.SAM:hasWorkingPowerSource())
        assert(not elements.SAM:isActive())
    """)


@pytest.mark.parametrize("side", [1, 2])
def test_explicit_power_requirement_with_zero_links_stays_dark(
    vm: Any, side: int
) -> None:
    data = relay_data()
    data["Sam"][0]["requiresPower"] = True
    data["CommandCenter"][0]["requiresPower"] = True
    start(vm, data, side)
    vm.execute("""
        cover(elements.EWR,elements.SAM)
        iads:evaluateContacts()
        assert(not elements.SAM:hasWorkingPowerSource())
        assert(not elements.SAM:isActive())
        assert(not elements.CC:hasWorkingPowerSource())
    """)


@pytest.mark.parametrize("side", [1, 2])
def test_local_generator_is_checked_live_and_grid_remains_a_backup(
    vm: Any, side: int
) -> None:
    data = relay_data()
    data["Sam"][0].update(
        requiresPower=True, localPowerSources=["GENERATOR"], PowerSource=["GRID"]
    )
    data["PowerSource"] = [{"dcsGroupName": "GRID"}]
    start(vm, data, side)
    vm.execute("""
        objects.GENERATOR={live=true,side=iads.topology.coalition}
        function objects.GENERATOR:isExist() return self.live end
        function objects.GENERATOR:getLife() return self.live and 100 or 0 end
        function objects.GENERATOR:getCoalition() return self.side end
        objects.GRID.live=false
        iads.topology:beginCycle()
        assert(elements.SAM:hasWorkingPowerSource())
        objects.GENERATOR.live=false
        iads.topology:onEvent({initiator={getName=function() return 'GENERATOR' end}})
        assert(not elements.SAM:hasWorkingPowerSource())
        assert(not elements.SAM:isActive())
        objects.GRID.live=true
        iads.topology:beginCycle()
        assert(elements.SAM:hasWorkingPowerSource())
        objects.GRID=nil
        objects.GENERATOR.side=3-iads.topology.coalition
        objects.GENERATOR.live=true
        iads.topology:beginCycle()
        assert(not elements.SAM:hasWorkingPowerSource())
    """)


def test_power_station_cannot_relay_radio_and_absent_command_is_not_global_command(
    vm: Any,
) -> None:
    data: dict[str, list[dict[str, Any]]] = {
        "CommandCenter": [{"dcsGroupName": "CC"}],
        "PowerSource": [{"dcsGroupName": "POWER", "CommandCenter": ["CC"]}],
        "Sam": [{"dcsGroupName": "SAM", "PowerSource": ["POWER"]}],
    }
    start(vm, data)
    vm.execute(
        "assert(not elements.SAM:hasActiveConnectionNode()); assert(elements.SAM:hasWorkingPowerSource())"
    )
    del data["CommandCenter"]
    start(vm, data)
    vm.execute("assert(not elements.SAM:hasActiveConnectionNode())")


def partition_data() -> dict[str, list[dict[str, Any]]]:
    return {
        "CommandCenter": [{"dcsGroupName": "CC1"}, {"dcsGroupName": "CC2"}],
        "Ewr": [
            {"dcsGroupName": "E1", "CommandCenter": ["CC1"]},
            {"dcsGroupName": "E2", "CommandCenter": ["CC2"]},
        ],
        "Sam": [
            {"dcsGroupName": "S1", "CommandCenter": ["CC1"]},
            {"dcsGroupName": "S2", "CommandCenter": ["CC2"]},
        ],
    }


def test_native_contact_fanout_and_harm_notifications_respect_partitions(
    vm: Any,
) -> None:
    start(vm, partition_data())
    vm.execute("""
        cover(elements.E1,elements.S1)
        cover(elements.E1,elements.S2) -- Radar coverage crosses the radio partition.
        cover(elements.E2,elements.S2)
        first=contact('FIRST',elements.E1); second=contact('SECOND',elements.E2)
        elements.E1.detected={first}; elements.E2.detected={second}
        iads:evaluateContacts()
        assert(#elements.S1.inbox==1 and elements.S1.inbox[1]=='FIRST')
        assert(#elements.S2.inbox==1 and elements.S2.inbox[1]=='SECOND')
        iads.harmDetection:informRadarsOfHARM(first)
        assert(#elements.S1.harms==1 and #elements.S2.harms==0)
        assert(#elements.E1.harms==1 and #elements.E2.harms==0)
    """)


def test_point_defences_inherit_local_radio_paths_not_global_airborne_connectivity(
    vm: Any,
) -> None:
    data = partition_data()
    data["Sam"][0]["PD"] = ["PD1"]
    start(vm, data)
    vm.execute("""
        -- Point-defence groups are enrolled by the configuration, not top-level rows.
        objects.PD1={isExist=function() return true end,
            getUnits=function() return {{isExist=function() return true end,getLife=function() return 100 end}} end}
        local pd=setmetatable({iads=iads,dcsName='PD1',connectionNodes={}},SkynetIADSSamSite)
        iads.topology:updateState()
        assert(iads.topology:canExchange(pd,elements.S1))
        assert(not iads.topology:canExchange(pd,elements.S2))
        objects.CC1.live=false
        iads.topology:updateState()
        assert(not pd:hasActiveConnectionNode())
        assert(pd:hasWorkingPowerSource())
    """)


def test_old_detection_provenance_does_not_leak_contacts_after_a_cut(vm: Any) -> None:
    data = partition_data()
    data["CommandCenter"][0]["CommandCenter"] = ["CC2"]
    data["CommandCenter"][1]["CommandCenter"] = ["CC1"]
    start(vm, data)
    vm.execute("""
        cover(elements.E1,elements.S1); cover(elements.E2,elements.S2)
        known=contact('KNOWN',elements.E1)
        elements.E1.detected={known}; iads:evaluateContacts()
        -- Simulate the turn's graph separating into two surviving command sectors.
        data.CommandCenter[1].CommandCenter={}
        data.CommandCenter[2].CommandCenter={}
        iads.topology.signature=nil
        elements.E1.detected={contact('LOCAL',elements.E1)}
        elements.E2.detected={contact('KNOWN',elements.E2)}
        elements.S1.inbox={}; elements.S2.inbox={}
        iads:evaluateContacts()
        assert(#elements.S1.inbox==1 and elements.S1.inbox[1]=='LOCAL')
        assert(#elements.S2.inbox==1 and elements.S2.inbox[1]=='KNOWN')
        assert(#known:getAbstractRadarElementsDetected()>1)
    """)


def test_enemy_or_dead_command_cannot_complete_a_path(vm: Any) -> None:
    start(vm, relay_data())
    vm.execute("""
        objects.CC.side=2
        iads.topology:beginCycle()
        assert(not elements.SAM:hasActiveConnectionNode())
        objects.CC.side=1
        iads.topology:beginCycle()
        assert(elements.SAM:hasActiveConnectionNode())
        objects.CC.live=false
        iads.topology:beginCycle()
        assert(not elements.SAM:hasActiveConnectionNode())
    """)


def test_native_death_event_breaks_a_remote_chain_before_the_next_scan(vm: Any) -> None:
    start(vm, relay_data())
    vm.execute("""
        cover(elements.EWR,elements.SAM)
        objects.A.live=false
        iads:onEvent({id=world.event.S_EVENT_DEAD})
        assert(elements.SAM:getAutonomousState())
        objects.A.live=true
        iads:onEvent({id=world.event.S_EVENT_BIRTH})
        assert(not elements.SAM:getAutonomousState())
    """)


def test_ships_and_airborne_radios_do_not_restore_isolated_ground_sites(
    vm: Any,
) -> None:
    data = partition_data()
    data["Sam"].append({"dcsGroupName": "SHIP", "independentComms": True})
    data["Sam"].append({"dcsGroupName": "ISOLATED"})
    start(vm, data)
    vm.execute("""
        assert(iads.topology:canExchange(elements.SHIP,elements.S1))
        assert(iads.topology:canExchange(elements.SHIP,elements.S2))
        assert(not iads.topology:canExchange(elements.SHIP,elements.ISOLATED))
        awacs=setmetatable({iads=iads,dcsName='AWACS',connectionNodes={}},SkynetIADSEWRadar)
        assert(iads.topology:canExchange(awacs,elements.S1))
        assert(not iads.topology:canExchange(awacs,elements.ISOLATED))
    """)


def test_infrastructure_events_refresh_paths_but_unrelated_deaths_do_not(
    vm: Any,
) -> None:
    start(vm, relay_data())
    vm.execute("""
        local original=iads.topology.refresh
        refreshes=0
        function iads.topology:refresh()
            refreshes=refreshes+1
            return original(self)
        end
        iads.topology:onEvent({initiator={getName=function() return 'UNRELATED' end}})
        assert(refreshes==0)
        objects.CC.live=false
        iads.topology:onEvent({initiator={getName=function() return 'CC object' end}})
        assert(refreshes==1 and not elements.SAM:hasActiveConnectionNode())
        objects.CC.live=true
        iads.topology:onEvent({initiator={getName=function() return 'CREW UNIT' end,
            getGroup=function() return {getName=function() return 'SAM' end} end}})
        assert(refreshes==2 and elements.SAM:hasActiveConnectionNode())
    """)


def exported(
    network: IadsNetwork, side: Player | None = None
) -> dict[str, list[dict[str, Any]]]:
    game: Any = SimpleNamespace(
        iads_considerate_culling=lambda _: False, skynet_culled=lambda _: False
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in network.skynet_nodes(game):
        if side is not None and entry.player is not side:
            continue
        row: dict[str, Any] = {"dcsGroupName": entry.dcs_name, **entry.connections}
        if entry.independent_comms:
            row["independentComms"] = True
        if entry.requires_power:
            row["requiresPower"] = True
        if entry.local_power_sources:
            row["localPowerSources"] = entry.local_power_sources
        result.setdefault(entry.iads_role.value, []).append(row)
    return result


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_exported_python_graph_and_runtime_agree_through_remote_losses(
    vm: Any, side: Player
) -> None:
    network, (_, relay_a, _, sam, _, _) = chain(side)
    data = exported(network)
    start(vm, data, 2 if side is Player.BLUE else 1)
    name_by_object = {
        current.group.ground_object: next(
            entry["dcsGroupName"]
            for entry in data[current.group.iads_role.value]
            if entry["dcsGroupName"]
            == (
                current.group.group_name
                if current.group.iads_role.value == "Sam"
                else current.group.units[0].unit_name
            )
        )
        for current in network.nodes
    }
    for alive in [True, False, True]:
        relay_a.groups[0].units[0].alive = alive
        network.update_tgo(relay_a, GameUpdateEvents())
        vm.globals().objects[name_by_object[relay_a]].live = alive
        vm.globals().iads.topology.beginCycle(vm.globals().iads.topology)
        connectivity = network.state_map.connectivity
        assert connectivity is not None
        for obj, name in name_by_object.items():
            element = vm.globals().elements[name]
            if element is not None:
                assert element.hasActiveConnectionNode(
                    element
                ) == connectivity.connected(node(network, obj))
                assert element.hasWorkingPowerSource(element) == connectivity.powered(
                    node(network, obj)
                )


def test_plugin_loads_topology_before_configuration() -> None:
    plugin = json.loads(Path("resources/plugins/skynetiads/plugin.json").read_text())
    files = [order["file"] for order in plugin["scriptsWorkOrders"]]
    assert files.index("skynet-iads-compiled.lua") < files.index("skynet-topology.lua")


@pytest.mark.parametrize("value", [True, False])
def test_topology_flags_are_lua_booleans_not_truthy_strings(
    vm: Any, value: bool
) -> None:
    vm.execute(LuaValue("automaticTopology", value).serialize())
    assert vm.globals().automaticTopology is value


@pytest.mark.parametrize("advanced", [True, False])
def test_generated_miz_packages_the_graph_and_runtime_in_load_order(
    vm: Any, tmp_path: Path, advanced: bool
) -> None:
    network, objects = chain()
    network.advanced_iads = advanced
    network.initialize_network(iter(objects))
    game: Any = SimpleNamespace(
        settings=Settings(),
        theater=SimpleNamespace(iads_network=network, controlpoints=[]),
        iads_considerate_culling=lambda _: False,
        skynet_culled=lambda _: False,
    )
    mission = Mission()
    game.settings.set_plugin_option("gpsjamming", False)
    generator = LuaGenerator(game, mission, MissionData())
    generator.generate_plugin_data()
    plugin = LuaPlugin.from_json(
        "skynetiads", Path("resources/plugins/skynetiads/plugin.json")
    )
    assert plugin is not None
    plugin.set_settings(game.settings)
    plugin.inject_scripts(generator)
    plugin.inject_configuration(generator)
    path = tmp_path / "automatic-iads.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        assert any(name.endswith("skynet-topology.lua") for name in archive.namelist())
        for name in archive.namelist():
            if name == "mission" or name.endswith(".lua"):
                vm.compile(archive.read(name).decode())
        vm.execute(archive.read("mission").decode())
        vm.execute(archive.read("l10n/DEFAULT/dictionary").decode())
    vm.execute("""
        function getValueDictByKey(key) return dictionary[key] or key end
        function a_do_script(code) assert(loadstring(code))() end
    """)
    vm.execute(vm.globals().mission.trig.actions[1])
    data = vm.globals().dcsRetribution.IADS
    assert data.automaticTopology is advanced
    assert len(data.RED.Sam) == 1
    if advanced:
        assert data.RED.Sam[1].requiresPower is True
        assert len(data.RED.ConnectionNode) == 2
        assert len(data.RED.CommandCenter) == 1
        assert len(data.RED.Sam[1].ConnectionNode) == 1
    else:
        assert data.RED.Sam[1].requiresPower is None
        assert data.RED.ConnectionNode is None
        assert data.RED.CommandCenter is None
