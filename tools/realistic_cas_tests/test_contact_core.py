"""Run with Python -B -m unittest discover -s tools/realistic_cas_tests -p test_contact_core.py.

Lua 5.1 contract tests, not a simulation of DCS detection or weapon behavior.
"""

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

PLUGIN = Path(__file__).resolve().parents[2] / "resources/plugins/realisticcas"
CORE = (PLUGIN / "core.lua").read_text(encoding="utf-8")
ADAPTER = (PLUGIN / "dcs.lua").read_text(encoding="utf-8")

CORE_FIXTURE = """
now=0; calls={}; logs={}; fail=false; crash=false
p={x=10,y=20,z=30}
function backend(id,visible)
  calls[#calls+1]={id=id,visible=visible}
  if crash then error('backend unavailable') end
  return not fail
end
function make(enabled)
  return RealisticCAS.new({enabled=enabled,ttl=10,retryInterval=2,
    clock=function() return now end,setVisible=backend,
    log=function(kind,id,detail) logs[#logs+1]=kind end})
end
s=make(true)
"""

ADAPTER_FIXTURE = """
now=0; commands={}; logs={}; groups={}; pending={}; handlers={}
timer={getTime=function() return now end,
  scheduleFunction=function(f,a,t) pending[#pending+1]={f=f,a=a,t=t};return #pending end}
env={info=function(message) logs[#logs+1]=message end}
world={event={S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=23,S_EVENT_BIRTH=15},
  addEventHandler=function(h) handlers[h]=true end,
  removeEventHandler=function(h) handlers[h]=nil end}
Group={Category={GROUND=2,AIRPLANE=0,SHIP=3},getByName=function(name) return groups[name] end}
function group(name,id,side,category)
  local g={name=name,id=id,side=side or 1,category=category or 2,exists=true,fail=false}
  function g:getName() return self.name end
  function g:getID() return self.id end
  function g:getCoalition() return self.side end
  function g:getCategory() return self.category end
  function g:isExist() return self.exists end
  g.controller={setCommand=function(_,c)
    if g.fail then error('controller failure') end
    commands[#commands+1]={id=g.id,hidden=c.params.value}
    assert(c.id=='SetInvisible'); g.hidden=c.params.value
    -- Native setCommand has no success boolean.
  end}
  function g:getController() return self.controller end
  groups[name]=g;return g
end
function emit(id,g)
  local u={isExist=function() return true end,getCoalition=function() return g.side end,
    getGroup=function() return g end,getPoint=function() return {x=1,y=2,z=3} end}
  for h in pairs(handlers) do h:onEvent({id=id,initiator=u}) end
end
function start(names)
  local targets={}
  for _,name in ipairs(names) do targets[#targets+1]={name=name,originalInvisible=false} end
  return RealisticCAS.start({enabled=true,ttl=10,debug=true,targets=targets})
end
"""


class ContactCoreTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(CORE)
        self.rt.execute(CORE_FIXTURE)

    def check(self, script):
        self.rt.execute(script)

    def test_opt_in_and_validation(self):
        self.check("""
        assert(not make(false):register('a',1));assert(#calls==0)
        for _,side in ipairs({0,3,-1}) do assert(not s:register('a',side)) end
        assert(not s:register('',1));assert(not s:register(0/0,1))
        assert(not s:register({},1));assert(#calls==0)
        assert(s:register('a',1));assert(not s:register('a',1));assert(#calls==1)
        assert(not s:observe('a',0,p));assert(not s:observe('a',1,p))
        assert(not s:observe('a',2,{x=0,y=math.huge,z=0}))
        assert(not s:observe('a',2,p,{}));assert(#calls==1)
        assert(not pcall(RealisticCAS.new,{ttl=0,clock=function()end,setVisible=backend}))
        """)

    def test_symmetry_fire_and_snapshots(self):
        self.check("""
        assert(s:register('red',1));assert(s:register('blue',2))
        assert(s:observe('red',2,p,'visual'));assert(s:fire('blue',p))
        assert(s:isRevealed('red',2));assert(s:isRevealed('blue',1))
        assert(not s:isRevealed('red',1));assert(s:getContact('red',1)==nil)
        p.x=999
        local c=s:getContact('red',2);assert(c.lastPosition.x==10)
        c.lastPosition.x=777;c.expiresAt=10000
        assert(s:getContact('red',2).lastPosition.x==10)
        now=10;assert(not s:isRevealed('red',2));assert(s:tick()==2)
        c=s:getContact('red',2)
        assert(not c.revealed and not c.backendVisible and c.lastPosition.x==10)
        assert(c.expiresAt==10 and c.observedAt==0)
        """)

    def test_renewal_bounded_heap_no_repeated_commands(self):
        self.check("""
        s:register(1,1);s:fire(1,p)
        for i=1,10000 do now=i/1000;assert(s:fire(1,p)) end
        assert(#calls==2);assert(s:getDiagnostics().scheduled==1)
        now=19.99;assert(s:tick()==0)
        now=20;assert(s:tick()==1);assert(#calls==3)
        assert(s:getDiagnostics().renewals==10000)
        assert(s:getDiagnostics().scheduled==0)
        """)

    def test_failure_registration_reveal_expiry_and_retry(self):
        self.check("""
        fail=true;assert(not s:register('a',1));assert(not s:isRegistered('a'))
        fail=false;s:register('a',1)
        crash=true;assert(not s:fire('a',p));assert(s:getContact('a',2)==nil)
        crash=false;s:fire('a',p)
        now=10;fail=true;assert(s:tick()==1)
        local c=s:getContact('a',2);assert(not c.revealed and c.backendVisible)
        now=11;assert(s:tick()==0)
        fail=false;now=12;assert(s:tick()==1)
        assert(not s:getContact('a',2).backendVisible)
        assert(s:getDiagnostics().backendErrors==3)
        """)

    def test_renewal_cancels_pending_failed_expiry(self):
        self.check("""
        s:register(1,1);s:fire(1,p);now=10;fail=true;s:tick()
        now=11;fail=false;assert(s:fire(1,p))
        now=12;assert(s:tick()==0);assert(s:isRevealed(1,2))
        now=21;assert(s:tick()==1);assert(not s:isRevealed(1,2))
        """)

    def test_budget_unregister_and_stop_retry(self):
        self.check("""
        for i=1,500 do s:register(i,1);s:fire(i,p) end
        now=10;assert(s:tick(37)==37)
        assert(s:getDiagnostics().scheduled==463)
        for i=1,500 do assert(not s:isRevealed(i,2)) end
        assert(s:unregister(250,true));assert(not s:isRegistered(250))
        fail=true;assert(not s:stop())
        assert(s:getDiagnostics().registered>0)
        fail=false;assert(s:stop());assert(s:getDiagnostics().registered==0)
        assert(s:getDiagnostics().scheduled==0);assert(not s:getDiagnostics().enabled)
        """)

    def test_random_heap_matches_reference(self):
        self.check("""
        math.randomseed(183);local expected={};local actual={}
        s=RealisticCAS.new({enabled=true,ttl=10,clock=function()return now end,
          setVisible=function(id,v) actual[id]=v;return true end})
        for step=1,12000 do
          now=now+math.random()/20
          local id=math.random(1,500)
          if not expected[id] then
            s:register(id,1);expected[id]={due=-1}
          elseif math.random()<0.12 then
            assert(s:unregister(id,true));expected[id]=nil;actual[id]=nil
          else s:fire(id,p);expected[id].due=now+10 end
          s:tick(1000)
          local n,scheduled=0,0
          for k,v in pairs(expected) do
            n=n+1;local visible=v.due>now
            if visible then scheduled=scheduled+1 end
            assert(actual[k]==visible,'heap mismatch at step '..step)
          end
          assert(s:getDiagnostics().registered==n)
          assert(s:getDiagnostics().scheduled==scheduled)
        end
        now=now+11;s:tick(1000);assert(s:getDiagnostics().scheduled==0)
        """)


class DcsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(CORE)
        self.rt.execute(ADAPTER_FIXTURE)
        self.rt.execute(ADAPTER)

    def check(self, script):
        self.rt.execute(script)

    def test_inert_and_all_or_nothing_input_validation(self):
        self.check("""
        group('r',1);assert(#commands==0 and next(handlers)==nil and #pending==0)
        assert(RealisticCAS.start({})==nil)
        assert(not pcall(RealisticCAS.start,{enabled=true,targets={
          {name='r',originalInvisible=false},{name='bad',originalInvisible=true}}}))
        assert(#commands==0 and next(handlers)==nil and #pending==0)
        """)

    def test_scope_events_and_expiry(self):
        self.check("""
        r=group('r',1);b=group('b',2,2);n=group('neutral',3,0)
        plane=group('plane',4,1,0);outside=group('outside',5)
        a=start({'r','b','neutral','plane'})
        assert(r.hidden and b.hidden and n.hidden==nil and plane.hidden==nil)
        assert(#commands==2)
        emit(1,r);assert(not r.hidden and a.service:isRevealed(1,2))
        emit(23,b);assert(not b.hidden and a.service:isRevealed(2,1))
        emit(1,outside);assert(outside.hidden==nil)
        now=5;emit(23,b);assert(#commands==4)
        now=10;assert(pending[1].f(nil,now)==11)
        assert(r.hidden and not b.hidden)
        now=15;pending[1].f(nil,now);assert(b.hidden)
        assert(a:stop());assert(not r.hidden and not b.hidden)
        assert(next(handlers)==nil and pending[1].f(nil,now)==nil)
        """)

    def test_late_birth_and_replacement(self):
        self.check("""
        a=start({'late'});assert(#commands==0)
        r=group('late',10);emit(15,r);assert(r.hidden)
        emit(1,r);emit(15,r);assert(not r.hidden and #commands==2)
        r.exists=false;r2=group('late',11);emit(15,r2)
        assert(r2.hidden and not a.service:isRegistered(10))
        assert(a.service:isRegistered(11))
        local other=group('unlisted',11)
        assert(not a:observe('unlisted',2,{x=1,y=2,z=3},'visual'))
        """)

    def test_duplicate_load_does_not_install_twice(self):
        self.check("r=group('r',1);a=start({'r'})")
        self.rt.execute(CORE)
        self.rt.execute(ADAPTER)
        self.check("""
        local duplicate,why=start({'r'})
        assert(duplicate==nil and why=='already running')
        assert(#pending==1 and #commands==1);assert(a:stop())
        assert(start({'r'}))
        """)

    def test_partial_stop_retry_does_not_reregister_or_hide(self):
        self.check("""
        r=group('r',1);b=group('b',2,2);a=start({'r','b'})
        r.fail=true;assert(not a:stop());assert(not b.hidden and r.hidden)
        local count=#commands
        emit(15,b);emit(1,b);now=100;pending[1].f(nil,now)
        assert(#commands==count);assert(not a:observe('b',1,{x=0,y=0,z=0}))
        r.fail=false;assert(a:stop());assert(not r.hidden and not b.hidden)
        assert(next(handlers)==nil and not RealisticCAS._running)
        """)

    def test_startup_failure_leaves_no_hidden_groups(self):
        self.check("""
        r=group('r',1)
        timer.scheduleFunction=function() error('scheduler failed') end
        assert(not pcall(start,{'r'}))
        assert(r.hidden==nil and #commands==0 and next(handlers)==nil)
        assert(not RealisticCAS._running)
        """)

    def test_visibility_failure_logged(self):
        self.check("""
        r=group('r',1);r.fail=true;a=start({'r'})
        assert(not a.service:isRegistered(1))
        local found=false
        for _,line in ipairs(logs) do if line:find('BACKEND_ERROR',1,true) then found=true end end
        assert(found);r.fail=false;emit(15,r);assert(a.service:isRegistered(1))
        """)

    def run_smoke(self, simulate_fire):
        self.check("""
        trigger={action={outText=function()end}}
        AI={Option={Ground={id={ROE=0},val={ROE={OPEN_FIRE=2,WEAPON_HOLD=4}}}}}
        for _,g in ipairs({group('RED_ARMOUR',1),group('BLUE_ARMOUR',2,2)}) do
          g.controller.setOption=function()end
          -- No engine detection claim: explicitly return no contact in the double.
          g.controller.isTargetDetected=function()return false,false,false,false,nil,nil end
          function g:getUnit() return {getPoint=function()return {x=1,y=2,z=3}end} end
        end
        """)
        self.rt.execute(
            (Path(__file__).parent / "core_smoke.lua").read_text(encoding="utf-8")
        )
        if simulate_fire:
            self.check("""
            timer.scheduleFunction(function()emit(1,groups.RED_ARMOUR)end,nil,50)
            timer.scheduleFunction(function()emit(23,groups.BLUE_ARMOUR)end,nil,100)
            """)
        self.check("""
        local steps=0
        while #pending>0 do
          table.sort(pending,function(a,b)return a.t<b.t end)
          local nextCall=table.remove(pending,1);now=nextCall.t
          local again=nextCall.f(nextCall.a,now)
          if again then pending[#pending+1]={f=nextCall.f,a=nextCall.a,t=again} end
          steps=steps+1;assert(steps<1500,'unbounded smoke scheduler')
        end
        assert(next(handlers)==nil and not RealisticCAS._running)
        assert(not groups.RED_ARMOUR.hidden and not groups.BLUE_ARMOUR.hidden)
        for _,line in ipairs(logs) do assert(not line:find('|ERROR|',1,true),line) end
        """)
        return "\n".join(self.rt.globals().logs.values())

    def test_smoke_runner_with_injected_events(self):
        logs = self.run_smoke(True)
        self.assertNotIn("|FAIL|", logs)
        self.assertIn("failures=0|redFire=1|blueFire=1", logs)

    def test_smoke_runner_does_not_pass_without_real_fire(self):
        logs = self.run_smoke(False)
        self.assertIn("|FAIL|", logs)
        self.assertIn("otherwise invalid fire coverage", logs)
        self.assertNotIn("failures=0|", logs)


if __name__ == "__main__":
    unittest.main()
