"""AFAC search uses the existing bounded perception bridge and visibility owner."""

import unittest

import test_sensors
from test_contact_core import PLUGIN


class AfacSearchTests(unittest.TestCase):
    def setUp(self):
        test_sensors.BridgeTests.setUp(self)
        self.rt.execute((PLUGIN / "afac-search.lua").read_text("utf-8"))
        self.rt.execute("""
        RealisticCAS.afacStations={blue=0}
        config.afacEnabled=true
        config.acquisitionSeconds=5
        config.observers[1].role='AFAC — Area'
        config.observers[1].equipment={ir=true,eo=true}
        config.observers[1].afac={groupName='blue',stationSeconds=600,skill=4,
          zone={radius=10000,points={{x=0,z=0}}}}
        observer.fuel=0.5
        function observer:getFuel() return self.fuel end
        messages={};trigger={action={outTextForCoalition=function(side,text,seconds)
          messages[#messages+1]={side=side,text=text,seconds=seconds} end}}
        """)

    def test_arrival_starts_search_and_expired_contacts_do_not_farm_xp(self):
        self.rt.execute("""
        RealisticCAS.afacStations={}
        RealisticCAS.startDetection(fog,config);run(30)
        assert(red.hidden and not afac_discoveries)
        RealisticCAS.afacStations.blue=now
        run(40);assert(not red.hidden and #afac_discoveries==1 and dirty_state)
        local credit=afac_discoveries[1]
        assert(credit.observer=='observer' and credit.target=='target' and credit.group=='red' and credit.coalition==2)
        observer.life=0;run(60);assert(red.hidden)
        observer.life=100;run(40);assert(not red.hidden and #afac_discoveries==1)
        """)

    def test_fuel_and_station_expiry_stop_observations(self):
        for modification in (
            "observer.fuel=0.1",
            "RealisticCAS.afacStations.blue=-600",
        ):
            with self.subTest(modification=modification):
                self.setUp()
                self.rt.execute(
                    modification
                    + ";RealisticCAS.startDetection(fog,config);run(40);assert(red.hidden and not afac_discoveries)"
                )

    def test_zone_bounds_apply_to_observer_and_targets(self):
        for modification in ("observer.point.x=-11000", "target.point.x=11000"):
            with self.subTest(modification=modification):
                self.setUp()
                self.rt.execute(
                    modification
                    + ";RealisticCAS.startDetection(fog,config);run(40);assert(red.hidden and not afac_discoveries)"
                )

    def test_known_contacts_give_no_discovery_credit(self):
        self.rt.execute("""
        assert(fog:observe('red',2,target.point,'already known'))
        RealisticCAS.startDetection(fog,config);run(40)
        assert(not afac_discoveries)
        """)

    def test_same_group_gets_one_credit_with_multiple_members_and_observers(self):
        self.rt.execute("""
        local second=unit('other',blue,'FA-18C_hornet',0,1000)
        function second:getFuel() return 0.5 end
        local meta=config.observers[1]
        config.observers[2]={name='other',typeName=meta.typeName,role=meta.role,
          category='air',equipment=meta.equipment,afac=meta.afac}
        unit('target2',red,'T-72B',5100,0)
        config.targets[2]={name='target2',groupName='red'}
        RealisticCAS.startDetection(fog,config);run(80)
        assert(#afac_discoveries==1)
        """)

    def test_red_afac_discovers_blue_with_the_same_rules(self):
        self.rt.execute("""
        assert(fog:stop());blue.side=1;red.side=2;fog=start({'red'})
        RealisticCAS.startDetection(fog,config);run(40)
        assert(not red.hidden and afac_discoveries[1].coalition==1)
        """)

    def test_visual_only_night_warning_is_coalition_only_and_not_repeated(self):
        self.rt.execute("""
        config.observers[1].equipment={ir=false,eo=false}
        e.light=0
        RealisticCAS.startDetection(fog,config);run(40)
        assert(#messages==1 and messages[1].side==2 and messages[1].seconds==15)
        assert(messages[1].text:find('no thermal'))
        """)

    def test_capsule_geometry_and_metadata_validation(self):
        self.rt.execute("""
        local a=RealisticCAS.AFACSearch
        local z={radius=100,points={{x=0,z=0},{x=1000,z=0}}}
        assert(a.inside({x=500,z=99},z) and a.inside({x=-99,z=0},z))
        assert(not a.inside({x=500,z=101},z) and not a.inside({x=1101,z=0},z))
        local m=config.observers[1].afac
        m.zone=z;a.validate(m)
        m.skill=5;assert(not pcall(a.validate,m))
        m.skill=0;m.zone.radius=0;assert(not pcall(a.validate,m))
        """)

    def test_skill_improves_chance_without_bypassing_los_or_bounds(self):
        self.rt.execute("""
        local meta=config.observers[1].afac
        local o={point=observer.point,forward={x=1,y=0,z=0},side=2,agl=1000,afac=meta}
        local t={point=target.point,side=1}
        local p=S.profile('unknown','air',{ir=true,eo=true})
        meta.skill=0;local low=S.assess(o,t,e,p,true)
        meta.skill=4;local high=S.assess(o,t,e,p,true)
        assert(low and high and high.chance>low.chance)
        target.point.x=11000;assert(not S.assess(o,t,e,p,true))
        """)

    def test_disabled_afac_does_not_start(self):
        self.rt.execute(
            "config.afacEnabled=false;assert(not pcall(RealisticCAS.startDetection,fog,config))"
        )
