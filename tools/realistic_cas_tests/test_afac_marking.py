"""Native AFAC adapter contracts with fake spots, not DCS weapon acceptance."""

import unittest

import test_afac_search
from test_contact_core import PLUGIN


class AfacMarkingTests(unittest.TestCase):
    def setUp(self):
        test_afac_search.AfacSearchTests.setUp(self)
        for name in ("afac.lua", "afac-dcs.lua", "bootstrap.lua"):
            self.rt.execute((PLUGIN / name).read_text("utf-8"))
        self.rt.execute("""
        config.afacMarking={markSeconds=300,messageSeconds=15,laserCode=1688,coordinateFormat=0}
        local meta=config.observers[1]
        meta.coalition=2;meta.equipment.laser=true;meta.equipment.irPointer=true
        meta.afac.smokeRounds=2
        function observer:getName() return 'observer' end
        function observer:getCallsign() return 'Chevy1' end
        coord={LOtoLL=function()return 41.5,42.25 end,
          LLtoMGRS=function()return {UTMZone='38T',MGRSDigraph='KM',Easting=12345,Northing=67890} end}
        made={};smokes={};failIR=false;failStop=false;failUpdate=false;failLaser=false
        function spot(source,offset,point,code)
          local h={source=source,point=point,code=code,dead=false,updates=0}
          function h:destroy() if failStop then error('destroy failed') end;self.dead=true end
          function h:setPoint(p) if failUpdate then error('update failed') end;self.point=p;self.updates=self.updates+1 end
          made[#made+1]=h;return h
        end
        Spot={createLaser=function(...)if failLaser then error('laser failed')end;return spot(...)end,
          createInfraRed=function(...)if failIR then error('IR failed')end;return spot(...)end}
        trigger.smokeColor={Green=0,Red=1,White=2,Orange=3,Blue=4}
        trigger.action.smoke=function(p,color)smokes[#smokes+1]={point=p,color=color}end
        function advance(seconds)
          local untilTime=now+seconds
          while now<untilTime do run(1) end
        end
        function begin()
          detector=RealisticCAS.startDetection(fog,config)
          marker=detector.afacMarking
          assert(marker)
        end
        function colourMarker(entries)
          config.observers={}
          for _,entry in ipairs(entries)do
            unit(entry.id,blue,'FA-18C_hornet',0,1000)
            config.observers[#config.observers+1]={name=entry.id,coalition=entry.side or 2,
              typeName='FA-18C_hornet',category='air',
              equipment={laser=false,irPointer=false},afac={smokeRounds=entry.rounds or 2}}
          end
          marker=RealisticCAS.newAFACMarking(fog,config,{})
        end
        function smokeFor(id,side)
          marker.coordinator:step(id,{alive=true,fuel=0.5,onStation=true,
            contacts={{id='target-'..id,group='group-'..id,side=3-(side or 2),alive=true,
              observed=true,revealed=true,safe=true,inZone=true,point={x=5000,y=0,z=0}}}})
        end
        """)

    def test_discovery_creates_laser_smoke_and_separate_credit(self):
        self.rt.execute("""
        begin();advance(25)
        assert(#made==1 and made[1].source==observer and made[1].code==1688)
        assert(#smokes==1 and smokes[1].point.y==0 and smokes[1].color==trigger.smokeColor.Green)
        assert(#afac_discoveries==1 and #afac_marks==1)
        assert(afac_marks[1].laser and afac_marks[1].smoke and not afac_marks[1].infrared)
        assert(marker.coordinator:get('observer').state=='mark')
        assert(messages[#messages].side==2 and messages[#messages].text:find('Chevy1'))
        assert(messages[#messages].text:find('T%-72B') and messages[#messages].text:find('1688'))
        assert(messages[#messages].text:find('green smoke',1,true))
        """)

    def test_campaign_contact_switch_controls_discovery_but_keeps_marking_reports(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.setUp()
                self.rt.globals().reports_enabled = enabled
                self.rt.execute("""
                assert(fog:stop())
                fog=assert(RealisticCAS.start({enabled=true,ttl=600,
                  targets={{name='red',originalInvisible=false}},contactReports=reports_enabled,
                  contactReportSeconds=27,afacObservers={observer=true}}))
                config.contactReports=reports_enabled
                begin();advance(25)
                local found,lasing=0,0
                for _,m in ipairs(messages)do
                  assert(m.side==2)
                  if m.text:find(' found ',1,true)then
                    found=found+1;assert(m.text:find('JTAC Chevy1',1,true) and m.seconds==27)
                  end
                  if m.text:find('lasing',1,true)then lasing=lasing+1 end
                end
                assert(found==(reports_enabled and 1 or 0))
                assert(lasing>0 and #made>0 and #afac_discoveries==1 and #afac_marks==1)
                """)

    def test_night_includes_ir_and_actual_moving_target_updates(self):
        self.rt.execute("""
        e.light=0;begin();advance(25)
        assert(#made==2 and afac_marks[1].infrared)
        target.point.x=5300;advance(2)
        assert(made[1].point.x==5300 and made[2].point.x==5300)
        assert(made[1].updates>0)
        """)

    def test_first_four_smokers_get_distinct_nonwhite_colours_before_reuse(self):
        self.rt.execute("""
        colourMarker({{id='e'},{id='d'},{id='c'},{id='b'},{id='a'},
          {id='a-drone',rounds=0}})
        for _,id in ipairs({'a','b','c','d','e'})do smokeFor(id)end
        assert(#smokes==5)
        local expected={0,1,3,4,0}
        for index,value in ipairs(expected)do
          assert(smokes[index].color==value and value~=trigger.smokeColor.White)
        end
        assert(marker.coordinator:get('a-drone').smokeRounds==0)
        assert(marker.coordinator:get('a').smokeRounds==1)
        """)

    def test_colour_assignment_is_stable_when_observer_metadata_is_reordered(self):
        self.rt.execute("""
        colourMarker({{id='zulu'},{id='alpha'}})
        smokeFor('alpha');smokeFor('zulu')
        local first,second=smokes[1].color,smokes[2].color
        assert(first==trigger.smokeColor.Green and second==trigger.smokeColor.Red)
        assert(marker:stop());smokes={}
        colourMarker({{id='alpha'},{id='zulu'}})
        smokeFor('alpha');smokeFor('zulu')
        assert(smokes[1].color==first and smokes[2].color==second)
        """)

    def test_each_coalition_has_its_own_colour_cycle_and_reports_the_colour(self):
        self.rt.execute("""
        colourMarker({{id='red-z',side=1},{id='blue-z'},
          {id='red-a',side=1},{id='blue-a'}})
        smokeFor('red-a',1);smokeFor('blue-a')
        smokeFor('red-z',1);smokeFor('blue-z')
        assert(smokes[1].color==0 and smokes[2].color==0)
        assert(smokes[3].color==1 and smokes[4].color==1)
        assert(messages[1].side==1 and messages[1].text:find('green smoke',1,true))
        assert(messages[2].side==2 and messages[2].text:find('green smoke',1,true))
        assert(messages[3].side==1 and messages[3].text:find('red smoke',1,true))
        assert(messages[4].side==2 and messages[4].text:find('red smoke',1,true))
        """)

    def test_lost_los_and_reacquisition_do_not_farm_experience(self):
        self.rt.execute("""
        begin();advance(25)
        land.isVisible=function()return false end;advance(2)
        assert(made[1].dead and marker.coordinator:get('observer').state=='search')
        land.isVisible=function()return true end;advance(10)
        assert(#made>=2 and #afac_marks==1 and #smokes==2)
        assert(smokes[1].color==trigger.smokeColor.Green and smokes[2].color==smokes[1].color)
        land.isVisible=function()return false end;advance(2)
        land.isVisible=function()return true end;advance(10)
        assert(#smokes==2 and marker.coordinator:get('observer').smokeRounds==0)
        """)

    def test_partial_native_failure_cleans_laser_and_pays_nothing(self):
        self.rt.execute("""
        e.light=0;failIR=true;begin();advance(25)
        assert(#made>0 and not afac_marks and #smokes==0)
        for _,h in ipairs(made)do assert(h.dead)end
        assert(marker.coordinator:get('observer').state=='search')
        """)

    def test_failed_destruction_keeps_reservation_and_stop_is_retryable(self):
        self.rt.execute("""
        begin();advance(25);failStop=true
        assert(not detector:stop())
        assert(marker.coordinator:get('observer').state=='stopping' and not made[1].dead)
        failStop=false;assert(detector:stop());assert(made[1].dead)
        """)

    def test_smoke_only_failures_pay_nothing_and_native_shots_debit_inventory(self):
        self.rt.execute("""
        config.observers[1].equipment.laser=false
        config.observers[1].equipment.irPointer=false
        begin();marker:shot('observer');assert(marker.coordinator:get('observer').smokeRounds==1)
        trigger.action.smoke=function()error('smoke failed')end
        advance(25)
        assert(not afac_marks and #made==0 and marker.coordinator:get('observer').smokeRounds==0)
        """)

    def test_hidden_or_outside_zone_targets_never_get_marked(self):
        for modification in (
            "target.point.x=11000",
            "land.isVisible=function()return false end",
        ):
            with self.subTest(modification=modification):
                self.setUp()
                self.rt.execute(
                    modification
                    + ";begin();advance(30);assert(#made==0 and not afac_marks)"
                )

    def test_bingo_loss_zone_exit_and_station_expiry_stop_spots(self):
        for modification in (
            "observer.fuel=0.1",
            "observer.life=0",
            "observer.point.x=-11000",
            "RealisticCAS.afacStations.blue=-600",
        ):
            with self.subTest(modification=modification):
                self.setUp()
                self.rt.execute(
                    "begin();advance(25);"
                    + modification
                    + ";advance(2);assert(made[1].dead)"
                )

    def test_late_activation_waits_in_transit_not_lost(self):
        self.rt.execute("""
        observer.exists=false;begin();advance(15)
        assert(marker.coordinator:get('observer').state=='transit')
        observer.exists=true;advance(25)
        assert(#made==1 and afac_marks[1].laser)
        """)

    def test_native_station_clock_sets_terminal_rtb(self):
        self.rt.execute("""
        begin();advance(25)
        RealisticCAS.afacStations.blue=-600;advance(2)
        assert(made[1].dead and marker.coordinator:get('observer').state=='rtb')
        RealisticCAS.afacStations.blue=now;advance(10)
        assert(#made==1)
        """)

    def test_squadron_members_reserve_a_whole_group_not_each_vehicle(self):
        self.rt.execute("""
        local other=unit('wingman',blue,'FA-18C_hornet',0,1000)
        function other:getFuel()return 0.5 end
        local meta=config.observers[1]
        config.observers[2]={name='wingman',typeName=meta.typeName,category=meta.category,
          coalition=2,role=meta.role,equipment=meta.equipment,afac=meta.afac}
        unit('target2',red,'T-72B',5100,0)
        config.targets[2]={name='target2',groupName='red'}
        begin();advance(35)
        assert(#made==1 and #afac_marks==1)
        """)

    def test_target_death_announced_and_releases_reservation(self):
        self.rt.execute("""
        begin();advance(25);target.life=0;advance(2)
        assert(made[1].dead and messages[#messages].text:find('target destroyed'))
        assert(marker.coordinator:get('observer').state=='search')
        """)

    def test_messages_use_configured_coordinates_and_duration(self):
        for fmt, expected in (
            (0, "N 41 30.000 E 42 15.000"),
            (1, "N 41 30 00 E 42 15 00"),
            (2, "38T KM 12345 67890"),
        ):
            with self.subTest(fmt=fmt):
                self.setUp()
                self.rt.execute(
                    f"config.afacMarking.coordinateFormat={fmt};config.afacMarking.messageSeconds=25;begin();advance(25)"
                )
                self.assertIn(expected, self.rt.globals().messages[2]["text"])
                self.assertEqual(self.rt.globals().messages[2]["seconds"], 25)

    def test_opaque_cloud_blocks_marking_even_with_ir_observation(self):
        self.rt.execute("""
        e.visualTransmission=0;begin();advance(25)
        assert(not red.hidden and #afac_discoveries==1)
        assert(#made==0 and not afac_marks)
        """)

    def test_ir_pointer_follows_dusk_and_dawn_without_extra_credit(self):
        self.rt.execute("""
        begin();advance(25);assert(#made==1)
        e.light=0;advance(2);assert(#made==2 and not made[2].dead)
        e.light=1;advance(2);assert(made[2].dead and not made[1].dead)
        assert(#afac_marks==1)
        """)

    def test_human_afacs_do_not_get_duplicate_scripted_smoke(self):
        self.rt.execute("""
        config.observers[1].allowPlayer=true
        observer.player='Human';begin();advance(25)
        assert(#made==1 and #smokes==0 and not afac_marks[1].smoke)
        """)

    def test_known_armor_can_be_marked_without_discovery_credit(self):
        self.rt.execute("""
        assert(fog:stop());run(3)
        local cfg={enabled=true,afacEnabled=true,afacMarking=config.afacMarking,
          registry={schemaVersion=1,groups={},targets={},observers=config.observers,
            knownAirDefenseGroups={},knownGroundGroups={{name='red',coalition=1}},
            afacKnownTargets=config.targets,warnings={}},
          acquisitionSeconds=0,environment={defaultCover='desert',startTime=43200,
            sunrise=21600,sunset=64800,weather=1,visibility=30000}}
        local m=assert(RealisticCAS.startMission(cfg));advance(25)
        assert(not red.hidden and not m.fog.service:isRegistered(1))
        assert(#made==1 and #afac_marks==1)
        assert(not afac_discoveries or #afac_discoveries==0)
        assert(m:stop())
        """)

    def test_bootstrap_shots_and_mission_end_cleanup(self):
        self.rt.execute("""
        assert(fog:stop());run(3)
        local cfg={enabled=true,afacEnabled=true,afacMarking=config.afacMarking,
          registry={schemaVersion=1,groups={{name='red',originalInvisible=false}},
            targets=config.targets,observers=config.observers,knownAirDefenseGroups={},warnings={}},
          acquisitionSeconds=5,environment={defaultCover='desert',startTime=43200,
            sunrise=21600,sunset=64800,weather=1,visibility=30000}}
        world.event.S_EVENT_MISSION_END=12
        local m=assert(RealisticCAS.startMission(cfg));advance(25)
        marker=m.detectors.afacMarking
        local before=marker.coordinator:get('observer').smokeRounds
        for h in pairs(handlers)do h:onEvent({id=1,initiator=observer})end
        assert(marker.coordinator:get('observer').smokeRounds==before-1)
        -- A source without getName must not raise the user's earlier event error.
        for h in pairs(handlers)do h:onEvent({id=1,initiator={isExist=function()return false end}})end
        failStop=true;assert(not m:stop() and RealisticCAS.mission==m)
        failStop=false;assert(m:stop());run(10)
        assert(made[1].dead and not RealisticCAS.mission)
        """)

    def test_two_groups_can_mark_in_parallel_with_the_shared_code(self):
        self.rt.execute("""
        local other=unit('wingman',blue,'FA-18C_hornet',0,1000)
        function other:getFuel()return 0.5 end
        local meta=config.observers[1]
        config.observers[2]={name='wingman',typeName=meta.typeName,category=meta.category,
          coalition=2,role=meta.role,equipment=meta.equipment,afac=meta.afac}
        local another=group('another',3,1)
        unit('target2',another,'T-72B',5100,0)
        assert(fog:stop());fog=start({'red','another'})
        config.targets[2]={name='target2',groupName='another'}
        begin();advance(40)
        assert(#made==2 and made[1].code==1688 and made[2].code==1688 and #afac_marks==2)
        assert(afac_marks[1].group~=afac_marks[2].group)
        """)

    def test_red_afac_marks_and_reports_only_to_red(self):
        self.rt.execute("""
        assert(fog:stop());blue.side=1;red.side=2;fog=start({'red'})
        config.observers[1].coalition=1
        begin();advance(25)
        assert(#made==1 and afac_marks[1].coalition==1)
        for _,m in ipairs(messages)do assert(m.side==1)end
        """)

    def test_ir_only_marker_stops_at_dawn(self):
        self.rt.execute("""
        local meta=config.observers[1]
        meta.equipment.laser=false;meta.afac.smokeRounds=0
        e.light=0;begin();advance(25)
        assert(#made==1 and afac_marks[1].infrared)
        e.light=1;advance(2)
        assert(made[1].dead and marker.coordinator:get('observer').state=='search')
        """)

    def test_configured_duration_rotates_groups(self):
        self.rt.execute("""
        config.afacMarking.markSeconds=5
        local another=group('another',3,1)
        unit('target2',another,'T-72B',5100,0)
        assert(fog:stop());fog=start({'red','another'})
        config.targets[2]={name='target2',groupName='another'}
        begin();advance(40)
        assert(#afac_marks==2 and #made>2)
        assert(afac_marks[1].group~=afac_marks[2].group)
        """)

    def test_invalid_configuration_fails_before_hiding(self):
        self.rt.execute("""
        assert(fog:stop());run(3)
        local cfg={enabled=true,afacEnabled=true,afacMarking={laserCode=1689},
          registry={schemaVersion=1,groups={{name='red',originalInvisible=false}},
            targets=config.targets,observers=config.observers,knownAirDefenseGroups={},warnings={}},
          acquisitionSeconds=5,environment={defaultCover='desert',startTime=43200,
            sunrise=21600,sunset=64800,weather=1,visibility=30000}}
        assert(not pcall(RealisticCAS.startMission,cfg))
        assert(not red.hidden and #made==0)
        """)
