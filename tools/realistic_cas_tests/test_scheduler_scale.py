"""Campaign-sized scheduling contracts; fake LOS is not a DCS CPU benchmark."""

import unittest

from lupa.lua51 import LuaRuntime
from test_contact_core import CORE
from test_sensors import SOURCES


class CampaignScaleTests(unittest.TestCase):
    def runtime(self):
        rt = LuaRuntime()
        rt.execute(CORE)
        for source in SOURCES:
            rt.execute(source)
        return rt

    def test_729_observers_acquire_without_starvation_and_obey_shared_limits(self):
        rt = self.runtime()
        rt.execute("""
        local now,known,targets,observers=0,{},{},{}
        local e={cover='desert',light=1,weather=1,visibility=30000,
          visualTransmission=1,irTransmission=1}
        local engine=RealisticCAS.newDetection({clock=function()return now end,
          acquisitionSeconds=20,revisit=5,targetBudget=64,workBudget=1024,
          observerBudget=64,observerQuantum=128,losBudget=64,
          readObserver=function(id)return observers[id]end,
          readTarget=function(id)return targets[id]end,
          environment=function()return e end,lineOfSight=function()return true end,
          isRevealed=function(t)return known[t.name]~=nil end,
          reveal=function(t)known[t.name]=now;return true end})
        -- Separate sectors ensure every observer must complete its own search;
        -- one early shared contact cannot mask starvation of the other 728.
        for i=1,729 do
          local x=i*100000
          local air=i>550
          observers['o'..i]={side=2,point={x=x,y=air and 1000 or 2,z=0},
            forward={x=1,y=0,z=0},agl=air and 1000 or 2,role='CAS',radarOn=true}
          targets['t'..i]={name='t'..i,groupName='g'..i,side=1,
            point={x=x+1000,y=1,z=0},velocity={x=0,y=0,z=0}}
          assert(engine:addObserver('o'..i,RealisticCAS.Sensors.profile(
            air and 'FA-18C_hornet' or 'truck',air and 'air' or 'ground')))
          assert(engine:addTarget('t'..i))
          assert(not engine:addTarget('t'..i))
        end
        for i=1,480 do
          local before=engine:getDiagnostics();now=i*0.25;engine:tick()
          local after=engine:getDiagnostics()
          assert(after.work-before.work<=1024)
          assert(after.los-before.los<=64)
          assert(after.observerReads-before.observerReads<=128)
          assert(after.targetReads-before.targetReads<=64+1024)
        end
        local d=engine:getDiagnostics()
        assert(d.acquisitionCompletions==729,tostring(d.acquisitionCompletions))
        assert(d.acquisitionResets==0,tostring(d.acquisitionResets))
        assert(d.maxSweepGap<60,tostring(d.maxSweepGap))
        assert(d.overdueVisits==0)
        engine:stop();assert(engine:getDiagnostics().pendingJobs==0)
        """)

    def test_dense_observer_yields_to_other_observers_and_caps_los(self):
        rt = self.runtime()
        rt.execute("""
        local now,found,units=0,{},{}
        local engine=RealisticCAS.newDetection({clock=function()return now end,
          targetBudget=4096,workBudget=32,observerQuantum=8,observerBudget=16,losBudget=3,
          readObserver=function(id)
            if id=='dead' then return nil end
            return {side=2,point={x=id=='dense' and 0 or 100000,y=2,z=0},
              forward={x=1,y=0,z=0},agl=2}
          end,
          readTarget=function(id)return units[id]end,
          environment=function()return {cover='desert',light=1,weather=1,
            visibility=30000,visualTransmission=1,irTransmission=1}end,
          lineOfSight=function()return true end,
          reveal=function(t)found[t.name]=true;return true end})
        for i=1,1000 do
          units['t'..i]={name='t'..i,side=1,point={x=1000,y=1,z=0}}
          engine:addTarget('t'..i)
        end
        units.quiet={name='quiet',side=1,point={x=101000,y=1,z=0}}
        engine:addTarget('quiet')
        for _,id in ipairs({'dense','dead','quiet'}) do
          local p=RealisticCAS.Sensors.profile('truck','ground')
          assert(engine:addObserver(id,p));assert(not engine:addObserver(id,p))
        end
        for i=1,30 do
          local before=engine:getDiagnostics();now=now+0.25;engine:tick()
          local after=engine:getDiagnostics()
          assert(after.los-before.los<=3 and after.work-before.work<=32)
        end
        assert(found.quiet,'dense observer monopolised scheduler')
        assert(engine:getDiagnostics().losBudgetHits>0)
        assert(engine:getDiagnostics().pendingJobs>0)
        """)

    def test_real_observation_gap_resets_and_warns(self):
        rt = self.runtime()
        rt.execute("""
        local now,warnings,found=0,0,0
        local target={name='target',side=1,point={x=1000,y=1,z=0}}
        local engine=RealisticCAS.newDetection({clock=function()return now end,
          acquisitionSeconds=20,
          log=function(kind)if kind=='WARNING' then warnings=warnings+1 end end,
          readObserver=function()return {side=2,point={x=0,y=2,z=0},
            forward={x=1,y=0,z=0},agl=2}end,
          readTarget=function()return target end,
          environment=function()return {cover='desert',light=1,weather=1,
            visibility=30000,visualTransmission=1,irTransmission=1}end,
          lineOfSight=function()return true end,isRevealed=function()return false end,
          reveal=function()found=found+1;return true end})
        engine:addTarget('target');engine:addObserver('o',RealisticCAS.Sensors.profile('truck','ground'))
        engine:tick();now=5;engine:tick();now=100;engine:tick()
        assert(found==0 and warnings==1)
        assert(engine:getDiagnostics().acquisitionResets==1)
        """)

    def test_culling_rechecks_movement_coalition_changes_and_removal(self):
        rt = self.runtime()
        rt.execute("""
        local now,assessments=0,0
        local observer={side=2,point={x=0,y=2,z=0},forward={x=1,y=0,z=0},agl=2}
        local target={name='target',side=1,point={x=200000,y=1,z=0}}
        local engine=RealisticCAS.newDetection({clock=function()return now end,
          readObserver=function()return observer end,readTarget=function()return target end,
          environment=function()assessments=assessments+1;return {cover='desert',light=1,
            weather=1,visibility=30000,visualTransmission=1,irTransmission=1}end,
          lineOfSight=function()return true end,reveal=function()return true end})
        engine:addTarget('target');engine:addObserver('o',RealisticCAS.Sensors.profile('truck','ground'))
        local function step()now=now+5;engine:tick()end
        step();assert(assessments==0 and engine:getDiagnostics().culledObservers==1)
        target.point.x=1000;step();assert(assessments>0 and engine:getDiagnostics().reveals==1)
        target.side=2;local before=assessments;step();assert(assessments==before)
        target.side=1;target.point.x=200000;step();assert(assessments==before)
        observer.point.x=199000;step();assert(assessments>before)
        before=assessments;target=nil;step();assert(assessments==before)
        """)


if __name__ == "__main__":
    unittest.main()
