"""Native avoidance task contracts; actual DCS manoeuvres need the probe missions."""

import unittest

import test_afac_marking
from test_contact_core import PLUGIN


class AfacNavigationTests(unittest.TestCase):
    def setUp(self):
        test_afac_marking.AfacMarkingTests.setUp(self)
        for name in ("afac-safety.lua", "afac-navigation.lua"):
            self.rt.execute((PLUGIN / name).read_text("utf-8"))
        self.rt.execute("""
        local meta=config.observers[1].afac
        meta.zone={radius=20000,points={{x=0,z=0}}}
        meta.navigation={speed=55,altitude=2000,altType='BARO',exitWaypoint=4,
          points={{x=-2000,z=0},{x=2000,z=0}}}
        config.afacAvoidance={}
        config.airDefenseThreats={{name='gun',groupName='red',coalition=1,typeName='ZSU_57_2',
          radius=7000,ceiling=4000,known=false}}
        observer.point={x=-15000,y=2000,z=0}
        function observer:getDesc() return {Hmax=9000} end
        function blue:getUnits()return {observer}end
        gun=unit('gun',red,'ZSU_57_2',0,0)
        enemyReads=0
        function gun:getPoint()enemyReads=enemyReads+1;return self.point end
        pushed={};popped=0;switches={};failPop=false
        function blue.controller:pushTask(task)pushed[#pushed+1]=task end
        function blue.controller:popTask()if failPop then error('pop failed')end;popped=popped+1 end
        function blue.controller:setCommand(command)switches[#switches+1]=command end
        function known()assert(fog:observe('red',2,gun.point,'test intelligence'))end
        function beginNavigation()nav=RealisticCAS.newAFACNavigation(fog,config)end
        function tick()now=now+1;nav:tick()end
        function finalOrbit(task)
          local points=task.params.task.params.route.points
          for _,action in ipairs(points[#points].task.params.tasks)do
            if action.id=='Orbit' then return action end
          end
          error('orbit missing')
        end
        """)

    def test_hidden_threats_are_not_read_and_do_not_change_routes(self):
        self.rt.execute("""
        beginNavigation();tick()
        assert(enemyReads==0 and #pushed==0 and #switches==0)
        known();tick()
        assert(enemyReads==1 and #pushed==1)
        assert(finalOrbit(pushed[1]).params.altitude==4500)
        """)

    def test_climb_uses_real_altitude_before_crossing_the_threat(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local first=finalOrbit(pushed[1]).params
        assert(first.point.x< -8000 and first.altitude==4500)
        assert(nav:clear('blue',{x=0,y=2000,z=0})==false)
        assert(nav:clear('blue',{x=0,y=4500,z=0})==true)
        local points=pushed[1].params.task.params.route.points
        assert(points[1].alt==2000)
        for index=2,#points do assert(points[index].alt==4500)end
        observer.point.y=4500;tick()
        assert(#pushed==2 and popped==1)
        assert(finalOrbit(pushed[2]).params.point.x==0)
        """)

    def test_cloud_ceiling_and_unknown_native_aircraft_limit_force_standoff(self):
        for change in (
            "config.afacAvoidance.clouds={base=2500,top=4000}",
            "function observer:getDesc()return {}end",
            "config.airDefenseThreats[1].ceiling=nil",
        ):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    change
                    + ";known();beginNavigation();tick();assert(finalOrbit(pushed[1]).params.altitude==2000)"
                )

    def test_blocked_zone_aborts_and_switches_to_original_exit(self):
        self.rt.execute("""
        config.observers[1].afac.zone.radius=6000
        observer.point.x=1000
        config.afacAvoidance.clouds={base=2500,top=4000}
        known();beginNavigation();tick()
        assert(RealisticCAS.afacAbort.blue and #pushed==0 and #switches==1)
        assert(switches[1].id=='SwitchWaypoint' and switches[1].params.goToWaypointIndex==4)
        assert(not nav:clear('blue',observer.point))
        tick();assert(#switches==1)
        """)

    def test_destroyed_or_expired_threat_resumes_original_task(self):
        for change in ("gun.life=0", "now=20"):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    "known();beginNavigation();tick();"
                    + change
                    + ";tick();assert(popped==1 and #pushed==1)"
                )

    def test_stop_condition_preserves_station_deadline_and_bingo(self):
        for change in ("now=601", "observer.fuel=0.1"):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    """
                known();beginNavigation();tick()
                expression=pushed[1].params.stopCondition.condition
                assert(not assert(loadstring('return '..expression))())
                """
                    + change
                    + """
                assert(assert(loadstring('return '..expression))())
                assert(RealisticCAS.afacNavigation.blue.finished)
                tick();assert(popped==0) -- The native wrapper has already finished.
                assert(#switches==1 and switches[1].params.goToWaypointIndex==4)
                assert(RealisticCAS.afacReturn.blue and not RealisticCAS.afacAbort.blue)
                assert(RealisticCAS.afacNavigation.blue.exitWaypoint==4)
                tick();assert(#switches==1)
                """
                )

    def test_cleanup_retries_without_replacing_original_mission(self):
        self.rt.execute("""
        known();beginNavigation();tick();failPop=true
        assert(not nav:stop() and not RealisticCAS.afacNavigation.blue.active)
        failPop=false;assert(nav:stop() and popped==1)
        """)

    def test_safe_climb_does_not_restart_when_the_aircraft_moves(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local first=finalOrbit(pushed[1]).params.point
        for index=1,8 do
          observer.point.x=-15000+index*300
          observer.point.z=index*20
          observer.point.y=2000+index*100
          tick()
          assert(#pushed==1 and popped==0)
        end
        observer.point.y=4500;known();tick()
        assert(#pushed==2 and finalOrbit(pushed[2]).params.point.x==0)
        """)

    def test_new_threat_invalidates_a_retained_climb(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local p=finalOrbit(pushed[1]).params.point
        gun.point.x=p.x;gun.point.z=p.y
        config.airDefenseThreats[1].ceiling=nil
        for index=1,5 do tick()end
        assert(#pushed>1 or RealisticCAS.afacAbort.blue)
        """)

    def test_native_waypoint_progress_is_revision_scoped(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local points=pushed[1].params.task.params.route.points
        local script=points[2].task.params.tasks[1].params.action.params.command
        assert(loadstring(script))()
        assert(RealisticCAS.afacNavigation.blue.nextPoint==2)
        observer.point.y=4500;tick()
        assert(RealisticCAS.afacNavigation.blue.nextPoint==1)
        assert(loadstring(script))()
        assert(RealisticCAS.afacNavigation.blue.nextPoint==1)
        """)

    def test_station_and_bingo_switch_exit_even_without_an_avoidance_task(self):
        for change in ("now=601", "observer.fuel=0.1"):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    "beginNavigation();tick();assert(#pushed==0);"
                    + change
                    + ";tick();assert(popped==0 and #switches==1);"
                    + "assert(switches[1].params.goToWaypointIndex==4);"
                    + "tick();assert(#switches==1 and #pushed==0)"
                )

    def test_departure_cleanup_retries_before_switching_the_original_route(self):
        self.rt.execute("""
        known();beginNavigation();tick();failPop=true;now=601;tick()
        assert(#switches==0 and RealisticCAS.afacReturn.blue)
        assert(not RealisticCAS.afacNavigation.blue.exitWaypoint)
        failPop=false;tick()
        assert(popped==1 and #switches==1)
        tick();assert(popped==1 and #switches==1)
        """)

    def test_exit_restores_unlimited_fuel_only_when_configured(self):
        self.rt.execute("""
        config.observers[1].afac.navigation.restoreUnlimitedFuel=true
        beginNavigation();now=601;tick()
        assert(#switches==2 and switches[1].id=='SetUnlimitedFuel' and switches[1].params.value)
        assert(switches[2].id=='SwitchWaypoint')
        tick();assert(#switches==2)
        """)

    def test_player_bingo_and_expiry_never_issue_exit_commands(self):
        self.rt.execute("""
        observer.player='Human';observer.fuel=0.1
        beginNavigation();now=601;tick()
        assert(#switches==0 and #pushed==0 and not RealisticCAS.afacReturn.blue)
        """)

    def test_returning_flight_stops_observing_and_removes_its_spots(self):
        self.rt.execute("""
        config.targets={};config.knownTargets={{name='gun',groupName='red'}}
        config.airDefenseThreats[1].known=true
        observer.point={x=-7000,y=4500,z=0}
        config.observers[1].afac.navigation.altitude=4500
        known();begin();advance(25)
        assert(#made>0 and not made[1].dead)
        RealisticCAS.afacStations.blue=now-600;advance(3)
        assert(RealisticCAS.afacReturn.blue=='station complete' and made[1].dead)
        assert(marker.coordinator:get('observer').state=='rtb')
        local count=#made;advance(15);assert(#made==count and #switches==1)
        """)

    def test_player_flights_are_never_steered_by_the_script(self):
        self.rt.execute("""
        observer.player='Human';known();beginNavigation();tick()
        assert(#pushed==0 and popped==0 and #switches==0)
        """)

    def test_shared_known_fixed_sam_does_not_require_fog_registration(self):
        self.rt.execute("""
        config.airDefenseThreats[1].known=true
        beginNavigation();tick()
        assert(red.hidden and enemyReads==1 and #pushed==1)
        """)

    def test_station_clock_does_not_restart_after_replanning(self):
        self.rt.execute("""
        RealisticCAS.afacStations.blue=0
        known();beginNavigation();tick()
        observer.point.y=4500;tick()
        assert(#pushed==2 and RealisticCAS.afacStations.blue==0)
        """)

    def test_unknown_ceiling_is_never_guessed_from_radius(self):
        self.rt.execute("""
        config.airDefenseThreats[1].ceiling=nil
        known();beginNavigation();tick()
        assert(not nav:clear('blue',{x=0,y=10000,z=0}))
        """)

    def test_known_sam_can_be_marked_without_discovery_or_fog_registration(self):
        self.rt.execute("""
        assert(fog:stop());fog=start({})
        config.targets={};config.knownTargets={{name='gun',groupName='red'}}
        config.airDefenseThreats[1].known=true
        observer.point={x=-7000,y=4500,z=0}
        config.observers[1].afac.navigation.altitude=4500
        begin();advance(25)
        assert(#made==1 and afac_marks[1].target=='gun' and not afac_discoveries)
        """)

    def test_known_danger_blocks_marking_and_warns_manual_flight(self):
        self.rt.execute("""
        observer.point={x=1000,y=2000,z=0};observer.player='Human'
        config.observers[1].allowPlayer=true
        known();begin();advance(25)
        assert(#made==0 and not afac_marks)
        local warned=false
        for _,m in ipairs(messages)do if m.text:find('not marking: known ZSU_57_2')then warned=true end end
        assert(warned and #pushed==0)
        """)

    def test_cloud_slab_blocks_marking_during_descent(self):
        self.rt.execute("""
        observer.player='Human';config.observers[1].allowPlayer=true
        config.targets={};config.knownTargets={{name='gun',groupName='red'}}
        config.airDefenseThreats[1].known=true
        observer.point={x=-7000,y=4500,z=0}
        config.afacAvoidance.clouds={base=2000,top=3000}
        known();begin();advance(25)
        assert(#made==0 and not afac_marks)
        observer.point.y=1500;observer.point.x=-9000;advance(10)
        assert(not RealisticCAS.afacAbort.blue and #made==1 and afac_marks[1].laser)
        """)
