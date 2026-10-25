"""Probability curves and bounded rolls; Lua doubles, not native DCS calibration."""

import unittest

import test_sensors

FIXTURE = """
now=0;known=false;draw=0.999;draws=0;losOK=true;found=0;logs={}
obs={side=2,point={x=0,y=2,z=0},forward={x=1,y=0,z=0},agl=2,role='CAS'}
units={}
function buildRolls(members,enabled,tuning,delay)
  now=0;known=false;draws=0;found=0;units={}
  local engine=RealisticCAS.newDetection({
    clock=function()return now end,acquisitionSeconds=delay or 20,revisit=5,
    probabilisticDetection=enabled,targetBudget=64,workBudget=1024,losBudget=64,
    probability=tuning,
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

    def test_zero_delay_rolls_on_first_observation_and_refreshes_without_rolls(self):
        self.check("""
        local engine=buildRolls(1,true,nil,0);draw=0
        tick(engine,0);assert(found==1 and draws==1)
        tick(engine,5);assert(found>1 and draws==1)
        assert(engine:getDiagnostics().pendingAcquisitions==0)
        """)

    def test_zero_delay_retries_remain_bounded_for_many_members_and_fast_ticks(self):
        self.check("""
        for _,members in ipairs({1,10,40})do
          local engine=buildRolls(members,true,nil,0);draw=0.999
          for i=0,40 do tick(engine,i*0.25)end
          assert(draws==3 and found==0,'unexpected zero-delay roll rate: '..draws)
          engine:stop()
        end
        local engine=buildRolls(1,false,nil,0)
        tick(engine,0);assert(found==1 and draws==0)
        """)

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

    def test_movement_increases_each_channel_by_half_and_caps_at_one(self):
        self.check("""
        for _,percent in ipairs({0,40,80}) do
          local c=S.probabilityConfig({visualFarPercent=percent,visualNearPercent=percent,
            opticalFarPercent=percent,opticalNearPercent=percent,
            radarFarPercent=percent,radarNearPercent=percent,
            gmtiFarPercent=percent,gmtiNearPercent=percent,airAltitudePenaltyPercent=0})
          for _,mode in ipairs({'visual','eo','ir','rbm','gmti'}) do
            local p=S.profile('unknown','air',{
              eo=mode=='eo',ir=mode=='ir',rbm=mode=='rbm',gmti=mode=='gmti'},c)
            p.visualRange=mode=='visual' and 9260 or 0
            t.velocity={x=0,y=0,z=0}
            local stationary=S.assess(o,t,e,p,true,c)
            if mode=='gmti' then assert(not stationary)
            else assert(stationary.mode==mode and stationary.chance==percent/100) end
            for _,velocity in ipairs({{x=10,y=0,z=0},{x=0,y=0,z=-10}}) do
              -- GMTI also requires radial motion; add it for that channel only.
              if mode=='gmti' then velocity.x=10 end
              t.velocity=velocity
              local moving=S.assess(o,t,e,p,true,c)
              assert(moving.mode==mode)
              assert(math.abs(moving.chance-math.min(1,percent/100*1.5))<1e-12)
            end
          end
        end
        """)

    def test_movement_requires_valid_horizontal_velocity_and_ignores_jitter(self):
        self.check("""
        local c=S.probabilityConfig({visualFarPercent=40,visualNearPercent=40})
        local p=S.profile('unknown','air',nil,c)
        local base=S.assess(o,t,e,p,true,c).chance
        t.velocity=nil;assert(S.assess(o,t,e,p,true,c).chance==base)
        for _,velocity in ipairs({{}, {x=0,y=100,z=0}, {x=0.49,y=0,z=0},
          {x=0/0,y=0,z=1}, {x=math.huge,y=0,z=0}}) do
          t.velocity=velocity;assert(S.assess(o,t,e,p,true,c).chance==base)
        end
        for _,velocity in ipairs({{x=0.5,y=0,z=0},{x=-0.3,y=0,z=-0.4}}) do
          t.velocity=velocity
          assert(math.abs(S.assess(o,t,e,p,true,c).chance-base*1.5)<1e-12)
        end
        t.side=2;assert(not S.assess(o,t,e,p,true,c))
        t.side=1;t.point.x=100000;assert(not S.assess(o,t,e,p,true,c))
        """)

    def test_movement_bonus_composes_with_afac_skill(self):
        self.rt.execute((test_sensors.PLUGIN / "afac-search.lua").read_text("utf-8"))
        self.check("""
        o.afac={skill=0,zone={radius=10000,points={{x=5000,z=0}}}}
        local c=S.probabilityConfig({visualFarPercent=40,visualNearPercent=40,
          airAltitudePenaltyPercent=0})
        local p=S.profile('unknown','air',nil,c)
        local stationary=S.assess(o,t,e,p,true,c)
        assert(math.abs(stationary.chance-0.24)<1e-12)
        t.velocity.x=1
        assert(math.abs(S.assess(o,t,e,p,true,c).chance-0.36)<1e-12)
        """)

    def test_actual_motion_changes_next_roll_without_bypassing_los_or_retry(self):
        self.check("""
        local engine=buildRolls(10,true,{visualFarPercent=40,visualNearPercent=40},0)
        draw=0.5;tick(engine,0);assert(draws==1 and found==0)
        for _,target in pairs(units) do target.velocity={x=1,y=0,z=0} end
        for i=1,19 do tick(engine,i*0.25) end
        assert(draws==1 and found==0)
        losOK=false;tick(engine,5);assert(draws==1 and found==0)
        losOK=true;tick(engine,10);assert(draws==2 and found>0)
        local renewals=found
        tick(engine,15);assert(draws==2 and found>renewals)
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

    def test_custom_chances_penalty_and_retry_interval_are_used(self):
        self.check("""
        local engine=buildRolls(1,true,{visualFarPercent=0,visualNearPercent=0,retrySeconds=15})
        draw=0
        for i=0,40 do tick(engine,i) end
        assert(draws==2 and found==0) -- attempts only at 20 and 35
        engine:stop()
        engine=buildRolls(1,true,{visualFarPercent=100,visualNearPercent=100})
        draw=0.999
        for i=0,20 do tick(engine,i) end
        assert(found==1)
        local c=S.probabilityConfig({visualFarPercent=50,visualNearPercent=50,
          airAltitudePenaltyPercent=0,visualMaxAGL=800,opticalMaxAGL=1500})
        local p=S.profile('A-10C_2','air',{targetingPod=true},c)
        assert(p.visualMaxAGL==800 and p.opticalMaxAGL==1500)
        assert(S.discoveryChance('visual',9000,10000,800,p,c)==0.5)
        c.airAltitudePenaltyPercent=100
        assert(S.discoveryChance('visual',1000,10000,800,p,c)==0)
        local ground=S.profile('truck','ground',nil,c)
        assert(ground.visualMaxAGL==100 and ground.opticalMaxAGL==100)
        """)

    def test_invalid_tuning_is_rejected_before_scheduling(self):
        self.check("""
        for _,bad in ipairs({
          {visualFarPercent=81,visualNearPercent=80},{radarNearPercent=101},
          {airAltitudePenaltyPercent=-1},{retrySeconds=0},{visualMaxAGL=0},
          {gmtiFarPercent='high'},{opticalNearPercent=0/0}
        }) do
          assert(not pcall(S.probabilityConfig,bad))
          assert(not pcall(buildRolls,1,true,bad))
        end
        """)

    def test_invalid_random_samples_fail_closed_without_retry_storm(self):
        self.check("""
        for _,sample in ipairs({-1,1,0/0}) do
          local engine=buildRolls(10,true);draw=sample
          for i=0,20 do tick(engine,i) end
          assert(draws==1 and found==0 and engine:getDiagnostics().errors==1)
        end
        """)
