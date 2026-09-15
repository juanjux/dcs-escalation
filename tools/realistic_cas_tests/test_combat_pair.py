"""Combat measurement contracts; these do not simulate DCS targeting AI."""

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

FIXTURE = """
now=0; messages={}; handlers={}; queue={}; units={}; groups={}
env={info=function(s) messages[#messages+1]=s end}
trigger={action={outText=function() end}}
timer={getTime=function()return now end,
 scheduleFunction=function(f,a,t)queue[#queue+1]={f=f,a=a,t=t}end}
world={event={S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=23,S_EVENT_HIT=2,
 S_EVENT_KILL=28,S_EVENT_DEAD=8,S_EVENT_UNIT_LOST=30,S_EVENT_CRASH=5},
 addEventHandler=function(h)handlers[h]=true end,
 removeEventHandler=function(h)handlers[h]=nil end}
function unit(name)
 local u={name=name,life=100}
 function u:getName()return self.name end
 function u:isExist()return true end
 function u:getLife()return self.life end
 function u:getPoint()return {x=0,y=2000,z=0}end
 function u:inAir()return true end
 function u:getAmmo()return {}end
 units[name]=u;return u
end
Unit={getByName=function(n)return units[n]end}
Group={getByName=function(n)return groups[n]end}
for _,name in ipairs({'jet','blue','red1','red2','red3'})do unit(name)end
RCAS_COMBAT_TEST={variant='OFF',enabled=false,duration=60,groundOpenAt=180,
 acquisitionSeconds=20,ttl=600,scenarioHash='test',groups={},units={
 {name='jet',side='blue',kind='cas'}, {name='blue',side='blue',kind='ground'},
 {name='red1',side='red',kind='ground'}, {name='red2',side='red',kind='ground'},
 {name='red3',side='red',kind='ground'}}}
function event(id,source,target)
 for h in pairs(handlers)do h:onEvent({id=id,initiator=units[source],target=units[target]})end
end
function finish()
 while #queue>0 do
  local v=table.remove(queue,1);now=v.t
  local nextTime=v.f(v.a,now)
  if nextTime then queue[#queue+1]={f=v.f,a=v.a,t=nextTime}end
 end
end
"""


class CombatLogTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute(FIXTURE)
        self.rt.execute(
            Path(__file__).with_name("combat_smoke.lua").read_text(encoding="utf-8")
        )

    def test_native_kills_deduplicated_and_hit_is_not_attribution(self):
        self.rt.execute("""
        event(1,'jet');event(28,'jet','red1');event(8,'red1')
        event(28,nil,'red1') -- Late anonymous kill must not erase CAS attribution.
        event(28,'blue','red2');event(30,'red2')
        event(2,'jet','red3');event(8,'red3')
        event(28,'jet','blue');finish()
        local r=RCAS_COMBAT_TEST_RESULT
        assert(r.failures==0 and r.inconclusive==0 and r.casShots==1)
        assert(r.totals.red_ground.cas==1 and r.totals.red_ground.ground==1)
        assert(r.totals.red_ground.unknown==1 and r.totals.red_ground.alive==0)
        assert(r.totals.blue_ground.friendly==1)
        assert(next(handlers)==nil and #queue==0)
        assert(RealisticCAS==nil) -- OFF must not need or run the plugin.
        """)

    def test_no_cas_fire_is_inconclusive_not_a_balance_success(self):
        self.rt.execute("""
        finish();local r=RCAS_COMBAT_TEST_RESULT
        assert(r.failures==0 and r.inconclusive==1)
        assert(r.totals.red_ground.alive==3)
        """)

    def test_ground_fire_and_damage_do_not_become_cas_kills(self):
        self.rt.execute("""
        event(23,'blue');event(2,'blue','red1');units.red1.life=50
        finish();local r=RCAS_COMBAT_TEST_RESULT
        assert(r.groundShots==1 and r.casShots==0)
        assert(r.totals.red_ground.damaged==1 and r.totals.red_ground.alive==3)
        assert(r.totals.red_ground.ground==0)
        """)

    def test_hold_fire_never_changes_to_open_and_violation_is_flagged(self):
        self.rt = LuaRuntime()
        self.rt.execute(FIXTURE)
        self.rt.execute("""
        options={};cfg=RCAS_COMBAT_TEST;cfg.groundHoldFire=true;cfg.duration=240
        cfg.groups={{name='ground'}}
        groups.ground={isExist=function()return true end,
          getController=function()return {setOption=function(_,id,value)
            assert(id==0 and value==4);options[#options+1]=value end}end}
        """)
        self.rt.execute(
            Path(__file__).with_name("combat_smoke.lua").read_text(encoding="utf-8")
        )
        self.rt.execute("""
        event(1,'jet');event(23,'blue');finish()
        local r=RCAS_COMBAT_TEST_RESULT
        assert(#options==1 and options[1]==4)
        assert(r.failures==1 and r.inconclusive==1)
        """)

    def test_unlimited_ammo_is_reported_only_after_exceeding_native_initial_load(self):
        self.rt = LuaRuntime()
        self.rt.execute(FIXTURE)
        self.rt.execute("""
        function units.jet:getAmmo()return {{count=6,desc={typeName='weapons.missiles.AGM_65D'}}}end
        """)
        self.rt.execute(
            Path(__file__).with_name("combat_smoke.lua").read_text(encoding="utf-8")
        )
        self.rt.execute("""
        local weapon={getTypeName=function()return 'AGM_65D'end}
        for i=1,7 do
          for h in pairs(handlers)do h:onEvent({id=1,initiator=units.jet,weapon=weapon})end
        end
        finish();local matches=0
        for _,s in ipairs(messages)do
          if s:find('|AMMO_EXCEEDED_INITIAL|',1,true)then
            matches=matches+1;assert(s:find('|initial=6|shots=7',1,true))
          end
        end
        assert(matches==1 and RCAS_COMBAT_TEST_RESULT.failures==0)
        """)


if __name__ == "__main__":
    unittest.main()
