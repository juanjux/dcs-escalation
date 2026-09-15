"""Lua 5.1 model, spatial scheduler and DCS bridge contract tests (no engine claims)."""

import unittest

from lupa.lua51 import LuaRuntime
from test_contact_core import CORE, ADAPTER, ADAPTER_FIXTURE, PLUGIN

FILES = ["sensors.lua", "environment.lua", "detection.lua", "detectors-dcs.lua"]
SOURCES = [(PLUGIN / name).read_text(encoding="utf-8") for name in FILES]

MODEL = """
S=RealisticCAS.Sensors
o={side=2,point={x=0,y=1000,z=0},forward={x=1,y=0,z=0},agl=1000,role='CAS',radarOn=true}
t={side=1,point={x=5000,y=0,z=0},velocity={x=0,y=0,z=0}}
e={cover='desert',light=1,weather=1,visibility=30000,visualTransmission=1,irTransmission=1}
p=S.profile('F-15C','air')
"""


class SensorModelTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(CORE)
        for source in SOURCES:
            self.rt.execute(source)
        self.rt.execute(MODEL)

    def check(self, code):
        self.rt.execute(code)

    def test_visual_fighter_and_unknown_types(self):
        self.check("""
        assert(S.assess(o,t,e,p).mode=='visual')
        assert(p.rbmRange==0 and p.irRange==0)
        local unknown=S.profile('unknown mod','air')
        assert(unknown.irRange==0 and unknown.rbmRange==0 and unknown.gmtiRange==0)
        t.point.x=-5000;assert(not S.assess(o,t,e,p))
        t.point.x=5000;o.agl=4000;assert(not S.assess(o,t,e,p))
        """)

    def test_invalid_geometry_environment_coalitions(self):
        self.check("""
        t.side=2;assert(not S.assess(o,t,e,p));t.side=0;assert(not S.assess(o,t,e,p));t.side=1
        assert(not S.assess(o,t,nil,p));e.cover='guess';assert(not S.assess(o,t,e,p))
        e.cover='desert';o.point.x=0/0;assert(not S.assess(o,t,e,p));o.point.x=0
        o.forward={x=0,y=1,z=0};assert(not S.assess(o,t,e,p))
        """)

    def test_light_weather_and_cover_reduce_range(self):
        self.check("""
        local last=math.huge
        t.point.x=100;t.point.y=999
        for _,cover in ipairs({'desert','grassland','tundra','forest','city'}) do
          e.cover=cover;local r=S.assess(o,t,e,p).range;assert(r<last);last=r
        end
        e.cover='desert';t.point.x=5000;e.light=0;assert(not S.assess(o,t,e,p))
        e.light=1;e.weather=0;assert(not S.assess(o,t,e,p))
        e.weather=1;e.visibility=1000;assert(not S.assess(o,t,e,p))
        """)

    def test_ir_pod_night_clouds_no_magic_irst(self):
        self.check("""
        e.light=0;e.visualTransmission=0.02
        assert(not S.assess(o,t,e,S.profile('A-10C_2','air')))
        p=S.profile('A-10C_2','air',{targetingPod=true})
        assert(S.assess(o,t,e,p).mode=='ir')
        e.irTransmission=0.1;assert(not S.assess(o,t,e,p))
        e.irTransmission=1;o.agl=7000;assert(not S.assess(o,t,e,p))
        assert(S.profile('Su-25T','air').irRange==0)
        assert(S.profile('Ka-50_3','air').irRange==0)
        assert(S.profile('OH58D','air').irRange>0)
        assert(S.profile('MQ-9','air').irRange>0)
        """)

    def test_rbm_gmti_role_state_and_radial_motion(self):
        self.check("""
        p=S.profile('FA-18C_hornet','air');e.light=0
        assert(S.assess(o,t,e,p).mode=='rbm')
        o.radarOn=false;assert(not S.assess(o,t,e,p));o.radarOn=true
        for _,role in ipairs({'BARCAP','JTAC','DEAD','SEAD','STRIKE'}) do
          o.role=role;assert(not S.assess(o,t,e,p))
        end
        for _,role in ipairs({'CAS','BAI','Armed Recon'}) do
          o.role=role;assert(S.assess(o,t,e,p).mode=='rbm')
        end
        o.role='CAS';t.point.x=18000;assert(not S.assess(o,t,e,p))
        t.velocity.x=10;assert(S.assess(o,t,e,p).mode=='gmti')
        t.velocity={x=0,y=0,z=10};assert(not S.assess(o,t,e,p))
        t.velocity={x=0.5,y=0,z=0};assert(not S.assess(o,t,e,p))
        t.velocity={x=10,y=0,z=0};t.point.x=-18000;assert(not S.assess(o,t,e,p))
        t.point={x=18000,y=2000,z=0};assert(not S.assess(o,t,e,p))
        t.point={x=0,y=0,z=18000};assert(not S.assess(o,t,e,p))
        """)

    def test_ground_has_separate_ranges_and_thermal(self):
        self.check("""
        o.point.y=2;o.agl=2;t.point.x=-2500;e.light=1
        p=S.profile('truck','ground');assert(S.assess(o,t,e,p).mode=='visual')
        e.light=0;assert(not S.assess(o,t,e,p))
        p=S.profile('M-1 Abrams','ground');assert(S.assess(o,t,e,p).mode=='ir')
        t.point.x=5000;assert(not S.assess(o,t,e,p))
        assert(p.rbmRange==0 and p.gmtiRange==0)
        """)

    def test_environment_cache_sun_cloud_geometry_and_copy(self):
        self.check("""
        local cfg={defaultCover='desert',startTime=0,sunrise=21600,sunset=64800,
          weather=0.8,visibility=12000,zones={{x=125,z=125,radius=400,cover='city'}},
          clouds={base=2000,top=3000,visualTransmission=0.05,irTransmission=0.6}}
        local env=RealisticCAS.newEnvironment(cfg)
        cfg.clouds.irTransmission=0;cfg.defaultCover='forest'
        local a={point={x=0,y=1000,z=0}};local b={point={x=125,y=0,z=125}}
        local v=env(a,b,43200);assert(v.cover=='city' and v.light==1 and v.irTransmission==1)
        a.point.y=4000;v=env(a,b,0)
        assert(v.light==0 and v.irTransmission==0.6 and v.visualTransmission==0.05)
        b.point.y=3500;assert(env(a,b,0).irTransmission==1)
        assert(S.lightAt(20700,21600,64800)==0.5)
        assert(S.lightAt(65700,21600,64800)==0.5)
        assert(S.lightAt(86400+43200,21600,64800)==1)
        for i=1,5000 do b.point.x=i*1000;assert(env(a,b,i).cover=='desert') end
        b.point.x=125;assert(env(a,b,6000).cover=='city')
        assert(not pcall(RealisticCAS.newEnvironment,{defaultCover='desert'}))
        """)


SEARCH = """
now=0;readCount=0;losCount=0;found={};known={};alive=true;losOK=true
obs={side=2,point={x=0,y=2,z=0},forward={x=1,y=0,z=0},agl=2,role='CAS'}
units={target={name='target',groupName='red',side=1,point={x=1000,y=1,z=0},velocity={x=0,y=0,z=0}}}
function build(tb,wb,acq)
  return RealisticCAS.newDetection({clock=function()return now end,targetBudget=tb,workBudget=wb,
    acquisitionSeconds=acq,
    readObserver=function()if alive then return obs end end,
    readTarget=function(id)readCount=readCount+1;return units[id]end,
    environment=function()return e end,
    lineOfSight=function()losCount=losCount+1;return losOK end,
    isRevealed=function(t)return known[t.groupName or t.name]==true end,
    reveal=function(t,o,r)
      found[#found+1]={name=t.name,mode=r.mode,time=now}
      if acq then known[t.groupName or t.name]=true end
      return true
    end})
end
function advance(engine,n) for i=1,n do now=now+1;engine:tick()end end
"""


class SearchTests(unittest.TestCase):
    def setUp(self):
        SensorModelTests.setUp(self)
        self.rt.execute(SEARCH)

    def check(self, code):
        self.rt.execute(code)

    def test_acquisition_requires_observed_time_not_first_range_hit(self):
        self.check("""
        local engine=build(64,128,10)
        engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        advance(engine,10);assert(#found==0)
        advance(engine,1);assert(#found==1 and found[1].time==11)
        assert(engine:getDiagnostics().acquisitionCompletions==1)
        advance(engine,10);assert(#found>1) -- known contact renewals do not search again
        assert(engine:getDiagnostics().acquisitionCompletions==1)
        """)

    def test_acquisition_one_unknown_group_at_a_time(self):
        self.check("""
        local engine=build(64,128,10)
        for i=1,20 do
          local id='t'..i;units[id]={name=id,groupName=id,side=1,point={x=1000,y=1,z=i}}
          engine:addTarget(id)
        end
        engine:addObserver('obs',S.profile('truck','ground'));advance(engine,60)
        local count=0;for _ in pairs(known) do count=count+1 end
        assert(count==5 and engine:getDiagnostics().pendingAcquisitions<=1)
        engine:stop();assert(engine:getDiagnostics().pendingAcquisitions==0)
        """)

    def test_many_group_members_do_not_accelerate_acquisition(self):
        self.check("""
        local engine=build(64,128,10)
        for i=1,30 do
          local id='member'..i;units[id]={name=id,groupName='same',side=1,point={x=1000,y=1,z=i}}
          engine:addTarget(id)
        end
        engine:addObserver('obs',S.profile('truck','ground'))
        advance(engine,10);assert(#found==0)
        advance(engine,1);assert(known.same)
        assert(engine:getDiagnostics().acquisitionCompletions==1)
        """)

    def test_lost_los_and_dead_observer_reset_search(self):
        self.check("""
        local engine=build(64,128,10)
        engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        advance(engine,6);losOK=false;advance(engine,5)
        assert(engine:getDiagnostics().pendingAcquisitions==0)
        losOK=true;advance(engine,10);assert(#found==0)
        alive=false;advance(engine,5);assert(engine:getDiagnostics().pendingAcquisitions==0)
        alive=true;advance(engine,10);assert(#found==0)
        advance(engine,5);assert(#found>0)
        """)

    def test_scheduler_gap_is_not_continuous_observation(self):
        self.check("""
        local engine=build(64,128,10)
        engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        advance(engine,6);now=now+100;engine:tick();assert(#found==0)
        advance(engine,9);assert(#found==0)
        advance(engine,1);assert(#found==1)
        """)

    def test_shared_contact_bypasses_search_but_not_los(self):
        self.check("""
        local engine=build(64,128,20)
        engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        advance(engine,1);known.red=true;losOK=false;advance(engine,5);assert(#found==0)
        losOK=true;advance(engine,5);assert(#found==1)
        assert(engine:getDiagnostics().acquisitionCompletions==0)
        """)

    def test_many_observers_do_not_reset_on_normal_scheduler_rotation(self):
        self.check("""
        local engine=build(64,128,20)
        engine:addTarget('target')
        for i=1,34 do engine:addObserver('obs'..i,S.profile('truck','ground')) end
        advance(engine,140)
        assert(#found>0 and engine:getDiagnostics().acquisitionCompletions>0)
        assert(found[1].time>=21 and found[1].time<60)
        """)

    def test_spatial_search_los_and_dead_observer(self):
        self.check("""
        local engine=build(64,128);engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        losOK=false;advance(engine,20);assert(#found==0 and losCount>0)
        losOK=true;advance(engine,20);assert(#found>0)
        local count=#found;alive=false;advance(engine,20);assert(#found==count)
        engine:stop();local reads=readCount;advance(engine,20);assert(readCount==reads)
        """)

    def test_non_candidates_do_not_call_los(self):
        self.check("""
        local engine=build(64,128);engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        units.target.side=2;advance(engine,20);assert(losCount==0)
        units.target.side=1;e.light=0;advance(engine,20);assert(losCount==0)
        e.light=1;units.target.point.x=100000;advance(engine,20);assert(losCount==0)
        """)

    def test_moving_targets_reindexed_and_rechecked(self):
        self.check("""
        local engine=build(1,1);engine:addTarget('target');engine:addObserver('obs',S.profile('truck','ground'))
        units.target.point.x=100000;advance(engine,20);assert(#found==0)
        units.target.point.x=1000;advance(engine,40);assert(#found>0)
        units.target=nil;local count=#found;advance(engine,40);assert(#found==count)
        """)

    def test_large_dense_search_bounded_and_completes(self):
        self.check("""
        local engine=build(31,17)
        for i=1,5000 do
          local name='t'..i;units[name]={name=name,side=1,point={x=1000,y=0,z=i%100}}
          engine:addTarget(name)
        end
        engine:addObserver('obs',S.profile('truck','ground'))
        for i=1,1000 do
          local d=engine:getDiagnostics();local before=readCount
          now=now+1;engine:tick()
          local after=engine:getDiagnostics()
          assert(after.work-d.work<=17)
          assert(readCount-before<=31+17)
          assert(after.observerReads-d.observerReads<=2)
        end
        assert(engine:getDiagnostics().sweeps>=1 and #found>=5000)
        """)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(CORE)
        self.rt.execute(ADAPTER_FIXTURE)
        self.rt.execute(ADAPTER)
        for source in SOURCES:
            self.rt.execute(source)
        self.rt.execute(MODEL)
        self.rt.execute("""
        land={getHeight=function()return 0 end,isVisible=function()return true end}
        units={};Unit={getByName=function(n)return units[n]end}
        function unit(name,g,kind,x,y)
          local u={exists=true,life=100,player=nil,airborne=true,radar=true,typeName=kind,
            point={x=x,y=y,z=0},velocity={x=0,y=0,z=0}}
          function u:isExist()return self.exists end
          function u:getLife()return self.life end
          function u:getCoalition()return g.side end
          function u:getGroup()return g end
          function u:getPoint()return self.point end
          function u:getVelocity()return self.velocity end
          function u:getTypeName()return self.typeName end
          function u:getPlayerName()return self.player end
          function u:inAir()return self.airborne end
          function u:getPosition()return {p=self.point,x={x=1,y=0,z=0}}end
          function u:getRadar()return self.radar end
          units[name]=u;return u
        end
        red=group('red',1);blue=group('blue',2,2,0)
        target=unit('target',red,'T-72B',5000,0)
        observer=unit('observer',blue,'FA-18C_hornet',0,1000)
        fog=start({'red'})
        config={targets={{name='target',groupName='red'}},
          observers={{name='observer',typeName='FA-18C_hornet',category='air',role='CAS'}},
          environment=function()return e end}
        function run(n)
          for i=1,n do
            table.sort(pending,function(a,b)return a.t<b.t end)
            local v=table.remove(pending,1);if not v then return end
            now=v.t;local again=v.f(v.a,now)
            if again then pending[#pending+1]={f=v.f,a=v.a,t=again}end
          end
        end
        """)

    def check(self, code):
        self.rt.execute(code)

    def test_hidden_target_discovered_without_native_detection(self):
        self.check("""
        assert(red.hidden);detectors=RealisticCAS.startDetection(fog,config)
        run(40);assert(not red.hidden and fog.service:isRevealed(1,2))
        local c=fog.service:getContact(1,2)
        assert(c.reason=='rbm:observer' and c.lastPosition.y==0)
        observer.life=0;run(60);assert(red.hidden)
        assert(fog:stop());run(3);assert(not detectors:getDiagnostics().enabled)
        """)

    def test_two_hidden_ground_sides_reveal_each_other_without_shots(self):
        self.check("""
        assert(fog:stop());blue.category=2
        observer.typeName='M-1 Abrams';observer.point.y=0;target.point.x=1500
        fog=start({'red','blue'});assert(red.hidden and blue.hidden)
        config.observers={
          {name='observer',typeName='M-1 Abrams',category='ground'},
          {name='target',typeName='T-72B',category='ground'}}
        config.targets={{name='target',groupName='red'},{name='observer',groupName='blue'}}
        config.acquisitionSeconds=20
        RealisticCAS.startDetection(fog,config)
        while now<35 do run(1)end
        assert(not red.hidden and not blue.hidden)
        assert(fog.service:isRevealed(1,2) and fog.service:isRevealed(2,1))
        """)

    def test_scheduler_warning_is_logged_with_debug_disabled(self):
        self.check("""
        config.debug=false;config.acquisitionSeconds=20
        local detector=RealisticCAS.startDetection(fog,config)
        detector:tick();now=100;detector:tick()
        local warning=false
        for _,line in ipairs(logs)do
          if line:find('REALISTIC_CAS_SENSOR|WARNING|',1,true)then warning=true end
        end
        assert(warning)
        """)

    def test_radar_off_player_and_replacement_do_not_cheat(self):
        self.check("""
        e.light=0;observer.radar=false
        local detector=RealisticCAS.startDetection(fog,config)
        run(40);assert(red.hidden)
        observer.radar=true;observer.player='human';run(40);assert(red.hidden)
        observer.player=nil;observer.typeName='F-15C';run(40);assert(red.hidden)
        observer.typeName='FA-18C_hornet';observer.airborne=false;run(40);assert(red.hidden)
        observer.airborne=true;run(40);assert(not red.hidden)
        """)

    def test_duplicate_start_and_unknown_ownership(self):
        self.check("""
        config.targets[1].groupName='different'
        RealisticCAS.startDetection(fog,config);run(40);assert(red.hidden)
        assert(not pcall(RealisticCAS.startDetection,fog,config))
        """)

    def test_live_bridge_acquisition_delays_first_reveal(self):
        self.check("""
        config.acquisitionSeconds=20
        local detector=RealisticCAS.startDetection(fog,config)
        while now<19 do run(1) end
        assert(red.hidden and not fog.service:isRevealed(1,2))
        while now<30 do run(1) end
        assert(not red.hidden and fog.service:isRevealed(1,2))
        assert(detector:getDiagnostics().acquisitionCompletions==1)
        observer.life=0;run(80);assert(red.hidden)
        """)

    def test_sensor_mission_runner_completes_and_restores(self):
        self.check("""
        assert(fog:stop())
        trigger={action={outText=function()end}}
        observer.typeName='T-72B';blue.category=2;observer.point.y=0
        target.point.x=1000
        RCAS_SENSOR_TEST={groups={{name='red',originalInvisible=false}},zones={},
          targets={{name='target',groupName='red',expect=true}},
          observers={{name='observer',typeName='T-72B',category='ground'}}}
        """)
        runner = PLUGIN.parents[2] / "tools/realistic_cas_tests/sensor_smoke.lua"
        self.rt.execute(runner.read_text(encoding="utf-8"))
        self.check("""
        run(1800)
        assert(#pending==0 and not RealisticCAS._running and not red.hidden)
        local result=false
        for _,line in ipairs(logs) do
          assert(not line:find('|FAIL|',1,true) and not line:find('|ERROR|',1,true),line)
          if line:find('|RESULT|',1,true) and line:find('failures=0',1,true) then result=true end
        end
        assert(result)
        """)

    def run_night_mission(self, blocked=False, missing_ir=False):
        self.check("""
        assert(fog:stop())
        trigger={action={outText=function()end}}
        observer.typeName='M-1 Abrams';blue.category=2;observer.point.y=0
        target.point.x=2000
        RCAS_NIGHT_TEST={observer='observer',target={name='target',groupName='red'}}
        """)
        if blocked:
            self.check("land.isVisible=function()return false end")
        if missing_ir:
            self.check("""
            local original=RealisticCAS.Sensors.profile
            RealisticCAS.Sensors.profile=function(...)
              local p=original(...);p.irRange=0;return p
            end
            """)
        runner = PLUGIN.parents[2] / "tools/realistic_cas_tests/night_smoke.lua"
        self.rt.execute(runner.read_text(encoding="utf-8"))
        self.check(
            "run(2000);assert(#pending==0 and not RealisticCAS._running and not red.hidden)"
        )
        return "\n".join(self.rt.globals().logs.values())

    def test_night_runner_exact_channels_expiry_and_recovery(self):
        logs = self.run_night_mission()
        self.assertIn("failures=0|inconclusive=0|checks=11", logs)
        self.assertNotIn("|ERROR|", logs)
        self.assertIn("NIGHT_IR_ON exact channel ir", logs)

    def test_night_runner_blocked_is_inconclusive(self):
        logs = self.run_night_mission(blocked=True)
        self.assertIn("failures=0|inconclusive=1|checks=0", logs)

    def test_night_runner_catches_missing_ir(self):
        logs = self.run_night_mission(missing_ir=True)
        self.assertIn("failures=1|inconclusive=0|checks=11", logs)

    def run_cloud_mission(self, blocked=False, ignore_clouds=False):
        self.check("""
        assert(fog:stop())
        trigger={action={outText=function()end}}
        observer.typeName='A-10C_2';observer.point.y=4000
        target.point.x=5000
        RCAS_CLOUD_TEST={observer='observer',target={name='target',groupName='red'}}
        """)
        if blocked:
            self.check("land.isVisible=function()return false end")
        if ignore_clouds:
            self.check("""
            local original=RealisticCAS.newEnvironment
            RealisticCAS.newEnvironment=function(c) c.clouds=nil;return original(c) end
            """)
        runner = PLUGIN.parents[2] / "tools/realistic_cas_tests/cloud_smoke.lua"
        self.rt.execute(runner.read_text(encoding="utf-8"))
        self.check(
            "run(3000);assert(#pending==0 and not RealisticCAS._running and not red.hidden)"
        )
        return "\n".join(self.rt.globals().logs.values())

    def test_cloud_runner_channels_and_expiry(self):
        logs = self.run_cloud_mission()
        self.assertIn("failures=0|inconclusive=0|checks=13", logs)
        self.assertNotIn("|ERROR|", logs)

    def test_cloud_runner_no_los_not_false_pass(self):
        logs = self.run_cloud_mission(blocked=True)
        self.assertIn("failures=0|inconclusive=4|checks=9", logs)

    def test_cloud_runner_catches_missing_cloud_attenuation(self):
        logs = self.run_cloud_mission(ignore_clouds=True)
        self.assertIn("|FAIL|", logs)
        self.assertIn("failures=4|inconclusive=0|checks=13", logs)
        self.assertNotIn("|ERROR|", logs)

    def run_radar_mission(self, radar=True, moving=True, broken_gmti=False):
        self.check("""
        assert(fog:stop())
        trigger={action={outText=function()end}}
        observer.typeName='FA-18C_hornet';observer.point.y=4500
        target.point.x=18000;target.velocity.x=6
        local farGroup=group('far',3)
        unit('far-target',farGroup,'Ural-375',18000,0)
        local nearGroup=group('near',4)
        unit('near-target',nearGroup,'Ural-375',8000,0)
        RCAS_RADAR_TEST={observer='observer',groups={
          {name='red',originalInvisible=false},{name='far',originalInvisible=false},
          {name='near',originalInvisible=false}},targets={
          {name='target',groupName='red',kind='moving'},
          {name='far-target',groupName='far',kind='far'},
          {name='near-target',groupName='near',kind='near'}}}
        """)
        if not radar:
            self.check("observer.radar=false")
        if not moving:
            self.check("target.velocity.x=0")
        if broken_gmti:
            self.check("""
            local original=RealisticCAS.Sensors.profile
            RealisticCAS.Sensors.profile=function(...)
              local p=original(...);p.gmtiRange=0;return p
            end
            """)
        runner = PLUGIN.parents[2] / "tools/realistic_cas_tests/radar_smoke.lua"
        self.rt.execute(runner.read_text(encoding="utf-8"))
        self.check("""
        run(4000);assert(#pending==0 and not RealisticCAS._running)
        assert(not red.hidden and not groups.far.hidden and not groups.near.hidden)
        """)
        return "\n".join(self.rt.globals().logs.values())

    def test_radar_runner_exact_channels_and_roles(self):
        logs = self.run_radar_mission()
        self.assertIn("failures=0|inconclusive=0|checks=36", logs)
        self.assertNotIn("|ERROR|", logs)

    def test_radar_runner_no_radar_is_inconclusive(self):
        logs = self.run_radar_mission(radar=False)
        self.assertIn("failures=0|inconclusive=15|checks=6", logs)

    def test_radar_runner_stuck_convoy_is_inconclusive(self):
        logs = self.run_radar_mission(moving=False)
        self.assertIn("failures=0|inconclusive=5|checks=26", logs)

    def test_radar_runner_catches_missing_gmti(self):
        logs = self.run_radar_mission(broken_gmti=True)
        self.assertIn("failures=3|inconclusive=0|checks=36", logs)
        self.assertNotIn("|ERROR|", logs)

    def run_ground_mission(self, blocked):
        self.check("""
        assert(fog:stop())
        trigger={action={outText=function()end}}
        observer.typeName='T-72B';blue.category=2;observer.point.y=0
        target.point.x=1500
        local farGroup=group('far',3)
        unit('far-target',farGroup,'Ural-375',4000,0)
        RCAS_GROUND_TEST={observers={{name='observer',typeName='T-72B',category='ground'}},sets={
          {label='city',observer='observer',expected=true,city=true,
            candidates={{name='target',groupName='red'}}},
          {label='original',observer='observer',expected=true,original=true,
            candidates={{name='target',groupName='red'}}},
          {label='far',observer='observer',expected=false,
            candidates={{name='far-target',groupName='far'}}}}}
        """)
        if blocked:
            self.check("land.isVisible=function()return false end")
        runner = PLUGIN.parents[2] / "tools/realistic_cas_tests/ground_los_smoke.lua"
        self.rt.execute(runner.read_text(encoding="utf-8"))
        self.check("""
        run(1500)
        assert(#pending==0 and not RealisticCAS._running and not red.hidden)
        for _,line in ipairs(logs) do
          assert(not line:find('|ERROR|',1,true) and not line:find('|FAIL|',1,true),line)
        end
        """)
        return "\n".join(self.rt.globals().logs.values())

    def test_ground_runner_clear_los_and_decision_trace(self):
        logs = self.run_ground_mission(False)
        self.assertIn("failures=0|inconclusive=0|checks=3", logs)
        self.assertIn("|LOS_CLEAR|", logs)
        self.assertIn("|ENVELOPE_REJECT|", logs)
        self.assertIn("city cover rejects previously observed identical geometry", logs)

    def test_ground_runner_blocked_controls_are_inconclusive(self):
        logs = self.run_ground_mission(True)
        self.assertIn("failures=0|inconclusive=2|checks=1", logs)
        self.assertIn("|LOS_BLOCKED|", logs)
        self.assertIn("no usable LOS pair; not a sensor failure", logs)


class SiteSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(ADAPTER_FIXTURE)
        self.rt.execute("""
        messages={};spawns={};ran=0
        trigger={action={outText=function(s)messages[#messages+1]=s end}}
        land={getSurfaceType=function()return 1 end,getHeight=function()return 100 end,
          isVisible=function(a,b)return a.x>=10 end}
        coalition={addGroup=function(country,category,g)
          assert(category==2 and (country==80 or country==81))
          assert(g.units[1].x==g.x and g.route.points[1].y==g.y)
          spawns[#spawns+1]=g;return {}
        end}
        local templates={}
        for _,name in ipairs({'observer','near','city'}) do
          templates[name]={name=name,units={{}},route={points={{}}}}
        end
        local candidates={}
        for i=0,9 do candidates[#candidates+1]={observer={x=i*10,z=0},
          near={x=i*10+2000,z=0},city={x=i*10+1500,z=0}}end
        RCAS_GROUND_TEST={search={templates=templates,candidates=candidates}}
        RCAS_RUN_GROUND_TEST=function()ran=ran+1 end
        function drain()
          local count=0
          while #pending>0 do
            table.sort(pending,function(a,b)return a.t<b.t end)
            local p=table.remove(pending,1);now=p.t
            local again=p.f(p.a,now)
            if again then pending[#pending+1]={f=p.f,a=p.a,t=again}end
            count=count+1;assert(count<20)
          end
        end
        """)

    def run_selector(self):
        source = PLUGIN.parents[2] / "tools/realistic_cas_tests/select_ground_site.lua"
        self.rt.execute(source.read_text(encoding="utf-8"))
        self.rt.execute("drain()")
        return "\n".join(self.rt.globals().logs.values())

    def test_selects_new_site_and_starts_after_spawn_settles(self):
        logs = self.run_selector()
        self.rt.execute(
            "assert(#spawns==3 and ran==1 and now>=4);assert(spawns[1].x==10)"
        )
        self.assertIn("candidate=2", logs)
        self.assertNotIn("|ERROR|", logs)

    def test_no_clear_site_is_inconclusive_without_spawning(self):
        self.rt.execute("land.isVisible=function()return false end")
        logs = self.run_selector()
        self.rt.execute("assert(#spawns==0 and ran==0)")
        self.assertIn("|INCONCLUSIVE|", logs)

    def test_water_sites_are_not_used(self):
        self.rt.execute("land.getSurfaceType=function()return 3 end")
        logs = self.run_selector()
        self.rt.execute("assert(#spawns==0 and ran==0)")
        self.assertIn("|INCONCLUSIVE|", logs)

    def test_spawn_failure_never_runs_detector_test(self):
        self.rt.execute("coalition.addGroup=function()error('spawn unavailable')end")
        logs = self.run_selector()
        self.rt.execute("assert(ran==0)")
        self.assertIn("|ERROR|", logs)


if __name__ == "__main__":
    unittest.main()
