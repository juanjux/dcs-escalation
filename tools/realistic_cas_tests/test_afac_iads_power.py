"""AFAC navigation against the production Skynet power and configuration code."""

import unittest

import test_afac_navigation
from test_contact_core import PLUGIN


class AfacIadsPowerTests(unittest.TestCase):
    def setUp(self):
        test_afac_navigation.AfacNavigationTests.setUp(self)
        skynet = PLUGIN.parent / "skynetiads"
        self.rt.execute("mist=mist or {};mist.utils=mist.utils or {}")
        self.rt.execute((skynet / "skynet-iads-compiled.lua").read_text("utf-8"))
        self.rt.execute("""
        plants={}
        function plant(name,alive)
          local p={alive=alive}
          function p:isExist()return self.alive end
          plants[name..' object']=p;return p
        end
        primary=plant('primary',false);backup=plant('backup',false)
        StaticObject={getByName=function(name)return plants[name]end}
        iads={eventElements={},activated=0}
        function iads:getDebugSettings()return {}end
        function iads:activate()self.activated=self.activated+1 end
        function iads:addSAMSite(name)return sites[name]end
        function site()
          SkynetIADSAbstractRadarElement.__index=SkynetIADSAbstractRadarElement
          local s=setmetatable({powerSources={},connectionNodes={},pointDefences={},
            iads=iads,aiState=false},SkynetIADSAbstractRadarElement)
          -- Native event registration and child updates are outside this fixture.
          function s:informChildrenOfStateChange()end
          return s
        end
        sites={red=site(),pd=site(),blueSam=site(),autonomous=site()}
        function SkynetIADS:create()return iads end
        dcsRetribution={plugins={skynetiads={createRedIADS=true,createBlueIADS=true}},
          IADS={RED={Sam={
            {dcsGroupName='red',PowerSource={'primary','backup'},PD={'pd','unsupported'}},
            {dcsGroupName='unsupported'},
            {dcsGroupName='autonomous'},
          }},BLUE={Sam={{dcsGroupName='blueSam'}}}}}
        function fixedThreat()
          config.airDefenseThreats[1].known=true
          config.airDefenseThreats[1].initialPoint={x=0,z=0}
        end
        """)
        self.config_source = (skynet / "skynetiads-config.lua").read_text("utf-8")
        self.rt.execute(self.config_source)

    def test_bridge_uses_live_power_for_both_coalitions_and_separate_point_defence(
        self,
    ):
        self.rt.execute("""
        local query=dcsRetribution.iadsHasWorkingPower
        assert(iads.activated==2)
        assert(query('red')==false)
        assert(query('pd')==true and sites.pd:getIsAPointDefence())
        assert(query('blueSam')==true and query('autonomous')==true)
        assert(query('unsupported')==nil and query('unmanaged')==nil)
        backup.alive=true;assert(query('red')==true)
        backup.alive=false;assert(query('red')==false)
        primary.alive=true;assert(query('red')==true)
        assert(#sites.red:getPowerSources()==2)
        assert(#sites.pd:getPowerSources()==0)
        """)

    def test_unpowered_long_range_sam_does_not_force_rtb(self):
        self.rt.execute("""
        fixedThreat()
        config.airDefenseThreats[1].radius=150000
        config.airDefenseThreats[1].ceiling=30000
        beginNavigation();tick()
        for i=1,15 do tick()end
        assert(#assigned==0 and not RealisticCAS.afacReturn.blue)
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        """)

    def test_initial_known_threat_and_observation_use_power_before_first_tick(self):
        self.rt.execute("""
        fixedThreat();beginNavigation()
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        nav:observe({name='gun',groupName='red',typeName='ZSU_57_2',side=1,
          point={x=0,y=1,z=0}})
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        primary.alive=true
        assert(not nav:clear('blue',{x=0,y=2000,z=0}))
        """)

    def test_powered_silent_battery_remains_a_threat(self):
        self.rt.execute("""
        primary.alive=true
        assert(sites.red.aiState==false)
        fixedThreat();beginNavigation();tick()
        assert(#assigned==1 and orbit(assigned[1]).params.altitude==4500)
        assert(not nav:clear('blue',{x=0,y=2000,z=0}))
        """)

    def test_power_loss_and_restoration_replan_without_losing_the_site(self):
        self.rt.execute("""
        primary.alive=true;fixedThreat();beginNavigation();tick()
        assert(#assigned==1 and RealisticCAS.afacNavigation.blue.active)
        primary.alive=false
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        tick();assert(#assigned==2 and not RealisticCAS.afacNavigation.blue.active)
        primary.alive=true;tick()
        assert(#assigned==3 and RealisticCAS.afacNavigation.blue.active)
        """)

    def test_parent_power_loss_does_not_disable_independent_point_defence(self):
        self.rt.execute("""
        fixedThreat()
        config.airDefenseThreats[1].radius=150000
        config.airDefenseThreats[1].ceiling=30000
        local pd=group('pd',41,1,2)
        unit('pd-gun',pd,'ZSU_57_2',0,0)
        config.airDefenseThreats[2]={name='pd-gun',groupName='pd',typeName='ZSU_57_2',
          coalition=1,radius=7000,ceiling=4000,known=true,initialPoint={x=0,z=0}}
        beginNavigation();tick()
        assert(#assigned==1 and not RealisticCAS.afacReturn.blue)
        assert(orbit(assigned[1]).params.altitude==4500)
        assert(not nav:clear('blue',{x=0,y=2000,z=0}))
        assert(nav:clear('blue',{x=30000,y=2000,z=0}))
        """)

    def test_recovery_ignores_unpowered_rings_in_both_candidate_passes(self):
        self.rt.execute("""
        local n=config.observers[1].afac.navigation
        n.route[4].x=25000;observer.point.x=-20000
        fixedThreat();beginNavigation();now=601;tick()
        assert(#assigned==1 and jump(assigned[1])==4)
        assert(RealisticCAS.afacReturn.blue=='station complete')
        primary.alive=true;tick()
        assert(#assigned==2 and jump(assigned[2])<4)
        primary.alive=false;tick()
        -- The existing detour is still safe; no route replacement is needed.
        assert(#assigned==2)
        """)

    def test_unpowered_battery_no_longer_blocks_a_recovery_hold(self):
        self.rt.execute("""
        local n=config.observers[1].afac.navigation
        n.exitWaypoint=5;n.route[5].x=0;n.route[5].alt=0;n.route[5].speed=0
        observer.point.x=-20000;primary.alive=true
        fixedThreat();beginNavigation();now=601;tick()
        assert(#assigned==1 and finalOrbit(assigned[1]))
        primary.alive=false
        for i=1,6 do tick()end
        assert(#assigned==2 and jump(assigned[2])==5)
        assert(RealisticCAS.afacReturn.blue=='station complete')
        """)

    def test_unknown_contacts_never_query_power_or_position(self):
        self.rt.execute("""
        powerReads=0
        dcsRetribution.iadsHasWorkingPower=function()
          powerReads=powerReads+1;return false
        end
        function gun:getName()return 'gun'end
        beginNavigation();nav:fireEvent(gun);tick()
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        assert(powerReads==0 and enemyReads==0 and #assigned==0)
        """)

    def test_unavailable_power_information_does_not_hide_known_threats(self):
        for change in (
            "dcsRetribution=nil",
            "dcsRetribution.iadsHasWorkingPower=nil",
            "dcsRetribution.iadsHasWorkingPower=function()return nil end",
            "dcsRetribution.iadsHasWorkingPower=function()error('unavailable')end",
        ):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    change
                    + ";fixedThreat();beginNavigation();tick();assert(#assigned==1)"
                )

    def test_disabled_network_does_not_report_unpowered_sites(self):
        self.rt.execute("""
        dcsRetribution.plugins.skynetiads.createRedIADS=false
        dcsRetribution.plugins.skynetiads.createBlueIADS=false
        """)
        self.rt.execute(self.config_source)
        self.rt.execute("""
        assert(dcsRetribution.iadsHasWorkingPower('red')==nil)
        fixedThreat();beginNavigation();tick();assert(#assigned==1)
        """)

    def test_actual_known_fire_temporarily_overrides_conflicting_power_state(self):
        self.rt.execute("""
        fixedThreat();beginNavigation();tick();assert(#assigned==0)
        function gun:getName()return 'gun'end
        nav:fireEvent(gun);tick()
        assert(#assigned==1 and not nav:clear('blue',{x=0,y=2000,z=0}))
        now=now+61;tick()
        assert(nav:clear('blue',{x=0,y=2000,z=0}))
        assert(#assigned==2 and not RealisticCAS.afacNavigation.blue.active)
        """)
