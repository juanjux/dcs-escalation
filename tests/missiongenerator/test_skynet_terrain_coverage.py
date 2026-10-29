"""Exercise the production Skynet engine with controlled DCS terrain queries."""

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def vm() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("env={info=function() end}; mist={utils={}}")
    lua.execute(
        Path("resources/plugins/skynetiads/skynet-iads-compiled.lua").read_text(
            encoding="utf-8"
        )
    )
    lua.execute("""
        visible = true
        checks = 0
        land = {
            getHeight=function(point)
                assert(point.x == 100 and point.y == 200)
                return 700
            end,
            isVisible=function(from, to)
                checks=checks+1
                lastFrom=from; lastTo=to
                return visible
            end,
        }
        function radar(x,y,z,exists)
            return {
                isExist=function() return exists ~= false end,
                getDCSRepresentation=function()
                    return {getPosition=function() return {p={x=x,y=y,z=z}} end}
                end,
            }
        end
        function element(kind, radars)
            -- Skynet's constructors set this on each concrete radar class.
            kind.__index=kind
            local site=setmetatable({
                searchRadars=radars, trackingRadars={},
                parentRadars={}, childRadars={}, updates=0,
                iads={isCommandCenterUsable=function() return true end},
            },kind)
            function site:informChildrenOfStateChange() self.updates=self.updates+1 end
            function site:hasWorkingPowerSource() return true end
            function site:hasActiveConnectionNode() return true end
            function site:getActAsEW() return true end
            function site:isDestroyed() return false end
            function site:goLive() self.live=true end
            function site:goDark() self.live=false end
            return site
        end
        parent=element(SkynetIADSEWRadar,{radar(0,500,0)})
        child=element(SkynetIADSSamSite,{radar(100,900,200)})
    """)
    return lua


def test_clear_ground_cover_uses_radar_mast_and_terrain_relative_height(
    vm: Any,
) -> None:
    vm.execute("SkynetIADS:buildRadarAssociation(parent,child)")
    assert len(vm.globals().child.parentRadars) == 1
    assert len(vm.globals().parent.childRadars) == 1
    assert vm.globals().child.updates == 1
    assert vm.globals().lastFrom.y == 510
    assert vm.globals().lastTo.y == 700 + 3048
    assert vm.globals().lastTo.z == 200


def test_blocked_cover_adds_neither_half_of_the_link(vm: Any) -> None:
    vm.execute("visible=false; SkynetIADS:buildRadarAssociation(parent,child)")
    assert len(vm.globals().child.parentRadars) == 0
    assert len(vm.globals().parent.childRadars) == 0
    assert vm.globals().child.updates == 0


def test_awacs_keeps_range_only_cover_without_any_terrain_query(vm: Any) -> None:
    vm.execute("""
        parent=element(SkynetIADSAWACSRadar,{})
        land=nil
        SkynetIADS:buildRadarAssociation(parent,child)
    """)
    assert len(vm.globals().child.parentRadars) == 1
    assert vm.globals().checks == 0


def test_ewr_is_never_a_child_and_deferral_is_preserved(vm: Any) -> None:
    vm.execute("SkynetIADS:buildRadarAssociation(child,parent)")
    assert vm.globals().checks == 0
    vm.execute("SkynetIADS:buildRadarAssociation(parent,child,true)")
    assert len(vm.globals().child.parentRadars) == 1
    assert vm.globals().child.updates == 0


def test_any_live_search_or_tracking_radar_can_supply_cover(vm: Any) -> None:
    vm.execute("""
        parent.searchRadars={radar(0,0,0,false),radar(0,500,0)}
        parent.trackingRadars={radar(10,500,0)}
        child.searchRadars={radar(0,0,0,false)}
        child.trackingRadars={radar(100,900,200)}
        land.isVisible=function(from,to)
            checks=checks+1
            return from.x==10
        end
        SkynetIADS:buildRadarAssociation(parent,child)
    """)
    assert len(vm.globals().child.parentRadars) == 1
    assert vm.globals().checks == 2


def test_missing_live_radars_cannot_supply_cover(vm: Any) -> None:
    vm.execute("""
        parent.searchRadars={radar(0,0,0,false)}
        SkynetIADS:buildRadarAssociation(parent,child)
    """)
    assert len(vm.globals().child.parentRadars) == 0
    assert vm.globals().checks == 0


@pytest.mark.parametrize("visible", [True, False])
def test_autonomy_depends_on_actual_cover_not_nominal_range(
    vm: Any, visible: bool
) -> None:
    vm.globals().visible = visible
    vm.execute("""
        SkynetIADS:buildRadarAssociation(parent,child)
        SkynetIADSAbstractRadarElement.setToCorrectAutonomousState(child)
    """)
    assert vm.globals().child.isAutonomous is not visible
    assert vm.globals().child.live is not visible


def test_full_rebuild_discards_cover_when_terrain_blocks_it(vm: Any) -> None:
    vm.execute("""
        iads=setmetatable({},SkynetIADS)
        function iads:getSAMSites() return {child} end
        function iads:getEarlyWarningRadars() return {parent} end
        function iads:getAbstracRadarElements() return {parent,child} end
        function iads:addRadarsToCommandCenters() end
        function parent:isInRadarDetectionRangeOf(other) return true end
        function child:isInRadarDetectionRangeOf(other) return true end
        iads:buildRadarCoverage()
        assert(#child.parentRadars==1)
        visible=false
        iads:buildRadarCoverage()
    """)
    assert len(vm.globals().child.parentRadars) == 0
    assert len(vm.globals().parent.childRadars) == 0
    assert vm.globals().child.updates == 2


def test_terrain_does_not_extend_nominal_radar_range(vm: Any) -> None:
    vm.execute("""
        iads=setmetatable({},SkynetIADS)
        function iads:getAbstracRadarElements() return {parent,child} end
        function parent:isInRadarDetectionRangeOf(other) return false end
        function child:isInRadarDetectionRangeOf(other) return false end
        iads:buildRadarCoverageForAbstractRadarElement(child)
    """)
    assert len(vm.globals().child.parentRadars) == 0
    assert vm.globals().checks == 0


def test_autonomy_does_not_restore_a_battery_without_power(vm: Any) -> None:
    vm.execute("""
        visible=false
        function child:hasWorkingPowerSource() return false end
        SkynetIADS:buildRadarAssociation(parent,child)
        SkynetIADSAbstractRadarElement.setToCorrectAutonomousState(child)
    """)
    assert vm.globals().child.isAutonomous is True
    assert vm.globals().child.live is False
