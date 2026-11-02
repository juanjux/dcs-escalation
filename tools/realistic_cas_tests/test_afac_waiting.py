"""Blocked work areas stay recoverable until safe entry or BINGO fuel."""

import unittest

import test_afac_navigation


class AfacWaitingTests(unittest.TestCase):
    def setUp(self):
        test_afac_navigation.AfacNavigationTests.setUp(self)
        self.rt.execute("""
        function waitingSetup()
          config.observers[1].afac.zone.radius=6000
          config.afacAvoidance.clouds={base=2500,top=4000}
          config.airDefenseThreats[1].known=true
          RealisticCAS.afacStations={}
        end
        function isWaiting()
          local s=RealisticCAS.afacNavigation.blue
          return s and s.active and s.waiting==true
        end
        function bingoOption(task)
          for _,t in ipairs(task.params.route.points[1].task.params.tasks)do
            local a=t.params and t.params.action
            if a and a.id=='Option'and a.params.name==6 then return a.params.value end
          end
        end
        """)

    def test_blocked_work_area_holds_without_starting_station_or_return(self):
        self.rt.execute("""
        waitingSetup();beginNavigation();tick()
        assert(#assigned==1 and isWaiting())
        assert(not RealisticCAS.afacAbort.blue and not RealisticCAS.afacReturn.blue)
        assert(not RealisticCAS.afacStations.blue)
        local hold=orbit(assigned[1]).params
        assert(hold.altitude==observer.point.y and hold.point.x==observer.point.x)
        assert(bingoOption(assigned[1])==false)
        assert(#switches==1 and switches[1].id=='SetUnlimitedFuel'and switches[1].params.value==false)
        local expression=finalOrbit(assigned[1]).params.stopCondition.condition
        assert(assert(loadstring(expression))()==false)
        now=2000;tick()
        assert(#assigned==1 and not RealisticCAS.afacReturn.blue)
        assert(assert(loadstring(expression))()==false)
        """)

    def test_destroyed_threat_resumes_original_search_not_return_route(self):
        self.rt.execute("""
        waitingSetup();beginNavigation();tick()
        local previous=finalOrbit(assigned[1]).params.stopCondition.condition
        gun.life=0;now=10;tick()
        assert(#assigned==2 and jump(assigned[2])==2 and not isWaiting())
        assert(not RealisticCAS.afacAbort.blue and not RealisticCAS.afacReturn.blue)
        assert(not RealisticCAS.afacStations.blue)
        assert(assert(loadstring(previous))()==true)
        assert(bingoOption(assigned[2])==true)
        assert(assigned[2].params.route.points[5].airdromeId==12)
        """)

    def test_power_loss_and_cloud_clearance_each_allow_mission_to_continue(self):
        for change in (
            "dcsRetribution={iadsHasWorkingPower=function()return false end}",
            "config.afacAvoidance.clouds=nil;observer.point.y=4500",
        ):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    "waitingSetup();beginNavigation();tick();assert(isWaiting());"
                    + change
                    + ";now=10;tick();assert(#assigned==2 and not isWaiting());"
                    "assert(not RealisticCAS.afacAbort.blue and not RealisticCAS.afacReturn.blue)"
                )

    def test_bingo_while_waiting_preserves_original_recovery(self):
        self.rt.execute("""
        waitingSetup();config.observers[1].afac.navigation.restoreUnlimitedFuel=true
        beginNavigation();tick()
        local expression=finalOrbit(assigned[1]).params.stopCondition.condition
        observer.fuel=0.2
        assert(assert(loadstring(expression))()==true)
        tick();assert(#assigned==2 and jump(assigned[2])==4 and not isWaiting())
        assert(RealisticCAS.afacReturn.blue=='BINGO fuel'and not RealisticCAS.afacAbort.blue)
        assert(switches[2].id=='SetUnlimitedFuel'and switches[2].params.value)
        local landing=assigned[2].params.route.points[5]
        assert(landing.type=='Land'and landing.airdromeId==12)
        tick();assert(#assigned==2)
        """)

    def test_existing_station_deadline_is_not_reset_by_waiting(self):
        self.rt.execute("""
        waitingSetup();RealisticCAS.afacStations.blue=0
        beginNavigation();tick();assert(isWaiting())
        now=601;tick()
        assert(RealisticCAS.afacReturn.blue=='station complete'and #assigned==2)
        assert(RealisticCAS.afacStations.blue==0)
        """)

    def test_waiting_does_not_restart_the_orbit_or_repeat_notices(self):
        self.rt.execute("""
        waitingSetup();beginNavigation();tick()
        local count=#messages
        observer.point.z=30
        for i=1,40 do tick()end
        assert(isWaiting()and #assigned==1 and #messages==count and #switches==1)
        """)

    def test_waiting_stops_discovery_and_cleans_existing_marks(self):
        self.rt.execute("""
        observer.point.x=0;config.airDefenseThreats={};begin();advance(25)
        assert(#made>0 and not made[1].dead)
        RealisticCAS.afacNavigation.blue={active=true,waiting=true}
        local count=#made;advance(10)
        assert(made[1].dead and #made==count)
        local state=marker.coordinator:get('observer')
        assert(state.state~='mark'and state.state~='rtb')
        """)

    def test_waiting_prevents_discovery_even_if_station_clock_and_zone_allow_it(self):
        self.rt.execute("""
        observer.point.x=0;config.airDefenseThreats={}
        RealisticCAS.afacNavigation={blue={active=true,waiting=true}}
        begin();advance(40)
        assert(red.hidden and not afac_discoveries and #made==0)
        RealisticCAS.afacNavigation.blue.waiting=false
        advance(40);assert(not red.hidden and #afac_discoveries==1 and #made>0)
        """)

    def test_human_takeover_never_gets_waiting_or_return_commands(self):
        self.rt.execute("""
        waitingSetup();beginNavigation();tick()
        observer.player='Human';observer.fuel=0.1
        tick();assert(#assigned==1 and #switches==1)
        assert(not RealisticCAS.afacReturn.blue and not RealisticCAS.afacNavigation.blue.active)
        """)

    def test_no_safe_waiting_point_preserves_emergency_return_fallback(self):
        self.rt.execute("""
        waitingSetup()
        function land.getHeight()return 1999 end
        beginNavigation();tick()
        assert(RealisticCAS.afacAbort.blue and RealisticCAS.afacReturn.blue)
        assert(not isWaiting())
        """)

    def test_unknown_enemy_is_not_read_while_waiting(self):
        self.rt.execute("""
        waitingSetup()
        config.airDefenseThreats[2]={name='hidden',groupName='unknown',coalition=1,
          typeName='ZSU_57_2',known=false,radius=20000}
        local hidden=unit('hidden',red,'ZSU_57_2',-15000,0)
        function hidden:getPoint()error('must not query unknown enemy')end
        beginNavigation();tick()
        for i=1,20 do tick()end
        assert(isWaiting()and not RealisticCAS.afacAbort.blue)
        """)
