"""Run the production Skynet engine and relay graph against controlled DCS objects."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

from dcs import Mission
from dcs.vehicles import AirDefence
import pytest

from game.missiongenerator.luagenerator import LuaGenerator, LuaValue
from game.missiongenerator.missiondata import MissionData
from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, SkynetNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from tests.test_iads_relay_connectivity import chain, node
from tests.test_iads_automatic_topology import site


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


def automatic_data() -> dict[str, list[dict[str, Any]]]:
    """A redundant radio sector, an isolated relay and three nearby plants."""
    positions = {"CC1": 0, "A": 1000, "B": 2000, "C": 3000, "CC2": 4000}
    data: dict[str, list[dict[str, Any]]] = {
        "CommandCenter": [],
        "ConnectionNode": [],
        "PowerSource": [{"dcsGroupName": name} for name in ["P1", "P2", "P3"]],
    }
    for name, position in positions.items():
        candidates = sorted(
            (
                {"name": other, "distance": abs(position - x)}
                for other, x in positions.items()
                if other != name
            ),
            key=lambda row: (row["distance"], row["name"]),
        )
        role = "CommandCenter" if name.startswith("CC") else "ConnectionNode"
        data[role].append(
            {
                "dcsGroupName": name,
                "topologyKey": name,
                "radioCandidates": candidates,
            }
        )
    data["ConnectionNode"].append(
        {"dcsGroupName": "ISOLATED", "topologyKey": "ISOLATED", "radioCandidates": []}
    )
    for role, name in [("Sam", "SAM"), ("Ewr", "EWR")]:
        data[role] = [
            {
                "dcsGroupName": name,
                "topologyKey": name,
                "radioCandidates": [
                    {"name": name, "distance": distance}
                    for name, distance in [
                        ("ISOLATED", 1),
                        ("A", 10),
                        ("B", 20),
                        ("C", 30),
                    ]
                ],
                "ConnectionNode": ["ISOLATED"],  # A stale initial link is not reused.
                "requiresPower": True,
                "PowerSource": ["P1", "P2"],
            }
        ]
    return data


@pytest.mark.parametrize("side", [1, 2])
def test_automatic_radio_uses_one_live_rooted_uplink_and_all_standbys(
    vm: Any, side: int
) -> None:
    data = automatic_data()
    data["Sam"][0]["PD"] = ["PD"]
    start(vm, data, side)
    vm.execute("""
        objects.PD={isExist=function() return true end,
            getUnits=function() return {{isExist=function() return true end,getLife=function() return 100 end}} end}
        pd=setmetatable({iads=iads,dcsName='PD',connectionNodes={}},SkynetIADSSamSite)
        cover(elements.EWR,elements.SAM)
        iads.topology:beginCycle()
        assert(iads.topology.radioParents.SAM=='A')
        assert(iads.topology.radioParents.EWR=='A')
        assert(iads.topology.radioParents.PD=='A')
        assert(iads.topology:canExchange(pd,elements.SAM))
        objects.A.live=false
        iads.topology:beginCycle()
        assert(iads.topology.radioParents.SAM=='B')
        assert(iads.topology.radioParents.PD=='B')
        assert(not elements.SAM:getAutonomousState())
        objects.B.live=false
        iads.topology:beginCycle()
        assert(iads.topology.radioParents.SAM=='C')
        assert(elements.SAM:hasActiveConnectionNode())
        objects.C.live=false
        iads.topology:beginCycle()
        assert(iads.topology.radioParents.SAM==nil)
        assert(not elements.SAM:hasActiveConnectionNode())
        assert(elements.SAM:getAutonomousState())
        objects.A.live=true
        iads.topology:beginCycle()
        assert(iads.topology.radioParents.SAM=='A')
        assert(not elements.SAM:getAutonomousState())
    """)


def test_automatic_power_never_rewires_to_a_third_station(vm: Any) -> None:
    start(vm, automatic_data())
    vm.execute("""
        objects.P1.live=false
        iads.topology:beginCycle()
        assert(elements.SAM:hasWorkingPowerSource())
        objects.P2.live=false
        iads.topology:beginCycle()
        assert(objects.P3.live)
        assert(not elements.SAM:hasWorkingPowerSource())
        assert(not elements.EWR:hasWorkingPowerSource())
        assert(not elements.SAM:isActive())
        objects.P2.live=true
        iads.topology:beginCycle()
        assert(elements.SAM:hasWorkingPowerSource())
    """)


def test_automatic_command_centres_share_the_component_and_reroute_on_loss(
    vm: Any,
) -> None:
    start(vm, automatic_data())
    vm.execute("""
        assert(iads.topology.roots.SAM.CC1 and iads.topology.roots.SAM.CC2)
        assert(iads.topology:canExchange(elements.CC1,elements.CC2))
        objects.CC1.live=false
        iads.topology:beginCycle()
        assert(not iads.topology.roots.SAM.CC1 and iads.topology.roots.SAM.CC2)
        assert(elements.SAM:hasActiveConnectionNode())
        assert(iads.topology:canExchange(elements.CC2,elements.EWR))
        objects.CC2.live=false
        iads.topology:beginCycle()
        assert(not elements.SAM:hasActiveConnectionNode())
    """)


def test_automatic_power_only_rows_never_relay_radio(vm: Any) -> None:
    data = automatic_data()
    data["Ewr"].append(
        {
            "dcsGroupName": "GPS",
            "powerOnly": True,
            "radioCandidates": [],
            "requiresPower": True,
            "PowerSource": ["P1", "P2"],
        }
    )
    start(vm, data)
    vm.execute("""
        objects.CC1.live=false; objects.CC2.live=false
        iads.topology:beginCycle()
        assert(elements.GPS:hasWorkingPowerSource())
        assert(iads.topology:connected(elements.GPS))
        assert(iads.topology.radioParents.GPS==nil)
        assert(not iads.topology:canExchange(elements.GPS,elements.SAM))
        objects.P1.live=false; objects.P2.live=false
        iads.topology:beginCycle()
        assert(not iads.topology:connected(elements.GPS))
    """)


def test_automatic_forest_is_recomputed_only_when_availability_changes(vm: Any) -> None:
    start(vm, automatic_data())
    vm.execute("""
        local original=iads.topology.selectRadio
        rebuilds=0
        function iads.topology:selectRadio(alive,powered)
            rebuilds=rebuilds+1
            return original(self,alive,powered)
        end
        for _=1,20 do
            iads.topology:beginCycle()
            iads.topology:canExchange(elements.SAM,elements.EWR)
        end
        assert(rebuilds==0)
        objects.A.live=false
        iads.topology:beginCycle()
        assert(rebuilds==1)
    """)


def test_multi_building_station_and_command_survive_partial_losses(vm: Any) -> None:
    data = automatic_data()
    data["PowerSource"][0]["staticMembers"] = ["P1", "P1_SECOND"]
    data["CommandCenter"][0]["staticMembers"] = ["CC1", "CC1_SECOND"]
    start(vm, data)
    vm.execute("""
        for _, name in ipairs({'P1_SECOND','CC1_SECOND'}) do
            local object={live=true,side=iads.topology.coalition}
            function object:isExist() return self.live end
            function object:getLife() return self.live and 100 or 0 end
            function object:getCoalition() return self.side end
            objects[name]=object
        end
        elements.CC1.isDestroyed=SkynetIADSAbstractElement.isDestroyed
        function elements.CC1:getDCSRepresentation() return objects.CC1 end
        objects.P1.live=false; objects.P2.live=false; objects.CC1.live=false
        objects.CC2.live=false
        iads.topology:beginCycle()
        assert(elements.SAM:hasWorkingPowerSource())
        assert(not elements.CC1:isDestroyed())
        assert(elements.SAM:hasActiveConnectionNode())
        objects.CC1_SECOND.live=false
        iads.topology:onEvent({initiator={getName=function() return 'CC1_SECOND object' end}})
        assert(elements.CC1:isDestroyed())
        assert(not elements.SAM:hasActiveConnectionNode())
        objects.P1_SECOND.live=false
        iads.topology:onEvent({initiator={getName=function() return 'P1_SECOND object' end}})
        assert(not elements.SAM:hasWorkingPowerSource())
        objects.CC1_SECOND.live=true; objects.P1_SECOND.live=true
        iads.topology:beginCycle()
        assert(elements.SAM:hasActiveConnectionNode())
        assert(elements.SAM:hasWorkingPowerSource())
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
        if entry.radio_candidates is not None:
            row["topologyKey"] = entry.topology_key
            row["radioCandidates"] = [
                {"name": name, "distance": distance}
                for name, distance in entry.radio_candidates
            ]
        if entry.power_only:
            row["powerOnly"] = True
        if entry.static_members:
            row["staticMembers"] = entry.static_members
        if entry.independent_comms:
            row["independentComms"] = True
        if entry.requires_power:
            row["requiresPower"] = True
        if entry.local_power_sources:
            row["localPowerSources"] = entry.local_power_sources
        result.setdefault(entry.iads_role.value, []).append(row)
    return result


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_exported_integrated_power_preserves_native_autonomy(
    vm: Any, side: Player
) -> None:
    network, objects = chain(side)
    sam, plant = objects[3], objects[5]
    unit = sam.groups[0].units[0]
    unit.type = AirDefence.x_2S6_Tunguska
    network.initialize_network(iter(objects))
    data = exported(network)
    row = data["Sam"][0]
    assert row["localPowerSources"] == [unit.unit_name]
    assert "PowerSource" not in row
    assert not row.get("independentComms", False)
    start(vm, data, 2 if side is Player.BLUE else 1)
    vm.globals().sam_name = row["dcsGroupName"]
    vm.globals().unit_name = unit.unit_name
    vm.globals().ewr_name = data["Ewr"][0]["dcsGroupName"]
    vm.globals().plant_name = plant.groups[0].units[0].unit_name
    vm.globals().cc_name = data["CommandCenter"][0]["dcsGroupName"]
    vm.execute("""
        objects[unit_name]=objects[sam_name]
        cover(elements[ewr_name],elements[sam_name])
        iads.topology:beginCycle()
        assert(elements[sam_name]:hasWorkingPowerSource())
        assert(not elements[sam_name]:getAutonomousState())
        objects[cc_name].live=false
        iads.topology:beginCycle()
        assert(elements[sam_name]:getAutonomousState())
        assert(elements[sam_name]:isActive())
        objects[cc_name].live=true
        iads.topology:beginCycle()
        assert(not elements[sam_name]:getAutonomousState())
        objects[plant_name].live=false
        iads.topology:beginCycle()
        assert(elements[sam_name]:hasWorkingPowerSource())
        assert(elements[sam_name]:getAutonomousState())
        assert(elements[sam_name]:isActive())
        objects[unit_name].live=false
        iads.topology:beginCycle()
        assert(not elements[sam_name]:hasWorkingPowerSource())
    """)
    plant.groups[0].units[0].alive = False
    network.update_tgo(plant, GameUpdateEvents())
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is IadsState.AUTONOMOUS


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


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_generated_failover_parents_power_and_shared_roots_match_python(
    vm: Any, side: Player
) -> None:
    objects = [
        site("CC1", IadsRole.COMMAND_CENTER, 0, side),
        site("CC2", IadsRole.COMMAND_CENTER, 30_000, side),
        site("A", IadsRole.CONNECTION_NODE, 1000, side),
        site("B", IadsRole.CONNECTION_NODE, 2000, side),
        site("C", IadsRole.CONNECTION_NODE, 3000, side),
        site("P1", IadsRole.POWER_SOURCE, 0, side),
        site("P2", IadsRole.POWER_SOURCE, 100, side),
        site("P3", IadsRole.POWER_SOURCE, 200, side),
        site("SAM", IadsRole.SAM, 0, side),
        site("EWR", IadsRole.EWR, 1, side),
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    start(vm, exported(network), 2 if side is Player.BLUE else 1)
    by_name = {obj.original_name: obj for obj in objects}
    names = {obj: SkynetNode.dcs_name_for_group(obj.groups[0]) for obj in objects}
    sequence: list[tuple[str | None, bool]] = [
        (None, True),
        ("A", False),
        ("B", False),
        ("C", False),
        ("A", True),
        ("CC1", False),
        ("CC2", False),
        ("P1", False),
        ("P2", False),
        ("P2", True),
        ("CC2", True),
        ("CC1", True),
        ("B", True),
    ]
    for changed, alive in sequence:
        if changed is not None:
            obj = by_name[changed]
            obj.groups[0].units[0].alive = alive
            network.update_tgo(obj, GameUpdateEvents())
            vm.globals().objects[names[obj]].live = alive
        runtime = vm.globals().iads.topology
        runtime.beginCycle(runtime)
        connectivity = network.state_map.connectivity
        assert connectivity is not None
        for obj, name in names.items():
            current = node(network, obj)
            parent = connectivity.radio_parent(current)
            assert runtime.radioParents[name] == (
                SkynetNode.dcs_name_for_group(parent) if parent is not None else None
            ), (changed, obj.original_name)
            roots = {
                names[n.group.ground_object] for n in connectivity.centres_for(current)
            }
            assert set(runtime.roots[name]) == roots, (changed, obj.original_name)
            assert runtime.powered[name] == connectivity.powered(current)
            element = vm.globals().elements[name]
            if element is not None:
                assert runtime.connected(runtime, element) == connectivity.connected(
                    current
                )
                for other in objects:
                    other_element = vm.globals().elements[names[other]]
                    if other_element is not None:
                        assert runtime.canExchange(
                            runtime, element, other_element
                        ) == connectivity.can_exchange(current, node(network, other)), (
                            changed,
                            obj.original_name,
                            other.original_name,
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
@pytest.mark.parametrize("integrated", [True, False])
def test_generated_miz_packages_the_graph_and_runtime_in_load_order(
    vm: Any, tmp_path: Path, advanced: bool, integrated: bool
) -> None:
    network, objects = chain()
    if integrated:
        objects[3].groups[0].units[0].type = AirDefence.x_2S6_Tunguska
    network.advanced_iads = advanced
    network.initialize_network(iter(objects))
    game: Any = SimpleNamespace(
        settings=Settings(),
        theater=SimpleNamespace(iads_network=network, controlpoints=[]),
        iads_considerate_culling=lambda _: False,
        skynet_culled=lambda _: False,
    )
    mission = Mission()
    game.settings.gps_jamming_enabled = False
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
        if integrated:
            assert data.RED.Sam[1].PowerSource is None
            assert (
                data.RED.Sam[1].localPowerSources[1]
                == objects[3].groups[0].units[0].unit_name
            )
        else:
            assert len(data.RED.Sam[1].PowerSource) == 1
        assert len(data.RED.ConnectionNode) == 2
        assert len(data.RED.CommandCenter) == 1
        assert len(data.RED.Sam[1].ConnectionNode) == 1
        assert len(data.RED.Sam[1].radioCandidates) == 1
        assert data.RED.Sam[1].radioCandidates[1].distance == 20000
        assert data.RED.Sam[1].topologyKey == "SAM"
    else:
        assert data.RED.Sam[1].requiresPower is None
        assert data.RED.ConnectionNode is None
        assert data.RED.CommandCenter is None
