"""Probability curves and bounded rolls; Lua doubles, not native DCS calibration."""

import unittest

import test_sensors

FIXTURE = """
now=0;known=false;draw=0.999;draws=0;losOK=true;found=0;logs={}
obs={side=2,point={x=0,y=2,z=0},forward={x=1,y=0,z=0},agl=2,role='CAS'}
units={}
function buildRolls(members,enabled)
  now=0;known=false;draws=0;found=0;units={}
  local engine=RealisticCAS.newDetection({
    clock=function()return now end,acquisitionSeconds=20,revisit=5,
    probabilisticDetection=enabled,targetBudget=64,workBudget=1024,losBudget=64,
    random=function()draws=draws+1;return draw end,
    log=function(k,v)logs[#logs+1]={k,v}end,
    readObserver=function()return obs end,
    readTarget=function(id)return units[id]end,
    environment=function()return e end,
    lineOfSight=function()return losOK end,
    isRevealed=function()return known end,
    reveal=function()found=found+1;known=true;return true end})
  for i=1,members do
    local id='t'..i
    units[id]={name=id,groupName='red',side=1,point={x=1000,y=1,z=i}}
    engine:addTarget(id)
  end
  engine:addObserver('observer',S.profile('truck','ground'))
  return engine
end
function tick(engine,t)now=t;engine:tick()end
"""


class DetectionRollTests(unittest.TestCase):
    def setUp(self):
        test_sensors.SensorModelTests.setUp(self)
        self.rt.execute(FIXTURE)

    def check(self, code):
        self.rt.execute(code)

    def test_closer_and_lower_optical_observers_have_better_chances(self):
        self.check("""
        local p=S.profile('A-10C_2','air',{targetingPod=true})
        for _,mode in ipairs({'visual','eo','ir','rbm','gmti'}) do
          assert(S.discoveryChance(mode,1000,10000,1000,p)>
            S.discoveryChance(mode,9000,10000,1000,p))
          local low=S.discoveryChance(mode,5000,10000,500,p)
          local high=S.discoveryChance(mode,5000,10000,3000,p)
          if mode=='rbm' or mode=='gmti' then assert(low==high)
          else assert(low>high) end
          for _,d in ipairs({0,5000,10000}) do
            local c=S.discoveryChance(mode,d,10000,3000,p)
            assert(c>0 and c<1)
          end
        end
        local g=S.profile('truck','ground')
        assert(S.discoveryChance('visual',1000,3000,2,g)==
          S.discoveryChance('visual',1000,3000,90,g))
        """)

    def test_radar_advantage_and_best_channel_not_extra_rolls(self):
        self.check("""
        local p=S.profile('FA-18C_hornet','air',{targetingPod=true})
        local visual=S.discoveryChance('visual',5000,10000,1000,p)
        local optical=S.discoveryChance('ir',5000,10000,1000,p)
        local radar=S.discoveryChance('rbm',5000,10000,1000,p)
        assert(visual<optical and optical<radar)
        assert(radar<S.discoveryChance('gmti',5000,10000,1000,p))
        -- Optical range is deliberately longer, but radar's chance is better.
        p.irRange=18000
        assert(S.assess(o,t,e,p).mode=='ir') -- deterministic compatibility
        assert(S.assess(o,t,e,p,true).mode=='rbm')
        o.radarOn=false;assert(S.assess(o,t,e,p,true).mode=='ir')
        o.radarOn=true;t.velocity.x=10
        assert(S.assess(o,t,e,p,true).mode=='gmti')
        """)

    def test_radar_still_needs_role_cone_motion_and_active_sensor(self):
        self.check("""
        local p=S.profile('FA-18C_hornet','air')
        e.light=0
        assert(S.assess(o,t,e,p,true).mode=='rbm')
        o.radarOn=false;assert(not S.assess(o,t,e,p,true))
        o.radarOn=true;o.role='BARCAP';assert(not S.assess(o,t,e,p,true))
        o.role='CAS';t.point.x=-5000;assert(not S.assess(o,t,e,p,true))
        t.point.x=18000;assert(not S.assess(o,t,e,p,true))
        t.velocity.x=10;assert(S.assess(o,t,e,p,true).mode=='gmti')
        """)

    def test_delay_failure_retry_success_and_known_contact_refresh(self):
        self.check("""
        local engine=buildRolls(1,true)
        for i=0,19 do tick(engine,i) end
        assert(draws==0 and found==0)
        tick(engine,20);assert(draws==1 and found==0)
        tick(engine,21);assert(draws==1)
        draw=0;tick(engine,25);assert(draws==2 and found==1)
        for i=26,40 do tick(engine,i) end
        assert(draws==2 and found>1)
        local d=engine:getDiagnostics()
        assert(d.detectionRolls==2 and d.detectionPasses==1 and d.detectionMisses==1)
        assert(d.acquisitionCompletions==1 and d.pendingAcquisitions==0)
        local logged=false
        for _,v in ipairs(logs) do
          if v[1]=='DETECTION_ROLL' then
            assert(v[2]:find('chance=') and v[2]:find('agl=') and v[2]:find('roll='))
            logged=true
          end
        end
        assert(logged)
        """)

    def test_group_size_and_faster_ticks_do_not_multiply_rolls(self):
        self.check("""
        for _,members in ipairs({1,10,40}) do
          for _,step in ipairs({1,0.25}) do
            local engine=buildRolls(members,true)
            for i=0,40/step do tick(engine,i*step) end
            assert(draws==5,'members='..members..' step='..step..' draws='..draws)
            assert(found==0 and engine:getDiagnostics().pendingAcquisitions==1)
            engine:stop()
          end
        end
        """)

    def test_blocked_los_and_outside_range_never_roll(self):
        self.check("""
        local engine=buildRolls(1,true);draw=0;losOK=false
        for i=0,40 do tick(engine,i) end
        assert(draws==0 and found==0)
        losOK=true;units.t1.point.x=100000
        for i=41,80 do tick(engine,i) end
        assert(draws==0 and found==0)
        """)

    def test_losing_los_resets_search_and_stall_does_not_bank_rolls(self):
        self.check("""
        local engine=buildRolls(1,true)
        tick(engine,0);tick(engine,5);losOK=false;tick(engine,10)
        losOK=true;tick(engine,15);tick(engine,20);tick(engine,25);tick(engine,30)
        assert(draws==0);tick(engine,35);assert(draws==1)
        tick(engine,200);assert(draws==1) -- gap reset, not 33 missed attempts
        assert(engine:getDiagnostics().acquisitionResets==2)
        """)

    def test_disabled_rolls_keep_original_search_behavior(self):
        self.check("""
        local engine=buildRolls(10,false)
        for i=0,20 do tick(engine,i) end
        assert(found>0 and draws==0 and engine:getDiagnostics().detectionRolls==0)
        """)

    def test_invalid_random_samples_fail_closed_without_retry_storm(self):
        self.check("""
        for _,sample in ipairs({-1,1,0/0}) do
          local engine=buildRolls(10,true);draw=sample
          for i=0,20 do tick(engine,i) end
          assert(draws==1 and found==0 and engine:getDiagnostics().errors==1)
        end
        """)
