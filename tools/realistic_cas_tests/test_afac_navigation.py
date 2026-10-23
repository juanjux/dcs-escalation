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
        meta.navigation={speed=55,altitude=2000,altType='BARO',searchWaypoint=2,exitWaypoint=4,
          points={{x=-2000,z=0},{x=2000,z=0}}}
        meta.navigation.route={}
        for index=1,5 do
          meta.navigation.route[index]={x=index*1000,y=0,alt=2000,speed=100,
            type='Turning Point',action='Turning Point',alt_type='BARO',ETA_locked=true,
            task={id='ComboTask',params={tasks={}}}}
        end
        meta.navigation.route[5].type='Land';meta.navigation.route[5].action='Landing'
        meta.navigation.route[5].airdromeId=12
        config.afacAvoidance={}
        config.airDefenseThreats={{name='gun',groupName='red',coalition=1,typeName='ZSU_57_2',
          radius=7000,ceiling=4000,known=false}}
        observer.point={x=-15000,y=2000,z=0}
        function observer:getDesc() return {Hmax=9000} end
        function blue:getUnits()return {observer}end
        gun=unit('gun',red,'ZSU_57_2',0,0)
        enemyReads=0
        function gun:getPoint()enemyReads=enemyReads+1;return self.point end
        assigned={};switches={};failSet=false
        function blue.controller:setTask(task)
          if failSet then error('set failed')end
          assigned[#assigned+1]=task
        end
        function blue.controller:pushTask()error('must replace the active native mission')end
        function blue.controller:popTask()error('must not pop the native task stack')end
        function blue.controller:setCommand(command)switches[#switches+1]=command end
        function known()assert(fog:observe('red',2,gun.point,'test intelligence'))end
        function beginNavigation()nav=RealisticCAS.newAFACNavigation(fog,config)end
        function tick()now=now+1;nav:tick()end
        function finalOrbit(task)
          for _,p in ipairs(task.params.route.points)do
            for _,action in ipairs(p.task.params.tasks)do
              if action.id=='ControlledTask' and action.params.task.id=='Orbit' then return action end
            end
          end
          error('orbit missing')
        end
        function orbit(task)return finalOrbit(task).params.task end
        function jump(task)
          return task.params.route.points[1].task.params.tasks[2].params.action.params.goToWaypointIndex
        end
        """)

    def test_hidden_threats_are_not_read_and_do_not_change_routes(self):
        self.rt.execute("""
        beginNavigation();tick()
        assert(enemyReads==0 and #assigned==0 and #switches==0)
        known();tick()
        assert(enemyReads==1 and #assigned==1)
        assert(assigned[1].id=='Mission' and assigned[1].params.airborne)
        assert(orbit(assigned[1]).params.altitude==4500)
        """)

    def test_climb_uses_real_altitude_before_crossing_the_threat(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local first=orbit(assigned[1]).params
        assert(first.point.x< -8000 and first.altitude==4500)
        assert(nav:clear('blue',{x=0,y=2000,z=0})==false)
        assert(nav:clear('blue',{x=0,y=4500,z=0})==true)
        local points=assigned[1].params.route.points
        assert(points[1].alt==2000)
        for index=2,3 do assert(points[index].alt==4500)end
        assert(points[5].airdromeId==12)
        observer.point.y=4500;tick()
        assert(#assigned==2)
        assert(orbit(assigned[2]).params.point.x==0)
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
                    + ";known();beginNavigation();tick();assert(orbit(assigned[1]).params.altitude==2000)"
                )

    def test_blocked_zone_aborts_and_switches_to_original_exit(self):
        self.rt.execute("""
        config.observers[1].afac.zone.radius=6000
        observer.point.x=1000
        config.afacAvoidance.clouds={base=2500,top=4000}
        known();beginNavigation();tick()
        assert(RealisticCAS.afacAbort.blue and #assigned==1 and #switches==0)
        assert(jump(assigned[1])==4)
        assert(not nav:clear('blue',observer.point))
        tick();assert(#assigned==1)
        """)

    def test_destroyed_or_expired_threat_resumes_original_task(self):
        for change in ("gun.life=0", "now=20"):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    "known();beginNavigation();tick();"
                    + change
                    + ";tick();assert(#assigned==2 and jump(assigned[2])==2)"
                )

    def test_stop_condition_preserves_station_deadline_and_bingo(self):
        for change in ("now=601", "observer.fuel=0.1"):
            with self.subTest(change=change):
                self.setUp()
                self.rt.execute(
                    """
                known();beginNavigation();tick()
                expression=finalOrbit(assigned[1]).params.stopCondition.condition
                assert(not assert(loadstring('return '..expression))())
                """
                    + change
                    + """
                assert(assert(loadstring('return '..expression))())
                assert(RealisticCAS.afacNavigation.blue.finished)
                tick();assert(#assigned==2 and jump(assigned[2])==4)
                assert(RealisticCAS.afacReturn.blue and not RealisticCAS.afacAbort.blue)
                assert(RealisticCAS.afacNavigation.blue.exitWaypoint==4)
                tick();assert(#assigned==2)
                """
                )

    def test_cleanup_retries_restoring_the_original_search_route(self):
        self.rt.execute("""
        known();beginNavigation();tick();failSet=true
        assert(not nav:stop() and not RealisticCAS.afacNavigation.blue.active)
        failSet=false;assert(nav:stop() and #assigned==2 and jump(assigned[2])==2)
        """)

    def test_safe_climb_does_not_restart_when_the_aircraft_moves(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        for index=1,8 do
          observer.point.x=-15000+index*300
          observer.point.z=index*20
          observer.point.y=2000+index*100
          tick()
          assert(#assigned==1)
        end
        observer.point.y=4500;known();tick()
        assert(#assigned==2 and orbit(assigned[2]).params.point.x==0)
        """)

    def test_new_threat_invalidates_a_retained_climb(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local p=orbit(assigned[1]).params.point
        gun.point.x=p.x;gun.point.z=p.y
        config.airDefenseThreats[1].ceiling=nil
        for index=1,5 do tick()end
        assert(#assigned>1 or RealisticCAS.afacAbort.blue)
        """)

    def test_native_waypoint_progress_is_revision_scoped(self):
        self.rt.execute("""
        known();beginNavigation();tick()
        local points=assigned[1].params.route.points
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
                    "beginNavigation();tick();assert(#assigned==0);"
                    + change
                    + ";tick();assert(#assigned==1 and jump(assigned[1])==4);"
                    + "tick();assert(#assigned==1 and #switches==0)"
                )

    def test_departure_cleanup_retries_before_switching_the_original_route(self):
        self.rt.execute("""
        known();beginNavigation();tick();failSet=true;now=601;tick()
        assert(#assigned==1 and RealisticCAS.afacReturn.blue)
        assert(not RealisticCAS.afacNavigation.blue.exitWaypoint)
        failSet=false;tick()
        assert(#assigned==2 and jump(assigned[2])==4)
        tick();assert(#assigned==2)
        """)

    def test_exit_restores_unlimited_fuel_only_when_configured(self):
        self.rt.execute("""
        config.observers[1].afac.navigation.restoreUnlimitedFuel=true
        beginNavigation();now=601;tick()
        assert(#switches==1 and switches[1].id=='SetUnlimitedFuel' and switches[1].params.value)
        assert(#assigned==1 and jump(assigned[1])==4)
        tick();assert(#switches==1 and #assigned==1)
        """)

    def test_player_bingo_and_expiry_never_issue_exit_commands(self):
        self.rt.execute("""
        observer.player='Human';observer.fuel=0.1
        beginNavigation();now=601;tick()
        assert(#switches==0 and #assigned==0 and not RealisticCAS.afacReturn.blue)
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
        local count=#made;advance(15);assert(#made==count and #assigned==1)
        """)

    def test_player_flights_are_never_steered_by_the_script(self):
        self.rt.execute("""
        observer.player='Human';known();beginNavigation();tick()
        assert(#assigned==0 and #switches==0)
        """)

    def test_human_takeover_cancels_ownership_without_replacing_the_route(self):
        self.rt.execute("""
        known();beginNavigation();tick();assert(#assigned==1)
        observer.player='Human';tick()
        assert(#assigned==1 and not RealisticCAS.afacNavigation.blue.active)
        assert(nav:stop() and #assigned==1)
        """)

    def test_route_replacement_preserves_carrier_links_tasks_and_original_indices(self):
        self.rt.execute("""
        local original=config.observers[1].afac.navigation.route
        original[4].alt_type='RADIO'
        original[4].task.params.tasks={{number=1,id='WrappedAction',
          params={action={id='Script',params={command='recovery_flag=true'}}}}}
        original[5].airdromeId=nil;original[5].helipadId=44;original[5].linkUnit=99
        known();beginNavigation();tick()
        local points=assigned[1].params.route.points
        assert(points[4].alt_type=='RADIO' and points[5].helipadId==44 and points[5].linkUnit==99)
        assert(points[4].task.params.tasks[1].params.action.params.command=='recovery_flag=true')
        assert(original[2].alt==2000 and original[4].ETA_locked)
        now=601;tick();points=assigned[2].params.route.points
        assert(jump(assigned[2])==4 and #points==#original)
        assert(points[5].linkUnit==99 and points[5].helipadId==44 and points[5].type=='Land')
        for index=1,3 do
          for _,t in ipairs(points[index].task.params.tasks)do assert(t.id~='ControlledTask')end
        end
        assert(not points[4].ETA_locked and original[4].ETA_locked)
        """)

    def test_recovery_route_activation_script_compiles_without_touching_patrols(self):
        self.rt.execute("""
        beginNavigation();now=601;tick()
        local actions=assigned[1].params.route.points[1].task.params.tasks
        assert(loadstring(actions[1].params.action.params.command))()
        assert(actions[2].params.action.id=='SwitchWaypoint' and jump(assigned[1])==4)
        assert(not RealisticCAS.afacStations.blue or RealisticCAS.afacStations.blue==0)
        """)

    def test_native_landing_speed_zero_does_not_stop_the_airborne_return_prefix(self):
        self.rt.execute("""
        local n=config.observers[1].afac.navigation
        n.exitWaypoint=5;n.route[5].speed=0;n.route[5].alt=0
        beginNavigation();now=601;tick()
        local points=assigned[1].params.route.points
        assert(jump(assigned[1])==5 and points[5].speed==0 and points[5].airdromeId==12)
        for index=1,4 do assert(points[index].speed==100 and points[index].alt==observer.point.y)end
        """)

    def test_minimal_original_patrol_has_a_safe_direct_approach_and_keeps_its_exit(
        self,
    ):
        self.rt.execute("""
        local n=config.observers[1].afac.navigation
        n.searchWaypoint=1;n.exitWaypoint=3
        known();beginNavigation();tick()
        assert(#assigned==1 and #assigned[1].params.route.points==#n.route)
        assert(assigned[1].params.route.points[3].x==n.route[3].x)
        assert(orbit(assigned[1]).params.altitude==4500)
        """)

    def test_shared_known_fixed_sam_does_not_require_fog_registration(self):
        self.rt.execute("""
        config.airDefenseThreats[1].known=true
        beginNavigation();tick()
        assert(red.hidden and enemyReads==1 and #assigned==1)
        """)

    def test_station_clock_does_not_restart_after_replanning(self):
        self.rt.execute("""
        RealisticCAS.afacStations.blue=0
        known();beginNavigation();tick()
        observer.point.y=4500;tick()
        assert(#assigned==2 and RealisticCAS.afacStations.blue==0)
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
        assert(warned and #assigned==0)
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
